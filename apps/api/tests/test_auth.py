from datetime import timedelta
from uuid import UUID
import pytest
from sqlalchemy import select, func, update
from pydantic import ValidationError
from app.auth.models import BrowserSession, User, RecoveryToken, InstallationState
from app.auth.operator import setup_token, recovery_token, set_account_active, seed_team
from app.auth.schemas import PasswordInput
from app.core.config import Settings
from app.core.errors import ApiError
from app.security.passwords import password_hasher
from app.security.tokens import now, token_hash
from app.projects.models import WorkspaceMembership, AuditEvent
from tests.auth_helpers import bootstrap, mutation, other_client, invite, accept, login, PASSWORD


def test_first_owner_setup_and_hashed_tokens(client, database):
    anonymous = client.get("/api/v1/auth/session")
    old_cookie = client.cookies.get(database.settings.session_cookie_name)
    assert anonymous.json()["bootstrap_required"] and anonymous.json()["user"] is None
    assert "HttpOnly" in anonymous.headers["set-cookie"]
    assert "SameSite=lax" in anonymous.headers["set-cookie"]
    data = bootstrap(client, database)
    assert old_cookie != client.cookies.get(database.settings.session_cookie_name)
    with database.session() as db:
        user = db.get(User, UUID(data["user"]["id"]))
        assert user.password_hash.startswith("$argon2id$") and PASSWORD not in user.password_hash
        assert password_hasher().verify(user.password_hash, PASSWORD)
        state = db.get(InstallationState, 1)
        assert state.bootstrap_token_hash is None and state.bootstrap_expires_at is None
        assert db.scalar(select(BrowserSession).where(BrowserSession.token_hash == token_hash(old_cookie, "session"))).revoked_at
        assert db.scalar(select(BrowserSession).where(BrowserSession.token_hash == client.cookies.get(database.settings.session_cookie_name))) is None
    with pytest.raises(ApiError, match="setup_complete"):
        setup_token(database)


def test_invalid_and_expired_bootstrap_do_not_create_user(client, database):
    token = setup_token(database)
    with database.session() as db:
        db.get(InstallationState, 1).bootstrap_expires_at = now() - timedelta(seconds=1)
        db.commit()
    response = mutation(client, "/api/v1/auth/bootstrap", {"token": token,
        "email": "owner@example.test", "display_name": "Test owner", "password": PASSWORD,
        "workspace_name": "Workspace", "project_name": "Game"})
    assert response.status_code == 400
    with database.session() as db:
        assert db.scalar(select(func.count()).select_from(User)) == 0


def test_bootstrap_rotation_invalidates_earlier_token(client, database):
    first, second = setup_token(database), setup_token(database)
    with database.session() as db:
        assert db.get(InstallationState, 1).bootstrap_token_hash == token_hash(second, "bootstrap")
        assert db.get(InstallationState, 1).bootstrap_token_hash != token_hash(first, "bootstrap")


def test_logout_revokes_old_session(client, database):
    bootstrap(client, database)
    token = client.cookies.get(database.settings.session_cookie_name)
    assert mutation(client, "/api/v1/auth/logout").status_code == 200
    client.cookies.set(database.settings.session_cookie_name, token)
    assert client.get("/api/v1/workspaces").status_code == 401


@pytest.mark.parametrize("field", ["expires_at", "last_seen_at", "revoked_at"])
def test_expired_idle_and_revoked_sessions_fail(client, database, field):
    bootstrap(client, database)
    with database.session() as db:
        session = db.scalar(select(BrowserSession).where(BrowserSession.user_id.is_not(None)))
        setattr(session, field, now() - timedelta(hours=24))
        db.commit()
    assert client.get("/api/v1/workspaces").status_code == 401


def test_session_status_poll_does_not_extend_idle(client, database):
    bootstrap(client, database)
    with database.session() as db:
        session = db.scalar(select(BrowserSession).where(BrowserSession.user_id.is_not(None)))
        old = now() - timedelta(minutes=10)
        session.last_seen_at = old; db.commit(); identity = session.id
    client.get("/api/v1/auth/session")
    with database.session() as db:
        assert db.get(BrowserSession, identity).last_seen_at.replace(tzinfo=old.tzinfo) == old


