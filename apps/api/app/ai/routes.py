from uuid import UUID
from fastapi import APIRouter,Request,Query
from sqlalchemy import select
from app.auth.dependencies import Authenticated,Db
from app.ai.models import (AIConnection,AIModel,AIPrice,AIUsageBucket,AIJob,AIEvent,AIProfile,AIUsageResolution)
from app.ai.schemas import (ConnectionCreate,ConnectionUpdate,Rotate,Revoke,CatalogRequest,PriceCreate,ProbeRequest,Resolution,ProfileCreate,ProfileApprove,Reason)
from app.ai.connections import service as c
from app.ai.profiles import service as profiles
from app.ai.usage import service as usage
from app.core.errors import ApiError
from app.security.secrets.store import SecretUnavailable
from app.security.secrets.encrypted import CredentialWrites

router=APIRouter(prefix='/api/v1/workspaces/{workspace_id}/projects/{project_id}/ai',tags=['ai-provider-foundation'])

@router.get('')
def overview(workspace_id:UUID,project_id:UUID,request:Request,db:Db,identity:Authenticated):
    p,role=c.context(db,workspace_id,project_id,identity.user.id)
    query=select(AIConnection).where(AIConnection.project_id==p.id)
    rows=db.scalars(query.order_by(AIConnection.created_at).limit(50)).all()
    rows=[r for r in rows if r.owner_id==identity.user.id or (r.allow_project_use and role in {'admin','reviewer'})]
    active=profiles.active_profile(db,p)
    return {'connections':[c.connection_view(r,identity.user.id) for r in rows],
        'can_create':role!='viewer','can_approve':role=='admin','active_profile_id':active.id if active else None,
        'live_enabled':request.app.state.settings.ai_live_enabled,'paid_probes_enabled':request.app.state.settings.ai_paid_probes_enabled,
        'providers':['mock',*request.app.state.settings.ai_permitted_providers] if request.app.state.settings.ai_live_enabled else ['mock'],
        'notice':c.NOTICE,'budget_notice':c.BUDGET_NOTICE}

@router.post('/connections',status_code=201)
def create(workspace_id:UUID,project_id:UUID,body:ConnectionCreate,request:Request,db:Db,identity:Authenticated):
    p,role=c.context(db,workspace_id,project_id,identity.user.id,lock=True)
    writes=CredentialWrites(request.app.state.ai_store)
    try:
        row=c.create(db,p,identity.user,role,body,request.app.state.settings,writes)
        db.flush()
    except Exception:
        writes.discard();raise
    # A commit exception is ambiguous; retain encrypted bytes for recovery.
    db.commit();return c.connection_view(row,identity.user.id)

@router.patch('/connections/{connection_id}')
def update(workspace_id:UUID,project_id:UUID,connection_id:UUID,body:ConnectionUpdate,request:Request,db:Db,identity:Authenticated):
    p,role=c.context(db,workspace_id,project_id,identity.user.id,lock=True)
    row=c.connection(db,p,identity.user.id,role,connection_id,owner=True);c.update(db,row,identity.user,body,request.app.state.settings)
    db.commit();return c.connection_view(row,identity.user.id)

@router.post('/connections/{connection_id}/rotate')
def rotate(workspace_id:UUID,project_id:UUID,connection_id:UUID,body:Rotate,request:Request,db:Db,identity:Authenticated):
    p,role=c.context(db,workspace_id,project_id,identity.user.id,lock=True)
    row=c.connection(db,p,identity.user.id,role,connection_id,owner=True)
    writes=CredentialWrites(request.app.state.ai_store)
    try:
        old=c.rotate(db,row,identity.user,body,writes,request.app.state.settings)
        db.flush()
    except Exception:
        writes.discard();raise
    db.commit()
    deletion=True
    if old:
        try:request.app.state.ai_store.delete(old)
        except SecretUnavailable:deletion=False
    return {**c.connection_view(row,identity.user.id),'old_ciphertext_removed':deletion}

@router.post('/connections/{connection_id}/revoke')
def revoke(workspace_id:UUID,project_id:UUID,connection_id:UUID,body:Revoke,request:Request,db:Db,identity:Authenticated):
    p,role=c.context(db,workspace_id,project_id,identity.user.id,lock=True)
    row=c.scoped(db,AIConnection,p,connection_id)
    if row.owner_id!=identity.user.id and role!='admin':raise c.not_found()
    c.revoke(db,row,identity.user,body);db.commit()
    deleted=True
    if row.credential_ref:
        try:request.app.state.ai_store.delete(row.credential_ref)
        except SecretUnavailable:deleted=False
    return {'revoked':True,'ciphertext_removed':deleted,'notice':'Revoke the provider-side key separately. Previously sent calls and external backups cannot be recalled.'}

