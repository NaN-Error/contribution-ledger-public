"""Project-scoped sync controls and content-free operational status."""
from uuid import UUID
from fastapi import APIRouter,Request,Query
from sqlalchemy import select,func,and_
from app.auth.dependencies import Db,Authenticated
from app.security.tokens import now,utc
from app.integrations.github import service
from app.integrations.github.models import GitHubRepository,GitHubImport,GitHubSourceVersion,GitHubEvidenceLink
from app.integrations.github.sync_models import (GitHubSyncConfig,GitHubSyncRun,WebhookDelivery,WebhookTarget,GitHubSourceHead,JobHeartbeat)
from app.integrations.github.sync_schemas import ConfigureSync,RequestSync
from app.integrations.github.sync_service import configure,config_view,request_now
from app.jobs.models import OutboxMessage

router=APIRouter(prefix='/api/v1/workspaces/{workspace_id}/projects/{project_id}/github',tags=['github-synchronization'])


@router.get('/sync')
def overview(workspace_id:UUID,project_id:UUID,request:Request,db:Db,identity:Authenticated):
    project,role=service.context(db,identity,workspace_id,project_id)
    rows=db.scalars(select(GitHubSyncConfig).where(GitHubSyncConfig.project_id==project.id).order_by(GitHubSyncConfig.id)).all()
    queued=dict(db.execute(select(WebhookTarget.state,func.count()).where(WebhookTarget.project_id==project.id).group_by(WebhookTarget.state)).all())
    states=dict(db.execute(select(GitHubImport.state,func.count()).where(GitHubImport.project_id==project.id).group_by(GitHubImport.state)).all())
    heartbeats=db.scalars(select(JobHeartbeat)).all()
    # Each linked source version stays pinned. This count is a warning, not a rewrite.
    changed=db.scalar(select(func.count()).select_from(GitHubEvidenceLink).join(GitHubSourceVersion,
        GitHubSourceVersion.id==GitHubEvidenceLink.source_id).join(GitHubSourceHead,and_(
            GitHubSourceHead.repository_id==GitHubSourceVersion.repository_id,
            GitHubSourceHead.kind==GitHubSourceVersion.kind,GitHubSourceHead.remote_key==GitHubSourceVersion.remote_key))
        .where(GitHubEvidenceLink.project_id==project.id,
            (GitHubSourceHead.source_id!=GitHubSourceVersion.id)|(GitHubSourceHead.state=='unavailable')))
    return {'can_manage':role=='admin','sync_configured':request.app.state.settings.github_sync_enabled,
        'webhook_configured':request.app.state.settings.github_webhook_enabled,'configurations':[config_view(r) for r in rows],
        'delivery_counts':queued,'job_counts':states,'linked_sources_with_new_observations':changed,
        'heartbeat':[{'component':r.component,'last_seen_at':r.last_seen_at,'status':r.status,
            'stale':(now()-utc(r.last_seen_at)).total_seconds()>120} for r in heartbeats],
        'notice':'Runs are bounded current observations, not guaranteed complete history. Pinned evidence, accepted credit and saved financial examples never change automatically.'}


@router.put('/sync/{repository_id}')
def change(workspace_id:UUID,project_id:UUID,repository_id:UUID,request:Request,body:ConfigureSync,db:Db,identity:Authenticated):
    project,_=service.context(db,identity,workspace_id,project_id,manage=True,lock=True)
    result=configure(db,project,identity.user,repository_id,body,request.app.state.settings)
    db.commit();return result


@router.post('/sync/{repository_id}/request')
def request_sync(workspace_id:UUID,project_id:UUID,repository_id:UUID,request:Request,body:RequestSync,db:Db,identity:Authenticated):
    project,_=service.context(db,identity,workspace_id,project_id,manage=True,lock=True)
    result=request_now(db,project,identity.user,repository_id,body,request.app.state.settings)
    db.commit();return result


@router.get('/deliveries')
def deliveries(workspace_id:UUID,project_id:UUID,db:Db,identity:Authenticated,
               offset:int=Query(0,ge=0,le=100000),limit:int=Query(25,ge=1,le=50)):
    project,_=service.context(db,identity,workspace_id,project_id)
    rows=db.execute(select(WebhookTarget,WebhookDelivery).join(WebhookDelivery,WebhookTarget.delivery_id==WebhookDelivery.id)
        .where(WebhookTarget.project_id==project.id).order_by(WebhookTarget.created_at.desc(),WebhookTarget.id).offset(offset).limit(limit+1)).all()
    return {'items':[{'id':s.id,'repository_id':s.repository_id,'delivery_id':d.delivery_key,'event':d.event,'action':d.action,
        'received_at':d.received_at,'state':s.state,'note':s.note,'import_id':s.import_id,
        'payload_hash':d.payload_hash,'target_count':len(s.targets)} for s,d in rows[:limit]],
        'next_offset':offset+limit if len(rows)>limit else None}


@router.get('/jobs')
def jobs(workspace_id:UUID,project_id:UUID,db:Db,identity:Authenticated,
         offset:int=Query(0,ge=0,le=100000),limit:int=Query(25,ge=1,le=50)):
    project,_=service.context(db,identity,workspace_id,project_id)
    rows=db.execute(select(GitHubImport,OutboxMessage).outerjoin(OutboxMessage,OutboxMessage.job_id==GitHubImport.id)
        .where(GitHubImport.project_id==project.id).order_by(GitHubImport.created_at.desc(),GitHubImport.id).offset(offset).limit(limit+1)).all()
    return {'items':[service.import_view(db,j)|{'dispatch':None if o is None else {
        'publish_attempts':o.publish_attempts,'last_published_at':o.last_published_at,'next_dispatch_at':o.next_dispatch_at,
        'publish_error':o.publish_error,'lease_until':o.dispatch_lease_until},
        'dead_letter':j.state=='failed','worker_lease_until':j.lease_until} for j,o in rows[:limit]],
        'next_offset':offset+limit if len(rows)>limit else None}


@router.get('/observations')
def observations(workspace_id:UUID,project_id:UUID,db:Db,identity:Authenticated,repository_id:UUID|None=None,
                 offset:int=Query(0,ge=0,le=100000),limit:int=Query(25,ge=1,le=50)):
    project,_=service.context(db,identity,workspace_id,project_id)
    query=select(GitHubSourceHead).where(GitHubSourceHead.project_id==project.id)
    if repository_id:
        service.row_in_project(db,GitHubRepository,project,repository_id);query=query.where(GitHubSourceHead.repository_id==repository_id)
    rows=db.scalars(query.order_by(GitHubSourceHead.observed_at.desc(),GitHubSourceHead.id).offset(offset).limit(limit+1)).all()
    return {'items':[{k:getattr(r,k) for k in ('id','repository_id','kind','remote_key','source_id','state','observed_at','remote_updated_at','import_id')} for r in rows[:limit]],
        'next_offset':offset+limit if len(rows)>limit else None,
        'notice':'Latest locally committed observations. An older pinned source may still be valid historical evidence. Unavailable does not mean zero contribution.'}
