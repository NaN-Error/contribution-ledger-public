"""Native MFA locking and upgrade tests. Never silently replaced by SQLite."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import UUID
import pytest
from alembic import command
from sqlalchemy import select,text
from sqlalchemy.exc import DBAPIError
from app.auth.mfa_models import Authenticator
from app.auth.models import BrowserSession
from app.db.migration import migration_config,expected_revision
from app.operations.security import initialize_auth_key,reset_factor
from tests.test_postgres_accounts import pg_accounts,browser
from tests.auth_helpers import bootstrap,login
from tests.test_phase14_mfa import enroll
pytestmark=pytest.mark.postgres

@pytest.fixture
def factor(pg_accounts,tmp_path):
    settings,db=pg_accounts;settings.auth_master_key_file=str(tmp_path/'auth/master.key')
    initialize_auth_key(db);client=browser(settings,db);owner=bootstrap(client,db)
    seed,result=enroll(client)
    try:yield settings,db,client,owner,seed,result
    finally:client.close()

def test_native_recovery_code_is_consumed_once(factor):
    settings,db,_,owner,seed,result=factor;barrier=Barrier(2)
    clients=[browser(settings,db) for _ in range(2)]
    for client in clients:assert login(client).json()['mfa_required']
    def attempt(client):
        csrf=client.get('/api/v1/auth/session').json()['csrf_token'];barrier.wait(timeout=10)
        return client.post('/api/v1/auth/mfa/verify',headers={'Origin':'http://testserver','X-CSRF-Token':csrf},json={'code':result['recovery_codes'][0]}).status_code
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:statuses=list(executor.map(attempt,clients))
        assert sorted(statuses)==[200,401]
        with db.session() as session:assert len(session.get(Authenticator,UUID(owner['user']['id'])).recovery_hashes)==9
    finally:
        for client in clients:client.close()

def test_native_mfa_seed_and_old_sessions(factor):
    settings,db,client,owner,seed,result=factor
    with db.session() as s:
        row=s.get(Authenticator,UUID(owner['user']['id']));assert row.enabled and row.last_counter>=0
        assert seed.hex() not in row.encrypted_secret
        sessions=list(s.scalars(select(BrowserSession).where(BrowserSession.user_id==UUID(owner['user']['id']),BrowserSession.revoked_at.is_(None))))
        assert all(x.mfa_verified_at is not None for x in sessions)

def test_native_reset_requires_reenrollment(factor):
    settings,db,client,*_=factor
    reset_factor(db,'owner@example.test','Verified synthetic recovery identity','RESET-MFA:owner@example.test')
    assert client.get('/api/v1/workspaces').status_code==401
    assert login(client).json()['mfa_required']

def test_native_factor_foreign_key_and_downgrade(factor):
    _,db,_,owner,*_=factor
    with pytest.raises(DBAPIError),db.engine.begin() as c:
        c.execute(text("UPDATE authenticators SET user_id='00000000-0000-4000-8000-000000000000' WHERE user_id=:user"),{'user':UUID(owner['user']['id'])})
    with pytest.raises(RuntimeError,match='MFA records'),db.engine.begin() as c:
        cfg=migration_config();cfg.attributes['connection']=c;command.downgrade(cfg,'0013_financial_distributions')

def test_native_upgrade_repeats_and_preserves_sessions(pg_accounts):
    settings,db=pg_accounts;client=browser(settings,db);bootstrap(client,db)
    with db.engine.begin() as c:
        cfg=migration_config();cfg.attributes['connection']=c
        before=c.execute(text('SELECT count(*) FROM browser_sessions')).scalar_one()
        command.downgrade(cfg,'0013_financial_distributions');command.upgrade(cfg,'head');command.upgrade(cfg,'head')
        assert c.execute(text('SELECT version_num FROM alembic_version')).scalar_one()==expected_revision()
        assert c.execute(text('SELECT count(*) FROM browser_sessions')).scalar_one()==before
        assert c.execute(text('SELECT count(*) FROM browser_sessions WHERE mfa_verified_at IS NOT NULL')).scalar_one()==0
    client.close()
