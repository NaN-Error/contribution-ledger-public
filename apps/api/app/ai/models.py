"""Project-scoped provider configuration and jobs. No contribution or finance FKs."""
from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import (BigInteger, Boolean, CheckConstraint, DateTime, ForeignKeyConstraint,
    Integer, JSON, String, UniqueConstraint, Uuid, func)
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base
from app.security.tokens import now
from app.policies.models import actor_fk, project_fk

def conn_fk(name):return ForeignKeyConstraint(['workspace_id','project_id','connection_id'],
    ['ai_connections.workspace_id','ai_connections.project_id','ai_connections.id'],name=name)
def job_fk(name):return ForeignKeyConstraint(['workspace_id','project_id','job_id'],
    ['ai_jobs.workspace_id','ai_jobs.project_id','ai_jobs.id'],name=name)
def model_fk(name):return ForeignKeyConstraint(['workspace_id','project_id','connection_id','model_id'],
    ['ai_models.workspace_id','ai_models.project_id','ai_models.connection_id','ai_models.id'],name=name)

class AIConnection(Base):
    __tablename__='ai_connections'
    __table_args__=(project_fk('fk_ai_connection_project'),actor_fk('owner_id','fk_ai_connection_owner'),
        UniqueConstraint('workspace_id','project_id','id',name='uq_ai_connection_scope'),
        UniqueConstraint('workspace_id','project_id','owner_id','request_id',name='uq_ai_connection_request'),
        CheckConstraint("provider IN ('mock','openai','anthropic','gemini')",name='ai_provider'),
        CheckConstraint('monthly_limit_microusd >= 0 AND monthly_limit_microusd <= 1000000000',name='ai_limit'),)
    id:Mapped[UUID]=mapped_column(Uuid,primary_key=True,default=uuid4)
    workspace_id:Mapped[UUID]=mapped_column(Uuid,nullable=False)
    project_id:Mapped[UUID]=mapped_column(Uuid,nullable=False,index=True)
    owner_id:Mapped[UUID]=mapped_column(Uuid,nullable=False)
    request_id:Mapped[UUID]=mapped_column(Uuid,nullable=False)
    provider:Mapped[str]=mapped_column(String(20),nullable=False)
    label:Mapped[str]=mapped_column(String(100),nullable=False)
    permission_reference:Mapped[str]=mapped_column(String(500),nullable=False)
    credential_ref:Mapped[str|None]=mapped_column(String(36))
    generation:Mapped[int]=mapped_column(Integer,nullable=False,default=1)
    version:Mapped[int]=mapped_column(Integer,nullable=False,default=1)
    enabled:Mapped[bool]=mapped_column(Boolean,nullable=False,default=True)
    allow_project_use:Mapped[bool]=mapped_column(Boolean,nullable=False,default=False)
    monthly_limit_microusd:Mapped[int]=mapped_column(BigInteger,nullable=False,default=0)
    next_refresh_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False)
    last_catalog_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    last_error:Mapped[str|None]=mapped_column(String(40))
    retry_not_before:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False,default=now,server_default=func.now())

class AIModel(Base):
    __tablename__='ai_models'
    __table_args__=(conn_fk('fk_ai_model_connection'),
        UniqueConstraint('workspace_id','project_id','connection_id','id',name='uq_ai_model_scope'),
        UniqueConstraint('connection_id','remote_id',name='uq_ai_model_remote'))
    id:Mapped[UUID]=mapped_column(Uuid,primary_key=True,default=uuid4)
    workspace_id:Mapped[UUID]=mapped_column(Uuid,nullable=False)
    project_id:Mapped[UUID]=mapped_column(Uuid,nullable=False,index=True)
    connection_id:Mapped[UUID]=mapped_column(Uuid,nullable=False)
    remote_id:Mapped[str]=mapped_column(String(200),nullable=False)
    document:Mapped[dict]=mapped_column(JSON,nullable=False)
    fingerprint:Mapped[str]=mapped_column(String(64),nullable=False)
    generation:Mapped[int]=mapped_column(Integer,nullable=False)
    available:Mapped[bool]=mapped_column(Boolean,nullable=False,default=True)
    observed_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False)
    probe_state:Mapped[str]=mapped_column(String(40),nullable=False,default='unknown')
    probe_job_id:Mapped[UUID|None]=mapped_column(Uuid)
    probe_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))

