"""Phase-13 records are append-only. Status is derived, never edited in place.

Every foreign key includes the tenant/project scope. SQL triggers added by 0013
reject ordinary UPDATE/DELETE/TRUNCATE. The operator/database owner is still a
trusted recovery boundary, not an adversary defeated by these triggers.
"""
from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import (BigInteger, CheckConstraint, DateTime, ForeignKeyConstraint,
                        Integer, JSON, String, UniqueConstraint, Uuid, func)
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base
from app.policies.models import project_fk, actor_fk


def scoped_fk(table: str, field: str, name: str):
    return ForeignKeyConstraint(['workspace_id', 'project_id', field],
        [f'{table}.workspace_id', f'{table}.project_id', f'{table}.id'], name=name)


def common(name: str):
    return (project_fk(f'fk_{name}_project'), actor_fk('created_by', f'fk_{name}_author'),
            UniqueConstraint('workspace_id', 'project_id', 'id', name=f'uq_{name}_scope'),
            UniqueConstraint('project_id', 'created_by', 'request_id', name=f'uq_{name}_request'))


class Record:
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    workspace_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    project_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, index=True)
    created_by: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    request_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    record: Mapped[dict] = mapped_column(JSON, nullable=False)
    record_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class FinancePeriod(Record, Base):
    __tablename__ = 'finance_periods'
    __table_args__ = (*common('finance_period'),
        scoped_fk('policy_versions', 'source_policy_id', 'fk_finance_source_policy'),
        scoped_fk('policy_versions', 'calculation_policy_id', 'fk_finance_calculation_policy'),
        scoped_fk('finance_periods', 'previous_period_id', 'fk_finance_previous_period'),
        UniqueConstraint('project_id', 'month', name='uq_finance_project_month'),
        UniqueConstraint('previous_period_id', name='uq_finance_previous_successor'),
        CheckConstraint('end_at > start_at', name='finance_period_order'))
    month: Mapped[str] = mapped_column(String(7), nullable=False)
    timezone: Mapped[str] = mapped_column(String(80), nullable=False)
    source_policy_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    calculation_policy_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    previous_period_id: Mapped[UUID | None] = mapped_column(Uuid)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class FinanceDocument(Record, Base):
    __tablename__ = 'finance_documents'
    __table_args__ = (*common('finance_document'),
        scoped_fk('finance_periods', 'period_id', 'fk_finance_document_period'),
        CheckConstraint('size_bytes > 0 AND size_bytes <= 2097152', name='finance_document_size'))
    period_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, index=True)
    object_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    backend: Mapped[str] = mapped_column(String(20), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)


class FinanceEntry(Record, Base):
    __tablename__ = 'finance_entries'
    __table_args__ = (*common('finance_entry'),
        scoped_fk('finance_periods', 'period_id', 'fk_finance_entry_period'),
        scoped_fk('finance_documents', 'document_id', 'fk_finance_entry_document'),
        scoped_fk('finance_entries', 'related_entry_id', 'fk_finance_entry_related'),
        UniqueConstraint('project_id', 'source_key', name='uq_finance_source_line'),
        CheckConstraint('amount_cents > 0 AND amount_cents <= 1000000000000', name='finance_entry_amount'),
        CheckConstraint("kind IN ('receipt','deduction','reserve_hold','reserve_release','adjustment_credit','adjustment_debit')", name='finance_entry_kind'))
    period_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, index=True)
    document_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    related_entry_id: Mapped[UUID | None] = mapped_column(Uuid)
    source_key: Mapped[str] = mapped_column(String(64), nullable=False)
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    amount_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)


class FinanceEntryDecision(Record, Base):
    __tablename__ = 'finance_entry_decisions'
    __table_args__ = (*common('finance_entry_decision'),
        scoped_fk('finance_entries', 'entry_id', 'fk_finance_decision_entry'),
        UniqueConstraint('entry_id', 'sequence', name='uq_finance_entry_decision_sequence'),
        CheckConstraint('sequence >= 1', name='finance_entry_decision_sequence'))
    entry_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, index=True)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)


class ReleaseShareSnapshot(Record, Base):
    __tablename__ = 'release_share_snapshots'
    __table_args__ = (*common('release_share'),
        scoped_fk('policy_versions', 'source_policy_id', 'fk_release_share_policy'),
        scoped_fk('release_share_snapshots', 'predecessor_id', 'fk_release_share_predecessor'),
        UniqueConstraint('project_id', 'source_policy_id', 'version', name='uq_release_share_version'),
        UniqueConstraint('predecessor_id', name='uq_release_share_successor'),
        CheckConstraint('version >= 1', name='release_share_version'))
    source_policy_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    predecessor_id: Mapped[UUID | None] = mapped_column(Uuid)
    version: Mapped[int] = mapped_column(Integer, nullable=False)


class FinanceProposal(Record, Base):
    __tablename__ = 'finance_proposals'
    __table_args__ = (*common('finance_proposal'),
        scoped_fk('finance_periods', 'period_id', 'fk_finance_proposal_period'),
        CheckConstraint("kind IN ('close','release_correction')", name='finance_proposal_kind'))
    period_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(24), nullable=False)


class FinanceApproval(Record, Base):
    __tablename__ = 'finance_approvals'
    __table_args__ = (*common('finance_approval'),
        scoped_fk('finance_proposals', 'proposal_id', 'fk_finance_approval_proposal'),
        UniqueConstraint('proposal_id', name='uq_finance_proposal_decision'))
    proposal_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)


class DistributionClose(Record, Base):
    __tablename__ = 'distribution_closes'
    __table_args__ = (*common('distribution_close'),
        scoped_fk('finance_periods', 'period_id', 'fk_distribution_period'),
        scoped_fk('finance_proposals', 'proposal_id', 'fk_distribution_proposal'),
        scoped_fk('release_share_snapshots', 'release_snapshot_id', 'fk_distribution_release'),
        UniqueConstraint('period_id', name='uq_distribution_period'),
        UniqueConstraint('proposal_id', name='uq_distribution_proposal'))
    period_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    proposal_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    release_snapshot_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)


class ExternalPayment(Record, Base):
    __tablename__ = 'external_payments'
    __table_args__ = (*common('external_payment'),
        scoped_fk('distribution_closes', 'close_id', 'fk_external_payment_close'),
        actor_fk('recipient_id', 'fk_external_payment_recipient'),
        UniqueConstraint('project_id', 'external_key', name='uq_external_payment_reference'),
        CheckConstraint('amount_cents > 0 AND amount_cents <= 1000000000000', name='external_payment_amount'))
    close_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, index=True)
    recipient_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    amount_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    external_key: Mapped[str] = mapped_column(String(64), nullable=False)


class PaymentVoid(Record, Base):
    __tablename__ = 'payment_voids'
    __table_args__ = (*common('payment_void'),
        scoped_fk('external_payments', 'payment_id', 'fk_payment_void_payment'),
        UniqueConstraint('payment_id', name='uq_payment_void_once'))
    payment_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)


class FinanceReceiptImport(Record, Base):
    __tablename__ = 'finance_receipt_imports'
    __table_args__ = (*common('finance_receipt_import'),
        scoped_fk('finance_periods', 'period_id', 'fk_finance_receipt_import_period'))
    period_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, index=True)
