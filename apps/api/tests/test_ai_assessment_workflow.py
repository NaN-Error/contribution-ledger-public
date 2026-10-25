import json
from datetime import timedelta
from uuid import UUID,uuid4
import pytest
from sqlalchemy import select,func
from app.ai.jobs import claim,execute,maintain
from app.ai.models import AIConnection,AIJob,AIProfile,AIUsageBucket
from app.ai.assessments.models import AIReviewPacket,AIReviewPlan,AIReviewResult,AIReviewGrant,AIReviewFeedback
from app.ai.assessments.prompt import generation_material
from app.providers.mock import MockProvider
from app.providers.contracts import GenerationResult,ProviderError
from app.ledger.models import CreditAward,ContributionEvent
from app.projects.models import ProjectMembership
from app.security.tokens import now
from tests.phase11_helpers import setup,packet,plan,grant,enqueue,complete
from tests.auth_helpers import mutation
from tests.phase5_helpers import add,metadata,file_input,revise,png_bytes
from tests.phase4_helpers import advance
from tests.phase6_helpers import assign,vote,finalize

@pytest.fixture
def env(client,database,settings):return setup(client,database,settings)


def refresh_submission(env):
    current=env['client'].get(env['path']).json()
    env['package']=advance(env['client'],env['root'],current,'refresh_submission')


class Factory:
    def __init__(self,alter=None,error=None,callback=None):self.alter=alter;self.error=error;self.callback=callback;self.calls=0;self.request=None
    def get(self,provider):return self
    def generate(self,key,request):
        self.calls+=1;self.request=request
        if self.callback:self.callback()
        if self.error:raise self.error
        base=MockProvider().generate('',request)
        if self.alter:
            d=json.loads(base.content);self.alter(d)
            return GenerationResult(json.dumps(d),base.model,'fixture-request','complete',base.input_tokens,base.output_tokens)
        return base


def test_packet_excludes_structured_economics_and_names(env):
    value=packet(env);payload=json.dumps(value['payload'])
    for key in ('budget_atoms','attributions','owner_id','current_share','salary','workspace_id','policy_id','user_id'):
        assert key not in payload
    assert env['owner']['user']['id'] not in payload
    assert env['owner']['user']['display_name'] not in payload
    assert value['capture']['aliases']


def test_packet_redacts_uploaded_text_and_marks_images_links(env):
    text=b'api_key = synthetic-secret\nTest reconnect restores the state.\nemail: user@example.test\nhttps://example.test/hidden'
    assert add(env['client'],env['path'],'file',file=file_input(text)).status_code==201
    assert add(env['client'],env['path'],'file',file=file_input(png_bytes(),'character.png','image/png')).status_code==201
    assert add(env['client'],env['path'],'link').status_code==201
    refresh_submission(env);value=packet(env);encoded=json.dumps(value['payload'])
    assert 'synthetic-secret' not in encoded and 'user@example.test' not in encoded and 'https://' not in encoded
    assert 'Test reconnect restores the state.' in encoded
    reasons={x['code'] for x in value['omissions']}
    assert {'nontext_artifact_not_inspected','external_link_not_fetched'}<=reasons
    assert value['capture']['redaction_counts']


def test_restricted_evidence_excluded_unless_explicit(env):
    assert add(env['client'],env['path'],metadata=metadata(visibility='restricted'),text='Unique confidential test observation').status_code==201
    refresh_submission(env)
    assert 'Unique confidential' not in json.dumps(packet(env)['payload'])
    assert 'Unique confidential' in json.dumps(packet(env,include_restricted=True)['payload'])


def test_excluded_filename_and_unselected_evidence_do_not_leak(env):
    response=add(env['client'],env['path'],'file',file=file_input(b'Unshared financial content','salary.txt'));assert response.status_code==201
    refresh_submission(env);value=packet(env)
    assert 'Unshared financial' not in json.dumps(value['payload'])
    assert any(o['code']=='excluded_path' for o in value['omissions'])
    selected=[response.json()['evidence_id']]
    value=packet(env,evidence_ids=selected)
    assert value['source_count']==0