class AIPrice(Base):
    __tablename__='ai_prices'
    __table_args__=(model_fk('fk_ai_price_model'),actor_fk('created_by','fk_ai_price_author'),
        UniqueConstraint('workspace_id','project_id','connection_id','id',name='uq_ai_price_scope'),
        CheckConstraint('input_rate >= 0 AND output_rate >= 0',name='ai_price_positive'))
    id:Mapped[UUID]=mapped_column(Uuid,primary_key=True,default=uuid4)
    workspace_id:Mapped[UUID]=mapped_column(Uuid,nullable=False)
    project_id:Mapped[UUID]=mapped_column(Uuid,nullable=False,index=True)
    connection_id:Mapped[UUID]=mapped_column(Uuid,nullable=False)
    model_id:Mapped[UUID]=mapped_column(Uuid,nullable=False)
    created_by:Mapped[UUID]=mapped_column(Uuid,nullable=False)
    input_rate:Mapped[int]=mapped_column(BigInteger,nullable=False) # microUSD per million tokens
    output_rate:Mapped[int]=mapped_column(BigInteger,nullable=False)
    source_reference:Mapped[str]=mapped_column(String(500),nullable=False)
    reason:Mapped[str]=mapped_column(String(500),nullable=False)
    valid_until:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False)
    fingerprint:Mapped[str]=mapped_column(String(64),nullable=False)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False,default=now,server_default=func.now())

class AIUsageBucket(Base):
    __tablename__='ai_usage_buckets'
    __table_args__=(conn_fk('fk_ai_usage_connection'),UniqueConstraint('connection_id','month',name='uq_ai_usage_month'),
        CheckConstraint('held_microusd >= 0 AND estimated_microusd >= 0',name='ai_usage_positive'))
    id:Mapped[UUID]=mapped_column(Uuid,primary_key=True,default=uuid4)
    workspace_id:Mapped[UUID]=mapped_column(Uuid,nullable=False)
    project_id:Mapped[UUID]=mapped_column(Uuid,nullable=False,index=True)
    connection_id:Mapped[UUID]=mapped_column(Uuid,nullable=False)
    month:Mapped[str]=mapped_column(String(7),nullable=False)
    held_microusd:Mapped[int]=mapped_column(BigInteger,nullable=False,default=0)
    estimated_microusd:Mapped[int]=mapped_column(BigInteger,nullable=False,default=0)

class AIJob(Base):
    __tablename__='ai_jobs'
    __table_args__=(conn_fk('fk_ai_job_connection'),actor_fk('requested_by','fk_ai_job_actor'),
        UniqueConstraint('workspace_id','project_id','id',name='uq_ai_job_scope'),
        UniqueConstraint('connection_id','request_id',name='uq_ai_job_request'),
        ForeignKeyConstraint(['workspace_id','project_id','assessment_plan_id'],['ai_review_plans.workspace_id','ai_review_plans.project_id','ai_review_plans.id'],name='fk_ai_job_assessment_plan'),
        UniqueConstraint('assessment_plan_id',name='uq_ai_job_assessment_plan'),
        CheckConstraint("(kind = 'assessment' AND assessment_plan_id IS NOT NULL) OR (kind <> 'assessment' AND assessment_plan_id IS NULL)",name='ai_job_plan_kind'),
        CheckConstraint("kind IN ('catalog','probe','assessment')",name='ai_job_kind'),
        CheckConstraint("status IN ('queued','running','succeeded','failed','ambiguous','cancelled')",name='ai_job_status'),
        CheckConstraint('reserved_microusd >= 0',name='ai_reserved_positive'))
    id:Mapped[UUID]=mapped_column(Uuid,primary_key=True,default=uuid4)
    workspace_id:Mapped[UUID]=mapped_column(Uuid,nullable=False)
    project_id:Mapped[UUID]=mapped_column(Uuid,nullable=False,index=True)
    connection_id:Mapped[UUID]=mapped_column(Uuid,nullable=False)
    requested_by:Mapped[UUID]=mapped_column(Uuid,nullable=False)
    request_id:Mapped[UUID]=mapped_column(Uuid,nullable=False)
    kind:Mapped[str]=mapped_column(String(20),nullable=False)
    status:Mapped[str]=mapped_column(String(20),nullable=False,default='queued')
    generation:Mapped[int]=mapped_column(Integer,nullable=False)
    assessment_plan_id:Mapped[UUID|None]=mapped_column(Uuid)
    # Frozen safe settings only; contains neither a key nor evidence/prompt text.
    specification:Mapped[dict]=mapped_column(JSON,nullable=False)
    month:Mapped[str|None]=mapped_column(String(7))
    reserved_microusd:Mapped[int]=mapped_column(BigInteger,nullable=False,default=0)
    accounting_state:Mapped[str]=mapped_column(String(20),nullable=False,default='none')
    accounted_microusd:Mapped[int|None]=mapped_column(BigInteger)
    attempts:Mapped[int]=mapped_column(Integer,nullable=False,default=0)
    not_before:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False)
    lease_token:Mapped[UUID|None]=mapped_column(Uuid)
    lease_until:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    dispatched_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    finished_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    last_error:Mapped[str|None]=mapped_column(String(40))
    result:Mapped[dict|None]=mapped_column(JSON)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False,default=now,server_default=func.now())

