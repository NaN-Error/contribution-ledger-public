from datetime import timedelta
from uuid import UUID,uuid4
import pytest
from sqlalchemy import select,func
from app.integrations.github.client import GitHubError
from app.integrations.github.importer import step
from app.integrations.github.models import GitHubImport,GitHubRepository,GitHubSourceVersion
from app.integrations.github.sync_models import GitHubSyncConfig,GitHubSyncRun,WebhookTarget,GitHubSourceHead,JobHeartbeat
from app.integrations.github.sync_service import schedule_one,schedule_due
from app.jobs.dispatch import publish_one,heartbeat,CeleryPublisher
from app.jobs.checkpoint import run_checkpoint
from app.jobs.models import OutboxMessage
from app.security.tokens import now
from tests.auth_helpers import mutation
from tests.phase8_helpers import queue,run,due
from tests.phase9_helpers import sync_environment,enable,config_body,schedule,send,make_due,event


def test_scheduler_and_event_coalesce_into_one_database_job(client,database,settings,tmp_path):
    _,root,fake,overview,*_=sync_environment(client,database,settings,tmp_path);cfg=enable(client,root,overview)
    assert send(client).status_code==202
    assert send(client,event(action='edited')).status_code==202
    id_=schedule(database,settings,cfg['id'])
    assert schedule_one(database,settings,UUID(cfg['id']))=='waiting'
    with database.session() as db:
        assert db.scalar(select(func.count()).select_from(GitHubImport))==1
        assert db.scalar(select(func.count()).select_from(GitHubSyncRun))==1
        assert db.scalar(select(func.count()).select_from(OutboxMessage))==1
        assert all(s.state=='scheduled' for s in db.scalars(select(WebhookTarget)))
    assert run(database,settings,fake,id_)[-1] in {'completed','completed_incomplete'}
    schedule_due(database,settings)
    current=client.get(root+'/github/sync').json()
    assert current['configurations'][0]['last_success_at']
    assert current['delivery_counts']['processed']==2
    assert all('THIS UNTRUSTED' not in str(s) for s in client.get(root+'/github/observations').json()['items'])


def test_reconciliation_runs_without_webhook_and_finds_old_created_pull(client,database,settings,tmp_path):
    _,root,fake,overview,*_=sync_environment(client,database,settings,tmp_path);cfg=enable(client,root,overview,lookback_days=1)
    id_=schedule(database,settings,cfg['id']);run(database,settings,fake,id_)
    assert any(path.endswith('/issues') and params.get('sort')=='updated' for path,params in fake.calls)
    with database.session() as db:
        assert db.scalar(select(GitHubSourceVersion).where(GitHubSourceVersion.kind=='pull_request'))
        assert db.get(GitHubImport,UUID(id_)).capture_mode=='sync'


def test_config_stale_revision_and_draft_preview_cannot_schedule(client,database,settings,tmp_path):
    _,root,_,overview,*_=sync_environment(client,database,settings,tmp_path);cfg=enable(client,root,overview)
    repo=overview['repositories'][0]['id']
    assert mutation(client,root+'/github/sync/'+repo,config_body(),method='put').status_code==409
    body={'expected_version':cfg['version'],'reviewed':True,'reason':'Request a fictional refresh'}
    assert mutation(client,root+'/github/sync/'+repo+'/request',body).status_code==200
    assert mutation(client,root+'/github/sync/'+repo+'/request',body).status_code==409


def test_pause_fences_active_import_and_requires_explicit_reenable(client,database,settings,tmp_path):
    _,root,_,overview,*_=sync_environment(client,database,settings,tmp_path);cfg=enable(client,root,overview)
    id_=schedule(database,settings,cfg['id']);repo=overview['repositories'][0]['id']
    assert mutation(client,root+'/github/sync/'+repo,config_body(cfg['version'],enabled=False),method='put').status_code==200
    with database.session() as db:assert db.get(GitHubImport,UUID(id_)).state=='cancelled'
    assert schedule_due(database,settings)==[]


def test_authorizer_github_permission_is_checked_before_any_data(client,database,settings,tmp_path):
    _,root,fake,overview,*_=sync_environment(client,database,settings,tmp_path);cfg=enable(client,root,overview)
    id_=schedule(database,settings,cfg['id']);fake.no_repo_admin=True
    assert step(database,settings,fake,UUID(id_))=='cancelled'
    assert fake.calls==[]
    with database.session() as db:assert not db.get(GitHubRepository,UUID(overview['repositories'][0]['id'])).enabled


def test_permission_revocation_during_network_discards_response(client,database,settings,tmp_path):
    _,root,fake,overview,*_=sync_environment(client,database,settings,tmp_path);cfg=enable(client,root,overview)
    id_=schedule(database,settings,cfg['id'])
    fake.on_get=lambda path:setattr(fake,'no_repo_admin',True)
    assert step(database,settings,fake,UUID(id_))=='cancelled'
    with database.session() as db:assert db.scalar(select(func.count()).select_from(GitHubSourceVersion))==0


