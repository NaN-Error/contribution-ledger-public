"""Explicit synchronization settings and database-owned scheduling.

A signed event is only a hint. Jobs refetch live REST representations; neither
webhook content nor a scheduled run may rewrite pinned evidence or award credit.
"""
from datetime import timedelta
from uuid import UUID,uuid4
from sqlalchemy import select,func
from app.auth.models import User
from app.core.errors import ApiError
from app.projects.authorization import project_access
from app.security.tokens import now,utc
from app.security.audit import audit
from app.integrations.github.models import (GitHubConnection,GitHubRepository,GitHubImport,
    GitHubSourceVersion,GitHubFetchTask)
from app.integrations.github.sync_models import (GitHubSyncConfig,GitHubSyncRun,WebhookTarget,GitHubSourceHead)
from app.integrations.github.service import row_in_project,require_connection,create_import,add_task
from app.integrations.github.schemas import ImportCreate

TERMINAL={'completed','completed_incomplete','failed','cancelled'}


def config_view(row):
    if row is None: return None
    return {k:getattr(row,k) for k in ('id','repository_id','configured_by','enabled','version','interval_minutes',
        'lookback_days','request_limit','entity_limit','next_due_at','active_import_id','last_started_at',
        'last_finished_at','last_success_at','last_complete_at','last_error','updated_at')}


def pause_config(db,repo_id,code):
    config=db.scalar(select(GitHubSyncConfig).where(GitHubSyncConfig.repository_id==repo_id))
    if config:
        config.enabled=False;config.version+=1;config.last_error=code;config.updated_at=now()
    for signal in db.scalars(select(WebhookTarget).where(WebhookTarget.repository_id==repo_id,WebhookTarget.state=='pending')):
        signal.state='ignored';signal.note=code


def configure(db,project,actor,repo_id,body,settings):
    repo=row_in_project(db,GitHubRepository,project,repo_id,lock=True)
    config=db.scalar(select(GitHubSyncConfig).where(GitHubSyncConfig.repository_id==repo.id).with_for_update())
    if (config.version if config else 0)!=body.expected_version:
        raise ApiError(409,'github_sync_stale','Refresh the synchronization settings before changing them.')
    if body.enabled:
        if not settings.github_sync_enabled:
            raise ApiError(409,'github_sync_disabled','The operator must enable the optional synchronization deployment first.')
        require_connection(db,project,repo,settings)
    if config and config.active_import_id:
        job=db.get(GitHubImport,config.active_import_id)
        if job and job.state not in TERMINAL:
            job.state='cancelled';job.version+=1;job.lease_token=None;job.lease_until=None
            job.finished_at=now();job.error_code='github_sync_settings_changed'
        reconcile_finished(db,config)
    if config is None:
        config=GitHubSyncConfig(id=uuid4(),workspace_id=project.workspace_id,project_id=project.id,
            repository_id=repo.id,configured_by=actor.id,version=0,next_due_at=now(),updated_at=now(),scan_cursor='')
        db.add(config)
    config.version+=1;config.enabled=body.enabled;config.configured_by=actor.id
    config.interval_minutes=body.interval_minutes;config.lookback_days=body.lookback_days
    config.request_limit=body.request_limit;config.entity_limit=body.entity_limit
    config.next_due_at=now()+timedelta(seconds=5);config.last_error=None;config.updated_at=now()
    if not body.enabled:
        for signal in db.scalars(select(WebhookTarget).where(WebhookTarget.repository_id==repo.id,WebhookTarget.state=='pending')):
            signal.state='ignored';signal.note='synchronization_paused_by_administrator'
    db.flush()
    audit(db,'github.sync_configured',actor_id=actor.id,workspace_id=project.workspace_id,project_id=project.id,
          subject_id=repo.id,reason=body.reason,details={'version':config.version,'enabled':body.enabled})
    return config_view(config)


def request_now(db,project,actor,repo_id,body,settings):
    repo=row_in_project(db,GitHubRepository,project,repo_id,lock=True)
    config=db.scalar(select(GitHubSyncConfig).where(GitHubSyncConfig.repository_id==repo.id).with_for_update())
    if not config or config.version!=body.expected_version:
        raise ApiError(409,'github_sync_stale','Refresh the synchronization settings.')
    if not settings.github_sync_enabled or not config.enabled:
        raise ApiError(409,'github_sync_disabled','Enable and review synchronization first.')
    require_connection(db,project,repo,settings)
    # Never bypass a GitHub backoff or create an overlapping active import.
    if config.active_import_id:
        raise ApiError(409,'github_sync_active','A synchronization run is already active. Its retry delay cannot be bypassed.')
    config.next_due_at=now();config.version+=1;config.updated_at=now()
    audit(db,'github.sync_requested',actor_id=actor.id,workspace_id=project.workspace_id,project_id=project.id,
        subject_id=repo.id,reason=body.reason)
    return config_view(config)


