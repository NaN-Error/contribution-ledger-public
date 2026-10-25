"""Project-protected preparation/review routes. None accepts a free-form model prompt."""
from uuid import UUID
from typing import Literal
from fastapi import APIRouter,Request,Query
from sqlalchemy import select,or_
from app.auth.dependencies import Authenticated,Db
from app.ai.assessments.models import AIReviewPacket,AIReviewPlan,AIReviewResult,AIReviewFeedback
from app.ai.assessments.schemas import PacketCreate,PlanCreate,DataGrant,Feedback
from app.ai.schemas import Reason,ProbeRequest
from app.ai.assessments import service as s
from app.ai.packets import service as p
from app.ai.connections import service as c
from app.ai.profiles import service as profiles
from app.ai.models import AIProfile,AIConnection
from app.contributions.work_packages.models import WorkPackageRevision
from app.contributions.work_packages.service import get_package
from app.evidence.models import EvidenceItem,EvidenceRevision

router=APIRouter(prefix='/api/v1/workspaces/{workspace_id}/projects/{project_id}/ai/assessments',tags=['ai-evidence-assessments'])


def context(db,wid,pid,identity,lock=False):
    project,role=c.context(db,wid,pid,identity.user.id,lock=lock);p.review_access(role)
    return project,role


@router.get('/options')
def options(workspace_id:UUID,project_id:UUID,package_id:UUID,request:Request,db:Db,identity:Authenticated):
    project,role=context(db,workspace_id,project_id,identity)
    package=get_package(db,project,package_id)
    revision=db.get(WorkPackageRevision,(package.id,package.scope_revision))
    values=[]
    rows=db.scalars(select(AIProfile).where(AIProfile.workspace_id==workspace_id,AIProfile.project_id==project.id)
        .order_by(AIProfile.version.desc()).limit(1001)).all()
    for profile in rows[:1000]:
        try:p.profile_contract(profile)
        except c.ApiError:continue
        values.append(profiles.view(db,profile))
    active=profiles.active_profile(db,project)
    evidence=[]
    for item in db.scalars(select(EvidenceItem).where(EvidenceItem.workspace_id==workspace_id,EvidenceItem.project_id==project.id,
        EvidenceItem.package_id==package.id).order_by(EvidenceItem.id)).all():
        rev=db.get(EvidenceRevision,(item.id,item.current_revision));doc=rev.document
        evidence.append({'id':item.id,'revision':item.current_revision,'kind':doc['kind'],
            'title':doc['metadata']['title'],'visibility':doc['metadata']['visibility'],'inclusion':doc['metadata']['inclusion']})
    return {'role':role,'can_approve_data':role=='admin','package_id':package.id,'package_version':package.version,
        'state':package.state,'deliverables':[{'id':d['id'],'title':d['title']} for d in revision.document['deliverables']],
        'profiles':values,'profiles_truncated':len(rows)>1000,'active_profile_id':active.id if active else None,'evidence':evidence,
        'live_evidence_enabled':request.app.state.settings.ai_evidence_enabled,'notice':s.NOTICE}


@router.post('/packets',status_code=201)
def packet_create(workspace_id:UUID,project_id:UUID,body:PacketCreate,request:Request,db:Db,identity:Authenticated):
    project,role=context(db,workspace_id,project_id,identity,True)
    packet=p.create(db,project,identity.user,role,body,request.app.state.object_storage);db.commit()
    return p.view(db,packet)


@router.get('/packets/{packet_id}')
def packet_get(workspace_id:UUID,project_id:UUID,packet_id:UUID,db:Db,identity:Authenticated):
    project,role=context(db,workspace_id,project_id,identity)
    return p.view(db,c.scoped(db,AIReviewPacket,project,packet_id))


@router.get('/packets')
def packets(workspace_id:UUID,project_id:UUID,package_id:UUID,db:Db,identity:Authenticated,offset:int=Query(0,ge=0,le=2000)):
    project,role=context(db,workspace_id,project_id,identity);get_package(db,project,package_id)
    rows=db.scalars(select(AIReviewPacket).where(AIReviewPacket.project_id==project.id,AIReviewPacket.package_id==package_id)
        .order_by(AIReviewPacket.created_at.desc(),AIReviewPacket.id.desc()).offset(offset).limit(26)).all()
    return {'items':[p.view(db,v,full=False) for v in rows[:25]],'next_offset':offset+25 if len(rows)>25 else None}


@router.post('/plans',status_code=201)
def plan_create(workspace_id:UUID,project_id:UUID,body:PlanCreate,request:Request,db:Db,identity:Authenticated):
    project,role=context(db,workspace_id,project_id,identity,True)
    plan=s.create_plan(db,project,identity.user,role,body,request.app.state.settings);db.commit()
    return s.plan_view(db,project,identity.user.id,role,plan)


