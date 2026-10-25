"""Real local cryptography plus application gates; no live authenticator service."""
import base64
import importlib
import os
from datetime import timedelta
from pathlib import Path
from uuid import UUID,uuid4
import pytest
from sqlalchemy import select
from app.auth.mfa_crypto import totp,match_counter,FactorCipher
from app.auth.mfa_models import Authenticator
from app.auth.models import BrowserSession
from app.operations.security import initialize_auth_key,reset_factor
from app.security.tokens import now,utc
from app.security.secrets.store import SecretUnavailable
from tests.auth_helpers import bootstrap,mutation,login,PASSWORD,other_client

@pytest.fixture
def factor_env(client,database,settings,tmp_path):
    settings.auth_master_key_file=str(tmp_path/'auth-master'/'master.key')
    initialize_auth_key(database)
    owner=bootstrap(client,database)
    return owner

def enroll(client):
    r=mutation(client,'/api/v1/auth/mfa/enroll',{'password':PASSWORD});assert r.status_code==200,r.text
    seed=base64.b32decode(r.json()['secret']+'='*((-len(r.json()['secret']))%8))
    r=mutation(client,'/api/v1/auth/mfa/confirm',{'code':totp(seed,int(now().timestamp())//30)})
    assert r.status_code==200,r.text
    return seed,r.json()

@pytest.mark.parametrize('timestamp,expected',[(59,'94287082'),(1111111109,'07081804'),(1111111111,'14050471'),(1234567890,'89005924'),(2000000000,'69279037'),(20000000000,'65353130')])
def test_rfc6238_vectors(timestamp,expected):
    assert totp(b'12345678901234567890',timestamp//30,digits=8)==expected

def test_codes_replay_skew_and_bad_input():
    secret=b'12345678901234567890'
    assert match_counter(secret,totp(secret,99),3000,98)==99
    assert match_counter(secret,totp(secret,99),3000,99) is None
    assert match_counter(secret,totp(secret,97),3000,0) is None
    assert match_counter(secret,'not-a-code',3000,-1) is None

def test_cipher_is_account_bound(tmp_path):
    path=tmp_path/'key';path.write_bytes(os.urandom(32));path.chmod(0o600)
    c=FactorCipher(str(path));user=uuid4();encrypted=c.seal(user,b'private-seed')
    assert c.open(user,encrypted)==b'private-seed'
    with pytest.raises(SecretUnavailable):c.open(uuid4(),encrypted)
    path.write_bytes(os.urandom(32))
    with pytest.raises(SecretUnavailable):c.open(user,encrypted)

def test_cli_is_importable():
    assert callable(importlib.import_module('app.cli').main)

def test_enrollment_encrypts_seed_and_requires_second_factor(client,database,settings,factor_env):
    seed,result=enroll(client)
    assert len(result['recovery_codes'])==10
    with database.session() as db:
        factor=db.get(Authenticator,UUID(factor_env['user']['id']))
        assert seed.hex() not in factor.encrypted_secret
        assert result['recovery_codes'][0] not in str(factor.recovery_hashes)
    mutation(client,'/api/v1/auth/logout')
    first=login(client).json();assert first['mfa_required'] and first['user'] is None
    assert client.get('/api/v1/workspaces').status_code==401
    assert mutation(client,'/api/v1/auth/password',{'current_password':PASSWORD,'password':PASSWORD+'new'}).status_code==401
    r=mutation(client,'/api/v1/auth/mfa/verify',{'code':result['recovery_codes'][0]})
    assert r.status_code==200,r.text
    assert r.json()['user'] and not r.json()['mfa_required']
    assert client.get('/api/v1/workspaces').status_code==200
    mutation(client,'/api/v1/auth/logout');login(client)
    assert mutation(client,'/api/v1/auth/mfa/verify',{'code':result['recovery_codes'][0]}).status_code==401

def test_totp_cannot_replay_enrollment_step(client,database,factor_env):
    seed,result=enroll(client);mutation(client,'/api/v1/auth/logout');login(client)
    r=mutation(client,'/api/v1/auth/mfa/verify',{'code':totp(seed,int(now().timestamp())//30)})
    assert r.status_code==401

def test_lost_key_cannot_be_initialized_over_existing_factors(client,database,settings,factor_env):
    enroll(client);Path(settings.auth_master_key_file).unlink()
    with pytest.raises(ValueError):initialize_auth_key(database)

def test_reset_revokes_and_forces_reenrollment_even_locally(client,database,factor_env):
    enroll(client)
    reset_factor(database,'owner@example.test','Verified fictional identity by operator','RESET-MFA:owner@example.test')
    assert client.get('/api/v1/workspaces').status_code==401
    result=login(client).json();assert result['mfa_required'] and not result['mfa_enrolled']
    assert client.get('/api/v1/workspaces').status_code==401

def test_mfa_attempts_are_rate_limited(client,database,factor_env):
    _,result=enroll(client);mutation(client,'/api/v1/auth/logout');login(client)
    responses=[mutation(client,'/api/v1/auth/mfa/verify',{'code':'notvalid'}).status_code for _ in range(12)]
    assert 429 in responses

def test_mfa_disable_requires_password_and_existing_factor(client,database,factor_env):
    _,result=enroll(client)
    r=mutation(client,'/api/v1/auth/mfa/disable',{'password':PASSWORD,'code':result['recovery_codes'][0]})
    assert r.status_code==200,r.text
    mutation(client,'/api/v1/auth/logout');r=login(client).json()
    assert not r['mfa_required'] and r['user']

def test_password_recovery_does_not_remove_mfa(client,database,factor_env):
    from app.auth.operator import recovery_token
    enroll(client);token=recovery_token(database,'owner@example.test','Verified synthetic password recovery')
    r=mutation(client,'/api/v1/auth/recover',{'token':token,'password':PASSWORD+' changed'})
    assert r.status_code==200,r.text
    r=login(client,password=PASSWORD+' changed').json();assert r['mfa_required']

def test_pending_login_expires(client,database,factor_env):
    enroll(client);mutation(client,'/api/v1/auth/logout');s=login(client).json()
    with database.session() as db:
        row=db.get(BrowserSession,UUID(s['session_id']));row.expires_at=now()-timedelta(seconds=1);db.commit()
    assert client.get('/api/v1/auth/mfa/status').status_code==401

def test_enrollment_wrong_password_does_not_change_factor(client,database,factor_env):
    r=mutation(client,'/api/v1/auth/mfa/enroll',{'password':'wrong'})
    assert r.status_code==401
    assert client.get('/api/v1/auth/mfa/status').json()['enabled'] is False

def test_required_mfa_cannot_disable(client,database,settings,factor_env):
    _,result=enroll(client);settings.require_mfa=True
    assert mutation(client,'/api/v1/auth/mfa/disable',{'password':PASSWORD,'code':result['recovery_codes'][0]}).status_code==403
