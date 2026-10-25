from datetime import timedelta
import re
from typing import Annotated, Literal
from urllib.parse import urlsplit
from uuid import UUID
from pydantic import AwareDatetime, Field, field_validator, model_validator
from app.auth.schemas import Input, Reason
from app.policies.schemas import Confirmed, Hash

MAX_ATOMS = 1_000_000_000_000
Atoms = Annotated[int, Field(strict=True, ge=0, le=MAX_ATOMS)]
KEY = re.compile(r'^(?:github:[1-9][0-9]{0,18}|email:[a-f0-9]{64}|unknown:[a-f0-9]{64}|manual:[a-f0-9-]{36}|local:[a-f0-9-]{36})$')


def repository_name(value):
    url = urlsplit(value.strip())
    if (url.scheme != 'https' or url.netloc.lower() != 'github.com' or url.username or url.password
            or url.query or url.fragment or '%' in url.path):
        raise ValueError('Paste an HTTPS GitHub repository address, without credentials, query or fragment.')
    parts = url.path.rstrip('/').split('/')
    if len(parts) != 3 or parts[0] or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9-]{0,38}', parts[1]):
        raise ValueError('Use a repository address such as https://github.com/team/project.')
    repo = parts[2].removesuffix('.git')
    if not re.fullmatch(r'[A-Za-z0-9_.-]{1,100}', repo) or repo in {'.', '..'}:
        raise ValueError('The repository name is invalid.')
    return parts[1] + '/' + repo


class AnalysisCreate(Input):
    request_id: UUID
    repository_urls: list[str] = Field(default_factory=list, max_length=8)
    import_ids: list[UUID] = Field(default_factory=list, max_length=8)
    start_at: AwareDatetime
    end_before: AwareDatetime
    public_read_confirmed: Confirmed
    connection_id: UUID | None = None

    @field_validator('repository_urls')
    @classmethod
    def urls(cls, values):
        names = [repository_name(v) for v in values]
        if len(set(n.casefold() for n in names)) != len(names):
            raise ValueError('Select each repository once.')
        return ['https://github.com/' + name for name in names]

    @model_validator(mode='after')
    def scope(self):
        if not 1 <= len(self.repository_urls) + len(self.import_ids) <= 8:
            raise ValueError('Choose one to eight public repositories or completed authorized imports.')
        if len(set(self.import_ids)) != len(self.import_ids):
            raise ValueError('Select each import once.')
        if not timedelta(0) < self.end_before - self.start_at <= timedelta(days=366):
            raise ValueError('Use an increasing UTC range of at most 366 days.')
        if self.start_at.year < 1970 or self.end_before.year > 2099:
            raise ValueError('Use supported GitHub dates from 1970 through 2099.')
        return self


class DraftChange(Input):
    request_id: UUID
    expected_version: int = Field(strict=True, ge=0)
    reason: Reason


class Attribution(Input):
    contributor_key: str = Field(max_length=100)
    atoms: Atoms

    @field_validator('contributor_key')
    @classmethod
    def key(cls, value):
        if not KEY.fullmatch(value):
            raise ValueError('Select a retained contributor identifier.')
        return value


class Proposal(DraftChange):
    report_id: UUID
    outcome_id: str = Field(pattern=r'^[a-f0-9]{64}$')
    proposed_atoms: Atoms
    entries: list[Attribution] = Field(default_factory=list, max_length=30)
    rationale: str = Field(min_length=8, max_length=2000)
    rubric_version: Literal['outcome-review-v1'] = 'outcome-review-v1'

    @model_validator(mode='after')
    def reconcile(self):
        if len({e.contributor_key for e in self.entries}) != len(self.entries):
            raise ValueError('Combine each contributor once.')
        if sum(e.atoms for e in self.entries) > self.proposed_atoms:
            raise ValueError('Attribution exceeds the proposed outcome units.')
        return self


class ManualContribution(DraftChange):
    contribution_id: UUID | None = None
    title: str = Field(min_length=2, max_length=200)
    category: Literal['code','art','design','audio','testing','documentation','production','other']
    description: str = Field(min_length=8, max_length=6000)
    contributor_key: str | None = Field(default=None, max_length=100)
    contributor_name: str = Field(default='', max_length=120)
    evidence: str = Field(min_length=8, max_length=4000)
    performed_at: AwareDatetime
    repository: str | None = Field(default=None, max_length=150)
    proposed_atoms: Atoms = 0
    rationale: str = Field(min_length=8, max_length=2000)


class IdentityAlias(DraftChange):
    source_key: str = Field(max_length=100)
    target_key: str = Field(max_length=100)


class ManualDisposition(DraftChange):
    contribution_id: UUID
    status: Literal['proposed','excluded']


class Scenario(DraftChange):
    amount_cents: int = Field(strict=True, ge=0, le=1_000_000_000_000)


class RunAction(Input):
    expected_version: int = Field(strict=True, ge=1)


class ShareReport(DraftChange):
    report_id: UUID
    reviewed_hash: Hash
    sharing_confirmed: Confirmed


class RevokeReport(Input):
    request_id: UUID
    reason: Reason


from app.contributions.reconstruction.schemas import IdentityResolution
from app.contributions.work_packages.schemas import ScopeInput


class Handoff(DraftChange):
    report_id: UUID
    outcome_id: Hash
    batch_id: UUID
    expected_batch_version: int = Field(strict=True, ge=1)
    reviewed_hash: Hash
    project_sharing_confirmed: Confirmed
    identities: list[IdentityResolution] = Field(min_length=1, max_length=100)
    allocation_id: UUID
    expected_allocation_version: int = Field(strict=True, ge=1)
    scope: ScopeInput

    @model_validator(mode='after')
    def unique_identities(self):
        if len({i.external_key for i in self.identities}) != len(self.identities):
            raise ValueError('Review every identity exactly once.')
        return self
