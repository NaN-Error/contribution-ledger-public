from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import (BigInteger, CheckConstraint, DateTime, ForeignKeyConstraint, Integer,
                        JSON, String, UniqueConstraint, Uuid, func)
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base
from app.policies.models import project_fk, policy_fk, actor_fk
from app.policies.schemas import MAX_ATOMS


def milestone_fk(name):
    return ForeignKeyConstraint(['workspace_id', 'project_id', 'milestone_id'],
        ['milestones.workspace_id', 'milestones.project_id', 'milestones.id'], name=name)


class Milestone(Base):
    __tablename__ = 'milestones'
    __table_args__ = (
        project_fk('fk_milestone_project'), policy_fk('fk_milestone_policy'), actor_fk('created_by', 'fk_milestone_author'),
        UniqueConstraint('workspace_id', 'project_id', 'id', name='uq_milestone_scope'),
        CheckConstraint("status IN ('draft','active')", name='milestone_status'),
        CheckConstraint('version >= 1', name='milestone_version'),
        CheckConstraint(f'total_atoms >= 0 AND total_atoms <= {MAX_ATOMS}', name='milestone_total'),
        CheckConstraint('reserve_floor_atoms >= 0 AND allocated_atoms >= 0 AND issued_atoms >= 0', name='milestone_nonnegative'),
        CheckConstraint('issued_atoms <= allocated_atoms', name='milestone_issued_bound'),
        CheckConstraint('allocated_atoms + reserve_floor_atoms <= total_atoms', name='milestone_budget_bound'),
        CheckConstraint("status <> 'draft' OR (total_atoms = 0 AND reserve_floor_atoms = 0 AND allocated_atoms = 0 AND issued_atoms = 0)", name='milestone_draft_zero'),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    project_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, index=True)
    policy_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(String(1000), nullable=False, default='', server_default='')
    status: Mapped[str] = mapped_column(String(20), nullable=False, default='draft', server_default='draft')
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default='1')
    total_atoms: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default='0')
    reserve_floor_atoms: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default='0')
    allocated_atoms: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default='0')
    # A future ledger projection; phase 3 has NO endpoint capable of issuing units.
    issued_atoms: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default='0')
    created_by: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class BudgetAllocation(Base):
    __tablename__ = 'budget_allocations'
    __table_args__ = (
        milestone_fk('fk_allocation_milestone'),
        UniqueConstraint('workspace_id', 'project_id', 'milestone_id', 'id', name='uq_allocation_scope'),
        CheckConstraint("status IN ('active','cancelled')", name='allocation_status'),
        CheckConstraint("pool_key IN ('release','ongoing')", name='allocation_pool'),
        CheckConstraint(f'atoms >= 0 AND atoms <= {MAX_ATOMS}', name='allocation_amount'),
        CheckConstraint('issued_atoms >= 0 AND issued_atoms <= atoms', name='allocation_issued_bound'),
        CheckConstraint('version >= 1', name='allocation_version'),
        CheckConstraint("status <> 'cancelled' OR (atoms = 0 AND issued_atoms = 0)", name='cancelled_allocation_zero'),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    project_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    milestone_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    category: Mapped[str] = mapped_column(String(30), nullable=False)
    pool_key: Mapped[str] = mapped_column(String(20), nullable=False)
    atoms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    issued_atoms: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default='0')
    status: Mapped[str] = mapped_column(String(20), nullable=False, default='active', server_default='active')
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default='1')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class BudgetAmendment(Base):
    __tablename__ = 'budget_amendments'
    __table_args__ = (milestone_fk('fk_amendment_milestone'), actor_fk('proposed_by', 'fk_amendment_author'),
        UniqueConstraint('workspace_id', 'project_id', 'milestone_id', 'id', name='uq_amendment_scope'),
        CheckConstraint('expected_version >= 1', name='amendment_version'))
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    project_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    milestone_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, index=True)
    proposed_by: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    expected_version: Mapped[int] = mapped_column(Integer, nullable=False)
    change: Mapped[dict] = mapped_column(JSON, nullable=False)
    preview: Mapped[dict] = mapped_column(JSON, nullable=False)
    preview_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class BudgetDecision(Base):
    __tablename__ = 'budget_decisions'
    __table_args__ = (
        ForeignKeyConstraint(['workspace_id', 'project_id', 'milestone_id', 'amendment_id'],
            ['budget_amendments.workspace_id', 'budget_amendments.project_id',
             'budget_amendments.milestone_id', 'budget_amendments.id'], name='fk_decision_amendment'),
        actor_fk('decided_by', 'fk_budget_decider'),
        CheckConstraint("decision IN ('approve','reject')", name='budget_decision'),
    )
    amendment_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    workspace_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    project_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    milestone_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    decided_by: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    decision: Mapped[str] = mapped_column(String(10), nullable=False)
    reviewed_preview_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    resulting_version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