def reconcile_finished(db,config):
    if not config.active_import_id:return
    job=db.get(GitHubImport,config.active_import_id)
    if job is None or job.state not in TERMINAL:return
    config.last_finished_at=job.finished_at or now()
    good=job.state in {'completed','completed_incomplete'}
    if good:
        config.last_success_at=job.finished_at or now()
        if job.state=='completed':config.last_complete_at=job.finished_at or now()
        config.last_error='capture_has_omissions' if job.state=='completed_incomplete' else None
    else:
        config.enabled=False;config.version+=1
        config.last_error=job.error_code or 'github_sync_failed'
    for signal in db.scalars(select(WebhookTarget).where(WebhookTarget.import_id==job.id,WebhookTarget.state=='scheduled')):
        signal.state='processed' if good else 'failed'
        signal.note='bounded_capture_finished' if good else config.last_error
    config.active_import_id=None;config.updated_at=now()


def tracked_targets(db,repo_id,cursor,limit=20):
    """Bounded round robin, not a claim that every remote entity was discovered."""
    # SQL DISTINCT does not load all historical versions into process memory.
    key=(GitHubSourceVersion.kind+':'+GitHubSourceVersion.remote_key)
    query=select(GitHubSourceVersion.kind,GitHubSourceVersion.remote_key,key.label('scan_key')).where(
        GitHubSourceVersion.repository_id==repo_id,GitHubSourceVersion.kind.in_(['pull_request','issue'])).distinct()
    rows=db.execute(query.where(key>cursor).order_by(key).limit(limit+1)).all()
    if not rows and cursor:rows=db.execute(query.order_by(key).limit(limit+1)).all()
    batch=rows[:limit]
    return ([{'kind':'pull' if r.kind=='pull_request' else 'issue','subject':r.remote_key} for r in batch],
            batch[-1].scan_key if len(rows)>limit else '')


