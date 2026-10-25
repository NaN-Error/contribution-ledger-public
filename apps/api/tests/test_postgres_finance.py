"""Real PostgreSQL lock/immutability checks, explicitly skipped without native DB."""
from uuid import UUID,uuid4
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
import pytest
from tests.test_postgres_accounts import pg_accounts,browser
from tests.test_postgres_reconstruction import race
from tests.auth_helpers import mutation
from tests.phase13_helpers import *
pytestmark=pytest.mark.postgres


def test_native_finance_same_period_request_creates_one(pg_accounts,monkeypatch):
    settings,db=pg_accounts;client=browser(settings,db)
    try:
        e=finance_environment(client,db,settings,monkeypatch)
        rows=race(settings,db,client,e['finance']+'/periods',period_body(e));assert rows[0]['id']==rows[1]['id']
        with db.session() as s:assert s.scalar(text('SELECT count(*) FROM finance_periods'))==1
    finally:client.close()


def test_native_duplicate_receipt_command_is_atomic(pg_accounts,monkeypatch):
    settings,db=pg_accounts;client=browser(settings,db)
    try:
        e=finance_environment(client,db,settings,monkeypatch);p=period(e);d=document(e,p)
        rows=race(settings,db,client,e['finance']+'/periods/'+p['id']+'/entries',entry_body(d))
        assert rows[0]['id']==rows[1]['id']
        with db.session() as s:assert s.scalar(text('SELECT count(*) FROM finance_entries'))==1
    finally:client.close()


def test_native_simultaneous_close_creates_one_snapshot(pg_accounts,monkeypatch):
    settings,db=pg_accounts;client=browser(settings,db)
    try:
        e=finance_environment(client,db,settings,monkeypatch);p=period(e);d=document(e,p);decide(e,add_entry(e,p,d));proposal=propose(e,p)
        rows=race(settings,db,client,e['finance']+'/proposals/'+proposal['id']+'/decisions',approval_body(proposal))
        assert rows[0]['decision']['record']['close_id']==rows[1]['decision']['record']['close_id']
        with db.session() as s:
            assert s.scalar(text('SELECT count(*) FROM distribution_closes'))==1
            assert s.scalar(text('SELECT count(*) FROM release_share_snapshots'))==1
    finally:client.close()


def test_native_payment_idempotency_preserves_one_reference(pg_accounts,monkeypatch):
    settings,db=pg_accounts;client=browser(settings,db)
    try:
        e=finance_environment(client,db,settings,monkeypatch);p,d,entry,closed=complete(e)
        rows=race(settings,db,client,e['finance']+'/closes/'+closed['id']+'/payments',payment_body(e,closed))
        assert rows[0]['id']==rows[1]['id']
        with db.session() as s:assert s.scalar(text('SELECT count(*) FROM external_payments'))==1
    finally:client.close()


def test_native_finance_history_cannot_be_deleted_truncated_or_changed(pg_accounts,monkeypatch):
    settings,db=pg_accounts;client=browser(settings,db)
    try:
        e=finance_environment(client,db,settings,monkeypatch);complete(e)
        for name in ['finance_periods','finance_documents','finance_entries','finance_entry_decisions','release_share_snapshots','finance_proposals','finance_approvals','distribution_closes']:
            for sql in [f'DELETE FROM {name}',f'TRUNCATE {name}',f"UPDATE {name} SET record='{{}}'"]:
                with pytest.raises(DBAPIError),db.engine.begin() as conn:conn.execute(text(sql))
    finally:client.close()


def test_native_finance_foreign_project_reference_rejected(pg_accounts,monkeypatch):
    settings,db=pg_accounts;client=browser(settings,db)
    try:
        e=finance_environment(client,db,settings,monkeypatch);p=period(e)
        with pytest.raises(DBAPIError),db.engine.begin() as conn:
            conn.execute(text("""INSERT INTO finance_documents(id,workspace_id,project_id,period_id,created_by,request_id,request_hash,record,record_hash,object_id,backend,sha256,size_bytes)
            SELECT :id,workspace_id,:wrong,id,created_by,:request,:hash,'{}',:hash,:object,'local',:hash,1 FROM finance_periods WHERE id=:period"""),
            {'id':uuid4(),'wrong':uuid4(),'request':uuid4(),'hash':'a'*64,'object':uuid4(),'period':UUID(p['id'])})
    finally:client.close()
