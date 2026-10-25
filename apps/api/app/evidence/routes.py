from uuid import UUID
from urllib.parse import quote
from fastapi import APIRouter, Query, Request, Response
from sqlalchemy import select
from app.auth.dependencies import Db, Authenticated
from app.core.errors import ApiError
from app.projects.authorization import project_access, not_found
from app.contributions.work_packages.service import (get_package, lock_package, get_context,
    can_coordinate, validate_review)
from app.evidence.models import EvidenceRevision, EvidenceSnapshot
from app.evidence.schemas import (EvidenceCreate, EvidenceRevise, SnapshotCreate,
    RetireArtifacts, MAX_ITEMS, MAX_UPLOAD_BYTES, MAX_TEXT_BYTES)
from app.evidence.service import (ObjectWrites, get_item, require_visible, revision_view,
    save_revision, summary, capture_snapshot, snapshot_view, require_version,
    retire_revision, read_object, ref)
from app.storage.contracts import StorageError

router = APIRouter(prefix='/api/v1/workspaces/{workspace_id}/projects/{project_id}/work-packages/{package_id}/evidence', tags=['manual evidence'])


def context(db, identity, workspace_id, project_id, package_id, *, lock=False):
    project, role = project_access(db, workspace_id, project_id, identity.user.id, lock=True)
    package = lock_package(db, project, package_id) if lock else get_package(db, project, package_id)
    return project, role, package


def evidence_revision(db, package, evidence_id, number, identity, role):
    item = get_item(db, package, evidence_id)
    require_visible(item, identity.user.id, role)
    revision = db.get(EvidenceRevision, (item.id, number))
    if revision is None: raise not_found()
    require_visible(item, identity.user.id, role, revision.document)
    return item, revision


@router.get('/{evidence_id}/revisions/{revision_number}/analysis-source')
def analysis_source(workspace_id:UUID,project_id:UUID,package_id:UUID,evidence_id:UUID,revision_number:int,
                    db:Db,identity:Authenticated):
    # The exact handoff is already explicitly shared as package evidence.
    # Current AND historical evidence visibility still govern every read.
    from app.analysis.models import AnalysisHandoff
    from app.policies.service import digest
    _,role,package=context(db,identity,workspace_id,project_id,package_id)
    _,revision=evidence_revision(db,package,evidence_id,revision_number,identity,role)
    origin=revision.document.get('external_source')
    if not origin or origin.get('provider')!='repository_analysis':raise not_found()
    try: handoff_id=UUID(origin.get('handoff_id',''))
    except (ValueError,TypeError,AttributeError):
        raise ApiError(409,'analysis_handoff_integrity','The preserved handoff reference does not reconcile.') from None
    row=db.scalar(select(AnalysisHandoff).where(AnalysisHandoff.workspace_id==workspace_id,
        AnalysisHandoff.project_id==project_id,AnalysisHandoff.package_id==package_id,AnalysisHandoff.id==handoff_id))
    if row is None:raise not_found()
    if row.content_hash!=origin.get('handoff_hash') or digest(row.document)!=row.content_hash:
        raise ApiError(409,'analysis_handoff_integrity','The preserved handoff fingerprint does not reconcile.')
    return {'id':str(row.id),'document':row.document,'content_hash':row.content_hash,'created_at':row.created_at}


@router.get('')
def evidence_list(workspace_id: UUID, project_id: UUID, package_id: UUID, request: Request,
                  db: Db, identity: Authenticated, offset: int = Query(0, ge=0, le=MAX_ITEMS)):
    project, role, package = context(db, identity, workspace_id, project_id, package_id)
    result = summary(db, project, package, identity.user.id, role, request.app.state.object_storage, offset=offset)
    result['limits'] = {'max_upload_bytes': MAX_UPLOAD_BYTES, 'max_text_bytes': MAX_TEXT_BYTES,
        'allowed_extensions': ['.txt','.md','.csv','.json','.png','.jpg','.jpeg','.webp'], 'max_entries': MAX_ITEMS}
    return result


@router.post('', status_code=201)
def evidence_create(workspace_id: UUID, project_id: UUID, package_id: UUID, request: Request,
                    body: EvidenceCreate, db: Db, identity: Authenticated):
    project, role, package = context(db, identity, workspace_id, project_id, package_id, lock=True)
    with ObjectWrites(request.app.state.object_storage) as writes:
        item, revision, replay = save_revision(db, project, package, identity.user, role, body, writes,
            request.app.state.settings.evidence_workspace_quota_bytes)
        result = revision_view(db, package, item, revision, identity.user.id, role, writes.storage)
        result.update(package_version=package.version, replayed=replay)
        db.flush(); writes.success(); db.commit()
        return result


