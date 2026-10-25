from datetime import datetime, timedelta
from typing import Annotated, Literal
from uuid import UUID
from pydantic import AwareDatetime, Field, model_validator
from app.auth.schemas import Input, Reason
from app.policies.schemas import VersionNumber, Hash, Confirmed
from app.evidence.schemas import EvidenceMetadata

GitHubID = Annotated[int, Field(strict=True, gt=0, le=2**53-1)]


class BeginAuthorization(Input):
    installation_id: GitHubID
    reason: Reason


class CompleteAuthorization(Input):
    state: str = Field(pattern=r'^[A-Za-z0-9_-]{43}$')
    code: str = Field(min_length=10, max_length=200, pattern=r'^[A-Za-z0-9_-]+$')


class ConnectRepositories(Input):
    flow_id: UUID
    reviewed_proof_hash: Hash
    repository_ids: list[GitHubID] = Field(min_length=1, max_length=20)
    sharing_confirmed: Confirmed
    reason: Reason

    @model_validator(mode='after')
    def unique_ids(self):
        if len(self.repository_ids) != len(set(self.repository_ids)):
            raise ValueError('Do not repeat repository IDs.')
        return self


class ChangeConnection(Input):
    expected_version: VersionNumber
    reason: Reason
    reviewed: Confirmed


class ImportCreate(Input):
    repository_id: UUID
    start_at: AwareDatetime
    end_before: AwareDatetime
    request_limit: int = Field(default=200, ge=10, le=1000, strict=True)
    entity_limit: int = Field(default=50, ge=1, le=200, strict=True)
    request_id: UUID
    reason: Reason
    reviewed: Confirmed

    @model_validator(mode='after')
    def window(self):
        if self.start_at >= self.end_before or self.end_before - self.start_at > timedelta(days=366):
            raise ValueError('Use an increasing, timezone-qualified range of at most 366 days.')
        if self.start_at.year < 1970 or self.end_before.year > 9998:
            raise ValueError('The import range is outside the supported dates.')
        return self


class ImportAction(Input):
    reason: Reason
    expected_version: VersionNumber


class IdentityMapping(Input):
    expected_version: VersionNumber
    user_id: UUID | None
    reviewed: Confirmed
    reason: Reason


class LinkSource(Input):
    package_id: UUID
    expected_package_version: VersionNumber
    reviewed_source_hash: Hash
    metadata: EvidenceMetadata
    reason: Reason
    request_id: UUID
    sharing_confirmed: Confirmed
