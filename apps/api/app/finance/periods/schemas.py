"""Bounded commands. Cents are integers; imported CSV numbers are parsed explicitly."""
from datetime import datetime, timezone
from typing import Annotated, Literal
from uuid import UUID
import unicodedata
from pydantic import AfterValidator, Field, model_validator, field_validator
from app.auth.schemas import Input, Name
from app.policies.schemas import Confirmed, Hash, Reason
from app.evidence.schemas import FileInput
from app.finance.calculation.engine import MAX_CENTS


def printable(value: str) -> str:
    value = unicodedata.normalize('NFC', value).strip()
    if len(value) < 2 or any(unicodedata.category(c) in {'Cc', 'Cf'} for c in value):
        raise ValueError('Use a nonempty printable reference without hidden controls.')
    return value


Reference = Annotated[str, Field(min_length=2, max_length=200), AfterValidator(printable)]
Cents = Annotated[int, Field(strict=True, ge=1, le=MAX_CENTS)]
Deduction = Literal['platform_fees','refunds','sales_taxes','hosting','tools','marketing','approved_external_services']
Kind = Literal['receipt','deduction','reserve_hold','reserve_release','adjustment_credit','adjustment_debit']


class Command(Input):
    request_id: UUID
    reason: Reason


class CreatePeriod(Command):
    month: Annotated[str, Field(pattern=r'^\d{4}-(0[1-9]|1[0-2])$')]
    source_policy_id: UUID
    calculation_policy_id: UUID
    agreement_reference: Reference
    deficit_rule: Literal['carry_negative_balance_forward']
    synthetic_only: Confirmed
    period_rules_reviewed: Confirmed


class UploadDocument(Command):
    title: Name
    provenance: Reference
    file: FileInput


class EntryInput(Input):
    document_id: UUID
    kind: Kind
    amount_cents: Cents
    source_name: Reference
    statement_reference: Reference
    line_reference: Reference
    description: Annotated[str, Field(min_length=8, max_length=1000)]
    revenue_basis: Literal['gross_receipts','net_storefront_settlements'] | None = None
    deduction_category: Deduction | None = None
    already_deducted: list[Deduction] = Field(default_factory=list, max_length=7)
    related_entry_id: UUID | None = None
    separate_charge_confirmed: Annotated[bool, Field(strict=True)] = False

    @model_validator(mode='after')
    def kind_fields(self):
        if len(set(self.already_deducted)) != len(self.already_deducted):
            raise ValueError('Already-deducted categories must be unique.')
        if self.kind == 'receipt':
            if not self.revenue_basis or self.deduction_category or self.related_entry_id:
                raise ValueError('A receipt requires a basis and cannot be a deduction/correction.')
            if self.revenue_basis == 'gross_receipts' and self.already_deducted:
                raise ValueError('Gross receipts cannot declare components already deducted.')
            if self.revenue_basis == 'net_storefront_settlements' and 'platform_fees' not in self.already_deducted:
                raise ValueError('Net settlements must explicitly include platform fees among already-deducted components.')
        elif self.revenue_basis or self.already_deducted:
            raise ValueError('Only receipts carry a revenue basis or already-deducted components.')
        if self.kind == 'deduction':
            if not self.deduction_category or self.separate_charge_confirmed is not True:
                raise ValueError('A deduction requires its category and an explicit separate-charge declaration.')
            if self.deduction_category in {'platform_fees','refunds','sales_taxes'} and not self.related_entry_id:
                raise ValueError('A settlement-related deduction must reference its receipt.')
        elif self.deduction_category:
            raise ValueError('Only a deduction has a deduction category.')
        if self.kind.startswith('adjustment_') and not self.related_entry_id:
            raise ValueError('A correction requires a prior closed financial entry.')
        if self.kind.startswith('reserve_') and self.related_entry_id:
            raise ValueError('Reserve movements use the agreed period reserve, not another entry.')
        return self


class AddEntry(Command):
    entry: EntryInput


class ImportReceipts(Command):
    document_id: UUID
    source_name: Reference
    statement_reference: Reference
    revenue_basis: Literal['gross_receipts','net_storefront_settlements']
    already_deducted: list[Deduction] = Field(default_factory=list, max_length=7)
    # Canonical CSV only, not an arbitrary storefront file mapper.
    csv_text: Annotated[str, Field(min_length=1, max_length=65536)]


class DecideEntry(Command):
    reviewed_entry_hash: Hash
    expected_decision_hash: Hash | None = None
    action: Literal['approve','reject','void']
    document_reviewed: Confirmed


class Propose(Command):
    kind: Literal['close','release_correction']
    reviewed_preview_hash: Hash
    financial_records_reviewed: Confirmed
    contribution_scope_reviewed: Confirmed
    synthetic_only: Confirmed


class ApproveProposal(Command):
    reviewed_proposal_hash: Hash
    action: Literal['approve','reject']
    reviewed: Confirmed
    synthetic_only: Confirmed


class RecordPayment(Command):
    recipient_id: UUID
    amount_cents: Cents
    provider: Reference
    external_reference: Reference
    paid_at: datetime
    reviewed_close_hash: Hash
    externally_completed: Confirmed
    synthetic_only: Confirmed
    overpayment_acknowledged: Annotated[bool, Field(strict=True)] = False

    @field_validator('paid_at', mode='before')
    @classmethod
    def timestamp_string(cls, value):
        import re
        if isinstance(value, datetime): return value
        if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})', value):
            raise ValueError('Use an ISO timestamp with seconds and an explicit UTC offset.')
        return value

    @field_validator('paid_at')
    @classmethod
    def aware(cls, value):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError('An explicit timestamp offset is required.')
        return value.astimezone(timezone.utc)


class VoidPayment(Command):
    reviewed_payment_hash: Hash
    bookkeeping_correction_only: Confirmed
