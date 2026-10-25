from io import StringIO
from alembic import command
from sqlalchemy import inspect
from app.db.migration import expected_revision, migration_config


def test_migration_is_repeatable(database):
    config = migration_config()
    with database.engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
        command.upgrade(config, "head")
        assert inspect(connection).has_table("development_markers")


def test_postgresql_offline_sql_is_generated(monkeypatch):
    from app.core.config import get_settings
    monkeypatch.setenv("CL_DB_PASSWORD", "synthetic-test-password-not-a-secret")
    get_settings.cache_clear()
    try:
        config = migration_config()
        output = StringIO()
        config.output_buffer = output
        command.upgrade(config, "head", sql=True)
        sql = output.getvalue()
        assert "CREATE TABLE development_markers" in sql
        assert "UUID" in sql
        assert "TIMESTAMP WITH TIME ZONE" in sql
        assert expected_revision() in sql
        assert "synthetic-test-password" not in sql
    finally:
        get_settings.cache_clear()


def test_migrations_match_declared_metadata(database):
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext
    from app.db.base import Base
    with database.engine.connect() as connection:
        assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []
