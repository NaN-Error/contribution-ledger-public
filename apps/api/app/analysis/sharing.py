"""Exact, explicit project disclosure. No anonymous access or credit commands."""
from copy import deepcopy
from uuid import uuid4
from sqlalchemy import select, func
from app.core.errors import ApiError
from app.policies.service import digest
from app.projects.authorization import not_found
from app.reporting.service import dashboard as recognized_dashboard
from app.security.audit import audit
from app.security.tokens import now
from .models import AnalysisPublication, AnalysisPublicationRevocation
from .analyzer import RUBRIC
from .capture import MAX_BYTES
from .service import run_in_project, report_dashboard
from app.integrations.github.normalization import canonical

NOTICE = ('This exact draft snapshot is shared with current project members. It includes contributor identities, '
    'source excerpts and repository context, manual work included in the period, unit proposals and a hypothetical '
    'USD scenario. It excludes raw import packets, excluded manual work and correction history. '
    'Sharing is not acceptance or credit. Later draft edits do not change this snapshot.')


def scoped(model, project):
    return select(model).where(model.workspace_id == project.workspace_id, model.project_id == project.id)


def preview(db, project, actor, report_id):
    run = run_in_project(db, project, report_id)
    if run.state != 'completed': raise ApiError(409, 'analysis_report_incomplete', 'Complete the source report first.')
    d = report_dashboard(db, project, actor, 'admin', run)
    # Whitelist the complete read-only view. Never copy run.progress, raw report outcomes,
    # stored drafts/aliases, excluded entries, unrelated reports or restricted credit details.
    document = {k:deepcopy(d[k]) for k in ('report_id', 'draft_version', 'contributors', 'outcomes', 'rubric',
        'stale_proposal_count', 'proposed_denominator_atoms', 'unassigned_atoms', 'scenario', 'denominator_label')}
    document['report'] = {k:deepcopy(d['report'][k]) for k in ('scope', 'repositories', 'omissions')}
    included = {o['id'] for o in document['outcomes']}
    source_keys = {p['key'] for p in run.report['contributors']}
    source_keys.update(m['contributor_key'] for m in d['manual_entries']
        if any(o.get('manual_id') == m['id'] for o in document['outcomes']))
    for o in document['outcomes']:
        if o['proposal']: source_keys.update(e['contributor_key'] for e in o['proposal']['entries'])
    document['contributors'] = [p for p in document['contributors'] if included.intersection(p['outcome_ids'])]
    for p in document['contributors']:
        related = [o for o in document['outcomes'] if o['id'] in p['outcome_ids']]
        p['repositories'] = sorted({r for o in related for r in o['repositories']})
        p['roles'] = sorted({role for o in related for c in o['contributors'] if c['key'] == p['key'] for role in c['roles']})
        p['aliases'] = [a for a in p['aliases'] if a['key'] in source_keys or a['key'] == p['key']]
        p['github_usernames'] = sorted({a['username'] for a in p['aliases'] if a.get('username')})
    # Revision management remains private even when an included manual outcome is shared.
    document['manual_entries'] = []; document['aliases'] = {}
    document['sharing_notice'] = NOTICE
    if len(canonical(document)) > MAX_BYTES:
        raise ApiError(409, 'analysis_share_limit', 'The complete shared snapshot exceeds the 2 MiB pilot limit.')
    return {'document':document, 'review_hash':digest(document), 'notice':NOTICE}


def publish(db, project, actor, body):
    fingerprint = digest(body.model_dump(mode='json'))
    existing = db.scalar(scoped(AnalysisPublication, project).where(AnalysisPublication.request_id == body.request_id))
    if existing:
        if existing.created_by != actor or existing.request_hash != fingerprint:
            raise ApiError(409, 'idempotency_conflict', 'This request ID belongs to another sharing command.')
        return {'publication_id':str(existing.id), 'content_hash':existing.content_hash, 'replayed':True}
    view = preview(db, project, actor, body.report_id)
    if view['document']['draft_version'] != body.expected_version or view['review_hash'] != body.reviewed_hash:
        raise ApiError(409, 'analysis_share_stale', 'The reviewed report or draft changed. Inspect a new sharing preview.')
    if db.scalar(select(func.count()).select_from(AnalysisPublication).where(AnalysisPublication.project_id == project.id)) >= 200:
        raise ApiError(409, 'analysis_publication_limit', 'This pilot preserves up to 200 shared snapshots per project.')
    row = AnalysisPublication(id=uuid4(), workspace_id=project.workspace_id, project_id=project.id,
        created_by=actor, request_id=body.request_id, request_hash=fingerprint, reason=body.reason,
        content_hash=view['review_hash'], document=view['document'], created_at=now())
    db.add(row)
    audit(db, 'analysis.report_shared', actor_id=actor, workspace_id=project.workspace_id, project_id=project.id,
        reason=body.reason, details={'publication_id':str(row.id), 'content_hash':row.content_hash, 'draft_only':True})
    return {'publication_id':str(row.id), 'content_hash':row.content_hash, 'replayed':False}


