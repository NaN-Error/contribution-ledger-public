from typing import Literal
from uuid import UUID
from fastapi import APIRouter, Request
from sqlalchemy import select
from app.auth.dependencies import Db, Authenticated
from app.core.errors import ApiError
from app.integrations.github.models import GitHubImport, GitHubRepository
from .models import RepositoryAnalysis
from .schemas import (AnalysisCreate, RunAction, Proposal, ManualContribution, ManualDisposition,
    IdentityAlias, Scenario, ShareReport, RevokeReport, Handoff)
from . import service, sharing, handoff
from app.projects.authorization import project_access
from app.security.secrets.encrypted import CredentialWrites
from app.security.secrets.store import SecretUnavailable
from . import connections

router = APIRouter(prefix='/api/v1/workspaces/{workspace_id}/projects/{project_id}/analysis',tags=['draft repository analysis'])


@router.get('')
def overview(workspace_id:UUID, project_id:UUID, request:Request, db:Db, identity:Authenticated, report_id:UUID|None=None):
    project,role = service.access(db,workspace_id,project_id,identity.user.id,lock=True)
    runs = service.list_runs(db,project)
    chosen = service.run_in_project(db,project,report_id) if report_id else db.scalar(select(RepositoryAnalysis)
        .where(RepositoryAnalysis.project_id==project.id,RepositoryAnalysis.state=='completed')
        .order_by(RepositoryAnalysis.created_at.desc(),RepositoryAnalysis.id.desc()).limit(1))
    if chosen and chosen.state!='completed': raise ApiError(409,'analysis_report_incomplete','Select a completed report.')
    imports = db.execute(select(GitHubImport,GitHubRepository).join(GitHubRepository,GitHubRepository.id==GitHubImport.repository_id)
        .where(GitHubImport.project_id==project.id,GitHubImport.state.in_(['completed','completed_incomplete']))
        .order_by(GitHubImport.created_at.desc()).limit(100)).all()
    return {'can_manage':role=='admin','runs':runs,
        'private_reads_enabled':request.app.state.settings.repository_private_reads_enabled,
        'cli_available':request.app.state.settings.desktop_enabled and connections.shutil.which('gh') is not None,
        'connection':connections.view(connections.own_connection(db,project,identity.user.id)),
        'imports':[{'id':str(j.id),'repository':r.full_name,'private':r.private,'start_at':j.start_at,'end_before':j.end_before} for j,r in imports],
        'dashboard':service.report_dashboard(db,project,identity.user.id,role,chosen)}


@router.post('/runs',status_code=201)
def create(workspace_id:UUID,project_id:UUID,body:AnalysisCreate,request:Request,db:Db,identity:Authenticated):
    project,_ = service.access(db,workspace_id,project_id,identity.user.id,manage=True,lock=True)
    row = service.create_run(db,project,identity.user.id,body,request.app.state.settings)
    db.commit(); return service.run_view(row,full=True)


@router.get('/runs/{run_id}')
def run(workspace_id:UUID,project_id:UUID,run_id:UUID,db:Db,identity:Authenticated):
    project,_ = service.access(db,workspace_id,project_id,identity.user.id)
    return service.run_view(service.run_in_project(db,project,run_id),full=True)


@router.post('/runs/{run_id}/advance')
def advance(workspace_id:UUID,project_id:UUID,run_id:UUID,body:RunAction,request:Request,db:Db,identity:Authenticated):
    return service.advance(db,workspace_id,project_id,identity.user.id,run_id,body,
        request.app.state.public_repository_client,request.app.state.settings,
        request.app.state.repository_store,request.app.state.repository_transport)


@router.put('/connection')
def connect(workspace_id:UUID,project_id:UUID,body:connections.ConnectionSave,request:Request,db:Db,identity:Authenticated):
    project,_ = service.access(db,workspace_id,project_id,identity.user.id,manage=True)
    token,username = connections.verify(body,request.app.state.settings,request.app.state.repository_transport)
    project,_ = service.access(db,workspace_id,project_id,identity.user.id,manage=True,lock=True)
    writes=CredentialWrites(request.app.state.repository_store)
    try:
        row,old=connections.save(db,project,identity.user.id,body,token,username,writes)
    except SecretUnavailable:
        writes.discard()
        raise ApiError(409,'analysis_credential_store_unavailable','Initialize the protected GitHub credential store before saving a token.') from None
    except Exception:
        writes.discard();raise
    # An ambiguous commit must retain ciphertext for deliberate recovery.
    db.commit()
    removed=True
    if old:
        try: request.app.state.repository_store.delete(old)
        except SecretUnavailable: removed=False
    return {'connection':connections.view(row),'old_ciphertext_removed':removed}