@router.post('/{evidence_id}/revisions')
def evidence_revise(workspace_id: UUID, project_id: UUID, package_id: UUID, evidence_id: UUID,
                    request: Request, body: EvidenceRevise, db: Db, identity: Authenticated):
    project, role, package = context(db, identity, workspace_id, project_id, package_id, lock=True)
    item = get_item(db, package, evidence_id)
    with ObjectWrites(request.app.state.object_storage) as writes:
        item, revision, replay = save_revision(db, project, package, identity.user, role, body, writes,
            request.app.state.settings.evidence_workspace_quota_bytes, item=item)
        result = revision_view(db, package, item, revision, identity.user.id, role, writes.storage)
        result.update(package_version=package.version, replayed=replay)
        db.flush(); writes.success(); db.commit()
        return result


@router.get('/snapshots')
def snapshots(workspace_id: UUID, project_id: UUID, package_id: UUID,
              db: Db, identity: Authenticated, offset: int = Query(0, ge=0, le=2000)):
    _, _, package = context(db, identity, workspace_id, project_id, package_id)
    rows = db.scalars(select(EvidenceSnapshot).where(EvidenceSnapshot.package_id == package.id)
        .order_by(EvidenceSnapshot.created_at.desc(), EvidenceSnapshot.id).offset(offset).limit(21)).all()
    return {'items': [{'id': row.id, 'scope_revision': row.scope_revision, 'content_hash': row.content_hash,
            'created_by': row.created_by, 'created_at': row.created_at} for row in rows[:20]],
        'next_offset': offset+20 if len(rows)>20 else None}


@router.post('/snapshots', status_code=201)
def snapshot_create(workspace_id: UUID, project_id: UUID, package_id: UUID, request: Request,
                    body: SnapshotCreate, db: Db, identity: Authenticated):
    project, role, package = context(db, identity, workspace_id, project_id, package_id, lock=True)
    milestone, allocation, scope = get_context(db, project, package)
    if role not in {'admin','reviewer'} and not can_coordinate(package, scope.document, role, identity.user.id):
        raise ApiError(403, 'permission_denied', 'A coordinator, reviewer or administrator can capture a review snapshot.')
    validate_review(package, milestone, allocation, scope, body.expected_package_version, body.reviewed_hash)
    row = capture_snapshot(db, package, identity.user, request.app.state.object_storage, body.reason)
    result = snapshot_view(db, package, row, identity.user.id, role, request.app.state.object_storage)
    db.commit(); return result


@router.get('/snapshots/{snapshot_id}')
def snapshot_get(workspace_id: UUID, project_id: UUID, package_id: UUID, snapshot_id: UUID,
                 request: Request, db: Db, identity: Authenticated):
    _, role, package = context(db, identity, workspace_id, project_id, package_id)
    row = db.scalar(select(EvidenceSnapshot).where(EvidenceSnapshot.id == snapshot_id,
        EvidenceSnapshot.package_id == package.id, EvidenceSnapshot.project_id == project_id,
        EvidenceSnapshot.workspace_id == workspace_id))
    if row is None: raise not_found()
    return snapshot_view(db, package, row, identity.user.id, role, request.app.state.object_storage)


@router.get('/{evidence_id}/revisions')
def revision_history(workspace_id: UUID, project_id: UUID, package_id: UUID, evidence_id: UUID,
                     db: Db, identity: Authenticated):
    _, role, package = context(db, identity, workspace_id, project_id, package_id)
    item = get_item(db, package, evidence_id)
    require_visible(item, identity.user.id, role)
    from app.evidence.service import can_view
    rows = db.scalars(select(EvidenceRevision).where(EvidenceRevision.evidence_id == item.id)
        .order_by(EvidenceRevision.number.desc()).limit(50)).all()
    return {'items': [{'number': r.number, 'created_at': r.created_at, 'created_by': r.created_by,
        'content_hash': r.content_hash, 'reason': r.reason} for r in rows if can_view(item, identity.user.id, role, r.document)]}


