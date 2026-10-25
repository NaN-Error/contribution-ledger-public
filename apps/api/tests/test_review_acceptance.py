from copy import deepcopy
from uuid import UUID,uuid4
import pytest
from sqlalchemy import select,func
from tests.phase6_helpers import (environment,assignment_body,assign,decision_body,vote,final_body,finalize,award)
from tests.auth_helpers import mutation
from tests.phase5_helpers import add,metadata,revise
from tests.phase4_helpers import advance
from app.projects.models import ProjectMembership,WorkspaceMembership
from app.reviews.models import ReviewRound,ReviewDecision
from app.ledger.models import CreditAward,ContributionEvent

@pytest.mark.parametrize('member',['owner','contributor','viewer'])
def test_conflicted_or_unqualified_reviewers_are_rejected(client,database,settings,member):
    e=environment(client,database,settings)
    uid=e['owner']['user']['id'] if member=='owner' else e['actors'][member]['id']
    body=assignment_body(e,reviewers=[uid]);r=mutation(client,e['root']+'/reviews',body)
    assert r.status_code==403,r.text
    assert client.get(e['root']+'/contributions').json()['total_issued_atoms']==0

@pytest.mark.parametrize('who',['owner','contributor','reviewer2','viewer'])
def test_only_assigned_independent_human_can_decide(client,database,settings,who):
    e=environment(client,database,settings);r=assign(e)
    browser=client if who=='owner' else e['actors'][who]['client']
    result=mutation(browser,e['root']+'/reviews/'+r['id']+'/decisions',decision_body(r))
    assert result.status_code==403,result.text

@pytest.mark.parametrize('case',['missing','duplicate','invented','no_reference','bad_reference','insufficient','false_declaration','wrong_hash'])
def test_findings_validate_exact_criteria_and_evidence(client,database,settings,case):
    e=environment(client,database,settings);r=assign(e);body=decision_body(r)
    expected=422
    if case=='missing':body['findings'].pop()
    elif case=='duplicate':body['findings'].append(body['findings'][0])
    elif case=='invented':body['findings'][0]['criterion_id']='invented'
    elif case=='no_reference':body['findings'][0]['evidence_refs']=[]
    elif case=='bad_reference':body['findings'][0]['evidence_refs']=['evidence:invented:1']
    elif case=='insufficient':body['findings'][0]['result']='insufficient'
    elif case=='false_declaration':body['independent']=False
    elif case=='wrong_hash':body['reviewed_target_hash']='0'*64;expected=409
    result=mutation(e['actors']['reviewer']['client'],e['root']+'/reviews/'+r['id']+'/decisions',body)
    assert result.status_code==expected,result.text
    with database.session() as db:assert db.scalar(select(func.count()).select_from(ReviewDecision))==0

@pytest.mark.parametrize('decision',['reject','request_evidence'])
def test_nonaccepting_findings_block_finalization(client,database,settings,decision):
    e=environment(client,database,settings);r=vote(e,assign(e),decision=decision)
    assert r['state']=='changes_requested'
    result=mutation(e['actors']['reviewer']['client'],e['root']+'/reviews/'+r['id']+'/finalize',final_body(r))
    assert result.status_code==409,result.text
    assert client.get(e['root']+'/contributions').json()['total_issued_atoms']==0

@pytest.mark.parametrize('minimum',[2,3])
def test_policy_quorum_cannot_be_shortened(client,database,settings,minimum):
    e=environment(client,database,settings,minimum=minimum)
    ids=[e['actors'][name]['id'] for name in ['reviewer','reviewer2','reviewer3'][:minimum]]
    invalid=assignment_body(e);res=mutation(client,e['root']+'/reviews',invalid);assert res.status_code==422,res.text
    r=assign(e,reviewers=ids);r=vote(e,r)
    res=mutation(e['actors']['reviewer']['client'],e['root']+'/reviews/'+r['id']+'/finalize',final_body(r));assert res.status_code==409,res.text
    for name in ['reviewer2','reviewer3'][:minimum-1]:r=vote(e,r,who=name)
    assert finalize(e,r)['state']=='finalized'


def test_assignment_vote_and_finalization_idempotency(client,database,settings):
    e=environment(client,database,settings);body=assignment_body(e)
    r=mutation(client,e['root']+'/reviews',body);assert r.status_code==201;r=r.json()
    repeat=mutation(client,e['root']+'/reviews',body);assert repeat.status_code==201 and repeat.json()['id']==r['id']
    bad=deepcopy(body);bad['reason']='Different command using the same request identifier'
    assert mutation(client,e['root']+'/reviews',bad).status_code==409
    vote_body=decision_body(r);r=vote(e,r,body=vote_body)
    repeat=mutation(e['actors']['reviewer']['client'],e['root']+'/reviews/'+r['id']+'/decisions',vote_body);assert repeat.status_code==200
    fresh=decision_body(r);assert mutation(e['actors']['reviewer']['client'],e['root']+'/reviews/'+r['id']+'/decisions',fresh).status_code==409
    f=final_body(r);final=finalize(e,r,body=f)
    repeated=finalize(e,r,body=f);assert repeated['finalized_record_id']==final['finalized_record_id']
    assert mutation(e['actors']['reviewer']['client'],e['root']+'/reviews/'+r['id']+'/finalize',final_body(r)).status_code==409
    with database.session() as db:
        assert db.scalar(select(func.count()).select_from(CreditAward))==1
        assert db.scalar(select(func.count()).select_from(ReviewDecision))==1
        assert db.scalar(select(func.count()).select_from(ReviewRound))==1


