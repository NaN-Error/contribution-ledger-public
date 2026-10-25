"""Local authenticated GitHub configuration and source browsing. No public callback writes."""
from uuid import UUID
from urllib.parse import urlsplit
from fastapi import APIRouter, Query, Request
from sqlalchemy import select, func
from app.auth.dependencies import Db, Authenticated
from app.core.errors import ApiError
from app.policies.service import digest
from app.projects.authorization import project_access, not_found
from app.integrations.github.client import GitHubError, API_VERSION, READ_PERMISSIONS
from app.security.secrets.store import SecretUnavailable
from app.integrations.github.models import (GitHubAuthFlow, GitHubConnection, GitHubRepository, GitHubImport,
    GitHubSourceVersion, GitHubIdentity, GitHubIdentityDecision, GitHubEvidenceLink)
from app.integrations.github.schemas import (BeginAuthorization, CompleteAuthorization, ConnectRepositories,
    ChangeConnection, ImportCreate, ImportAction, IdentityMapping, LinkSource)
from app.integrations.github import service

router=APIRouter(prefix='/api/v1/workspaces/{workspace_id}/projects/{project_id}/github',tags=['github-source'])
callback_router=APIRouter(prefix='/api/v1/github',tags=['github-authorization'])
evidence_router=APIRouter(prefix='/api/v1/workspaces/{workspace_id}/projects/{project_id}/work-packages/{package_id}/evidence',tags=['github-evidence'])


def source_view(row, detail=False):
    result={k:getattr(row,k) for k in ['id','repository_id','kind','remote_key','content_hash','size_bytes','captured_at']}
    result['title']=str(row.document['content'].get('title') or row.document['content'].get('name') or row.document['content'].get('message') or row.remote_key)[:200]
    result['omission_count']=len(row.document.get('omissions',[]))
    if detail:
        if digest(row.document)!=row.content_hash:
            raise ApiError(409,'github_source_integrity','The preserved source fingerprint does not reconcile. Ask the operator to investigate.')
        result['document']=row.document
    return result


@router.get('')
def overview(workspace_id:UUID,project_id:UUID,request:Request,db:Db,identity:Authenticated):
    project,role=service.context(db,identity,workspace_id,project_id)
    connections=db.scalars(select(GitHubConnection).where(GitHubConnection.project_id==project.id).order_by(GitHubConnection.created_at).limit(100)).all()
    repos=db.scalars(select(GitHubRepository).where(GitHubRepository.project_id==project.id).order_by(GitHubRepository.full_name).limit(100)).all()
    counts=dict(db.execute(select(GitHubSourceVersion.kind,func.count()).where(GitHubSourceVersion.project_id==project.id).group_by(GitHubSourceVersion.kind)).all())
    return {'configured':request.app.state.settings.github_enabled,'can_manage':role=='admin',
        'api_version':API_VERSION,'permissions':READ_PERMISSIONS,
        'connections':[{k:getattr(row,k) for k in ['id','installation_id','account','github_login','enabled','version','verified_at','verified_until','last_error']} for row in connections],
        'repositories':[{k:getattr(row,k) for k in ['id','connection_id','github_id','full_name','private','default_branch','enabled','version','retry_not_before']} for row in repos],
        'source_version_counts':counts, 'notice':service.NOTICE,
        'metric_notice':'Counts are retained source versions by type, not unique people, work hours, accepted outcomes, or contribution value.',
        'worker_notice':('The optional Celery worker and database scheduler process explicitly enabled reconciliation. Signed intake is separately configured.' if request.app.state.settings.github_sync_enabled else 'Historical-only database worker mode. Recurring synchronization is disabled until the operator enables the optional jobs deployment.')}


@router.post('/authorize',status_code=201)
def begin(workspace_id:UUID,project_id:UUID,request:Request,body:BeginAuthorization,db:Db,identity:Authenticated):
    project,_=service.context(db,identity,workspace_id,project_id,manage=True,lock=True)
    callback=urlsplit(request.app.state.settings.github_callback_url)
    if request.app.state.settings.github_enabled and request.headers.get('origin') != f'{callback.scheme}://{callback.netloc}':
        raise ApiError(409,'github_callback_origin','Open the ledger using the configured GitHub callback origin before authorizing. Localhost and 127.0.0.1 do not share a session cookie.')
    try:
        result=service.begin(db,project,identity,body,request.app.state.github_client,request.app.state.settings)
    except (GitHubError,SecretUnavailable) as error: raise service.external_error(error) from None
    db.commit();return result