@router.get('/{evidence_id}/revisions/{number}')
def revision_get(workspace_id: UUID, project_id: UUID, package_id: UUID, evidence_id: UUID, number: int,
                 request: Request, db: Db, identity: Authenticated):
    _, role, package = context(db, identity, workspace_id, project_id, package_id)
    item, revision = evidence_revision(db, package, evidence_id, number, identity, role)
    return revision_view(db, package, item, revision, identity.user.id, role, request.app.state.object_storage)


@router.get('/{evidence_id}/revisions/{number}/preview')
def preview_text(workspace_id: UUID, project_id: UUID, package_id: UUID, evidence_id: UUID, number: int,
                 request: Request, db: Db, identity: Authenticated):
    _, role, package = context(db, identity, workspace_id, project_id, package_id)
    item, revision = evidence_revision(db, package, evidence_id, number, identity, role)
    doc = revision.document
    if item.kind == 'statement':
        return {'kind': 'text', 'text': doc['text'], 'truncated': False}
    if item.kind != 'file' or not doc['file']['media_type'] in {'text/plain','text/markdown','text/csv','application/json'}:
        raise ApiError(409, 'text_preview_unavailable', 'This entry does not have a text preview.')
    data = read_object(db, package, revision, request.app.state.object_storage)
    text = data.decode('utf-8-sig')
    return {'kind': 'text', 'text': text[:20000], 'truncated': len(text)>20000,
        'notice': 'Plain text only. Markdown, HTML, formulas and scripts are never executed in this preview.'}


@router.get('/{evidence_id}/revisions/{number}/image')
def preview_image(workspace_id: UUID, project_id: UUID, package_id: UUID, evidence_id: UUID, number: int,
                  request: Request, db: Db, identity: Authenticated):
    _, role, package = context(db, identity, workspace_id, project_id, package_id)
    _, revision = evidence_revision(db, package, evidence_id, number, identity, role)
    data = read_object(db, package, revision, request.app.state.object_storage, preview=True)
    return Response(data, media_type='image/png', headers={
        'Cache-Control': 'no-store, private', 'X-Content-Type-Options': 'nosniff',
        'Content-Security-Policy': "default-src 'none'; sandbox", 'Content-Disposition': 'inline; filename="preview.png"',
        'Referrer-Policy': 'no-referrer', 'Vary': 'Cookie'})


@router.get('/{evidence_id}/revisions/{number}/download')
def download(workspace_id: UUID, project_id: UUID, package_id: UUID, evidence_id: UUID, number: int,
             request: Request, db: Db, identity: Authenticated):
    _, role, package = context(db, identity, workspace_id, project_id, package_id)
    _, revision = evidence_revision(db, package, evidence_id, number, identity, role)
    data = read_object(db, package, revision, request.app.state.object_storage)
    # Original filename is validated and RFC5987-encoded, never raw header text.
    filename = quote(revision.document['file']['filename'], safe='')
    return Response(data, media_type='application/octet-stream', headers={
        'Cache-Control': 'no-store, private', 'Content-Disposition': f"attachment; filename=artifact; filename*=UTF-8''{filename}",
        'X-Content-Type-Options': 'nosniff', 'Content-Security-Policy': "default-src 'none'; sandbox",
        'Referrer-Policy': 'no-referrer', 'Vary': 'Cookie'})


@router.post('/{evidence_id}/revisions/{number}/retire')
def retire(workspace_id: UUID, project_id: UUID, package_id: UUID, evidence_id: UUID, number: int,
           request: Request, body: RetireArtifacts, db: Db, identity: Authenticated):
    project, role, package = context(db, identity, workspace_id, project_id, package_id, lock=True)
    item, revision = evidence_revision(db, package, evidence_id, number, identity, role)
    objects, changed = retire_revision(db, project, package, item, revision, identity.user, role, body)
    if changed: capture_snapshot(db, package, identity.user, request.app.state.object_storage,
        'Automatic snapshot after artifact retirement.')
    # Denial is durable BEFORE deleting bytes. A deletion failure cannot expose them.
    db.commit()
    failures = 0
    for obj in objects:
        try:
            if obj.backend != request.app.state.object_storage.backend: failures += 1
            else: request.app.state.object_storage.delete(ref(obj))
        except StorageError: failures += 1
    return {'retired': True, 'changed': changed, 'package_version': package.version,
        'deletion_pending_objects': failures,
        'notice': 'Application delivery is blocked. Metadata, snapshots and accounting are retained. Storage versions, backups and previously saved copies are not erased by this command.'}
