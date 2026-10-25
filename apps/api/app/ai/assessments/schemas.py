from datetime import datetime
from typing import Literal
from uuid import UUID
from pydantic import Field,field_validator,model_validator
from app.ai.schemas import Strict,Reason,ProbeRequest

Hash = str

class PacketCreate(Reason):
    request_id:UUID
    package_id:UUID
    deliverable_id:UUID
    profile_id:UUID
    expected_package_version:int=Field(ge=1,strict=True)
    evidence_ids:list[UUID]=Field(default_factory=list,max_length=100)
    include_restricted:bool=Field(default=False,strict=True)
    excluded_paths:list[str]=Field(default_factory=list,max_length=30)
    @field_validator('evidence_ids')
    @classmethod
    def unique_ids(cls,v):
        if len(v)!=len(set(v)):raise ValueError('Duplicate evidence selection')
        return v
    @field_validator('excluded_paths')
    @classmethod
    def safe_patterns(cls,v):
        if any(not 1<=len(p)<=200 or '\x00' in p or '://' in p for p in v):raise ValueError('Bounded path patterns required')
        return v

class PlanCreate(Reason):
    request_id:UUID
    packet_id:UUID
    reviewed_packet_hash:str=Field(pattern=r'^[0-9a-f]{64}$')
    mode:Literal['official','advisory']
    prior_plan_id:UUID|None=None

class DataGrant(Reason):
    reviewed_plan_hash:str=Field(pattern=r'^[0-9a-f]{64}$')
    permission_reference:str=Field(min_length=12,max_length=500)
    valid_until:datetime
    packet_reviewed:bool=Field(strict=True)
    authorized_to_share:bool=Field(strict=True)
    @model_validator(mode='after')
    def explicit(self):
        if not self.packet_reviewed or not self.authorized_to_share:raise ValueError('Explicit review and data permission required')
        if self.valid_until.tzinfo is None or self.valid_until.utcoffset() is None:raise ValueError('Timezone required')
        return self

class Feedback(Strict):
    request_id:UUID
    review_id:UUID
    reviewed_result_hash:str=Field(pattern=r'^[0-9a-f]{64}$')
    criterion_id:str=Field(pattern=r'^C[1-9][0-9]{0,2}$')
    action:Literal['accept','modify','reject','request_evidence']
    reason:str=Field(min_length=8,max_length=800)
    replacement_text:str|None=Field(default=None,min_length=8,max_length=1200)
    original_evidence_reviewed:bool=Field(strict=True)
    @model_validator(mode='after')
    def explicit(self):
        if not self.original_evidence_reviewed:raise ValueError('Inspect original evidence first')
        if (self.action=='modify') != (self.replacement_text is not None):raise ValueError('Only modification requires replacement text')
        return self
