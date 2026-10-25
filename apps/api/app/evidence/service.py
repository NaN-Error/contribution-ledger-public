"""Manual evidence commands under workspace -> milestone -> package locking.

The database owns access and history. Private blobs are immutable and may be
retired independently. No source is fetched and no award/finance code is called.
"""
from copy import deepcopy
from hashlib import sha256
from io import BytesIO
from uuid import UUID, uuid4
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.core.errors import ApiError
from app.projects.authorization import not_found
from app.policies.service import digest
from app.security.audit import audit
from app.contributions.work_packages.models import WorkPackageRevision, WorkSubmission
from app.contributions.work_packages.service import (get_context, record_event, can_coordinate, guard_unissued)
from app.evidence.models import (EvidenceItem, EvidenceRevision, EvidenceObject,
    EvidenceRetirement, EvidenceSnapshot)
from app.evidence.schemas import MAX_ITEMS, MAX_REVISIONS, MAX_UPLOAD_BYTES
from app.evidence.content import checked_file, MAX_PREVIEW_BYTES
from app.storage.contracts import (ObjectReference, ObjectMissing, ObjectCorrupt,
    StorageUnavailable, StorageError)


class ObjectWrites:
    """Compensate known failed DB transactions; crash orphans require operator cleanup.

An ambiguous commit must NOT lead to blob deletion. Call success immediately
before attempting commit: failed/ambiguous commits may leave private orphans,
never deliberately delete a blob that could have a committed reference.
"""
    def __init__(self, storage): self.storage, self.refs, self.preserve = storage, [], False
    def __enter__(self): return self
    def add(self, reference): self.refs.append(reference); return reference
    def success(self): self.preserve = True
    def __exit__(self, *_):
        if not self.preserve:
            for ref in self.refs:
                try: self.storage.delete(ref)
                except StorageError: pass


def ref(row: EvidenceObject) -> ObjectReference:
    return ObjectReference(row.workspace_id, row.id, row.sha256, row.size_bytes)


def get_item(db, package, evidence_id):
    item = db.scalar(select(EvidenceItem).where(EvidenceItem.id == evidence_id,
        EvidenceItem.workspace_id == package.workspace_id, EvidenceItem.project_id == package.project_id,
        EvidenceItem.package_id == package.id))
    if item is None: raise not_found()
    return item


def can_view(item, user_id, role, document=None):
    privileged = role in {'admin', 'reviewer'} or item.created_by == user_id
    historic_visibility = document['metadata']['visibility'] if document else item.visibility
    return privileged or (item.visibility == 'project' and historic_visibility == 'project')


def require_visible(item, user_id, role, document=None):
    if not can_view(item, user_id, role, document): raise not_found()


def can_contribute(package, doc, user_id, role):
    return role == 'admin' or (role in {'contributor','reviewer'} and (
        doc['coordinator_id'] == str(user_id) or str(user_id) in doc['intended_contributor_ids'] or role == 'reviewer'))


def require_writable(db, project, package, user_id, role):
    _, allocation, scope = get_context(db, project, package)
    if not can_contribute(package, scope.document, user_id, role):
        raise ApiError(403, 'permission_denied', 'Only an assigned contributor, project reviewer or administrator can add evidence.')
    if package.state in {'cancelled', 'completed'}:
        raise ApiError(409, 'evidence_closed', 'Cancelled or completed work cannot be changed through this evidence workflow.')
    from app.ledger.service import can_extend_partial_evidence
    if not can_extend_partial_evidence(db,package,allocation):
        guard_unissued(allocation)
    return scope


def require_version(package, expected):
    if package.version != expected:
        raise ApiError(409, 'stale_package', 'The work package or its evidence changed. Refresh before trying again.')


def validate_deliverables(metadata, scope):
    known = {d['id'] for d in scope.document['deliverables']}
    if any(str(uid) not in known for uid in metadata.deliverable_ids):
        raise ApiError(422, 'invalid_deliverable', 'Evidence can refer only to deliverables in the current package scope.')


def row_object(db, package, object_id):
    if object_id is None: return None
    row = db.scalar(select(EvidenceObject).where(EvidenceObject.id == object_id,
        EvidenceObject.workspace_id == package.workspace_id, EvidenceObject.project_id == package.project_id,
        EvidenceObject.package_id == package.id))
    if row is None: raise ApiError(409, 'evidence_projection_invalid', 'An evidence object reference is inconsistent. Stop and inspect the records.')
    return row


