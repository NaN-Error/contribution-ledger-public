"""Project-scoped authorization and evidence commands. No ledger/finance writes.

Mutations take the existing workspace lock. External authorization exchanges
happen outside that lock and consume their session-bound state before sending
credentials. Every commit rechecks current project access.
"""
from datetime import timedelta
from hashlib import sha256
from secrets import token_urlsafe
from uuid import UUID, uuid4
from sqlalchemy import select, func
from app.auth.models import User
from app.core.errors import ApiError
from app.projects.authorization import project_access, not_found
from app.projects.models import WorkspaceMembership
from app.policies.service import digest
from app.security.audit import audit
from app.security.tokens import now, utc
from app.security.secrets.store import SecretUnavailable
from app.integrations.github.client import GitHubError
from app.integrations.github.models import (GitHubAuthFlow, GitHubConnection, GitHubRepository, GitHubImport,
    GitHubFetchTask, GitHubSourceVersion, GitHubIdentity, GitHubIdentityDecision, GitHubEvidenceLink)
from app.jobs.models import OutboxMessage

NOTICE = 'Imported activity is evidence only. No import, identity link or source attachment issues contribution units.'


def external_error(error):
    code = error.code if isinstance(error, GitHubError) else 'github_secret_unavailable'
    messages = {
        'github_not_configured': 'GitHub is disabled. Follow the operator GitHub setup guide; the manual app remains available.',
        'github_secret_unavailable': 'The mounted GitHub credentials are unavailable. Ask the operator to inspect configuration.',
        'github_installation_not_authorized': 'This GitHub account did not prove access to the selected installation.',
        'github_repository_admin_required': 'No repository with administrator access was verified for this GitHub account.',
        'github_read_permissions_required': 'Use a dedicated GitHub App with the documented read-only permissions and no write grants.',
        'github_installation_mismatch': 'The installation is suspended or belongs to another GitHub App.',
        'github_rate_limited': 'GitHub rate-limited the request. Do not retry before the recorded retry time.',
        'github_forbidden': 'GitHub denied the request or applied a secondary limit. Verify access and wait before retrying.',
        'github_access_denied': 'GitHub access was denied or the repository is unavailable. Verify the App installation.',
        'github_authorization_timeout': 'GitHub authorization exceeded its bounded exchange window. Start a new authorization attempt.',
        'github_authorization_failed': 'GitHub authorization could not be completed. Start a new authorization flow.',
        'github_authorization_catalog_limit': 'The authorization catalog exceeds this bounded pilot. Use a smaller selected-repository App installation.',
        'github_redirect_rejected': 'GitHub redirected this resource. Reauthorize to review its current repository identity.',
    }
    return ApiError(503 if code not in {'github_installation_not_authorized','github_repository_admin_required','github_installation_mismatch'} else 403,
                    code, messages.get(code, 'GitHub did not return a usable bounded response. Review the connection and try a new authorization flow.'))


def context(db, identity, workspace_id, project_id, *, manage=False, lock=False):
    project, role = project_access(db, workspace_id, project_id, identity.user.id, manage=manage, lock=lock)
    if role not in {'admin','reviewer'}:
        raise ApiError(403, 'github_source_access', 'Only project administrators and reviewers can browse the imported repository store. Other contributors see explicitly shared work-package evidence.')
    return project, role


def row_in_project(db, cls, project, row_id, lock=False):
    stmt = select(cls).where(cls.id == row_id, cls.workspace_id == project.workspace_id, cls.project_id == project.id)
    if lock: stmt = stmt.with_for_update().execution_options(populate_existing=True)
    row = db.scalar(stmt)
    if row is None: raise not_found()
    return row


