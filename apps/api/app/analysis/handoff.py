"""Reviewed dashboard -> retrospective package. No acceptance or ledger writes.

The caller holds the workspace lock, followed by the existing milestone/batch
locks. A single transaction creates a candidate, ordinary package/evidence and
immutable source claims. Public capture never executes repository code.
"""
from collections import defaultdict
from copy import deepcopy
from datetime import datetime
from hashlib import sha256
import json
from types import SimpleNamespace
from uuid import UUID, uuid4, uuid5, NAMESPACE_URL
from sqlalchemy import select
from app.core.errors import ApiError
from app.projects.authorization import not_found
from app.policies.service import digest, require_ready_policy
from app.security.tokens import utc
from app.contributions.budgets.models import BudgetAllocation
from app.contributions.work_packages.models import WorkPackage, WorkPackageRevision
from app.contributions.work_packages.service import active_people
from app.contributions.work_packages.calculation import normalize_scope, scope_blockers
from app.contributions.reconstruction import service as historical
from app.contributions.reconstruction.models import ReconstructionBatch, ReconstructionSourceClaim
from app.contributions.reconstruction.schemas import CandidateDocument, Promote
from app.contributions.reconstruction.grouping import entity_key
from app.integrations.github.models import GitHubSourceVersion, GitHubEvidenceLink
from app.evidence.schemas import EvidenceCreate, EvidenceMetadata
from app.evidence.service import save_revision, ObjectWrites
from .models import AnalysisHandoff, AnalysisSourceClaim
from . import service
from .analyzer import source_id
from .capture import MAX_BYTES, canonical

NOTICE = ('This creates a draft historical work package with pinned project-visible evidence. '
          'Planning approval, submission, independent review and credit finalization remain separate.')
ROOT_KINDS = {'commit', 'pull_request', 'issue'}


def work_category(outcome):
    # Preserve the original label in the pinned outcome, and disclose the
    # explicit mapping to the existing approved-policy category vocabulary.
    return {'testing':'qa', 'audio':'art'}.get(outcome['category'], outcome['category'])


def source_claim_keys(source):
    keys = {entity_key(source)}
    if source.kind == 'commit':
        keys.add(sha256(('github-shared-commit:' + source.remote_key).encode()).hexdigest())
    return keys


def primary_link_guard(db, project, source, package_id=None):
    """Used by both ordinary GitHub linking and historical source grouping."""
    query = historical.scoped(AnalysisSourceClaim, project).where(
        AnalysisSourceClaim.entity_key.in_(source_claim_keys(source)))
    for claim in db.scalars(query):
        row = db.get(AnalysisHandoff, claim.handoff_id)
        if row.package_id != package_id:
            raise ApiError(409, 'analysis_source_already_handed_off',
                'This source entity or shared commit already belongs to a reviewed dashboard package. Inspect that package instead of crediting it twice.')


def options(db, project, actor):
    rows = db.scalars(historical.scoped(ReconstructionBatch, project)
        .where(ReconstructionBatch.state == 'approved').order_by(ReconstructionBatch.created_at, ReconstructionBatch.id).limit(100))
    return {'batches':[{'id':str(b.id), 'title':b.definition['title'], 'start_at':b.definition['start_at'],
        'end_before':b.definition['end_before']} for b in rows], 'participants':list(active_people(db, project).values()),
        'my_user_id':str(actor), 'notice':NOTICE}


def captured_sources(run, outcome):
    if outcome['origin'] == 'manual': return []
    ids = {s['id'] for s in outcome['sources']}
    docs = {source_id(d):d for d in run.progress['sources']}
    if not ids <= docs.keys():
        raise ApiError(409, 'analysis_source_integrity', 'The outcome no longer reconciles with its captured evidence.')
    return [SimpleNamespace(document=docs[k], kind=docs[k]['kind'], remote_key=docs[k]['remote_key']) for k in sorted(ids)]


def claim_keys(outcome, sources):
    if outcome['origin'] == 'manual':
        return {sha256(('analysis-manual:' + outcome['manual_id']).encode()).hexdigest()}
    primary = [s for s in sources if s.kind in ROOT_KINDS] or sources
    return set().union(*(source_claim_keys(s) for s in primary))