class AIEvent(Base):
    __tablename__='ai_operation_events'
    __table_args__=(conn_fk('fk_ai_event_connection'),job_fk('fk_ai_event_job'))
    id:Mapped[UUID]=mapped_column(Uuid,primary_key=True,default=uuid4)
    workspace_id:Mapped[UUID]=mapped_column(Uuid,nullable=False)
    project_id:Mapped[UUID]=mapped_column(Uuid,nullable=False,index=True)
    connection_id:Mapped[UUID]=mapped_column(Uuid,nullable=False)
    job_id:Mapped[UUID|None]=mapped_column(Uuid)
    kind:Mapped[str]=mapped_column(String(50),nullable=False)
    document:Mapped[dict]=mapped_column(JSON,nullable=False)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False,default=now,server_default=func.now())

class AIProfile(Base):
    __tablename__='ai_profiles'
    __table_args__=(conn_fk('fk_ai_profile_connection'),actor_fk('created_by','fk_ai_profile_actor'),
        UniqueConstraint('workspace_id','project_id','id',name='uq_ai_profile_scope'),
        UniqueConstraint('project_id','version',name='uq_ai_profile_version'))
    id:Mapped[UUID]=mapped_column(Uuid,primary_key=True,default=uuid4)
    workspace_id:Mapped[UUID]=mapped_column(Uuid,nullable=False)
    project_id:Mapped[UUID]=mapped_column(Uuid,nullable=False,index=True)
    connection_id:Mapped[UUID]=mapped_column(Uuid,nullable=False)
    created_by:Mapped[UUID]=mapped_column(Uuid,nullable=False)
    version:Mapped[int]=mapped_column(Integer,nullable=False)
    definition:Mapped[dict]=mapped_column(JSON,nullable=False)
    fingerprint:Mapped[str]=mapped_column(String(64),nullable=False)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False,default=now,server_default=func.now())

class AIProfileApproval(Base):
    __tablename__='ai_profile_approvals'
    __table_args__=(project_fk('fk_ai_approval_project'),actor_fk('approved_by','fk_ai_approval_actor'),
        ForeignKeyConstraint(['workspace_id','project_id','profile_id'],['ai_profiles.workspace_id','ai_profiles.project_id','ai_profiles.id'],name='fk_ai_approval_profile'),
        UniqueConstraint('profile_id',name='uq_ai_approved_profile'))
    id:Mapped[UUID]=mapped_column(Uuid,primary_key=True,default=uuid4)
    workspace_id:Mapped[UUID]=mapped_column(Uuid,nullable=False)
    project_id:Mapped[UUID]=mapped_column(Uuid,nullable=False,index=True)
    profile_id:Mapped[UUID]=mapped_column(Uuid,nullable=False)
    approved_by:Mapped[UUID]=mapped_column(Uuid,nullable=False)
    reason:Mapped[str]=mapped_column(String(500),nullable=False)
    reviewed_hash:Mapped[str]=mapped_column(String(64),nullable=False)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False,default=now,server_default=func.now())

class AIUsageResolution(Base):
    __tablename__='ai_usage_resolutions'
    __table_args__=(job_fk('fk_ai_resolution_job'),actor_fk('created_by','fk_ai_resolution_actor'),
        UniqueConstraint('job_id',name='uq_ai_usage_resolution'),CheckConstraint('actual_microusd >= 0',name='ai_actual_positive'))
    id:Mapped[UUID]=mapped_column(Uuid,primary_key=True,default=uuid4)
    workspace_id:Mapped[UUID]=mapped_column(Uuid,nullable=False)
    project_id:Mapped[UUID]=mapped_column(Uuid,nullable=False,index=True)
    job_id:Mapped[UUID]=mapped_column(Uuid,nullable=False)
    created_by:Mapped[UUID]=mapped_column(Uuid,nullable=False)
    actual_microusd:Mapped[int]=mapped_column(BigInteger,nullable=False)
    source_reference:Mapped[str]=mapped_column(String(500),nullable=False)
    reason:Mapped[str]=mapped_column(String(500),nullable=False)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False,default=now,server_default=func.now())