def test_packet_source_bounds_are_visible(env):
    assert add(env['client'],env['path'],'file',file=file_input(('line '*250+'\n') .encode()+ b'valid observation\n'*200)).status_code==201
    refresh_submission(env);value=packet(env)
    assert len(json.dumps(value['payload'],ensure_ascii=True,separators=(',',':')).encode())<=24000
    assert any(o['code']=='source_text_bounded' for o in value['omissions'])

@pytest.mark.parametrize('role',['contributor','viewer'])
def test_unprivileged_cannot_access_assessment_routes(env,role):
    actor=env['actors'][role]['client'];p=packet(env);x=plan(env,p)
    for tail in ('/options?package_id='+p['package_id'],'/packets/'+p['id'],'/plans/'+x['id']):
        assert actor.get(env['assessments']+tail).status_code==403


def test_unknown_project_or_evidence_ids_fail_scoped(env):
    package=env['client'].get(env['path']).json()
    result=mutation(env['client'],env['assessments']+'/packets',{
        'request_id':str(uuid4()),'package_id':package['id'],'deliverable_id':package['revision']['document']['deliverables'][0]['id'],
        'profile_id':env['profile']['id'],'expected_package_version':package['version'],'evidence_ids':[str(uuid4())],
        'reason':'Unknown evidence must not enter a packet'})
    assert result.status_code==404
    assert env['client'].get(env['assessments']+'/packets/'+str(uuid4())).status_code==404


def test_data_grant_and_payer_approval_are_separate(env):
    x=plan(env,packet(env));path=env['assessments']+'/plans/'+x['id']
    assert env['client'].get(path+'/quote').status_code==409
    reviewer=env['actors']['reviewer']['client']
    assert grant(env,x,actor=reviewer).status_code==403
    assert grant(env,x,authorized_to_share=False).status_code==422
    assert grant(env,x).status_code==201
    assert reviewer.get(path+'/quote').status_code==404
    q=env['client'].get(path+'/quote').json()
    response=mutation(env['client'],path+'/run',{'request_id':str(uuid4()),'quote_hash':q['quote_hash'],
        'confirmed_reservation_microusd':q['specification']['reservation_microusd'],'payer_approved':False})
    assert response.status_code==422


def test_data_expiry_and_reviewed_hash_bounds(env):
    x=plan(env,packet(env))
    assert grant(env,x,valid_until=(now()+timedelta(days=2)).isoformat()).status_code==422
    assert grant(env,x,reviewed_plan_hash='0'*64).status_code==409
    assert grant(env,x,valid_until=(now()-timedelta(minutes=1)).isoformat()).status_code==422


def test_single_use_plan_and_idempotent_dispatch(env):
    x=plan(env,packet(env));assert grant(env,x).status_code==201;j,b=enqueue(env,x)
    path=env['assessments']+'/plans/'+x['id']+'/run'
    replay=mutation(env['client'],path,b);assert replay.status_code==202 and replay.json()['id']==j['id']
    b['request_id']=str(uuid4());assert mutation(env['client'],path,b).status_code==409
    with env['database'].session() as db:assert db.scalar(select(func.count()).select_from(AIJob).where(AIJob.kind=='assessment'))==1


def test_revoked_queued_plan_refunds_and_does_not_execute(env):
    x=plan(env,packet(env));assert grant(env,x).status_code==201;j,_=enqueue(env,x)
    response=mutation(env['client'],env['assessments']+'/plans/'+x['id']+'/revoke',{'reason':'Withdraw disclosure before the worker sends the packet'})
    assert response.status_code==200;assert response.json()['job']['status']=='cancelled'
    assert claim(env['database'],env['settings'],UUID(j['id'])) is None
    assert grant(env,x).status_code==409


