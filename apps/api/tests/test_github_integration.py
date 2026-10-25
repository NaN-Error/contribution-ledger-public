from copy import deepcopy
from datetime import timedelta
from uuid import uuid4,UUID
import pytest
from sqlalchemy import select,func,update
from app.integrations.github.client import GitHubError
from app.integrations.github.models import GitHubAuthFlow,GitHubSourceVersion,GitHubImport,GitHubConnection,GitHubIdentity,GitHubObservation,GitHubFetchTask
from app.integrations.github.importer import step,claim,LEASE_SECONDS
from app.security.tokens import now
from tests.auth_helpers import mutation,other_client,invite,accept,login,bootstrap
from tests.phase5_helpers import metadata,revise
from tests.phase8_helpers import environment,configure,flow,authorize,queue,run,due,SHA_A


def test_complete_import_preserves_roles_and_no_credit(client,database,settings):
    owner,root,fake,overview,_,_=environment(client,database,settings)
    job,_=queue(client,root,overview)
    results=run(database,settings,fake,job['id'])
    assert results[-1]=='completed',client.get(root+'/github/imports/'+job['id']).text
    result=client.get(root+'/github/imports/'+job['id']).json()
    assert result['anchor_sha']==SHA_A and result['tasks'].get('pending',0)==0
    rows=client.get(root+'/github/sources?limit=50').json()['items']
    assert {'pull_request','issue','commit','review','comment','review_comment','pull_files','commit_files','check_run'} <= {s['kind'] for s in rows}
    doc=client.get(root+'/github/sources/'+next(s['id'] for s in rows if s['kind']=='pull_request')).json()['document']
    assert {i['role'] for i in doc['identities']}=={'pull_request_author','merger_not_assumed_author'}
    identities=client.get(root+'/github/identities').json()['items']
    assert any(i['kind']=='email_claim' for i in identities)
    assert all(i['linked_user_id'] is None for i in identities)
    with database.session() as db:
        from app.ledger.models import CreditAward
        assert db.scalar(select(func.count()).select_from(CreditAward))==0
    assert all(p.startswith('/repos/synthetic/game') for p,_ in fake.calls)


def test_idempotent_request_and_source_versions(client,database,settings):
    _,root,fake,overview,_,_=environment(client,database,settings)
    job,body=queue(client,root,overview)
    assert mutation(client,root+'/github/imports',body).json()['id']==job['id']
    assert mutation(client,root+'/github/imports',{**body,'entity_limit':21}).status_code==409
    assert run(database,settings,fake,job['id'])[-1]=='completed'
    with database.session() as db:first=db.scalar(select(func.count()).select_from(GitHubSourceVersion))
    job2,_=queue(client,root,overview)
    assert run(database,settings,fake,job2['id'])[-1]=='completed'
    with database.session() as db:
        assert db.scalar(select(func.count()).select_from(GitHubSourceVersion))==first
        assert db.scalar(select(func.count()).select_from(GitHubObservation))>first


def test_changed_history_preserves_prior_version(client,database,settings):
    _,root,fake,overview,_,_=environment(client,database,settings)
    job,_=queue(client,root,overview);run(database,settings,fake,job['id'])
    old=client.get(root+'/github/sources?kind=pull_request').json()['items'][0]
    fake.pull_title='Changed source title observed later'
    job2,_=queue(client,root,overview);run(database,settings,fake,job2['id'])
    assert len(client.get(root+'/github/sources?kind=pull_request').json()['items'])==2
    preserved=client.get(root+'/github/sources/'+old['id']).json()
    assert preserved['document']['content']['title']=='Synthetic reconnection PR' and preserved['other_preserved_versions']==1


def test_arbitrary_installation_not_connected(client,database,settings):
    owner=bootstrap(client,database);fake=configure(settings,client)
    root=f"/api/v1/workspaces/{owner['workspace']['id']}/projects/{owner['project']['id']}"
    response=mutation(client,root+'/github/authorize',{'installation_id':999,'reason':'Try a synthetic unrelated installation'})
    from urllib.parse import parse_qs,urlsplit
    state=parse_qs(urlsplit(response.json()['authorize_url']).query)['state'][0]
    assert mutation(client,'/api/v1/github/callback',{'state':state,'code':'synthetic-code-12345'}).status_code==403
    assert not client.get(root+'/github').json()['connections']


