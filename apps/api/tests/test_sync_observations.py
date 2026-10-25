from datetime import timedelta
from uuid import UUID,uuid4
from types import SimpleNamespace
import pytest
from sqlalchemy import select,func,text
from app.integrations.github.client import GitHubClient,GitHubError
from app.integrations.github.models import GitHubImport,GitHubRepository,GitHubSourceVersion,GitHubFetchTask,GitHubEvidenceLink
from app.integrations.github.sync_models import GitHubSourceHead,GitHubSyncConfig
from app.integrations.github.sync_service import observe_head,schedule_one
from app.integrations.github.importer import step,claim,failure
from app.jobs.dispatch import claim_publication,publish_one
from app.jobs.models import OutboxMessage
from app.security.tokens import now,utc
from tests.auth_helpers import mutation,other_client,invite,accept
from tests.phase8_helpers import queue,run,pull,REPO
from tests.phase5_helpers import metadata
from tests.phase9_helpers import sync_environment,enable,schedule,send,event,make_due

@pytest.mark.parametrize('permission,user_id',[('read',7001),('write',7001),('none',7001),('admin',9000),('admin',True)])
def test_remote_permission_check_rejects_wrong_principal(permission,user_id):
    client=GitHubClient(SimpleNamespace(),None)
    client.get=lambda *a:({'permission':permission,'user':{'id':user_id}},False)
    with pytest.raises(GitHubError,match='github_authority_revoked'):
        client.check_repository_authority('synthetic',SimpleNamespace(full_name='synthetic/game'),SimpleNamespace(github_login='fictional-author',github_user_id=7001))

def test_remote_permission_check_uses_expected_repo_and_login():
    client=GitHubClient(SimpleNamespace(),None);calls=[]
    def get(*args):calls.append(args);return {'permission':'admin','user':{'id':7001}},False
    client.get=get
    client.check_repository_authority('synthetic',SimpleNamespace(full_name='synthetic/game'),SimpleNamespace(github_login='fictional-author',github_user_id=7001))
    assert calls==[('synthetic','/repos/synthetic/game/collaborators/fictional-author/permission')]


def test_new_sources_warn_without_replacing_pinned_evidence(client,database,settings,tmp_path):
    _,root,fake,overview,path,pkg=sync_environment(client,database,settings,tmp_path,package=True)
    job,_=queue(client,root,overview);run(database,settings,fake,job['id'])
    with database.session() as db:
        source=db.scalar(select(GitHubSourceVersion).where(GitHubSourceVersion.kind=='pull_request'))
        sid=str(source.id);content_hash=source.content_hash
    result=mutation(client,root+'/github/sources/'+sid+'/link',{
        'package_id':pkg['id'],'expected_package_version':pkg['version'],'reviewed_source_hash':content_hash,
        'metadata':metadata(title='Pinned fictional GitHub PR',visibility='project'),
        'reason':'Attach a reviewed exact source version','request_id':str(uuid4()),'sharing_confirmed':True})
    assert result.status_code==201,result.text
    cfg=enable(client,root,overview);fake.pull_title='New authoritative title, not the webhook body'
    assert send(client).status_code==202
    sync_id=schedule(database,settings,cfg['id']);run(database,settings,fake,sync_id)
    with database.session() as db:
        assert str(db.scalar(select(GitHubEvidenceLink)).source_id)==sid
        old=db.get(GitHubSourceVersion,UUID(sid));assert old.content_hash==content_hash
        head=db.scalar(select(GitHubSourceHead).where(GitHubSourceHead.kind=='pull_request'))
        assert str(head.source_id)!=sid
    assert client.get(root+'/github/sync').json()['linked_sources_with_new_observations']==1


def test_unavailable_primary_source_preserves_previous_version(client,database,settings,tmp_path):
    _,root,fake,overview,*_=sync_environment(client,database,settings,tmp_path)
    job,_=queue(client,root,overview);run(database,settings,fake,job['id'])
    with database.session() as db:
        old=db.scalar(select(GitHubSourceHead).where(GitHubSourceHead.kind=='pull_request')).source_id
    cfg=enable(client,root,overview);original=fake.get
    def get(token,path,params=None):
        if path.endswith('/pulls/1'):raise GitHubError('github_access_denied')
        return original(token,path,params)
    fake.get=get;sync_id=schedule(database,settings,cfg['id'])
    assert run(database,settings,fake,sync_id)[-1]=='completed_incomplete'
    with database.session() as db:
        head=db.scalar(select(GitHubSourceHead).where(GitHubSourceHead.kind=='pull_request'))
        assert head.state=='unavailable' and head.source_id==old and db.get(GitHubSourceVersion,old)


def test_old_remote_updated_value_does_not_regress_head(client,database,settings,tmp_path):
    _,root,fake,overview,*_=sync_environment(client,database,settings,tmp_path)
    job,_=queue(client,root,overview);run(database,settings,fake,job['id'])
    with database.session() as db:
        head=db.scalar(select(GitHubSourceHead).where(GitHubSourceHead.kind=='pull_request'));old=head.source_id
        # An old authoritative response can be retained as history but not replace
        # an already newer projection. This unit-level guard doesn't invent history.
        head.remote_updated_at=now();db.flush()
        jobrow=db.get(GitHubImport,UUID(job['id']));repo=db.get(GitHubRepository,jobrow.repository_id)
        observe_head(db,jobrow,repo,SimpleNamespace(id=uuid4(),kind='pull_request',remote_key='1'),now()-timedelta(days=2))
        assert head.source_id==old


def test_old_publication_lease_is_fenced(client,database,settings,tmp_path):
    _,root,_,overview,*_=sync_environment(client,database,settings,tmp_path);cfg=enable(client,root,overview)
    job_id=schedule(database,settings,cfg['id'])
    class Publisher:
        def publish(self,payload):
            with database.session() as db:
                outbox=db.scalar(select(OutboxMessage));outbox.dispatch_lease=uuid4();db.commit()
    assert publish_one(database,Publisher())=='discarded'
    with database.session() as db:assert db.scalar(select(OutboxMessage)).last_published_at is None


def test_old_worker_cannot_commit_after_new_lease(client,database,settings,tmp_path):
    _,root,fake,overview,*_=sync_environment(client,database,settings,tmp_path);cfg=enable(client,root,overview)
    job_id=schedule(database,settings,cfg['id'])
    def change_fence(path):
        with database.session() as db:
            job=db.get(GitHubImport,UUID(job_id));job.lease_token=uuid4();db.commit()
    fake.on_get=change_fence
    assert step(database,settings,fake,UUID(job_id))=='discarded'
    with database.session() as db:assert db.scalar(select(func.count()).select_from(GitHubSourceVersion))==0


def test_expired_authority_disables_periodic_schedule(client,database,settings,tmp_path):
    from app.integrations.github.models import GitHubConnection
    _,root,fake,overview,*_=sync_environment(client,database,settings,tmp_path);cfg=enable(client,root,overview)
    with database.session() as db:
        db.scalar(select(GitHubConnection)).verified_until=now()-timedelta(seconds=1);db.commit()
    make_due(database,cfg['id']);assert schedule_one(database,settings,UUID(cfg['id']))=='blocked'
    with database.session() as db:assert not db.get(GitHubSyncConfig,UUID(cfg['id'])).enabled
    assert fake.calls==[]
