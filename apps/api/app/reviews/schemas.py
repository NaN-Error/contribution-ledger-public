from typing import Annotated, Literal
from uuid import UUID
from pydantic import Field, model_validator
from app.auth.schemas import Input, Reason
from app.policies.schemas import Hash, VersionNumber, Confirmed, PositiveAtoms
from app.contributions.work_packages.schemas import WorkRole
from app.evidence.schemas import SourceURL

ReviewerIds = Annotated[list[UUID], Field(min_length=1,max_length=3)]

class ReviewCreate(Input):
    request_id: UUID
    package_id: UUID
    deliverable_id: UUID
    expected_package_version: VersionNumber
    reviewed_target_hash: Hash
    reviewer_ids: ReviewerIds
    reason: Reason

class Finding(Input):
    criterion_id: Annotated[str, Field(min_length=1,max_length=80)]
    result: Literal['supported','unsupported','insufficient']
    evidence_refs: list[Annotated[str, Field(min_length=1,max_length=80)]] = Field(default_factory=list,max_length=100)
    explanation: Reason

class DecisionCreate(Input):
    request_id: UUID
    reviewed_target_hash: Hash
    decision: Literal['accept','request_evidence','reject']
    findings: list[Finding] = Field(min_length=1,max_length=60)
    evidence_reviewed: Confirmed
    independent: Confirmed
    reason: Reason

class Finalize(Input):
    request_id: UUID
    reviewed_decisions_hash: Hash
    reviewed: Confirmed
    reason: Reason

class DisputeCreate(Input):
    request_id: UUID
    award_id: UUID
    reason: Reason

class AssignResolver(Input):
    request_id: UUID
    reviewed_context_hash: Hash
    resolver_id: UUID
    reason: Reason

class NoteCreate(Input):
    request_id: UUID
    text: Annotated[str, Field(min_length=12,max_length=4000)]
    source_url: SourceURL | None = None

    @model_validator(mode='after')
    def printable(self):
        self.text = self.text.strip()
        if len(self.text)<12 or any(ord(c)<32 and c not in '\n\t' for c in self.text):
            raise ValueError('Provide at least 12 printable characters.')
        return self

class CorrectedAttribution(Input):
    user_id: UUID
    role: WorkRole
    atoms: PositiveAtoms

class ResolutionCreate(Input):
    request_id: UUID
    reviewed_context_hash: Hash
    disposition: Literal['uphold','reallocate']
    attributions: list[CorrectedAttribution] = Field(default_factory=list,max_length=100)
    reviewer_ids: ReviewerIds
    reason: Reason
