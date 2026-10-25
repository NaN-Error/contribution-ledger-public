from alembic import context
from sqlalchemy import text
from app.core.config import get_settings
from app.db.base import Base
from app.db import models  # noqa: F401 - registers metadata
from app.db.session import Database
from app.db.migration import migration_statement_timeout


def run_offline() -> None:
    # PostgreSQL SQL generation requires no server or driver import.
    context.configure(url=get_settings().database_url(), target_metadata=Base.metadata,
                      literal_binds=True, dialect_opts={"paramstyle": "named"}, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


def run_online() -> None:
    supplied = context.config.attributes.get("connection")
    if supplied is not None:
        with migration_statement_timeout(supplied):
            context.configure(connection=supplied, target_metadata=Base.metadata, compare_type=True)
            with context.begin_transaction():
                context.run_migrations()
        return
    database = Database(get_settings())
    try:
        with database.engine.begin() as connection:
            with migration_statement_timeout(connection):
                # Serializes concurrent migration operators within this database.
                connection.execute(text("SELECT pg_advisory_xact_lock(721837001)"))
                context.configure(connection=connection, target_metadata=Base.metadata, compare_type=True)
                with context.begin_transaction():
                    context.run_migrations()
    finally:
        database.dispose()


run_offline() if context.is_offline_mode() else run_online()
