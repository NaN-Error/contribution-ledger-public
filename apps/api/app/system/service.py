from datetime import datetime, timezone
import logging
from sqlalchemy import inspect, select, text
from app.core.config import BUILD_VERSION
from app.db.migration import expected_revision
from app.db.models import DevelopmentMarker
from app.db.session import Database
from app.system.schemas import DatabaseHealth, MigrationHealth, PersistenceHealth, SystemStatus

MARKER_NAME = "phase1-persistence"


def system_status(database: Database) -> SystemStatus:
    settings = database.settings
    result = SystemStatus(
        status="degraded", environment=settings.environment, version=BUILD_VERSION,
        checked_at=datetime.now(timezone.utc),
        database=DatabaseHealth(status="unavailable", message="Database check did not complete."),
        migrations=MigrationHealth(status="unavailable", expected_revision=expected_revision()),
        persistence=PersistenceHealth(status="unavailable"),
        development_tools_enabled=(settings.environment == "development" and settings.enable_development_tools),
    )
    try:
        with database.engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            result.database = DatabaseHealth(status="ok", message="PostgreSQL connection is responding.")
            inspector = inspect(connection)
            if inspector.has_table("alembic_version"):
                revisions = list(connection.execute(text("SELECT version_num FROM alembic_version")).scalars())
            else:
                revisions = []
            result.migrations.current_revision = revisions[0] if len(revisions) == 1 else None
            if revisions != [expected_revision()] or not inspector.has_table("development_markers"):
                result.migrations.status = "pending"
                return result
            result.migrations.status = "current"
            row = connection.execute(select(DevelopmentMarker.id, DevelopmentMarker.created_at)
                .where(DevelopmentMarker.name == MARKER_NAME)).first()
            if row is None:
                result.persistence = PersistenceHealth(status="empty")
            else:
                created_at = row.created_at
                if created_at.tzinfo is None:
                    created_at = created_at.replace(tzinfo=timezone.utc)
                result.persistence = PersistenceHealth(status="present", marker_id=row.id, created_at=created_at)
            result.status = "ready"
    except Exception as exc:
        # Database/driver errors can contain connection strings. Log only the exception class.
        logging.getLogger("contribution_ledger").warning("database_check_failed", extra={
            "event": "database_check_failed", "error_type": type(exc).__name__})
        result.database = DatabaseHealth(status="unavailable", message="Database is unavailable. Check service logs and configuration.")
        result.migrations.status = "unavailable"
        result.persistence = PersistenceHealth(status="unavailable")
    return result
