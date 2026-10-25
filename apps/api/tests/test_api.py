import logging
import uuid
from fastapi.testclient import TestClient
from sqlalchemy import text
from app.main import create_app
from app.db.migration import expected_revision
from app.db.development import seed_marker


def test_liveness_is_independent_of_database(client, database):
    with database.engine.begin() as connection:
        connection.execute(text("DROP TABLE development_markers"))
    assert client.get("/health/live").status_code == 200
    assert client.get("/health/ready").status_code == 503


def test_readiness_reports_current_schema_and_empty_marker(client):
    response = client.get("/health/ready")
    assert response.status_code == 200
    assert response.json()["migrations"]["current_revision"] == expected_revision()
    assert response.json()["persistence"]["status"] == "empty"


def test_status_reports_real_marker(client, database):
    marker_id = seed_marker(database)
    body = client.get("/api/v1/system/status").json()
    assert body["status"] == "ready"
    assert body["persistence"]["marker_id"] == str(marker_id)


def test_wrong_revision_is_not_ready(client, database):
    with database.engine.begin() as connection:
        connection.execute(text("UPDATE alembic_version SET version_num = 'old_revision'"))
    response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.json()["migrations"]["status"] == "pending"


def test_missing_revision_table_is_not_ready(client, database):
    with database.engine.begin() as connection:
        connection.execute(text("DROP TABLE alembic_version"))
    assert client.get("/api/v1/system/status").json()["migrations"]["status"] == "pending"


def test_unavailable_database_is_sanitized(settings):
    class FailingDatabase:
        def __init__(self): self.settings = settings
        @property
        def engine(self): raise RuntimeError("password=never-print-this host=private")
        def dispose(self): pass
    with TestClient(create_app(settings, FailingDatabase()), raise_server_exceptions=False) as local:
        response = local.get("/api/v1/system/status")
        assert response.status_code == 503
        assert response.json()["database"]["status"] == "unavailable"
        assert "never-print-this" not in response.text
        assert local.get("/health/live").status_code == 200


def test_request_ids_and_cache_controls(client):
    identity = str(uuid.uuid4())
    response = client.get("/health/live", headers={"X-Request-ID": identity})
    assert response.headers["X-Request-ID"] == identity
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["X-Content-Type-Options"] == "nosniff"


def test_arbitrary_request_id_is_not_reflected(client):
    response = client.get("/health/live", headers={"X-Request-ID": "secret-not-an-identifier"})
    assert response.headers["X-Request-ID"] != "secret-not-an-identifier"
    uuid.UUID(response.headers["X-Request-ID"])


def test_error_routes_are_sanitized(client):
    response = client.get("/missing?token=never-echo")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
    assert "never-echo" not in response.text
    assert response.headers["X-Request-ID"] == response.json()["error"]["request_id"]


def test_no_seed_or_reset_http_mutations_exist(client):
    for path in ["/api/v1/system/seed", "/api/v1/system/reset", "/api/v1/system/status"]:
        response = client.post(path, json={}, headers={"Origin": "http://testserver"})
        assert response.status_code in {404, 405}


def test_unknown_host_is_rejected(client):
    assert client.get("/health/live", headers={"Host": "attacker.invalid"}).status_code == 400


def test_unexpected_error_is_sanitized(settings, database):
    app = create_app(settings, database)
    @app.get("/test-failure")
    def failure():
        raise RuntimeError("private-password-do-not-log")
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/test-failure")
    assert response.status_code == 500
    assert "private-password" not in response.text
    assert response.json()["error"]["code"] == "internal_error"
    assert response.headers["X-Request-ID"] == response.json()["error"]["request_id"]


def test_validation_inputs_are_not_echoed(settings, database):
    app = create_app(settings, database)
    @app.get("/test-validation")
    def validation(number: int):
        return {"number": number}
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/test-validation?number=secret-token")
    assert response.status_code == 422
    assert "secret-token" not in response.text


def test_openapi_has_versioned_status_route(client):
    schema = client.get("/openapi.json").json()
    assert "/api/v1/system/status" in schema["paths"]
    assert "503" in schema["paths"]["/api/v1/system/status"]["get"]["responses"]
