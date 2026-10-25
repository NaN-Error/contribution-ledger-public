from datetime import timedelta
from uuid import UUID, uuid4
import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError, DBAPIError
from app.auth.models import User
from app.auth.service import revoke_all
from app.projects.models import ProjectMembership, WorkspaceMembership, Invitation, AuditEvent
from app.security.tokens import now
from app.projects.authorization import is_independent_reviewer
from tests.auth_helpers import bootstrap, mutation, other_client, invite, accept, PASSWORD, login


def test_workspace_and_project_creation(client, database):
    data = bootstrap(client, database)
    wid, pid = data["workspace"]["id"], data["project"]["id"]
    response = mutation(client, f"/api/v1/workspaces/{wid}/projects", {
        "name": "Second game", "timezone": "America/Puerto_Rico", "currency": "USD"})
    assert response.status_code == 201 and response.json()["timezone"] == "America/Puerto_Rico"
    assert len(client.get(f"/api/v1/workspaces/{wid}/projects").json()["items"]) == 2
    detail = client.get(f"/api/v1/workspaces/{wid}/projects/{pid}").json()
    assert detail["can_manage"] and detail["role"] == "admin"


@pytest.mark.parametrize("path", ["/members", "/projects", "/invitations", "/audit", ""])
def test_workspace_guesses_never_grant_access(client, database, settings, path):
    data = bootstrap(client, database)
    token = invite(client, data["workspace"]["id"])["token"]
    with other_client(settings, database) as other:
        accept(other, token)
        second = mutation(other, "/api/v1/workspaces", {"name": "Other workspace"}).json()
        assert client.get(f"/api/v1/workspaces/{second['id']}{path}").status_code == 404
        assert second["id"] not in [w["id"] for w in client.get("/api/v1/workspaces").json()["items"]]


@pytest.mark.parametrize("operation", ["project_create", "invite", "workspace_member", "project_edit", "project_member_add", "project_member_edit", "invite_revoke"])
def test_cross_workspace_writes_are_denied(client, database, settings, operation):
    data = bootstrap(client, database)
    invitation = invite(client, data["workspace"]["id"])
    with other_client(settings, database) as other:
        user = accept(other, invitation["token"])
        w = mutation(other, "/api/v1/workspaces", {"name": "Other workspace"}).json()["id"]
        p = mutation(other, f"/api/v1/workspaces/{w}/projects", {"name": "Other project"}).json()["id"]
        base = f"/api/v1/workspaces/{w}"
        options = {
            "project_create": (base + "/projects", {"name": "Forbidden project"}, "post"),
            "invite": (base + "/invitations", {"email": "bad@example.test", "reason": "Cross workspace attempt"}, "post"),
            "workspace_member": (base + f"/members/{user['id']}", {"role": "member", "status": "active", "expected_version": 1, "reason": "Cross workspace attempt"}, "patch"),
            "project_edit": (base + f"/projects/{p}", {"name": "Forbidden edit", "expected_version": 1, "reason": "Cross workspace attempt"}, "patch"),
            "project_member_add": (base + f"/projects/{p}/members", {"user_id": data["user"]["id"], "role": "admin", "reason": "Cross workspace attempt"}, "post"),
            "project_member_edit": (base + f"/projects/{p}/members/{user['id']}", {"role": "admin", "status": "active", "expected_version": 1, "reason": "Cross workspace attempt"}, "patch"),
            "invite_revoke": (base + f"/invitations/{invitation['id']}", {"reason": "Cross workspace attempt"}, "delete"),
        }
        path, body, method = options[operation]
        assert mutation(client, path, body, method=method).status_code == 404
        # Even a valid accessible parent cannot be combined with a foreign project.
        assert client.get(f"/api/v1/workspaces/{data['workspace']['id']}/projects/{p}").status_code == 404


