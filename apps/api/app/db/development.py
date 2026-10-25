from uuid import UUID, uuid4
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from app.db.models import DevelopmentMarker
from app.db.session import Database
from app.system.service import MARKER_NAME, system_status

RESET_CONFIRMATION = "DELETE DEVELOPMENT RECORDS"


def seed_marker(database: Database) -> UUID:
    database.settings.require_development_tools()
    if system_status(database).status != "ready":
        raise RuntimeError("Database must be ready; apply migrations before seeding.")
    with database.session() as session, session.begin():
        # SQLite is used only by explicitly injected, in-process test engines.
        insert = pg_insert if session.bind.dialect.name == "postgresql" else sqlite_insert
        session.execute(insert(DevelopmentMarker).values(id=uuid4(), name=MARKER_NAME)
                        .on_conflict_do_nothing(index_elements=["name"]))
        return session.execute(select(DevelopmentMarker.id).where(DevelopmentMarker.name == MARKER_NAME)).scalar_one()


def reset_marker(database: Database, confirmation: str) -> int:
    database.settings.require_development_tools()
    if confirmation != RESET_CONFIRMATION:
        raise PermissionError("The exact development reset confirmation is required.")
    # Deliberately not a drop-all/reset-schema function. Future user data is untouched.
    with database.session() as session, session.begin():
        result = session.execute(delete(DevelopmentMarker).where(DevelopmentMarker.name == MARKER_NAME))
        return result.rowcount