def test_authorization_state_replay_expiry_and_unoffered_repository(client,database,settings):
    _,root,fake,_,_,_=environment(client,database,settings)
    state=flow(client,root);body={'state':state,'code':'synthetic-code-12345'}
    proof=mutation(client,'/api/v1/github/callback',body).json()
    assert mutation(client,'/api/v1/github/callback',body).status_code==409
    assert mutation(client,'/api/v1/github/connect',{'flow_id':proof['flow_id'],'reviewed_proof_hash':proof['proof_hash'],'repository_ids':[9999],'sharing_confirmed':True,'reason':'Reject an unverified repository'}).status_code==403
    with database.session() as db:
        f=db.get(GitHubAuthFlow,UUID(proof['flow_id']));f.expires_at=now()-timedelta(seconds=1);db.commit()
    assert mutation(client,'/api/v1/github/connect',{'flow_id':proof['flow_id'],'reviewed_proof_hash':proof['proof_hash'],'repository_ids':[9001],'sharing_confirmed':True,'reason':'Reject an expired source proof'}).status_code==403


def test_state_bound_to_original_browser_session(client,database,settings):
    _,root,_,_,_,_=environment(client,database,settings);state=flow(client,root)
    with other_client(settings,database) as second:
        assert login(second).status_code==200
        assert mutation(second,'/api/v1/github/callback',{'state':state,'code':'synthetic-code-12345'}).status_code==403


def test_wrong_callback_origin_and_missing_csrf_fail(client,database,settings):
    _,root,_,_,_,_=environment(client,database,settings)
    settings.github_callback_url='http://127.0.0.1:5173/github/callback'
    body={'installation_id':501,'reason':'Origin check for local authorization'}
    assert mutation(client,root+'/github/authorize',body).status_code==409
    assert client.post(root+'/github/authorize',json=body).status_code==403


def test_failed_exchange_is_consumed_without_remote_details(client,database,settings):
    _,root,fake,_,_,_=environment(client,database,settings);state=flow(client,root)
    fake.error=GitHubError('github_authorization_failed');body={'state':state,'code':'synthetic-code-12345'}
    response=mutation(client,'/api/v1/github/callback',body)
    assert response.status_code==503 and 'synthetic-code' not in response.text
    calls=fake.verify_calls;assert mutation(client,'/api/v1/github/callback',body).status_code==409
    assert fake.verify_calls==calls


def test_reauthorizing_cancels_old_jobs(client,database,settings):
    _,root,fake,overview,_,_=environment(client,database,settings);job,_=queue(client,root,overview)
    authorize(client,root)
    assert client.get(root+'/github/imports/'+job['id']).json()['state']=='cancelled'
    assert step(database,settings,fake,UUID(job['id']))=='idle'


def test_disconnect_preserves_sources_and_cancels_remaining(client,database,settings):
    _,root,fake,overview,_,_=environment(client,database,settings);job,_=queue(client,root,overview)
    for _ in range(6):step(database,settings,fake,UUID(job['id']))
    with database.session() as db:count=db.scalar(select(func.count()).select_from(GitHubSourceVersion))
    conn=overview['connections'][0]
    response=mutation(client,root+'/github/connections/'+conn['id']+'/disconnect',{'expected_version':conn['version'],'reviewed':True,'reason':'Stop synthetic import without deleting history'})
    assert response.status_code==200,response.text
    assert step(database,settings,fake,UUID(job['id']))=='idle'
    assert client.get(root+'/github/imports/'+job['id']).json()['state']=='cancelled'
    with database.session() as db:assert db.scalar(select(func.count()).select_from(GitHubSourceVersion))==count


def test_retry_delay_and_bounded_failures(client,database,settings):
    _,root,fake,overview,_,_=environment(client,database,settings);job,_=queue(client,root,overview)
    fake.error=GitHubError('github_rate_limited',3600)
    assert step(database,settings,fake,UUID(job['id']))=='paused'
    current=client.get(root+'/github/imports/'+job['id']).json()
    assert mutation(client,root+'/github/imports/'+job['id']+'/resume',{'expected_version':current['version'],'reason':'Must not override a rate-limit delay'}).status_code==429
    assert step(database,settings,fake,UUID(job['id']))=='idle'
    for _ in range(4):due(database,job['id']);step(database,settings,fake,UUID(job['id']))
    current=client.get(root+'/github/imports/'+job['id']).json()
    assert current['failures']==5 and current['state']=='failed'
    due(database,job['id'])
    assert mutation(client,root+'/github/imports/'+job['id']+'/resume',{'expected_version':current['version'],'reason':'Must not bypass bounded retry count'}).status_code==409


