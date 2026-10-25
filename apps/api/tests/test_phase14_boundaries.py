"""Negative tests for deployment gates, hostile input and operator boundaries."""
import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace
import pytest
from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import select,text
from app.auth.models import User,BrowserSession
from app.auth.mfa_models import Authenticator
from app.db.migration import migration_config,expected_revision
from app.main import create_app
from tests.auth_helpers import bootstrap
from tests.test_phase14_mfa import factor_env,enroll
ROOT=Path(__file__).resolve().parents[3]

def script(name):
    spec=importlib.util.spec_from_file_location('phase14_'+name,ROOT/'scripts'/(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

def staged(settings,**extra):
    base={'environment':'staging','restricted_staging_enabled':True,'require_mfa':True,
      'enable_development_tools':False,'secure_cookies':True,'allowed_origins':['https://testserver'],
      'ai_deployment_mode':'disabled','github_enabled':False,'ai_live_enabled':False}
    base.update(extra);return settings.model_copy(update=base)

@pytest.mark.parametrize('changes',[{'require_mfa':False},{'enable_development_tools':True},
 {'secure_cookies':False},{'allowed_origins':['http://testserver']},
 {'allowed_origins':['https://testserver','https://other.test']},{'github_enabled':True},
 {'ai_deployment_mode':'customer_controlled'},{'ai_live_enabled':True},{'environment':'production'}])
def test_staging_rejects_insecure_settings(settings,changes):
    with pytest.raises(ValueError):staged(settings,**changes).require_local_foundation()

def test_staging_hides_docs_and_requires_auth_for_system_details(settings,database):
    config=staged(settings);config.require_local_foundation()
    # Do not run lifespan: native role/secret startup verification is separate.
    client=TestClient(create_app(config,database),base_url='https://testserver',raise_server_exceptions=False)
    assert client.get('/docs').status_code==404
    assert client.get('/openapi.json').status_code==404
    assert client.get('/api/v1/system/status').status_code==401
    assert client.get('/health/live').status_code==200
    client.close()

def test_response_boundaries_and_get_body(client):
    response=client.get('/health/live')
    assert response.headers['Referrer-Policy']=='no-referrer'
    assert response.headers['X-Frame-Options']=='DENY'
    assert response.headers['Cache-Control']=='no-store'
    assert client.request('GET','/health/live',content=b'payload').status_code==400
    assert client.get('/health/live',headers=[('Host','testserver'),('Host','untrusted.test')]).status_code==400

def test_mfa_rejects_missing_csrf_and_cross_origin(client,database,factor_env):
    assert client.post('/api/v1/auth/mfa/enroll',json={'password':'untrusted'}).status_code==403
    assert client.post('/api/v1/auth/mfa/enroll',headers={'Origin':'https://untrusted.test'},json={'password':'untrusted'}).status_code==403

def test_factor_history_blocks_downgrade(client,database,factor_env):
    enroll(client)
    with pytest.raises(RuntimeError,match='MFA records'),database.engine.begin() as c:
        config=migration_config();config.attributes['connection']=c
        command.downgrade(config,'0013_financial_distributions')
    with database.session() as db:
        assert db.scalar(select(Authenticator)) is not None
        assert db.execute(text('SELECT version_num FROM alembic_version')).scalar_one()==expected_revision()

def test_populated_accounts_survive_phase13_upgrade(client,database):
    bootstrap(client,database)
    with database.session() as db:
        old_user=db.scalar(select(User.id));old_session=db.scalar(select(BrowserSession.id))
    config=migration_config()
    with database.engine.begin() as c:
        config.attributes['connection']=c
        command.downgrade(config,'0013_financial_distributions')
        command.upgrade(config,'head');command.upgrade(config,'head')
    with database.session() as db:
        assert db.get(User,old_user).email=='owner@example.test'
        assert db.get(BrowserSession,old_session).mfa_verified_at is None
        assert db.scalar(select(Authenticator)) is None

@pytest.mark.parametrize('host,bind,cidrs',[('https://testserver','127.0.0.1','127.0.0.0/8'),
 ('ledger.test','0.0.0.0','127.0.0.0/8'),('ledger.test','8.8.8.8','127.0.0.0/8'),
 ('ledger.test','127.0.0.1','0.0.0.0/0'),('ledger.test','127.0.0.1','8.8.8.0/24'),
 ('ledger.test\nmalicious','127.0.0.1','127.0.0.0/8')])
def test_operator_rejects_public_or_injected_staging(host,bind,cidrs):
    with pytest.raises(ValueError):script('staging').validate_network(host,bind,cidrs)

def test_unacknowledged_staging_cannot_start(tmp_path):
    tool=script('staging');tool.ROOT=tmp_path
    folder=tmp_path/'.local/staging';folder.mkdir(parents=True)
    (folder/'readiness.json').write_text(json.dumps({'scope':'restricted-synthetic-staging','reviewed_by':'Test operator',
     'clean_build_verified':True,'native_database_verified':True,'restore_drill_verified':False,
     'mfa_browser_verified':True,'tls_and_network_verified':True,'dependency_review_completed':True}))
    with pytest.raises(ValueError,match='verification'):tool.readiness()

def test_backup_rejects_nested_and_symlink_destinations(tmp_path):
    tool=script('recovery');key=tmp_path/'key';key.write_bytes(os.urandom(32));key.chmod(0o600)
    with pytest.raises(tool.OperationError):tool.check_locations(key,tmp_path/'scratch',tmp_path/'scratch/archive')
    link=tmp_path/'alias';(tmp_path/'scratch').mkdir();link.symlink_to(tmp_path/'scratch',target_is_directory=True)
    with pytest.raises(Exception):tool.check_locations(key,link,tmp_path/'archive')
    with pytest.raises(tool.OperationError):tool.check_locations(tool.ROOT/'key',tmp_path/'scratch',tmp_path/'archive')

def test_backup_missing_configuration_never_stops_docker(tmp_path,monkeypatch):
    tool=script('recovery');calls=[]
    monkeypatch.setattr(tool,'inspect',lambda *args:calls.append(args))
    args=SimpleNamespace(project='contribution-ledger',confirm='STOP-WRITERS:contribution-ledger',
     key_file=tmp_path/'key',scratch=tmp_path/'scratch',output=tmp_path/'capture',env_file=tmp_path/'missing.env',recovery_file=[])
    with pytest.raises(tool.OperationError):tool.backup(args)
    assert calls==[]

def test_dump_warning_is_not_accepted_as_complete(monkeypatch):
    tool=script('recovery')
    monkeypatch.setattr(tool.subprocess,'run',lambda *a,**k:SimpleNamespace(returncode=0,stderr=b'warning: partial',stdout=b'data'))
    with pytest.raises(tool.OperationError):tool.run(['pg_dump'],fail_on_warning=True)
    assert tool.run(['inspect'])==b'data'

def test_restore_waits_past_temporary_socket_server(monkeypatch):
    tool=script('recovery');probes=[]
    def probe(args,**kwargs):
        # During image initialization, the Unix socket accepts requests but
        # loopback TCP is unavailable until the permanent server starts.
        probes.append(args)
        tcp='-h 127.0.0.1' in args[-1]
        ready=not tcp or len(probes)>=3
        return SimpleNamespace(returncode=0 if ready else 1,stderr=b'',stdout=b'')
    monkeypatch.setattr(tool.subprocess,'run',probe)
    monkeypatch.setattr(tool.time,'sleep',lambda _:None)
    tool.wait_for_database('ledger-restore-synthetic-db',attempts=3)
    assert len(probes)==3

def test_restore_never_accepts_socket_only_initialization(monkeypatch):
    tool=script('recovery')
    def probe(args,**kwargs):
        return SimpleNamespace(returncode=1 if '-h 127.0.0.1' in args[-1] else 0,stderr=b'',stdout=b'')
    monkeypatch.setattr(tool.subprocess,'run',probe)
    monkeypatch.setattr(tool.time,'sleep',lambda _:None)
    with pytest.raises(tool.OperationError,match='did not become ready'):
        tool.wait_for_database('ledger-restore-synthetic-db',attempts=2)

def test_production_finance_boundary_unchanged(settings):
    with pytest.raises(ValueError):staged(settings,environment='production').require_local_foundation()

def test_populated_github_session_reference_survives_upgrade(client,database,settings):
    from tests.phase8_helpers import environment
    environment(client,database,settings)
    cfg=migration_config()
    with database.engine.begin() as c:
        cfg.attributes['connection']=c
        flows=list(c.execute(text('SELECT id,session_id FROM github_auth_flows')))
        assert flows
        command.downgrade(cfg,'0013_financial_distributions')
        command.upgrade(cfg,'head')
        assert list(c.execute(text('SELECT id,session_id FROM github_auth_flows')))==flows
        assert list(c.execute(text('PRAGMA foreign_key_check')))==[]

def test_failed_phase14_upgrade_rolls_back_without_half_schema(client,database,monkeypatch):
    import alembic.op as operations
    from sqlalchemy import inspect
    bootstrap(client,database);cfg=migration_config()
    with database.engine.begin() as c:
        cfg.attributes['connection']=c;command.downgrade(cfg,'0013_financial_distributions')
    original=operations.execute
    def fail_on_second_column(statement,*args,**kwargs):
        if 'ADD COLUMN mfa_verified_at' in str(statement):raise RuntimeError('Synthetic injected migration failure')
        return original(statement,*args,**kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(operations,'execute',fail_on_second_column)
        with pytest.raises(RuntimeError,match='Synthetic injected'),database.engine.begin() as c:
            cfg.attributes['connection']=c;command.upgrade(cfg,'head')
    with database.engine.begin() as c:
        assert c.execute(text('SELECT version_num FROM alembic_version')).scalar_one()=='0013_financial_distributions'
        assert 'authenticators' not in inspect(c).get_table_names()
        assert 'pending_user_id' not in {x['name'] for x in inspect(c).get_columns('browser_sessions')}
        assert c.execute(text('SELECT count(*) FROM users')).scalar_one()==1
        cfg.attributes['connection']=c;command.upgrade(cfg,'head')
        assert c.execute(text('SELECT version_num FROM alembic_version')).scalar_one()==expected_revision()
