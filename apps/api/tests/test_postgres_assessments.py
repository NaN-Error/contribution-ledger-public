"""Native PostgreSQL evidence/queue contracts; explicit disposable database only."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import UUID,uuid4
import pytest
from sqlalchemy import text,select,func
from sqlalchemy.exc import DBAPIError
from tests.test_postgres_accounts import pg_accounts,browser
from tests.phase11_helpers import setup,packet,plan,grant,enqueue,complete
from tests.auth_helpers import mutation
from app.ai.jobs import claim
from app.ai.models import AIJob
pytestmark=pytest.mark.postgres


def test_native_packet_freshness_function_and_synthetic_result(pg_accounts):
    settings,db=pg_accounts;client=browser(settings,db)
    try:
        env=setup(client,db,settings);p=packet(env)
        with db.session() as session:
            assert session.scalar(text('SELECT cl_ai_packet_current(:id)'),{'id':UUID(p['id'])}) is True
        result=complete(env,plan(env,p));assert result['status']=='valid'
        with db.session() as session:
            assert session.scalar(text('SELECT count(*) FROM credit_awards'))==0
            schema=session.scalar(text('SELECT current_schema()'))
            definition=session.scalar(text("SELECT pg_get_functiondef('cl_ai_packet_current(uuid)'::regprocedure)"))
            assert schema in definition and 'SECURITY DEFINER' in definition and 'pg_catalog' in definition
            assert 'UPDATE ' not in definition
    finally:client.close()


def test_native_same_assessment_request_reserves_once(pg_accounts):
    settings,db=pg_accounts;client=browser(settings,db)
    try:
        env=setup(client,db,settings);x=plan(env,packet(env));assert grant(env,x).status_code==201
        quote=client.get(env['assessments']+'/plans/'+x['id']+'/quote').json();state=client.get('/api/v1/auth/session').json()
        body={'request_id':str(uuid4()),'quote_hash':quote['quote_hash'],'confirmed_reservation_microusd':quote['specification']['reservation_microusd'],'payer_approved':True}
        barrier=Barrier(2)
        def attempt(_):
            peer=browser(settings,db);peer.cookies.update(client.cookies)
            try:
                barrier.wait(timeout=10)
                response=peer.post(env['assessments']+'/plans/'+x['id']+'/run',json=body,headers={'Origin':'http://testserver','X-CSRF-Token':state['csrf_token']})
                assert response.status_code==202,response.text
                return response.json()['id']
            finally:peer.close()
        with ThreadPoolExecutor(max_workers=2) as pool:ids=list(pool.map(attempt,[1,2]))
        assert ids[0]==ids[1]
        with db.session() as session:assert session.scalar(select(func.count()).select_from(AIJob).where(AIJob.kind=='assessment'))==1
    finally:client.close()


def test_native_only_one_worker_claims_assessment(pg_accounts):
    settings,db=pg_accounts;client=browser(settings,db)
    try:
        env=setup(client,db,settings);x=plan(env,packet(env));assert grant(env,x).status_code==201;j,_=enqueue(env,x);barrier=Barrier(2)
        def attempt(_):barrier.wait(timeout=10);return claim(db,settings,UUID(j['id']))
        with ThreadPoolExecutor(max_workers=2) as pool:claims=list(pool.map(attempt,[1,2]))
        assert sum(item is not None for item in claims)==1
    finally:client.close()


def test_native_revoked_plan_cannot_be_dispatched(pg_accounts):
    settings,db=pg_accounts;client=browser(settings,db)
    try:
        env=setup(client,db,settings);x=plan(env,packet(env));assert grant(env,x).status_code==201;j,_=enqueue(env,x)
        assert mutation(client,env['assessments']+'/plans/'+x['id']+'/revoke',{'reason':'Withdraw this synthetic disclosure before dispatch'}).status_code==200
        assert claim(db,settings,UUID(j['id'])) is None
    finally:client.close()


def test_native_assessment_history_and_job_identity_guards(pg_accounts):
    settings,db=pg_accounts;client=browser(settings,db)
    try:
        env=setup(client,db,settings);complete(env,plan(env,packet(env)))
        statements=["UPDATE ai_review_packets SET payload='{}'",'DELETE FROM ai_review_results','TRUNCATE ai_review_grants',
            "UPDATE ai_jobs SET assessment_plan_id=NULL WHERE kind='assessment'"]
        for statement in statements:
            with pytest.raises(DBAPIError),db.engine.begin() as conn:conn.execute(text(statement))
    finally:client.close()


def test_native_assessment_plan_cannot_cross_project(pg_accounts):
    settings,db=pg_accounts;client=browser(settings,db)
    try:
        env=setup(client,db,settings);p=packet(env)
        with pytest.raises(DBAPIError),db.engine.begin() as conn:
            conn.execute(text("""INSERT INTO ai_review_plans
                (id,workspace_id,project_id,package_id,packet_id,profile_id,connection_id,created_by,mode,request_id,request_hash,definition,content_hash,reason)
                SELECT :id,workspace_id,:wrong,package_id,id,profile_id,:connection,created_by,'official',:request,:hash,'{}',:hash,'Synthetic FK rejection'
                FROM ai_review_packets WHERE id=:packet"""),{'id':uuid4(),'wrong':uuid4(),'connection':UUID(env['connection']['id']),
                'request':uuid4(),'hash':'0'*64,'packet':UUID(p['id'])})
    finally:client.close()
