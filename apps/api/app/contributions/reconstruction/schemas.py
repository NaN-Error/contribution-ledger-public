from datetime import datetime, timezone
from typing import Annotated, Literal
from uuid import UUID
from pydantic import Field, model_validator
from app.auth.schemas import Input, Name, Reason
from app.policies.schemas import Category, Hash, Confirmed, VersionNumber
from app.contributions.work_packages.schemas import ScopeInput, ScopeText


class BatchCreate(Input):
    request_id: UUID
    milestone_id: UUID
    title: Name
    start_at: datetime
    end_before: datetime
    historical_scope: ScopeText
    agreement_reference: Reason
    reason: Reason

    @model_validator(mode='after')
    def interval(self):
        if self.start_at.tzinfo is None or self.end_before.tzinfo is None:
            raise ValueError('Explicit timezone offsets are required.')
        self.start_at=self.start_at.astimezone(timezone.utc)
        self.end_before=self.end_before.astimezone(timezone.utc)
        if self.start_at>=self.end_before or self.end_before>datetime.now(timezone.utc):
            raise ValueError('A historical half-open interval must end in the past.')
        return self


class Command(Input):
    request_id: UUID
    expected_version: VersionNumber
    reason: Reason


class ReviewedCommand(Command):
    reviewed_hash: Hash
    reviewed: Confirmed


class ImportGroup(Command):
    import_id: UUID


class IdentityResolution(Input):
    external_key: Annotated[str,Field(min_length=1,max_length=100)]
    disposition: Literal['participant','context_only']
    user_id: UUID | None = None
    reason: Reason

    @model_validator(mode='after')
    def resolved(self):
        if (self.disposition=='participant') != (self.user_id is not None):
            raise ValueError('A participant resolution requires exactly one local participant.')
        return self


class CandidateDocument(Input):
    title: Name
    category: Category
    summary: ScopeText
    unresolved_questions: list[ScopeText] = Field(default_factory=list,max_length=30)
    identity_resolutions: list[IdentityResolution] = Field(default_factory=list,max_length=100)

    @model_validator(mode='after')
    def distinct(self):
        if len({x.external_key for x in self.identity_resolutions})!=len(self.identity_resolutions):
            raise ValueError('Identity resolutions must be unique.')
        return self


class CandidateCreate(Command):
    document: CandidateDocument


class CandidateEdit(Command):
    document: CandidateDocument


class CandidateDisposition(Command):
    disposition: Literal['reject','restore']


class Regroup(Command):
    candidate_ids: list[UUID] = Field(min_length=1,max_length=50)
    # A merge has >=2 candidates and no split IDs. A split has one candidate
    # and a nonempty proper subset of its claimed source IDs.
    split_source_ids: list[UUID] = Field(default_factory=list,max_length=100)
    title: Name

    @model_validator(mode='after')
    def mode(self):
        if len(set(self.candidate_ids))!=len(self.candidate_ids) or len(set(self.split_source_ids))!=len(self.split_source_ids):
            raise ValueError('Do not repeat identifiers.')
        if self.split_source_ids and len(self.candidate_ids)!=1 or not self.split_source_ids and len(self.candidate_ids)<2:
            raise ValueError('Choose a merge or a proper source split.')
        return self


class Promote(ReviewedCommand):
    candidate_id: UUID
    allocation_id: UUID
    expected_allocation_version: VersionNumber
    scope: ScopeInput
    project_sharing_confirmed: Confirmed


class MissingClaimCreate(Input):
    request_id: UUID
    title: Name
    category: Category
    description: ScopeText


class MissingClaimResolve(Command):
    claim_id: UUID
    disposition: Literal['included','declined']
    candidate_id: UUID | None = None

    @model_validator(mode='after')
    def linked(self):
        if (self.disposition=='included') != (self.candidate_id is not None):
            raise ValueError('Included claims require an explicit candidate link.')
        return self