@pytest.mark.parametrize("role", ["viewer", "contributor", "reviewer", "finance"])
def test_non_admin_project_roles_are_read_only_for_access_management(client, database, settings, role):
    data = bootstrap(client, database)
    w, p = data["workspace"]["id"], data["project"]["id"]
    token = invite(client, w, project_id=p, role=role)["token"]
    with other_client(settings, database) as other:
        accept(other, token)
        response = other.get(f"/api/v1/workspaces/{w}/projects/{p}")
        assert response.status_code == 200 and response.json()["role"] == role and not response.json()["can_manage"]
        assert other.get(f"/api/v1/workspaces/{w}/members").status_code == 403
        assert other.get(f"/api/v1/workspaces/{w}/audit").status_code == 403
        assert mutation(other, f"/api/v1/workspaces/{w}/projects/{p}", {"name": "Forbidden edit", "expected_version": 1, "reason": "Unauthorized settings edit"}, method="patch").status_code == 403
        assert mutation(other, f"/api/v1/workspaces/{w}/invitations", {"email": "another@example.test", "reason": "Unauthorized invitation"}).status_code == 403


def test_unassigned_project_is_hidden_from_workspace_member(client, database, settings):
    data = bootstrap(client, database)
    invitation = invite(client, data["workspace"]["id"])
    with other_client(settings, database) as other:
        accept(other, invitation["token"])
        w, p = data["workspace"]["id"], data["project"]["id"]
        assert other.get(f"/api/v1/workspaces/{w}/projects").json()["items"] == []
        assert other.get(f"/api/v1/workspaces/{w}/projects/{p}").status_code == 404


def test_invitation_token_is_hashed_and_not_returned_from_lists(client, database):
    data = bootstrap(client, database)
    invitation = invite(client, data["workspace"]["id"])
    assert invitation["token"] not in client.get(f"/api/v1/workspaces/{data['workspace']['id']}/invitations").text
    with database.session() as db:
        assert db.get(Invitation, UUID(invitation["id"])).token_hash != invitation["token"]


def test_invitation_cannot_be_replayed(client, database, settings):
    data = bootstrap(client, database)
    token = invite(client, data["workspace"]["id"])["token"]
    with other_client(settings, database) as other:
        accept(other, token)
        assert mutation(other, "/api/v1/auth/invitations/accept", {"token": token}).status_code == 400


@pytest.mark.parametrize("condition", ["expired", "revoked", "superseded", "issuer_demoted", "issuer_disabled"])
def test_invalidated_invitations_cannot_be_accepted(client, database, settings, condition):
    data = bootstrap(client, database)
    invitation = invite(client, data["workspace"]["id"])
    with database.session() as db:
        record = db.get(Invitation, UUID(invitation["id"]))
        if condition == "expired": record.expires_at = now() - timedelta(seconds=1)
        if condition == "revoked": record.status = "revoked"
        if condition == "issuer_demoted": db.get(WorkspaceMembership, (UUID(data["workspace"]["id"]), UUID(data["user"]["id"]))).role = "member"
        if condition == "issuer_disabled": db.get(User, UUID(data["user"]["id"])).is_active = False
        db.commit()
    if condition == "superseded": invite(client, data["workspace"]["id"])
    with other_client(settings, database) as other:
        response = mutation(other, "/api/v1/auth/invitations/accept", {"token": invitation["token"], "display_name": "Blocked user", "password": PASSWORD})
        assert response.status_code == 400


def test_existing_account_requires_signin_and_cannot_reset_password_via_invite(client, database, settings):
    data = bootstrap(client, database)
    w = data["workspace"]["id"]
    with other_client(settings, database) as other:
        token = invite(client, w)["token"]
        accept(other, token)
        mutation(other, "/api/v1/auth/logout")
        second = mutation(client, "/api/v1/workspaces", {"name": "Another workspace"}).json()["id"]
        token = invite(client, second)["token"]
        assert mutation(other, "/api/v1/auth/invitations/accept", {"token": token, "password": "Attacker-selected password!", "display_name": "Wrong replacement"}).status_code == 403
        assert login(other, "member@example.test").status_code == 200
        accepted = mutation(other, "/api/v1/auth/invitations/accept", {"token": token})
        assert accepted.status_code == 200
        mutation(other, "/api/v1/auth/logout")
        assert login(other, "member@example.test", PASSWORD).status_code == 200


