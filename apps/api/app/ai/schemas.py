from datetime import datetime
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

class Strict(BaseModel):
    model_config=ConfigDict(extra='forbid',hide_input_in_errors=True,str_strip_whitespace=True)
class Reason(Strict):
    reason:str=Field(min_length=8,max_length=500)
class ConnectionCreate(Reason):
    request_id:UUID
    provider:Literal['mock','openai','anthropic','gemini']
    label:str=Field(min_length=2,max_length=100)
    api_key:SecretStr|None=None
    permission_reference:str=Field(min_length=8,max_length=500)
    monthly_limit_microusd:int=Field(default=0,ge=0,le=10**9,strict=True)
    allow_project_use:bool=Field(default=False,strict=True)
class ConnectionUpdate(Reason):
    expected_version:int=Field(ge=1,strict=True)
    label:str=Field(min_length=2,max_length=100)
    monthly_limit_microusd:int=Field(ge=0,le=10**9,strict=True)
    allow_project_use:bool=Field(strict=True)
class Rotate(Reason):
    expected_version:int=Field(ge=1,strict=True)
    api_key:SecretStr
class Revoke(Reason):
    expected_version:int=Field(ge=1,strict=True)
class CatalogRequest(Strict):
    request_id:UUID
class PriceCreate(Reason):
    model_id:UUID
    input_rate:int=Field(ge=0,le=10**10,strict=True)
    output_rate:int=Field(ge=0,le=10**10,strict=True)
    source_reference:str=Field(min_length=8,max_length=500)
    valid_until:datetime
    @field_validator('valid_until')
    @classmethod
    def aware(cls,v):
        if v.tzinfo is None or v.utcoffset() is None:raise ValueError('Timezone required')
        return v
class ProbeRequest(Strict):
    request_id:UUID
    quote_hash:str=Field(pattern=r'^[0-9a-f]{64}$')
    confirmed_reservation_microusd:int=Field(ge=0,le=10**9,strict=True)
    payer_approved:bool=Field(strict=True)
    @field_validator('payer_approved')
    @classmethod
    def affirmative(cls,v):
        if not v:raise ValueError('Explicit payer approval required')
        return v
class Resolution(Reason):
    actual_microusd:int=Field(ge=0,le=10**12,strict=True)
    source_reference:str=Field(min_length=8,max_length=500)
class ProfileCreate(Reason):
    purpose:Literal['compatibility','evidence']='compatibility'
    max_output_tokens:int=Field(default=4096,ge=512,le=8192,strict=True)
    connection_id:UUID
    model_id:UUID
    data_policy_reference:str=Field(min_length=12,max_length=500)
    # Enforced structured output, no tools, retries or implicit fallback.
    title:str=Field(min_length=2,max_length=100)
class ProfileApprove(Reason):
    reviewed_hash:str=Field(pattern=r'^[0-9a-f]{64}$')
    expected_active_profile_id:UUID|None=None
