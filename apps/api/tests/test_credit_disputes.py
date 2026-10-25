from uuid import UUID,uuid4
import pytest
from sqlalchemy import select,text
from sqlalchemy.exc import DBAPIError
from tests.phase6_helpers import (environment,award,open_dispute,resolver,correction,vote,finalize,final_body)
from tests.auth_helpers import mutation

@pytest.mark.parametrize('conflict',['owner','reviewer','viewer','contributor'])
def test_resolver_must_be_independent_and_have_review_access(client,database,settings,conflict):
    e=environment(client,database,settings);case=open_dispute(e,award(e))
    uid=e['owner']['user']['id'] if conflict=='owner' else e['actors'][conflict]['id']
    response=mutation(client,e['root']+'/disputes/'+case['id']+'/assignments',{'request_id':str(uuid4()),
        'reviewed_context_hash':case['context_hash'],'resolver_id':uid,'reason':'Choose a conflict-free resolver for this dispute'})
    assert response.status_code==403,response.text


def test_one_open_dispute_per_award_and_idempotent_open(client,database,settings):
    e=environment(client,database,settings);final=award(e)
    body={'request_id':str(uuid4()),'award_id':final['finalized_record_id'],'reason':'A specific attribution concern needs independent review.'}
    first=mutation(client,e['root']+'/disputes',body);assert first.status_code==201,first.text
    replay=mutation(client,e['root']+'/disputes',body);assert replay.status_code==201 and replay.json()['id']==first.json()['id']
    body['request_id']=str(uuid4());assert mutation(client,e['root']+'/disputes',body).status_code==409


def test_uphold_preserves_all_events_and_resolves_blocker(client,database,settings):
    e=environment(client,database,settings);final=award(e);case=resolver(e,open_dispute(e,final))
    p=correction(e,case,disposition='uphold');finalize(e,vote(e,p,who='resolver'),who='resolver')
    current=client.get(e['root']+'/contributions/awards/'+final['finalized_record_id']).json()
    assert len(current['events'])==1 and current['current_attributions'][0]['atoms']==100000
    assert client.get(e['root']+'/disputes/'+case['id']).json()['state']=='resolved'
    assert not client.get(e['root']+'/contributions').json()['groups'][0]['close_blocked']

@pytest.mark.parametrize('case_name',['too_large','too_small','negative','float','foreign_person','duplicate','conflicted_recipient'])
def test_corrections_cannot_create_money_or_negative_credit(client,database,settings,case_name):
    e=environment(client,database,settings);case=resolver(e,open_dispute(e,award(e)))
    entries=[{'user_id':e['owner']['user']['id'],'role':'implementation','atoms':60000},
        {'user_id':e['actors']['contributor']['id'],'role':'testing','atoms':40000}]
    if case_name=='too_large':entries[0]['atoms']=60001
    elif case_name=='too_small':entries[0]['atoms']=59999
    elif case_name=='negative':entries[0]['atoms']=-1;entries[1]['atoms']=100001
    elif case_name=='float':entries[0]['atoms']=60000.0
    elif case_name=='foreign_person':entries[1]['user_id']=str(uuid4())
    elif case_name=='duplicate':entries[1].update(user_id=entries[0]['user_id'],role=entries[0]['role'])
    elif case_name=='conflicted_recipient':entries[1]['user_id']=e['actors']['resolver']['id']
    response=mutation(e['actors']['resolver']['client'],e['root']+'/disputes/'+case['id']+'/proposals',{
        'request_id':str(uuid4()),'reviewed_context_hash':case['context_hash'],'disposition':'reallocate',
        'attributions':entries,'reviewer_ids':[e['actors']['resolver']['id']],'reason':'Propose a reviewed exact-budget allocation correction'})
    assert response.status_code in (403,409,422),response.text
    assert client.get(e['root']+'/contributions').json()['total_issued_atoms']==100000


def test_new_note_stales_resolution_votes(client,database,settings):
    e=environment(client,database,settings);case=resolver(e,open_dispute(e,award(e)));p=vote(e,correction(e,case),who='resolver')
    response=mutation(client,e['root']+'/disputes/'+case['id']+'/notes',{'request_id':str(uuid4()),
        'text':'Additional context identifies another original design contribution.', 'source_url':'https://example.test/design-notes'})
    assert response.status_code==201,response.text
    response=mutation(e['actors']['resolver']['client'],e['root']+'/reviews/'+p['id']+'/finalize',final_body(p))
    assert response.status_code==409,response.text
    assert client.get(e['root']+'/reviews/'+p['id']).json()['state']=='stale'


def test_resolver_reassignment_invalidates_old_proposal(client,database,settings):
    e=environment(client,database,settings);case=resolver(e,open_dispute(e,award(e)));p=correction(e,case)
    response=mutation(client,e['root']+'/disputes/'+case['id']+'/assignments',{'request_id':str(uuid4()),
        'reviewed_context_hash':case['context_hash'],'resolver_id':e['actors']['reviewer2']['id'],
        'reason':'Reassign to another independent reviewer because availability changed'})
    assert response.status_code==200,response.text
    assert client.get(e['root']+'/reviews/'+p['id']).json()['state']=='stale'


