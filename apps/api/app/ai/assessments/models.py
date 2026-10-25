"""Immutable scoped packets, per-call data grants, results and reviewer observations.

AIJob is the existing durable queue; result content never enters its broadly
visible specification/result metadata. None of these rows grants credit.
"""
from datetime import datetime
from uuid import UUID,uuid4
from sqlalchemy import (DateTime,Integer,JSON,String,UniqueConstraint,ForeignKeyConstraint,CheckConstraint,Uuid,func)
from sqlalchemy.orm import Mapped,mapped_column
from app.db.base import Base
from app.security.tokens import now
from app.policies.models import actor_fk
from app.contributions.work_packages.models import package_fk,revision_fk
from app.ai.models import conn_fk,job_fk


def profile_fk(name):
    return ForeignKeyConstraint(['workspace_id','project_id','profile_id'],
        ['ai_profiles.workspace_id','ai_profiles.project_id','ai_profiles.id'],name=name)


def packet_fk(name):
    return ForeignKeyConstraint(['workspace_id','project_id','package_id','packet_id'],
        ['ai_review_packets.workspace_id','ai_review_packets.project_id','ai_review_packets.package_id','ai_review_packets.id'],name=name)


def plan_fk(name):
    return ForeignKeyConstraint(['workspace_id','project_id','plan_id'],
        ['ai_review_plans.workspace_id','ai_review_plans.project_id','ai_review_plans.id'],name=name)


class AIReviewPacket(Base):
    __tablename__='ai_review_packets'
    __table_args__=(revision_fk('fk_ai_packet_scope'),profile_fk('fk_ai_packet_profile'),actor_fk('created_by','fk_ai_packet_actor'),
        ForeignKeyConstraint(['workspace_id','project_id','package_id','submission_id'],
            ['work_submissions.workspace_id','work_submissions.project_id','work_submissions.package_id','work_submissions.id'],name='fk_ai_packet_submission'),
        UniqueConstraint('workspace_id','project_id','package_id','id',name='uq_ai_packet_scope'),
        UniqueConstraint('project_id','created_by','request_id',name='uq_ai_packet_request'))
    id:Mapped[UUID]=mapped_column(Uuid,primary_key=True,default=uuid4)
    workspace_id:Mapped[UUID]=mapped_column(Uuid,nullable=False)
    project_id:Mapped[UUID]=mapped_column(Uuid,nullable=False,index=True)
    package_id:Mapped[UUID]=mapped_column(Uuid,nullable=False,index=True)
    scope_revision:Mapped[int]=mapped_column(Integer,nullable=False)
    submission_id:Mapped[UUID]=mapped_column(Uuid,nullable=False)
    deliverable_id:Mapped[UUID]=mapped_column(Uuid,nullable=False)
    profile_id:Mapped[UUID]=mapped_column(Uuid,nullable=False)
    created_by:Mapped[UUID]=mapped_column(Uuid,nullable=False)
    request_id:Mapped[UUID]=mapped_column(Uuid,nullable=False)
    request_hash:Mapped[str]=mapped_column(String(64),nullable=False)
    payload:Mapped[dict]=mapped_column(JSON,nullable=False)
    capture:Mapped[dict]=mapped_column(JSON,nullable=False) # local provenance; never sent
    content_hash:Mapped[str]=mapped_column(String(64),nullable=False)
    prompt_hash:Mapped[str]=mapped_column(String(64),nullable=False)
    reason:Mapped[str]=mapped_column(String(500),nullable=False)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False,default=now,server_default=func.now())


class AIReviewPlan(Base):
    __tablename__='ai_review_plans'
    __table_args__=(packet_fk('fk_ai_plan_packet'),profile_fk('fk_ai_plan_profile'),conn_fk('fk_ai_plan_connection'),
        actor_fk('created_by','fk_ai_plan_actor'),
        UniqueConstraint('workspace_id','project_id','id',name='uq_ai_plan_scope'),
        UniqueConstraint('project_id','created_by','request_id',name='uq_ai_plan_request'),
        CheckConstraint("mode IN ('official','advisory')",name='ai_review_mode'))
    id:Mapped[UUID]=mapped_column(Uuid,primary_key=True,default=uuid4)
    workspace_id:Mapped[UUID]=mapped_column(Uuid,nullable=False)
    project_id:Mapped[UUID]=mapped_column(Uuid,nullable=False,index=True)
    package_id:Mapped[UUID]=mapped_column(Uuid,nullable=False,index=True)
    packet_id:Mapped[UUID]=mapped_column(Uuid,nullable=False)
    profile_id:Mapped[UUID]=mapped_column(Uuid,nullable=False)
    connection_id:Mapped[UUID]=mapped_column(Uuid,nullable=False)
    created_by:Mapped[UUID]=mapped_column(Uuid,nullable=False)
    mode:Mapped[str]=mapped_column(String(12),nullable=False)
    prior_plan_id:Mapped[UUID|None]=mapped_column(Uuid)
    request_id:Mapped[UUID]=mapped_column(Uuid,nullable=False)
    request_hash:Mapped[str]=mapped_column(String(64),nullable=False)
    definition:Mapped[dict]=mapped_column(JSON,nullable=False)
    content_hash:Mapped[str]=mapped_column(String(64),nullable=False)
    reason:Mapped[str]=mapped_column(String(500),nullable=False)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False,default=now,server_default=func.now())


