"""Real PostgreSQL integration: never silently replace these with SQLite."""
import os
import pytest
from alembic import command
from sqlalchemy.engine import make_url
from sqlalchemy import text
from app.core.config import Settings
from app.db.session import Database
from app.db.migration import migration_config
from app.db.development import seed_marker, reset_marker, RESET_CONFIRMATION
from app.system.service import system_status

pytestmark = pytest.mark.postgres


@pytest.fixture
def postgres_database():
    value = os.environ.get("CL_TEST_DATABASE_URL")
    if not value:
        pytest.skip("CL_TEST_DATABASE_URL is not configured; a real disposable PostgreSQL database is required.")
    url = make_url(value)
    if not url.drivername.startswith("postgresql") or not url.database or not url.database.endswith("_test"):
        pytest.fail("Integration tests require a PostgreSQL database whose name ends in _test.")
    settings = Settings(environment="development", enable_development_tools=True,
        db_host=url.host, db_port=url.port or 5432, db_user=url.username, db_password=url.password,
        db_name=url.database, allowed_hosts=["testserver", "localhost", "127.0.0.1"])
    database = Database(settings)
    config = migration_config()
    with database.engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
        command.upgrade(config, "head")
    yield database
    reset_marker(database, RESET_CONFIRMATION)
    database.dispose()


def test_real_postgres_migration_and_seed(postgres_database):
    first = seed_marker(postgres_database)
    assert seed_marker(postgres_database) == first
    assert system_status(postgres_database).status == "ready"
    with postgres_database.engine.connect() as connection:
        assert connection.execute(text("SELECT pg_typeof(id)::text FROM development_markers LIMIT 1")).scalar_one() == "uuid"


def test_real_postgres_persistence_after_new_engine(postgres_database):
    first = seed_marker(postgres_database)
    postgres_database.dispose()
    another = Database(postgres_database.settings)
    try: assert system_status(another).persistence.marker_id == first
    finally: another.dispose()


def test_real_postgres_connection_failure_returns_unavailable(postgres_database):
    settings = postgres_database.settings.model_copy(update={"db_host": "127.0.0.1", "db_port": 1})
    unavailable = Database(settings)
    try:
        result = system_status(unavailable)
        assert result.status == "degraded"
        assert result.database.status == "unavailable"
    finally: unavailable.dispose()


def test_operator_timeout_allows_slow_statements_and_restores_runtime_limit(postgres_database):
    from app.db.migration import migration_statement_timeout
    with postgres_database.engine.begin() as connection:
        assert connection.execute(text("SHOW statement_timeout")).scalar_one() == "3s"
        with migration_statement_timeout(connection):
            connection.execute(text("SELECT pg_sleep(3.25)"))
        assert connection.execute(text("SHOW statement_timeout")).scalar_one() == "3s"


def test_operator_timeout_restores_caller_after_failed_statement(postgres_database):
    from sqlalchemy.exc import DBAPIError
    from app.db.migration import migration_statement_timeout
    with postgres_database.engine.begin() as connection:
        with pytest.raises(DBAPIError):
            with migration_statement_timeout(connection):
                connection.execute(text("SELECT 1 / 0"))
        assert connection.execute(text("SHOW statement_timeout")).scalar_one() == "3s"
        assert connection.execute(text("SELECT 1")).scalar_one() == 1


def test_owned_migration_waits_past_runtime_deadline_without_changing_it(postgres_database, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from time import monotonic, sleep
    from app.core.config import get_settings
    settings = postgres_database.settings
    for key, value in {"CL_ENVIRONMENT": "development", "CL_DB_HOST": settings.db_host,
            "CL_DB_PORT": str(settings.db_port), "CL_DB_NAME": settings.db_name,
            "CL_DB_USER": settings.db_user, "CL_DB_PASSWORD": settings.db_password.get_secret_value()}.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            with postgres_database.engine.begin() as connection:
                connection.execute(text("SELECT pg_advisory_xact_lock(721837001)"))
                future = pool.submit(command.upgrade, migration_config(), "head")
                deadline = monotonic() + 30
                while True:
                    connection.execute(text("SELECT pg_stat_clear_snapshot()"))
                    waiting = connection.execute(text("SELECT EXISTS (SELECT 1 FROM pg_stat_activity "
                        "WHERE datname = current_database() AND wait_event_type = 'Lock' "
                        "AND query LIKE '%pg_advisory_xact_lock(721837001)%')")).scalar_one()
                    if waiting:
                        break
                    assert monotonic() < deadline and not future.done(), "Migration operator did not reach the held lock."
                    sleep(0.05)
                sleep(4)
            future.result(timeout=60)
        with postgres_database.engine.connect() as connection:
            assert connection.execute(text("SHOW statement_timeout")).scalar_one() == "3s"
    finally:
        get_settings.cache_clear()
