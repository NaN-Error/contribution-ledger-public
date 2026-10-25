"""Saved explanatory examples, NEVER finalized financial distributions."""
from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import DateTime, ForeignKeyConstraint, JSON, String, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base
from app.policies.models import actor_fk, project_fk


class SimulationScenario(Base):
    __tablename__ = 'simulation_scenarios'
    __table_args__ = (
        project_fk('fk_simulation_project'), actor_fk('created_by', 'fk_simulation_author'),
        ForeignKeyConstraint(['workspace_id','project_id','source_policy_id'],
            ['policy_versions.workspace_id','policy_versions.project_id','policy_versions.id'],name='fk_simulation_source_policy'),
        ForeignKeyConstraint(['workspace_id','project_id','calculation_policy_id'],
            ['policy_versions.workspace_id','policy_versions.project_id','policy_versions.id'],name='fk_simulation_calculation_policy'),
        UniqueConstraint('workspace_id','project_id','request_id',name='uq_simulation_request'),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    project_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, index=True)
    source_policy_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    calculation_policy_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    created_by: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    request_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    record_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    record: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
