"""Immutable review, assignment, vote, dispute and notification records."""
from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import CheckConstraint, DateTime, ForeignKeyConstraint, Integer, JSON, String, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base
from app.policies.models import project_fk, policy_fk, actor_fk
from app.contributions.work_packages.models import package_fk


def review_fk(name):
    return ForeignKeyConstraint(['workspace_id','project_id','package_id','review_id'],
        ['review_rounds.workspace_id','review_rounds.project_id','review_rounds.package_id','review_rounds.id'], name=name)


def dispute_fk(name, **kwargs):
    return ForeignKeyConstraint(['workspace_id','project_id','package_id','dispute_id'],
        ['credit_disputes.workspace_id','credit_disputes.project_id','credit_disputes.package_id','credit_disputes.id'], name=name, **kwargs)


class ReviewRound(Base):
    __tablename__ = 'review_rounds'
    __table_args__ = (package_fk('fk_review_package'), policy_fk('fk_review_policy'),
        actor_fk('created_by','fk_review_author'), dispute_fk('fk_review_dispute', use_alter=True),
        ForeignKeyConstraint(['workspace_id','project_id','package_id','submission_id'],
            ['work_submissions.workspace_id','work_submissions.project_id','work_submissions.package_id','work_submissions.id'], name='fk_review_submission'),
        ForeignKeyConstraint(['workspace_id','project_id','package_id','evidence_snapshot_id'],
            ['evidence_snapshots.workspace_id','evidence_snapshots.project_id','evidence_snapshots.package_id','evidence_snapshots.id'], name='fk_review_evidence'),
        UniqueConstraint('workspace_id','project_id','package_id','id',name='uq_review_scope'),
        UniqueConstraint('workspace_id','project_id','request_id',name='uq_review_request'),
        UniqueConstraint('package_id','deliverable_id','number',name='uq_review_number'),
        CheckConstraint("kind IN ('award','uphold','reallocate')",name='review_kind'),
        CheckConstraint("(kind = 'award' AND dispute_id IS NULL) OR (kind <> 'award' AND dispute_id IS NOT NULL)",name='review_dispute_kind'),
        CheckConstraint('number >= 1 AND number <= 1000 AND minimum_reviewers BETWEEN 1 AND 3',name='review_bounds'))
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    project_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, index=True)
    package_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    deliverable_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    policy_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    submission_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    evidence_snapshot_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    dispute_id: Mapped[UUID | None] = mapped_column(Uuid)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    minimum_reviewers: Mapped[int] = mapped_column(Integer, nullable=False)
    target: Mapped[dict] = mapped_column(JSON, nullable=False)
    target_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    request_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class ReviewAssignment(Base):
    __tablename__ = 'review_assignments'
    __table_args__ = (review_fk('fk_review_assignment_round'), actor_fk('reviewer_id','fk_assigned_reviewer'))
    review_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    reviewer_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    workspace_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    project_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    package_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class ReviewDecision(Base):
    __tablename__ = 'review_decisions'
    __table_args__ = (review_fk('fk_review_decision_round'), actor_fk('reviewer_id','fk_review_decider'),
        ForeignKeyConstraint(['review_id','reviewer_id'], ['review_assignments.review_id','review_assignments.reviewer_id'], name='fk_decision_assignment'),
        UniqueConstraint('review_id','reviewer_id', name='uq_review_decider'),
        UniqueConstraint('workspace_id','project_id','request_id',name='uq_review_decision_request'),
        CheckConstraint("decision IN ('accept','request_evidence','reject')",name='review_decision_choice'))
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    project_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    package_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    review_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    reviewer_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    decision: Mapped[str] = mapped_column(String(24), nullable=False)
    findings: Mapped[list] = mapped_column(JSON, nullable=False)
    reviewed_target_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    request_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class CreditDispute(Base):
    __tablename__ = 'credit_disputes'
    __table_args__ = (package_fk('fk_dispute_package'), actor_fk('opened_by','fk_dispute_author'),
        ForeignKeyConstraint(['workspace_id','project_id','package_id','award_id'],
            ['credit_awards.workspace_id','credit_awards.project_id','credit_awards.package_id','credit_awards.id'], name='fk_dispute_award'),
        UniqueConstraint('workspace_id','project_id','package_id','id',name='uq_dispute_scope'),
        UniqueConstraint('workspace_id','project_id','request_id',name='uq_dispute_request'))
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    project_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, index=True)
    package_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    award_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    opened_by: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    request_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class DisputeAssignment(Base):
    __tablename__ = 'dispute_assignments'
    __table_args__ = (dispute_fk('fk_dispute_assignment'), actor_fk('assigned_by','fk_dispute_assigner'),
        actor_fk('resolver_id','fk_dispute_resolver'), CheckConstraint('number >= 1 AND number <= 100',name='dispute_assignment_number'),
        UniqueConstraint('workspace_id','project_id','request_id',name='uq_dispute_assignment_request'))
    dispute_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    number: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    project_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    package_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    resolver_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    assigned_by: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    request_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class DisputeNote(Base):
    __tablename__ = 'dispute_notes'
    __table_args__ = (dispute_fk('fk_dispute_note'), actor_fk('created_by','fk_dispute_note_author'),
        UniqueConstraint('workspace_id','project_id','request_id',name='uq_dispute_note_request'))
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    project_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    package_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    dispute_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    created_by: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    text: Mapped[str] = mapped_column(String(4000), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(2000))
    request_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class DisputeResolution(Base):
    __tablename__ = 'dispute_resolutions'
    __table_args__ = (dispute_fk('fk_dispute_resolution'), review_fk('fk_resolution_review'), actor_fk('resolved_by','fk_resolution_actor'),
        UniqueConstraint('dispute_id',name='uq_dispute_resolved_once'),
        UniqueConstraint('review_id',name='uq_resolution_review_once'),
        UniqueConstraint('workspace_id','project_id','package_id','id',name='uq_resolution_scope'),
        UniqueConstraint('workspace_id','project_id','request_id',name='uq_resolution_request'),
        CheckConstraint("disposition IN ('uphold','reallocate')",name='resolution_disposition'))
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    project_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    package_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    dispute_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    review_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    resolved_by: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    disposition: Mapped[str] = mapped_column(String(16), nullable=False)
    request_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class ParticipantNotification(Base):
    __tablename__ = 'participant_notifications'
    __table_args__ = (project_fk('fk_notification_project'), actor_fk('recipient_id','fk_notification_recipient'))
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    project_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, index=True)
    recipient_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    subject_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    message: Mapped[str] = mapped_column(String(300), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