@router.post('/activity')
def activity(workspace_id:UUID,project_id:UUID,body:connections.ActivityRead,request:Request,db:Db,identity:Authenticated):
    project,_=service.access(db,workspace_id,project_id,identity.user.id,manage=True)
    settings=request.app.state.settings;names=[connections.repository_name(u) for u in body.repository_urls]
    client=request.app.state.public_repository_client;version=None
    if body.connection_id:
        row=connections.checked(db,project,identity.user.id,body.connection_id,settings,names=names)
        version=row.version
        client=connections.client_for(row,request.app.state.repository_store,settings,request.app.state.repository_transport)
    elif not settings.repository_public_reads_enabled:
        raise ApiError(409,'analysis_public_reads_disabled','Public reads are disabled.')
    try:rows=connections.activity(client,names,authorized=bool(body.connection_id))
    except connections.GitHubError as error:
        raise ApiError(409,error.code,'GitHub activity dates could not be read. Check repository access and the recorded rate limit.',error.retry_seconds) from None
    project,_=service.access(db,workspace_id,project_id,identity.user.id,manage=True)
    if body.connection_id:
        row=connections.checked(db,project,identity.user.id,body.connection_id,settings,names=names)
        if row.version!=version:raise ApiError(409,'analysis_connection_changed','Reconnect and read the dates again; the response was discarded.')
    elif not settings.repository_public_reads_enabled:raise ApiError(409,'analysis_public_reads_disabled','Public reads were disabled during the fetch.')
    return {'repositories':rows,'notice':'Dates are context only. No analysis, credit or report sharing was created.'}


@router.post('/connection/disconnect')
def disconnect(workspace_id:UUID,project_id:UUID,body:RunAction,request:Request,db:Db,identity:Authenticated):
    project,_=service.access(db,workspace_id,project_id,identity.user.id,manage=True,lock=True)
    row=connections.own_connection(db,project,identity.user.id,lock=True)
    if not row: raise ApiError(404,'not_found','This connection does not exist.')
    if row.version!=body.expected_version: raise ApiError(409,'analysis_connection_stale','Refresh before disconnecting.')
    row.active=False;row.version+=1;old=row.credential_ref;row.credential_ref=None
    from app.security.audit import audit
    audit(db,'analysis.github_disconnected',actor_id=identity.user.id,workspace_id=workspace_id,project_id=project_id,
        subject_id=row.id,reason='Revoked direct repository reads; captured reports preserved.')
    db.commit();removed=True
    if old:
        try:request.app.state.repository_store.delete(old)
        except SecretUnavailable:removed=False
    return {'connection':connections.view(row),'ciphertext_removed':removed,
        'notice':'Captured reports remain. Revoke a saved token in GitHub separately if needed.'}


@router.post('/runs/{run_id}/{action}')
def run_action(workspace_id:UUID,project_id:UUID,run_id:UUID,action:Literal['cancel','retry','finish-partial'],body:RunAction,db:Db,identity:Authenticated):
    project,_ = service.access(db,workspace_id,project_id,identity.user.id,manage=True,lock=True)
    row = service.run_in_project(db,project,run_id,lock=True)
    result = service.action_run(db,project,row,body,action); db.commit(); return result


@router.post('/proposals')
def proposal(workspace_id:UUID,project_id:UUID,body:Proposal,db:Db,identity:Authenticated):
    project,_ = service.access(db,workspace_id,project_id,identity.user.id,manage=True,lock=True)
    result = service.save_proposal(db,project,identity.user.id,body); db.commit(); return result


@router.post('/manual')
def manual(workspace_id:UUID,project_id:UUID,body:ManualContribution,db:Db,identity:Authenticated):
    project,_ = service.access(db,workspace_id,project_id,identity.user.id,manage=True,lock=True)
    result = service.save_manual(db,project,identity.user.id,body); db.commit(); return result