def schedule_one(database,settings,config_id):
    """Workspace lock + due-time transition + import/outbox in ONE transaction."""
    if not settings.github_enabled or not settings.github_sync_enabled:return 'disabled'
    with database.session() as db:
        config=db.get(GitHubSyncConfig,config_id)
        if not config:return 'missing'
        try:
            project,_=project_access(db,config.workspace_id,config.project_id,config.configured_by,manage=True,lock=True)
            config=db.scalar(select(GitHubSyncConfig).where(GitHubSyncConfig.id==config_id)
                .with_for_update().execution_options(populate_existing=True))
            reconcile_finished(db,config)
            if not config.enabled or config.active_import_id or utc(config.next_due_at)>now():
                db.commit();return 'waiting'
            repo=row_in_project(db,GitHubRepository,project,config.repository_id)
            require_connection(db,project,repo,settings)
            active=db.scalar(select(GitHubImport.id).where(GitHubImport.repository_id==repo.id,
                GitHubImport.state.in_(['queued','running','paused'])))
            if active:
                config.last_error='historical_import_active';db.commit();return 'busy'
            signals=db.scalars(select(WebhookTarget).where(WebhookTarget.repository_id==repo.id,
                WebhookTarget.state=='pending').order_by(WebhookTarget.created_at,WebhookTarget.id).limit(50)).all()
            targets=[]
            for signal in signals:targets.extend(signal.targets)
            known,new_cursor=tracked_targets(db,repo.id,config.scan_cursor)
            targets.extend(known)
            distinct={(t['kind'],t['subject']) for t in targets if t['kind']!='reconcile'}
            # All hints in selected signals fit this bound (50 * at most 21 + 20).
            if len(distinct)>1200:raise ApiError(409,'github_sync_target_limit','Too many reconciliation targets.')
            instant=now();body=ImportCreate(repository_id=repo.id,start_at=instant-timedelta(days=config.lookback_days),
                end_before=instant,request_limit=config.request_limit,entity_limit=config.entity_limit,request_id=uuid4(),
                reviewed=True,reason='Explicitly enabled bounded authoritative reconciliation; no credit is issued.')
            actor=db.get(User,config.configured_by)
            result=create_import(db,project,actor,body,settings)
            job=db.get(GitHubImport,result['id']);job.capture_mode='sync'
            task=db.scalar(select(GitHubFetchTask).where(GitHubFetchTask.import_id==job.id,GitHubFetchTask.kind=='repository'))
            task.parameters={'sync':True,'targets':[{'kind':k,'subject':s} for k,s in sorted(distinct)]}
            for signal in signals:signal.state='scheduled';signal.import_id=job.id;signal.note='authoritative_import_queued'
            db.add(GitHubSyncRun(workspace_id=project.workspace_id,project_id=project.id,config_id=config.id,
                config_version=config.version,import_id=job.id,trigger='webhook' if signals else 'scheduled_or_requested',
                target_count=len(distinct),created_at=instant))
            config.active_import_id=job.id;config.last_started_at=instant;config.last_error=None
            config.next_due_at=instant+timedelta(minutes=config.interval_minutes)
            # Keep other pending signals due sooner, but never bypass active-run backoff.
            db.flush()
            if db.scalar(select(WebhookTarget.id).where(WebhookTarget.repository_id==repo.id,WebhookTarget.state=='pending').limit(1)):
                config.next_due_at=instant+timedelta(seconds=60)
            config.scan_cursor=new_cursor;config.updated_at=instant
            db.commit();return 'scheduled'
        except ApiError as error:
            if error.code=='github_repository_backoff':
                config=db.get(GitHubSyncConfig,config_id)
                repo=db.get(GitHubRepository,config.repository_id)
                config.next_due_at=repo.retry_not_before;config.last_error=error.code
                db.commit();return 'backoff'
            db.rollback()
            # System job state only: loss of access cannot leave an infinite retry loop.
            from app.projects.models import Workspace
            config=db.get(GitHubSyncConfig,config_id)
            if config:
                db.scalar(select(Workspace).where(Workspace.id==config.workspace_id).with_for_update())
                db.refresh(config)
                reconcile_finished(db,config)
                config.enabled=False;config.version+=1;config.last_error=error.code;config.updated_at=now()
                db.commit()
            return 'blocked'


def schedule_due(database,settings,limit=50):
    if not settings.github_sync_enabled:return []
    with database.session() as db:
        ids=db.scalars(select(GitHubSyncConfig.id).where(
            (GitHubSyncConfig.active_import_id.is_not(None)) |
            ((GitHubSyncConfig.enabled==True)&(GitHubSyncConfig.next_due_at<=now())))
            .order_by(GitHubSyncConfig.next_due_at,GitHubSyncConfig.id).limit(limit)).all()
    return [schedule_one(database,settings,id_) for id_ in ids]


def observe_head(db,job,repo,source,remote_updated_at=None):
    head=db.scalar(select(GitHubSourceHead).where(GitHubSourceHead.repository_id==repo.id,
        GitHubSourceHead.kind==source.kind,GitHubSourceHead.remote_key==source.remote_key))
    if head is None:
        head=GitHubSourceHead(workspace_id=repo.workspace_id,project_id=repo.project_id,repository_id=repo.id,
            kind=source.kind,remote_key=source.remote_key,import_id=job.id,state='captured',observed_at=now())
        db.add(head)
    if head.remote_updated_at and remote_updated_at and utc(remote_updated_at)<utc(head.remote_updated_at):
        return # Preserve history, but do not project an older remote revision as current.
    head.source_id=source.id;head.import_id=job.id;head.state='captured';head.observed_at=now()
    head.remote_updated_at=remote_updated_at


def observe_unavailable(db,job,repo,task):
    kind={'pull':'pull_request','issue':'issue','commit':'commit'}.get(task.kind)
    if kind is None:return
    head=db.scalar(select(GitHubSourceHead).where(GitHubSourceHead.repository_id==repo.id,
        GitHubSourceHead.kind==kind,GitHubSourceHead.remote_key==task.subject))
    if head is None:
        head=GitHubSourceHead(workspace_id=repo.workspace_id,project_id=repo.project_id,repository_id=repo.id,
            kind=kind,remote_key=task.subject,import_id=job.id,state='unavailable',observed_at=now())
        db.add(head)
    head.state='unavailable';head.import_id=job.id;head.observed_at=now()
    # Keep the previous source ID, if any; unavailable now is not erased history.
