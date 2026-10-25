"""Real PostgreSQL upgrade/credential checks in fixture-owned disposable schemas."""
import json
from hashlib import sha256
from uuid import UUID
import pytest
from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import text, select
from app.main import create_app
from app.analysis.models import RepositoryReadConnection, RepositoryAnalysis
from app.db.migration import migration_config
from app.security.secrets.encrypted import initialize, EncryptedCredentialStore
from tests.test_postgres_accounts import pg_accounts
from tests.test_repository_private import PrivateTransport, connect, private_start
from tests.test_repository_analysis import PublicFixture, start, finish, post
from tests.auth_helpers import bootstrap

pytestmark=pytest.mark.postgres


def test_populated_0018_to_0019_preserves_existing_users_reports_and_repeat_upgrade(pg_accounts):
    settings,database=pg_accounts
    with database.engine.begin() as c:
        cfg=migration_config();cfg.attributes['connection']=c;command.downgrade(cfg,'0018_desktop_profile')
    fixture=PublicFixture()
    with TestClient(create_app(settings,database,public_repository_client=fixture)) as client:
        owner=bootstrap(client,database)
        root=f"/api/v1/workspaces/{owner['workspace']['id']}/projects/{owner['project']['id']}/analysis"
        e={'client':client,'root':root};finish(e,start(e))
        def snapshot(c):
            return {name:sha256(json.dumps(sorted(c.execute(text('SELECT to_jsonb(t)::text FROM '+name+' t')).scalars()),sort_keys=True).encode()).hexdigest()
                for name in ['users','workspaces','projects','repository_analyses','analysis_draft_revisions']}
        with database.engine.begin() as c:
            before=snapshot(c);cfg=migration_config();cfg.attributes['connection']=c
            command.upgrade(cfg,'head');command.upgrade(cfg,'head')
            assert snapshot(c)==before
            assert c.execute(text('SELECT count(*) FROM repository_read_connections')).scalar_one()==0
            assert c.execute(text('SELECT version_num FROM alembic_version')).scalar_one()=='0019_repository_read'
        assert client.get(root).status_code==200


@pytest.fixture
def native_private(pg_accounts,tmp_path):
    settings,database=pg_accounts
    settings=settings.model_copy(update={'environment':'test','repository_private_reads_enabled':True,
        'repository_credential_root':str(tmp_path/'github-credentials'),
        'repository_master_key_file':str(tmp_path/'github-master/master.key')})
    initialize(settings.repository_master_key_file,settings.repository_credential_root)
    store=EncryptedCredentialStore(settings.repository_credential_root,settings.repository_master_key_file)
    transport=PrivateTransport()
    with TestClient(create_app(settings,database,repository_store=store,repository_transport=transport)) as client:
        owner=bootstrap(client,database)
        yield {'client':client,'root':f"/api/v1/workspaces/{owner['workspace']['id']}/projects/{owner['project']['id']}/analysis",
            'database':database,'transport':transport,'store':store}


def test_native_token_capture_and_populated_connection_prevent_destructive_downgrade(native_private):
    e=native_private;c=connect(e);r=finish(e,private_start(e,c))
    assert r['report']['repositories'][0]['private'] is True
    with e['database'].engine.begin() as connection:
        cfg=migration_config();cfg.attributes['connection']=connection
        with pytest.raises(RuntimeError,match='Connections exist'):command.downgrade(cfg,'0018_desktop_profile')
    assert e['client'].get(e['root']).status_code==200


def test_native_independent_connection_revocation_discards_inflight_private_response(native_private):
    e=native_private;c=connect(e);r=private_start(e,c)
    def revoke():
        with e['database'].engine.begin() as connection:
            connection.execute(text('UPDATE repository_read_connections SET active=false,version=version+1 WHERE id=:id'),{'id':UUID(c['id'])})
    e['transport'].callback=revoke
    failed=post(e,'/runs/'+r['id']+'/advance',{'expected_version':r['version']})
    assert failed['state']=='failed' and failed['error_code']=='analysis_connection_expired'
    with e['database'].session() as db:
        run=db.get(RepositoryAnalysis,UUID(r['id']));assert run.progress['sources']==[] and run.progress['repositories']==[]


@pytest.mark.parametrize('change', ['revoke', 'rotate'])
def test_native_activity_preview_rechecks_independently_changed_connection(native_private,change):
    e=native_private;c=connect(e)
    def update():
        with e['database'].engine.begin() as connection:
            connection.execute(text('UPDATE repository_read_connections SET version=version+1,active=:active WHERE id=:id'),
                {'id':UUID(c['id']),'active':change!='revoke'})
    e['transport'].callback=update
    response=post(e,'/activity',{'repository_urls':['https://github.com/team/game'],
        'connection_id':c['id'],'read_confirmed':True},409)
    assert response['error']['code']==('analysis_connection_expired' if change=='revoke' else 'analysis_connection_changed')
    assert 'repositories' not in response
    assert e['client'].get(e['root']).json()['runs']==[]
