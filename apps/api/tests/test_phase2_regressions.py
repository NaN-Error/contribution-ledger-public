"""Small cross-feature regressions found during phase-2 review."""
from uuid import uuid4
from app.projects.models import Workspace, WorkspaceMembership
from tests.auth_helpers import bootstrap, mutation, invite, accept, other_client


def test_audit_reason_requires_content_after_trimming(client, database):
    owner = bootstrap(client, database)
    response = mutation(client, f"/api/v1/workspaces/{owner['workspace']['id']}/members/{owner['user']['id']}",
        {"expected_version": 1, "role": "owner", "status": "active", "reason": " " * 20}, method="patch")
    assert response.status_code == 422


def test_membership_cap_applies_to_invitations_and_creation(client, database, settings):
    owner = bootstrap(client, database)
    initial = invite(client, owner['workspace']['id'])
    with other_client(settings, database) as second:
        accept(second, initial['token'])
        other = mutation(second, '/api/v1/workspaces', {"name": "Separate workspace"}).json()
        invitation = invite(second, other['id'], email='owner@example.test')
        with database.session() as db:
            scopes = [Workspace(id=uuid4(), name=f"Synthetic cap scope {i}") for i in range(99)]
            db.add_all(scopes); db.flush()
            from uuid import UUID
            db.add_all([WorkspaceMembership(workspace_id=w.id, user_id=UUID(owner['user']['id']), role='member') for w in scopes])
            db.commit()
        rejected = mutation(client, '/api/v1/workspaces', {"name": "Over the cap"})
        assert rejected.status_code == 409 and rejected.json()['error']['code'] == 'workspace_limit'
        rejected = mutation(client, '/api/v1/auth/invitations/accept', {"token": invitation['token']})
        assert rejected.status_code == 409 and rejected.json()['error']['code'] == 'workspace_limit'
        assert len(client.get('/api/v1/workspaces').json()['items']) == 100
