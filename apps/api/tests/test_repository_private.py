"""Local private capture and credentials. All remote responses are synthetic."""
import json
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.main import create_app
from app.analysis.models import RepositoryReadConnection, RepositoryAnalysis
from app.analysis.connections import cli_token, context, AuthorizedRepositoryClient
from app.core.errors import ApiError
from app.integrations.github.client import GitHubError
from app.security.secrets.encrypted import EncryptedCredentialStore, initialize
from app.security.secrets.store import SecretUnavailable
from tests.test_repository_analysis import PublicFixture, DATES, finish, start, post
from tests.auth_helpers import bootstrap, mutation

TOKEN='github_pat_'+'synthetic_test_only_'*3


class PrivateTransport:
    def __init__(self): self.fixture=PublicFixture();self.calls=[];self.callback=None
    def request(self,method,origin,path,**kwargs):
        self.calls.append((method,origin,path))
        assert method=='GET' and origin=='https://api.github.com'
        assert kwargs.get('token')==TOKEN
        if path=='/user':return {'id':1,'login':'alice'},False
        if self.callback:self.callback();self.callback=None
        raw,more=self.fixture.get(path,kwargs.get('params'))
        if len(path.split('/'))==4:raw['private']=True
        return raw,more


@pytest.fixture
def private_env(settings,database,tmp_path):
    settings=settings.model_copy(update={'environment':'test','repository_private_reads_enabled':True,
        'repository_credential_root':str(tmp_path/'github-credentials'),
        'repository_master_key_file':str(tmp_path/'github-master/master.key')})
    initialize(settings.repository_master_key_file,settings.repository_credential_root)
    store=EncryptedCredentialStore(settings.repository_credential_root,settings.repository_master_key_file)
    transport=PrivateTransport()
    app=create_app(settings,database,repository_store=store,repository_transport=transport)
    with TestClient(app) as client:
        owner=bootstrap(client,database)
        root=f"/api/v1/workspaces/{owner['workspace']['id']}/projects/{owner['project']['id']}/analysis"
        yield {'client':client,'database':database,'owner':owner,'root':root,'settings':settings,
            'store':store,'transport':transport}


def connect(e,version=0,**changes):
    body={'expected_version':version,'method':'token','token':TOKEN,
        'repository_urls':['https://github.com/team/game'],'access_confirmed':True,**changes}
    result=mutation(e['client'],e['root']+'/connection',body,method='PUT')
    assert result.status_code==200,result.text
    assert TOKEN not in result.text and 'credential_ref' not in result.text
    return result.json()['connection']


def private_start(e,connection,**changes):
    return post(e,'/runs',{'request_id':str(uuid4()),'repository_urls':['https://github.com/team/game'],
        'public_read_confirmed':True,'connection_id':connection['id'],**DATES,**changes},201)


def test_private_capture_uses_scoped_encrypted_credential_and_never_discloses_it(private_env):
    e=private_env;c=connect(e);report=finish(e,private_start(e,c))
    assert report['report']['repositories'][0]['private'] is True
    assert report['report']['contributors'] and report['report']['outcomes']
    response=e['client'].get(e['root']);assert TOKEN not in response.text and 'credential_ref' not in response.text
    with e['database'].session() as db:
        row=db.scalar(select(RepositoryReadConnection))
        assert e['store'].read(row.credential_ref,context(row))==TOKEN
        with pytest.raises(SecretUnavailable):e['store'].read(row.credential_ref,'another-project')
        assert TOKEN not in json.dumps(report)
    for path in e['store'].root.iterdir():assert TOKEN.encode() not in path.read_bytes()


def test_private_repository_needs_explicit_connection_and_selected_repository(private_env):
    e=private_env;c=connect(e);before=len(e['transport'].calls)
    post(e,'/runs',{'request_id':str(uuid4()),'repository_urls':['https://github.com/team/other'],
        'public_read_confirmed':True,'connection_id':c['id'],**DATES},403)
    assert len(e['transport'].calls)==before
    e['client'].app.state.public_repository_client=e['transport'].fixture
    original=e['transport'].fixture.get
    def private(path,params=None):
        raw,more=original(path,params)
        if len(path.split('/'))==4:raw['private']=True
        return raw,more
    e['transport'].fixture.get=private
    row=post(e,'/runs',{'request_id':str(uuid4()),'repository_urls':['https://github.com/team/game'],
        'public_read_confirmed':True,**DATES},201)
    row=post(e,'/runs/'+row['id']+'/advance',{'expected_version':row['version']})
    assert row['state']=='failed' and row['error_code']=='analysis_public_repository_required'