@router.post('/connections/{connection_id}/refresh',status_code=202)
def refresh(workspace_id:UUID,project_id:UUID,connection_id:UUID,body:CatalogRequest,request:Request,db:Db,identity:Authenticated):
    p,role=c.context(db,workspace_id,project_id,identity.user.id,lock=True)
    row=c.connection(db,p,identity.user.id,role,connection_id,owner=True)
    j=c.enqueue_catalog(db,row,body.request_id,identity.user.id,request.app.state.settings);db.commit();return c.job_view(j)

@router.get('/connections/{connection_id}/models')
def models(workspace_id:UUID,project_id:UUID,connection_id:UUID,db:Db,identity:Authenticated,offset:int=Query(0,ge=0,le=5000),limit:int=Query(100,ge=1,le=200)):
    p,role=c.context(db,workspace_id,project_id,identity.user.id);row=c.connection(db,p,identity.user.id,role,connection_id)
    items=db.scalars(select(AIModel).where(AIModel.connection_id==row.id).order_by(AIModel.remote_id).offset(offset).limit(limit+1)).all()
    return {'items':[c.model_view(m) for m in items[:limit]],'next_offset':offset+limit if len(items)>limit else None,
        'notice':'Listing is discovery, not proof of access, pricing, compatibility or suitability. New models never replace an approved evaluator.'}

@router.get('/connections/{connection_id}/prices')
def prices(workspace_id:UUID,project_id:UUID,connection_id:UUID,db:Db,identity:Authenticated,offset:int=Query(0,ge=0,le=10000)):
    p,role=c.context(db,workspace_id,project_id,identity.user.id);row=c.connection(db,p,identity.user.id,role,connection_id)
    items=db.scalars(select(AIPrice).where(AIPrice.connection_id==row.id).order_by(AIPrice.created_at.desc(),AIPrice.id.desc()).offset(offset).limit(51)).all()
    return {'items':[c.price_view(v) for v in items[:50]],'next_offset':offset+50 if len(items)>50 else None}

@router.post('/connections/{connection_id}/prices',status_code=201)
def price(workspace_id:UUID,project_id:UUID,connection_id:UUID,body:PriceCreate,db:Db,identity:Authenticated):
    p,role=c.context(db,workspace_id,project_id,identity.user.id,lock=True);row=c.connection(db,p,identity.user.id,role,connection_id,owner=True)
    result=c.price_create(db,row,identity.user,body);db.commit();return c.price_view(result)

@router.get('/connections/{connection_id}/models/{model_id}/probe-quote')
def quote(workspace_id:UUID,project_id:UUID,connection_id:UUID,model_id:UUID,request:Request,db:Db,identity:Authenticated):
    p,role=c.context(db,workspace_id,project_id,identity.user.id);row=c.connection(db,p,identity.user.id,role,connection_id,owner=True)
    return c.quote(db,row,model_id,request.app.state.settings)

@router.post('/connections/{connection_id}/models/{model_id}/probe',status_code=202)
def probe(workspace_id:UUID,project_id:UUID,connection_id:UUID,model_id:UUID,body:ProbeRequest,request:Request,db:Db,identity:Authenticated):
    p,role=c.context(db,workspace_id,project_id,identity.user.id,lock=True);row=c.connection(db,p,identity.user.id,role,connection_id,owner=True)
    j=c.enqueue_probe(db,row,identity.user,model_id,body,request.app.state.settings);db.commit();return c.job_view(j)

@router.get('/connections/{connection_id}/usage')
def usage_list(workspace_id:UUID,project_id:UUID,connection_id:UUID,db:Db,identity:Authenticated,offset:int=Query(0,ge=0,le=10000)):
    p,role=c.context(db,workspace_id,project_id,identity.user.id);row=c.connection(db,p,identity.user.id,role,connection_id)
    items=db.scalars(select(AIUsageBucket).where(AIUsageBucket.connection_id==row.id).order_by(AIUsageBucket.month.desc()).offset(offset).limit(25)).all()
    return {'items':[{k:getattr(b,k) for k in ['month','held_microusd','estimated_microusd']} for b in items[:24]],
        'next_offset':offset+24 if len(items)>24 else None,'notice':c.BUDGET_NOTICE}