@router.get('/plans')
def plans(workspace_id:UUID,project_id:UUID,package_id:UUID,db:Db,identity:Authenticated,deliverable_id:UUID|None=None,mode:Literal["official","advisory"]|None=None,mine:bool=False,offset:int=Query(0,ge=0,le=5000)):
    project,role=context(db,workspace_id,project_id,identity);get_package(db,project,package_id)
    query=select(AIReviewPlan).join(AIConnection,AIConnection.id==AIReviewPlan.connection_id).where(
        AIReviewPlan.workspace_id==workspace_id,AIReviewPlan.project_id==project.id,AIReviewPlan.package_id==package_id)
    if deliverable_id is not None:query=query.join(AIReviewPacket,AIReviewPacket.id==AIReviewPlan.packet_id).where(AIReviewPacket.deliverable_id==deliverable_id)
    if mode is not None:query=query.where(AIReviewPlan.mode==mode)
    if mine:query=query.where(AIReviewPlan.created_by==identity.user.id)
    if role!='admin':query=query.where(or_(AIReviewPlan.mode=='official',AIReviewPlan.created_by==identity.user.id,AIConnection.owner_id==identity.user.id))
    rows=db.scalars(query.order_by(AIReviewPlan.created_at.desc(),AIReviewPlan.id.desc()).offset(offset).limit(26)).all()
    return {'items':[s.plan_view(db,project,identity.user.id,role,v) for v in rows[:25]],'next_offset':offset+25 if len(rows)>25 else None}


@router.get('/plans/{plan_id}')
def plan_get(workspace_id:UUID,project_id:UUID,plan_id:UUID,db:Db,identity:Authenticated):
    project,role=context(db,workspace_id,project_id,identity)
    return s.plan_view(db,project,identity.user.id,role,s.scoped_plan(db,project,identity.user.id,role,plan_id))


@router.post('/plans/{plan_id}/approve-data',status_code=201)
def grant(workspace_id:UUID,project_id:UUID,plan_id:UUID,body:DataGrant,db:Db,identity:Authenticated):
    project,role=context(db,workspace_id,project_id,identity,True)
    plan=s.scoped_plan(db,project,identity.user.id,role,plan_id);s.approve_data(db,project,identity.user,plan,body);db.commit()
    return s.plan_view(db,project,identity.user.id,role,plan)


@router.post('/plans/{plan_id}/revoke')
def revoke(workspace_id:UUID,project_id:UUID,plan_id:UUID,body:Reason,db:Db,identity:Authenticated):
    project,role=context(db,workspace_id,project_id,identity,True)
    plan=s.scoped_plan(db,project,identity.user.id,role,plan_id);s.revoke(db,project,identity.user,role,plan,body);db.commit()
    return s.plan_view(db,project,identity.user.id,role,plan)


@router.get('/plans/{plan_id}/quote')
def quote(workspace_id:UUID,project_id:UUID,plan_id:UUID,request:Request,db:Db,identity:Authenticated):
    project,role=context(db,workspace_id,project_id,identity)
    return s.quote(db,project,identity.user,role,s.scoped_plan(db,project,identity.user.id,role,plan_id),request.app.state.settings)


@router.post('/plans/{plan_id}/run',status_code=202)
def run(workspace_id:UUID,project_id:UUID,plan_id:UUID,body:ProbeRequest,request:Request,db:Db,identity:Authenticated):
    project,role=context(db,workspace_id,project_id,identity,True)
    plan=s.scoped_plan(db,project,identity.user.id,role,plan_id)
    job=s.enqueue(db,project,identity.user,role,plan,body,request.app.state.settings);db.commit();return c.job_view(job)


@router.get('/results/{result_id}')
def result(workspace_id:UUID,project_id:UUID,result_id:UUID,db:Db,identity:Authenticated):
    project,role=context(db,workspace_id,project_id,identity)
    return s.result_view(db,project,identity.user.id,role,c.scoped(db,AIReviewResult,project,result_id))


@router.post('/results/{result_id}/feedback',status_code=201)
def feedback(workspace_id:UUID,project_id:UUID,result_id:UUID,body:Feedback,request:Request,db:Db,identity:Authenticated):
    project,role=context(db,workspace_id,project_id,identity,True)
    result=c.scoped(db,AIReviewResult,project,result_id)
    value=s.feedback(db,project,identity.user,role,result,body,request.app.state.object_storage);db.commit()
    return {'id':value.id,'notice':'Observation saved. The original AI output is preserved; no independent acceptance decision was submitted and no credit issued.'}


@router.get('/results/{result_id}/feedback')
def feedback_list(workspace_id:UUID,project_id:UUID,result_id:UUID,db:Db,identity:Authenticated,offset:int=Query(0,ge=0,le=10000)):
    project,role=context(db,workspace_id,project_id,identity);result=c.scoped(db,AIReviewResult,project,result_id)
    s.scoped_plan(db,project,identity.user.id,role,result.plan_id)
    rows=db.scalars(select(AIReviewFeedback).where(AIReviewFeedback.result_id==result.id,AIReviewFeedback.project_id==project.id)
        .order_by(AIReviewFeedback.created_at,AIReviewFeedback.id).offset(offset).limit(51)).all()
    return {'items':[{k:getattr(v,k) for k in ('id','result_id','review_id','created_by','criterion_id','action','reason','replacement_text','created_at')} for v in rows[:50]],
        'next_offset':offset+50 if len(rows)>50 else None}