def begin(db, project, identity, body, client, settings):
    client.ensure_configured()
    total = db.scalar(select(func.count()).select_from(GitHubAuthFlow).where(
        GitHubAuthFlow.created_by == identity.user.id, GitHubAuthFlow.expires_at > now(),
        GitHubAuthFlow.state.in_(['pending','exchanging','verified'])))
    if total >= 5: raise ApiError(429, 'github_flow_limit', 'Five authorization attempts are already open. Finish one or wait for expiry.')
    state = token_urlsafe(32)
    url = client.authorize_url(state)
    row = GitHubAuthFlow(id=uuid4(), workspace_id=project.workspace_id, project_id=project.id,
        created_by=identity.user.id, session_id=identity.session.id, state_hash=sha256(state.encode()).hexdigest(),
        installation_id=body.installation_id, app_id=settings.github_app_id, state='pending',
        expires_at=now()+timedelta(minutes=10), reason=body.reason)
    db.add(row)
    audit(db, 'github.authorization_started', actor_id=identity.user.id, workspace_id=project.workspace_id,
          project_id=project.id, subject_id=row.id, reason=body.reason)
    db.flush()
    return {'authorize_url': url, 'expires_at': row.expires_at,
            'notice': 'Authorize the dedicated GitHub App, then explicitly select repositories. This does not change your local sign-in account.'}


def check_flow_actor(flow, identity):
    if flow.created_by != identity.user.id or flow.session_id != identity.session.id or utc(flow.expires_at) <= now():
        raise ApiError(403, 'github_state_rejected', 'This authorization flow is expired or belongs to another browser session.')


def complete(db, identity, body, client, settings):
    hashed = sha256(body.state.encode()).hexdigest()
    flow = db.scalar(select(GitHubAuthFlow).where(GitHubAuthFlow.state_hash == hashed))
    if flow is None: raise ApiError(403, 'github_state_rejected', 'This authorization state is not recognized.')
    project, _ = context(db, identity, flow.workspace_id, flow.project_id, manage=True, lock=True)
    flow = row_in_project(db, GitHubAuthFlow, project, flow.id, lock=True)
    check_flow_actor(flow, identity)
    if flow.state != 'pending' or flow.app_id != settings.github_app_id:
        raise ApiError(409, 'github_state_consumed', 'This authorization attempt was already consumed or its App configuration changed. Start another attempt.')
    flow.state = 'exchanging'
    db.commit()  # An ambiguous exchange is never retried under a consumed state.
    try:
        proof = client.verify_authorization(body.code, body.state, flow.installation_id)
    except (GitHubError, SecretUnavailable) as error:
        flow = db.get(GitHubAuthFlow, flow.id, populate_existing=True)
        flow.state = 'failed'; flow.error_code = getattr(error, 'code', 'github_secret_unavailable')
        db.commit()
        raise external_error(error) from None
    project, _ = context(db, identity, flow.workspace_id, flow.project_id, manage=True, lock=True)
    flow = row_in_project(db, GitHubAuthFlow, project, flow.id, lock=True)
    check_flow_actor(flow, identity)
    if flow.state != 'exchanging': raise ApiError(409, 'github_state_consumed', 'The authorization flow changed while verifying access.')
    flow.proof, flow.proof_hash = proof, digest(proof)
    flow.state = 'verified'
    # Never extend beyond the original ten-minute browser flow.
    audit(db, 'github.authorization_verified', actor_id=identity.user.id, workspace_id=project.workspace_id,
          project_id=project.id, subject_id=flow.id, reason='GitHub account and repository-admin access were verified.')
    db.commit()
    return {'flow_id': flow.id, 'workspace_id': project.workspace_id, 'project_id': project.id,
            'proof_hash': flow.proof_hash, 'expires_at': flow.expires_at, **proof,
            'notice': 'Select only repositories you are authorized to share with this project. No repository has been connected yet.'}


