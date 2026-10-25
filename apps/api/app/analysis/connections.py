"""Owner/project-scoped local GitHub reads. Credentials never enter reports.

Token ciphertext uses the existing context-bound store with its own master.
Desktop CLI tokens remain in memory. All remote requests use fixed-origin GETs.
"""
import os
import re
import shutil
import subprocess
import time
from datetime import timedelta
from uuid import UUID, uuid4
from pydantic import Field, SecretStr, model_validator
from sqlalchemy import select
from app.auth.schemas import Input
from app.core.errors import ApiError
from app.integrations.github.client import GitHubError, Transport, AUTH_DEADLINE
from app.security.secrets.store import SecretUnavailable
from app.security.tokens import now, utc
from app.security.audit import audit
from .models import RepositoryReadConnection
from .schemas import repository_name
from app.policies.schemas import Confirmed


class ActivityRead(Input):
    repository_urls: list[str] = Field(min_length=1,max_length=8)
    connection_id: UUID | None = None
    read_confirmed: Confirmed

    @model_validator(mode='after')
    def scope(self):
        names=[repository_name(v) for v in self.repository_urls]
        if len(set(n.casefold() for n in names))!=len(names):raise ValueError('Choose each repository once.')
        self.repository_urls=['https://github.com/'+n for n in names]
        return self


def activity(client, names, authorized=False):
    from datetime import datetime,timezone
    rows=[]
    deadline=AUTH_DEADLINE.set(time.monotonic()+60)
    try:
        for name in names:
            raw,_=client.get('/repos/'+name)
            if not isinstance(raw,dict) or raw.get('full_name','').casefold()!=name.casefold() or type(raw.get('private')) is not bool:
                raise GitHubError('analysis_repository_identity_changed')
            if raw['private'] and not authorized:raise GitHubError('analysis_public_repository_required')
            try:
                commits,_=client.get('/repos/'+name+'/commits',{'per_page':1,'sha':str(raw.get('default_branch') or '')})
            except GitHubError as error:
                if error.code=='github_empty_or_conflicting_repository':commits=[]
                else:raise
            if not isinstance(commits,list):raise GitHubError('github_invalid_response')
            date=None
            if commits:
                try:
                    value=commits[0]['commit']['committer']['date']
                    parsed=datetime.fromisoformat(value.replace('Z','+00:00'))
                    if parsed.tzinfo is None or not 1970<=parsed.year<=2099 or parsed>now():raise ValueError()
                    date=parsed.astimezone(timezone.utc).isoformat()
                except (KeyError,TypeError,AttributeError,ValueError):raise GitHubError('github_invalid_response') from None
            rows.append({'full_name':name,'private':raw['private'],'latest_commit_at':date})
        return rows
    finally:AUTH_DEADLINE.reset(deadline)


class ConnectionSave(Input):
    expected_version: int = Field(strict=True, ge=0)
    method: str = Field(pattern='^(token|cli)$')
    token: SecretStr | None = None
    repository_urls: list[str] = Field(min_length=1, max_length=8)
    access_confirmed: Confirmed

    @model_validator(mode='after')
    def scope(self):
        if not self.access_confirmed:
            raise ValueError('Confirm the selected repository read.')
        names = [repository_name(v) for v in self.repository_urls]
        if len(set(n.casefold() for n in names)) != len(names):
            raise ValueError('Choose each repository once.')
        self.repository_urls = ['https://github.com/' + n for n in names]
        if self.method == 'token':
            value = self.token.get_secret_value() if self.token else ''
            if not re.fullmatch(r'github_pat_[A-Za-z0-9_]{20,245}', value):
                raise ValueError('Use a fine-grained GitHub token.')
        elif self.token is not None:
            raise ValueError('Do not send a token for CLI access.')
        return self


def enabled(settings):
    if not settings.repository_private_reads_enabled:
        raise ApiError(409, 'analysis_private_reads_disabled', 'Private repository reads are disabled in this installation.')


