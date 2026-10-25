"""Independent PostgreSQL connections; skipped unless a disposable native DB is configured."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4,UUID
import pytest
from sqlalchemy import text,select,func
from sqlalchemy.exc import DBAPIError
from tests.test_postgres_accounts import pg_accounts,browser
from tests.ai_helpers import start,price,queue_probe
from tests.auth_helpers import mutation
from app.ai.jobs import claim
from app.ai.models import AIJob,AIUsageBucket
pytestmark=pytest.mark.postgres

def test_native_ai_budget_race_cannot_double_reserve(pg_accounts,tmp_path):
    settings,db=pg_accounts;client=browser(settings,db)
    try:
        x=start(client,db,settings,tmp_path,'openai',limit=2560);price(client,x,True)
        url=x['base']+'/models/'+x['model']['id'];q=client.get(url+'/probe-quote').json();state=client.get('/api/v1/auth/session').json();barrier=Barrier(2)
        def attempt(_):
            peer=browser(settings,db);peer.cookies.update(client.cookies)
            try:
                barrier.wait(timeout=10)
                return peer.post(url+'/probe',headers={'Origin':'http://testserver','X-CSRF-Token':state['csrf_token']},json={
                  'request_id':str(uuid4()),'quote_hash':q['quote_hash'],'confirmed_reservation_microusd':2560,'payer_approved':True}).status_code
            finally:peer.close()
        with ThreadPoolExecutor(max_workers=2) as pool:result=list(pool.map(attempt,[1,2]))
        assert sorted(result)==[202,409]
        with db.session() as session:assert session.scalar(select(AIUsageBucket.held_microusd))==2560
    finally:client.close()

def test_native_ai_one_worker_claims_probe(pg_accounts,tmp_path):
    settings,db=pg_accounts;client=browser(settings,db)
    try:
        x=start(client,db,settings,tmp_path);price(client,x);queue_probe(client,x);barrier=Barrier(2)
        def attempt(_):barrier.wait(timeout=10);return claim(db,settings)
        with ThreadPoolExecutor(max_workers=2) as pool:result=list(pool.map(attempt,[1,2]))
        assert sum(value is not None for value in result)==1
    finally:client.close()

def test_native_ai_cancel_race_refunds_once(pg_accounts,tmp_path):
    settings,db=pg_accounts;client=browser(settings,db)
    try:
        x=start(client,db,settings,tmp_path,'openai');price(client,x,True);response,_=queue_probe(client,x)
        url=x['base']+'/jobs/'+response.json()['id']+'/cancel';state=client.get('/api/v1/auth/session').json();barrier=Barrier(2)
        def attempt(_):
            peer=browser(settings,db);peer.cookies.update(client.cookies)
            try:
                barrier.wait(timeout=10);return peer.post(url,headers={'Origin':'http://testserver','X-CSRF-Token':state['csrf_token']},json={'reason':'Concurrent synthetic cancellation'}).status_code
            finally:peer.close()
        with ThreadPoolExecutor(max_workers=2) as pool:assert list(pool.map(attempt,[1,2]))==[200,200]
        with db.session() as session:assert session.scalar(select(AIUsageBucket.held_microusd))==0
    finally:client.close()

def test_native_ai_history_and_dispatch_input_guards(pg_accounts,tmp_path):
    settings,db=pg_accounts;client=browser(settings,db)
    try:
        x=start(client,db,settings,tmp_path);price(client,x);queue_probe(client,x)
        for statement in ["UPDATE ai_jobs SET specification='{}'",'DELETE FROM ai_connections',"UPDATE ai_prices SET input_rate=1",'TRUNCATE ai_operation_events']:
            with pytest.raises(DBAPIError),db.engine.begin() as connection:connection.execute(text(statement))
    finally:client.close()

def test_native_ai_scoped_foreign_key(pg_accounts,tmp_path):
    settings,db=pg_accounts;client=browser(settings,db)
    try:
        x=start(client,db,settings,tmp_path)
        with pytest.raises(DBAPIError),db.engine.begin() as connection:
            connection.execute(text("INSERT INTO ai_models (id,workspace_id,project_id,connection_id,remote_id,document,fingerprint,generation,available,observed_at,probe_state) VALUES (:i,:w,:p,:c,'fake','{}',:hash,1,true,CURRENT_TIMESTAMP,'unknown')"),
              {'i':uuid4(),'w':uuid4(),'p':UUID(x['account']['project']['id']),'c':UUID(x['connection']['id']),'hash':'0'*64})
    finally:client.close()

def test_native_ai_lock_function_uses_migration_schema(pg_accounts):
    _,db=pg_accounts
    with db.engine.connect() as connection:
        schema=connection.execute(text('SELECT current_schema()')).scalar_one()
        definition=connection.execute(text("SELECT pg_get_functiondef('cl_ai_lock_workspace(uuid)'::regprocedure)")).scalar_one()
        assert 'SECURITY DEFINER' in definition and schema in definition and 'pg_catalog' in definition