def connect(db, identity, body, settings):
    flow = db.get(GitHubAuthFlow, body.flow_id)
    if flow is None: raise not_found()
    project, _ = context(db, identity, flow.workspace_id, flow.project_id, manage=True, lock=True)
    flow = row_in_project(db, GitHubAuthFlow, project, flow.id, lock=True)
    check_flow_actor(flow, identity)
    if not settings.github_enabled or flow.app_id != settings.github_app_id:
        raise ApiError(409, 'github_configuration_changed', 'The GitHub App configuration changed. Authorize again.')
    if flow.state != 'verified' or flow.proof_hash != body.reviewed_proof_hash or digest(flow.proof) != flow.proof_hash:
        raise ApiError(409, 'github_proof_stale', 'Repository selection requires the unconsumed verified proof you reviewed.')
    offered = {r['github_id']: r for r in flow.proof['repositories']}
    if any(i not in offered for i in body.repository_ids):
        raise ApiError(403, 'github_repository_not_verified', 'A selected repository was not verified for this GitHub account.')
    retained_ids = set(db.scalars(select(GitHubRepository.github_id).where(GitHubRepository.project_id == project.id)).all())
    if len(retained_ids | set(body.repository_ids)) > 100:
        raise ApiError(409, 'github_repository_limit', 'This pilot retains at most 100 repository connections per project.')
    connection = db.scalar(select(GitHubConnection).where(GitHubConnection.project_id == project.id,
        GitHubConnection.app_id == flow.app_id, GitHubConnection.installation_id == flow.installation_id))
    if connection is None:
        connection = GitHubConnection(id=uuid4(), workspace_id=project.workspace_id, project_id=project.id,
                                      app_id=flow.app_id, installation_id=flow.installation_id, version=1)
        db.add(connection)
    else:
        connection.version += 1
    connection.flow_id = flow.id; connection.authorized_by = identity.user.id
    connection.github_user_id = flow.proof['github_user_id']; connection.github_login = flow.proof['github_login']
    connection.account = flow.proof['account']; connection.enabled = True; connection.last_error = None
    connection.verified_at = now(); connection.verified_until = now() + timedelta(hours=settings.github_authorization_hours)
    db.flush()
    existing = db.scalars(select(GitHubRepository).where(GitHubRepository.connection_id == connection.id)).all()
    for repo in existing:
        repo.enabled = repo.github_id in body.repository_ids; repo.version += 1
    selected = []
    for rid in body.repository_ids:
        metadata = offered[rid]
        repo = db.scalar(select(GitHubRepository).where(GitHubRepository.project_id == project.id, GitHubRepository.github_id == rid))
        if repo is not None and repo.connection_id != connection.id:
            raise ApiError(409, 'github_repository_already_connected', 'This repository already belongs to another preserved installation connection. Disconnect/review it rather than rebinding its history.')
        if repo is None:
            repo = GitHubRepository(id=uuid4(), workspace_id=project.workspace_id, project_id=project.id,
                                    connection_id=connection.id, github_id=rid, version=1)
            db.add(repo)
        repo.enabled = True; repo.full_name = metadata['full_name']; repo.private = metadata['private']; repo.default_branch = metadata['default_branch']
        selected.append(repo)
    # Reauthorization requires fresh jobs under the reviewed new repository set.
    cancel_connection_jobs(db, connection, 'github_connection_reauthorized')
    flow.state = 'used'
    audit(db, 'github.repositories_connected', actor_id=identity.user.id, workspace_id=project.workspace_id,
          project_id=project.id, subject_id=connection.id, reason=body.reason,
          details={'repository_ids': body.repository_ids, 'source_only': True, 'proof_hash': flow.proof_hash})
    db.flush()
    return {'connection_id': connection.id, 'repository_ids': [r.id for r in selected],
            'verified_until': connection.verified_until, 'notice': NOTICE}


def cancel_connection_jobs(db, connection, code):
    from app.integrations.github.sync_service import pause_config
    for repo_id in db.scalars(select(GitHubRepository.id).where(GitHubRepository.connection_id==connection.id)):
        pause_config(db,repo_id,code)
    ids = select(GitHubRepository.id).where(GitHubRepository.connection_id == connection.id)
    jobs = db.scalars(select(GitHubImport).where(GitHubImport.repository_id.in_(ids), GitHubImport.state.in_(['queued','running','paused','failed'])).with_for_update()).all()
    for job in jobs:
        job.state = 'cancelled'; job.version += 1; job.lease_token = None; job.lease_until = None
        job.error_code = code; job.finished_at = now()