def test_new_evidence_marks_packet_stale_before_send(env):
    p=packet(env);x=plan(env,p);assert grant(env,x).status_code==201;j,_=enqueue(env,x)
    assert add(env['client'],env['path'],text='New testing observations require a new explicit submission.').status_code==201
    assert env['client'].get(env['assessments']+'/packets/'+p['id']).json()['stale'] is True
    assert claim(env['database'],env['settings'],UUID(j['id'])) is None
    assert env['client'].get(env['assessments']+'/plans/'+x['id']).json()['job']['status']=='cancelled'


def test_review_assignment_does_not_stale_exact_evidence(env):
    p=packet(env);assign(env)
    assert env['client'].get(env['assessments']+'/packets/'+p['id']).json()['stale'] is False


def test_model_upgrade_invalidates_pending_official_run(env):
    x=plan(env,packet(env));assert grant(env,x).status_code==201;j,_=enqueue(env,x)
    response=mutation(env['client'],env['ai']+'/profiles',{'purpose':'evidence','connection_id':env['connection']['id'],'model_id':env['model']['id'],
        'title':'Explicit successor evaluation settings','data_policy_reference':'Same synthetic privacy configuration reviewed','reason':'Change the official evaluator prospectively'})
    assert response.status_code==201;new=response.json()
    response=mutation(env['client'],env['ai']+'/profiles/'+new['id']+'/approve',{'reviewed_hash':new['fingerprint'],
        'expected_active_profile_id':env['profile']['id'],'reason':'Explicitly switch the official configuration'})
    assert response.status_code==200
    assert claim(env['database'],env['settings'],UUID(j['id'])) is None


def test_legacy_pending_profile_never_becomes_evidence_authority(env):
    response=mutation(env['client'],env['ai']+'/profiles',{'connection_id':env['connection']['id'],'model_id':env['model']['id'],
        'title':'Legacy compatibility only','data_policy_reference':'Protocol-only test; not permission to send evidence','reason':'Legacy behavior remains deliberately compatible'})
    assert response.status_code==201;old=response.json()
    assert old['definition']['prompt_version'].endswith('pending-phase11')
    options=env['client'].get(env['assessments']+'/options',params={'package_id':env['package']['id']}).json()
    assert old['id'] not in {p['id'] for p in options['profiles']}


def test_advisory_result_not_replaced_as_official(env):
    x=plan(env,packet(env),mode='advisory');r=complete(env,x)
    reviewer=env['actors']['reviewer']['client']
    assert reviewer.get(env['assessments']+'/results/'+r['id']).status_code==404
    listing=reviewer.get(env['assessments']+'/plans',params={'package_id':x['package_id']}).json()
    assert x['id'] not in {v['id'] for v in listing['items']}
    assert env['client'].get(env['ai']+'/profiles').json()['active_profile_id']==env['profile']['id']

@pytest.mark.parametrize('mode',['bad_ref','command','secret','missing_criterion'])
def test_invalid_provider_output_has_no_preserved_prose_or_credit(env,mode):
    def alter(d):
        if mode=='bad_ref':d['findings'][0]['evidence_refs']=[{'source_id':'E999','start_line':1,'end_line':1}]
        elif mode=='command':d['issue_credit']={'units':100000}
        elif mode=='secret':d['summary']='Contact leaked-person@example.test to discuss this result.'
        else:d['findings'].pop()
    r=complete(env,plan(env,packet(env)),Factory(alter=alter))
    assert r['status']!='valid' and r['document'] is None
    with env['database'].session() as db:
        assert db.scalar(select(func.count()).select_from(CreditAward))==0
        assert db.scalar(select(func.count()).select_from(ContributionEvent))==0
    assert 'leaked-person' not in json.dumps(r)