def test_retry_resumes_same_task_and_checkpoint(client,database,settings):
    _,root,fake,overview,_,_=environment(client,database,settings);job,_=queue(client,root,overview)
    step(database,settings,fake,UUID(job['id']))
    fake.error=GitHubError('github_unavailable',60)
    assert step(database,settings,fake,UUID(job['id']))=='paused'
    due(database,job['id']);fake.error=None
    assert run(database,settings,fake,job['id'])[-1]=='completed'
    assert sum(p=='/repos/synthetic/game' for p,_ in fake.calls)==1


def test_cancel_during_fetch_discards_result(client,database,settings):
    _,root,fake,overview,_,_=environment(client,database,settings);job,_=queue(client,root,overview)
    def cancel(path):
        current=client.get(root+'/github/imports/'+job['id']).json()
        response=mutation(client,root+'/github/imports/'+job['id']+'/cancel',{'expected_version':current['version'],'reason':'Cancel while a network response is in flight'})
        assert response.status_code==200,response.text
    fake.on_get=cancel
    assert step(database,settings,fake,UUID(job['id']))=='discarded'
    with database.session() as db:
        assert db.scalar(select(func.count()).select_from(GitHubSourceVersion))==0
        assert db.get(GitHubImport,UUID(job['id'])).data_requests==1


def test_expired_lease_reclaims_with_new_fence(client,database,settings):
    _,root,fake,overview,_,_=environment(client,database,settings);job,_=queue(client,root,overview)
    first=claim(database,UUID(job['id']));assert first
    assert claim(database,UUID(job['id'])) is None
    with database.session() as db:j=db.get(GitHubImport,UUID(job['id']));j.lease_until=now()-timedelta(seconds=1);db.commit()
    second=claim(database,UUID(job['id']));assert second and first[1]!=second[1]


def test_request_budget_and_empty_repository_are_explicit(client,database,settings):
    _,root,fake,overview,_,_=environment(client,database,settings);job,_=queue(client,root,overview,request_limit=10)
    assert run(database,settings,fake,job['id'])[-1]=='completed_incomplete'
    result=client.get(root+'/github/imports/'+job['id']).json()
    assert result['data_requests']<=10 and any('budget_reached' in s for s in result['omissions'])


def test_changed_pull_head_discards_file_page(client,database,settings):
    _,root,fake,overview,_,_=environment(client,database,settings);job,_=queue(client,root,overview)
    # Change only after the initial PR detail establishes the expected SHA.
    def alter(path):
        if path.endswith('/pulls/1/files'):fake.head_changed=True
    fake.on_get=alter
    assert run(database,settings,fake,job['id'])[-1]=='completed_incomplete'
    result=client.get(root+'/github/imports/'+job['id']).json()
    assert any('head_or_base_changed' in s for s in result['omissions'])
    assert not client.get(root+'/github/sources?kind=pull_files').json()['items']


def test_expired_authorization_stops_worker(client,database,settings):
    _,root,fake,overview,_,_=environment(client,database,settings);job,_=queue(client,root,overview)
    with database.session() as db:c=db.get(GitHubConnection,UUID(overview['connections'][0]['id']));c.verified_until=now()-timedelta(seconds=1);db.commit()
    assert step(database,settings,fake,UUID(job['id']))=='failed' and not fake.calls


def test_source_access_and_cross_project_boundaries(client,database,settings):
    owner,root,fake,overview,_,_=environment(client,database,settings);job,_=queue(client,root,overview);run(database,settings,fake,job['id'])
    source=client.get(root+'/github/sources').json()['items'][0]
    invitation=invite(client,owner['workspace']['id'],project_id=owner['project']['id'])
    with other_client(settings,database) as member:
        accept(member,invitation['token'])
        assert member.get(root+'/github').status_code==403
        assert member.get(root+'/github/sources/'+source['id']).status_code==403
        assert mutation(member,root+'/github/imports',{}).status_code==422 # strict schema before scoped command
    project=mutation(client,f"/api/v1/workspaces/{owner['workspace']['id']}/projects",{'name':'Other synthetic game','description':'Separate source scope','timezone':'UTC','currency':'USD'}).json()
    otherroot=f"/api/v1/workspaces/{owner['workspace']['id']}/projects/{project['id']}/github"
    assert client.get(otherroot+'/sources/'+source['id']).status_code==404
    assert client.get(otherroot+'/sources?repository_id='+overview['repositories'][0]['id']).status_code==404