def test_login_errors_do_not_reveal_account_exists(client, database):
    bootstrap(client, database)
    mutation(client, "/api/v1/auth/logout")
    one = login(client, password="incorrect password")
    two = login(client, email="absent@example.test", password="incorrect password")
    assert one.status_code == two.status_code == 401
    assert one.json()["error"]["code"] == two.json()["error"]["code"] == "invalid_credentials"
    assert one.json()["error"]["message"] == two.json()["error"]["message"]
    assert login(client).status_code == 200


def test_login_throttle_is_database_backed(client, database):
    bootstrap(client, database)
    mutation(client, "/api/v1/auth/logout")
    for _ in range(database.settings.login_account_limit):
        assert login(client, password="wrong password").status_code == 401
    blocked = login(client)
    assert blocked.status_code == 429 and blocked.headers["Retry-After"] == "900"


def test_csrf_and_origin_guards(client, database):
    bootstrap(client, database)
    state = client.get("/api/v1/auth/session").json()
    path = "/api/v1/workspaces"
    for headers in ({}, {"Origin": "http://testserver"},
        {"Origin": "https://attacker.invalid", "X-CSRF-Token": state["csrf_token"]},
        {"Origin": "http://testserver", "X-CSRF-Token": "forged"},
        {"Origin": "http://testserver", "X-CSRF-Token": state["csrf_token"], "Sec-Fetch-Site": "cross-site"}):
        assert client.post(path, json={"name": "Unauthorized workspace"}, headers=headers).status_code == 403
    assert mutation(client, path, {"name": "Allowed workspace"}).status_code == 201


def test_csrf_cannot_be_reused_from_another_session(client, database, settings):
    bootstrap(client, database)
    with other_client(settings, database) as other:
        token = other.get("/api/v1/auth/session").json()["csrf_token"]
    response = client.post("/api/v1/workspaces", json={"name": "Bad request"}, headers={"Origin": "http://testserver", "X-CSRF-Token": token})
    assert response.status_code == 403


def test_login_protected_against_csrf_before_authentication(client):
    state = client.get("/api/v1/auth/session").json()
    assert state["user"] is None
    assert client.post("/api/v1/auth/login", json={"email": "a@example.test", "password": PASSWORD}, headers={"Origin": "http://testserver"}).status_code == 403


def test_body_size_and_content_type(client):
    assert client.post("/api/v1/auth/login", content="x", headers={"Origin": "http://testserver", "Content-Type": "text/plain"}).status_code == 415
    assert client.post("/api/v1/auth/login", json={"x": "x" * 70000}, headers={"Origin": "http://testserver"}).status_code == 413


def test_password_change_revokes_other_sessions(client, database, settings):
    bootstrap(client, database)
    with other_client(settings, database) as other:
        assert login(other).status_code == 200
        changed = mutation(client, "/api/v1/auth/password", {"current_password": PASSWORD, "password": "New synthetic password phrase!"})
        assert changed.status_code == 200
        assert other.get("/api/v1/workspaces").status_code == 401
        assert client.get("/api/v1/workspaces").status_code == 200
        assert login(other, password="New synthetic password phrase!").status_code == 200


def test_wrong_current_password_rejected(client, database):
    bootstrap(client, database)
    response = mutation(client, "/api/v1/auth/password", {"current_password": "wrong password", "password": "New synthetic password phrase!"})
    assert response.status_code == 400


def test_session_list_and_revoke_are_user_scoped(client, database, settings):
    info = bootstrap(client, database)
    invitation = invite(client, info["workspace"]["id"])
    current = client.get("/api/v1/auth/session").json()["session_id"]
    with other_client(settings, database) as other:
        accept(other, invitation["token"])
        response = mutation(other, f"/api/v1/auth/sessions/{current}", method="delete")
        assert response.status_code == 404
    own = client.get("/api/v1/auth/sessions").json()["items"]
    assert own[0]["current"] and "token_hash" not in own[0]
    assert mutation(client, f"/api/v1/auth/sessions/{current}", method="delete").status_code == 200
    assert client.get("/api/v1/workspaces").status_code == 401