def test_project_settings_optimistic_version(client, database):
    data = bootstrap(client, database)
    path = f"/api/v1/workspaces/{data['workspace']['id']}/projects/{data['project']['id']}"
    payload = {"name": "Updated name", "expected_version": 1, "reason": "Rename synthetic project"}
    assert mutation(client, path, payload, method="patch").json()["version"] == 2
    assert mutation(client, path, payload, method="patch").status_code == 409


def test_last_owner_and_stale_membership_guard(client, database):
    data = bootstrap(client, database)
    path = f"/api/v1/workspaces/{data['workspace']['id']}/members/{data['user']['id']}"
    payload = {"role": "member", "status": "active", "expected_version": 1, "reason": "Unsafe owner removal"}
    assert mutation(client, path, payload, method="patch").json()["error"]["code"] == "last_owner"
    payload["expected_version"] = 999
    assert mutation(client, path, payload, method="patch").json()["error"]["code"] == "stale_version"


def test_workspace_suspend_revokes_access_and_preserves_identity(client, database, settings):
    data = bootstrap(client, database)
    w, p = data["workspace"]["id"], data["project"]["id"]
    token = invite(client, w, project_id=p)["token"]
    with other_client(settings, database) as other:
        user = accept(other, token)
        path = f"/api/v1/workspaces/{w}/members/{user['id']}"
        body = {"role": "member", "status": "suspended", "expected_version": 1, "reason": "Suspend synthetic member"}
        assert mutation(client, path, body, method="patch").status_code == 200
        assert other.get(f"/api/v1/workspaces/{w}/projects/{p}").status_code == 401
        assert login(other, user["email"]).status_code == 200
        assert other.get(f"/api/v1/workspaces/{w}/projects/{p}").status_code == 404
        body.update(status="active", expected_version=2)
        assert mutation(client, path, body, method="patch").status_code == 200
        # Workspace restoration alone must not restore the project grant.
        assert other.get(f"/api/v1/workspaces/{w}/projects/{p}").status_code == 404
        with database.session() as db:
            assert db.get(User, UUID(user["id"])) is not None
            assert db.get(ProjectMembership, (UUID(w), UUID(p), UUID(user["id"]))).status == "suspended"


def test_project_suspend_and_role_change_apply_to_existing_session(client, database, settings):
    data = bootstrap(client, database)
    w, p = data["workspace"]["id"], data["project"]["id"]
    token = invite(client, w, project_id=p)["token"]
    with other_client(settings, database) as other:
        user = accept(other, token)
        path = f"/api/v1/workspaces/{w}/projects/{p}/members/{user['id']}"
        body = {"role": "viewer", "status": "active", "expected_version": 1, "reason": "Change synthetic role"}
        assert mutation(client, path, body, method="patch").status_code == 200
        assert other.get(f"/api/v1/workspaces/{w}/projects/{p}").json()["role"] == "viewer"
        body.update(status="suspended", expected_version=2)
        assert mutation(client, path, body, method="patch").status_code == 200
        assert other.get(f"/api/v1/workspaces/{w}/projects/{p}").status_code == 404


def test_invitation_cannot_restore_suspended_workspace(client, database, settings):
    data = bootstrap(client, database)
    w = data["workspace"]["id"]
    token = invite(client, w)["token"]
    with other_client(settings, database) as other:
        user = accept(other, token)
    assert mutation(client, f"/api/v1/workspaces/{w}/members/{user['id']}",
        {"role": "member", "status": "suspended", "expected_version": 1, "reason": "Suspend synthetic member"}, method="patch").status_code == 200
    assert mutation(client, f"/api/v1/workspaces/{w}/invitations", {"email": user["email"], "reason": "Forbidden reactivation invite"}).status_code == 409


