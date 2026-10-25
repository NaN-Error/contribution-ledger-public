"""Content, approvals and acknowledgements are append-only, independently scoped records."""
from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import (CheckConstraint, DateTime, ForeignKeyConstraint, Integer, JSON,
                        String, UniqueConstraint, Uuid, func)
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


def project_fk(name: str):
    return ForeignKeyConstraint(['workspace_id', 'project_id'], ['projects.workspace_id', 'projects.id'], name=name)


def policy_fk(name: str):
    return ForeignKeyConstraint(['workspace_id', 'project_id', 'policy_id'],
        ['policy_versions.workspace_id', 'policy_versions.project_id', 'policy_versions.id'], name=name)


def actor_fk(field: str, name: str):
    return ForeignKeyConstraint(['workspace_id', field],
        ['workspace_memberships.workspace_id', 'workspace_memberships.user_id'], name=name)


class PolicyVersion(Base):
    __tablename__ = 'policy_versions'
    __table_args__ = (
        project_fk('fk_policy_project'), actor_fk('created_by', 'fk_policy_author'),
        ForeignKeyConstraint(['workspace_id', 'project_id', 'predecessor_id'],
            ['policy_versions.workspace_id', 'policy_versions.project_id', 'policy_versions.id'], name='fk_policy_predecessor'),
        UniqueConstraint('workspace_id', 'project_id', 'id', name='uq_policy_scope'),
        UniqueConstraint('project_id', 'version', name='uq_policy_project_version'),
        CheckConstraint('version >= 1', name='positive_policy_version'),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    project_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, index=True)
    predecessor_id: Mapped[UUID | None] = mapped_column(Uuid)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    rules: Mapped[dict] = mapped_column(JSON, nullable=False)
    agreement_reference: Mapped[str] = mapped_column(String(500), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class PolicyParticipant(Base):
    __tablename__ = 'policy_participants'
    __table_args__ = (policy_fk('fk_participant_policy'), actor_fk('user_id', 'fk_policy_participant_member'))
    policy_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    user_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    workspace_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    project_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    role_at_creation: Mapped[str] = mapped_column(String(20), nullable=False)


class PolicyApproval(Base):
    __tablename__ = 'policy_approvals'
    __table_args__ = (policy_fk('fk_approval_policy'), actor_fk('approved_by', 'fk_policy_approver'))
    policy_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    workspace_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    project_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    approved_by: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    reviewed_content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class PolicyAcknowledgement(Base):
    __tablename__ = 'policy_acknowledgements'
    __table_args__ = (policy_fk('fk_acknowledgement_policy'), actor_fk('user_id', 'fk_policy_acknowledger'))
    policy_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    user_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    workspace_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    project_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    reviewed_content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