def object_status(db, package, object_id, storage):
    if not object_id: return 'none'
    obj = row_object(db, package, object_id)
    if db.get(EvidenceRetirement, obj.id): return 'retired'
    if storage is None or obj.backend != storage.backend: return 'storage_unavailable'
    try: storage.check(ref(obj))
    except ObjectMissing: return 'missing'
    except ObjectCorrupt: return 'corrupt'
    except StorageUnavailable: return 'storage_unavailable'
    return 'available'  # size/existence check; full checksum is verified on delivery


def availability(db, package, revision, storage):
    metadata = revision.document['metadata']
    declared = metadata['inclusion']
    if declared == 'excluded': return 'excluded'
    if declared == 'unavailable': return 'declared_unavailable'
    kind = revision.document['kind']
    if kind == 'link': return 'external_unverified'
    if kind == 'file': return object_status(db, package, revision.original_object_id, storage)
    return 'available'


def revision_view(db, package, item, revision, user_id, role, storage):
    require_visible(item, user_id, role, revision.document)
    return {'evidence_id': item.id, 'number': revision.number, 'current_revision': item.current_revision,
        'kind': item.kind, 'document': revision.document, 'content_hash': revision.content_hash,
        'created_by': revision.created_by, 'created_at': revision.created_at, 'reason': revision.reason,
        'availability': availability(db, package, revision, storage),
        'preview_availability': object_status(db, package, revision.preview_object_id, storage),
        'can_edit': role == 'admin' or item.created_by == user_id,
        'historical': revision.number != item.current_revision,
        'claims_notice': 'Authors, dates and provenance are contributor claims, not independent verification.'}


def current_rows(db, package):
    return db.execute(select(EvidenceItem, EvidenceRevision).join(EvidenceRevision,
        (EvidenceRevision.evidence_id == EvidenceItem.id) & (EvidenceRevision.number == EvidenceItem.current_revision))
        .where(EvidenceItem.workspace_id == package.workspace_id, EvidenceItem.project_id == package.project_id,
            EvidenceItem.package_id == package.id).order_by(EvidenceItem.id)).all()


def store_file(db, package, actor, checked, writes, quota_bytes):
    size = len(checked.data) + len(checked.preview or b'')
    # Quota counts all recorded originals and previews, including retired history.
    # Conservative accounting avoids a purge/reupload loop bypassing the pilot cap.
    used = db.scalar(select(func.coalesce(func.sum(EvidenceObject.size_bytes), 0)).where(
        EvidenceObject.workspace_id == package.workspace_id))
    if used + size > quota_bytes:
        raise ApiError(409, 'artifact_quota', 'This workspace reached its pilot artifact quota. Ask the operator to review storage usage.')
    result = []
    for data, maximum in [(checked.data, MAX_UPLOAD_BYTES), (checked.preview, MAX_PREVIEW_BYTES)]:
        if data is None: result.append(None); continue
        try: reference = writes.add(writes.storage.put(package.workspace_id, BytesIO(data), maximum))
        except StorageError: raise ApiError(503, 'storage_unavailable', 'The private artifact store is unavailable. No evidence revision was saved.') from None
        obj = EvidenceObject(id=reference.object_id, workspace_id=package.workspace_id,
            project_id=package.project_id, package_id=package.id, backend=writes.storage.backend,
            sha256=reference.sha256, size_bytes=reference.size_bytes, created_by=actor.id)
        db.add(obj); db.flush(); result.append(obj)
    return result


def validate_kind(kind, body, old=None):
    if (kind != 'statement' and body.text is not None or kind != 'link' and body.source_url is not None
        or kind != 'file' and body.file is not None):
        raise ApiError(422, 'evidence_kind', 'Replacement content must match the existing evidence type.')
    if kind == 'statement' and not body.text or kind == 'link' and not body.source_url:
        raise ApiError(422, 'evidence_content_required', 'Provide the text or URL for this evidence revision.')
    if kind == 'unavailable' and body.metadata.inclusion != 'unavailable':
        raise ApiError(422, 'evidence_kind', 'Missing-evidence records remain unavailable; attach the actual evidence as a separate entry.')
    if kind == 'file' and body.file is None and old is None:
        raise ApiError(422, 'evidence_content_required', 'Select a file to upload.')