@callback_router.post('/callback')
def callback(request:Request,body:CompleteAuthorization,db:Db,identity:Authenticated):
    return service.complete(db,identity,body,request.app.state.github_client,request.app.state.settings)


@callback_router.post('/connect',status_code=201)
def connect(request:Request,body:ConnectRepositories,db:Db,identity:Authenticated):
    result=service.connect(db,identity,body,request.app.state.settings)
    db.commit();return result


@router.post('/connections/{connection_id}/disconnect')
def disconnect(workspace_id:UUID,project_id:UUID,connection_id:UUID,body:ChangeConnection,db:Db,identity:Authenticated):
    project,_=service.context(db,identity,workspace_id,project_id,manage=True,lock=True)
    result=service.disable(db,project,identity,connection_id,body)
    db.commit();return result


@router.post('/imports',status_code=201)
def create_import(workspace_id:UUID,project_id:UUID,request:Request,body:ImportCreate,db:Db,identity:Authenticated):
    project,_=service.context(db,identity,workspace_id,project_id,manage=True,lock=True)
    result=service.create_import(db,project,identity.user,body,request.app.state.settings)
    db.commit();return result


@router.get('/imports')
def imports(workspace_id:UUID,project_id:UUID,db:Db,identity:Authenticated,offset:int=Query(0,ge=0,le=500),limit:int=Query(25,ge=1,le=50)):
    project,_=service.context(db,identity,workspace_id,project_id)
    rows=db.scalars(select(GitHubImport).where(GitHubImport.project_id==project.id).order_by(GitHubImport.created_at.desc(),GitHubImport.id).offset(offset).limit(limit+1)).all()
    return {'items':[service.import_view(db,j) for j in rows[:limit]],'next_offset':offset+limit if len(rows)>limit else None}


@router.get('/imports/{job_id}')
def import_get(workspace_id:UUID,project_id:UUID,job_id:UUID,db:Db,identity:Authenticated):
    project,_=service.context(db,identity,workspace_id,project_id)
    return service.import_view(db,service.row_in_project(db,GitHubImport,project,job_id))


@router.post('/imports/{job_id}/{action}')
def import_action(workspace_id:UUID,project_id:UUID,job_id:UUID,action:str,body:ImportAction,request:Request,db:Db,identity:Authenticated):
    if action not in {'resume','cancel'}: raise not_found()
    project,_=service.context(db,identity,workspace_id,project_id,manage=True,lock=True)
    result=service.import_action(db,project,identity.user,job_id,body,action,request.app.state.settings)
    db.commit();return result


@router.get('/sources')
def sources(workspace_id:UUID,project_id:UUID,db:Db,identity:Authenticated,
            repository_id:UUID|None=None,kind:str|None=Query(None,max_length=40),
            offset:int=Query(0,ge=0,le=100000),limit:int=Query(25,ge=1,le=50)):
    project,_=service.context(db,identity,workspace_id,project_id)
    query=select(GitHubSourceVersion).where(GitHubSourceVersion.project_id==project.id)
    if repository_id:
        service.row_in_project(db,GitHubRepository,project,repository_id)
        query=query.where(GitHubSourceVersion.repository_id==repository_id)
    if kind:query=query.where(GitHubSourceVersion.kind==kind)
    rows=db.scalars(query.order_by(GitHubSourceVersion.captured_at.desc(),GitHubSourceVersion.id).offset(offset).limit(limit+1)).all()
    return {'items':[source_view(r) for r in rows[:limit]],'next_offset':offset+limit if len(rows)>limit else None,
            'notice':'Each row is a preserved source version. Repeated versions are not additional contribution credit.'}


@router.get('/sources/{source_id}')
def source_get(workspace_id:UUID,project_id:UUID,source_id:UUID,db:Db,identity:Authenticated):
    project,_=service.context(db,identity,workspace_id,project_id)
    source=service.row_in_project(db,GitHubSourceVersion,project,source_id)
    other=db.scalar(select(func.count()).select_from(GitHubSourceVersion).where(GitHubSourceVersion.repository_id==source.repository_id,
        GitHubSourceVersion.kind==source.kind,GitHubSourceVersion.remote_key==source.remote_key,GitHubSourceVersion.id!=source.id))
    return source_view(source,True)|{'other_preserved_versions':other}


