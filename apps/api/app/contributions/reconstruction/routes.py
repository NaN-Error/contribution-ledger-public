"""Current workspace membership and CSRF apply to every historical command."""
from uuid import UUID
from fastapi import APIRouter, Query, Request
from sqlalchemy import select
from app.auth.dependencies import Db, Authenticated
from app.core.errors import ApiError
from app.projects.authorization import project_access
from app.contributions.budgets.models import Milestone
from app.integrations.github.models import GitHubImport
from .models import ReconstructionBatch, ReconstructionEvent
from . import schemas as S, service as svc

router=APIRouter(prefix='/api/v1/workspaces/{workspace_id}/projects/{project_id}/reconstruction',tags=['historical reconstruction'])


def context(db,identity,wid,pid,*,manage=False,inspect=False):
    project,role=project_access(db,wid,pid,identity.user.id,manage=manage,lock=True)
    if inspect and role not in {'admin','reviewer'}:
        raise ApiError(403,'permission_denied','Only project administrators and reviewers can inspect unshared imported reconstruction records.')
    return project,role


def response(db,project,batch,identity,role,result):
    db.commit()
    # Recheck after commit before returning any private records.
    project,role=project_access(db,project.workspace_id,project.id,identity.user.id,lock=True)
    batch=svc.get_batch(db,project,batch.id,lock=True)
    return {'result':result,'batch':svc.batch_detail(db,project,batch,identity.user.id,role)}


@router.get('')
def listing(workspace_id:UUID,project_id:UUID,db:Db,identity:Authenticated):
    project,role=context(db,identity,workspace_id,project_id)
    rows=db.scalars(svc.scoped(ReconstructionBatch,project).order_by(ReconstructionBatch.created_at.desc(),ReconstructionBatch.id))
    return {'items':[svc.definition_view(row) for row in rows],'can_manage':role=='admin',
        'can_inspect':role in {'admin','reviewer'},'can_submit_claim':role!='viewer','notice':svc.NOTICE}


@router.get('/options')
def options(workspace_id:UUID,project_id:UUID,db:Db,identity:Authenticated):
    project,role=context(db,identity,workspace_id,project_id,inspect=True)
    assigned=select(ReconstructionBatch.milestone_id).where(ReconstructionBatch.project_id==project.id)
    milestones=db.scalars(svc.scoped(Milestone,project).where(Milestone.status=='active',Milestone.allocated_atoms==0,
        Milestone.issued_atoms==0,Milestone.id.not_in(assigned)).order_by(Milestone.created_at,Milestone.id).limit(201))
    imports=list(db.scalars(svc.scoped(GitHubImport,project).where(GitHubImport.state.in_(['completed','completed_incomplete']),
        GitHubImport.capture_mode=='historical').order_by(GitHubImport.created_at.desc(),GitHubImport.id).limit(101)))
    return {'milestones':[{'id':str(m.id),'name':m.name,'policy_id':str(m.policy_id),'total_atoms':m.total_atoms} for m in milestones],
        'imports':[{'id':str(j.id),'repository_id':str(j.repository_id),'start_at':j.start_at,'end_before':j.end_before,
            'state':j.state,'omission_count':len(j.omissions)} for j in imports[:100]],'imports_truncated':len(imports)>100,
        'my_user_id':str(identity.user.id),'notice':'Use a dedicated approved milestone with no allocations. Missing non-code work needs no import.'}


@router.post('',status_code=201)
def create(workspace_id:UUID,project_id:UUID,body:S.BatchCreate,db:Db,identity:Authenticated):
    project,role=context(db,identity,workspace_id,project_id,manage=True)
    batch=svc.create_batch(db,project,identity.user,body)
    db.commit()
    project,role=context(db,identity,workspace_id,project_id)
    batch=svc.get_batch(db,project,batch.id,lock=True)
    return svc.batch_detail(db,project,batch,identity.user.id,role)


@router.get('/{batch_id}')
def detail(workspace_id:UUID,project_id:UUID,batch_id:UUID,db:Db,identity:Authenticated):
    project,role=context(db,identity,workspace_id,project_id)
    return svc.batch_detail(db,project,svc.get_batch(db,project,batch_id),identity.user.id,role)


@router.get('/{batch_id}/history')
def history(workspace_id:UUID,project_id:UUID,batch_id:UUID,db:Db,identity:Authenticated,
            offset:int=Query(0,ge=0,le=2000)):
    project,role=context(db,identity,workspace_id,project_id,inspect=True);svc.get_batch(db,project,batch_id)
    rows=list(db.scalars(svc.scoped(ReconstructionEvent,project).where(ReconstructionEvent.batch_id==batch_id)
        .order_by(ReconstructionEvent.version).offset(offset).limit(21)))
    for row in rows:
        if svc.digest(row.record)!=row.record_hash:raise ApiError(409,'history_integrity_error','A reconstruction history record does not reconcile.')
    return {'items':[{'id':r.id,'version':r.version,'record':r.record,'record_hash':r.record_hash,
        'previous_hash':r.previous_hash,'created_at':r.created_at} for r in rows[:20]],
        'next_offset':offset+20 if len(rows)>20 else None}


