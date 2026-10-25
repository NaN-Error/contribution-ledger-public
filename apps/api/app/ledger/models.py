"""Awards and signed event lines are immutable. Balances are rebuildable projections."""
from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKeyConstraint, JSON, String, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base
from app.policies.models import policy_fk, actor_fk
from app.policies.schemas import MAX_ATOMS
from app.contributions.work_packages.models import package_fk
from app.contributions.budgets.models import milestone_fk
from app.reviews.models import review_fk


def award_fk(name):
    return ForeignKeyConstraint(['workspace_id','project_id','package_id','award_id'],
        ['credit_awards.workspace_id','credit_awards.project_id','credit_awards.package_id','credit_awards.id'],name=name)


class CreditAward(Base):
    __tablename__ = 'credit_awards'
    __table_args__ = (package_fk('fk_award_package'), milestone_fk('fk_award_milestone'), policy_fk('fk_award_policy'),
        review_fk('fk_award_review'), actor_fk('finalized_by','fk_award_finalizer'),
        ForeignKeyConstraint(['workspace_id','project_id','milestone_id','allocation_id'],
            ['budget_allocations.workspace_id','budget_allocations.project_id','budget_allocations.milestone_id','budget_allocations.id'],name='fk_award_allocation'),
        UniqueConstraint('workspace_id','project_id','package_id','id',name='uq_award_scope'),
        UniqueConstraint('package_id','deliverable_id',name='uq_deliverable_awarded_once'),
        UniqueConstraint('review_id',name='uq_award_review'),
        UniqueConstraint('workspace_id','project_id','request_id',name='uq_award_request'),
        CheckConstraint(f'budget_atoms > 0 AND budget_atoms <= {MAX_ATOMS}', name='award_budget'),
        CheckConstraint("pool_key IN ('release','ongoing')",name='award_pool'))
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    project_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, index=True)
    package_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    milestone_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    allocation_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    policy_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    review_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    deliverable_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    budget_atoms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    pool_key: Mapped[str] = mapped_column(String(20), nullable=False)
    original_attributions: Mapped[list] = mapped_column(JSON, nullable=False)
    finalized_by: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    request_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class ContributionEvent(Base):
    __tablename__ = 'contribution_events'
    __table_args__ = (award_fk('fk_contribution_award'), review_fk('fk_contribution_review'),
        actor_fk('user_id','fk_credit_recipient'),
        ForeignKeyConstraint(['workspace_id','project_id','package_id','resolution_id'],
            ['dispute_resolutions.workspace_id','dispute_resolutions.project_id','dispute_resolutions.package_id','dispute_resolutions.id'],name='fk_event_resolution'),
        UniqueConstraint('review_id','user_id','role',name='uq_credit_line_effect'),
        CheckConstraint(f'delta_atoms <> 0 AND delta_atoms BETWEEN -{MAX_ATOMS} AND {MAX_ATOMS}',name='credit_delta_bound'),
        CheckConstraint("(kind = 'award' AND delta_atoms > 0 AND resolution_id IS NULL) OR (kind = 'adjustment' AND resolution_id IS NOT NULL)",name='credit_kind'))
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    project_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, index=True)
    package_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    award_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, index=True)
    review_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    resolution_id: Mapped[UUID | None] = mapped_column(Uuid)
    user_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    role: Mapped[str] = mapped_column(String(30), nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    delta_atoms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class ContributionBalance(Base):
    __tablename__ = 'contribution_balances'
    __table_args__ = (award_fk('fk_balance_award'),actor_fk('user_id','fk_balance_recipient'),
        CheckConstraint(f'atoms >= 0 AND atoms <= {MAX_ATOMS}',name='balance_nonnegative'))
    award_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    user_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    role: Mapped[str] = mapped_column(String(30), primary_key=True)
    workspace_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    project_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, index=True)
    package_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    atoms: Mapped[int] = mapped_column(BigInteger, nullable=False)
