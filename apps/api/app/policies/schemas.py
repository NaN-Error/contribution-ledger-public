from datetime import datetime, timezone
from typing import Annotated, Literal
from pydantic import Field, AfterValidator, BeforeValidator, model_validator, field_validator
from app.auth.schemas import Input, Name, Reason, Timezone

# Phase-3 arithmetic is deliberately bounded below JavaScript's safe-integer
# limit. API integers are strict: 1.5, "1000" and True are NOT unit atoms.
UNIT_SCALE = 1000
MAX_ATOMS = 1_000_000_000_000
AtomCount = Annotated[int, Field(strict=True, ge=0, le=MAX_ATOMS)]
PositiveAtoms = Annotated[int, Field(strict=True, ge=1, le=MAX_ATOMS)]
VersionNumber = Annotated[int, Field(strict=True, ge=1, le=1_000_000)]
Hash = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Category = Literal['code', 'art', 'design', 'qa', 'documentation', 'research',
                   'maintenance', 'marketing', 'production', 'community', 'other']
CATEGORIES = ['code', 'art', 'design', 'qa', 'documentation', 'research',
              'maintenance', 'marketing', 'production', 'community', 'other']
PoolKey = Literal['release', 'ongoing']


def policy_text(value: str) -> str:
    value = value.strip()
    if len(value) < 12 or len(value) > 2000 or any(ord(c) < 32 and c not in '\n\t' for c in value):
        raise ValueError('Explain this rule using 12 to 2,000 printable characters.')
    return value


PolicyText = Annotated[str, Field(max_length=2000), AfterValidator(policy_text)]


def real_true(value):
    if type(value) is not bool or value is not True:
        raise ValueError('An explicit true confirmation is required.')
    return value


def real_integer(value):
    if type(value) is not int:
        raise ValueError('Use an integer, not a boolean, decimal or string.')
    return value


Confirmed = Annotated[Literal[True], BeforeValidator(real_true)]
FixedOne = Annotated[Literal[1], BeforeValidator(real_integer)]
FixedScale = Annotated[Literal[1000], BeforeValidator(real_integer)]


class PoolRule(Input):
    key: PoolKey
    weight_bps: Annotated[int, Field(strict=True, ge=1, le=10000)]
    eligibility: Literal['accepted_release_work', 'accepted_work_in_accounting_period']

    @model_validator(mode='after')
    def matching_eligibility(self):
        expected = 'accepted_release_work' if self.key == 'release' else 'accepted_work_in_accounting_period'
        if self.eligibility != expected:
            raise ValueError('Pool eligibility must match its release or ongoing scope.')
        return self


class ReviewRule(Input):
    minimum_independent_reviewers: Annotated[int, Field(strict=True, ge=1, le=3)]
    beneficiary_cannot_be_sole_approver: Confirmed
    acceptance: Literal['budgeted_deliverables_only']


class GovernanceRule(Input):
    policy_approval: Literal['project_admin']
    budget_approval: Literal['project_admin']
    acknowledgement: Literal['snapshot_and_current_non_viewer_participants']


class AccountingRule(Input):
    cadence: Literal['calendar_month']
    start_day: FixedOne
    boundary_time: Literal['00:00:00']
    boundary_resolution: Literal['reject_ambiguous_or_nonexistent_local_time']
    revenue_basis: Literal['gross_receipts', 'net_storefront_settlements']
    allowed_deductions: list[Literal['platform_fees', 'refunds', 'sales_taxes', 'hosting',
                                     'tools', 'marketing', 'approved_external_services']] = Field(max_length=7)
    distributable_definition: PolicyText
    expense_approval: Literal['documented_project_admin_approval']
    reserve_rule: PolicyText
    capital_repayment_rule: PolicyText
    empty_pool_rule: Literal['block_close']
    dispute_rule: Literal['block_affected_close']

    @model_validator(mode='after')
    def valid_deductions(self):
        if len(set(self.allowed_deductions)) != len(self.allowed_deductions):
            raise ValueError('Do not repeat a deduction category.')
        if self.revenue_basis == 'net_storefront_settlements' and 'platform_fees' in self.allowed_deductions:
            raise ValueError('Do not deduct platform fees again from net storefront settlements.')
        # Pydantic's Literal[1] would otherwise accept True / 1.0.
        if type(self.start_day) is not int:
            raise ValueError('The accounting start day must be integer 1.')
        return self


class PolicyRules(Input):
    schema_version: FixedOne
    currency: Literal['USD']
    timezone: Timezone
    unit_scale: FixedScale
    eligible_categories: list[Category] = Field(min_length=1, max_length=11)
    review: ReviewRule
    governance: GovernanceRule
    pools: list[PoolRule] = Field(min_length=1, max_length=2)
    accounting: AccountingRule
    departure_rule: PolicyText
    attribution_rule: PolicyText
    unissued_units: Literal['unowned_until_accepted']

    @model_validator(mode='after')
    def validate_rules(self):
        if type(self.schema_version) is not int or type(self.unit_scale) is not int:
            raise ValueError('Schema version and unit scale must be integers.')
        if len(set(self.eligible_categories)) != len(self.eligible_categories):
            raise ValueError('Eligible categories must be unique.')
        if len({p.key for p in self.pools}) != len(self.pools):
            raise ValueError('Each pool must appear only once.')
        if sum(p.weight_bps for p in self.pools) != 10000:
            raise ValueError('Pool weights must total exactly 10,000 basis points (100%).')
        if not any(p.key == 'release' for p in self.pools):
            raise ValueError('This release requires a release pool.')
        return self


class PolicyCreate(Input):
    expected_latest_version: Annotated[int, Field(strict=True, ge=0, le=999_999)]
    title: Name
    rules: PolicyRules
    agreement_reference: Annotated[str, Field(min_length=8, max_length=500), AfterValidator(lambda s: s.strip())]
    reason: Reason

    @model_validator(mode='after')
    def reference_is_explicit(self):
        if len(self.agreement_reference) < 8 or any(ord(c) < 32 for c in self.agreement_reference):
            raise ValueError('Provide a printable agreement reference or an explicit synthetic-only reference.')
        return self


class PolicyApprove(Input):
    reviewed_content_hash: Hash
    expected_latest_version: VersionNumber
    examples_reviewed: Confirmed
    effective_at: datetime | None = None
    reason: Reason

    @field_validator('effective_at', mode='before')
    @classmethod
    def explicit_effective_instant(cls, value):
        import re
        if value is None or isinstance(value, datetime):
            return value
        if not isinstance(value, str) or not re.fullmatch(
            r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})', value
        ):
            raise ValueError('Use an ISO-8601 effective time with seconds and an explicit UTC offset.')
        return value

    @model_validator(mode='after')
    def exact_instant(self):
        if self.effective_at is not None:
            if self.effective_at.tzinfo is None or self.effective_at.utcoffset() is None:
                raise ValueError('Use an ISO-8601 effective time with an explicit UTC offset, or immediate approval.')
            self.effective_at = self.effective_at.astimezone(timezone.utc)
        return self


class PolicyAcknowledge(Input):
    reviewed_content_hash: Hash
    reviewed: Confirmed