@router.get('/identities')
def identities(workspace_id:UUID,project_id:UUID,db:Db,identity:Authenticated,
               offset:int=Query(0,ge=0,le=100000),limit:int=Query(25,ge=1,le=50)):
    from app.contributions.work_packages.service import active_people
    project,role=service.context(db,identity,workspace_id,project_id)
    rows=db.scalars(select(GitHubIdentity).where(GitHubIdentity.project_id==project.id).order_by(GitHubIdentity.external_key).offset(offset).limit(limit+1)).all()
    return {'items':[{k:getattr(row,k) for k in ['id','external_key','kind','label','linked_user_id','version']} for row in rows[:limit]],
            'next_offset':offset+limit if len(rows)>limit else None,'people':list(active_people(db,project).values()),
            'can_manage':role=='admin','notice':'Mappings are reviewed attribution aids, not verified identities or awards. Bot accounts cannot be mapped to humans. Multiple email claims remain separate until explicitly reviewed.'}


@router.post('/identities/{identity_id}/mapping')
def mapping(workspace_id:UUID,project_id:UUID,identity_id:UUID,body:IdentityMapping,db:Db,identity:Authenticated):
    project,_=service.context(db,identity,workspace_id,project_id,manage=True,lock=True)
    result=service.map_identity(db,project,identity.user,identity_id,body)
    db.commit();return result


@router.get('/identities/{identity_id}/history')
def mapping_history(workspace_id:UUID,project_id:UUID,identity_id:UUID,db:Db,identity:Authenticated,
                    offset:int=Query(0,ge=0,le=10000),limit:int=Query(25,ge=1,le=50)):
    project,_=service.context(db,identity,workspace_id,project_id)
    row=service.row_in_project(db,GitHubIdentity,project,identity_id)
    history=db.scalars(select(GitHubIdentityDecision).where(GitHubIdentityDecision.identity_id==row.id)
        .order_by(GitHubIdentityDecision.version.desc()).offset(offset).limit(limit+1)).all()
    return {'items':[{k:getattr(h,k) for k in ['id','version','linked_user_id','created_by','reason','created_at']} for h in history[:limit]],
            'next_offset':offset+limit if len(history)>limit else None}


@router.post('/sources/{source_id}/link',status_code=201)
def link(workspace_id:UUID,project_id:UUID,source_id:UUID,body:LinkSource,request:Request,db:Db,identity:Authenticated):
    project,role=service.context(db,identity,workspace_id,project_id,manage=True,lock=True)
    result=service.link_source(db,project,identity.user,role,source_id,body,request.app.state.object_storage,
                               request.app.state.settings.evidence_workspace_quota_bytes)
    db.commit();return result


@evidence_router.get('/{evidence_id}/revisions/{revision_number}/github-source')
def linked_source(workspace_id:UUID,project_id:UUID,package_id:UUID,evidence_id:UUID,revision_number:int,
                  db:Db,identity:Authenticated):
    # Evidence sharing, not raw-repository browsing authority, controls this path.
    from app.evidence.routes import context as evidence_context, evidence_revision
    _,role,package=evidence_context(db,identity,workspace_id,project_id,package_id)
    _,revision=evidence_revision(db,package,evidence_id,revision_number,identity,role)
    origin=revision.document.get('external_source')
    if not origin or origin.get('provider')!='github':raise not_found()
    link=db.scalar(select(GitHubEvidenceLink).where(GitHubEvidenceLink.workspace_id==workspace_id,
        GitHubEvidenceLink.project_id==project_id,GitHubEvidenceLink.package_id==package_id,
        GitHubEvidenceLink.evidence_id==evidence_id,GitHubEvidenceLink.source_id==UUID(origin['source_id'])))
    if link is None:raise not_found()
    source=db.get(GitHubSourceVersion,link.source_id)
    if source is None or source.content_hash!=origin['source_hash']:
        raise ApiError(409,'github_source_integrity','The preserved source reference does not reconcile.')
    return source_view(source,True)