def test_mapping_history_and_pin_evidence(client,database,settings):
    owner,root,fake,overview,path,pkg=environment(client,database,settings,package=True)
    job,_=queue(client,root,overview);assert run(database,settings,fake,job['id'])[-1]=='completed'
    identities=client.get(root+'/github/identities').json()['items'];identity=next(i for i in identities if i['external_key']=='github:7001')
    command={'expected_version':identity['version'],'user_id':owner['user']['id'],'reviewed':True,'reason':'Map only after reviewing the source author claim'}
    response=mutation(client,root+'/github/identities/'+identity['id']+'/mapping',command);assert response.status_code==200,response.text
    assert mutation(client,root+'/github/identities/'+identity['id']+'/mapping',command).status_code==409
    source=client.get(root+'/github/sources?kind=pull_request').json()['items'][0]
    body={'package_id':pkg['id'],'expected_package_version':client.get(path).json()['version'],'reviewed_source_hash':source['content_hash'],
      'metadata':metadata(visibility='restricted'),'reason':'Attach the reviewed source as private evidence','request_id':str(uuid4()),'sharing_confirmed':True}
    response=mutation(client,root+'/github/sources/'+source['id']+'/link',body);assert response.status_code==201,response.text
    linked=response.json();assert not linked['already_linked']
    assert mutation(client,root+'/github/sources/'+source['id']+'/link',body).json()['already_linked']
    revision_path=path+f"/evidence/{linked['evidence_id']}/revisions/1"
    original=client.get(revision_path).json();origin=original['document']['external_source']
    assert origin['source_hash']==source['content_hash']
    assert origin['mapping_at_link'][0]['mapped_user_id']==owner['user']['id']
    assert client.get(revision_path+'/github-source').json()['content_hash']==source['content_hash']
    response=revise(client,path,original,text='Human-edited statement, original source remains pinned.');assert response.status_code==200,response.text
    assert client.get(path+f"/evidence/{linked['evidence_id']}/revisions/2/github-source").status_code==200
    assert client.get(revision_path).json()['content_hash']==original['content_hash']
    assert client.get(root+'/github/identities/'+identity['id']+'/history').json()['items'][0]['linked_user_id']==owner['user']['id']


def test_unlinked_source_is_not_public_evidence(client,database,settings):
    owner,root,fake,overview,path,pkg=environment(client,database,settings,package=True)
    job,_=queue(client,root,overview);run(database,settings,fake,job['id'])
    source=client.get(root+'/github/sources?kind=pull_request').json()['items'][0]
    body={'package_id':pkg['id'],'expected_package_version':client.get(path).json()['version'],'reviewed_source_hash':source['content_hash'],
      'metadata':metadata(visibility='project'),'reason':'Explicitly share this source with the project','request_id':str(uuid4()),'sharing_confirmed':True}
    link=mutation(client,root+'/github/sources/'+source['id']+'/link',body).json()
    invitation=invite(client,owner['workspace']['id'],project_id=owner['project']['id'])
    with other_client(settings,database) as member:
        accept(member,invitation['token'])
        assert member.get(root+'/github/sources/'+source['id']).status_code==403
        assert member.get(path+f"/evidence/{link['evidence_id']}/revisions/1/github-source").status_code==200
        assert member.get(path+f"/evidence/{uuid4()}/revisions/1/github-source").status_code==404


def test_bot_cannot_map_to_human(client,database,settings):
    owner,root,_,_,_,_=environment(client,database,settings)
    with database.session() as db:
        bot=GitHubIdentity(workspace_id=UUID(owner['workspace']['id']),project_id=UUID(owner['project']['id']),external_key='github:999',kind='github_bot',label='bot',version=1)
        db.add(bot);db.commit();bot_id=str(bot.id)
    response=mutation(client,root+'/github/identities/'+bot_id+'/mapping',{'expected_version':1,'user_id':owner['user']['id'],'reviewed':True,'reason':'Attempt synthetic bot to human attribution'})
    assert response.status_code==422


