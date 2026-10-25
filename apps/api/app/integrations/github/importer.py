"""One bounded fetch per leased checkpoint. No repository execution or credit writes.

The dispatcher may deliver at least once. A random lease fence plus current
workspace/connection checks prevent stale workers from committing after a cancel,
reauthorization, or another lease. PostgreSQL-native concurrency tests are separate
from SQLite behavior tests. Network requests run outside database transactions.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4
from sqlalchemy import select, func, or_, and_
from app.auth.models import User
from app.projects.authorization import project_access
from app.core.errors import ApiError
from app.policies.service import digest
from app.security.tokens import now, utc
from app.security.secrets.store import SecretUnavailable
from app.security.audit import audit
from app.integrations.github.client import GitHubError, repo_descriptor
from app.integrations.github.normalization import normalize, canonical, sha, number
from app.integrations.github.service import row_in_project, require_connection, add_task
from app.integrations.github.models import (GitHubImport, GitHubRepository, GitHubConnection, GitHubFetchTask,
    GitHubSourceVersion, GitHubObservation, GitHubIdentity)
from app.jobs.models import OutboxMessage

LEASE_SECONDS = 180
MAX_LIST_PAGES = 20
MAX_CHILD_PAGES = 5
MAX_FILE_PAGES = 10
RETRY_LIMIT = 5


def omitted(job, message):
    values = list(job.omissions or [])
    if message not in values:
        if len(values) < 199: values.append(message[:1200])
        elif 'additional_omissions_not_enumerated' not in values: values.append('additional_omissions_not_enumerated')
    job.omissions = values


def timestamp(value):
    try:
        result = datetime.fromisoformat(str(value).replace('Z','+00:00'))
        return result.astimezone(timezone.utc) if result.tzinfo else None
    except (ValueError, TypeError, OverflowError): return None


def claim(database, requested_job_id=None):
    with database.session() as db:
        instant = now()
        ready = or_(GitHubImport.state == 'queued',
                    and_(GitHubImport.state == 'running', GitHubImport.lease_until <= instant),
                    and_(GitHubImport.state == 'paused', GitHubImport.failures < RETRY_LIMIT))
        query = select(GitHubImport).join(GitHubRepository,GitHubRepository.id==GitHubImport.repository_id).where(ready, GitHubImport.next_attempt_at <= instant,
            or_(GitHubRepository.retry_not_before.is_(None),GitHubRepository.retry_not_before<=instant))
        if requested_job_id is not None: query = query.where(GitHubImport.id == requested_job_id)
        job = db.scalar(query.order_by(GitHubImport.created_at, GitHubImport.id).with_for_update(skip_locked=True,of=GitHubImport))
        if job is None: return None
        job.state = 'running'; job.version += 1
        job.lease_token = uuid4(); job.lease_until = instant + timedelta(seconds=LEASE_SECONDS)
        intent = db.scalar(select(OutboxMessage).where(OutboxMessage.job_id == job.id))
        if intent is None:
            # A job without its transactional dispatch intent is invalid, not a task to guess.
            job.state = 'failed'; job.error_code = 'github_outbox_missing'; job.finished_at = instant
            db.commit(); return None
        if intent.first_dispatched_at is None: intent.first_dispatched_at = instant
        fence = job.lease_token
        db.commit()
        return job.id, fence


def fenced(db, job_id, fence):
    job = db.scalar(select(GitHubImport).where(GitHubImport.id == job_id).with_for_update().execution_options(populate_existing=True))
    if job is None or job.state != 'running' or job.lease_token != fence or utc(job.lease_until) <= now():
        return None
    return job


def release(job):
    job.lease_token = None; job.lease_until = None; job.version += 1


def failure(database, job_id, fence, error):
    with database.session() as db:
        # This transition writes only system job state, even if the requesting
        # member no longer has access. No source/evidence is committed here.
        from app.projects.models import Workspace
        preliminary=db.get(GitHubImport,job_id)
        if preliminary is not None:
            db.scalar(select(Workspace).where(Workspace.id==preliminary.workspace_id).with_for_update())
        job = fenced(db, job_id, fence)
        if not job: return 'discarded'
        code = getattr(error, 'code', 'github_secret_unavailable' if isinstance(error, SecretUnavailable) else 'github_worker_failed')
        delay = getattr(error, 'retry_seconds', None)
        job.failures += 1; job.error_code = code
        if delay is not None:
            job.next_attempt_at = now() + timedelta(seconds=max(delay,60*2**min(job.failures-1,8)))
            repo=db.get(GitHubRepository,job.repository_id)
            repo.retry_not_before=max(utc(repo.retry_not_before) if repo.retry_not_before else now(),utc(job.next_attempt_at))
        if delay is not None and job.failures < RETRY_LIMIT:
            job.state = 'paused'
        else:
            job.state = 'failed'; job.finished_at = now()
        release(job)
        db.commit(); return job.state


def request_cost(task):
    return 3 if task.kind == 'pull_files' else 1


def fetch(client, token, repo, job, task):
    base = '/repos/' + repo.full_name
    page = {'per_page':100, 'page':task.page}
    paths = {
        'repository': (base, None),
        'anchor': (base+'/commits', {'per_page':1, 'page':1, 'sha':repo.default_branch}),
        'pulls': (base+'/pulls', {**page,'state':'all','sort':'created','direction':'asc'}),
        'issues': (base+'/issues', {**page,'state':'all','sort':'created','direction':'asc','since':utc(job.start_at).isoformat()}),
        'commits': (base+'/commits', {**page,'sha':job.anchor_sha,'since':utc(job.start_at).isoformat(),'until':utc(job.end_before).isoformat()}),
        'pull': (base+'/pulls/'+task.subject, None),
        'issue': (base+'/issues/'+task.subject, None),
        'sync_issues': (base+'/issues', {**page,'state':'all','sort':'updated','direction':'desc','since':utc(job.start_at).isoformat()}),
        'reviews': (base+'/pulls/'+task.subject+'/reviews', page),
        'comments': (base+'/issues/'+task.subject+'/comments', page),
        'review_comments': (base+'/pulls/'+task.subject+'/comments', page),
        'pull_commits': (base+'/pulls/'+task.subject+'/commits', page),
        'commit': (base+'/commits/'+task.subject, page),
        'checks': (base+'/commits/'+task.subject+'/check-runs', {**page, 'filter':'all'}),
    }
    if task.kind == 'pull_files':
        before, _ = client.get(token, base+'/pulls/'+task.subject)
        expected = (task.parameters['head_sha'], task.parameters['base_sha'])
        pair = lambda data: ((data.get('head') or {}).get('sha'), (data.get('base') or {}).get('sha'))
        if pair(before) != expected:
            return {'files':[], 'head_changed':True}, False
        data, more = client.get(token, base+'/pulls/'+task.subject+'/files', page)
        after, _ = client.get(token, base+'/pulls/'+task.subject)
        if pair(after) != expected:
            return {'files':[], 'head_changed':True}, False
        return {'files':data, 'head_changed':False}, more
    if task.kind not in paths: raise GitHubError('github_unknown_fetch_task')
    path, params = paths[task.kind]
    return client.get(token, path, params)


def store_source(db, job, task, repo, document, settings):
    encoded = canonical(document)
    content_hash = digest(document)
    if len(encoded) > 524288:
        omitted(job, task.kind+':normalized_source_limit'); return None
    source = db.scalar(select(GitHubSourceVersion).where(GitHubSourceVersion.repository_id == repo.id,
        GitHubSourceVersion.kind == document['kind'], GitHubSourceVersion.remote_key == document['remote_key'],
        GitHubSourceVersion.content_hash == content_hash))
    if source is None:
        size = db.scalar(select(func.coalesce(func.sum(GitHubSourceVersion.size_bytes),0)).where(GitHubSourceVersion.project_id == job.project_id))
        if size + len(encoded) > settings.github_project_quota_bytes:
            raise ApiError(409,'github_source_quota','The project reached its bounded source-history quota.')
        source = GitHubSourceVersion(id=uuid4(), workspace_id=job.workspace_id, project_id=job.project_id,
            repository_id=repo.id, kind=document['kind'], remote_key=document['remote_key'], content_hash=content_hash,
            size_bytes=len(encoded), document=document, captured_at=now())
        db.add(source); db.flush()
        counts = dict(job.stats or {}); counts['new_source_versions'] = counts.get('new_source_versions',0)+1; job.stats = counts
    observed = db.scalar(select(GitHubObservation.id).where(GitHubObservation.import_id == job.id,
        GitHubObservation.task_id == task.id, GitHubObservation.source_id == source.id))
    if not observed:
        db.add(GitHubObservation(workspace_id=job.workspace_id, project_id=job.project_id,
            import_id=job.id, task_id=task.id, source_id=source.id, observed_at=now()))
    for identity in document['identities']:
        exists = db.scalar(select(GitHubIdentity.id).where(GitHubIdentity.project_id == job.project_id,
                                                         GitHubIdentity.external_key == identity['external_key']))
        if not exists:
            db.add(GitHubIdentity(workspace_id=job.workspace_id, project_id=job.project_id,
                external_key=identity['external_key'], kind=identity['kind'], label=identity['label'], version=1))
            db.flush()
    for item in document['omissions'][:20]: omitted(job, document['kind']+':'+document['remote_key']+':'+item)
    updated = timestamp(document['content'].get('updated_at'))
    if job.capture_mode == 'historical' and updated and updated >= utc(job.end_before):
        omitted(job, document['kind']+':'+document['remote_key']+':current_representation_updated_after_selected_window')
    from app.integrations.github.sync_service import observe_head
    observe_head(db,job,repo,source,updated)
    return source


def next_page(db, job, task, more, maximum):
    if more:
        if task.page >= maximum:
            omitted(job, f'{task.kind}:{task.subject}:page_limit_{maximum}')
        else:
            add_task(db, job, task.kind, task.subject, task.page+1, task.parameters)


def entity_count(job, kind):
    return (job.stats or {}).get(kind+'_selected',0)


def count_entity(job, kind):
    values = dict(job.stats or {}); values[kind+'_selected'] = values.get(kind+'_selected',0)+1; job.stats=values


def apply_response(db, job, task, repo, data, more, settings):
    def save(kind, row, **kw):
        return store_source(db, job, task, repo, normalize(kind,row,repo,**kw), settings)
    if task.kind == 'repository':
        actual = repo_descriptor(data)
        if actual['github_id'] != repo.github_id or actual['full_name'] != repo.full_name:
            raise GitHubError('github_repository_identity_changed')
        if job.capture_mode == 'sync':
            for target in task.parameters.get('targets',[]):
                if target['kind'] not in {'pull','issue','commit','checks'}:
                    raise GitHubError('github_unknown_sync_target')
                add_task(db,job,target['kind'],target['subject'])
            for kind in ('anchor','sync_issues'):add_task(db,job,kind)
        else:
            for kind in ('anchor','pulls','issues'):add_task(db,job,kind)
        if actual['default_branch'] != repo.default_branch:
            raise GitHubError('github_default_branch_changed')
    elif task.kind == 'issue':
        if not isinstance(data,dict) or number(data.get('number')) != task.subject:
            raise GitHubError('github_source_identity_changed')
        if data.get('pull_request'):
            add_task(db,job,'pull',task.subject)
        else:
            save('issue',data);add_task(db,job,'comments',task.subject)
    elif task.kind == 'sync_issues':
        if not isinstance(data,list):raise GitHubError('github_invalid_response')
        reached_limit=False
        for row in data:
            if not isinstance(row,dict):raise GitHubError('github_invalid_response')
            key=number(row.get('number'));kind='pull' if row.get('pull_request') else 'issue'
            if db.scalar(select(GitHubFetchTask.id).where(GitHubFetchTask.import_id==job.id,
                GitHubFetchTask.kind==kind,GitHubFetchTask.subject==key,GitHubFetchTask.page==1)):
                continue
            if entity_count(job,'updated_items')>=job.entity_limit:
                omitted(job,'reconciliation:updated_entity_limit');reached_limit=True;break
            count_entity(job,'updated_items');add_task(db,job,kind,key)
        if not reached_limit:next_page(db,job,task,more,MAX_LIST_PAGES)
        elif more:omitted(job,'reconciliation:unscanned_updated_pages')
    elif task.kind == 'anchor':
        if not isinstance(data,list): raise GitHubError('github_invalid_response')
        if data:
            job.anchor_sha = sha(data[0].get('sha'))
            add_task(db,job,'commits')
        else: omitted(job,'default_branch_has_no_commit_anchor')
    elif task.kind in {'pulls','issues','commits'}:
        if not isinstance(data,list): raise GitHubError('github_invalid_response')
        reached_end = False
        for row in data:
            if not isinstance(row,dict): raise GitHubError('github_invalid_response')
            if task.kind == 'issues' and row.get('pull_request'): continue
            observed_date = timestamp(((row.get('commit') or {}).get('committer') or {}).get('date') if task.kind == 'commits' else row.get('created_at'))
            if observed_date is None:
                omitted(job, task.kind+':missing_date'); continue
            if observed_date >= utc(job.end_before):
                if task.kind != 'commits': reached_end = True
                continue
            if observed_date < utc(job.start_at): continue
            child_kind = {'pulls':'pull','issues':'comments','commits':'commit'}[task.kind]
            key = sha(row.get('sha')) if task.kind == 'commits' else number(row.get('number'))
            existing = db.scalar(select(GitHubFetchTask.id).where(GitHubFetchTask.import_id == job.id,
                GitHubFetchTask.kind == child_kind, GitHubFetchTask.subject == key, GitHubFetchTask.page == 1))
            if existing: continue  # Pagination drift or redelivery does not count/select twice.
            if entity_count(job,task.kind) >= job.entity_limit:
                omitted(job, task.kind+':entity_limit'); reached_end = True; break
            count_entity(job,task.kind)
            add_task(db,job,child_kind,key)
            if task.kind == 'issues': save('issue',row)
            if task.kind == 'commits': save('commit',row)
        if not reached_end: next_page(db,job,task,more,MAX_LIST_PAGES)
        elif more and entity_count(job,task.kind) >= job.entity_limit:
            omitted(job,task.kind+':unscanned_pages_after_entity_limit')
    elif task.kind == 'pull':
        if number(data.get('number')) != task.subject: raise GitHubError('github_source_identity_changed')
        save('pull_request',data)
        head = sha((data.get('head') or {}).get('sha')); base = sha((data.get('base') or {}).get('sha'))
        parameters = {'head_sha':head, 'base_sha':base}
        for child in ('reviews','comments','review_comments','pull_commits','pull_files'):
            add_task(db,job,child,task.subject,parameters=parameters)
        add_task(db,job,'checks',head)
        if type(data.get('commits')) is int and data['commits'] > 250: omitted(job,task.subject+':github_pull_commit_api_cap_250')
        if type(data.get('changed_files')) is int and data['changed_files'] > MAX_FILE_PAGES*100:
            omitted(job,task.subject+':pull_file_capture_limit_'+str(MAX_FILE_PAGES*100))
    elif task.kind == 'commit':
        if sha(data.get('sha')) != task.subject: raise GitHubError('github_source_identity_changed')
        if task.page == 1:
            save('commit',data); add_task(db,job,'checks',task.subject)
        save('commit_files', {'files':data.get('files',[])}, remote_key=task.subject+':'+str(task.page), extra={'commit_sha':task.subject,'page':task.page})
        next_page(db,job,task,more,MAX_FILE_PAGES)
    elif task.kind == 'pull_files':
        if data['head_changed']:
            omitted(job,task.subject+':pull_head_or_base_changed_files_not_captured')
            task.state = 'omitted'
        else:
            save('pull_files',data,remote_key=task.subject+':'+str(task.page)+':'+task.parameters['head_sha'],
                 extra={**task.parameters,'pull_number':int(task.subject),'page':task.page,
                        'consistency':'head/base matched before and after this page; pages are not a transaction across GitHub'})
            next_page(db,job,task,more,MAX_FILE_PAGES)
    elif task.kind == 'checks':
        rows = data.get('check_runs') if isinstance(data,dict) else None
        if not isinstance(rows,list): raise GitHubError('github_invalid_response')
        for row in rows:
            if row.get('head_sha') != task.subject:
                omitted(job,'check_run:head_mismatch'); continue
            save('check_run',row)
        next_page(db,job,task,more,MAX_CHILD_PAGES)
    elif task.kind in {'reviews','comments','review_comments','pull_commits'}:
        if not isinstance(data,list): raise GitHubError('github_invalid_response')
        kind = {'reviews':'review','comments':'comment','review_comments':'review_comment','pull_commits':'commit'}[task.kind]
        for row in data:
            save(kind,row,extra={'parent_issue_or_pull':task.subject,'observed_pull_head':task.parameters.get('head_sha'),
                                'observation':'Current REST representation, not guaranteed to predate the selected window end.'})
        next_page(db,job,task,more,3 if task.kind=='pull_commits' else MAX_CHILD_PAGES)
    else: raise GitHubError('github_unknown_fetch_task')
    if task.state != 'omitted': task.state = 'done'
    db.flush()


def step(database, settings, client, job_id=None):
    claimed = claim(database, job_id)
    if not claimed: return 'idle'
    job_id, fence = claimed
    try:
        with database.session() as db:
            job = db.get(GitHubImport,job_id)
            project, _ = project_access(db,job.workspace_id,job.project_id,job.requested_by,manage=True,lock=True)
            job = fenced(db,job_id,fence)
            if not job: return 'discarded'
            repo = row_in_project(db,GitHubRepository,project,job.repository_id)
            conn = require_connection(db,project,repo,settings)
            if conn.version != job.connection_version or repo.version != job.repository_version:
                raise ApiError(409,'github_stale_authorization','The approved connection changed.')
            task = db.scalar(select(GitHubFetchTask).where(GitHubFetchTask.import_id == job.id,
                GitHubFetchTask.state == 'pending').order_by(GitHubFetchTask.ordinal))
            if task is None:
                job.state = 'completed_incomplete' if job.omissions else 'completed'
                job.finished_at = now(); release(job); db.commit(); return job.state
            cost = request_cost(task)
            if job.data_requests + cost > job.request_limit:
                omitted(job,'data_request_budget_reached_remaining_tasks_not_captured')
                job.state = 'completed_incomplete'; job.finished_at = now(); release(job); db.commit(); return job.state
            job.data_requests += cost  # Conservatively reserve before outbound calls/crashes.
            db.commit()
        token = client.repository_token(conn.installation_id,repo.github_id)
        client.check_repository_authority(token,repo,conn)
        missing_source = False
        try:
            data, more = fetch(client,token,repo,job,task)
        except GitHubError as error:
            if error.code == 'github_empty_or_conflicting_repository' and task.kind == 'anchor':
                data,more = [],False
            elif error.code == 'github_access_denied' and task.kind in {'pull','issue','commit','checks','comments','reviews','review_comments','pull_files','pull_commits'}:
                # The post-fetch authority check below must still succeed.
                data,more = None,False;missing_source=True
            elif error.code == 'github_response_too_large':
                data,more = None,False
            else: raise
        client.check_repository_authority(token,repo,conn)
        # token only lives in this call; queue/DB records contain no bearer material.
        del token
        with database.session() as db:
            project, _ = project_access(db,job.workspace_id,job.project_id,job.requested_by,manage=True,lock=True)
            job = fenced(db,job_id,fence)
            if not job: return 'discarded'
            repo = row_in_project(db,GitHubRepository,project,job.repository_id)
            conn = require_connection(db,project,repo,settings)
            if conn.version != job.connection_version or repo.version != job.repository_version:
                raise ApiError(409,'github_stale_authorization','The approved connection changed during the fetch.')
            task = row_in_project(db,GitHubFetchTask,project,task.id,lock=True)
            if task.import_id != job.id or task.state != 'pending': return 'discarded'
            if data is None:
                task.state='omitted'
                omitted(job,task.kind+':'+task.subject+(':source_unavailable' if missing_source else ':response_size_limit'))
                if missing_source:
                    from app.integrations.github.sync_service import observe_unavailable
                    observe_unavailable(db,job,repo,task)
            else:
                apply_response(db,job,task,repo,data,more,settings)
            pending = db.scalar(select(GitHubFetchTask.id).where(GitHubFetchTask.import_id==job.id,GitHubFetchTask.state=='pending').limit(1))
            job.state = 'queued' if pending else 'completed_incomplete' if job.omissions else 'completed'
            job.error_code = None; job.next_attempt_at = now()
            if not pending:
                job.finished_at=now()
                audit(db,'github.import_finished',actor_id=job.requested_by,workspace_id=job.workspace_id,
                      project_id=job.project_id,subject_id=job.id,reason='Bounded source capture finished; no contribution credit was issued.',details={'state':job.state})
            release(job); db.commit(); return job.state
    except (GitHubError, SecretUnavailable, ApiError) as error:
        if getattr(error,'code',None) in {'github_authority_revoked','github_installation_mismatch','github_access_denied'}:
            with database.session() as db:
                old=db.get(GitHubImport,job_id)
                if old:
                    from app.projects.models import Workspace
                    from app.integrations.github.webhooks import fence_repository
                    db.scalar(select(Workspace).where(Workspace.id==old.workspace_id).with_for_update())
                    current=fenced(db,job_id,fence)
                    if current:
                        repo=db.get(GitHubRepository,current.repository_id)
                        fence_repository(db,repo,error.code)
                        audit(db,'github.live_authority_lost',workspace_id=current.workspace_id,project_id=current.project_id,
                            subject_id=repo.id,reason='Current GitHub sharing authority failed; future fetches are fenced.',details={'code':error.code})
                        db.commit();return 'cancelled'
        return failure(database,job_id,fence,error)
    except Exception:
        # No exception repr/remote response/secret is emitted. Repeated failures
        # require inspection rather than infinite automatic retries.
        return failure(database,job_id,fence,GitHubError('github_worker_failed'))
