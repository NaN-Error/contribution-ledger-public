from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import (CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint,
                        Boolean, Index, Integer, JSON, String, UniqueConstraint, Uuid, func)
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


def project_fk(name):
    return ForeignKeyConstraint(['workspace_id', 'project_id'],
        ['projects.workspace_id', 'projects.id'], name=name)


class RepositoryReadConnection(Base):
    __tablename__ = 'repository_read_connections'
    __table_args__ = (project_fk('fk_repository_read_project'),
        UniqueConstraint('project_id','owner_id',name='uq_repository_read_owner'),
        CheckConstraint("method IN ('token','cli')",name='repository_read_method'),
        CheckConstraint('version >= 1',name='repository_read_version'))
    id: Mapped[UUID] = mapped_column(Uuid,primary_key=True,default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(Uuid,nullable=False)
    project_id: Mapped[UUID] = mapped_column(Uuid,nullable=False)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey('users.id'),nullable=False)
    version: Mapped[int] = mapped_column(Integer,nullable=False)
    method: Mapped[str] = mapped_column(String(10),nullable=False)
    username: Mapped[str] = mapped_column(String(39),nullable=False)
    credential_ref: Mapped[str | None] = mapped_column(String(36))
    repository_urls: Mapped[list] = mapped_column(JSON,nullable=False)
    active: Mapped[bool] = mapped_column(Boolean,nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),nullable=False)


class RepositoryAnalysis(Base):
    __tablename__ = 'repository_analyses'
    __table_args__ = (project_fk('fk_analysis_project'),
        Index('uq_analysis_report_scope', 'workspace_id', 'project_id', 'id', unique=True),
        UniqueConstraint('project_id', 'request_id', name='uq_analysis_request'),
        CheckConstraint("state IN ('queued','running','completed','failed','cancelled')", name='analysis_state'),
        CheckConstraint('version >= 1', name='analysis_version'))
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    project_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, index=True)
    created_by: Mapped[UUID] = mapped_column(ForeignKey('users.id'), nullable=False)
    request_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    definition: Mapped[dict] = mapped_column(JSON, nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    progress: Mapped[dict] = mapped_column(JSON, nullable=False)
    report: Mapped[dict | None] = mapped_column(JSON)
    error_code: Mapped[str | None] = mapped_column(String(100))
    lease_token: Mapped[UUID | None] = mapped_column(Uuid)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retry_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AnalysisDraft(Base):
    __tablename__ = 'analysis_drafts'
    __table_args__ = (project_fk('fk_analysis_draft_project'), CheckConstraint('version >= 1', name='analysis_draft_version'))
    project_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    workspace_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    document: Mapped[dict] = mapped_column(JSON, nullable=False)


class AnalysisDraftRevision(Base):
    __tablename__ = 'analysis_draft_revisions'
    __table_args__ = (project_fk('fk_analysis_revision_project'),
        UniqueConstraint('project_id', 'request_id', name='uq_analysis_revision_request'))
    project_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    created_by: Mapped[UUID] = mapped_column(ForeignKey('users.id'), nullable=False)
    request_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    document: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class AnalysisPublication(Base):
    """An exact administrator-reviewed disclosure, independent of mutable drafts."""
    __tablename__ = 'analysis_publications'
    __table_args__ = (project_fk('fk_analysis_publication_project'),
        UniqueConstraint('workspace_id', 'project_id', 'id', name='uq_analysis_publication_scope'),
        UniqueConstraint('project_id', 'request_id', name='uq_analysis_publication_request'))
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    project_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    created_by: Mapped[UUID] = mapped_column(ForeignKey('users.id'), nullable=False)
    request_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    document: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class AnalysisPublicationRevocation(Base):
    __tablename__ = 'analysis_publication_revocations'
    __table_args__ = (project_fk('fk_analysis_revocation_project'),
        ForeignKeyConstraint(['workspace_id', 'project_id', 'publication_id'],
            ['analysis_publications.workspace_id', 'analysis_publications.project_id', 'analysis_publications.id'],
            name='fk_analysis_revocation_publication'),
        UniqueConstraint('project_id', 'request_id', name='uq_analysis_revocation_request'))
    publication_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    workspace_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    project_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    created_by: Mapped[UUID] = mapped_column(ForeignKey('users.id'), nullable=False)
    request_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class AnalysisHandoff(Base):
    """Pinned evidence/identity/proposal review creating one ordinary historical package."""
    __tablename__ = 'analysis_handoffs'
    __table_args__ = (project_fk('fk_analysis_handoff_project'),
        ForeignKeyConstraint(['workspace_id', 'project_id', 'report_id'],
            ['repository_analyses.workspace_id', 'repository_analyses.project_id', 'repository_analyses.id'],
            name='fk_analysis_handoff_report'),
        ForeignKeyConstraint(['workspace_id', 'project_id', 'package_id'],
            ['work_packages.workspace_id', 'work_packages.project_id', 'work_packages.id'],
            name='fk_analysis_handoff_package'),
        UniqueConstraint('workspace_id', 'project_id', 'id', name='uq_analysis_handoff_scope'),
        UniqueConstraint('project_id', 'request_id', name='uq_analysis_handoff_request'),
        UniqueConstraint('package_id', name='uq_analysis_handoff_package'))
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    project_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    report_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    package_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    created_by: Mapped[UUID] = mapped_column(ForeignKey('users.id'), nullable=False)
    request_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    document: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class AnalysisSourceClaim(Base):
    """Stable primary entity and shared-commit claims; captured versions do not reset them."""
    __tablename__ = 'analysis_source_claims'
    __table_args__ = (project_fk('fk_analysis_claim_project'),
        ForeignKeyConstraint(['workspace_id', 'project_id', 'handoff_id'],
            ['analysis_handoffs.workspace_id', 'analysis_handoffs.project_id', 'analysis_handoffs.id'],
            name='fk_analysis_claim_handoff'))
    project_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    entity_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    handoff_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
