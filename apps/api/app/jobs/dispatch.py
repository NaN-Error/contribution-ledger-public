"""Database outbox publication, independent of task execution.

Broker acknowledgement is not a guarantee of execution. Ready database jobs are
periodically re-published. Leased/fenced effects make duplicates safe. No task ETA
or results are kept in Redis; retry due times and business state stay in PostgreSQL.
"""
from datetime import timedelta
from uuid import UUID,uuid4
from sqlalchemy import select,or_,and_
from app.security.tokens import now,utc
from app.jobs.models import OutboxMessage
from app.integrations.github.models import GitHubImport, GitHubRepository
from app.integrations.github.importer import RETRY_LIMIT
from app.integrations.github.sync_models import JobHeartbeat


class CeleryPublisher:
    def __init__(self,app):self.app=app
    def publish(self,payload):
        self.app.send_task('ledger.github.checkpoint',kwargs=payload,queue='github-source',
            serializer='json',ignore_result=True,retry=False)


def claim_publication(database):
    with database.session() as db:
        instant=now()
        ready=or_(GitHubImport.state=='queued',
            and_(GitHubImport.state=='paused',GitHubImport.failures<RETRY_LIMIT),
            and_(GitHubImport.state=='running',GitHubImport.lease_until<=instant))
        row=db.scalar(select(OutboxMessage).join(GitHubImport,GitHubImport.id==OutboxMessage.job_id)
            .join(GitHubRepository,GitHubRepository.id==GitHubImport.repository_id).where(
            GitHubRepository.enabled==True,
            or_(GitHubRepository.retry_not_before.is_(None),GitHubRepository.retry_not_before<=instant),
            ready,GitHubImport.next_attempt_at<=instant,
            or_(OutboxMessage.next_dispatch_at.is_(None),OutboxMessage.next_dispatch_at<=instant),
            or_(OutboxMessage.dispatch_lease_until.is_(None),OutboxMessage.dispatch_lease_until<=instant))
            .order_by(OutboxMessage.created_at,OutboxMessage.id).with_for_update(skip_locked=True,of=OutboxMessage))
        if row is None:return None
        row.dispatch_lease=uuid4();row.dispatch_lease_until=instant+timedelta(seconds=30)
        row.publish_attempts+=1
        payload={'job_id':str(row.job_id),'workspace_id':str(row.workspace_id),'project_id':str(row.project_id)}
        result=row.id,row.dispatch_lease,payload
        db.commit();return result


def publish_one(database,publisher):
    claimed=claim_publication(database)
    if claimed is None:return 'idle'
    id_,fence,payload=claimed
    ok=True
    try:publisher.publish(payload)
    except Exception:ok=False # Never log a broker URL, credentials or message repr.
    with database.session() as db:
        row=db.scalar(select(OutboxMessage).where(OutboxMessage.id==id_).with_for_update())
        if row is None or row.dispatch_lease!=fence or row.dispatch_lease_until is None or utc(row.dispatch_lease_until)<=now():return 'discarded'
        instant=now();row.dispatch_lease=None;row.dispatch_lease_until=None
        if ok:
            row.last_published_at=instant
            if row.first_dispatched_at is None:row.first_dispatched_at=instant
            row.publish_error=None;row.next_dispatch_at=instant+timedelta(seconds=30)
        else:
            row.publish_error='broker_publication_failed'
            row.next_dispatch_at=instant+timedelta(seconds=min(300,10*2**min(row.publish_attempts,5)))
        db.commit()
    return 'published' if ok else 'broker_unavailable'


def heartbeat(database,component,status):
    with database.session() as db:
        # Native upsert also makes multiple schedulers' first heartbeat safe.
        values={'component':component,'last_seen_at':now(),'status':status}
        if db.bind.dialect.name=='postgresql':
            from sqlalchemy.dialects.postgresql import insert
        else:
            from sqlalchemy.dialects.sqlite import insert
        stmt=insert(JobHeartbeat).values(**values)
        db.execute(stmt.on_conflict_do_update(index_elements=['component'],set_=values));db.commit()
