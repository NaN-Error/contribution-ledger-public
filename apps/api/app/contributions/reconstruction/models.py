"""Historical scopes and projections backed by immutable command history."""
from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import (CheckConstraint, DateTime, ForeignKeyConstraint, Integer, JSON,
                        String, UniqueConstraint, Uuid, func)
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base
from app.policies.models import project_fk, policy_fk, actor_fk
from app.contributions.budgets.models import milestone_fk
from app.contributions.work_packages.models import package_fk
from app.integrations.github.models import scoped_fk


def batch_fk(name):
    return scoped_fk('reconstruction_batches', 'batch_id', name)


def candidate_fk(name):
    return ForeignKeyConstraint(['workspace_id','project_id','batch_id','candidate_id'],
        ['reconstruction_candidates.workspace_id','reconstruction_candidates.project_id',
         'reconstruction_candidates.batch_id','reconstruction_candidates.id'], name=name)


class ReconstructionBatch(Base):
    __tablename__ = 'reconstruction_batches'
    __table_args__ = (project_fk('fk_reconstruction_project'), policy_fk('fk_reconstruction_policy'),
        milestone_fk('fk_reconstruction_milestone'), actor_fk('created_by','fk_reconstruction_author'),
        UniqueConstraint('workspace_id','project_id','id',name='uq_reconstruction_scope'),
        UniqueConstraint('milestone_id',name='uq_reconstruction_milestone'),
        UniqueConstraint('project_id','created_by','request_id',name='uq_reconstruction_request'),
        CheckConstraint("state IN ('draft','approved','frozen')",name='reconstruction_state'),
        CheckConstraint('version >= 1',name='reconstruction_version'))
    id: Mapped[UUID] = mapped_column(Uuid,primary_key=True,default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(Uuid,nullable=False)
    project_id: Mapped[UUID] = mapped_column(Uuid,nullable=False,index=True)
    milestone_id: Mapped[UUID] = mapped_column(Uuid,nullable=False)
    policy_id: Mapped[UUID] = mapped_column(Uuid,nullable=False)
    created_by: Mapped[UUID] = mapped_column(Uuid,nullable=False)
    request_id: Mapped[UUID] = mapped_column(Uuid,nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64),nullable=False)
    definition: Mapped[dict] = mapped_column(JSON,nullable=False)
    state: Mapped[str] = mapped_column(String(16),nullable=False,default='draft',server_default='draft')
    version: Mapped[int] = mapped_column(Integer,nullable=False,default=1,server_default='1')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),nullable=False,server_default=func.now())


class ReconstructionCandidate(Base):
    __tablename__ = 'reconstruction_candidates'
    __table_args__ = (batch_fk('fk_candidate_batch'), actor_fk('created_by','fk_candidate_author'),
        package_fk('fk_candidate_package'),
        UniqueConstraint('workspace_id','project_id','batch_id','id',name='uq_candidate_scope'),
        UniqueConstraint('package_id',name='uq_candidate_package'),
        CheckConstraint("state IN ('draft','linked','rejected','superseded')",name='candidate_state'),
        CheckConstraint('version >= 1',name='candidate_version'))
    id: Mapped[UUID] = mapped_column(Uuid,primary_key=True,default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(Uuid,nullable=False)
    project_id: Mapped[UUID] = mapped_column(Uuid,nullable=False,index=True)
    batch_id: Mapped[UUID] = mapped_column(Uuid,nullable=False,index=True)
    package_id: Mapped[UUID | None] = mapped_column(Uuid)
    state: Mapped[str] = mapped_column(String(16),nullable=False,default='draft',server_default='draft')
    version: Mapped[int] = mapped_column(Integer,nullable=False,default=1,server_default='1')
    document: Mapped[dict] = mapped_column(JSON,nullable=False)
    created_by: Mapped[UUID] = mapped_column(Uuid,nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),nullable=False,server_default=func.now())