def test_disconnect_during_fetch_discards_response_and_reconnection_can_resume(private_env):
    e=private_env;c=connect(e);run=private_start(e,c)
    def revoke():
        with e['database'].session() as db:
            row=db.scalar(select(RepositoryReadConnection));row.active=False;row.version+=1;db.commit()
    e['transport'].callback=revoke
    failed=post(e,'/runs/'+run['id']+'/advance',{'expected_version':run['version']})
    assert failed['state']=='failed' and failed['error_code']=='analysis_connection_expired'
    with e['database'].session() as db:
        from uuid import UUID
        row=db.get(RepositoryAnalysis,UUID(run['id']))
        assert row.progress['cursor']==0 and row.progress['repositories']==[] and row.progress['sources']==[]
    new=connect(e,2);assert new['id']==c['id']
    retry=post(e,'/runs/'+run['id']+'/retry',{'expected_version':failed['version']})
    assert finish(e,retry)['report']['outcomes']


def test_rotation_during_fetch_discards_response(private_env):
    e=private_env;c=connect(e);run=private_start(e,c)
    def changed():
        with e['database'].session() as db:
            row=db.scalar(select(RepositoryReadConnection));row.version+=1;db.commit()
    e['transport'].callback=changed
    failed=post(e,'/runs/'+run['id']+'/advance',{'expected_version':run['version']})
    assert failed['state']=='failed' and failed['error_code']=='analysis_connection_changed'
    assert failed['source_count']==0 and failed['completed_tasks']==0


def test_disconnect_removes_ciphertext_and_keeps_completed_private_report(private_env):
    e=private_env;c=connect(e);report=finish(e,private_start(e,c))
    result=post(e,'/connection/disconnect',{'expected_version':c['version']})
    assert not result['connection']['active'] and result['ciphertext_removed']
    assert list(e['store'].root.iterdir())==[]
    retained=e['client'].get(e['root'],params={'report_id':report['id']}).json()
    assert retained['dashboard']['report']['repositories'][0]['private'] is True
    assert retained['dashboard']['outcomes']


@pytest.mark.parametrize('changes',[{'access_confirmed':False},{'token':'invalid'},
    {'repository_urls':['https://github.com/team/game?token=unsafe']}, {'method':'cli','token':TOKEN}])
def test_invalid_connection_input_is_redacted_without_network_reads(private_env,changes):
    e=private_env
    body={'expected_version':0,'method':'token','token':TOKEN,
        'repository_urls':['https://github.com/team/game'],'access_confirmed':True,**changes}
    response=mutation(e['client'],e['root']+'/connection',body,method='PUT')
    assert response.status_code==422 and TOKEN not in response.text
    assert e['transport'].calls==[]


def test_credential_cannot_be_used_for_another_owner_or_project(private_env):
    e=private_env;c=connect(e)
    with e['database'].session() as db:
        from app.projects.models import Project
        original=db.scalar(select(Project));other=Project(workspace_id=original.workspace_id,
            name='Other synthetic project',timezone='UTC',currency='USD')
        db.add(other);db.flush();other_id=str(other.id);db.commit()
    body={'request_id':str(uuid4()),'repository_urls':['https://github.com/team/game'],
        'public_read_confirmed':True,'connection_id':c['id'],**DATES}
    root=e['root'].replace(e['owner']['project']['id'],other_id)
    response=mutation(e['client'],root+'/runs',body)
    assert response.status_code in {403,404}


def test_authenticated_client_rejects_other_repository_and_nonrepository_endpoints():
    c=AuthorizedRepositoryClient(TOKEN,['team/game'])
    for path in ['/user','/repos/team/other','//api.github.com/repos/team/game']:
        with pytest.raises(GitHubError):c.get(path)


