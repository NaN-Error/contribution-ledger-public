"""Real multi-connection native locks and history guards; skipped without test DB."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import UUID,uuid4
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from tests.test_postgres_accounts import pg_accounts,browser
from tests.phase12_helpers import environment,command,approve,manual,promote,accept_package,call
from tests.auth_helpers import mutation
pytestmark=pytest.mark.postgres


def race(settings,db,client,path,body):
    csrf=client.get('/api/v1/auth/session').json()['csrf_token'];barrier=Barrier(2)
    def attempt(_):
        peer=browser(settings,db);peer.cookies.update(client.cookies)
        try:
            barrier.wait(timeout=10)
            result=peer.post(path,json=body,headers={'Origin':'http://testserver','X-CSRF-Token':csrf})
            assert result.status_code in {200,201},result.text
            return result.json()
        finally:peer.close()
    with ThreadPoolExecutor(max_workers=2) as pool:return list(pool.map(attempt,[0,1]))


def test_native_repeated_historical_create_is_one_batch(pg_accounts):
    settings,db=pg_accounts;client=browser(settings,db)
    try:
        env=environment(client,db,settings)
        values=race(settings,db,client,env['root']+'/reconstruction',env['batch_create_body'])
        assert values[0]['id']==values[1]['id']
        with db.session() as session:assert session.scalar(text('SELECT count(*) FROM reconstruction_batches'))==1
    finally:client.close()


def test_native_same_candidate_command_has_one_result(pg_accounts):
    settings,db=pg_accounts;client=browser(settings,db)
    try:
        env=environment(client,db,settings);body=command(env['batch'],document={'title':'Historical art','category':'art','summary':'A documented outcome with independently reviewed evidence.'})
        values=race(settings,db,client,env['base']+'/candidates',body)
        assert values[0]['result']==values[1]['result']
        with db.session() as session:assert session.scalar(text('SELECT count(*) FROM reconstruction_candidates'))==1
    finally:client.close()


def test_native_simultaneous_archive_preserves_one_opening_snapshot(pg_accounts):
    settings,db=pg_accounts;client=browser(settings,db)
    try:
        env=environment(client,db,settings);approve(env);accept_package(env,promote(env,manual(env)))
        preview=client.get(env['base']+'/opening-preview').json()
        body=command(env['batch'],reviewed=True,reviewed_hash=preview['review_hash'])
        values=race(settings,db,client,env['base']+'/freeze',body);assert values[0]['result']==values[1]['result']
        with db.session() as session:
            assert session.scalar(text('SELECT count(*) FROM opening_balance_snapshots'))==1
            assert session.scalar(text('SELECT count(*) FROM credit_awards'))==1
    finally:client.close()


def test_native_history_cannot_be_truncated_or_rebound(pg_accounts):
    settings,db=pg_accounts;client=browser(settings,db)
    try:
        env=environment(client,db,settings);manual(env)
        for sql in ['TRUNCATE reconstruction_events','DELETE FROM reconstruction_candidates',"UPDATE reconstruction_batches SET definition='{}'"]:
            with pytest.raises(DBAPIError),db.engine.begin() as conn:conn.execute(text(sql))
    finally:client.close()


def test_native_candidate_project_reference_is_scoped(pg_accounts):
    settings,db=pg_accounts;client=browser(settings,db)
    try:
        env=environment(client,db,settings)
        with pytest.raises(DBAPIError),db.engine.begin() as conn:
            conn.execute(text("""INSERT INTO reconstruction_candidates(id,workspace_id,project_id,batch_id,state,version,document,created_by)
                SELECT :id,workspace_id,:wrong,id,'draft',1,'{}',created_by FROM reconstruction_batches WHERE id=:batch"""),
                {'id':uuid4(),'wrong':uuid4(),'batch':UUID(env['batch']['id'])})
    finally:client.close()