@router.get('/connections/{connection_id}/jobs')
def jobs(workspace_id:UUID,project_id:UUID,connection_id:UUID,db:Db,identity:Authenticated,offset:int=Query(0,ge=0,le=10000)):
    p,role=c.context(db,workspace_id,project_id,identity.user.id);row=c.connection(db,p,identity.user.id,role,connection_id)
    items=db.scalars(select(AIJob).where(AIJob.connection_id==row.id).order_by(AIJob.created_at.desc(),AIJob.id.desc()).offset(offset).limit(51)).all()
    return {'items':[c.job_view(j) for j in items[:50]],'next_offset':offset+50 if len(items)>50 else None}

@router.post('/connections/{connection_id}/jobs/{job_id}/cancel')
def cancel(workspace_id:UUID,project_id:UUID,connection_id:UUID,job_id:UUID,body:Reason,db:Db,identity:Authenticated):
    p,role=c.context(db,workspace_id,project_id,identity.user.id,lock=True);row=c.connection(db,p,identity.user.id,role,connection_id,owner=True)
    j=c.scoped(db,AIJob,p,job_id)
    if j.connection_id!=row.id:raise c.not_found()
    if j.status=='cancelled':return c.job_view(j)
    if j.status!='queued':raise ApiError(409,'ai_already_dispatched','Only queued jobs can be cancelled. An already-sent request may be billed.')
    from app.ai.jobs import _cancel
    _cancel(db,row,j,'cancelled_by_owner')
    from app.security.audit import audit
    audit(db,'ai_job_cancelled',actor_id=identity.user.id,workspace_id=p.workspace_id,project_id=p.id,subject_id=j.id,reason=body.reason)
    db.commit();return c.job_view(j)

@router.post('/connections/{connection_id}/jobs/{job_id}/reconcile')
def reconcile(workspace_id:UUID,project_id:UUID,connection_id:UUID,job_id:UUID,body:Resolution,db:Db,identity:Authenticated):
    p,role=c.context(db,workspace_id,project_id,identity.user.id,lock=True);row=c.connection(db,p,identity.user.id,role,connection_id,owner=True)
    j=c.scoped(db,AIJob,p,job_id)
    if j.connection_id!=row.id:raise c.not_found()
    result=usage.resolve(db,row,j,identity.user,body);db.commit()
    return {'id':result.id,'actual_microusd':result.actual_microusd,'job':c.job_view(j),'notice':'Recorded payer reconciliation, not automated invoice verification.'}

@router.get('/profiles')
def profile_list(workspace_id:UUID,project_id:UUID,db:Db,identity:Authenticated,offset:int=Query(0,ge=0,le=1000)):
    p,role=c.context(db,workspace_id,project_id,identity.user.id)
    rows=db.scalars(select(AIProfile).where(AIProfile.project_id==p.id).order_by(AIProfile.version.desc()).offset(offset).limit(26)).all()
    active=profiles.active_profile(db,p)
    return {'items':[profiles.view(db,v) for v in rows[:25]],'next_offset':offset+25 if len(rows)>25 else None,
        'active_profile_id':active.id if active else None,'notice':'Approval pins configuration, not model quality. Evidence profiles require separate packet-disclosure and payer approvals.'}

@router.post('/profiles',status_code=201)
def profile_create(workspace_id:UUID,project_id:UUID,body:ProfileCreate,request:Request,db:Db,identity:Authenticated):
    p,role=c.context(db,workspace_id,project_id,identity.user.id,manage=True,lock=True)
    result=profiles.create(db,p,identity.user,body,request.app.state.settings);db.commit();return profiles.view(db,result)

@router.post('/profiles/{profile_id}/approve')
def profile_approve(workspace_id:UUID,project_id:UUID,profile_id:UUID,body:ProfileApprove,request:Request,db:Db,identity:Authenticated):
    p,role=c.context(db,workspace_id,project_id,identity.user.id,manage=True,lock=True);profile=c.scoped(db,AIProfile,p,profile_id)
    profiles.approval(db,p,identity.user,profile,body,request.app.state.settings);db.commit();return profiles.view(db,profile)


@router.get('/connections/{connection_id}/events')
def event_history(workspace_id:UUID,project_id:UUID,connection_id:UUID,db:Db,identity:Authenticated,offset:int=Query(0,ge=0,le=100000)):
    p,role=c.context(db,workspace_id,project_id,identity.user.id);row=c.connection(db,p,identity.user.id,role,connection_id)
    items=db.scalars(select(AIEvent).where(AIEvent.connection_id==row.id).order_by(AIEvent.created_at.desc(),AIEvent.id.desc()).offset(offset).limit(51)).all()
    return {'items':[{k:getattr(item,k) for k in ('id','job_id','kind','document','created_at')} for item in items[:50]],
        'next_offset':offset+50 if len(items)>50 else None}