def publications(db, project, *, history=False):
    p, r = AnalysisPublication, AnalysisPublicationRevocation
    q = select(p.id, p.created_at, p.created_by, p.reason, p.content_hash,
        p.document['report_id'].as_string().label('report_id'),
        p.document['draft_version'].as_integer().label('draft_version'),
        r.created_at.label('revoked_at'), r.reason.label('revocation_reason'))\
        .outerjoin(r, r.publication_id == p.id).where(p.workspace_id == project.workspace_id, p.project_id == project.id)
    if not history: q = q.where(r.publication_id.is_(None))
    return [dict(row) for row in db.execute(q.order_by(p.created_at.desc(), p.id.desc()).limit(200)).mappings()]


def publication(db, project, publication_id):
    row = db.scalar(scoped(AnalysisPublication, project).where(AnalysisPublication.id == publication_id))
    if row is None: raise not_found()
    return row


def revoke(db, project, actor, publication_id, body):
    publication(db, project, publication_id)
    fingerprint = digest({'publication_id':str(publication_id), 'command':body.model_dump(mode='json')})
    prior = db.scalar(scoped(AnalysisPublicationRevocation, project).where(AnalysisPublicationRevocation.request_id == body.request_id))
    if prior:
        if prior.created_by != actor or prior.request_hash != fingerprint:
            raise ApiError(409, 'idempotency_conflict', 'This request ID belongs to another revocation.')
        return {'publication_id':str(prior.publication_id), 'replayed':True}
    if db.get(AnalysisPublicationRevocation, publication_id):
        raise ApiError(409, 'analysis_share_revoked', 'This snapshot is already revoked. Share a new reviewed snapshot to restore access.')
    db.add(AnalysisPublicationRevocation(publication_id=publication_id, workspace_id=project.workspace_id,
        project_id=project.id, created_by=actor, request_id=body.request_id, request_hash=fingerprint, reason=body.reason, created_at=now()))
    audit(db, 'analysis.report_revoked', actor_id=actor, workspace_id=project.workspace_id, project_id=project.id,
        reason=body.reason, details={'publication_id':str(publication_id)})
    return {'publication_id':str(publication_id), 'replayed':False}


def shared_overview(db, project, actor, role, publication_id=None):
    items = publications(db, project)
    row = publication(db, project, publication_id) if publication_id else (publication(db, project, items[0]['id']) if items else None)
    if row and db.get(AnalysisPublicationRevocation, row.id): raise not_found()
    if row and digest(row.document) != row.content_hash:
        raise ApiError(409, 'analysis_share_corrupt', 'The preserved shared report failed its integrity check.')
    document = deepcopy(row.document) if row else {'report_id':None, 'draft_version':0, 'contributors':[], 'outcomes':[],
        'rubric':RUBRIC, 'stale_proposal_count':0, 'proposed_denominator_atoms':0, 'unassigned_atoms':0,
        'manual_entries':[], 'aliases':{}, 'denominator_label':'No draft report has been shared with this project yet.',
        'scenario':{'currency':'USD', 'amount_cents':0, 'allocated_cents':0, 'unallocated_cents':0, 'synthetic_only':True, 'payable':False},
        'report':{'scope':None, 'repositories':[], 'omissions':[]}}
    # Approved credit is resolved afresh under the caller's ordinary reporting permissions.
    document['recognized'] = recognized_dashboard(db, project, actor, role)
    return {'can_manage':False, 'runs':[], 'imports':[], 'dashboard':document,
        'shared':{'publication_id':str(row.id) if row else None, 'created_at':row.created_at if row else None,
            'content_hash':row.content_hash if row else None, 'items':items, 'notice':NOTICE}}
