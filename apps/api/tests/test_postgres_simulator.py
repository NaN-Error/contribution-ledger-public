"""Native scenario transactions and scope/history guards. Not simulated on SQLite."""
import pytest
from sqlalchemy import select,func,text
from sqlalchemy.exc import DBAPIError
from tests.test_postgres_accounts import pg_accounts,browser
from tests.test_postgres_planning import race_requests
from tests.phase6_helpers import environment,assign,vote,final_body,award
from tests.phase7_helpers import preview,save,save_body
from app.finance.simulator.models import SimulationScenario

pytestmark=pytest.mark.postgres


def test_native_duplicate_scenario_save_is_one_record(pg_accounts):
    settings,db=pg_accounts;client=browser(settings,db)
    try:
        env=environment(client,db,settings);award(env);body=save_body(preview(env));path=env['root']+'/simulator/scenarios'
        assert sorted(race_requests(settings,db,client,[(path,body),(path,body)]))==[201,201]
        with db.session() as session:assert session.scalar(select(func.count()).select_from(SimulationScenario))==1
    finally:client.close()


def test_native_save_racing_award_is_complete_old_snapshot_or_stale(pg_accounts):
    settings,db=pg_accounts;client=browser(settings,db)
    try:
        env=environment(client,db,settings);record=preview(env);r=vote(env,assign(env))
        requests=[(env['root']+'/simulator/scenarios',save_body(record)),(env['root']+'/reviews/'+r['id']+'/finalize',final_body(r))]
        results=race_requests(settings,db,env['actors']['reviewer']['client'],requests)
        assert sorted(results) in ([200,201],[200,409])
        with db.session() as session:
            for row in session.scalars(select(SimulationScenario)):
                assert row.record['snapshot']['source_award_count']==0
                assert row.record['result']['unallocated_cents']==1000000
    finally:client.close()


def test_native_scenario_history_guards(pg_accounts):
    settings,db=pg_accounts;client=browser(settings,db)
    try:
        env=environment(client,db,settings);save(env)
        for sql in ["UPDATE simulation_scenarios SET title='changed'",'DELETE FROM simulation_scenarios','TRUNCATE simulation_scenarios CASCADE']:
            with pytest.raises(DBAPIError),db.engine.begin() as connection:connection.execute(text(sql))
    finally:client.close()


def test_native_scenario_composite_policy_scope(pg_accounts):
    settings,db=pg_accounts;client=browser(settings,db)
    try:
        env=environment(client,db,settings);save(env)
        # An otherwise-valid captured row cannot point at an invented policy ID.
        with pytest.raises(DBAPIError),db.engine.begin() as connection:
            connection.execute(text("""INSERT INTO simulation_scenarios
                (id,workspace_id,project_id,source_policy_id,calculation_policy_id,created_by,title,request_id,request_hash,snapshot_hash,record_hash,record)
                SELECT gen_random_uuid(),workspace_id,project_id,gen_random_uuid(),calculation_policy_id,created_by,title,
                gen_random_uuid(),request_hash,snapshot_hash,record_hash,record FROM simulation_scenarios LIMIT 1"""))
    finally:client.close()


def test_native_migrations_repeat_without_recalculating_scenarios(pg_accounts):
    from alembic import command
    from app.db.migration import migration_config
    settings,db=pg_accounts;client=browser(settings,db)
    try:
        env=environment(client,db,settings);award(env);original=save(env)
        with db.engine.begin() as connection:
            config=migration_config();config.attributes['connection']=connection;command.upgrade(config,'head')
        restored=client.get(env['root']+'/simulator/scenarios/'+original['id']).json()
        assert restored['record_hash']==original['record_hash']
        assert restored['record']==original['record']
    finally:client.close()
