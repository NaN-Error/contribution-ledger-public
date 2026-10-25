from datetime import datetime
from typing import Literal
from uuid import UUID
from pydantic import BaseModel
from app.core.config import BUILD_VERSION


class DatabaseHealth(BaseModel):
    status: Literal["ok", "unavailable"]
    message: str


class MigrationHealth(BaseModel):
    status: Literal["current", "pending", "unavailable"]
    current_revision: str | None = None
    expected_revision: str


class PersistenceHealth(BaseModel):
    status: Literal["present", "empty", "unavailable"]
    marker_id: UUID | None = None
    created_at: datetime | None = None


class SystemStatus(BaseModel):
    status: Literal["ready", "degraded"]
    api: Literal["ok"] = "ok"
    environment: str
    version: str
    phase: int = int(BUILD_VERSION.rsplit("-phase", 1)[1])
    checked_at: datetime
    database: DatabaseHealth
    migrations: MigrationHealth
    persistence: PersistenceHealth
    development_tools_enabled: bool
