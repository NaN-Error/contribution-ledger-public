from functools import lru_cache
from contextlib import contextmanager
from pathlib import Path
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text

API_ROOT = Path(__file__).resolve().parents[2]


@contextmanager
def migration_statement_timeout(connection):
    """Bound operator DDL to five minutes; retain the caller's query deadline."""
    if connection.dialect.name != "postgresql":
        yield
        return
    # A savepoint restores SET LOCAL on failure, including an aborted statement.
    # Successful migrations restore the previous value before returning control.
    with connection.begin_nested():
        previous = connection.execute(text("SHOW statement_timeout")).scalar_one()
        connection.execute(text("SET LOCAL statement_timeout = '5min'"))
        yield
        connection.execute(text("SELECT set_config('statement_timeout', :previous, true)"),
                           {"previous": previous})


def migration_config() -> Config:
    config = Config(str(API_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(API_ROOT / "migrations"))
    return config


@lru_cache
def expected_revision() -> str:
    revision = ScriptDirectory.from_config(migration_config()).get_current_head()
    if revision is None:
        raise RuntimeError("A baseline migration is required.")
    return revision