@router.post('/aliases')
def alias(workspace_id:UUID,project_id:UUID,body:IdentityAlias,db:Db,identity:Authenticated):
    project,_ = service.access(db,workspace_id,project_id,identity.user.id,manage=True,lock=True)
    result = service.save_alias(db,project,identity.user.id,body); db.commit(); return result


@router.post('/manual/disposition')
def manual_disposition(workspace_id:UUID,project_id:UUID,body:ManualDisposition,db:Db,identity:Authenticated):
    project,_ = service.access(db,workspace_id,project_id,identity.user.id,manage=True,lock=True)
    result = service.save_manual_disposition(db,project,identity.user.id,body); db.commit(); return result


@router.get('/manual/{contribution_id}/history')
def manual_history(workspace_id:UUID,project_id:UUID,contribution_id:UUID,db:Db,identity:Authenticated):
    project,_ = service.access(db,workspace_id,project_id,identity.user.id)
    return service.manual_history(db,project,contribution_id)


@router.post('/scenario')
def scenario(workspace_id:UUID,project_id:UUID,body:Scenario,db:Db,identity:Authenticated):
    project,_ = service.access(db,workspace_id,project_id,identity.user.id,manage=True,lock=True)
    result = service.change_draft(db,project,identity.user.id,body,lambda d:d.update(amount_cents=body.amount_cents))
    db.commit(); return result


@router.get('/sharing/preview')
def sharing_preview(workspace_id:UUID,project_id:UUID,report_id:UUID,db:Db,identity:Authenticated):
    project,_ = service.access(db,workspace_id,project_id,identity.user.id,manage=True,lock=True)
    return sharing.preview(db,project,identity.user.id,report_id)


@router.get('/sharing/history')
def sharing_history(workspace_id:UUID,project_id:UUID,db:Db,identity:Authenticated):
    project,_ = service.access(db,workspace_id,project_id,identity.user.id,manage=True)
    return {'items':sharing.publications(db,project,history=True)}


@router.post('/sharing',status_code=201)
def share_report(workspace_id:UUID,project_id:UUID,body:ShareReport,db:Db,identity:Authenticated):
    project,_ = service.access(db,workspace_id,project_id,identity.user.id,manage=True,lock=True)
    result = sharing.publish(db,project,identity.user.id,body); db.commit(); return result


@router.post('/sharing/{publication_id}/revoke')
def revoke_report(workspace_id:UUID,project_id:UUID,publication_id:UUID,body:RevokeReport,db:Db,identity:Authenticated):
    project,_ = service.access(db,workspace_id,project_id,identity.user.id,manage=True,lock=True)
    result = sharing.revoke(db,project,identity.user.id,publication_id,body); db.commit(); return result


@router.get('/shared')
def shared_reports(workspace_id:UUID,project_id:UUID,db:Db,identity:Authenticated,publication_id:UUID|None=None):
    project,role = project_access(db,workspace_id,project_id,identity.user.id)
    return sharing.shared_overview(db,project,identity.user.id,role,publication_id)


@router.get('/handoff/options')
def handoff_options(workspace_id:UUID,project_id:UUID,db:Db,identity:Authenticated):
    project,_ = service.access(db,workspace_id,project_id,identity.user.id,manage=True,lock=True)
    return handoff.options(db,project,identity.user.id)


@router.get('/handoff/preview')
def handoff_preview(workspace_id:UUID,project_id:UUID,report_id:UUID,outcome_id:str,batch_id:UUID,db:Db,identity:Authenticated):
    project,_ = service.access(db,workspace_id,project_id,identity.user.id,manage=True,lock=True)
    return handoff.preview(db,project,identity.user.id,report_id,outcome_id,batch_id)


@router.post('/handoff',status_code=201)
def handoff_create(workspace_id:UUID,project_id:UUID,body:Handoff,request:Request,db:Db,identity:Authenticated):
    project,_ = service.access(db,workspace_id,project_id,identity.user.id,manage=True,lock=True)
    result = handoff.create(db,project,identity.user,body,request.app.state.object_storage,
        request.app.state.settings.evidence_workspace_quota_bytes)
    db.commit(); return result
