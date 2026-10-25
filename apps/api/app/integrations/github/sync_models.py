"""Durable signed signals, explicit schedules, and current observations.

Source versions and economic history are never overwritten by these projections.
Webhook rows store hashes and bounded routing identifiers, never raw code/payloads.
"""
from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import (BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey,
    Integer, JSON, String, UniqueConstraint, Uuid, func, Index)
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base
from app.policies.models import actor_fk
from app.integrations.github.models import scoped_fk


class WebhookDelivery(Base):
    __tablename__ = 'github_webhook_deliveries'
    __table_args__ = (
        UniqueConstraint('app_id', 'delivery_key', name='uq_gh_delivery_key'),
        UniqueConstraint('app_id', 'payload_hash', name='uq_gh_delivery_body'),
        CheckConstraint('body_bytes >= 2 AND body_bytes <= 1048576', name='gh_delivery_size'),)
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    app_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    delivery_key: Mapped[str] = mapped_column(String(36), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    body_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    event: Mapped[str] = mapped_column(String(60), nullable=False)
    action: Mapped[str] = mapped_column(String(60), nullable=False)
    installation_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    disposition: Mapped[str] = mapped_column(String(60), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class WebhookTarget(Base):
    __tablename__ = 'github_webhook_targets'
    __table_args__ = (
        Index('ix_gh_signal_pending','repository_id','state','created_at'),
        scoped_fk('github_repositories', 'repository_id', 'fk_gh_signal_repo'),
        scoped_fk('github_imports', 'import_id', 'fk_gh_signal_import'),
        UniqueConstraint('delivery_id', 'repository_id', name='uq_gh_delivery_repo'),
        CheckConstraint("state IN ('pending','scheduled','processed','ignored','failed')", name='gh_signal_state'),)
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    project_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, index=True)
    repository_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    delivery_id: Mapped[UUID] = mapped_column(ForeignKey('github_webhook_deliveries.id'), nullable=False)
    targets: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    state: Mapped[str] = mapped_column(String(20), nullable=False)
    import_id: Mapped[UUID | None] = mapped_column(Uuid)
    note: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class GitHubSyncConfig(Base):
    __tablename__ = 'github_sync_configs'
    __table_args__ = (
        Index('ix_gh_sync_due','enabled','next_due_at'),
        scoped_fk('github_repositories', 'repository_id', 'fk_gh_sync_repo'),
        scoped_fk('github_imports', 'active_import_id', 'fk_gh_sync_active'),
        actor_fk('configured_by', 'fk_gh_sync_actor'),
        UniqueConstraint('repository_id', name='uq_gh_sync_repo'),
        UniqueConstraint('workspace_id', 'project_id', 'id', name='uq_gh_sync_scope'),
        CheckConstraint('version >= 1 AND interval_minutes >= 60 AND interval_minutes <= 10080', name='gh_sync_interval'),
        CheckConstraint('lookback_days >= 1 AND lookback_days <= 90', name='gh_sync_lookback'),
        CheckConstraint('request_limit >= 10 AND request_limit <= 1000 AND entity_limit >= 1 AND entity_limit <= 200', name='gh_sync_limits'),)
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    project_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, index=True)
    repository_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    configured_by: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    interval_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=360)
    lookback_days: Mapped[int] = mapped_column(Integer, nullable=False, default=7)
    request_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=200)
    entity_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    next_due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    active_import_id: Mapped[UUID | None] = mapped_column(Uuid)
    # Round-robin refreshes known primary sources, including old closed PRs/issues.
    scan_cursor: Mapped[str] = mapped_column(String(180), nullable=False, default='')
    last_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_complete_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String(100))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class GitHubSyncRun(Base):
    __tablename__ = 'github_sync_runs'
    __table_args__ = (
        scoped_fk('github_sync_configs', 'config_id', 'fk_gh_run_config'),
        scoped_fk('github_imports', 'import_id', 'fk_gh_run_import'),
        UniqueConstraint('import_id', name='uq_gh_sync_import'),)
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    project_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, index=True)
    config_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    config_version: Mapped[int] = mapped_column(Integer, nullable=False)
    import_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    trigger: Mapped[str] = mapped_column(String(30), nullable=False)
    target_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class GitHubSourceHead(Base):
    __tablename__ = 'github_source_heads'
    __table_args__ = (
        scoped_fk('github_repositories', 'repository_id', 'fk_gh_head_repo'),
        scoped_fk('github_source_versions', 'source_id', 'fk_gh_head_source'),
        scoped_fk('github_imports', 'import_id', 'fk_gh_head_import'),
        UniqueConstraint('repository_id', 'kind', 'remote_key', name='uq_gh_head_key'),
        CheckConstraint("state IN ('captured','unavailable')", name='gh_head_state'),)
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    project_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, index=True)
    repository_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    remote_key: Mapped[str] = mapped_column(String(180), nullable=False)
    source_id: Mapped[UUID | None] = mapped_column(Uuid)
    import_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    remote_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class JobHeartbeat(Base):
    __tablename__ = 'job_heartbeats'
    component: Mapped[str] = mapped_column(String(40), primary_key=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(80), nullable=False)