def disable(db, project, identity, connection_id, body):
    connection = row_in_project(db, GitHubConnection, project, connection_id, lock=True)
    if connection.version != body.expected_version:
        raise ApiError(409, 'github_stale_connection', 'The connection changed. Refresh before disconnecting.')
    connection.enabled = False; connection.version += 1
    for row in db.scalars(select(GitHubRepository).where(GitHubRepository.connection_id == connection.id)):
        row.enabled = False; row.version += 1
    cancel_connection_jobs(db, connection, 'github_disconnected')
    audit(db, 'github.disconnected', actor_id=identity.user.id, workspace_id=project.workspace_id,
          project_id=project.id, subject_id=connection.id, reason=body.reason)
    return {'disconnected': True, 'notice': 'Further local imports are blocked. Source history and already linked evidence remain protected and retained. This does not uninstall the App on GitHub.'}


def require_connection(db, project, repo, settings):
    connection = row_in_project(db, GitHubConnection, project, repo.connection_id)
    if not settings.github_enabled or settings.github_app_id != connection.app_id:
        raise ApiError(409, 'github_configuration_changed', 'The GitHub App is disabled or changed.')
    if not connection.enabled or not repo.enabled:
        raise ApiError(409, 'github_disconnected', 'This repository is disconnected.')
    if repo.retry_not_before is not None and utc(repo.retry_not_before)>now():
        raise ApiError(429,'github_repository_backoff','Wait for the repository retry delay; new imports and settings cannot bypass it.')
    if utc(connection.verified_until) <= now():
        raise ApiError(409, 'github_reauthorization_required', 'The bounded authorization period expired. Reauthorize repository access before another import.')
    project_access(db, project.workspace_id, project.id, connection.authorized_by, manage=True)
    return connection


def add_task(db, job, kind, subject='', page=1, parameters=None):
    existing = db.scalar(select(GitHubFetchTask).where(GitHubFetchTask.import_id == job.id,
        GitHubFetchTask.kind == kind, GitHubFetchTask.subject == subject, GitHubFetchTask.page == page))
    if existing: return existing
    maximum = db.scalar(select(func.coalesce(func.max(GitHubFetchTask.ordinal), 0)).where(GitHubFetchTask.import_id == job.id))
    if maximum >= 5000: raise ApiError(409, 'github_task_limit', 'The bounded import task limit was reached.')
    task = GitHubFetchTask(id=uuid4(), workspace_id=job.workspace_id, project_id=job.project_id,
        import_id=job.id, ordinal=maximum+1, kind=kind, subject=subject, page=page,
        parameters=parameters or {}, state='pending')
    db.add(task); db.flush(); return task


def create_import(db, project, actor, body, settings):
    repo = row_in_project(db, GitHubRepository, project, body.repository_id, lock=True)
    conn = require_connection(db, project, repo, settings)
    payload_hash = digest(body.model_dump(mode='json'))
    previous = db.scalar(select(GitHubImport).where(GitHubImport.project_id == project.id, GitHubImport.request_id == body.request_id))
    if previous:
        if previous.request_hash != payload_hash or previous.requested_by != actor.id:
            raise ApiError(409, 'idempotency_conflict', 'This request ID already belongs to a different import command.')
        return import_view(db, previous)
    if utc(body.end_before) > now() + timedelta(seconds=1):
        raise ApiError(422, 'github_future_range', 'The import end must not be in the future.')
    if db.scalar(select(func.count()).select_from(GitHubImport).where(GitHubImport.project_id == project.id)) >= settings.github_project_run_limit:
        raise ApiError(409, 'github_import_history_limit', 'The configured bounded import-history capacity was reached. Ask the operator to review retention and capacity.')
    active = db.scalar(select(GitHubImport.id).where(GitHubImport.repository_id == repo.id,
                      GitHubImport.state.in_(['queued','running','paused'])))
    if active: raise ApiError(409, 'github_import_active', 'This repository already has an active or paused import. Finish or cancel that run first.')
    job = GitHubImport(id=uuid4(), workspace_id=project.workspace_id, project_id=project.id, repository_id=repo.id,
        requested_by=actor.id, request_id=body.request_id, request_hash=payload_hash,
        connection_version=conn.version, repository_version=repo.version, state='queued', version=1,
        start_at=body.start_at, end_before=body.end_before, requested_as_of=now(),
        request_limit=body.request_limit, entity_limit=body.entity_limit, data_requests=0, failures=0,
        next_attempt_at=now(), stats={}, omissions=[])
    db.add(job); db.flush()
    add_task(db, job, 'repository')
    db.add(OutboxMessage(workspace_id=project.workspace_id, project_id=project.id, job_id=job.id, kind='github_import'))
    audit(db, 'github.import_requested', actor_id=actor.id, workspace_id=project.workspace_id,
          project_id=project.id, subject_id=job.id, reason=body.reason,
          details={'repository_id': str(repo.id), 'source_only': True})
    db.flush()
    return import_view(db, job)


