"""Real multi-connection gates, never simulated with SQLite or counted as passed when skipped."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import UUID
import pytest
from sqlalchemy import select,func,text
from sqlalchemy.exc import DBAPIError
from tests.test_postgres_accounts import pg_accounts,browser
from tests.phase9_helpers import sync_environment,enable,send,schedule,make_due,signed,event
from app.integrations.github.sync_models import WebhookDelivery,WebhookTarget,GitHubSyncRun
from app.integrations.github.sync_service import schedule_one
from app.integrations.github.models import GitHubImport
from app.jobs.models import OutboxMessage
from app.jobs.dispatch import claim_publication
pytestmark=pytest.mark.postgres

def parallel(fn):
    barrier=Barrier(2)
    def one(_):barrier.wait();return fn()
    with ThreadPoolExecutor(max_workers=2) as pool:return list(pool.map(one,range(2)))

def test_native_duplicate_webhook_receipt_commits_once(pg_accounts,tmp_path):
    settings,db=pg_accounts;client=browser(settings,db)
    try:
        _,root,_,overview,*_=sync_environment(client,db,settings,tmp_path);enable(client,root,overview)
        raw,headers=signed(event())
        def post():
            other=browser(settings,db)
            try:return other.post('/api/v1/github/webhook',content=raw,headers=headers).status_code
            finally:other.close()
        assert parallel(post)==[202,202]
        with db.session() as session:
            assert session.scalar(select(func.count()).select_from(WebhookDelivery))==1
            assert session.scalar(select(func.count()).select_from(WebhookTarget))==1
    finally:client.close()

def test_native_two_schedulers_issue_one_import_outbox(pg_accounts,tmp_path):
    settings,db=pg_accounts;client=browser(settings,db)
    try:
        _,root,_,overview,*_=sync_environment(client,db,settings,tmp_path);cfg=enable(client,root,overview);make_due(db,cfg['id'])
        results=parallel(lambda:schedule_one(db,settings,UUID(cfg['id'])))
        assert sorted(results)==['scheduled','waiting']
        with db.session() as session:
            assert session.scalar(select(func.count()).select_from(GitHubSyncRun))==1
            assert session.scalar(select(func.count()).select_from(OutboxMessage))==1
    finally:client.close()

def test_native_publication_lease_claimed_by_one_dispatcher(pg_accounts,tmp_path):
    settings,db=pg_accounts;client=browser(settings,db)
    try:
        _,root,_,overview,*_=sync_environment(client,db,settings,tmp_path);cfg=enable(client,root,overview);schedule(db,settings,cfg['id'])
        assert sum(result is not None for result in parallel(lambda:claim_publication(db)))==1
    finally:client.close()

def test_native_revocation_fences_concurrent_scheduler(pg_accounts,tmp_path):
    settings,db=pg_accounts;client=browser(settings,db)
    try:
        _,root,_,overview,*_=sync_environment(client,db,settings,tmp_path);cfg=enable(client,root,overview);make_due(db,cfg['id']);barrier=Barrier(2)
        def revoke():barrier.wait();return send(client,event(action='deleted'),'installation').status_code
        def dispatch():barrier.wait();return schedule_one(db,settings,UUID(cfg['id']))
        with ThreadPoolExecutor(max_workers=2) as pool:
            a=pool.submit(revoke);b=pool.submit(dispatch);assert a.result()==202;b.result()
        with db.session() as session:assert not session.scalar(select(GitHubImport.id).where(GitHubImport.state.in_(['queued','running','paused'])))
    finally:client.close()

def test_native_receipt_history_rejects_updates_deletes_and_truncation(pg_accounts,tmp_path):
    settings,db=pg_accounts;client=browser(settings,db)
    try:
        sync_environment(client,db,settings,tmp_path);assert send(client).status_code==202
        for sql in ["UPDATE github_webhook_deliveries SET event='push'",'DELETE FROM github_webhook_deliveries','TRUNCATE github_webhook_deliveries CASCADE']:
            with pytest.raises(DBAPIError),db.engine.begin() as connection:connection.execute(text(sql))
    finally:client.close()

def test_native_cross_project_source_pointer_rejected(pg_accounts,tmp_path):
    settings,db=pg_accounts;client=browser(settings,db)
    try:
        _,root,_,overview,*_=sync_environment(client,db,settings,tmp_path);cfg=enable(client,root,overview);schedule(db,settings,cfg['id'])
        with pytest.raises(DBAPIError),db.engine.begin() as c:
            c.execute(text("""INSERT INTO github_source_heads (id,workspace_id,project_id,repository_id,kind,remote_key,import_id,state,observed_at)
            SELECT gen_random_uuid(),workspace_id,gen_random_uuid(),repository_id,'issue','1',id,'unavailable',now() FROM github_imports LIMIT 1"""))
    finally:client.close()
