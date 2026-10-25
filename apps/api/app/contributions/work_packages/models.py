"""Mutable package projection with immutable scope, membership, event and submission records."""
from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import (CheckConstraint, DateTime, Index, ForeignKeyConstraint, Integer, JSON,
                        String, UniqueConstraint, Uuid, func)
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base
from app.policies.models import project_fk, policy_fk, actor_fk
from app.contributions.budgets.models import milestone_fk


def package_fk(name: str):
    return ForeignKeyConstraint(['workspace_id', 'project_id', 'package_id'],
        ['work_packages.workspace_id', 'work_packages.project_id', 'work_packages.id'], name=name)


def revision_fk(name: str):
    return ForeignKeyConstraint(['workspace_id', 'project_id', 'package_id', 'scope_revision'],
        ['work_package_revisions.workspace_id', 'work_package_revisions.project_id',
         'work_package_revisions.package_id', 'work_package_revisions.number'], name=name)


class WorkPackage(Base):
    __tablename__ = 'work_packages'
    __table_args__ = (
        project_fk('fk_work_package_project'), policy_fk('fk_work_package_policy'),
        milestone_fk('fk_work_package_milestone'), actor_fk('created_by', 'fk_work_package_author'),
        ForeignKeyConstraint(['workspace_id', 'project_id', 'milestone_id', 'allocation_id'],
            ['budget_allocations.workspace_id', 'budget_allocations.project_id',
             'budget_allocations.milestone_id', 'budget_allocations.id'], name='fk_work_package_allocation'),
        UniqueConstraint('workspace_id', 'project_id', 'id', name='uq_work_package_scope'),
        UniqueConstraint('allocation_id', name='uq_work_package_allocation'),
        CheckConstraint("state IN ('draft','budget_approved','in_progress','submitted','changes_requested','cancelled','completed')", name='work_package_state'),
        CheckConstraint('version >= 1 AND scope_revision >= 1', name='work_package_versions'),
        CheckConstraint('approved_revision IS NULL OR approved_revision = scope_revision', name='work_package_approval_revision'),
        CheckConstraint("state NOT IN ('budget_approved','in_progress','submitted','completed') OR (approved_revision IS NOT NULL AND approved_revision = scope_revision)", name='work_package_approved_state'),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    project_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, index=True)
    milestone_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    allocation_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    policy_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    state: Mapped[str] = mapped_column(String(24), nullable=False, default='draft', server_default='draft')
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default='1')
    scope_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default='1')
    approved_revision: Mapped[int | None] = mapped_column(Integer)
    created_by: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class WorkPackageRevision(Base):
    __tablename__ = 'work_package_revisions'
    __table_args__ = (
        package_fk('fk_work_revision_package'), actor_fk('created_by', 'fk_work_revision_author'),
        UniqueConstraint('workspace_id', 'project_id', 'package_id', 'number', name='uq_work_revision_scope'),
        CheckConstraint('number >= 1 AND allocation_version >= 1', name='work_revision_versions'),
    )
    package_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    number: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    project_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    allocation_version: Mapped[int] = mapped_column(Integer, nullable=False)
    document: Mapped[dict] = mapped_column(JSON, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class WorkPackageParticipant(Base):
    """Foreign-key-backed project-scope claims per revision, never a mutable roster."""
    __tablename__ = 'work_package_participants'
    __table_args__ = (
        revision_fk('fk_work_participant_revision'), actor_fk('user_id', 'fk_work_participant_member'),
        CheckConstraint("kind IN ('coordinator','intended')", name='work_participant_kind'),
    )
    package_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    scope_revision: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    kind: Mapped[str] = mapped_column(String(20), primary_key=True)
    workspace_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    project_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)


class WorkPackageEvent(Base):
    __tablename__ = 'work_package_events'
    __table_args__ = (
        revision_fk('fk_work_event_revision'), actor_fk('actor_id', 'fk_work_event_actor'),
        UniqueConstraint('package_id', 'package_version', name='uq_work_event_version'),
        CheckConstraint('package_version >= 1', name='work_event_version'),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    project_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    package_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, index=True)
    scope_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    package_version: Mapped[int] = mapped_column(Integer, nullable=False)
    actor_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    details: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class WorkSubmission(Base):
    __tablename__ = 'work_submissions'
    __table_args__ = (
        revision_fk('fk_work_submission_revision'), actor_fk('submitted_by', 'fk_work_submission_actor'),
        UniqueConstraint('package_id', 'package_version', name='uq_work_submission_version'),
        Index('uq_work_submission_scope', 'workspace_id','project_id','package_id','id', unique=True),
        CheckConstraint('package_version >= 1', name='work_submission_version'),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    project_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    package_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, index=True)
    scope_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    package_version: Mapped[int] = mapped_column(Integer, nullable=False)
    submitted_by: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