@router.post('/{batch_id}/approve-scope')
def approve(workspace_id:UUID,project_id:UUID,batch_id:UUID,body:S.ReviewedCommand,db:Db,identity:Authenticated):
    project,role=context(db,identity,workspace_id,project_id,manage=True);b=svc.get_batch(db,project,batch_id,lock=True)
    return response(db,project,b,identity,role,svc.approve_scope(db,project,b,identity.user,body))


@router.post('/{batch_id}/group-import')
def group(workspace_id:UUID,project_id:UUID,batch_id:UUID,body:S.ImportGroup,db:Db,identity:Authenticated):
    project,role=context(db,identity,workspace_id,project_id,manage=True);b=svc.get_batch(db,project,batch_id,lock=True)
    return response(db,project,b,identity,role,svc.import_groups(db,project,b,identity.user,body))


@router.post('/{batch_id}/candidates',status_code=201)
def candidate_create(workspace_id:UUID,project_id:UUID,batch_id:UUID,body:S.CandidateCreate,db:Db,identity:Authenticated):
    project,role=context(db,identity,workspace_id,project_id,manage=True);b=svc.get_batch(db,project,batch_id,lock=True)
    return response(db,project,b,identity,role,svc.create_manual(db,project,b,identity.user,body))


@router.post('/{batch_id}/candidates/{candidate_id}/revisions')
def candidate_edit(workspace_id:UUID,project_id:UUID,batch_id:UUID,candidate_id:UUID,body:S.CandidateEdit,db:Db,identity:Authenticated):
    project,role=context(db,identity,workspace_id,project_id,manage=True);b=svc.get_batch(db,project,batch_id,lock=True)
    return response(db,project,b,identity,role,svc.edit_candidate(db,project,b,identity.user,candidate_id,body))


@router.post('/{batch_id}/candidates/{candidate_id}/disposition')
def candidate_disposition(workspace_id:UUID,project_id:UUID,batch_id:UUID,candidate_id:UUID,body:S.CandidateDisposition,db:Db,identity:Authenticated):
    project,role=context(db,identity,workspace_id,project_id,manage=True);b=svc.get_batch(db,project,batch_id,lock=True)
    return response(db,project,b,identity,role,svc.disposition(db,project,b,identity.user,candidate_id,body))


@router.post('/{batch_id}/regroup')
def regroup(workspace_id:UUID,project_id:UUID,batch_id:UUID,body:S.Regroup,db:Db,identity:Authenticated):
    project,role=context(db,identity,workspace_id,project_id,manage=True);b=svc.get_batch(db,project,batch_id,lock=True)
    return response(db,project,b,identity,role,svc.regroup(db,project,b,identity.user,body))


@router.post('/{batch_id}/promote',status_code=201)
def promote(workspace_id:UUID,project_id:UUID,batch_id:UUID,body:S.Promote,request:Request,db:Db,identity:Authenticated):
    project,role=context(db,identity,workspace_id,project_id,manage=True);b=svc.get_batch(db,project,batch_id,lock=True)
    settings=request.app.state.settings
    return response(db,project,b,identity,role,svc.promote(db,project,b,identity.user,body,
        request.app.state.object_storage,settings.evidence_workspace_quota_bytes))


@router.post('/{batch_id}/missing-claims',status_code=201)
def missing_claim(workspace_id:UUID,project_id:UUID,batch_id:UUID,body:S.MissingClaimCreate,db:Db,identity:Authenticated):
    project,role=context(db,identity,workspace_id,project_id)
    if role=='viewer':raise ApiError(403,'permission_denied','A current non-viewer participant can submit a missing-work claim.')
    b=svc.get_batch(db,project,batch_id,lock=True)
    return response(db,project,b,identity,role,svc.add_missing_claim(db,project,b,identity.user,body))


@router.post('/{batch_id}/resolve-claim')
def resolve_claim(workspace_id:UUID,project_id:UUID,batch_id:UUID,body:S.MissingClaimResolve,db:Db,identity:Authenticated):
    project,role=context(db,identity,workspace_id,project_id,manage=True);b=svc.get_batch(db,project,batch_id,lock=True)
    return response(db,project,b,identity,role,svc.resolve_missing(db,project,b,identity.user,body))


@router.get('/{batch_id}/opening-preview')
def opening_preview(workspace_id:UUID,project_id:UUID,batch_id:UUID,db:Db,identity:Authenticated):
    project,role=context(db,identity,workspace_id,project_id,inspect=True);b=svc.get_batch(db,project,batch_id)
    return svc.opening_preview(db,project,b,identity.user.id)


@router.post('/{batch_id}/freeze')
def freeze(workspace_id:UUID,project_id:UUID,batch_id:UUID,body:S.ReviewedCommand,db:Db,identity:Authenticated):
    project,role=context(db,identity,workspace_id,project_id,manage=True);b=svc.get_batch(db,project,batch_id,lock=True)
    return response(db,project,b,identity,role,svc.freeze(db,project,b,identity.user,body))
