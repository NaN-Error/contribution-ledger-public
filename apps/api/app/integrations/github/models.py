"""Scoped source records and durable import state, independent of economic tables."""
from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import (BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint,
                        Integer, JSON, String, UniqueConstraint, Uuid, func)
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base
from app.policies.models import actor_fk, project_fk


def scoped_fk(table, column, name):
    return ForeignKeyConstraint(['workspace_id', 'project_id', column],
                                [f'{table}.workspace_id', f'{table}.project_id', f'{table}.id'], name=name)


class GitHubAuthFlow(Base):
    __tablename__ = 'github_auth_flows'
    __table_args__ = (project_fk('fk_gh_flow_project'), actor_fk('created_by', 'fk_gh_flow_actor'),
        UniqueConstraint('workspace_id', 'project_id', 'id', name='uq_gh_flow_scope'),
        CheckConstraint("state IN ('pending','exchanging','verified','used','failed')", name='gh_flow_state'))
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    project_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, index=True)
    created_by: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    session_id: Mapped[UUID] = mapped_column(ForeignKey('browser_sessions.id'), nullable=False)
    state_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    installation_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    app_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False, default='pending')
    proof: Mapped[dict | None] = mapped_column(JSON)
    proof_hash: Mapped[str | None] = mapped_column(String(64))
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(80))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class GitHubConnection(Base):
    __tablename__ = 'github_connections'
    __table_args__ = (project_fk('fk_gh_conn_project'), actor_fk('authorized_by', 'fk_gh_conn_actor'),
        scoped_fk('github_auth_flows', 'flow_id', 'fk_gh_conn_flow'),
        UniqueConstraint('workspace_id', 'project_id', 'id', name='uq_gh_conn_scope'),
        UniqueConstraint('project_id', 'app_id', 'installation_id', name='uq_gh_installation_project'),
        CheckConstraint('version >= 1', name='gh_conn_version'))
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    project_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, index=True)
    app_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    installation_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    flow_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    authorized_by: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    github_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    github_login: Mapped[str] = mapped_column(String(100), nullable=False)
    account: Mapped[str] = mapped_column(String(100), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    verified_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_error: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class GitHubRepository(Base):
    __tablename__ = 'github_repositories'
    __table_args__ = (scoped_fk('github_connections', 'connection_id', 'fk_gh_repo_conn'),
        UniqueConstraint('workspace_id', 'project_id', 'id', name='uq_gh_repo_scope'),
        UniqueConstraint('project_id', 'github_id', name='uq_gh_repository_project'),
        CheckConstraint('version >= 1', name='gh_repo_version'))
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    project_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, index=True)
    connection_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    github_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    full_name: Mapped[str] = mapped_column(String(202), nullable=False)
    retry_not_before: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    private: Mapped[bool] = mapped_column(Boolean, nullable=False)
    default_branch: Mapped[str] = mapped_column(String(200), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class GitHubImport(Base):
    __tablename__ = 'github_imports'
    __table_args__ = (scoped_fk('github_repositories', 'repository_id', 'fk_gh_import_repo'),
        actor_fk('requested_by', 'fk_gh_import_actor'),
        UniqueConstraint('workspace_id', 'project_id', 'id', name='uq_gh_import_scope'),
        UniqueConstraint('project_id', 'request_id', name='uq_gh_import_request'),
        CheckConstraint("state IN ('queued','running','paused','failed','cancelled','completed','completed_incomplete')", name='gh_import_state'),
        CheckConstraint('data_requests >= 0 AND request_limit >= 10 AND request_limit <= 1000', name='gh_import_requests'),
        CheckConstraint('entity_limit >= 1 AND entity_limit <= 200', name='gh_import_entities'),
        CheckConstraint('version >= 1 AND failures >= 0', name='gh_import_version'))
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    project_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, index=True)
    repository_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    requested_by: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    request_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    connection_version: Mapped[int] = mapped_column(Integer, nullable=False)
    repository_version: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[str] = mapped_column(String(30), nullable=False, default='queued')
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_before: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    requested_as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    capture_mode: Mapped[str] = mapped_column(String(20), nullable=False, default='historical', server_default='historical')
    anchor_sha: Mapped[str | None] = mapped_column(String(64))
    request_limit: Mapped[int] = mapped_column(Integer, nullable=False)
    entity_limit: Mapped[int] = mapped_column(Integer, nullable=False)
    data_requests: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    stats: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    omissions: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    lease_token: Mapped[UUID | None] = mapped_column(Uuid)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class GitHubFetchTask(Base):
    __tablename__ = 'github_fetch_tasks'
    __table_args__ = (scoped_fk('github_imports', 'import_id', 'fk_gh_task_import'),
        UniqueConstraint('workspace_id', 'project_id', 'id', name='uq_gh_task_scope'),
        UniqueConstraint('import_id', 'kind', 'subject', 'page', name='uq_gh_fetch_page'),
        CheckConstraint("state IN ('pending','done','omitted')", name='gh_task_state'),
        CheckConstraint('page >= 1 AND ordinal >= 1', name='gh_task_page'))
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    project_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    import_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, index=True)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    subject: Mapped[str] = mapped_column(String(100), nullable=False, default='')
    page: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    state: Mapped[str] = mapped_column(String(20), nullable=False, default='pending')
    parameters: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class GitHubSourceVersion(Base):
    __tablename__ = 'github_source_versions'
    __table_args__ = (scoped_fk('github_repositories', 'repository_id', 'fk_gh_source_repo'),
        UniqueConstraint('workspace_id', 'project_id', 'id', name='uq_gh_source_scope'),
        UniqueConstraint('repository_id', 'kind', 'remote_key', 'content_hash', name='uq_gh_source_content'),
        CheckConstraint('size_bytes > 0 AND size_bytes <= 524288', name='gh_source_size'))
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    project_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, index=True)
    repository_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    remote_key: Mapped[str] = mapped_column(String(200), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    document: Mapped[dict] = mapped_column(JSON, nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class GitHubObservation(Base):
    __tablename__ = 'github_observations'
    __table_args__ = (scoped_fk('github_imports', 'import_id', 'fk_gh_observe_import'),
        scoped_fk('github_source_versions', 'source_id', 'fk_gh_observe_source'),
        scoped_fk('github_fetch_tasks', 'task_id', 'fk_gh_observe_task'),
        UniqueConstraint('import_id', 'task_id', 'source_id', name='uq_gh_observation'))
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    project_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    import_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    task_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    source_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class GitHubIdentity(Base):
    __tablename__ = 'github_identities'
    __table_args__ = (project_fk('fk_gh_identity_project'), actor_fk('linked_user_id', 'fk_gh_identity_user'),
        UniqueConstraint('workspace_id', 'project_id', 'id', name='uq_gh_identity_scope'),
        UniqueConstraint('project_id', 'external_key', name='uq_gh_identity_key'),
        CheckConstraint("kind IN ('github_user','github_bot','email_claim','unknown')", name='gh_identity_kind'),
        CheckConstraint('version >= 1', name='gh_identity_version'))
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    project_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, index=True)
    external_key: Mapped[str] = mapped_column(String(100), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    label: Mapped[str] = mapped_column(String(254), nullable=False)
    linked_user_id: Mapped[UUID | None] = mapped_column(Uuid)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class GitHubIdentityDecision(Base):
    __tablename__ = 'github_identity_decisions'
    __table_args__ = (scoped_fk('github_identities', 'identity_id', 'fk_gh_map_identity'),
        actor_fk('created_by', 'fk_gh_map_actor'), actor_fk('linked_user_id', 'fk_gh_map_user'),
        UniqueConstraint('identity_id', 'version', name='uq_gh_map_version'))
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    project_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    identity_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    linked_user_id: Mapped[UUID | None] = mapped_column(Uuid)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_by: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class GitHubEvidenceLink(Base):
    __tablename__ = 'github_evidence_links'
    __table_args__ = (scoped_fk('github_source_versions', 'source_id', 'fk_gh_link_source'),
        ForeignKeyConstraint(['workspace_id', 'project_id', 'package_id', 'evidence_id', 'evidence_revision'],
            ['evidence_revisions.workspace_id', 'evidence_revisions.project_id', 'evidence_revisions.package_id', 'evidence_revisions.evidence_id', 'evidence_revisions.number'], name='fk_gh_link_evidence'),
        actor_fk('created_by', 'fk_gh_link_actor'),
        UniqueConstraint('package_id', 'source_id', name='uq_gh_link_package_source'))
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    project_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    package_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    source_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    evidence_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    evidence_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    created_by: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