def test_reallocation_finalization_is_idempotent(client,database,settings):
    e=environment(client,database,settings);first=award(e);case=resolver(e,open_dispute(e,first));p=vote(e,correction(e,case),who='resolver');body=final_body(p)
    one=finalize(e,p,who='resolver',body=body);two=finalize(e,p,who='resolver',body=body)
    assert one['finalized_record_id']==two['finalized_record_id']
    rows=client.get(e['root']+'/contributions/awards/'+first['finalized_record_id']).json()['events']
    assert len(rows)==3 and sum(r['delta_atoms'] for r in rows if r['kind']=='adjustment')==0


def test_closed_dispute_rejects_notes_but_can_be_appealed_as_new_case(client,database,settings):
    e=environment(client,database,settings);first=award(e);case=resolver(e,open_dispute(e,first))
    finalize(e,vote(e,correction(e,case,disposition='uphold'),who='resolver'),who='resolver')
    result=mutation(client,e['root']+'/disputes/'+case['id']+'/notes',{'request_id':str(uuid4()),'text':'This new information requires a new auditable case.'})
    assert result.status_code==409,result.text
    second=open_dispute(e,first);assert second['id']!=case['id']


def test_notes_and_resolutions_are_immutable(client,database,settings):
    e=environment(client,database,settings);case=resolver(e,open_dispute(e,award(e)))
    result=mutation(client,e['root']+'/disputes/'+case['id']+'/notes',{'request_id':str(uuid4()),'text':'An immutable additional attribution claim was provided.'});assert result.status_code==201,result.text
    case=result.json();finalize(e,vote(e,correction(e,case,disposition='uphold'),who='resolver'),who='resolver')
    for table in ['credit_disputes','dispute_assignments','dispute_notes','dispute_resolutions']:
        with pytest.raises(DBAPIError),database.engine.begin() as conn:conn.execute(text(f'DELETE FROM {table}'))


def test_untrusted_note_url_is_not_accepted(client,database,settings):
    e=environment(client,database,settings);case=open_dispute(e,award(e))
    for url in ['javascript:alert(1)','http://example.test','https://user:pass@example.test/file','file:///etc/passwd']:
        response=mutation(client,e['root']+'/disputes/'+case['id']+'/notes',{'request_id':str(uuid4()),'text':'A meaningful synthetic supporting reference.','source_url':url})
        assert response.status_code==422,response.text


def test_resolution_requires_original_two_person_quorum(client,database,settings):
    from tests.phase6_helpers import assign
    e=environment(client,database,settings,minimum=2)
    r=assign(e,reviewers=[e['actors']['reviewer']['id'],e['actors']['reviewer2']['id']])
    r=vote(e,r);r=vote(e,r,who='reviewer2');first=finalize(e,r)
    case=resolver(e,open_dispute(e,first))
    body={'request_id':str(uuid4()),'reviewed_context_hash':case['context_hash'],'disposition':'uphold',
        'attributions':[],'reviewer_ids':[e['actors']['resolver']['id'],e['actors']['reviewer3']['id']],
        'reason':'Two independent people review this correction under the original policy.'}
    response=mutation(e['actors']['resolver']['client'],e['root']+'/disputes/'+case['id']+'/proposals',body)
    assert response.status_code==201,response.text
    p=vote(e,response.json(),who='resolver')
    denied=mutation(e['actors']['resolver']['client'],e['root']+'/reviews/'+p['id']+'/finalize',final_body(p))
    assert denied.status_code==409,denied.text
    p=vote(e,p,who='reviewer3')
    denied=mutation(e['actors']['reviewer3']['client'],e['root']+'/reviews/'+p['id']+'/finalize',final_body(p))
    assert denied.status_code==403,denied.text
    assert finalize(e,p,who='resolver')['state']=='finalized'


def test_successor_policy_never_rewrites_original_award_quorum(client,database,settings):
    from tests.phase3_helpers import policy_body,approve,acknowledge
    e=environment(client,database,settings);first=award(e)
    body=policy_body(client,e['root'],version=1);body['rules']['review']['minimum_independent_reviewers']=3
    response=mutation(client,e['root']+'/policies',body);assert response.status_code==201,response.text
    policy=response.json();assert approve(client,e['root'],policy).status_code==200
    assert acknowledge(client,e['root'],policy).status_code==200
    for name,actor in e['actors'].items():
        if name!='viewer':assert acknowledge(actor['client'],e['root'],policy).status_code==200
    case=resolver(e,open_dispute(e,first));assert case['minimum_reviewers']==1
    proposal=correction(e,case,disposition='uphold')
    assert proposal['minimum_reviewers']==1 and proposal['target']['policy_id']==e['policy']['id']
    assert finalize(e,vote(e,proposal,who='resolver'),who='resolver')['state']=='finalized'


def test_later_appeal_excludes_prior_resolution_reviewers(client,database,settings):
    e=environment(client,database,settings);first=award(e);case=resolver(e,open_dispute(e,first))
    finalize(e,vote(e,correction(e,case,disposition='uphold'),who='resolver'),who='resolver')
    new=open_dispute(e,first)
    assert e['actors']['resolver']['id'] not in {p['user_id'] for p in new['resolver_candidates']}
    assert e['actors']['reviewer2']['id'] in {p['user_id'] for p in new['resolver_candidates']}
    response=mutation(client,e['root']+'/disputes/'+new['id']+'/assignments',{
        'request_id':str(uuid4()),'reviewed_context_hash':new['context_hash'],
        'resolver_id':e['actors']['resolver']['id'],'reason':'Cannot resolve an appeal of my own earlier resolution'})
    assert response.status_code==403,response.text