def save_revision(db, project, package, actor, role, body, writes, quota_bytes, item=None, *, external_source=None):
    scope = require_writable(db, project, package, actor.id, role)
    kind = item.kind if item else body.kind
    if item and not (role == 'admin' or item.created_by == actor.id):
        raise ApiError(403, 'permission_denied', 'Only the evidence submitter or a project administrator can revise this entry.')
    if item: require_visible(item, actor.id, role)
    request_hash = digest({'kind': kind, 'evidence_id': str(item.id) if item else None, 'command': body.model_dump(mode='json')})
    if external_source is not None:
        request_hash = digest({'command_hash': request_hash, 'external_source': external_source})
    replay = db.scalar(select(EvidenceRevision).where(EvidenceRevision.workspace_id == package.workspace_id,
        EvidenceRevision.project_id == package.project_id, EvidenceRevision.package_id == package.id,
        EvidenceRevision.request_id == body.request_id))
    if replay:
        if replay.created_by != actor.id or replay.request_hash != request_hash:
            raise ApiError(409, 'idempotency_conflict', 'This request identifier was already used for another evidence command.')
        replay_item = get_item(db, package, replay.evidence_id)
        require_visible(replay_item, actor.id, role, replay.document)
        return replay_item, replay, True
    require_version(package, body.expected_package_version)
    validate_deliverables(body.metadata, scope)
    if item:
        if item.current_revision != body.expected_revision:
            raise ApiError(409, 'stale_evidence', 'A newer evidence revision exists. Refresh and review it first.')
        if item.current_revision >= MAX_REVISIONS:
            raise ApiError(409, 'evidence_revision_limit', 'This pilot supports 50 revisions per evidence entry.')
        old = db.get(EvidenceRevision, (item.id, item.current_revision))
    else:
        count = db.scalar(select(func.count()).select_from(EvidenceItem).where(EvidenceItem.package_id == package.id))
        if count >= MAX_ITEMS:
            raise ApiError(409, 'evidence_item_limit', 'This pilot supports 100 evidence entries per work package.')
        old = None
    validate_kind(kind, body, old)
    doc = {'schema_version': 1, 'kind': kind, 'metadata': body.metadata.model_dump(mode='json'),
           'text': body.text, 'source_url': body.source_url, 'file': None}
    if external_source is not None:
        doc['external_source'] = deepcopy(external_source)
    elif old is not None and old.document.get('external_source'):
        # Preserve the pinned source when the human-edited excerpt is revised.
        doc['external_source'] = deepcopy(old.document['external_source'])
    original_id = preview_id = None
    if body.file:
        checked = checked_file(body.file)
        original, preview = store_file(db, package, actor, checked, writes, quota_bytes)
        original_id, preview_id = original.id, preview.id if preview else None
        doc['file'] = {'filename': checked.filename, 'media_type': checked.media_type,
            'size_bytes': original.size_bytes, 'sha256': original.sha256,
            'width': checked.width, 'height': checked.height,
            'preview_sha256': preview.sha256 if preview else None,
            'preview_size_bytes': preview.size_bytes if preview else None,
            'processing': 'decoded_raster_with_regenerated_preview' if preview else 'validated_utf8_plaintext',
            'scanner': 'not_scanned_for_malware'}
    elif kind == 'file':
        original_id, preview_id = old.original_object_id, old.preview_object_id
        doc['file'] = deepcopy(old.document['file'])
        if body.metadata.inclusion == 'included' and object_status(db, package, original_id, writes.storage) != 'available':
            raise ApiError(409, 'replacement_required', 'Upload a replacement or explicitly mark this unavailable artifact as omitted.')
    if item is None:
        item = EvidenceItem(id=uuid4(), workspace_id=package.workspace_id, project_id=package.project_id,
            package_id=package.id, kind=kind, visibility=body.metadata.visibility, current_revision=1, created_by=actor.id)
        db.add(item); db.flush()
    else:
        item.current_revision += 1
        item.visibility = body.metadata.visibility
    revision = EvidenceRevision(evidence_id=item.id, number=item.current_revision,
        workspace_id=package.workspace_id, project_id=package.project_id, package_id=package.id,
        document=doc, content_hash=digest(doc), original_object_id=original_id, preview_object_id=preview_id,
        created_by=actor.id, reason=body.reason, request_id=body.request_id, request_hash=request_hash)
    db.add(revision); db.flush()
    package.version += 1
    # Work-package history is visible to the whole team. Do not leak private notes.
    record_event(db, package, actor, 'evidence_revised' if old else 'evidence_added',
        'Evidence was revised; inspect it with appropriate access.' if old else 'Evidence was added; inspect it with appropriate access.',
        {'evidence_id': str(item.id), 'evidence_revision': revision.number, 'fresh_review_required': True})
    capture_snapshot(db, package, actor, writes.storage, 'Automatic snapshot after an evidence revision.')
    return item, revision, False


