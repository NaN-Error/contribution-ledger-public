from copy import deepcopy
from uuid import UUID, uuid4
from sqlalchemy import select,func,text,delete
from sqlalchemy.exc import IntegrityError
import pytest
from app.finance.simulator.models import SimulationScenario
from app.finance.simulator.service import verify_record
from app.core.errors import ApiError
from app.ledger.models import CreditAward,ContributionEvent,ContributionBalance
from app.ledger.service import reconcile
from app.projects.models import Project,WorkspaceMembership,ProjectMembership
from tests.auth_helpers import mutation,bootstrap
from tests.phase6_helpers import environment,award,open_dispute,resolver,correction,vote,finalize
from tests.phase7_helpers import input_for,preview,save_body,save
from tests.phase3_helpers import draft


def test_manual_end_to_end_with_partial_credit_and_saved_scenario(client,database,settings):
    env=environment(client,database,settings,partial=True)
    award(env)
    record=preview(env)
    assert record['payable'] is False
    assert record['result']['allocated_cents']==1000000
    assert record['result']['pools'][0]['denominator_atoms']==60000
    assert record['snapshot']['pending_planned_atoms']==40000
    assert record['snapshot']['source_award_count']==1
    assert record['snapshot']['source_event_count']==1
    assert len(record['snapshot']['ledger_revision'])==64
    stored=save(env,record)
    read=client.get(env['root']+'/simulator/scenarios/'+stored['id'])
    assert read.status_code==200
    assert read.json()['reproduced']
    assert read.json()['record']['result']==record['result']
    assert client.get(env['root']+'/contributions').json()['total_issued_atoms']==60000
    second=preview(env,input_for(env,2000000))
    assert second['result']['allocated_cents']==2000000
    assert second['snapshot']['ledger_revision']==record['snapshot']['ledger_revision']
    assert second['snapshot_hash']!=record['snapshot_hash']


def test_unsaved_preview_does_not_create_business_records(client,database,settings):
    env=environment(client,database,settings);award(env)
    with database.session() as db:
        counts=[db.scalar(select(func.count()).select_from(table)) for table in [CreditAward,ContributionEvent,SimulationScenario]]
    preview(env);preview(env,input_for(env,1))
    with database.session() as db:
        assert counts==[db.scalar(select(func.count()).select_from(table)) for table in [CreditAward,ContributionEvent,SimulationScenario]]


def test_empty_pool_never_pays_owner(client,database,settings):
    env=environment(client,database,settings)
    record=preview(env)
    assert record['result']['status']=='blocked'
    assert record['result']['people']==[]
    assert record['result']['unallocated_cents']==1000000
    assert record['snapshot']['pending_planned_atoms']==100000


def test_dispute_blocks_pool_without_debit_then_correction_reproduces(client,database,settings):
    env=environment(client,database,settings);final=award(env)
    original=save(env)
    case=open_dispute(env,final)
    blocked=preview(env)
    assert blocked['result']['unallocated_cents']==1000000
    assert 'unresolved_dispute' in blocked['result']['pools'][0]['blockers']
    assert blocked['snapshot']['ledger_revision']==original['record']['snapshot']['ledger_revision']
    assert blocked['snapshot_hash']!=original['record']['snapshot_hash']
    case=resolver(env,case);finalize(env,vote(env,correction(env,case),who='resolver'),who='resolver')
    current=preview(env)
    assert sorted(p['amount_cents'] for p in current['result']['people'])==[400000,600000]
    assert current['snapshot']['ledger_revision']!=original['record']['snapshot']['ledger_revision']
    historical=client.get(env['root']+'/simulator/scenarios/'+original['id']).json()
    assert historical['record']==original['record']
    assert historical['record']['result']['people'][0]['amount_cents']==1000000


def test_stale_preview_cannot_be_saved_after_credit_or_dispute(client,database,settings):
    env=environment(client,database,settings)
    before=preview(env);final=award(env)
    result=mutation(client,env['root']+'/simulator/scenarios',save_body(before))
    assert result.status_code==409
    now_record=preview(env);open_dispute(env,final)
    assert mutation(client,env['root']+'/simulator/scenarios',save_body(now_record)).status_code==409


