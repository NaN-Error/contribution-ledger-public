"""Native PostgreSQL acceptance tests; never reported as passing on SQLite.

CL_TEST_DATABASE_URL must name a disposable *_test database. Every test uses
its own schema and removes that schema only. Independent engines/connections
exercise actual database locks; no process-local authentication mutex exists.
"""
import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4
import pytest
from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text, select, func
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from app.auth.models import User
from app.auth.operator import setup_token
from app.core.config import Settings
from app.db.migration import migration_config, expected_revision
from app.db.session import Database
from app.main import create_app
from app.projects.models import AuditEvent, WorkspaceMembership
from tests.auth_helpers import bootstrap, mutation, invite, PASSWORD

pytestmark = pytest.mark.postgres

@pytest.fixture
def pg_accounts(tmp_path):
    value = os.environ.get('CL_TEST_DATABASE_URL')
    if not value:
        pytest.skip('Native PostgreSQL account/locking tests need CL_TEST_DATABASE_URL; not simulated with SQLite.')
    url = make_url(value)
    if not url.drivername.startswith('postgresql') or not url.database or not url.database.endswith('_test'):
        pytest.fail('Only an explicitly configured disposable PostgreSQL *_test database is permitted.')
    schema = 'accounts_test_' + uuid4().hex
    control = create_engine(url, hide_parameters=True)
    with control.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(url, hide_parameters=True, pool_size=8, max_overflow=0,
        connect_args={'options': f'-c search_path={schema} -c statement_timeout=10000'})
    settings = Settings(object_storage_root=str(tmp_path/'evidence'), environment='development', enable_development_tools=True,
        db_host=url.host, db_port=url.port or 5432, db_name=url.database,
        db_user=url.username, db_password=url.password, allowed_hosts=['testserver'],
        allowed_origins=['http://testserver'])
    db = Database(settings, engine=engine)
    config = migration_config()
    with engine.begin() as connection:
        config.attributes['connection'] = connection
        command.upgrade(config, '0001_foundation')
        from app.system.service import MARKER_NAME
        connection.execute(text("INSERT INTO development_markers (id,name) VALUES (:id,:name)"),
            {"id": uuid4(), "name": MARKER_NAME})
        command.upgrade(config, 'head')
    try:
        yield settings, db
    finally:
        db.dispose()
        with control.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        control.dispose()


def browser(settings, db):
    # Not entering lifespan avoids disposing an engine shared by other clients.
    return TestClient(create_app(settings, db), raise_server_exceptions=False)


def test_native_migration_preserves_foundation_and_repeats(pg_accounts):
    _, db = pg_accounts
    from app.db.development import seed_marker
    from app.system.service import system_status
    first = seed_marker(db)
    with db.engine.begin() as connection:
        config = migration_config(); config.attributes['connection'] = connection
        command.upgrade(config, 'head')
        assert connection.execute(text('SELECT version_num FROM alembic_version')).scalar_one() == expected_revision()
    assert system_status(db).persistence.marker_id == first


def test_native_audit_trigger_and_scoped_foreign_key(pg_accounts):
    settings, db = pg_accounts
    with browser(settings, db) as client:
        owner = bootstrap(client, db)
        with db.session() as session:
            event_id = session.scalar(select(AuditEvent.id).where(AuditEvent.workspace_id == owner['workspace']['id']))
        for sql in ['UPDATE audit_events SET reason = :reason WHERE id = :id', 'DELETE FROM audit_events WHERE id = :id']:
            with pytest.raises(DBAPIError), db.engine.begin() as connection:
                connection.execute(text(sql), {'id': event_id, 'reason': 'Unauthorized rewrite'})
        with pytest.raises(DBAPIError), db.engine.begin() as connection:
            connection.execute(text('INSERT INTO project_memberships (workspace_id, project_id, user_id, role, status, version) VALUES (:w,:p,:u,\'viewer\',\'active\',1)'),
                {'w': uuid4(), 'p': owner['project']['id'], 'u': owner['user']['id']})


def test_native_concurrent_bootstrap_has_one_owner(pg_accounts):
    settings, db = pg_accounts
    token = setup_token(db); barrier = Barrier(2)
    def attempt(index):
        client = browser(settings, db)
        try:
            state = client.get('/api/v1/auth/session').json(); barrier.wait(timeout=10)
            return client.post('/api/v1/auth/bootstrap', headers={'Origin': 'http://testserver', 'X-CSRF-Token': state['csrf_token']}, json={
                'token': token, 'email': f'owner{index}@example.test', 'display_name': f'Owner {index}',
                'password': PASSWORD, 'workspace_name': 'Concurrent workspace', 'project_name': 'Concurrent game'}).status_code
        finally: client.close()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, [1, 2]))
    assert sorted(results) == [200, 400]
    with db.session() as session: assert session.scalar(select(func.count()).select_from(User)) == 1


def test_native_invitation_consumes_once_under_race(pg_accounts):
    settings, db = pg_accounts
    owner_client = browser(settings, db)
    owner = bootstrap(owner_client, db)
    item = invite(owner_client, owner['workspace']['id']); owner_client.close()
    barrier = Barrier(2)
    def accept_one(_):
        client = browser(settings, db)
        try:
            state = client.get('/api/v1/auth/session').json(); barrier.wait(timeout=10)
            return client.post('/api/v1/auth/invitations/accept', headers={'Origin': 'http://testserver', 'X-CSRF-Token': state['csrf_token']},
                json={'token': item['token'], 'display_name': 'Invited person', 'password': PASSWORD}).status_code
        finally: client.close()
    with ThreadPoolExecutor(max_workers=2) as pool: results = list(pool.map(accept_one, [1, 2]))
    assert sorted(results) == [200, 400]
    with db.session() as session:
        assert session.scalar(select(func.count()).select_from(User).where(User.email == 'member@example.test')) == 1


def test_native_concurrent_last_owner_changes_are_serialized(pg_accounts):
    settings, db = pg_accounts
    owner_client = browser(settings, db); owner = bootstrap(owner_client, db)
    item = invite(owner_client, owner['workspace']['id']); second = browser(settings, db)
    accepted = mutation(second, '/api/v1/auth/invitations/accept', {'token': item['token'], 'display_name': 'Second owner', 'password': PASSWORD})
    assert accepted.status_code == 200
    second_id = accepted.json()['user']['id']; workspace_id = owner['workspace']['id']
    promoted = mutation(owner_client, f'/api/v1/workspaces/{workspace_id}/members/{second_id}',
        {'expected_version': 1, 'role': 'owner', 'status': 'active', 'reason': 'Add a second synthetic owner'}, method='patch')
    assert promoted.status_code == 200
    barrier = Barrier(2)
    def demote(item):
        client, user_id, version = item
        state = client.get('/api/v1/auth/session').json(); barrier.wait(timeout=10)
        return client.patch(f'/api/v1/workspaces/{workspace_id}/members/{user_id}',
            headers={'Origin': 'http://testserver', 'X-CSRF-Token': state['csrf_token']},
            json={'expected_version': version, 'role': 'member', 'status': 'active', 'reason': 'Voluntarily remove owner authority'}).status_code
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(demote, [(owner_client, owner['user']['id'], 1), (second, second_id, 2)]))
        assert sorted(results) == [200, 409]
        with db.session() as session:
            assert session.scalar(select(func.count()).select_from(WorkspaceMembership).where(
                WorkspaceMembership.workspace_id == workspace_id, WorkspaceMembership.role == 'owner', WorkspaceMembership.status == 'active')) == 1
    finally:
        owner_client.close(); second.close()
