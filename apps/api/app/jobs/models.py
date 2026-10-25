"""Transactional dispatch intents. The importer owns checkpoints and lease fencing.

Phase 8 uses a database-backed runner; phase 9 adds broker delivery and recurring
reconciliation without replacing the database as the source of truth.
"""
from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import DateTime, String, Uuid, Integer, UniqueConstraint, func, ForeignKeyConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class OutboxMessage(Base):
    __tablename__ = 'job_outbox'
    __table_args__ = (ForeignKeyConstraint(['workspace_id', 'project_id', 'job_id'],
        ['github_imports.workspace_id', 'github_imports.project_id', 'github_imports.id'], name='fk_outbox_github_job'),
        UniqueConstraint('job_id', name='uq_outbox_import'),
        Index('ix_outbox_due','next_dispatch_at','dispatch_lease_until'))
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    project_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    job_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    kind: Mapped[str] = mapped_column(String(40), nullable=False, default='github_import')
    first_dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dispatch_lease: Mapped[UUID | None] = mapped_column(Uuid)
    dispatch_lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_dispatch_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    publish_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default='0')
    publish_error: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