def test_operator_recovery_invalidates_sessions_and_is_single_use(client, database):
    bootstrap(client, database)
    token = recovery_token(database, "owner@example.test", "Verified owner requested recovery")
    assert client.get("/api/v1/workspaces").status_code == 401
    response = mutation(client, "/api/v1/auth/recover", {"token": token, "password": "Recovered synthetic passphrase!"})
    assert response.status_code == 200 and response.json()["user"] is None
    assert mutation(client, "/api/v1/auth/recover", {"token": token, "password": PASSWORD}).status_code == 400
    assert login(client, password="Recovered synthetic passphrase!").status_code == 200
    with database.session() as db:
        row = db.scalar(select(RecoveryToken))
        assert row.token_hash != token and row.consumed_at
        assert db.scalar(select(AuditEvent).where(AuditEvent.action == "operator.recovery_issued")).reason


def test_expired_recovery_rejected(client, database):
    bootstrap(client, database)
    token = recovery_token(database, "owner@example.test", "Synthetic recovery expiry case")
    with database.session() as db:
        db.scalar(select(RecoveryToken)).expires_at = now() - timedelta(seconds=1); db.commit()
    assert mutation(client, "/api/v1/auth/recover", {"token": token, "password": PASSWORD}).status_code == 400


def test_disabled_user_fails_and_history_is_preserved(client, database, settings):
    info = bootstrap(client, database)
    invitation = invite(client, info["workspace"]["id"])
    with other_client(settings, database) as other:
        user = accept(other, invitation["token"])
        set_account_active(database, user["email"], False, "Disable synthetic account for test")
        assert other.get("/api/v1/workspaces").status_code == 401
        with pytest.raises(ApiError):
            recovery_token(database, user["email"], "Recovery must not enable account")
        assert login(other, user["email"]).status_code == 401
        with database.session() as db:
            assert db.get(User, UUID(user["id"])) is not None
            assert db.get(WorkspaceMembership, (UUID(info["workspace"]["id"]), UUID(user["id"]))) is not None
        set_account_active(database, user["email"], True, "Restore synthetic account for test")
        assert login(other, user["email"]).status_code == 200


def test_last_owner_cannot_be_disabled(client, database):
    bootstrap(client, database)
    with pytest.raises(ApiError, match="last_owner"):
        set_account_active(database, "owner@example.test", False, "Attempt unsafe last-owner removal")


def test_secret_values_not_in_audit(client, database):
    info = bootstrap(client, database)
    secret = invite(client, info["workspace"]["id"])["token"]
    with database.session() as db:
        rows = list(db.scalars(select(AuditEvent)))
        text = str([(r.action, r.reason, r.details) for r in rows])
    assert secret not in text and PASSWORD not in text and info["token"] not in text


@pytest.mark.parametrize("password", ["short", " " * 20, "x" * 129])
def test_password_policy_rejects_invalid_values(password):
    with pytest.raises(ValidationError): PasswordInput(password=password)


def test_secure_cookie_configuration_and_remote_guard(settings, database):
    from fastapi.testclient import TestClient
    from app.main import create_app
    secure = settings.model_copy(update={"secure_cookies": True, "allowed_origins": ["https://testserver"]})
    local = TestClient(create_app(secure, database), base_url="https://testserver")
    response = local.get("/api/v1/auth/session")
    assert "__Host-cl_session=" in response.headers["set-cookie"]
    assert "Secure" in response.headers["set-cookie"] and "Domain=" not in response.headers["set-cookie"]
    local.close()
    with pytest.raises(ValidationError): Settings(environment="production", db_password="synthetic-long-password")


def test_optional_synthetic_team_is_explicit_and_not_repeatable(client, database):
    bootstrap(client, database)
    with pytest.raises(PermissionError): seed_team(database, "no")
    fixture = seed_team(database, "CREATE SYNTHETIC TEAM")
    assert len(fixture["accounts"]) == 8 and fixture["workspace_a"] != fixture["workspace_b"]
    with pytest.raises(ApiError, match="demo_exists"): seed_team(database, "CREATE SYNTHETIC TEAM")
