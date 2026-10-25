"""Strict scope commands. All amounts are integer atoms or integer basis points."""
from typing import Annotated, Literal
from uuid import UUID
from pydantic import AfterValidator, Field, model_validator
from app.auth.schemas import Input, Name, Reason
from app.policies.schemas import AtomCount, PositiveAtoms, VersionNumber, Hash, Confirmed

MAX_DELIVERABLES = 30
MAX_ATTRIBUTIONS = 30
ROLES = ('implementation', 'design', 'testing', 'review', 'documentation', 'production', 'other')
STATES = ('draft', 'budget_approved', 'in_progress', 'submitted', 'changes_requested', 'cancelled', 'completed')
State = Literal['draft', 'budget_approved', 'in_progress', 'submitted', 'changes_requested', 'cancelled', 'completed']
WorkRole = Literal['implementation', 'design', 'testing', 'review', 'documentation', 'production', 'other']


def clean_text(value: str) -> str:
    value = value.strip()
    if not 8 <= len(value) <= 2000 or any(ord(c) < 32 and c not in '\n\t' for c in value):
        raise ValueError('Use 8 to 2,000 printable characters describing the outcome or requirement.')
    return value


ScopeText = Annotated[str, Field(max_length=2000), AfterValidator(clean_text)]
Criteria = Annotated[list[ScopeText], Field(min_length=1, max_length=20)]


class UnitAttribution(Input):
    user_id: UUID
    role: WorkRole
    atoms: PositiveAtoms


class PercentAttribution(Input):
    user_id: UUID
    role: WorkRole
    basis_points: Annotated[int, Field(strict=True, ge=1, le=10000)]


class UnitPlan(Input):
    mode: Literal['units']
    entries: list[UnitAttribution] = Field(default_factory=list, max_length=MAX_ATTRIBUTIONS)


class PercentPlan(Input):
    mode: Literal['percent']
    entries: list[PercentAttribution] = Field(default_factory=list, max_length=MAX_ATTRIBUTIONS)


AttributionPlan = Annotated[UnitPlan | PercentPlan, Field(discriminator='mode')]


class DeliverableInput(Input):
    id: UUID | None = None
    title: Name
    outcome: ScopeText
    acceptance_criteria: Criteria
    evidence_requirements: ScopeText
    budget_atoms: PositiveAtoms
    attribution: AttributionPlan

    @model_validator(mode='after')
    def validate_allocation(self):
        entries = self.attribution.entries
        if len({(e.user_id, e.role) for e in entries}) != len(entries):
            raise ValueError('Use only one attribution row per person and role in a deliverable.')
        if self.attribution.mode == 'units':
            if sum(e.atoms for e in entries) > self.budget_atoms:
                raise ValueError('Proposed units cannot exceed the deliverable budget.')
        elif sum(e.basis_points for e in entries) > 10000:
            raise ValueError('Proposed percentages cannot exceed 100%.')
        if len(set(self.acceptance_criteria)) != len(self.acceptance_criteria):
            raise ValueError('Acceptance criteria must be distinct.')
        return self


class ScopeInput(Input):
    title: Name
    outcome: ScopeText
    acceptance_criteria: Criteria
    evidence_requirements: ScopeText
    coordinator_id: UUID
    intended_contributor_ids: list[UUID] = Field(min_length=1, max_length=50)
    deliverables: list[DeliverableInput] = Field(default_factory=list, max_length=MAX_DELIVERABLES)

    @model_validator(mode='after')
    def validate_scope(self):
        ids = self.intended_contributor_ids
        if len(set(ids)) != len(ids):
            raise ValueError('Intended contributors must be unique.')
        if len(set(self.acceptance_criteria)) != len(self.acceptance_criteria):
            raise ValueError('Acceptance criteria must be distinct.')
        supplied_ids = [d.id for d in self.deliverables if d.id is not None]
        if len(set(supplied_ids)) != len(supplied_ids):
            raise ValueError('Each deliverable must have its own identifier.')
        if any(e.user_id not in ids for d in self.deliverables for e in d.attribution.entries):
            raise ValueError('Every attributed person must also be an intended contributor.')
        return self


class PackageCreate(Input):
    milestone_id: UUID
    allocation_id: UUID
    expected_allocation_version: VersionNumber
    scope: ScopeInput
    reason: Reason


class ScopeEdit(Input):
    expected_version: VersionNumber
    reviewed_hash: Hash
    scope: ScopeInput
    reason: Reason


class PackageAction(Input):
    action: Literal['approve_scope', 'start', 'submit', 'request_changes', 'withdraw', 'cancel', 'refresh_submission']
    expected_version: VersionNumber
    reviewed_hash: Hash
    reviewed: Confirmed
    reason: Reason
