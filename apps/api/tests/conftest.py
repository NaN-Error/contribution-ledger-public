import pytest
from alembic import command
from sqlalchemy import create_engine, event
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient
from app.core.config import Settings
from app.db.migration import migration_config
from app.db.session import Database
from app.main import create_app


@pytest.fixture
def settings(tmp_path):
    return Settings(object_storage_root=str(tmp_path / "evidence"), environment="development", enable_development_tools=True,
                    db_password="synthetic-test-password-not-a-secret", allowed_hosts=["testserver", "localhost", "127.0.0.1"], allowed_origins=["http://testserver"])


@pytest.fixture
def database(settings):
    # SQLite exercises isolated application behavior, NOT PostgreSQL compatibility.
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    @event.listens_for(engine, "connect")
    def enforce_foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")
    config = migration_config()
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
    database = Database(settings, engine=engine)
    yield database
    database.dispose()


@pytest.fixture
def client(settings, database):
    with TestClient(create_app(settings, database), raise_server_exceptions=False) as client:
        yield client
