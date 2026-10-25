"""Tenant-scoped references are enforced with composite foreign keys, not just UI rules."""
from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import (CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Integer,
                        JSON, String, UniqueConstraint, Uuid, func)
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class Workspace(Base):
    __tablename__ = "workspaces"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class WorkspaceMembership(Base):
    __tablename__ = "workspace_memberships"
    __table_args__ = (
        CheckConstraint("role IN ('owner','admin','member')", name="workspace_role"),
        CheckConstraint("status IN ('active','suspended')", name="workspace_member_status"),
        CheckConstraint("version >= 1", name="workspace_member_version"),
    )
    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id"), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active", server_default="active")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (
        UniqueConstraint("workspace_id", "id", name="uq_project_workspace_id"),
        CheckConstraint("currency = 'USD'", name="project_supported_currency"),
        CheckConstraint("version >= 1", name="project_version"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(String(1000), nullable=False, default="", server_default="")
    timezone: Mapped[str] = mapped_column(String(80), nullable=False, default="UTC", server_default="UTC")
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD", server_default="USD")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class ProjectMembership(Base):
    __tablename__ = "project_memberships"
    __table_args__ = (
        ForeignKeyConstraint(["workspace_id", "project_id"], ["projects.workspace_id", "projects.id"], name="fk_project_member_project"),
        ForeignKeyConstraint(["workspace_id", "user_id"], ["workspace_memberships.workspace_id", "workspace_memberships.user_id"], name="fk_project_member_workspace_member"),
        CheckConstraint("role IN ('admin','contributor','reviewer','finance','viewer')", name="project_role"),
        CheckConstraint("status IN ('active','suspended')", name="project_member_status"),
        CheckConstraint("version >= 1", name="project_member_version"),
    )
    workspace_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    project_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    user_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active", server_default="active")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class Invitation(Base):
    __tablename__ = "invitations"
    __table_args__ = (
        ForeignKeyConstraint(["workspace_id", "project_id"], ["projects.workspace_id", "projects.id"], name="fk_invitation_project"),
        ForeignKeyConstraint(["workspace_id", "inviter_id"], ["workspace_memberships.workspace_id", "workspace_memberships.user_id"], name="fk_invitation_issuer"),
        CheckConstraint("workspace_role IN ('admin','member')", name="invitation_workspace_role"),
        CheckConstraint("status IN ('pending','accepted','revoked')", name="invitation_status"),
        CheckConstraint("(project_id IS NULL AND project_role IS NULL) OR (project_id IS NOT NULL AND project_role IN ('admin','contributor','reviewer','finance','viewer'))", name="invitation_project_role"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id"), nullable=False, index=True)
    project_id: Mapped[UUID | None] = mapped_column(Uuid)
    inviter_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    email: Mapped[str] = mapped_column(String(254), nullable=False)
    workspace_role: Mapped[str] = mapped_column(String(20), nullable=False, default="member")
    project_role: Mapped[str | None] = mapped_column(String(20))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", server_default="pending")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        ForeignKeyConstraint(["workspace_id", "project_id"], ["projects.workspace_id", "projects.id"], name="fk_audit_project"),
        CheckConstraint("project_id IS NULL OR workspace_id IS NOT NULL", name="audit_project_scope"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID | None] = mapped_column(ForeignKey("workspaces.id"), index=True)
    project_id: Mapped[UUID | None] = mapped_column(Uuid)
    actor_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    subject_id: Mapped[str | None] = mapped_column(String(80))
    reason: Mapped[str] = mapped_column(String(500), nullable=False, default="", server_default="")
    details: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
