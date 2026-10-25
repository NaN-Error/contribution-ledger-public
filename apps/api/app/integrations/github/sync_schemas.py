from pydantic import Field
from app.auth.schemas import Input, Reason
from app.policies.schemas import Confirmed, VersionNumber


class ConfigureSync(Input):
    expected_version: int = Field(ge=0,le=2**31-1,strict=True)
    enabled: bool = Field(strict=True)
    interval_minutes: int = Field(default=360,ge=60,le=10080,strict=True)
    lookback_days: int = Field(default=7,ge=1,le=90,strict=True)
    request_limit: int = Field(default=200,ge=10,le=1000,strict=True)
    entity_limit: int = Field(default=50,ge=1,le=200,strict=True)
    reviewed: Confirmed
    reason: Reason


class RequestSync(Input):
    expected_version: VersionNumber
    reviewed: Confirmed
    reason: Reason