def import_view(db, job):
    counts = dict(db.execute(select(GitHubFetchTask.state, func.count()).where(GitHubFetchTask.import_id == job.id).group_by(GitHubFetchTask.state)).all())
    return {k: getattr(job,k) for k in ['id','repository_id','state','version','start_at','end_before','requested_as_of','anchor_sha',
        'capture_mode','request_limit','entity_limit','data_requests','failures','stats','omissions','next_attempt_at','error_code','created_at','finished_at']} | {
        'tasks': counts, 'notice': NOTICE,
        'scope': ('Live REST updates within the configured lookback, plus explicit signal targets and a bounded rotation of known old PRs/issues. Default-branch commits remain window-scoped; gaps outside coverage may remain.' if job.capture_mode=='sync' else 'PRs/issues CREATED within [start,end); default-branch commits COMMITTED within that window. Details/reviews/checks are observed at fetch time, not a historical point-in-time snapshot. Other branches, deleted history and non-code work may be absent.')}


def import_action(db, project, actor, job_id, body, action, settings):
    job = row_in_project(db, GitHubImport, project, job_id, lock=True)
    if job.version != body.expected_version: raise ApiError(409, 'github_stale_import', 'The import changed. Refresh its current state.')
    if action == 'cancel':
        if job.state not in {'queued','running','paused','failed'}: raise ApiError(409, 'github_import_terminal', 'This import is already terminal.')
        job.state = 'cancelled'; job.finished_at = now(); job.error_code = 'operator_cancelled'
    else:
        if job.state not in {'paused','failed'}: raise ApiError(409, 'github_import_not_paused', 'Only a paused or failed import can resume.')
        if utc(job.next_attempt_at) > now(): raise ApiError(429, 'github_retry_not_due', 'The recorded retry delay has not elapsed. Do not bypass GitHub rate limits.')
        if job.failures >= 5: raise ApiError(409, 'github_retry_limit', 'The bounded failure limit was reached. Inspect the connection and start a fresh overlapping import.')
        repo = row_in_project(db, GitHubRepository, project, job.repository_id)
        conn = require_connection(db, project, repo, settings)
        if conn.version != job.connection_version or repo.version != job.repository_version:
            raise ApiError(409, 'github_stale_authorization', 'The connection changed. Create a fresh import under the new authorization.')
        if db.scalar(select(GitHubImport.id).where(GitHubImport.repository_id == repo.id,
            GitHubImport.id != job.id, GitHubImport.state.in_(['queued','running','paused']))):
            raise ApiError(409, 'github_import_active', 'Another import is already active for this repository.')
        job.state = 'queued'; job.error_code = None; job.finished_at = None
    job.version += 1; job.lease_token = None; job.lease_until = None
    if action == 'cancel' and job.capture_mode == 'sync':
        from app.integrations.github.sync_service import pause_config
        pause_config(db,job.repository_id,'operator_cancelled_synchronization')
    audit(db, 'github.import_' + action, actor_id=actor.id, workspace_id=project.workspace_id,
          project_id=project.id, subject_id=job.id, reason=body.reason)
    return import_view(db, job)