def test_save_idempotency_and_actor_binding(client,database,settings):
    env=environment(client,database,settings);award(env)
    body=save_body(preview(env));path=env['root']+'/simulator/scenarios'
    first=mutation(client,path,body);second=mutation(client,path,body)
    assert first.status_code==second.status_code==201
    assert first.json()['id']==second.json()['id']
    assert mutation(env['actors']['reviewer']['client'],path,body).status_code==409
    body['title']='Different example title'
    assert mutation(client,path,body).status_code==409
    assert len(client.get(path).json()['items'])==1


def test_viewer_can_calculate_but_not_save(client,database,settings):
    env=environment(client,database,settings);award(env);viewer=env['actors']['viewer']['client']
    options=viewer.get(env['root']+'/simulator/options').json();assert not options['can_save']
    record=preview(env,client=viewer)
    assert mutation(viewer,env['root']+'/simulator/scenarios',save_body(record)).status_code==403
    own=save(env)
    assert viewer.get(env['root']+'/simulator/scenarios/'+own['id']).status_code==200


def test_removed_member_cannot_read_saved_or_new_scenarios(client,database,settings):
    env=environment(client,database,settings);award(env);stored=save(env)
    member=env['actors']['contributor']
    with database.session() as db:
        row=db.get(ProjectMembership,(UUID(env['owner']['workspace']['id']),UUID(env['owner']['project']['id']),UUID(member['id'])))
        row.status='suspended';db.commit()
    other=member['client']
    assert other.get(env['root']+'/simulator/scenarios/'+stored['id']).status_code==404
    assert other.get(env['root']+'/simulator/scenarios').status_code==404
    assert mutation(other,env['root']+'/simulator/preview',input_for(env)).status_code==404


def test_draft_alternative_never_rewrites_source_credit(client,database,settings):
    env=environment(client,database,settings);award(env)
    alternative=draft(client,env['root'],version=1,key=1)
    body=input_for(env);body['calculation_policy_id']=alternative['id']
    record=preview(env,body)
    assert record['snapshot']['calculation_policy']['state']=='draft'
    assert record['snapshot']['source_policy']['id']==env['policy']['id']
    assert record['result']['status']=='blocked'  # No ongoing credit for this source policy.
    release=next(p for p in record['result']['pools'] if p['key']=='release')
    assert release['denominator_atoms']==100000
    assert client.get(env['root']+'/contributions').json()['total_issued_atoms']==100000
    body['source_policy_id']=alternative['id']
    assert preview(env,body)['result']['people']==[]  # No cross-policy combination.


def test_balances_are_reconstructed_from_events_not_cache(client,database,settings):
    env=environment(client,database,settings);award(env)
    before=preview(env)
    with database.session() as db:
        db.execute(delete(ContributionBalance));db.commit()
    assert preview(env)['result']==before['result']
    with database.session() as db:
        project=db.get(Project,UUID(env['owner']['project']['id']))
        reconcile(db,project,repair=True);db.commit()
    after=preview(env)
    assert after['result']==before['result']
    assert after['snapshot']['ledger_revision']==before['snapshot']['ledger_revision']


def test_scenario_immutability_and_nonempty_downgrade(client,database,settings):
    from alembic import command
    from app.db.migration import migration_config
    env=environment(client,database,settings);save(env)
    for sql in ['UPDATE simulation_scenarios SET title=\'changed\'','DELETE FROM simulation_scenarios']:
        with pytest.raises(IntegrityError),database.engine.begin() as connection:connection.execute(text(sql))
    with pytest.raises(RuntimeError,match='Saved scenarios'),database.engine.begin() as connection:
        config=migration_config();config.attributes['connection']=connection;command.downgrade(config,'0006_human_credit')


