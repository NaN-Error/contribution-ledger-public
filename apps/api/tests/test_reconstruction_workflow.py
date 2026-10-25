from copy import deepcopy
from uuid import UUID,uuid4
import pytest
from sqlalchemy import select,func
from tests.auth_helpers import mutation
from tests.phase12_helpers import environment,command,call,approve,manual,imported,promote,accept_package,refresh,promotion_body,allocate_for
from tests.phase6_helpers import open_dispute,award
from app.contributions.reconstruction.models import ReconstructionCandidate,ReconstructionSourceClaim,OpeningBalanceSnapshot
from app.ledger.models import CreditAward


def test_manual_opening_uses_existing_acceptance_and_snapshot_only(client,database,settings):
    env=environment(client,database,settings);approve(env);candidate=manual(env);package=promote(env,candidate)
    assert package['state']=='draft' and package['issued_atoms']==0
    with database.session() as db:assert db.scalar(select(func.count()).select_from(CreditAward))==0
    changed,final=accept_package(env,package)
    preview=client.get(env['base']+'/opening-preview').json()
    assert not preview['record']['blockers'],preview
    assert preview['record']['batch_issued_atoms']==100000
    body=command(env['batch'],reviewed=True,reviewed_hash=preview['review_hash'])
    result=call(env,'/freeze',body)
    assert result['batch']['state']=='frozen'
    again=call(env,'/freeze',body)
    assert again['result']==result['result']
    with database.session() as db:
        assert db.scalar(select(func.count()).select_from(CreditAward))==1
        assert db.scalar(select(func.count()).select_from(OpeningBalanceSnapshot))==1
    saved=result['batch']['frozen_snapshot']
    assert client.get(env['base']).json()['frozen_snapshot']==saved


def test_reimport_groups_do_not_duplicate_source_claims_or_issue_units(client,database,settings):
    env=environment(client,database,settings);job,result=imported(env)
    assert result['result']['source_count']>0 and result['result']['group_count']>0
    same=call(env,'/group-import',command(env['batch'],import_id=job['id']))
    assert same['result']['group_count']==same['result']['source_count']==0
    assert same['result']['already_claimed_count']==result['result']['source_count']
    with database.session() as db:
        assert db.scalar(select(func.count()).select_from(CreditAward))==0
        assert db.scalar(select(func.count()).select_from(ReconstructionSourceClaim))==result['result']['source_count']


def test_imported_attribution_requires_explicit_resolution_and_promotion_pins_sources(client,database,settings):
    env=environment(client,database,settings);approve(env);imported(env)
    candidate=next(c for c in env['batch']['candidates'] if c['identities'])
    allocation=allocate_for(env,candidate)
    bad=mutation(client,env['base']+'/promote',promotion_body(env,candidate,allocation));assert bad.status_code==409,bad.text
    doc={k:v for k,v in candidate['document'].items() if k!='provenance'}
    doc['unresolved_questions']=[]
    doc['identity_resolutions']=[{'external_key':x['external_key'],'disposition':'context_only','user_id':None,
        'reason':'Reviewed as contextual evidence rather than asserted recipient; final attribution requires independent acceptance.'} for x in candidate['identities']]
    result=call(env,'/candidates/'+candidate['id']+'/revisions',command(env['batch'],document=doc))
    candidate=next(c for c in env['batch']['candidates'] if c['id']==candidate['id'])
    body=promotion_body(env,candidate,allocation)
    result=call(env,'/promote',body,expected=201)
    assert len(result['result']['evidence_ids'])==len(candidate['sources'])
    assert call(env,'/promote',body,expected=201)['result']==result['result']
    assert client.get(env['root']+'/work-packages/'+result['result']['package_id']).json()['issued_atoms']==0


def test_missing_artist_claim_blocks_until_reviewed_and_remains_visible_to_author(client,database,settings):
    env=environment(client,database,settings);approve(env)
    person=env['actors']['contributor']['client']
    claim=call(env,'/missing-claims',{'request_id':str(uuid4()),'title':'Unrecorded character artwork','category':'art',
        'description':'Character concepts and texture work are missing from the imported repository.'},expected=201,client=person)
    # A contributor gets their claim, but never the unshared candidate/source collection.
    assert 'candidates' not in claim['batch']
    assert len(claim['batch']['my_claims_or_review_queue'])==1
    refresh(env)
    assert any('claim' in x for x in client.get(env['base']+'/opening-preview').json()['record']['blockers'])
    candidate=manual(env)
    call(env,'/resolve-claim',command(env['batch'],claim_id=claim['result']['claim_id'],disposition='included',candidate_id=candidate['id']))
    assert any('included claim' in x.lower() for x in client.get(env['base']+'/opening-preview').json()['record']['blockers'])
    package=promote(env,next(c for c in env['batch']['candidates'] if c['id']==candidate['id']))
    accept_package(env,package)
    assert not client.get(env['base']+'/opening-preview').json()['record']['blockers']