def cli_token(settings, username=None):
    enabled(settings)
    if not settings.desktop_enabled:
        raise ApiError(409, 'analysis_cli_desktop_required', 'GitHub CLI access is available only in personal desktop mode.')
    executable = shutil.which('gh')
    if not executable:
        raise ApiError(409, 'analysis_cli_unavailable', 'GitHub CLI is not installed. Use a fine-grained token instead.')
    # Saved github.com login only; do not silently select an inherited CI token.
    env = {k:v for k,v in os.environ.items() if k.upper() not in
        {'GH_TOKEN','GITHUB_TOKEN','GH_ENTERPRISE_TOKEN','GITHUB_ENTERPRISE_TOKEN','GH_HOST','GITHUB_HOST'}}
    env.update(GH_PROMPT_DISABLED='1', GH_NO_UPDATE_NOTIFIER='1')
    args=[executable,'auth','token','--hostname','github.com']
    if username is not None:
        if not re.fullmatch(r'[A-Za-z0-9-]{1,39}',username):raise ApiError(409,'analysis_cli_signed_out','Reconnect the selected GitHub account.')
        args += ['--user',username]
    try:
        result = subprocess.run(args,
            capture_output=True, timeout=8, env=env, creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        value = result.stdout.decode('ascii').strip()
        if result.returncode or not re.fullmatch(r'[A-Za-z0-9_]{20,4096}',value):
            raise ValueError()
        return value
    except (OSError, subprocess.TimeoutExpired, ValueError, UnicodeError):
        raise ApiError(409, 'analysis_cli_signed_out', 'Sign in to github.com with GitHub CLI, or use a fine-grained token.') from None


def context(row):
    return f'github-read-v1:{row.workspace_id}:{row.project_id}:{row.owner_id}:{row.id}'


def own_connection(db, project, actor, connection_id=None, *, lock=False):
    q = select(RepositoryReadConnection).where(RepositoryReadConnection.project_id==project.id,
        RepositoryReadConnection.workspace_id==project.workspace_id, RepositoryReadConnection.owner_id==actor).execution_options(populate_existing=True)
    if connection_id: q = q.where(RepositoryReadConnection.id==connection_id)
    if lock: q = q.with_for_update()
    row = db.scalar(q)
    if connection_id and not row:
        raise ApiError(404,'not_found','This connection does not exist.')
    return row


def view(row):
    if not row: return None
    return {'id':str(row.id),'version':row.version,'method':row.method,'username':row.username,
        'repository_urls':row.repository_urls,'active':row.active and utc(row.expires_at)>now(),
        'expires_at':row.expires_at}


def checked(db, project, actor, connection_id, settings, *, names=(), lock=False):
    enabled(settings)
    row = own_connection(db,project,actor,UUID(str(connection_id)),lock=lock)
    if not row.active or utc(row.expires_at)<=now():
        raise ApiError(409,'analysis_connection_expired','Reconnect GitHub before continuing this private analysis.')
    allowed = {repository_name(u).casefold() for u in row.repository_urls}
    if any(n.casefold() not in allowed for n in names):
        raise ApiError(403,'analysis_repository_not_authorized','Reconnect GitHub with these repository links explicitly selected.')
    return row


class AuthorizedRepositoryClient:
    def __init__(self, token, names, transport=None):
        self._token = token
        self._names = {n.casefold() for n in names}
        self.transport = transport or Transport()

    def get(self, path, params=None):
        parts = path.split('/')
        if len(parts)<4 or parts[1]!='repos' or '/'.join(parts[2:4]).casefold() not in self._names:
            raise GitHubError('analysis_repository_not_authorized')
        return self.transport.request('GET','https://api.github.com',path,token=self._token,params=params)


def client_for(row, store, settings, transport=None):
    try:
        token = cli_token(settings,row.username) if row.method=='cli' else store.read(row.credential_ref,context(row))
    except SecretUnavailable:
        raise ApiError(409,'analysis_credential_unavailable','Reconnect GitHub; the local credential cannot be opened.') from None
    return AuthorizedRepositoryClient(token,[repository_name(u) for u in row.repository_urls],transport)


def verify(body, settings, transport=None):
    enabled(settings)
    token = cli_token(settings) if body.method=='cli' else body.token.get_secret_value()
    try:
        user,_ = (transport or Transport()).request('GET','https://api.github.com','/user',token=token)
        if not isinstance(user,dict) or type(user.get('id')) is not int or not re.fullmatch(r'[A-Za-z0-9-]{1,39}',str(user.get('login',''))):
            raise GitHubError('github_invalid_response')
    except GitHubError as error:
        raise ApiError(409,error.code,'GitHub could not verify this connection. Check token access, expiration and the recorded rate limit.',error.retry_seconds) from None
    return token,user['login']


def save(db, project, actor, body, token, username, writes):
    row = own_connection(db,project,actor,lock=True)
    if (row.version if row else 0)!=body.expected_version:
        raise ApiError(409,'analysis_connection_stale','The connection changed. Refresh before reconnecting.')
    if not row:
        row = RepositoryReadConnection(id=uuid4(),workspace_id=project.workspace_id,
            project_id=project.id,owner_id=actor,version=0)
        db.add(row)
    old = row.credential_ref
    row.method=body.method;row.username=username;row.repository_urls=body.repository_urls
    row.expires_at=now()+timedelta(days=30);row.active=True;row.version+=1
    row.credential_ref=writes.write(token,context(row)) if body.method=='token' else None
    audit(db,'analysis.github_connected',actor_id=actor,workspace_id=project.workspace_id,
        project_id=project.id,subject_id=row.id,reason='Explicit selected repository reads; credential omitted.',
        details={'method':row.method,'repository_count':len(row.repository_urls)})
    db.flush()
    return row,old