def duplicate_blockers(db, project, sources, keys):
    blockers = []
    if db.scalar(historical.scoped(AnalysisSourceClaim, project).where(AnalysisSourceClaim.entity_key.in_(keys)).limit(1)):
        blockers.append('A primary source or this manual entry already has a preserved handoff. Open its existing package.')
    source_entities = {entity_key(s) for s in sources}
    if db.scalar(historical.scoped(ReconstructionSourceClaim, project)
        .where(ReconstructionSourceClaim.entity_key.in_(source_entities)).limit(1)):
        blockers.append('Evidence is already assigned to a historical reconstruction candidate. Resolve it in that workflow.')
    roots = [s for s in sources if s.kind in ROOT_KINDS] or sources
    commits = {s.remote_key for s in roots if s.kind == 'commit'}
    remote_keys = {s.remote_key for s in roots}
    if remote_keys:
        q = select(GitHubSourceVersion).join(GitHubEvidenceLink, GitHubEvidenceLink.source_id == GitHubSourceVersion.id).where(
            GitHubSourceVersion.workspace_id == project.workspace_id, GitHubSourceVersion.project_id == project.id,
            GitHubSourceVersion.remote_key.in_(remote_keys))
        for source in db.scalars(q):
            if entity_key(source) in source_entities or source.kind == 'commit' and source.remote_key in commits:
                blockers.append('A primary entity or shared commit is already attached to another work package. Resolve possible duplicate credit.'); break
        q = select(GitHubSourceVersion).join(ReconstructionSourceClaim, ReconstructionSourceClaim.source_id == GitHubSourceVersion.id).where(
            GitHubSourceVersion.workspace_id == project.workspace_id, GitHubSourceVersion.project_id == project.id,
            GitHubSourceVersion.kind == 'commit', GitHubSourceVersion.remote_key.in_(commits))
        if db.scalar(q.limit(1)):
            blockers.append('This shared commit is already assigned to a historical candidate in another capture.')
    return blockers


def preview(db, project, actor, report_id, outcome_id, batch_id):
    run = service.run_in_project(db, project, report_id)
    if run.state != 'completed': raise ApiError(409, 'analysis_report_incomplete', 'Complete the source report first.')
    batch = historical.get_batch(db, project, batch_id, lock=True)
    d = service.report_dashboard(db, project, actor, 'admin', run)
    outcome = next((o for o in d['outcomes'] if o['id'] == outcome_id), None)
    if not outcome: raise not_found()
    sources = captured_sources(run, outcome); keys = claim_keys(outcome, sources)
    blockers = duplicate_blockers(db, project, sources, keys)
    if batch.state != 'approved': blockers.append('Approve the historical scope before preparing its work packages.')
    require_ready_policy(db, project, batch.policy_id)
    period = run.report['scope']
    instant = lambda v: datetime.fromisoformat(v.replace('Z', '+00:00'))
    if instant(period['start_at']) < instant(batch.definition['start_at']) or instant(period['end_before']) > instant(batch.definition['end_before']):
        blockers.append('The report work window must fit inside the approved historical scope.')
    if len(outcome['sources']) > 30: blockers.append('This outcome exceeds 30 pinned sources. Prepare a smaller bounded report before handing it off.')
    proposal = outcome['proposal']
    if not proposal or outcome['proposal_stale'] or proposal['proposed_atoms'] <= 0:
        blockers.append('Save a positive, current-evidence unit proposal before preparing a package.')
    elif sum(e['atoms'] for e in proposal['entries']) != proposal['proposed_atoms']:
        blockers.append('Assign every proposed atom before preparing a package.')
    people = active_people(db, project)
    involved = {p['key'] for p in outcome['contributors']} | {e['contributor_key'] for e in (proposal or {}).get('entries', [])}
    profiles = [deepcopy(p) for p in d['contributors'] if p['key'] in involved]
    identities = [{'external_key':p['key'], 'name':p['name'], 'usernames':p['github_usernames'],
        'aliases':p['aliases'], 'suggested_user_id':p['key'][6:] if p['key'].startswith('local:') and p['key'][6:] in people else None}
        for p in profiles]
    occupied = select(WorkPackage.allocation_id).where(WorkPackage.project_id == project.id)
    allocations = list(db.scalars(historical.scoped(BudgetAllocation, project).where(
        BudgetAllocation.milestone_id == batch.milestone_id, BudgetAllocation.status == 'active',
        BudgetAllocation.issued_atoms == 0, BudgetAllocation.category == work_category(outcome),
        BudgetAllocation.atoms == (proposal or {}).get('proposed_atoms', -1), BudgetAllocation.id.not_in(occupied))
        .order_by(BudgetAllocation.created_at, BudgetAllocation.id).limit(201)))
    if not allocations: blockers.append('Create an unlinked allocation in this historical milestone with the same category and exact proposed units, then refresh.')
    manual = next((m for m in d['manual_entries'] if m['id'] == outcome.get('manual_id')), None)
    document = {'schema_version':1, 'report_id':str(run.id), 'draft_version':d['draft_version'],
        'outcome':deepcopy(outcome), 'work_category':work_category(outcome), 'manual_entry':deepcopy(manual), 'identities':identities,
        'work_window':period, 'report_omissions':run.report['omissions'], 'rubric':d['rubric'],
        'batch_id':str(batch.id), 'batch_version':batch.version, 'historical_scope':batch.definition,
        'policy_id':str(batch.policy_id), 'primary_claim_keys':sorted(keys), 'notice':NOTICE}
    if len(canonical(document)) > MAX_BYTES:
        raise ApiError(409, 'analysis_handoff_limit', 'This pinned outcome exceeds the 2 MiB handoff bound.')
    allocation_view = [{'id':str(a.id), 'milestone_id':str(batch.milestone_id), 'milestone_name':batch.definition['title'],
        'policy_id':str(batch.policy_id), 'title':a.title, 'category':a.category, 'pool_key':a.pool_key,
        'atoms':a.atoms, 'version':a.version} for a in allocations[:200]]
    base = {'document':document, 'participants':list(people.values()), 'allocations':allocation_view,
        'allocations_truncated':len(allocations) > 200, 'my_user_id':str(actor), 'blockers':blockers}
    return {**base, 'review_hash':digest(base)}


