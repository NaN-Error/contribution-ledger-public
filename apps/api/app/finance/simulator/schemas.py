from typing import Annotated
from uuid import UUID
from pydantic import Field
from app.auth.schemas import Input, Name
from app.policies.schemas import Confirmed, Hash
from app.finance.calculation.engine import MAX_CENTS


class PreviewInput(Input):
    source_policy_id: UUID
    calculation_policy_id: UUID
    month: Annotated[str, Field(pattern=r'^\d{4}-(0[1-9]|1[0-2])$')]
    amount_cents: Annotated[int, Field(strict=True, ge=0, le=MAX_CENTS)]


class SaveScenario(Input):
    request_id: UUID
    title: Name
    input: PreviewInput
    reviewed_snapshot_hash: Hash
    hypothetical_confirmed: Confirmed