def test_repository_backoff_cannot_be_bypassed_by_new_import(client,database,settings,tmp_path):
    _,root,fake,overview,*_=sync_environment(client,database,settings,tmp_path);cfg=enable(client,root,overview)
    id_=schedule(database,settings,cfg['id']);fake.error=GitHubError('github_rate_limited',retry_seconds=120)
    assert step(database,settings,fake,UUID(id_))=='paused'
    with database.session() as db:
        assert db.get(GitHubRepository,UUID(overview['repositories'][0]['id'])).retry_not_before
    repo=overview['repositories'][0]['id']
    response=mutation(client,root+'/github/sync/'+repo,config_body(cfg['version'],enabled=True),method='put')
    assert response.status_code==429
    from tests.phase8_helpers import import_body
    assert mutation(client,root+'/github/imports',import_body(repo)).status_code==429


class Publisher:
    def __init__(self):self.payloads=[];self.fail=False
    def publish(self,payload):
        self.payloads.append(payload)
        if self.fail:raise RuntimeError('Do not put the broker secret in logs')


def dispatch_due(database,job):
    with database.session() as db:
        row=db.scalar(select(OutboxMessage).where(OutboxMessage.job_id==UUID(job)))
        row.next_dispatch_at=now()-timedelta(seconds=1);db.commit()


def test_failed_broker_and_lost_message_are_republished_scoped_ids_only(client,database,settings,tmp_path):
    owner,root,fake,overview,*_=sync_environment(client,database,settings,tmp_path);cfg=enable(client,root,overview)
    id_=schedule(database,settings,cfg['id']);publisher=Publisher();publisher.fail=True
    assert publish_one(database,publisher)=='broker_unavailable'
    with database.session() as db:
        outbox=db.scalar(select(OutboxMessage));assert outbox.publish_error=='broker_publication_failed'
        assert db.get(GitHubImport,UUID(id_)).state=='queued'
    dispatch_due(database,id_);publisher.fail=False
    assert publish_one(database,publisher)=='published'
    assert publish_one(database,publisher)=='idle'
    dispatch_due(database,id_)
    assert publish_one(database,publisher)=='published' # broker lost accepted message: DB resends.
    assert publisher.payloads[-1]=={'job_id':id_,'workspace_id':owner['workspace']['id'],'project_id':owner['project']['id']}


def test_scope_checked_again_when_broker_message_runs(client,database,settings,tmp_path):
    owner,root,fake,overview,*_=sync_environment(client,database,settings,tmp_path);cfg=enable(client,root,overview)
    id_=schedule(database,settings,cfg['id'])
    assert run_checkpoint(database,settings,fake,id_,str(uuid4()),owner['project']['id'])=='scope_rejected'
    assert run_checkpoint(database,settings,fake,'bad',owner['workspace']['id'],owner['project']['id'])=='invalid_message'
    assert fake.calls==[]
    assert run_checkpoint(database,settings,fake,id_,owner['workspace']['id'],owner['project']['id'])=='queued'


def test_live_lease_rejects_duplicate_execution(client,database,settings,tmp_path):
    _,root,fake,overview,*_=sync_environment(client,database,settings,tmp_path);cfg=enable(client,root,overview)
    id_=schedule(database,settings,cfg['id'])
    with database.session() as db:
        j=db.get(GitHubImport,UUID(id_));j.state='running';j.lease_token=uuid4();j.lease_until=now()+timedelta(seconds=100);db.commit()
    assert step(database,settings,fake,UUID(id_))=='idle'
    assert publish_one(database,Publisher())=='idle'
    with database.session() as db:
        j=db.get(GitHubImport,UUID(id_));j.lease_until=now()-timedelta(seconds=1);db.commit()
    assert step(database,settings,fake,UUID(id_))=='queued'


def test_heartbeat_is_upsert_not_unbounded_log(database):
    heartbeat(database,'test-worker','idle');heartbeat(database,'test-worker','processed')
    with database.session() as db:
        assert db.scalar(select(func.count()).select_from(JobHeartbeat))==1
        assert db.get(JobHeartbeat,'test-worker').status=='processed'


def test_celery_publication_has_no_results_or_arbitrary_task():
    class App:
        def send_task(self,*args,**kwargs):self.args=args;self.kwargs=kwargs
    app=App();payload={'job_id':str(uuid4()),'workspace_id':str(uuid4()),'project_id':str(uuid4())}
    CeleryPublisher(app).publish(payload)
    assert app.args==('ledger.github.checkpoint',) and app.kwargs['kwargs']==payload
    assert app.kwargs['serializer']=='json' and app.kwargs['ignore_result'] and not app.kwargs['retry']