def test_workspace_admin_cannot_promote_self_to_owner(client, database, settings):
    data = bootstrap(client, database)
    w = data["workspace"]["id"]
    token = invite(client, w, workspace_role="admin")["token"]
    with other_client(settings, database) as other:
        user = accept(other, token)
        assert mutation(other, f"/api/v1/workspaces/{w}/members/{user['id']}",
            {"role": "owner", "status": "active", "expected_version": 1, "reason": "Unauthorized owner promotion"}, method="patch").status_code == 403
        assert mutation(other, f"/api/v1/workspaces/{w}/invitations", {"email": "new@example.test", "workspace_role": "admin", "reason": "Unauthorized administrator invite"}).status_code == 403


def test_foreign_keys_reject_cross_workspace_project_member(client, database, settings):
    data = bootstrap(client, database)
    token = invite(client, data["workspace"]["id"])["token"]
    with other_client(settings, database) as other:
        user = accept(other, token)
        other_w = mutation(other, "/api/v1/workspaces", {"name": "Other workspace"}).json()["id"]
        other_p = mutation(other, f"/api/v1/workspaces/{other_w}/projects", {"name": "Other project"}).json()["id"]
    with database.session() as db:
        db.add(ProjectMembership(workspace_id=UUID(data["workspace"]["id"]), project_id=UUID(other_p), user_id=UUID(user["id"]), role="viewer"))
        with pytest.raises(IntegrityError): db.commit()


@pytest.mark.parametrize("statement", ["UPDATE audit_events SET action='tampered'", "DELETE FROM audit_events"])
def test_audit_events_reject_update_and_delete(client, database, statement):
    bootstrap(client, database)
    with database.engine.begin() as connection:
        with pytest.raises(DBAPIError): connection.execute(text(statement))


def test_role_change_records_reason_without_mutating_old_audit(client, database, settings):
    data = bootstrap(client, database)
    token = invite(client, data["workspace"]["id"])["token"]
    with other_client(settings, database) as other: user = accept(other, token)
    mutation(client, f"/api/v1/workspaces/{data['workspace']['id']}/members/{user['id']}",
        {"role": "admin", "status": "active", "expected_version": 1, "reason": "Promote synthetic administrator"}, method="patch")
    items = client.get(f"/api/v1/workspaces/{data['workspace']['id']}/audit").json()["items"]
    row = next(item for item in items if item["action"] == "workspace.membership_changed")
    assert row["details"]["before"]["role"] == "member" and row["details"]["after"]["role"] == "admin"
    assert row["reason"] == "Promote synthetic administrator"


def test_review_independence_has_no_administrator_shortcut(client, database):
    data = bootstrap(client, database)
    owner = UUID(data["user"]["id"])
    assert not is_independent_reviewer(owner, {owner})
    assert is_independent_reviewer(uuid4(), {owner})


@pytest.mark.parametrize("path", ["/api/v1/workspaces", "/api/v1/auth/sessions"])
def test_anonymous_private_queries_are_denied(client, path):
    client.get("/api/v1/auth/session")
    assert client.get(path).status_code == 401


def test_mass_assignment_and_invalid_timezone_rejected(client, database):
    data = bootstrap(client, database)
    w = data["workspace"]["id"]
    assert mutation(client, "/api/v1/workspaces", {"name": "Mass assign", "owner_id": str(uuid4())}).status_code == 422
    assert mutation(client, f"/api/v1/workspaces/{w}/projects", {"name": "Invalid timezone", "timezone": "Not/AZone"}).status_code == 422
    assert mutation(client, f"/api/v1/workspaces/{w}/projects", {"name": "Unsupported currency", "currency": "EUR"}).status_code == 422