class AIReviewGrant(Base):
    __tablename__='ai_review_grants'
    __table_args__=(plan_fk('fk_ai_grant_plan'),actor_fk('approved_by','fk_ai_grant_actor'),
        UniqueConstraint('plan_id',name='uq_ai_grant_plan'))
    id:Mapped[UUID]=mapped_column(Uuid,primary_key=True,default=uuid4)
    workspace_id:Mapped[UUID]=mapped_column(Uuid,nullable=False)
    project_id:Mapped[UUID]=mapped_column(Uuid,nullable=False,index=True)
    plan_id:Mapped[UUID]=mapped_column(Uuid,nullable=False)
    approved_by:Mapped[UUID]=mapped_column(Uuid,nullable=False)
    reviewed_hash:Mapped[str]=mapped_column(String(64),nullable=False)
    permission_reference:Mapped[str]=mapped_column(String(500),nullable=False)
    reason:Mapped[str]=mapped_column(String(500),nullable=False)
    valid_until:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False,default=now,server_default=func.now())


class AIReviewRevocation(Base):
    __tablename__='ai_review_revocations'
    __table_args__=(plan_fk('fk_ai_revoke_plan'),actor_fk('revoked_by','fk_ai_revoke_actor'),UniqueConstraint('plan_id',name='uq_ai_revoked_plan'))
    id:Mapped[UUID]=mapped_column(Uuid,primary_key=True,default=uuid4)
    workspace_id:Mapped[UUID]=mapped_column(Uuid,nullable=False)
    project_id:Mapped[UUID]=mapped_column(Uuid,nullable=False,index=True)
    plan_id:Mapped[UUID]=mapped_column(Uuid,nullable=False)
    revoked_by:Mapped[UUID]=mapped_column(Uuid,nullable=False)
    reason:Mapped[str]=mapped_column(String(500),nullable=False)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False,default=now,server_default=func.now())


class AIReviewResult(Base):
    __tablename__='ai_review_results'
    __table_args__=(plan_fk('fk_ai_result_plan'),job_fk('fk_ai_result_job'),
        UniqueConstraint('workspace_id','project_id','id',name='uq_ai_result_scope'),
        UniqueConstraint('job_id',name='uq_ai_result_job'),UniqueConstraint('plan_id',name='uq_ai_result_plan'))
    id:Mapped[UUID]=mapped_column(Uuid,primary_key=True,default=uuid4)
    workspace_id:Mapped[UUID]=mapped_column(Uuid,nullable=False)
    project_id:Mapped[UUID]=mapped_column(Uuid,nullable=False,index=True)
    plan_id:Mapped[UUID]=mapped_column(Uuid,nullable=False)
    job_id:Mapped[UUID]=mapped_column(Uuid,nullable=False)
    status:Mapped[str]=mapped_column(String(40),nullable=False)
    document:Mapped[dict|None]=mapped_column(JSON)
    metadata_record:Mapped[dict]=mapped_column(JSON,nullable=False)
    content_hash:Mapped[str]=mapped_column(String(64),nullable=False)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False,default=now,server_default=func.now())


class AIReviewFeedback(Base):
    __tablename__='ai_review_feedback'
    __table_args__=(
        ForeignKeyConstraint(['workspace_id','project_id','result_id'],['ai_review_results.workspace_id','ai_review_results.project_id','ai_review_results.id'],name='fk_ai_feedback_result'),
        ForeignKeyConstraint(['workspace_id','project_id','package_id','review_id'],['review_rounds.workspace_id','review_rounds.project_id','review_rounds.package_id','review_rounds.id'],name='fk_ai_feedback_review'),
        actor_fk('created_by','fk_ai_feedback_actor'),UniqueConstraint('project_id','created_by','request_id',name='uq_ai_feedback_request'),
        CheckConstraint("action IN ('accept','modify','reject','request_evidence')",name='ai_feedback_action'))
    id:Mapped[UUID]=mapped_column(Uuid,primary_key=True,default=uuid4)
    workspace_id:Mapped[UUID]=mapped_column(Uuid,nullable=False)
    project_id:Mapped[UUID]=mapped_column(Uuid,nullable=False,index=True)
    package_id:Mapped[UUID]=mapped_column(Uuid,nullable=False)
    result_id:Mapped[UUID]=mapped_column(Uuid,nullable=False)
    review_id:Mapped[UUID]=mapped_column(Uuid,nullable=False)
    created_by:Mapped[UUID]=mapped_column(Uuid,nullable=False)
    criterion_id:Mapped[str]=mapped_column(String(10),nullable=False)
    action:Mapped[str]=mapped_column(String(20),nullable=False)
    reason:Mapped[str]=mapped_column(String(800),nullable=False)
    replacement_text:Mapped[str|None]=mapped_column(String(1200))
    reviewed_result_hash:Mapped[str]=mapped_column(String(64),nullable=False)
    request_id:Mapped[UUID]=mapped_column(Uuid,nullable=False)
    request_hash:Mapped[str]=mapped_column(String(64),nullable=False)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False,default=now,server_default=func.now())
