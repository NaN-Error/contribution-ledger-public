import pytest
from sqlalchemy import create_engine, select
from alembic import command
from app.db.development import RESET_CONFIRMATION, reset_marker, seed_marker
from app.db.migration import migration_config
from app.db.models import DevelopmentMarker
from app.db.session import Database
from app.system.service import system_status


def test_seed_is_idempotent(database):
    first = seed_marker(database)
    second = seed_marker(database)
    assert first == second
    with database.session() as session:
        assert len(session.execute(select(DevelopmentMarker)).all()) == 1


@pytest.mark.parametrize("environment", ["test", "staging", "production"])
def test_seed_and_reset_refuse_non_development(database, environment):
    database.settings = database.settings.model_copy(update={"environment": environment})
    with pytest.raises(PermissionError): seed_marker(database)
    with pytest.raises(PermissionError): reset_marker(database, RESET_CONFIRMATION)


def test_development_tools_must_be_explicitly_enabled(database):
    database.settings = database.settings.model_copy(update={"enable_development_tools": False})
    with pytest.raises(PermissionError): seed_marker(database)
    with pytest.raises(PermissionError): reset_marker(database, RESET_CONFIRMATION)


def test_wrong_reset_confirmation_preserves_marker(database):
    first = seed_marker(database)
    with pytest.raises(PermissionError): reset_marker(database, "yes")
    assert system_status(database).persistence.marker_id == first


def test_reset_only_deletes_the_synthetic_marker(database):
    from uuid import uuid4
    first = seed_marker(database)
    with database.session() as session, session.begin():
        session.add(DevelopmentMarker(id=uuid4(), name="different-future-test"))
    assert reset_marker(database, RESET_CONFIRMATION) == 1
    assert reset_marker(database, RESET_CONFIRMATION) == 0
    with database.session() as session:
        records = session.execute(select(DevelopmentMarker)).scalars().all()
        assert len(records) == 1
        assert records[0].name == "different-future-test"
    assert seed_marker(database) != first


def test_seed_requires_current_migrations(database):
    from sqlalchemy import text
    with database.engine.begin() as connection:
        connection.execute(text("UPDATE alembic_version SET version_num='old'"))
    with pytest.raises(RuntimeError): seed_marker(database)


def test_file_backed_test_record_survives_engine_restart(settings, tmp_path):
    # This is a SQLite-backed process-independent storage test, not a container/PG restart test.
    url = f"sqlite:///{tmp_path / 'unit-test.db'}"
    one = Database(settings, create_engine(url))
    config = migration_config()
    with one.engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
    marker = seed_marker(one)
    one.dispose()
    two = Database(settings, create_engine(url))
    try: assert system_status(two).persistence.marker_id == marker
    finally: two.dispose()
