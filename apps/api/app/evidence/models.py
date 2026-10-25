"""Append-only evidence content and snapshot history; mutable visibility projection.

All references carry workspace, project and package scope. Object retirement
blocks subsequent delivery but never edits archived evidence or accounting.
"""
from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import (BigInteger, CheckConstraint, DateTime, ForeignKeyConstraint,
                        Integer, JSON, String, UniqueConstraint, Uuid, func)
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base
from app.policies.models import actor_fk
from app.contributions.work_packages.models import package_fk, revision_fk


def evidence_fk(name: str):
    return ForeignKeyConstraint(['workspace_id','project_id','package_id','evidence_id'],
        ['evidence_items.workspace_id','evidence_items.project_id','evidence_items.package_id','evidence_items.id'], name=name)


def object_fk(column: str, name: str):
    return ForeignKeyConstraint(['workspace_id','project_id','package_id',column],
        ['evidence_objects.workspace_id','evidence_objects.project_id','evidence_objects.package_id','evidence_objects.id'], name=name)


class EvidenceItem(Base):
    __tablename__ = 'evidence_items'
    __table_args__ = (package_fk('fk_evidence_package'), actor_fk('created_by','fk_evidence_author'),
        UniqueConstraint('workspace_id','project_id','package_id','id', name='uq_evidence_scope'),
        CheckConstraint('current_revision >= 1', name='evidence_positive_revision'),
        CheckConstraint("kind IN ('statement','link','file','unavailable')", name='evidence_kind'),
        CheckConstraint("visibility IN ('project','restricted')", name='evidence_visibility'))
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    project_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    package_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    visibility: Mapped[str] = mapped_column(String(20), nullable=False)
    current_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    created_by: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class EvidenceObject(Base):
    __tablename__ = 'evidence_objects'
    __table_args__ = (package_fk('fk_object_package'), actor_fk('created_by','fk_object_author'),
        UniqueConstraint('workspace_id','project_id','package_id','id', name='uq_evidence_object_scope'),
        CheckConstraint('size_bytes > 0 AND size_bytes <= 5242880', name='object_size'),
        CheckConstraint("backend IN ('local','s3')", name='object_backend'))
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    workspace_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, index=True)
    project_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    package_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    backend: Mapped[str] = mapped_column(String(10), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_by: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class EvidenceRevision(Base):
    __tablename__ = 'evidence_revisions'
    __table_args__ = (evidence_fk('fk_evidence_revision_item'), actor_fk('created_by','fk_evidence_revision_author'),
        object_fk('original_object_id','fk_evidence_original'), object_fk('preview_object_id','fk_evidence_preview'),
        UniqueConstraint('workspace_id','project_id','package_id','request_id', name='uq_evidence_request'),
        UniqueConstraint('workspace_id','project_id','package_id','evidence_id','number',name='uq_evidence_revision_scope'),
        CheckConstraint('number >= 1 AND number <= 50', name='evidence_revision_bounds'))
    evidence_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    number: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    project_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    package_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    document: Mapped[dict] = mapped_column(JSON, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    original_object_id: Mapped[UUID | None] = mapped_column(Uuid)
    preview_object_id: Mapped[UUID | None] = mapped_column(Uuid)
    request_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class EvidenceRetirement(Base):
    __tablename__ = 'evidence_retirements'
    __table_args__ = (object_fk('object_id','fk_retirement_object'), actor_fk('retired_by','fk_retirement_actor'))
    object_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    workspace_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    project_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    package_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    retired_by: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class EvidenceSnapshot(Base):
    __tablename__ = 'evidence_snapshots'
    __table_args__ = (revision_fk('fk_snapshot_scope'), actor_fk('created_by','fk_snapshot_actor'),
        UniqueConstraint('workspace_id','project_id','package_id','id', name='uq_evidence_snapshot_scope'),
        UniqueConstraint('package_id','content_hash',name='uq_snapshot_content'))
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    project_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    package_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, index=True)
    scope_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    document: Mapped[dict] = mapped_column(JSON, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