def test_integrity_rejects_modified_archived_result(client,database,settings):
    env=environment(client,database,settings);award(env)
    record=deepcopy(preview(env));record['result']['people'][0]['amount_cents']=1
    with pytest.raises(ApiError,match='integrity'):verify_record(record)


@pytest.mark.parametrize('field,value', [('amount_cents',True),('amount_cents',-1),('amount_cents','100'),
    ('amount_cents',1.5),('amount_cents',1000000000001),('month','2026-9'),('month','1999-01')])
def test_rejects_invalid_requests(client,database,settings,field,value):
    env=environment(client,database,settings);body=input_for(env);body[field]=value
    assert mutation(client,env['root']+'/simulator/preview',body).status_code==422


def test_cross_project_ids_and_anonymous_access_fail(client,database,settings):
    env=environment(client,database,settings);record=save(env)
    from app.main import create_app
    from fastapi.testclient import TestClient
    stranger=TestClient(create_app(settings,database))
    assert stranger.get(env['root']+'/simulator/options').status_code==401
    # Owner creates another workspace, which still must not expose the first project's IDs.
    workspace=mutation(client,'/api/v1/workspaces',{'name':'Other scoped workspace'}).json()
    project=mutation(client,f"/api/v1/workspaces/{workspace['id']}/projects",{'name':'Other project',
        'description':'Synthetic scoped test','timezone':'UTC','currency':'USD'}).json()
    otherroot=f"/api/v1/workspaces/{workspace['id']}/projects/{project['id']}"
    assert client.get(otherroot+'/simulator/scenarios/'+record['id']).status_code==404
    assert mutation(client,otherroot+'/simulator/preview',input_for(env)).status_code==404


def test_preview_requires_csrf(client,database,settings):
    env=environment(client,database,settings)
    result=client.post(env['root']+'/simulator/preview',json=input_for(env),headers={'Origin':'http://testserver'})
    assert result.status_code==403



def test_transaction_failure_does_not_leave_scenario_or_audit(client,database,settings):
    from app.finance.simulator.service import save_scenario
    from app.finance.simulator.schemas import SaveScenario
    from app.projects.authorization import project_access
    from app.auth.models import User
    from app.projects.models import AuditEvent
    env=environment(client,database,settings);record=preview(env)
    with database.session() as db:before=db.scalar(select(func.count()).select_from(AuditEvent))
    with pytest.raises(RuntimeError),database.session() as db:
        project,role=project_access(db,UUID(env['owner']['workspace']['id']),UUID(env['owner']['project']['id']),UUID(env['owner']['user']['id']),lock=True)
        actor=db.get(User,UUID(env['owner']['user']['id']))
        save_scenario(db,project,actor,role,SaveScenario.model_validate(save_body(record)))
        raise RuntimeError('synthetic transaction failure before commit')
    with database.session() as db:
        assert db.scalar(select(func.count()).select_from(SimulationScenario))==0
        assert db.scalar(select(func.count()).select_from(AuditEvent))==before


def test_archived_credit_survives_contributor_departure(client,database,settings):
    env=environment(client,database,settings);final=award(env)
    case=resolver(env,open_dispute(env,final));finalize(env,vote(env,correction(env,case),who='resolver'),who='resolver')
    before=preview(env)
    with database.session() as db:
        member=db.get(ProjectMembership,(UUID(env['owner']['workspace']['id']),UUID(env['owner']['project']['id']),UUID(env['actors']['contributor']['id'])))
        member.status='suspended';db.commit()
    after=preview(env)
    assert after['result']==before['result']
    assert after['snapshot']['ledger_revision']==before['snapshot']['ledger_revision']


def test_read_has_no_store_and_no_payment_mutation_routes(client,database,settings):
    env=environment(client,database,settings);saved=save(env)
    path=env['root']+'/simulator/scenarios/'+saved['id']
    response=client.get(path);assert response.headers['cache-control']=='no-store'
    for method in ['PATCH','DELETE']:
        assert mutation(client,path,{},method=method).status_code==405
    assert mutation(client,env['root']+'/simulator/pay',{}).status_code==404