def test_latest_round_explicitly_supersedes_unfinished_votes(client,database,settings):
    e=environment(client,database,settings);old=vote(e,assign(e));new=assign(e)
    assert new['number']==2
    res=mutation(e['actors']['reviewer']['client'],e['root']+'/reviews/'+old['id']+'/finalize',final_body(old))
    assert res.status_code==409 and res.json()['error']['code']=='superseded_review',res.text
    assert client.get(e['root']+'/reviews/'+old['id']).json()['state']=='stale'
    assert finalize(e,vote(e,new))['state']=='finalized'


def test_evidence_change_requires_new_submission_and_round(client,database,settings):
    e=environment(client,database,settings);old=vote(e,assign(e))
    assert add(client,e['path'],text='A second piece of synthetic evidence changes the submitted packet.').status_code==201
    res=mutation(e['actors']['reviewer']['client'],e['root']+'/reviews/'+old['id']+'/finalize',final_body(old))
    assert res.status_code==409,res.text
    package=client.get(e['path']).json();advance(client,e['root'],package,'refresh_submission')
    assert finalize(e,vote(e,assign(e)))['state']=='finalized'
    assert client.get(e['root']+'/reviews/'+old['id']).json()['state']=='stale'


def test_new_participant_without_ack_blocks_acceptance(client,database,settings):
    e=environment(client,database,settings);r=vote(e,assign(e))
    with database.session() as db:
        row=db.get(ProjectMembership,(UUID(e['owner']['workspace']['id']),UUID(e['owner']['project']['id']),UUID(e['actors']['viewer']['id'])))
        row.role='contributor';db.commit()
    res=mutation(e['actors']['reviewer']['client'],e['root']+'/reviews/'+r['id']+'/finalize',final_body(r));assert res.status_code==409,res.text


def test_revoked_reviewer_cannot_finalize_previous_vote(client,database,settings):
    e=environment(client,database,settings);r=vote(e,assign(e))
    with database.session() as db:
        row=db.get(ProjectMembership,(UUID(e['owner']['workspace']['id']),UUID(e['owner']['project']['id']),UUID(e['actors']['reviewer']['id'])))
        row.status='suspended';db.commit()
    res=mutation(e['actors']['reviewer']['client'],e['root']+'/reviews/'+r['id']+'/finalize',final_body(r));assert res.status_code in (403,404),res.text
    assert client.get(e['root']+'/contributions').json()['total_issued_atoms']==0


def test_missing_sources_do_not_allow_supported_acceptance(client,database,settings):
    e=environment(client,database,settings,evidence=False);r=assign(e)
    assert r['target']['evidence_sources']==[]
    response=mutation(e['actors']['reviewer']['client'],e['root']+'/reviews/'+r['id']+'/decisions',decision_body(r))
    assert response.status_code==422,response.text
    assert vote(e,r,decision='request_evidence')['state']=='changes_requested'


def test_restricted_sources_not_leaked_through_review_views(client,database,settings):
    e=environment(client,database,settings,evidence=False)
    res=add(client,e['path'],metadata=metadata(title='Private synthetic reviewer-only source',visibility='restricted'))
    assert res.status_code==201,res.text
    advance(client,e['root'],client.get(e['path']).json(),'refresh_submission');r=assign(e)
    public=e['actors']['viewer']['client'].get(e['root']+'/reviews/'+r['id'])
    assert public.status_code==200
    assert 'Private synthetic reviewer-only source' not in public.text
    assert public.json()['target']['evidence_sources']==[{'restricted':True}]
    rv=e['actors']['reviewer']['client'].get(e['root']+'/reviews/'+r['id']).json()
    assert rv['target']['evidence_sources'][0]['title']=='Private synthetic reviewer-only source'


def test_nonreviewer_sees_decision_exists_not_private_findings(client,database,settings):
    e=environment(client,database,settings);r=vote(e,assign(e))
    res=e['actors']['contributor']['client'].get(e['root']+'/reviews/'+r['id']).json()
    assert res['decisions'][0]['decision']=='accept' and not res['decisions'][0]['findings']
    assert res['decisions'][0]['reason'] is None and not res['can_finalize']


def test_stale_decision_hash_cannot_finalize_after_quorum_changes(client,database,settings):
    e=environment(client,database,settings);r=assign(e);body=final_body(r);r=vote(e,r)
    res=mutation(e['actors']['reviewer']['client'],e['root']+'/reviews/'+r['id']+'/finalize',body)
    assert res.status_code==409,res.text


def test_mutating_review_requires_csrf(client,database,settings):
    e=environment(client,database,settings);r=assign(e)
    res=e['actors']['reviewer']['client'].post(e['root']+'/reviews/'+r['id']+'/decisions',json=decision_body(r))
    assert res.status_code==403,res.text