def test_provider_revocation_during_request_discards_output_but_retains_usage(env):
    x=plan(env,packet(env));path=env['assessments']+'/plans/'+x['id']
    factory=Factory(callback=lambda:mutation(env['client'],path+'/revoke',{'reason':'Withdraw permission while the synthetic request is in flight'}))
    r=complete(env,x,factory)
    assert r['status']=='authorization_changed' and r['document'] is None
    assert env['client'].get(path).json()['job']['accounting_state']=='estimated'


def test_ambiguous_generation_is_not_automatically_retried(env):
    x=plan(env,packet(env));assert grant(env,x).status_code==201;j,_=enqueue(env,x)
    factory=Factory(error=ProviderError('timeout',ambiguous=True))
    item=claim(env['database'],env['settings'],UUID(j['id']));assert item
    execute(env['database'],env['settings'],factory,env['store'],item)
    maintain(env['database'],env['settings']);assert claim(env['database'],env['settings'],UUID(j['id'])) is None
    detail=env['client'].get(env['assessments']+'/plans/'+x['id']).json()
    assert factory.calls==1 and detail['job']['status']=='ambiguous' and detail['job']['accounting_state']=='uncertain'
    assert detail['result_id'] is None
    response=mutation(env['client'],env['ai']+'/connections/'+env['connection']['id']+'/jobs/'+j['id']+'/reconcile',{
        'actual_microusd':0,'source_reference':'Synthetic request has no actual external invoice','reason':'Payer checked this simulated uncertain transaction'})
    assert response.status_code==200,response.text


def test_lost_dispatched_worker_retains_hold_no_retry(env):
    x=plan(env,packet(env));assert grant(env,x).status_code==201;j,_=enqueue(env,x)
    item=claim(env['database'],env['settings'],UUID(j['id']));assert item
    with env['database'].session() as db:
        job=db.get(AIJob,UUID(j['id']));job.lease_until=now()-timedelta(seconds=1);db.commit()
    maintain(env['database'],env['settings'])
    assert claim(env['database'],env['settings'],UUID(j['id'])) is None
    assert env['client'].get(env['assessments']+'/plans/'+x['id']).json()['job']['status']=='ambiguous'


def test_generic_job_views_do_not_contain_excerpts_or_ai_explanations(env):
    r=complete(env,plan(env,packet(env)))
    jobs=env['client'].get(env['ai']+'/connections/'+env['connection']['id']+'/jobs').json()
    serialized=json.dumps(jobs)
    assert r['document']['summary'] not in serialized
    assert r['packet']['payload']['sources'][0]['lines'][0] not in serialized
    assert 'untrusted_evidence_packet' not in serialized

@pytest.mark.parametrize('action',['accept','modify','reject','request_evidence'])
def test_feedback_is_independent_commentary_not_award(env,action):
    p=packet(env);review=assign(env);r=complete(env,plan(env,p));reviewer=env['actors']['reviewer']['client']
    body={'request_id':str(uuid4()),'review_id':review['id'],'reviewed_result_hash':r['content_hash'],'criterion_id':'C1',
        'action':action,'reason':'Independently inspected the original statement against the criterion.',
        'replacement_text':'This observation needs the original integration test result.' if action=='modify' else None,
        'original_evidence_reviewed':True}
    path=env['assessments']+'/results/'+r['id']+'/feedback'
    assert mutation(env['client'],path,body).status_code==403
    response=mutation(reviewer,path,body);assert response.status_code==201,response.text
    assert mutation(reviewer,path,body).json()['id']==response.json()['id']
    with env['database'].session() as db:assert db.scalar(select(func.count()).select_from(CreditAward))==0
    assert env['client'].get(env['assessments']+'/results/'+r['id']).json()['document']==r['document']
    review=vote(env,review);finalize(env,review)
    assert env['client'].get(env['assessments']+'/results/'+r['id']).json()['packet']['stale'] is True
    with env['database'].session() as db:assert db.scalar(select(func.count()).select_from(CreditAward))==1


