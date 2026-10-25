from datetime import date
from typing import Annotated, Literal
from uuid import UUID
import re
import unicodedata
from urllib.parse import urlsplit, unquote
from pydantic import AfterValidator, Field, model_validator
from app.auth.schemas import Input, Name, Reason
from app.policies.schemas import VersionNumber, Hash, Confirmed

MAX_UPLOAD_BYTES = 2 * 1024 * 1024
MAX_ENCODED_BYTES = 4 * ((MAX_UPLOAD_BYTES + 2) // 3)
UPLOAD_JSON_LIMIT = MAX_ENCODED_BYTES + 65536
MAX_TEXT_BYTES = 256 * 1024
MAX_ITEMS = 100
MAX_REVISIONS = 50


def plain_text(value: str) -> str:
    value = value.strip()
    if not value or any(unicodedata.category(c) in {'Cc', 'Cf'} and c not in '\n\t' for c in value):
        raise ValueError('Use visible text without hidden controls.')
    return value


Text = Annotated[str, Field(min_length=1, max_length=12000), AfterValidator(plain_text)]
ShortText = Annotated[str, Field(min_length=3, max_length=1000), AfterValidator(plain_text)]


def link(value: str) -> str:
    value = value.strip()
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError: raise ValueError('Use a complete HTTPS source URL.') from None
    if (len(value) > 2000 or parsed.scheme != 'https' or not parsed.hostname or parsed.username
        or parsed.password or '\\' in value or any(c.isspace() or ord(c) < 32 for c in unquote(value))
        or not re.fullmatch(r'[A-Za-z0-9.:-]+', parsed.netloc) or '%' in parsed.netloc
        or port not in {None, 443}):
        raise ValueError('Use an HTTPS source URL without credentials or a custom port.')
    return value


SourceURL = Annotated[str, Field(max_length=2000), AfterValidator(link)]


class EvidenceMetadata(Input):
    title: Name
    description: ShortText
    claimed_authors: ShortText
    provenance: ShortText
    occurred_on: date
    category: Literal['code', 'art', 'design', 'qa', 'research', 'documentation', 'maintenance', 'marketing', 'other']
    visibility: Literal['project', 'restricted'] = 'project'
    inclusion: Literal['included', 'excluded', 'unavailable'] = 'included'
    omission_reason: ShortText | None = None
    deliverable_ids: list[UUID] = Field(default_factory=list, max_length=30)

    @model_validator(mode='after')
    def omission(self):
        if self.inclusion != 'included' and not self.omission_reason:
            raise ValueError('Explain why evidence is excluded or unavailable.')
        if self.inclusion == 'included' and self.omission_reason:
            raise ValueError('Included evidence must not carry an omission reason.')
        if len(set(self.deliverable_ids)) != len(self.deliverable_ids):
            raise ValueError('Do not duplicate a deliverable reference.')
        return self


class FileInput(Input):
    filename: str = Field(min_length=1, max_length=120)
    media_type: str = Field(min_length=1, max_length=80)
    content_base64: str = Field(min_length=1, max_length=MAX_ENCODED_BYTES)


class EvidenceCreate(Input):
    kind: Literal['statement', 'link', 'file', 'unavailable']
    metadata: EvidenceMetadata
    text: Text | None = None
    source_url: SourceURL | None = None
    file: FileInput | None = None
    expected_package_version: VersionNumber
    request_id: UUID
    reason: Reason

    @model_validator(mode='after')
    def content(self):
        required = {'statement': self.text, 'link': self.source_url, 'file': self.file, 'unavailable': True}
        if required[self.kind] is None:
            raise ValueError('Provide content for the selected evidence type.')
        if (self.kind != 'statement' and self.text is not None or self.kind != 'link' and self.source_url is not None
            or self.kind != 'file' and self.file is not None):
            raise ValueError('Evidence content must match its type.')
        if self.kind == 'unavailable' and self.metadata.inclusion != 'unavailable':
            raise ValueError('Missing-evidence entries must remain explicitly unavailable.')
        return self


class EvidenceRevise(Input):
    metadata: EvidenceMetadata
    text: Text | None = None
    source_url: SourceURL | None = None
    file: FileInput | None = None  # null retains current file, not an arbitrary object reference
    expected_revision: VersionNumber
    expected_package_version: VersionNumber
    request_id: UUID
    reason: Reason


class SnapshotCreate(Input):
    expected_package_version: VersionNumber
    reviewed_hash: Hash
    reviewed: Confirmed
    reason: Reason


class RetireArtifacts(Input):
    expected_package_version: VersionNumber
    reviewed: Confirmed
    reason: Reason