def test_rejected_candidate_history_and_restoration(client,database,settings):
    env=environment(client,database,settings);candidate=manual(env)
    call(env,'/candidates/'+candidate['id']+'/disposition',command(env['batch'],disposition='reject'))
    assert env['batch']['candidates'][0]['state']=='rejected'
    call(env,'/candidates/'+candidate['id']+'/disposition',command(env['batch'],disposition='restore'))
    assert env['batch']['candidates'][0]['state']=='draft'
    history=client.get(env['base']+'/history').json()['items']
    assert len(history)==4
    assert all(history[i]['previous_hash']==history[i-1]['record_hash'] for i in range(1,len(history)))


def test_merge_split_preserve_primary_sources_and_no_budgets(client,database,settings):
    env=environment(client,database,settings);imported(env)
    rows=env['batch']['candidates'];assert len(rows)>=2
    ids=[r['id'] for r in rows];sources={s['id'] for r in rows for s in r['sources']}
    result=call(env,'/regroup',command(env['batch'],candidate_ids=ids,title='Reviewed combined networking outcome'))
    merged=next(c for c in env['batch']['candidates'] if c['id']==result['result']['candidate_id'])
    assert {s['id'] for s in merged['sources']}==sources
    result=call(env,'/regroup',command(env['batch'],candidate_ids=[merged['id']],split_source_ids=[merged['sources'][0]['id']],title='Separate reviewed historical outcome'))
    active=[c for c in env['batch']['candidates'] if c['state']=='draft']
    assert len(active)==2 and {s['id'] for c in active for s in c['sources']}==sources
    assert sum(len(c['sources']) for c in active)==len(sources)


def test_unresolved_dispute_blocks_opening_and_frozen_snapshot_does_not_reissue(client,database,settings):
    env=environment(client,database,settings);approve(env);package=promote(env,manual(env));changed,final=accept_package(env,package)
    open_dispute(changed,final);refresh(env)
    preview=client.get(env['base']+'/opening-preview').json()
    assert any('dispute' in x for x in preview['record']['blockers'])
    response=mutation(client,env['base']+'/freeze',command(env['batch'],reviewed=True,reviewed_hash=preview['review_hash']))
    assert response.status_code==409,response.text


def test_person_filter_preserves_denominator_and_art_is_present(client,database,settings):
    env=environment(client,database,settings);award(env);approve(env);accept_package(env,promote(env,manual(env)))
    report=client.get(env['root']+'/reports/overview').json()
    assert report['groups'][0]['denominator_atoms']==200000
    assert report['groups'][0]['by_category']=={'code':100000,'art':100000}
    assert report['groups'][0]['by_origin']=={'prospective':100000,'retrospective':100000}
    filtered=client.get(env['root']+'/reports/overview',params={'person_id':env['actors']['contributor']['id']}).json()
    assert filtered['groups'][0]['denominator_atoms']==200000 and filtered['groups'][0]['people']==[]
    art=client.get(env['root']+'/reports/overview',params={'category':'art'}).json()
    assert art['groups'][0]['denominator_atoms']==100000 and art['filters']['category']=='art'
    assert 'category/origin' in art['denominator_label']


def test_reviewer_can_inspect_not_approve_scope_and_contributor_cannot_inspect_sources(client,database,settings):
    env=environment(client,database,settings)
    reviewer=env['actors']['reviewer']['client'];contributor=env['actors']['contributor']['client']
    assert reviewer.get(env['base']).json()['can_inspect'] is True
    assert 'candidates' not in contributor.get(env['base']).json()
    assert contributor.get(env['base']+'/history').status_code==403
    assert contributor.get(env['root']+'/reconstruction/options').status_code==403
    body=command(env['batch'],reviewed=True,reviewed_hash=env['batch']['scope_review_hash'])
    assert mutation(reviewer,env['base']+'/approve-scope',body).status_code==403
    assert contributor.get(env['root']+'/reports/overview').json()['activity'] is None


def test_stale_candidate_change_is_rejected(client,database,settings):
    env=environment(client,database,settings);candidate=manual(env)
    body=command(env['batch'],document={k:v for k,v in candidate['document'].items() if k!='provenance'})
    manual(env,title='Another independent outcome')
    assert mutation(client,env['base']+'/candidates/'+candidate['id']+'/revisions',body).status_code==409


def test_cannot_bypass_reserved_milestone_with_ordinary_package_route(client,database,settings):
    from tests.phase4_helpers import create,scope
    env=environment(client,database,settings);approve(env);candidate=manual(env);allocation=allocate_for(env,candidate)
    milestone=client.get(env['root']+'/milestones/'+env['batch']['milestone_id']).json()
    result=create(client,env['root'],env['owner'],milestone,allocation,custom=scope(env['owner']['user']['id'],allocation['atoms']))
    assert result.status_code==409,result.text


@pytest.mark.parametrize('field,value',[('start_at','2026-09-01T00:00:00'),('end_before','2099-01-01T00:00:00Z'),('end_before','2025-01-01T00:00:00Z')])
def test_invalid_historical_intervals(client,database,settings,field,value):
    env=environment(client,database,settings);body={**env['batch_create_body'],'request_id':str(uuid4()),field:value}
    result=mutation(client,env['root']+'/reconstruction',body);assert result.status_code==422,result.text
