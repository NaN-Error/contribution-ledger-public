"""Usage estimate settlement, including ambiguous requests. Not finance ledger entries."""
from sqlalchemy import select
from app.ai.models import AIUsageResolution
from app.ai.connections import service as c
from app.core.errors import ApiError
from app.security.audit import audit
from app.ai.usage.calculation import token_cost


def settle(db,row,job,*,input_tokens=None,output_tokens=None,usage_supported=True):
    if job.accounting_state!='held':return
    if input_tokens is None or output_tokens is None or not usage_supported:
        job.accounting_state='uncertain';return
    cost=token_cost(input_tokens,output_tokens,job.specification['input_rate'],job.specification['output_rate'])
    b=c.bucket(db,row,job.month)
    if b.held_microusd<job.reserved_microusd:raise ApiError(409,'ai_usage_integrity','Stored usage does not reconcile.')
    b.held_microusd-=job.reserved_microusd;b.estimated_microusd+=cost
    job.accounting_state='estimated';job.accounted_microusd=cost
    c.event(db,row,'usage_estimated',{'input_tokens':input_tokens,'output_tokens':output_tokens,'estimated_microusd':cost,
        'reservation_exceeded':cost>job.reserved_microusd},job)


def resolve(db,row,job,user,body):
    existing=db.scalar(select(AIUsageResolution).where(AIUsageResolution.job_id==job.id))
    if existing:
        if existing.actual_microusd!=body.actual_microusd or existing.source_reference!=body.source_reference:
            raise ApiError(409,'ai_resolution_exists','Usage has already been reconciled with a different record.')
        return existing
    if job.kind not in {'probe','assessment'} or job.accounting_state!='uncertain' or job.status not in {'ambiguous','succeeded','failed','cancelled'}:
        raise ApiError(409,'ai_usage_not_uncertain','Only a finished uncertain generation can be reconciled. An in-flight request cannot be recalled.')
    b=c.bucket(db,row,job.month)
    if b.held_microusd<job.reserved_microusd:raise ApiError(409,'ai_usage_integrity','Stored usage requires operator investigation.')
    b.held_microusd-=job.reserved_microusd;b.estimated_microusd+=body.actual_microusd
    job.accounting_state='reconciled';job.accounted_microusd=body.actual_microusd
    resolution=AIUsageResolution(workspace_id=row.workspace_id,project_id=row.project_id,job_id=job.id,created_by=user.id,
        actual_microusd=body.actual_microusd,source_reference=body.source_reference,reason=body.reason)
    db.add(resolution);db.flush()
    c.event(db,row,'usage_reconciled',{'resolution_id':str(resolution.id),'actual_microusd':body.actual_microusd},job)
    audit(db,'ai_usage_reconciled',actor_id=user.id,workspace_id=row.workspace_id,project_id=row.project_id,
        subject_id=job.id,reason=body.reason,details={'resolution_id':str(resolution.id)})
    return resolution