def test_child_page_limit_and_missing_commits_are_visible(client,database,settings):
    _,root,fake,overview,_,_=environment(client,database,settings)
    fake.more_for.add('/repos/synthetic/game/issues/2/comments');fake.empty=True
    job,_=queue(client,root,overview)
    assert run(database,settings,fake,job['id'])[-1]=='completed_incomplete'
    current=client.get(root+'/github/imports/'+job['id']).json()
    assert any('anchor' in s for s in current['omissions'])
    assert any('page' in s for s in current['omissions'])
    assert sum(p.endswith('/issues/2/comments') for p,_ in fake.calls)==5


def test_oversized_response_records_omission_not_infinite_retry(client,database,settings):
    _,root,fake,overview,_,_=environment(client,database,settings)
    normal=fake.get
    def bounded(token,path,params=None):
        if path.endswith('/pulls/1/reviews'):raise GitHubError('github_response_too_large')
        return normal(token,path,params)
    fake.get=bounded
    job,_=queue(client,root,overview)
    assert run(database,settings,fake,job['id'])[-1]=='completed_incomplete'
    current=client.get(root+'/github/imports/'+job['id']).json()
    assert any('response_size_limit' in s for s in current['omissions']) and current['failures']==0


def test_reviewer_can_read_but_cannot_import_or_map(client,database,settings):
    owner,root,fake,overview,_,_=environment(client,database,settings)
    invitation=invite(client,owner['workspace']['id'],project_id=owner['project']['id'],role='reviewer')
    from tests.phase8_helpers import import_body
    with other_client(settings,database) as reviewer:
        accept(reviewer,invitation['token'])
        assert reviewer.get(root+'/github').status_code==200
        assert mutation(reviewer,root+'/github/imports',import_body(overview['repositories'][0]['id'])).status_code==403
        assert mutation(reviewer,root+'/github/authorize',{'installation_id':501,'reason':'A reviewer must not authorize source sharing'}).status_code==403


def test_restricted_source_history_cannot_be_made_public_retroactively(client,database,settings):
    owner,root,fake,overview,path,pkg=environment(client,database,settings,package=True)
    job,_=queue(client,root,overview);run(database,settings,fake,job['id'])
    source=client.get(root+'/github/sources?kind=pull_request').json()['items'][0]
    body={'package_id':pkg['id'],'expected_package_version':client.get(path).json()['version'],'reviewed_source_hash':source['content_hash'],
      'metadata':metadata(visibility='restricted'),'reason':'Initially restrict the source to reviewers','request_id':str(uuid4()),'sharing_confirmed':True}
    link=mutation(client,root+'/github/sources/'+source['id']+'/link',body).json()
    original=client.get(path+f"/evidence/{link['evidence_id']}/revisions/1").json()
    assert revise(client,path,original,metadata=metadata(visibility='project')).status_code==200
    invitation=invite(client,owner['workspace']['id'],project_id=owner['project']['id'])
    with other_client(settings,database) as member:
        accept(member,invitation['token'])
        assert member.get(path+f"/evidence/{link['evidence_id']}/revisions/1/github-source").status_code in {403,404}
        assert member.get(path+f"/evidence/{link['evidence_id']}/revisions/2/github-source").status_code==200


def test_cross_project_link_cannot_create_evidence(client,database,settings):
    owner,root,fake,overview,path,pkg=environment(client,database,settings,package=True)
    job,_=queue(client,root,overview);run(database,settings,fake,job['id'])
    source=client.get(root+'/github/sources?kind=pull_request').json()['items'][0]
    body={'package_id':str(uuid4()),'expected_package_version':1,'reviewed_source_hash':source['content_hash'],
      'metadata':metadata(),'reason':'Reject an unrelated work package reference','request_id':str(uuid4()),'sharing_confirmed':True}
    assert mutation(client,root+'/github/sources/'+source['id']+'/link',body).status_code==404
    body['package_id']=pkg['id'];body['reviewed_source_hash']='0'*64
    assert mutation(client,root+'/github/sources/'+source['id']+'/link',body).status_code==409
    assert not client.get(path+'/evidence').json()['items']


def test_disabled_github_keeps_manual_account_routes_working(client,database,settings):
    owner=bootstrap(client,database);root=f"/api/v1/workspaces/{owner['workspace']['id']}/projects/{owner['project']['id']}"
    assert client.get(root+'/github').json()['configured'] is False
    response=mutation(client,root+'/github/authorize',{'installation_id':501,'reason':'A disabled integration must not contact GitHub'})
    assert response.status_code==503 and client.get(root).status_code==200