def map_identity(db, project, actor, identity_id, body):
    row = row_in_project(db, GitHubIdentity, project, identity_id, lock=True)
    if row.version != body.expected_version: raise ApiError(409, 'github_identity_stale', 'Refresh the identity before changing its mapping.')
    if body.user_id is not None:
        if row.kind == 'github_bot': raise ApiError(422, 'github_bot_mapping', 'Do not attribute a bot account directly to a human. Document the human work separately.')
        project_access(db, project.workspace_id, project.id, body.user_id)
    row.linked_user_id = body.user_id; row.version += 1
    decision = GitHubIdentityDecision(workspace_id=project.workspace_id, project_id=project.id,
        identity_id=row.id, linked_user_id=body.user_id, version=row.version, created_by=actor.id, reason=body.reason)
    db.add(decision)
    audit(db, 'github.identity_mapped', actor_id=actor.id, workspace_id=project.workspace_id,
          project_id=project.id, subject_id=row.id, reason=body.reason,
          details={'version':row.version, 'user_id':str(body.user_id) if body.user_id else None, 'credit_changed':False})
    return {'id':row.id, 'version':row.version, 'user_id':row.linked_user_id, 'notice':NOTICE}


def link_source(db, project, actor, role, source_id, body, storage, quota_bytes):
    from app.contributions.work_packages.service import lock_package
    from app.evidence.schemas import EvidenceCreate
    from app.evidence.service import ObjectWrites, save_revision
    from app.integrations.github.normalization import summary
    source = row_in_project(db, GitHubSourceVersion, project, source_id)
    from app.contributions.reconstruction.service import primary_link_guard
    primary_link_guard(db, project, source, body.package_id)
    if source.content_hash != body.reviewed_source_hash or digest(source.document) != source.content_hash:
        raise ApiError(409, 'github_source_changed', 'The reviewed source fingerprint does not reconcile.')
    package = lock_package(db, project, body.package_id)
    prior = db.scalar(select(GitHubEvidenceLink).where(GitHubEvidenceLink.package_id == package.id, GitHubEvidenceLink.source_id == source.id))
    if prior:
        return {'evidence_id':prior.evidence_id, 'revision':prior.evidence_revision, 'already_linked':True, 'notice':NOTICE}
    mappings = []
    for claim in source.document['identities']:
        row = db.scalar(select(GitHubIdentity).where(GitHubIdentity.project_id == project.id, GitHubIdentity.external_key == claim['external_key']))
        mappings.append({'external_key':claim['external_key'], 'role':claim['role'],
            'mapped_user_id':str(row.linked_user_id) if row and row.linked_user_id else None,
            'mapping_version':row.version if row else None})
    origin = {'provider':'github', 'source_id':str(source.id), 'repository_id':str(source.repository_id),
              'source_hash':source.content_hash, 'kind':source.kind, 'remote_key':source.remote_key,
              'captured_at':utc(source.captured_at).isoformat(), 'mapping_at_link':mappings,
              'omissions':source.document['omissions'],
              'notice':'Pinned imported source. The statement is a short editable excerpt; view the protected full source before relying on it. Later imports/mappings never silently replace this reference.'}
    command = EvidenceCreate(kind='statement', metadata=body.metadata, text=summary(source.document),
        expected_package_version=body.expected_package_version, request_id=body.request_id, reason=body.reason)
    with ObjectWrites(storage) as writes:
        item, revision, replay = save_revision(db, project, package, actor, role, command, writes, quota_bytes, external_source=origin)
        if replay:
            existing_origin = revision.document.get('external_source')
            if not existing_origin or existing_origin.get('source_id') != str(source.id):
                raise ApiError(409, 'idempotency_conflict', 'This request ID belongs to another evidence entry.')
        link = GitHubEvidenceLink(workspace_id=project.workspace_id, project_id=project.id, package_id=package.id,
            source_id=source.id, evidence_id=item.id, evidence_revision=revision.number, created_by=actor.id)
        db.add(link); db.flush(); writes.success()
    return {'evidence_id':item.id, 'revision':revision.number, 'already_linked':False, 'notice':NOTICE}
