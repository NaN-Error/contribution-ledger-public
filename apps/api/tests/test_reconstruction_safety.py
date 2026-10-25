from uuid import UUID,uuid4
import pytest
from sqlalchemy import select,text,func
from sqlalchemy.exc import DBAPIError
from alembic import command as alembic_command
from app.db.migration import migration_config
from app.contributions.reconstruction.models import ReconstructionBatch,ReconstructionEvent,ReconstructionMissingClaim
from tests.auth_helpers import mutation
from tests.phase12_helpers import environment,command,call,refresh,approve,manual,promote,accept_package,allocate_for,imported
from tests.phase4_helpers import advance


def test_idempotency_reuse_across_commands_is_a_conflict(client,database,settings):
    env=environment(client,database,settings);request=command(env['batch'],document={'title':'Reviewed art','category':'art','summary':'A complete historical outcome description'})
    call(env,'/candidates',request,expected=201)
    result=mutation(client,env['base']+'/missing-claims',{'request_id':request['request_id'],'title':'Different action','category':'art','description':'This cannot reuse a candidate command identity.'})
    assert result.status_code==409,result.text


def test_repeated_batch_create_preserves_one_scope(client,database,settings):
    env=environment(client,database,settings)
    again=mutation(client,env['root']+'/reconstruction',env['batch_create_body']);assert again.status_code==201
    assert again.json()['id']==env['batch']['id']
    changed={**env['batch_create_body'],'title':'Cannot replace history'}
    assert mutation(client,env['root']+'/reconstruction',changed).status_code==409


def test_missing_work_disposition_can_be_corrected_with_prior_decision_history(client,database,settings):
    env=environment(client,database,settings);candidate=manual(env)
    claim=call(env,'/missing-claims',{'request_id':str(uuid4()),'title':'Unrecorded QA work','category':'qa','description':'A documented testing contribution absent from source control.'},expected=201)
    cid=claim['result']['claim_id']
    call(env,'/resolve-claim',command(env['batch'],claim_id=cid,disposition='declined',candidate_id=None))
    call(env,'/resolve-claim',command(env['batch'],claim_id=cid,disposition='included',candidate_id=candidate['id']))
    history=client.get(env['base']+'/history').json()['items']
    assert history[-1]['record']['details']['previous']['state']=='declined'
    assert env['batch']['my_claims_or_review_queue'][0]['document']['title']=='Unrecorded QA work'


def test_cancelled_unaccepted_link_can_be_rejected_not_rebound(client,database,settings):
    env=environment(client,database,settings);approve(env);candidate=manual(env);package=promote(env,candidate)
    advance(client,env['root'],package,'cancel');refresh(env)
    call(env,'/candidates/'+candidate['id']+'/disposition',command(env['batch'],disposition='reject'))
    assert mutation(client,env['base']+'/candidates/'+candidate['id']+'/disposition',command(env['batch'],disposition='restore')).status_code==409


def test_accepted_work_cannot_be_discarded_through_candidate_disposition(client,database,settings):
    env=environment(client,database,settings);approve(env);candidate=manual(env);accept_package(env,promote(env,candidate))
    result=mutation(client,env['base']+'/candidates/'+candidate['id']+'/disposition',command(env['batch'],disposition='reject'))
    assert result.status_code==409


def test_reserved_allocations_are_not_offered_as_prospective_work(client,database,settings):
    env=environment(client,database,settings);approve(env);a=allocate_for(env,manual(env))
    assert a['id'] not in {x['id'] for x in client.get(env['root']+'/work-packages/options').json()['allocations']}


def test_opening_review_becomes_stale_when_another_claim_arrives(client,database,settings):
    env=environment(client,database,settings);approve(env);accept_package(env,promote(env,manual(env)))
    preview=client.get(env['base']+'/opening-preview').json();body=command(env['batch'],reviewed=True,reviewed_hash=preview['review_hash'])
    call(env,'/missing-claims',{'request_id':str(uuid4()),'title':'Additional music','category':'art','description':'A composer supplied work that this batch did not include.'},expected=201)
    assert mutation(client,env['base']+'/freeze',body).status_code==409


def test_frozen_history_and_definition_reject_ordinary_sql_mutation(client,database,settings):
    env=environment(client,database,settings);approve(env);accept_package(env,promote(env,manual(env)))
    preview=client.get(env['base']+'/opening-preview').json();call(env,'/freeze',command(env['batch'],reviewed=True,reviewed_hash=preview['review_hash']))
    for sql in ['DELETE FROM reconstruction_batches','DELETE FROM opening_balance_snapshots',
        "UPDATE opening_balance_snapshots SET record='{}'","UPDATE reconstruction_batches SET version=version+1",'DELETE FROM reconstruction_events']:
        with pytest.raises(DBAPIError),database.engine.begin() as db:db.execute(text(sql))


def test_nonempty_downgrade_refused_without_changing_previous_records(client,database,settings):
    env=environment(client,database,settings)
    with pytest.raises(RuntimeError,match='history exists'),database.engine.begin() as connection:
        config=migration_config();config.attributes['connection']=connection;alembic_command.downgrade(config,'0011_ai_evidence_review')
    assert client.get(env['base']).status_code==200


def test_wrong_project_and_policy_filters_do_not_disclose_scope(client,database,settings):
    env=environment(client,database,settings);foreign=env['root'].rsplit('/',1)[0]+'/'+str(uuid4())
    assert client.get(foreign+'/reconstruction/'+env['batch']['id']).status_code==404
    assert client.get(env['root']+'/reports/overview',params={'policy_id':str(uuid4())}).status_code==404
    assert client.get(env['root']+'/reports/overview',params={'category':'salary'}).status_code==422


def test_viewer_and_anonymous_cannot_submit_missing_work(client,database,settings):
    env=environment(client,database,settings);body={'request_id':str(uuid4()),'title':'Claimed work','category':'art','description':'This mutation needs a participating project member.'}
    viewer=env['actors']['viewer']['client'];assert mutation(viewer,env['base']+'/missing-claims',body).status_code==403
    client.cookies.clear();assert client.get(env['base']).status_code==401


def test_linked_package_shows_retrospective_origin_without_backdating_acceptance(client,database,settings):
    env=environment(client,database,settings);approve(env);package=promote(env,manual(env))
    assert package['origin']=='retrospective' and package['reconstruction_batch_id']==env['batch']['id']
    assert client.get(env['path']).json()['origin']=='prospective'