def snapshot_document(db, package, storage):
    scope = db.get(WorkPackageRevision, (package.id, package.scope_revision))
    entries, omissions = [], []
    for item, rev in current_rows(db, package):
        status = availability(db, package, rev, storage)
        preview_status = object_status(db, package, rev.preview_object_id, storage)
        entries.append({'evidence_id': str(item.id), 'revision': rev.number, 'revision_hash': rev.content_hash,
            'document': deepcopy(rev.document), 'submitted_by': str(rev.created_by),
            'original_object_id': str(rev.original_object_id) if rev.original_object_id else None,
            'preview_object_id': str(rev.preview_object_id) if rev.preview_object_id else None,
            'availability_at_capture': status, 'preview_availability_at_capture': preview_status})
        if status not in {'available', 'external_unverified'}:
            omissions.append({'evidence_id': str(item.id), 'status': status,
                'reason': rev.document['metadata'].get('omission_reason') or 'The stored artifact is not currently available.'})
        known_deliverables = {item['id'] for item in scope.document['deliverables']}
        if any(item not in known_deliverables for item in rev.document['metadata']['deliverable_ids']):
            omissions.append({'evidence_id': str(item.id), 'status': 'superseded_deliverable',
                'reason': 'This evidence refers to a deliverable no longer in the current scope. Review its attribution.'})
    if not entries:
        omissions.append({'evidence_id': None, 'status': 'no_evidence', 'reason': 'No evidence entries have been provided.'})
    return {'schema_version': 1, 'workspace_id': str(package.workspace_id), 'project_id': str(package.project_id),
        'package_id': str(package.id), 'scope_revision': scope.number, 'scope_hash': scope.content_hash,
        'policy_id': str(package.policy_id), 'policy_hash': scope.document['policy_hash'],
        'scope': deepcopy(scope.document), 'entries': entries, 'omissions': omissions,
        'notice': 'A snapshot records available claims and artifacts, not proof of completion. External URLs are not fetched. File checksums are verified on delivery; capture checks stored availability and metadata.'}


def capture_snapshot(db, package, actor, storage, reason):
    document = snapshot_document(db, package, storage)
    content_hash = digest(document)
    row = db.scalar(select(EvidenceSnapshot).where(EvidenceSnapshot.package_id == package.id,
        EvidenceSnapshot.content_hash == content_hash))
    if row: return row
    count = db.scalar(select(func.count()).select_from(EvidenceSnapshot).where(EvidenceSnapshot.package_id == package.id))
    if count >= 2000: raise ApiError(409, 'snapshot_limit', 'This pilot supports 2,000 evidence snapshots per package.')
    row = EvidenceSnapshot(id=uuid4(), workspace_id=package.workspace_id, project_id=package.project_id,
        package_id=package.id, scope_revision=package.scope_revision, document=document,
        content_hash=content_hash, created_by=actor.id, reason=reason)
    db.add(row); db.flush()
    audit(db, 'evidence.snapshot_created', actor_id=actor.id, workspace_id=package.workspace_id,
        project_id=package.project_id, subject_id=row.id, reason='An immutable evidence packet was captured.',
        details={'package_id': str(package.id), 'hash': content_hash})
    return row


def snapshot_view(db, package, row, user_id, role, storage):
    document = deepcopy(row.document)
    hidden = set()
    current_states = {}
    for index, entry in enumerate(document['entries']):
        item = get_item(db, package, UUID(entry['evidence_id']))
        if not can_view(item, user_id, role, entry['document']):
            hidden.add(entry['evidence_id'])
            document['entries'][index] = {'restricted': True}
        else:
            revision = db.get(EvidenceRevision, (item.id, entry['revision']))
            current_states[str(item.id)] = availability(db, package, revision, storage)
    document['omissions'] = [entry for entry in document['omissions'] if entry['evidence_id'] not in hidden]
    if hidden: document['omissions'].append({'evidence_id': None, 'status': 'restricted',
        'reason': f'{len(hidden)} evidence entries are hidden by current or historical access restrictions.'})
    current_hash = digest(snapshot_document(db, package, storage))
    return {'id': row.id, 'scope_revision': row.scope_revision, 'content_hash': row.content_hash,
        'document': document, 'current_artifact_states': current_states, 'redacted': bool(hidden), 'stale': current_hash != row.content_hash,
        'current_content_hash': current_hash, 'created_by': row.created_by, 'created_at': row.created_at,
        # Auto snapshots have a fixed reason; manually supplied reasons remain team-visible.
        'reason': row.reason, 'historical_notice': 'Historical content is preserved. Current authorization and retirement records still govern every file delivery.'}