def create(db, project, actor, body, storage, quota_bytes):
    fingerprint = digest(body.model_dump(mode='json'))
    prior = db.scalar(historical.scoped(AnalysisHandoff, project).where(AnalysisHandoff.request_id == body.request_id))
    if prior:
        if prior.created_by != actor.id or prior.request_hash != fingerprint:
            raise ApiError(409, 'idempotency_conflict', 'This request identifier belongs to another reviewed handoff.')
        return {'handoff_id':str(prior.id), 'package_id':str(prior.package_id), 'replayed':True}
    view = preview(db, project, actor.id, body.report_id, body.outcome_id, body.batch_id)
    doc = view['document']
    if doc['draft_version'] != body.expected_version or doc['batch_version'] != body.expected_batch_version or view['review_hash'] != body.reviewed_hash:
        raise ApiError(409, 'analysis_handoff_stale', 'The outcome, identities, historical scope or budget changed. Refresh the preview and inspect it again.')
    if view['blockers']: raise ApiError(409, 'analysis_handoff_blocked', 'Resolve the preview blockers before preparing this package.')
    allocation = next((a for a in view['allocations'] if a['id'] == str(body.allocation_id)), None)
    if not allocation or allocation['version'] != body.expected_allocation_version:
        raise ApiError(409, 'analysis_handoff_budget_changed', 'Select a current matching allocation from this reviewed historical scope.')
    resolutions = {r.external_key:r.model_dump(mode='json') for r in body.identities}
    if set(resolutions) != {i['external_key'] for i in doc['identities']}:
        raise ApiError(409, 'analysis_handoff_identity', 'Explicitly resolve every observed and proposed identity, without adding unrelated ones.')
    people = active_people(db, project)
    for key, r in resolutions.items():
        if r['disposition'] == 'participant' and (r['user_id'] not in people or key.startswith('local:') and r['user_id'] != key[6:]):
            raise ApiError(409, 'analysis_handoff_identity', 'Use current project participants and preserve explicitly linked local identities.')
    expected = defaultdict(int)
    for e in doc['outcome']['proposal']['entries']:
        if e['atoms'] == 0: continue
        r = resolutions[e['contributor_key']]
        if r['disposition'] != 'participant':
            raise ApiError(409, 'analysis_handoff_attribution', 'Every positive proposed recipient needs an explicit current participant mapping.')
        expected[r['user_id']] += e['atoms']
    scope = normalize_scope(body.scope, allocation['atoms'], people)
    if scope_blockers(scope, set(people)):
        raise ApiError(409, 'incomplete_scope', 'Fully budget and attribute independently acceptable deliverables before preparing the package.')
    actual = defaultdict(int)
    for d in scope['deliverables']:
        for e in d['resolved_attributions']: actual[e['user_id']] += e['atoms']
    participants = {r['user_id'] for r in resolutions.values() if r['disposition'] == 'participant'}
    if dict(actual) != dict(expected) or set(scope['intended_contributor_ids']) != participants:
        raise ApiError(409, 'analysis_handoff_attribution', 'The scope must preserve the exact reviewed proposal and participant dispositions. Correct the dashboard proposal first if the attribution needs to change.')
    batch = historical.get_batch(db, project, body.batch_id, lock=True)
    candidate_doc = CandidateDocument(title=body.scope.title, category=doc['work_category'], summary=body.scope.outcome).model_dump(mode='json')
    hid = uuid4()
    candidate = historical.new_candidate(db, project, batch, actor, candidate_doc,
        {'kind':'reviewed_dashboard_v1', 'handoff_id':str(hid), 'report_id':str(body.report_id), 'outcome_id':body.outcome_id})
    candidate_view = historical.candidate_view(db, project, batch, candidate)
    command = Promote(request_id=uuid5(NAMESPACE_URL, str(body.request_id)+':promote'), expected_version=batch.version,
        reviewed_hash=candidate_view['review_hash'], reviewed=True, candidate_id=candidate.id,
        allocation_id=body.allocation_id, expected_allocation_version=body.expected_allocation_version,
        scope=body.scope, project_sharing_confirmed=True, reason=body.reason)
    result = historical.promote(db, project, batch, actor, command, storage, quota_bytes)
    package = db.get(WorkPackage, UUID(result['package_id']))
    doc = {**doc, 'identity_resolutions':sorted(resolutions.values(), key=lambda r:r['external_key']),
        'scope':db.get(WorkPackageRevision, (package.id, package.scope_revision)).document,
        'allocation':allocation, 'candidate_id':str(candidate.id), 'package_id':str(package.id)}
    if len(canonical(doc)) > MAX_BYTES:
        raise ApiError(409, 'analysis_handoff_limit', 'The complete evidence, identity and scope record exceeds the 2 MiB handoff bound.')
    row = AnalysisHandoff(id=hid, workspace_id=project.workspace_id, project_id=project.id, report_id=body.report_id,
        package_id=package.id, created_by=actor.id, request_id=body.request_id, request_hash=fingerprint,
        reason=body.reason, content_hash=digest(doc), document=doc)
    db.add(row); db.flush()
    for key in doc['primary_claim_keys']:
        db.add(AnalysisSourceClaim(workspace_id=project.workspace_id, project_id=project.id, handoff_id=hid, entity_key=key))
    db.flush()
    outcome = doc['outcome']; manual = doc['manual_entry']; run = service.run_in_project(db, project, body.report_id)
    occurred = utc(datetime.fromisoformat(manual['performed_at'].replace('Z','+00:00'))).date() if manual else utc(run.created_at).date()
    category = outcome['category'] if outcome['category'] in {'code','art','design','documentation'} else 'qa' if outcome['category'] == 'testing' else 'other'
    title = body.scope.title
    overview = {k:outcome[k] for k in ('id','title','summary','category','origin','proposal','limitations')}
    overview.update(findings=outcome.get('findings', []), work_window=doc['work_window'],
        identity_resolutions=doc['identity_resolutions'], manual_performed_at=manual['performed_at'] if manual else None,
        report_omissions=doc['report_omissions'], notice=NOTICE)
    evidence = [(title, overview)] + [(s['title'][:120], s) for s in outcome['sources']]
    with ObjectWrites(storage) as writes:
        for n, (label, content) in enumerate(evidence):
            statement = json.dumps(content, ensure_ascii=True, sort_keys=True, indent=2)
            if len(statement) > 12000:
                raise ApiError(409, 'analysis_handoff_evidence_limit', 'One evidence record exceeds the 12,000-character statement bound. Prepare a smaller report or proposal.')
            metadata = EvidenceMetadata(title=label if len(label) >= 2 else title,
                description='Exact reviewed dashboard findings or captured source excerpt; inspect the limitations and preserved provenance.',
                claimed_authors='See the explicitly reviewed identity dispositions; authorship and completion remain claims.',
                provenance='Pinned dashboard report '+str(run.id)+'. Dates describe manual work or the report capture, not independent acceptance.',
                occurred_on=occurred, category=category, visibility='project')
            save_revision(db, project, package, actor, 'admin', EvidenceCreate(kind='statement', metadata=metadata, text=statement,
                expected_package_version=package.version, request_id=uuid5(NAMESPACE_URL, str(hid)+':evidence:'+str(n)), reason=body.reason),
                writes, quota_bytes, external_source={'provider':'repository_analysis', 'handoff_id':str(hid),
                    'report_id':str(run.id), 'outcome_id':outcome['id'], 'handoff_hash':row.content_hash,
                    'source_fingerprint':outcome['sources'][n-1].get('content_hash') if n else None})
    return {'handoff_id':str(hid), 'package_id':str(package.id), 'replayed':False}