def test_rerun_cannot_be_hidden_by_preparing_another_packet(env):
    one=packet(env);first=plan(env,one);two=packet(env)
    assert one['prompt_hash']==two['prompt_hash']
    body={'request_id':str(uuid4()),'packet_id':two['id'],'reviewed_packet_hash':two['content_hash'],
        'mode':'official','reason':'Reattempt with identical inputs still needs a visible predecessor'}
    response=mutation(env['client'],env['assessments']+'/plans',body);assert response.status_code==409
    body['prior_plan_id']=first['id']
    response=mutation(env['client'],env['assessments']+'/plans',body);assert response.status_code==201,response.text
    assert response.json()['prior_plan_id']==first['id']


def test_result_remains_unchanged_after_new_evidence_and_rerun(env):
    p=packet(env);x=plan(env,p);r=complete(env,x)
    assert add(env['client'],env['path'],text='New independent reproduction report with actual steps.').status_code==201
    refresh_submission(env);p2=packet(env);assert p2['content_hash']!=p['content_hash']
    r2=complete(env,plan(env,p2,prior_plan_id=x['id']))
    before=env['client'].get(env['assessments']+'/results/'+r['id']).json()
    assert before['document']==r['document'] and before['content_hash']==r['content_hash'] and before['packet']['stale']
    assert r2['id']!=r['id'] and not r2['packet']['stale']


def test_lost_reviewer_or_payer_permission_stops_queued_generation(env):
    reviewer=env['actors']['reviewer']['client'];p=packet(env)
    response=mutation(reviewer,env['assessments']+'/plans',{'request_id':str(uuid4()),'packet_id':p['id'],
        'reviewed_packet_hash':p['content_hash'],'mode':'official','reason':'Reviewer requests official-profile evaluation'})
    assert response.status_code==201;x=response.json();assert grant(env,x).status_code==201;j,_=enqueue(env,x)
    with env['database'].session() as db:
        member=db.get(ProjectMembership,(UUID(env['owner']['workspace']['id']),UUID(env['owner']['project']['id']),UUID(env['actors']['reviewer']['id'])))
        member.status='suspended';member.version+=1;db.commit()
    assert claim(env['database'],env['settings'],UUID(j['id'])) is None
    assert reviewer.get(env['assessments']+'/plans/'+x['id']).status_code==404


def test_mocked_refusal_truncation_and_unexpected_response_never_become_findings(env):
    for finish in ('refused','truncated','unexpected'):
        prior=env['client'].get(env['assessments']+'/plans',params={'package_id':env['package']['id']}).json()['items']
        x=plan(env,packet(env),prior_plan_id=prior[0]['id'] if prior else None)
        class Refusing:
            def get(self,provider):return self
            def generate(self,key,request):return GenerationResult('sensitive invalid raw response',request.model,'fixture',finish,3,2)
        r=complete(env,x,Refusing());assert r['status']==finish and r['document'] is None
        assert 'sensitive invalid raw response' not in json.dumps(r)


def test_private_advisory_lineage_does_not_disclose_or_block_peer_runs(env):
    p=packet(env);reviewer=env['actors']['reviewer']['client']
    def create(actor,prior=None):
        return mutation(actor,env['assessments']+'/plans',{'request_id':str(uuid4()),'packet_id':p['id'],
            'reviewed_packet_hash':p['content_hash'],'mode':'advisory','prior_plan_id':prior,'reason':'Separate private advisory comparison for this requester'})
    first=create(reviewer);assert first.status_code==201
    second=create(env['client']);assert second.status_code==201
    assert reviewer.get(env['assessments']+'/plans/'+second.json()['id']).status_code==404
    assert create(reviewer,second.json()['id']).status_code==409
    successor=create(reviewer,first.json()['id']);assert successor.status_code==201
    own=env['client'].get(env['assessments']+'/plans',params={'package_id':p['package_id'],'mode':'advisory','mine':True}).json()['items']
    assert [v['id'] for v in own]==[second.json()['id']]
