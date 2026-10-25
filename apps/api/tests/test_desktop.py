from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import select, func
from app.auth.desktop import DesktopProfile, desktop_ticket
from app.auth.models import User, InstallationState
from app.auth.mfa_models import Authenticator
from app.core.config import Settings
from app.core.errors import ApiError
from app.main import create_app
from app.projects.models import Workspace, Project
from app.security.tokens import now, token_hash
from tests.auth_helpers import bootstrap, mutation


def enable(settings):
    # TestClient injects its transport; production configuration is separately validated.
    settings.desktop_enabled=True


def test_disabled_desktop_never_creates_an_owner(client,database):
    with pytest.raises(ApiError,match='desktop_disabled'): desktop_ticket(database)
    assert mutation(client,'/api/v1/auth/desktop/login',{'token':'a'*43}).status_code==404
    with database.session() as db: assert db.scalar(select(func.count()).select_from(User))==0


def test_personal_initialization_rotation_and_restart_are_idempotent(client,database,settings):
    enable(settings)
    client.cookies.set('cl_session','a'*43)
    first=desktop_ticket(database);second=desktop_ticket(database)
    assert first!=second
    assert mutation(client,'/api/v1/auth/desktop/login',{'token':first}).status_code==400
    response=mutation(client,'/api/v1/auth/desktop/login',{'token':second})
    assert response.status_code==200,response.text
    assert response.json()['user']['display_name']=='Local user'
    assert not response.json()['bootstrap_required']
    assert client.cookies.get('cl_session')=='a'*43
    assert client.cookies.get('cl_desktop_session') is not None
    assert client.get('/api/v1/workspaces').json()['items'][0]['name']=='Personal workspace'
    with database.session() as db:
        assert db.scalar(select(func.count()).select_from(User))==1
        assert db.scalar(select(func.count()).select_from(Workspace))==1
        assert db.scalar(select(func.count()).select_from(Project))==1
        assert db.get(DesktopProfile,1).ticket_hash is None
        user_id=db.get(DesktopProfile,1).user_id
    third=desktop_ticket(database)
    assert mutation(client,'/api/v1/auth/desktop/login',{'token':third}).status_code==200
    with database.session() as db: assert db.get(DesktopProfile,1).user_id==user_id


def test_ticket_hash_expiry_replay_and_purpose_separation(client,database,settings):
    enable(settings);ticket=desktop_ticket(database)
    with database.session() as db:
        profile=db.get(DesktopProfile,1)
        assert profile.ticket_hash==token_hash(ticket,'desktop')
        assert profile.ticket_hash!=token_hash(ticket,'bootstrap')
        profile.ticket_expires_at=now()-timedelta(seconds=1);db.commit()
    assert mutation(client,'/api/v1/auth/desktop/login',{'token':ticket}).status_code==400
    ticket=desktop_ticket(database)
    assert mutation(client,'/api/v1/auth/desktop/login',{'token':ticket}).status_code==200
    assert mutation(client,'/api/v1/auth/desktop/login',{'token':ticket}).status_code==400


def test_existing_regular_owner_is_preserved_and_not_adopted(client,database,settings):
    owner=bootstrap(client,database)['user']['id'];enable(settings)
    with pytest.raises(ApiError,match='desktop_existing_owner'): desktop_ticket(database)
    with database.session() as db:
        assert str(db.get(InstallationState,1).owner_user_id)==owner
        assert db.get(DesktopProfile,1) is None
        assert db.scalar(select(func.count()).select_from(User))==1


def test_disabled_profile_cannot_be_recovered_by_start(client,database,settings):
    enable(settings);ticket=desktop_ticket(database)
    with database.session() as db:
        db.get(User,db.get(DesktopProfile,1).user_id).is_active=False;db.commit()
    with pytest.raises(ApiError,match='desktop_unavailable'): desktop_ticket(database)
    assert mutation(client,'/api/v1/auth/desktop/login',{'token':ticket}).status_code==400


def test_mfa_is_not_bypassed_by_desktop_ticket(client,database,settings):
    enable(settings);ticket=desktop_ticket(database);settings.require_mfa=True
    response=mutation(client,'/api/v1/auth/desktop/login',{'token':ticket})
    assert response.status_code==200,response.text
    assert response.json()['user'] is None and response.json()['mfa_required']
    assert client.get('/api/v1/workspaces').status_code==401


def test_csrf_and_cross_origin_protect_desktop_login(client,database,settings):
    enable(settings);ticket=desktop_ticket(database)
    session=client.get('/api/v1/auth/session').json()
    for headers in [{},{'Origin':'https://evil.invalid','X-CSRF-Token':session['csrf_token']},
                    {'Origin':'http://testserver','X-CSRF-Token':'forged'}]:
        assert client.post('/api/v1/auth/desktop/login',json={'token':ticket},headers=headers).status_code==403
    assert mutation(client,'/api/v1/auth/desktop/login',{'token':ticket}).status_code==200


@pytest.mark.parametrize('configuration',[
    {'allowed_origins':['http://remote.example:5173']}, {'allowed_hosts':['api']},
    {'environment':'staging','secure_cookies':True,'allowed_origins':['https://localhost']},
    {'environment':'production','secure_cookies':True,'allowed_origins':['https://localhost']},
])
def test_personal_mode_refuses_remote_or_staging_configuration(configuration):
    values=dict(desktop_enabled=True,db_password='synthetic-test-password-not-secret',
        allowed_hosts=['127.0.0.1'],allowed_origins=['http://127.0.0.1:5173'])
    values.update(configuration)
    with pytest.raises(ValidationError): Settings(**values)


@pytest.mark.postgres
def test_native_competing_ticket_consumption_is_single_use(pg_accounts):
    settings,database=pg_accounts;enable(settings);ticket=desktop_ticket(database)
    barrier=Barrier(2)
    def consume(_):
        client=TestClient(create_app(settings,database),raise_server_exceptions=True)
        try:
            session=client.get('/api/v1/auth/session').json();barrier.wait(timeout=10)
            return client.post('/api/v1/auth/desktop/login',json={'token':ticket},headers={
                'Origin':'http://testserver','X-CSRF-Token':session['csrf_token']}).status_code
        finally: client.close()
    with ThreadPoolExecutor(max_workers=2) as pool: assert sorted(pool.map(consume,[0,1]))==[200,400]
    with database.session() as db:
        assert db.scalar(select(func.count()).select_from(User))==1
        assert db.get(DesktopProfile,1).ticket_hash is None


from tests.test_postgres_accounts import pg_accounts  # noqa: E402,F401


@pytest.mark.postgres
def test_native_0017_upgrade_preserves_regular_owner_and_refuses_desktop_adoption(pg_accounts):
    from alembic import command
    from app.db.migration import migration_config
    from sqlalchemy import text
    settings,database=pg_accounts
    client=TestClient(create_app(settings,database),raise_server_exceptions=True)
    try:
        owner=bootstrap(client,database)['user']['id']
        with database.engine.begin() as connection:
            before=connection.execute(text('SELECT id,email,password_hash FROM users')).all()
            config=migration_config();config.attributes['connection']=connection
            command.downgrade(config,'0017_analysis_handoff')
            command.upgrade(config,'head');command.upgrade(config,'head')
            assert connection.execute(text('SELECT id,email,password_hash FROM users')).all()==before
            assert connection.execute(text('SELECT count(*) FROM desktop_profiles')).scalar_one()==0
        enable(settings)
        with pytest.raises(ApiError,match='desktop_existing_owner'):desktop_ticket(database)
        with database.session() as db:assert str(db.get(InstallationState,1).owner_user_id)==owner
    finally:client.close()
