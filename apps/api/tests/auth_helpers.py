from contextlib import contextmanager
from fastapi.testclient import TestClient
from app.auth.operator import setup_token
from app.main import create_app

PASSWORD = "Synthetic long password phrase 2026!"


def mutation(client, path, body=None, method="post", **kwargs):
    state = client.get("/api/v1/auth/session").json()
    return client.request(method.upper(), path, json=body or {},
        headers={"Origin": "http://testserver", "X-CSRF-Token": state["csrf_token"]}, **kwargs)


def bootstrap(client, database):
    token = setup_token(database)
    response = mutation(client, "/api/v1/auth/bootstrap", {"token": token,
        "email": "owner@example.test", "display_name": "Test owner", "password": PASSWORD,
        "workspace_name": "First workspace", "project_name": "First game"})
    assert response.status_code == 200, response.text
    workspace = client.get("/api/v1/workspaces").json()["items"][0]
    project = client.get(f"/api/v1/workspaces/{workspace['id']}/projects").json()["items"][0]
    return {"user": response.json()["user"], "workspace": workspace, "project": project, "token": token}


@contextmanager
def other_client(settings, database):
    # Don't dispose the shared test-only engine by entering another lifespan.
    client = TestClient(create_app(settings, database), raise_server_exceptions=True)
    try:
        yield client
    finally:
        client.close()


def invite(client, workspace_id, email="member@example.test", project_id=None, role="contributor", workspace_role="member"):
    body = {"email": email, "workspace_role": workspace_role, "reason": "Invite synthetic collaborator"}
    if project_id:
        body.update(project_id=project_id, project_role=role)
    response = mutation(client, f"/api/v1/workspaces/{workspace_id}/invitations", body)
    assert response.status_code == 201, response.text
    return response.json()


def accept(client, token, name="Synthetic member"):
    response = mutation(client, "/api/v1/auth/invitations/accept", {
        "token": token, "display_name": name, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return response.json()["user"]


def login(client, email="owner@example.test", password=PASSWORD):
    return mutation(client, "/api/v1/auth/login", {"email": email, "password": password})