def summary(db, project, package, user_id, role, storage, *, offset=0):
    rows = current_rows(db, package)
    visible = [(item, rev) for item, rev in rows if can_view(item, user_id, role, rev.document)]
    doc = snapshot_document(db, package, storage)
    latest_submission = db.scalar(select(WorkSubmission).where(WorkSubmission.package_id == package.id)
        .order_by(WorkSubmission.package_version.desc()).limit(1))
    submitted_hash = latest_submission.snapshot.get('evidence_snapshot_hash') if latest_submission else None
    current_hash = digest(doc)
    latest_snapshot = db.scalar(select(EvidenceSnapshot).where(EvidenceSnapshot.package_id == package.id,
        EvidenceSnapshot.content_hash == current_hash))
    _, allocation, scope = get_context(db, project, package)
    from app.ledger.service import can_extend_partial_evidence
    can_add = can_contribute(package, scope.document, user_id, role) and package.state not in {'cancelled','completed'} and (not allocation.issued_atoms or can_extend_partial_evidence(db,package,allocation))
    return {'package_id': package.id, 'package_version': package.version,
        'items': [revision_view(db, package, item, rev, user_id, role, storage) for item, rev in visible[offset:offset+20]],
        'total_entries': len(rows), 'restricted_entries': len(rows)-len(visible), 'offset': offset,
        'next_offset': offset+20 if len(visible)>offset+20 else None, 'can_add': can_add,
        'can_snapshot': role in {'admin','reviewer'} or can_coordinate(package, scope.document, role, user_id),
        'can_retire': role == 'admin', 'current_snapshot_id': latest_snapshot.id if latest_snapshot else None,
        'current_content_hash': current_hash, 'last_submission_id': latest_submission.id if latest_submission else None,
        'submitted_snapshot_hash': submitted_hash,
        'review_state': 'not_submitted' if not latest_submission else ('legacy_without_evidence' if not submitted_hash else ('current' if submitted_hash == current_hash else 'stale')),
        'retention_notice': 'Original downloads may contain personal metadata and are not malware-scanned. No-store access checks cannot recall files a person already saved.'}


def retire_revision(db, project, package, item, revision, actor, role, body):
    if role != 'admin': raise ApiError(403, 'permission_denied', 'A project administrator must approve artifact retirement.')
    require_version(package, body.expected_package_version)
    if item.kind != 'file': raise ApiError(409, 'artifact_required', 'This evidence revision has no stored artifact to retire.')
    objects = [row_object(db, package, oid) for oid in [revision.original_object_id, revision.preview_object_id] if oid]
    changed = []
    for obj in objects:
        if db.get(EvidenceRetirement, obj.id) is None:
            db.add(EvidenceRetirement(object_id=obj.id, workspace_id=package.workspace_id,
                project_id=package.project_id, package_id=package.id, retired_by=actor.id, reason=body.reason))
            changed.append(obj)
    if changed:
        package.version += 1
        record_event(db, package, actor, 'artifact_retired', 'Stored evidence was retired; its metadata and accounting history remain.',
            {'evidence_id': str(item.id), 'evidence_revision': revision.number, 'fresh_review_required': True})
        db.flush()
    return objects, bool(changed)


def read_object(db, package, revision, storage, *, preview=False):
    if revision.document['metadata']['inclusion'] != 'included':
        raise ApiError(410, 'artifact_omitted', 'This revision is explicitly excluded or unavailable.')
    if revision.original_object_id and db.get(EvidenceRetirement, revision.original_object_id):
        raise ApiError(410, 'artifact_retired', 'This artifact was retired. Its history is preserved, but its bytes are unavailable.')
    object_id = revision.preview_object_id if preview else revision.original_object_id
    if not object_id: raise not_found()
    obj = row_object(db, package, object_id)
    if db.get(EvidenceRetirement, obj.id):
        raise ApiError(410, 'artifact_retired', 'This artifact was retired. Its history is preserved, but its bytes are unavailable.')
    if obj.backend != storage.backend:
        raise ApiError(503, 'storage_backend_unavailable', 'The artifact belongs to an unavailable storage backend. Switching settings does not migrate stored files.')
    try:
        with storage.open(ref(obj)) as source: data = source.read(obj.size_bytes + 1)
    except ObjectMissing: raise ApiError(410, 'artifact_missing', 'The artifact bytes are missing. The reference remains in the evidence history.') from None
    except ObjectCorrupt: raise ApiError(409, 'artifact_integrity', 'The artifact failed its integrity check and was not delivered.') from None
    except StorageUnavailable: raise ApiError(503, 'storage_unavailable', 'The private artifact store is unavailable.') from None
    if len(data) != obj.size_bytes or sha256(data).hexdigest() != obj.sha256:
        raise ApiError(409, 'artifact_integrity', 'The artifact failed its integrity check and was not delivered.')
    return data