def test_cli_requires_desktop_and_uses_saved_fixed_hostname_without_inherited_tokens(private_env,monkeypatch):
    e=private_env
    with pytest.raises(ApiError):cli_token(e['settings'])
    settings=e['settings'].model_copy(update={'desktop_enabled':True})
    monkeypatch.setenv('GH_TOKEN','synthetic-unselected-env-token')
    monkeypatch.setattr('app.analysis.connections.shutil.which',lambda name:'trusted-gh.exe')
    def run(args,**kwargs):
        from types import SimpleNamespace
        assert args in [['trusted-gh.exe','auth','token','--hostname','github.com'],
            ['trusted-gh.exe','auth','token','--hostname','github.com','--user','alice']]
        assert 'GH_TOKEN' not in kwargs['env'] and kwargs['timeout']==8
        return SimpleNamespace(returncode=0,stdout=TOKEN.encode())
    monkeypatch.setattr('app.analysis.connections.subprocess.run',run)
    assert cli_token(settings)==TOKEN
    assert cli_token(settings,'alice')==TOKEN


def test_expired_connection_stops_before_network_and_leaves_actionable_failed_report(private_env):
    from datetime import timedelta
    from app.security.tokens import now
    e=private_env;c=connect(e);run=private_start(e,c)
    with e['database'].session() as db:
        row=db.scalar(select(RepositoryReadConnection));row.expires_at=now()-timedelta(seconds=1);db.commit()
    calls=len(e['transport'].calls)
    row=post(e,'/runs/'+run['id']+'/advance',{'expected_version':run['version']})
    assert row['state']=='failed' and row['error_code']=='analysis_connection_expired'
    assert len(e['transport'].calls)==calls


def test_activity_preview_uses_private_scope_without_creating_report(private_env):
    e=private_env;c=connect(e)
    preview=post(e,'/activity',{'repository_urls':['https://github.com/team/game'],
        'connection_id':c['id'],'read_confirmed':True})
    assert preview['repositories'][0]['private'] is True
    assert preview['repositories'][0]['latest_commit_at']=='2026-01-15T00:00:00+00:00'
    assert e['client'].get(e['root']).json()['runs']==[]


def test_empty_repository_completes_with_explicit_omission_and_no_contributor_claim(private_env):
    e=private_env;c=connect(e);original=e['transport'].request
    def empty(method,origin,path,**kwargs):
        if path.endswith('/commits'):raise GitHubError('github_empty_or_conflicting_repository')
        return original(method,origin,path,**kwargs)
    e['transport'].request=empty
    report=finish(e,private_start(e,c))
    assert report['report']['source_count']==0 and report['report']['contributors']==[]
    assert report['report']['repositories'][0]['history_unavailable'] is True
    assert any('commit_history_unavailable_or_empty' in x for x in report['omissions'])


def test_another_project_admin_cannot_reuse_or_read_a_personal_connection(private_env):
    from tests.auth_helpers import invite,accept
    e=private_env;c=connect(e)
    invitation=invite(e['client'],e['owner']['workspace']['id'],project_id=e['owner']['project']['id'],role='admin')
    with TestClient(e['client'].app) as other:
        accept(other,invitation['token'])
        overview=other.get(e['root']).json();assert overview['connection'] is None
        response=mutation(other,e['root']+'/runs',{'request_id':str(uuid4()),
            'repository_urls':['https://github.com/team/game'],'public_read_confirmed':True,
            'connection_id':c['id'],**DATES})
        assert response.status_code==404


@pytest.mark.parametrize('change',[{'environment':'staging'},{'allowed_hosts':['public.example']},
    {'allowed_origins':['https://public.example']},{'repository_master_key_file':'inside/key','repository_credential_root':'inside'}])
def test_private_tokens_are_rejected_for_remote_or_unseparated_configuration(settings,change):
    from app.core.config import Settings
    from pydantic import ValidationError
    values=settings.model_dump();values.update(environment='test',repository_private_reads_enabled=True);values.update(change)
    with pytest.raises(ValidationError):Settings(**values)


def test_capture_byte_bound_serializes_retained_sources_once_per_page(monkeypatch):
    from app.analysis import capture
    from app.integrations.github.normalization import canonical
    fixture=PublicFixture();p=capture.initial(['team/game'])
    raw,_=fixture.get('/repos/team/game');capture.absorb(p,p['tasks'][0],raw,False,DATES)
    # Repeated synthetic rows exercise page processing and the exact byte guard.
    commits,_=fixture.get('/repos/team/game/commits')
    capture.absorb(p,{'repository':'team/game','kind':'commits'},commits,False,DATES)
    p['sources']=[p['sources'][0] for _ in range(100)]
    calls=[]
    def tracked(value):calls.append(1);return canonical(value)
    monkeypatch.setattr(capture,'canonical',tracked)
    capture.absorb(p,{'repository':'team/game','kind':'commits'},commits*20,False,DATES)
    assert len(calls)==120
