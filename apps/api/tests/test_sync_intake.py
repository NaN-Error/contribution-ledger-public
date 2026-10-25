from datetime import timedelta
from uuid import UUID,uuid4
import pytest
from sqlalchemy import select,func,text
from sqlalchemy.exc import IntegrityError
from app.integrations.github.models import GitHubConnection,GitHubRepository,GitHubImport
from app.integrations.github.sync_models import WebhookDelivery,WebhookTarget,GitHubSyncConfig
from app.jobs.models import OutboxMessage
from app.security.tokens import now
from tests.auth_helpers import mutation,other_client,invite,accept
from tests.phase8_helpers import queue
from tests.phase9_helpers import sync_environment,enable,send,event,signed


def test_signed_intake_commits_without_provider_or_broker(client,database,settings,tmp_path):
    owner,root,fake,overview,*_=sync_environment(client,database,settings,tmp_path)
    cfg=enable(client,root,overview);response=send(client)
    assert response.status_code==202,response.text
    with database.session() as db:
        assert db.scalar(select(func.count()).select_from(WebhookDelivery))==1
        assert db.scalar(select(WebhookTarget)).state=='pending'
        assert db.scalar(select(func.count()).select_from(OutboxMessage))==0
    assert fake.calls==[]


def test_same_body_and_delivery_replay_do_not_duplicate(client,database,settings,tmp_path):
    _,root,_,overview,*_=sync_environment(client,database,settings,tmp_path);enable(client,root,overview)
    id_=uuid4()
    assert send(client,delivery=id_).status_code==202
    assert send(client,delivery=id_).json()['duplicate']
    assert send(client,delivery=uuid4()).json()['duplicate']
    with database.session() as db:assert db.scalar(select(func.count()).select_from(WebhookTarget))==1


def test_changed_routing_headers_or_reused_delivery_fail(client,database,settings,tmp_path):
    _,root,_,overview,*_=sync_environment(client,database,settings,tmp_path);enable(client,root,overview)
    id_=uuid4();assert send(client,delivery=id_).status_code==202
    assert send(client,event(action='edited'),delivery=id_).status_code==409
    raw,headers=signed(event());headers['x-github-event']='repository'
    assert client.post('/api/v1/github/webhook',content=raw,headers=headers).status_code==400


def test_unauthenticated_event_needs_signature_not_cookie(client,database,settings,tmp_path):
    _,root,_,overview,*_=sync_environment(client,database,settings,tmp_path);enable(client,root,overview)
    with other_client(settings,database) as stranger:
        assert send(stranger).status_code==202
        raw,headers=signed(event());headers['x-hub-signature-256']='sha256='+'0'*64
        assert stranger.post('/api/v1/github/webhook',content=raw,headers=headers).status_code==401
        assert stranger.get(root+'/github/deliveries').status_code==401
    assert client.put(root+'/github/sync/'+overview['repositories'][0]['id'],json={}).status_code==403


def test_webhook_disabled_and_missing_secret(client,database,settings,tmp_path):
    assert send(client).status_code==404
    sync_environment(client,database,settings,tmp_path)
    signing=settings.github_secret_root/'github-webhook-secret'
    signing.chmod(0o600)  # Windows refuses unlink of the fixture's read-only file.
    signing.unlink()
    assert send(client).status_code==503


def test_unknown_installation_is_not_a_repository_authorization(client,database,settings,tmp_path):
    _,root,_,overview,*_=sync_environment(client,database,settings,tmp_path);enable(client,root,overview)
    assert send(client,event(installation={'id':9999})).status_code==202
    with database.session() as db:assert db.scalar(select(func.count()).select_from(WebhookTarget))==0


@pytest.mark.parametrize('event_name,body',[
 ('installation',event(action='deleted')),('installation',event(action='suspend')),
 ('installation_repositories',event(action='removed',repositories_removed=[{'id':9001}])),
 ('repository',event(action='renamed'))])
def test_revocation_fences_pending_and_running_work(client,database,settings,tmp_path,event_name,body):
    _,root,_,overview,*_=sync_environment(client,database,settings,tmp_path);cfg=enable(client,root,overview)
    job,_=queue(client,root,overview)
    with database.session() as db:
        j=db.get(GitHubImport,UUID(job['id']));j.state='running';j.lease_token=uuid4();j.lease_until=now()+timedelta(seconds=180);db.commit()
    assert send(client,body,event_name).status_code==202
    with database.session() as db:
        assert not db.get(GitHubRepository,UUID(overview['repositories'][0]['id'])).enabled
        assert not db.get(GitHubSyncConfig,UUID(cfg['id'])).enabled
        j=db.get(GitHubImport,UUID(job['id']));assert j.state=='cancelled' and j.lease_token is None
    assert send(client,event(action='unsuspend'),'installation').status_code==202
    with database.session() as db:assert not db.get(GitHubRepository,UUID(overview['repositories'][0]['id'])).enabled


def test_delivery_cannot_mutate_or_delete_history(client,database,settings,tmp_path):
    sync_environment(client,database,settings,tmp_path);assert send(client).status_code==202
    for sql in ("UPDATE github_webhook_deliveries SET event='push'",'DELETE FROM github_webhook_deliveries'):
        with database.session() as db:
            with pytest.raises(IntegrityError):db.execute(text(sql))


def test_contributors_cannot_browse_raw_operational_history(client,database,settings,tmp_path):
    owner,root,_,overview,*_=sync_environment(client,database,settings,tmp_path);enable(client,root,overview)
    invitation=invite(client,owner['workspace']['id'],project_id=owner['project']['id'])
    with other_client(settings,database) as member:
        accept(member,invitation['token'])
        for suffix in ['sync','jobs','deliveries','observations']:
            assert member.get(root+'/github/'+suffix).status_code==403


def test_intake_rollback_does_not_ack_receipt(client,database,settings,tmp_path,monkeypatch):
    _,root,_,overview,*_=sync_environment(client,database,settings,tmp_path);enable(client,root,overview)
    from app.integrations.github import webhooks
    original=webhooks.accept_delivery
    def fail(db,envelope,settings):
        original(db,envelope,settings)
        raise RuntimeError('Synthetic interruption before commit')
    monkeypatch.setattr(webhooks,'accept_delivery',fail)
    client._transport.raise_server_exceptions=False
    assert send(client).status_code==500
    with database.session() as db:assert db.scalar(select(func.count()).select_from(WebhookDelivery))==0