class ReconstructionSourceClaim(Base):
    """One primary outcome per observed entity across reconnects and reimports.

    The entity key uses the numeric remote repository ID, not a local connection.
    Moves only reassign a pinned source to another unpromoted candidate in its batch.
    """
    __tablename__ = 'reconstruction_source_claims'
    __table_args__ = (candidate_fk('fk_source_claim_candidate'),
        scoped_fk('github_source_versions','source_id','fk_source_claim_source'),
        UniqueConstraint('project_id','entity_key',name='uq_reconstruction_entity'))
    id: Mapped[UUID] = mapped_column(Uuid,primary_key=True,default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(Uuid,nullable=False)
    project_id: Mapped[UUID] = mapped_column(Uuid,nullable=False,index=True)
    batch_id: Mapped[UUID] = mapped_column(Uuid,nullable=False)
    candidate_id: Mapped[UUID] = mapped_column(Uuid,nullable=False,index=True)
    source_id: Mapped[UUID] = mapped_column(Uuid,nullable=False)
    entity_key: Mapped[str] = mapped_column(String(64),nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),nullable=False,server_default=func.now())


class ReconstructionEvent(Base):
    __tablename__ = 'reconstruction_events'
    __table_args__ = (batch_fk('fk_reconstruction_event_batch'),actor_fk('actor_id','fk_reconstruction_event_actor'),
        UniqueConstraint('batch_id','version',name='uq_reconstruction_event_version'),
        UniqueConstraint('project_id','actor_id','request_id',name='uq_reconstruction_event_request'),
        CheckConstraint('version >= 1',name='reconstruction_event_version'))
    id: Mapped[UUID] = mapped_column(Uuid,primary_key=True,default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(Uuid,nullable=False)
    project_id: Mapped[UUID] = mapped_column(Uuid,nullable=False,index=True)
    batch_id: Mapped[UUID] = mapped_column(Uuid,nullable=False,index=True)
    version: Mapped[int] = mapped_column(Integer,nullable=False)
    actor_id: Mapped[UUID] = mapped_column(Uuid,nullable=False)
    request_id: Mapped[UUID] = mapped_column(Uuid,nullable=False)
    command_hash: Mapped[str] = mapped_column(String(64),nullable=False)
    action: Mapped[str] = mapped_column(String(100),nullable=False)
    reason: Mapped[str] = mapped_column(String(500),nullable=False)
    record: Mapped[dict] = mapped_column(JSON,nullable=False)
    record_hash: Mapped[str] = mapped_column(String(64),nullable=False)
    previous_hash: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),nullable=False,server_default=func.now())


class ReconstructionMissingClaim(Base):
    __tablename__ = 'reconstruction_missing_claims'
    __table_args__ = (batch_fk('fk_missing_claim_batch'),actor_fk('created_by','fk_missing_claim_author'),
        candidate_fk('fk_missing_claim_candidate'),
        UniqueConstraint('project_id','created_by','request_id',name='uq_missing_claim_request'),
        CheckConstraint("state IN ('open','included','declined')",name='missing_claim_state'))
    id: Mapped[UUID] = mapped_column(Uuid,primary_key=True,default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(Uuid,nullable=False)
    project_id: Mapped[UUID] = mapped_column(Uuid,nullable=False,index=True)
    batch_id: Mapped[UUID] = mapped_column(Uuid,nullable=False)
    created_by: Mapped[UUID] = mapped_column(Uuid,nullable=False)
    request_id: Mapped[UUID] = mapped_column(Uuid,nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64),nullable=False)
    document: Mapped[dict] = mapped_column(JSON,nullable=False)
    state: Mapped[str] = mapped_column(String(16),nullable=False,default='open',server_default='open')
    candidate_id: Mapped[UUID | None] = mapped_column(Uuid)
    resolution_reason: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),nullable=False,server_default=func.now())


class OpeningBalanceSnapshot(Base):
    __tablename__ = 'opening_balance_snapshots'
    __table_args__ = (batch_fk('fk_opening_snapshot_batch'),actor_fk('created_by','fk_opening_snapshot_actor'),
        UniqueConstraint('batch_id',name='uq_opening_snapshot_batch'))
    id: Mapped[UUID] = mapped_column(Uuid,primary_key=True,default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(Uuid,nullable=False)
    project_id: Mapped[UUID] = mapped_column(Uuid,nullable=False,index=True)
    batch_id: Mapped[UUID] = mapped_column(Uuid,nullable=False)
    created_by: Mapped[UUID] = mapped_column(Uuid,nullable=False)
    record: Mapped[dict] = mapped_column(JSON,nullable=False)
    record_hash: Mapped[str] = mapped_column(String(64),nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),nullable=False,server_default=func.now())
