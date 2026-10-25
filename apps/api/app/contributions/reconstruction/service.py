"""Project-scoped historical workflow.

All commands run under the existing workspace lock, then the milestone/batch
locks. Promotion calls the ordinary package/evidence services; credit posting
is deliberately absent. Freezing archives already accepted units, not money.
"""
from collections import defaultdict
from datetime import datetime
from uuid import UUID, uuid4, uuid5, NAMESPACE_URL
from sqlalchemy import select, func
from app.core.errors import ApiError
from app.projects.authorization import not_found
from app.policies.service import digest, require_ready_policy, get_policy, policy_view
from app.security.audit import audit
from app.security.tokens import utc, now
from app.contributions.budgets.models import BudgetAllocation, Milestone
from app.contributions.budgets.service import get_milestone, snapshot as budget_snapshot
from app.contributions.work_packages.models import WorkPackage, WorkPackageRevision
from app.contributions.work_packages.service import create_package, active_people
from app.contributions.work_packages.schemas import PackageCreate
from app.contributions.work_packages.calculation import normalize_scope, scope_blockers
from app.integrations.github.models import (GitHubImport, GitHubSourceVersion, GitHubObservation,
    GitHubIdentity, GitHubEvidenceLink)
from app.ledger.models import CreditAward
from app.ledger.service import balance_rows, open_disputes
from app.reviews.models import ReviewRound
from .models import (ReconstructionBatch, ReconstructionCandidate, ReconstructionSourceClaim,
    ReconstructionEvent, ReconstructionMissingClaim, OpeningBalanceSnapshot)
from .schemas import CandidateDocument
from .grouping import groups, group_title, entity_key

MAX_BATCHES=100
MAX_CANDIDATES=200
MAX_SOURCES_PER_IMPORT=500
MAX_SOURCES_PER_PACKAGE=30
MAX_EVENTS=2000
NOTICE=('Retrospective reconstruction, not proof of an agreement in the past. '
        'Imported activity and proposed allocations are not earned credit. '
        'Each deliverable still requires independent review and explicit finalization.')


def scoped(model,project):
    return select(model).where(model.workspace_id==project.workspace_id,model.project_id==project.id)


def get_batch(db,project,batch_id,*,lock=False):
    row=db.scalar(scoped(ReconstructionBatch,project).where(ReconstructionBatch.id==batch_id))
    if row is None:raise not_found()
    if lock:
        get_milestone(db,project,row.milestone_id,lock=True)
        row=db.scalar(scoped(ReconstructionBatch,project).where(ReconstructionBatch.id==batch_id)
            .with_for_update().execution_options(populate_existing=True))
    return row


def get_candidate(db,project,batch,candidate_id):
    row=db.scalar(scoped(ReconstructionCandidate,project).where(
        ReconstructionCandidate.batch_id==batch.id,ReconstructionCandidate.id==candidate_id)
        .execution_options(populate_existing=True))
    if row is None:raise not_found()
    return row


def candidate_rows(db,project,batch):
    return list(db.scalars(scoped(ReconstructionCandidate,project).where(ReconstructionCandidate.batch_id==batch.id)
        .order_by(ReconstructionCandidate.created_at,ReconstructionCandidate.id)))


def claims(db,project,batch,candidate=None):
    q=scoped(ReconstructionSourceClaim,project).where(ReconstructionSourceClaim.batch_id==batch.id)
    if candidate:q=q.where(ReconstructionSourceClaim.candidate_id==candidate.id)
    return list(db.scalars(q.order_by(ReconstructionSourceClaim.entity_key)))


def command_hash(action,body):return digest({'action':action,'input':body.model_dump(mode='json')})


def replay(db,project,batch,actor,action,body):
    row=db.scalar(scoped(ReconstructionEvent,project).where(
        ReconstructionEvent.actor_id==actor.id,ReconstructionEvent.request_id==body.request_id))
    if row:
        if row.batch_id!=batch.id or row.command_hash!=command_hash(action,body):
            raise ApiError(409,'idempotency_conflict','This request identifier belongs to a different reconstruction command.')
        return row.record['details'].get('result',{})
    return None


def mutable(batch,body,*,approved=False):
    if batch.state=='frozen':raise ApiError(409,'opening_balance_frozen','This opening balance is archived. Use a new milestone for additional work.')
    if batch.version!=body.expected_version:raise ApiError(409,'stale_version','The reconstruction changed. Refresh and review before trying again.')
    if approved and batch.state!='approved':raise ApiError(409,'historical_scope_unapproved','Approve this historical scope before creating work packages.')


def emit(db,project,batch,actor,action,body,details,*,initial=False):
    if not initial:batch.version+=1
    if batch.version>MAX_EVENTS:raise ApiError(409,'reconstruction_history_limit','This pilot supports 2,000 recorded changes per historical batch.')
    previous=db.scalar(select(ReconstructionEvent).where(ReconstructionEvent.batch_id==batch.id)
        .order_by(ReconstructionEvent.version.desc()).limit(1))
    record={'batch_id':str(batch.id),'version':batch.version,'action':action,'actor_id':str(actor.id),
        'request_id':str(body.request_id),'command_hash':command_hash(action,body),'reason':getattr(body,'reason','Participant submitted missing contribution'),
        'previous_hash':previous.record_hash if previous else None,'details':details}
    db.add(ReconstructionEvent(workspace_id=project.workspace_id,project_id=project.id,batch_id=batch.id,
        version=batch.version,actor_id=actor.id,request_id=body.request_id,command_hash=record['command_hash'],
        action=action,reason=record['reason'],record=record,record_hash=digest(record),previous_hash=record['previous_hash']))
    audit(db,'reconstruction.'+action,actor_id=actor.id,workspace_id=project.workspace_id,project_id=project.id,
        subject_id=batch.id,reason=record['reason'],details={'version':batch.version,'credit_issued':False})
    db.flush()


def credit_capture(db,project,policy_id):
    """Event-derived current attribution; never a cached balance or an AI score."""
    awards=list(db.scalars(scoped(CreditAward,project).where(CreditAward.policy_id==policy_id)
        .order_by(CreditAward.id)))
    if len(awards)>6000:raise ApiError(409,'report_limit','The bounded pilot cannot capture more than 6,000 awards per policy.')
    pools={};records=[]
    for award in awards:
        entries=balance_rows(db,award)
        records.append({'id':str(award.id),'package_id':str(award.package_id),'milestone_id':str(award.milestone_id),
            'pool_key':award.pool_key,'budget_atoms':award.budget_atoms,'attributions':entries})
        pool=pools.setdefault(award.pool_key,{'denominator_atoms':0,'people':{}})
        pool['denominator_atoms']+=award.budget_atoms
        for e in entries:
            p=pool['people'].setdefault(e['user_id'],{'user_id':e['user_id'],'display_name':e['display_name'],'atoms':0})
            p['atoms']+=e['atoms']
    for pool in pools.values():
        pool['people']=sorted(pool['people'].values(),key=lambda p:p['user_id'])
        for p in pool['people']:p['share']={'numerator':p['atoms'],'denominator':pool['denominator_atoms']}
    return {'policy_id':str(policy_id),'pools':pools,'awards':records}


def definition_view(batch):
    return {'id':str(batch.id),'milestone_id':str(batch.milestone_id),'policy_id':str(batch.policy_id),
        'definition':batch.definition,'state':batch.state,'version':batch.version,'created_at':utc(batch.created_at).isoformat(),
        'notice':NOTICE}


def create_batch(db,project,actor,body):
    prior=db.scalar(scoped(ReconstructionBatch,project).where(ReconstructionBatch.created_by==actor.id,
        ReconstructionBatch.request_id==body.request_id))
    fingerprint=digest(body.model_dump(mode='json'))
    if prior:
        if prior.request_hash!=fingerprint:raise ApiError(409,'idempotency_conflict','This request was already used for another historical scope.')
        return prior
    if db.scalar(select(func.count()).select_from(ReconstructionBatch).where(ReconstructionBatch.project_id==project.id))>=MAX_BATCHES:
        raise ApiError(409,'batch_limit','This pilot supports 100 historical batches per project.')
    milestone=get_milestone(db,project,body.milestone_id,lock=True)
    require_ready_policy(db,project,milestone.policy_id)
    if milestone.status!='active' or milestone.allocated_atoms or milestone.issued_atoms:
        raise ApiError(409,'dedicated_milestone_required','Choose an approved, dedicated milestone without allocations or issued credit.')
    if db.scalar(select(ReconstructionBatch.id).where(ReconstructionBatch.milestone_id==milestone.id)):
        raise ApiError(409,'milestone_already_reconstructed','This milestone is already assigned to a historical scope.')
    definition=body.model_dump(mode='json',exclude={'request_id','milestone_id','reason'})
    definition['initial_approved_budget']=budget_snapshot(db,milestone)
    row=ReconstructionBatch(id=uuid4(),workspace_id=project.workspace_id,project_id=project.id,milestone_id=milestone.id,
        policy_id=milestone.policy_id,created_by=actor.id,request_id=body.request_id,request_hash=fingerprint,
        definition=definition,state='draft',version=1)
    db.add(row);db.flush()
    emit(db,project,row,actor,'created',body,{'definition':definition,'result':{'batch_id':str(row.id)}},initial=True)
    return row


def review_context(db,project,batch,actor_id):
    milestone=get_milestone(db,project,batch.milestone_id)
    policy=policy_view(db,project,get_policy(db,project,batch.policy_id),actor_id)
    current=credit_capture(db,project,batch.policy_id)
    return {'batch_id':str(batch.id),'version':batch.version,'definition':batch.definition,
        'milestone':budget_snapshot(db,milestone),'policy_hash':policy['content_hash'],
        'policy_ready':policy['ready_for_pinned_work'],'credit':current}


def approve_scope(db,project,batch,actor,body):
    prior=replay(db,project,batch,actor,'scope_approved',body)
    if prior is not None:return prior
    mutable(batch,body)
    if batch.state!='draft':raise ApiError(409,'scope_already_approved','The historical scope is already approved.')
    require_ready_policy(db,project,batch.policy_id)
    context=review_context(db,project,batch,actor.id)
    if digest(context)!=body.reviewed_hash:raise ApiError(409,'review_changed','The budget, policy or contribution baseline changed. Review again.')
    batch.state='approved';result={'batch_id':str(batch.id)}
    emit(db,project,batch,actor,'scope_approved',body,{'baseline':context,'result':result})
    return result


def new_candidate(db,project,batch,actor,document,provenance):
    if db.scalar(select(func.count()).select_from(ReconstructionCandidate).where(ReconstructionCandidate.batch_id==batch.id))>=MAX_CANDIDATES:
        raise ApiError(409,'candidate_limit','This pilot supports 200 candidate records per historical batch, including superseded ones.')
    row=ReconstructionCandidate(id=uuid4(),workspace_id=project.workspace_id,project_id=project.id,batch_id=batch.id,
        created_by=actor.id,state='draft',version=1,document={**document,'provenance':provenance})
    db.add(row);db.flush();return row


def candidate_record(row):
    return {'id':str(row.id),'version':row.version,'state':row.state,'document':row.document,
        'package_id':str(row.package_id) if row.package_id else None}


def import_groups(db,project,batch,actor,body):
    action='history_grouped';prior=replay(db,project,batch,actor,action,body)
    if prior is not None:return prior
    mutable(batch,body)
    job=db.scalar(scoped(GitHubImport,project).where(GitHubImport.id==body.import_id))
    if job is None:raise not_found()
    if job.state not in {'completed','completed_incomplete'}:
        raise ApiError(409,'import_not_complete','Finish the bounded import before grouping its captured observations.')
    start=datetime.fromisoformat(batch.definition['start_at'].replace('Z','+00:00'))
    end=datetime.fromisoformat(batch.definition['end_before'].replace('Z','+00:00'))
    if utc(job.start_at)<start or utc(job.end_before)>end:
        raise ApiError(409,'historical_scope_mismatch','The selected import interval must be inside this historical scope. Use a matching bounded historical import.')
    if job.capture_mode!='historical':
        raise ApiError(409,'historical_import_required','Use a historical import, not a rolling reconciliation, for an opening scope.')
    rows=list(db.scalars(scoped(GitHubSourceVersion,project).join(GitHubObservation,GitHubObservation.source_id==GitHubSourceVersion.id)
        .where(GitHubObservation.import_id==job.id).order_by(GitHubSourceVersion.captured_at,GitHubSourceVersion.id).limit(MAX_SOURCES_PER_IMPORT+1)))
    if len(rows)>MAX_SOURCES_PER_IMPORT:raise ApiError(409,'grouping_limit','This capture is too large for one grouping operation. Import a smaller historical scope.')
    newest={};duplicate_version_count=0
    for source in rows:
        if digest(source.document)!=source.content_hash:raise ApiError(409,'source_integrity_error','An imported source fingerprint does not reconcile.')
        key=entity_key(source)
        if key in newest:duplicate_version_count+=1
        newest[key]=source
    existing={r.entity_key for r in db.scalars(scoped(ReconstructionSourceClaim,project))}
    eligible=[s for key,s in newest.items() if key not in existing]
    from app.analysis.handoff import primary_link_guard as analysis_link_guard
    for source in eligible: analysis_link_guard(db,project,source)
    created=[];assignments=[]
    for selected in groups(eligible):
        doc=CandidateDocument(title=group_title(selected),category='code',
            summary='Review these related imported records and describe the useful historical outcome.',
            unresolved_questions=['Confirm the outcome, category, missing evidence and attribution before creating a work package.']).model_dump(mode='json')
        row=new_candidate(db,project,batch,actor,doc,{'kind':'captured_relationships_v1','import_id':str(job.id),
            'import_omissions':job.omissions,'observed_source_count':len(selected),
            'notice':'Structured relationships suggest a grouping, not accepted value. Current REST contents may postdate the historical interval.'})
        created.append(candidate_record(row))
        for source in selected:
            claim=ReconstructionSourceClaim(workspace_id=project.workspace_id,project_id=project.id,batch_id=batch.id,
                candidate_id=row.id,source_id=source.id,entity_key=entity_key(source))
            db.add(claim);assignments.append({'candidate_id':str(row.id),'source_id':str(source.id),'entity_key':claim.entity_key})
    result={'candidate_ids':[r['id'] for r in created],'group_count':len(created),'source_count':len(eligible),
        'already_claimed_count':len(newest)-len(eligible),'older_versions_omitted':duplicate_version_count,'import_omissions':job.omissions}
    emit(db,project,batch,actor,action,body,{'candidates':created,'source_assignments':assignments,'result':result})
    return result


def create_manual(db,project,batch,actor,body):
    prior=replay(db,project,batch,actor,'manual_candidate',body)
    if prior is not None:return prior
    mutable(batch,body)
    row=new_candidate(db,project,batch,actor,body.document.model_dump(mode='json'),{'kind':'manual','notice':'Contributor-supplied outcome; evidence must be attached and reviewed separately.'})
    result={'candidate_id':str(row.id)}
    emit(db,project,batch,actor,'manual_candidate',body,{'candidate':candidate_record(row),'result':result});return result


def edit_candidate(db,project,batch,actor,candidate_id,body):
    action='candidate_edited:'+str(candidate_id)
    prior=replay(db,project,batch,actor,action,body)
    if prior is not None:return prior
    mutable(batch,body);row=get_candidate(db,project,batch,candidate_id)
    if row.state!='draft':raise ApiError(409,'candidate_locked','Only draft candidates can be edited. Linked work uses its preserved package workflow.')
    row.document={**body.document.model_dump(mode='json'),'provenance':row.document['provenance']};row.version+=1
    result={'candidate_id':str(row.id)}
    emit(db,project,batch,actor,action,body,{'candidate':candidate_record(row),'result':result});return result


def disposition(db,project,batch,actor,candidate_id,body):
    action=body.disposition+':'+str(candidate_id);prior=replay(db,project,batch,actor,action,body)
    if prior is not None:return prior
    mutable(batch,body);row=get_candidate(db,project,batch,candidate_id)
    expected='draft' if body.disposition=='reject' else 'rejected'
    if row.package_id:
        package=db.get(WorkPackage,row.package_id)
        if body.disposition!='reject' or row.state!='linked' or not package or package.state!='cancelled' or db.get(BudgetAllocation,package.allocation_id).issued_atoms:
            raise ApiError(409,'candidate_locked','Linked work can only be rejected after cancellation without earned credit; it cannot be rebound.')
        expected='linked'
    if row.state!=expected:raise ApiError(409,'candidate_locked','This candidate cannot make the requested transition.')
    row.state='rejected' if body.disposition=='reject' else 'draft';row.version+=1
    result={'candidate_id':str(row.id)}
    emit(db,project,batch,actor,action,body,{'candidate':candidate_record(row),'result':result});return result


def regroup(db,project,batch,actor,body):
    prior=replay(db,project,batch,actor,'regrouped',body)
    if prior is not None:return prior
    mutable(batch,body);rows=[get_candidate(db,project,batch,x) for x in body.candidate_ids]
    if any(r.state!='draft' for r in rows):raise ApiError(409,'candidate_locked','Merge or split draft candidates before converting them to work packages.')
    available=[c for row in rows for c in claims(db,project,batch,row)]
    if body.split_source_ids:
        selected=set(body.split_source_ids)
        if not selected < {c.source_id for c in available}:raise ApiError(409,'invalid_split','Choose a nonempty proper subset of the candidate source IDs.')
        moving=[c for c in available if c.source_id in selected]
    else:moving=available
    first=rows[0];doc=CandidateDocument(title=body.title,category=first.document['category'],
        summary=first.document['summary'],unresolved_questions=['Review this changed grouping and resolve its attribution and evidence before promotion.']).model_dump(mode='json')
    new=new_candidate(db,project,batch,actor,doc,{'kind':'human_split' if body.split_source_ids else 'human_merge',
        'parent_candidate_ids':[str(r.id) for r in rows]})
    for c in moving:c.candidate_id=new.id
    for row in rows:
        row.version+=1
        if not body.split_source_ids:row.state='superseded'
        else:
            row.document={**row.document,'identity_resolutions':[],'unresolved_questions':['Review the remaining source grouping after this split.']}
    result={'candidate_id':str(new.id),'moved_source_ids':[str(c.source_id) for c in moving]}
    emit(db,project,batch,actor,'regrouped',body,{'candidates':[candidate_record(r) for r in [*rows,new]],'result':result});return result


def candidate_view(db,project,batch,row):
    source_rows=[];identities={};blockers=list(row.document['unresolved_questions'])
    for claim in claims(db,project,batch,row):
        source=db.get(GitHubSourceVersion,claim.source_id)
        if source is None or source.project_id!=project.id or digest(source.document)!=source.content_hash:
            raise ApiError(409,'source_integrity_error','Pinned reconstruction evidence is unavailable or inconsistent.')
        source_rows.append({'id':str(source.id),'entity_key':claim.entity_key,'repository_id':str(source.repository_id),
            'repository':source.document['repository'],'kind':source.kind,'remote_key':source.remote_key,
            'content_hash':source.content_hash,'captured_at':utc(source.captured_at).isoformat(),
            'omissions':source.document['omissions']})
        for identity in source.document['identities']:identities[identity['external_key']]=identity
    resolutions={r['external_key']:r for r in row.document['identity_resolutions']}
    identity_rows=[];people=active_people(db,project)
    for key,claim in sorted(identities.items()):
        mapping=db.scalar(scoped(GitHubIdentity,project).where(GitHubIdentity.external_key==key))
        identity_rows.append({**claim,'suggested_user_id':str(mapping.linked_user_id) if mapping and mapping.linked_user_id else None,
            'resolution':resolutions.get(key)})
        resolution=resolutions.get(key)
        if not resolution:blockers.append('Unresolved observed identity: '+key)
        elif resolution['disposition']=='participant' and resolution['user_id'] not in people:
            blockers.append('A resolved participant is not currently active in this project: '+key)
    if set(resolutions)-set(identities):blockers.append('Remove identity resolutions that do not belong to this source grouping.')
    if len(source_rows)>MAX_SOURCES_PER_PACKAGE:blockers.append('Split or reduce this grouping: a promoted package can attach at most 30 source records.')
    package=db.get(WorkPackage,row.package_id) if row.package_id else None
    base={**candidate_record(row),'allocation_id':str(package.allocation_id) if package else None,'sources':source_rows,'identities':identity_rows,'blockers':blockers}
    return {**base,'review_hash':digest({'batch_version':batch.version,'candidate':base})}


def primary_link_guard(db,project,source,package_id):
    from app.analysis.handoff import primary_link_guard as analysis_link_guard
    analysis_link_guard(db,project,source,package_id)
    claim=db.scalar(scoped(ReconstructionSourceClaim,project).where(ReconstructionSourceClaim.entity_key==entity_key(source)))
    if claim:
        candidate=db.get(ReconstructionCandidate,claim.candidate_id)
        if candidate.package_id!=package_id:
            raise ApiError(409,'source_claimed_for_reconstruction','This source entity is assigned to another historical outcome. Resolve the candidate before attaching it elsewhere.')


def reserved_milestone_guard(db,project,milestone_id,candidate_id=None):
    batch=db.scalar(scoped(ReconstructionBatch,project).where(ReconstructionBatch.milestone_id==milestone_id))
    if batch:
        if not candidate_id or batch.state!='approved':
            raise ApiError(409,'historical_milestone_reserved','Create work in this dedicated milestone through an approved reconstruction candidate.')
        candidate=get_candidate(db,project,batch,candidate_id)
        if candidate.state!='draft':raise ApiError(409,'candidate_locked','This candidate already has a disposition.')


def promote(db,project,batch,actor,body,storage,quota_bytes):
    prior=replay(db,project,batch,actor,'promoted',body)
    if prior is not None:return prior
    mutable(batch,body,approved=True);require_ready_policy(db,project,batch.policy_id)
    row=get_candidate(db,project,batch,body.candidate_id);view=candidate_view(db,project,batch,row)
    if row.state!='draft':raise ApiError(409,'candidate_locked','This candidate has already been converted or disposed.')
    if body.reviewed_hash!=view['review_hash']:raise ApiError(409,'review_changed','The candidate or identity review changed. Inspect it again.')
    if view['blockers']:raise ApiError(409,'unresolved_reconstruction','Resolve the candidate questions, attribution and size blockers first.')
    allocation=db.scalar(scoped(BudgetAllocation,project).where(BudgetAllocation.id==body.allocation_id,
        BudgetAllocation.milestone_id==batch.milestone_id))
    if not allocation:raise not_found()
    if allocation.category!=row.document['category']:raise ApiError(409,'category_mismatch','The reviewed candidate category must match its approved allocation.')
    normalized=normalize_scope(body.scope,allocation.atoms,active_people(db,project))
    if scope_blockers(normalized,set(active_people(db,project))):raise ApiError(409,'incomplete_scope','Fully budget and attribute the proposed deliverables before converting historical work.')
    resolved={r['user_id'] for r in row.document['identity_resolutions'] if r['disposition']=='participant'}
    if not resolved <= {str(x) for x in body.scope.intended_contributor_ids}:
        raise ApiError(409,'unresolved_attribution','Every identity resolved as a participant must be included in the proposed scope.')
    # Prevent a root entity already used by a different package from being
    # silently credited again through another imported version/reconnection.
    keys={s['entity_key'] for s in view['sources']}
    for source,link in db.execute(select(GitHubSourceVersion,GitHubEvidenceLink).join(GitHubEvidenceLink,
        GitHubEvidenceLink.source_id==GitHubSourceVersion.id).where(GitHubEvidenceLink.project_id==project.id,
        GitHubEvidenceLink.workspace_id==project.workspace_id)):
        if entity_key(source) in keys:
            raise ApiError(409,'source_already_attached','A selected source entity already belongs to another work package. Resolve possible duplicate credit explicitly.')
    package=create_package(db,project,actor,'admin',PackageCreate(milestone_id=batch.milestone_id,
        allocation_id=body.allocation_id,expected_allocation_version=body.expected_allocation_version,
        scope=body.scope,reason=body.reason),reconstruction_candidate_id=row.id)
    row.package_id=package.id;row.state='linked';row.version+=1;db.flush()
    from app.integrations.github.service import link_source
    from app.integrations.github.schemas import LinkSource
    from app.evidence.schemas import EvidenceMetadata
    category=row.document['category'] if row.document['category'] not in {'community','production'} else 'other'
    evidence_links=[]
    for s in view['sources']:
        source=db.get(GitHubSourceVersion,UUID(s['id']))
        metadata=EvidenceMetadata(title=(source.kind+' '+source.remote_key)[:120],
            description='Pinned historical reconstruction source; inspect the full captured record and its limitations.',
            claimed_authors='See the explicit candidate identity dispositions; imported authorship remains a claim.',
            provenance='Captured GitHub REST source, attached during a retrospective review. Its capture date is not an assertion of when the work occurred.',
            occurred_on=utc(source.captured_at).date(),category=category,visibility='project')
        linked=link_source(db,project,actor,'admin',source.id,LinkSource(package_id=package.id,
            expected_package_version=package.version,request_id=uuid5(NAMESPACE_URL,str(row.id)+':'+s['id']),
            reviewed_source_hash=source.content_hash,metadata=metadata,reason=body.reason,sharing_confirmed=True),storage,quota_bytes)
        evidence_links.append(str(linked['evidence_id']))
    result={'candidate_id':str(row.id),'package_id':str(package.id),'evidence_ids':evidence_links}
    emit(db,project,batch,actor,'promoted',body,{'candidate':candidate_record(row),'scope':body.scope.model_dump(mode='json'),
        'source_fingerprints':view['sources'],'result':result})
    return result


def add_missing_claim(db,project,batch,actor,body):
    replayed=replay(db,project,batch,actor,'missing_claim',body)
    if replayed is not None:return replayed
    prior=db.scalar(scoped(ReconstructionMissingClaim,project).where(
        ReconstructionMissingClaim.created_by==actor.id,ReconstructionMissingClaim.request_id==body.request_id))
    fingerprint=digest({'batch_id':str(batch.id),'input':body.model_dump(mode='json')})
    if prior:
        if prior.request_hash!=fingerprint:raise ApiError(409,'idempotency_conflict','This missing-work request was already used.')
        return {'claim_id':str(prior.id)}
    if batch.state=='frozen':raise ApiError(409,'opening_balance_frozen','This snapshot is frozen. Report a concern through the relevant award dispute or a new historical batch.')
    if db.scalar(select(func.count()).select_from(ReconstructionMissingClaim).where(ReconstructionMissingClaim.batch_id==batch.id))>=200:
        raise ApiError(409,'missing_claim_limit','This pilot supports 200 missing-work claims per batch.')
    row=ReconstructionMissingClaim(id=uuid4(),workspace_id=project.workspace_id,project_id=project.id,batch_id=batch.id,
        created_by=actor.id,request_id=body.request_id,request_hash=fingerprint,state='open',document=body.model_dump(mode='json',exclude={'request_id'}))
    db.add(row);db.flush();result={'claim_id':str(row.id)}
    emit(db,project,batch,actor,'missing_claim',body,{'claim_id':str(row.id),'document':row.document,'result':result});return result


def resolve_missing(db,project,batch,actor,body):
    prior=replay(db,project,batch,actor,'missing_resolved',body)
    if prior is not None:return prior
    mutable(batch,body)
    row=db.scalar(scoped(ReconstructionMissingClaim,project).where(ReconstructionMissingClaim.batch_id==batch.id,
        ReconstructionMissingClaim.id==body.claim_id))
    if not row:raise not_found()
    previous={'state':row.state,'candidate_id':str(row.candidate_id) if row.candidate_id else None,'reason':row.resolution_reason}
    if body.candidate_id:
        candidate=get_candidate(db,project,batch,body.candidate_id)
        if candidate.state not in {'draft','linked'}:raise ApiError(409,'invalid_claim_target','Link the claim to a current candidate, not a rejected or superseded grouping.')
    row.state=body.disposition;row.candidate_id=body.candidate_id;row.resolution_reason=body.reason
    result={'claim_id':str(row.id)}
    emit(db,project,batch,actor,'missing_resolved',body,{'claim_id':str(row.id),'previous':previous,'state':row.state,
        'candidate_id':str(row.candidate_id) if row.candidate_id else None,'result':result});return result


def share_comparison(baseline_credit,current_credit,batch_awards):
    """Expose exact numerators/denominators; never equate a draft comparison with pay."""
    before=baseline_credit['pools'] if baseline_credit else {}
    after=current_credit['pools'];batch_pools={}
    for award in batch_awards:
        pool=batch_pools.setdefault(award['pool_key'],{'denominator_atoms':0,'people':{}})
        pool['denominator_atoms']+=award['budget_atoms']
        for entry in award['attributions']:
            person=pool['people'].setdefault(entry['user_id'],{'atoms':0,'display_name':entry['display_name']})
            person['atoms']+=entry['atoms']
    result=[]
    for key in sorted(set(before)|set(after)|set(batch_pools)):
        old=before.get(key,{'denominator_atoms':0,'people':[]});new=after.get(key,{'denominator_atoms':0,'people':[]})
        batch=batch_pools.get(key,{'denominator_atoms':0,'people':{}})
        a={p['user_id']:p for p in old['people']};b={p['user_id']:p for p in new['people']};people=[]
        for uid in sorted(set(a)|set(b)|set(batch['people'])):
            prior=a.get(uid,{});current=b.get(uid,{});delta=batch['people'].get(uid,{})
            people.append({'user_id':uid,'display_name':current.get('display_name',prior.get('display_name',delta.get('display_name',uid))),
                'baseline_atoms':prior.get('atoms',0),'current_atoms':current.get('atoms',0),'batch_atoms':delta.get('atoms',0),
                'baseline_share':{'numerator':prior.get('atoms',0),'denominator':old['denominator_atoms']},
                'current_share':{'numerator':current.get('atoms',0),'denominator':new['denominator_atoms']}})
        result.append({'pool_key':key,'baseline_denominator_atoms':old['denominator_atoms'],
            'current_denominator_atoms':new['denominator_atoms'],'batch_denominator_atoms':batch['denominator_atoms'],
            'people':sorted(people,key=lambda p:(p['display_name'].casefold(),p['user_id']))})
    return result


def opening_preview(db,project,batch,actor_id):
    baseline_event=db.scalar(select(ReconstructionEvent).where(ReconstructionEvent.batch_id==batch.id,
        ReconstructionEvent.action=='scope_approved'))
    baseline=baseline_event.record['details']['baseline'] if baseline_event else None
    context=review_context(db,project,batch,actor_id);blockers=[]
    if batch.state!='approved':blockers.append('The historical scope must be approved and not already frozen.')
    if not context['policy_ready']:blockers.append('The pinned policy approval or required acknowledgements are incomplete.')
    candidates=candidate_rows(db,project,batch);linked=[];dispositions=[]
    for row in candidates:
        dispositions.append({'id':str(row.id),'version':row.version,'state':row.state,'package_id':str(row.package_id) if row.package_id else None})
        if row.state=='draft':blockers.append('An undecided historical candidate remains: '+str(row.id))
        if row.state=='linked':
            package=db.get(WorkPackage,row.package_id)
            if package is None or package.state!='completed':blockers.append('A linked work package is not fully accepted: '+str(row.package_id))
            linked.append(str(row.package_id))
    if not linked:blockers.append('At least one independently accepted historical package is required.')
    pending_claims=list(db.scalars(scoped(ReconstructionMissingClaim,project).where(ReconstructionMissingClaim.batch_id==batch.id).order_by(ReconstructionMissingClaim.id)))
    for claim in pending_claims:
        if claim.state=='open':blockers.append('A missing-work claim is unresolved: '+str(claim.id))
        if claim.state=='included':
            target=get_candidate(db,project,batch,claim.candidate_id)
            if target.state!='linked':blockers.append('An included claim does not lead to an accepted package: '+str(claim.id))
    batch_awards=[a for a in context['credit']['awards'] if a['package_id'] in linked]
    affected_pools={a['pool_key'] for a in batch_awards}
    disputes=open_disputes(db,project,policy_id=batch.policy_id)
    for case in disputes:
        award=db.get(CreditAward,case.award_id)
        if award.pool_key in affected_pools:blockers.append('An unresolved dispute affects this policy and pool: '+str(case.id))
    # Also include unlinked planned allocations: they cannot quietly disappear.
    linked_allocations={str(db.get(WorkPackage,UUID(pid)).allocation_id) for pid in linked}
    for allocation in context['milestone']['allocations']:
        if allocation['status']=='active' and allocation['atoms'] and allocation['id'] not in linked_allocations:
            blockers.append('An active milestone allocation has not become accepted historical work: '+allocation['id'])
    record={'schema':'opening_balance_v1','batch_id':str(batch.id),'version':batch.version,'historical_definition':batch.definition,
        'baseline_at_scope_approval':baseline,'current_context':context,'candidates':dispositions,
        'missing_claims':[{'id':str(c.id),'state':c.state,'candidate_id':str(c.candidate_id) if c.candidate_id else None} for c in pending_claims],
        'batch_awards':batch_awards,'batch_issued_atoms':sum(a['budget_atoms'] for a in batch_awards),
        'share_comparison':share_comparison(baseline['credit'] if baseline else None,context['credit'],batch_awards),
        'blockers':blockers,'notice':('This archives current recognized credit after ordinary per-deliverable finalizations. '
            'Awards took effect when finalized; this is not a bulk credit issuance, a financial close, or a permanent release-share freeze. '
            'The baseline-to-current comparison also includes separately identified work accepted outside this batch.')}
    return {'record':record,'review_hash':digest(record)}


def freeze(db,project,batch,actor,body):
    prior=replay(db,project,batch,actor,'frozen',body)
    if prior is not None:return prior
    mutable(batch,body,approved=True);preview=opening_preview(db,project,batch,actor.id)
    if preview['review_hash']!=body.reviewed_hash:raise ApiError(409,'opening_preview_stale','The opening balance changed. Inspect a new preview before freezing.')
    if preview['record']['blockers']:raise ApiError(409,'opening_balance_blocked','Resolve missing work, unaccepted allocations, policy requirements and affected disputes first.')
    row=OpeningBalanceSnapshot(id=uuid4(),workspace_id=project.workspace_id,project_id=project.id,batch_id=batch.id,
        created_by=actor.id,record=preview['record'],record_hash=preview['review_hash'])
    db.add(row);batch.state='frozen';result={'snapshot_id':str(row.id)}
    emit(db,project,batch,actor,'frozen',body,{'snapshot_id':str(row.id),'snapshot_hash':row.record_hash,'result':result});return result


def batch_detail(db,project,batch,actor_id,role):
    private=role in {'admin','reviewer'}
    qs=scoped(ReconstructionMissingClaim,project).where(ReconstructionMissingClaim.batch_id==batch.id)
    if not private:qs=qs.where(ReconstructionMissingClaim.created_by==actor_id)
    missing=[{'id':str(x.id),'created_by':str(x.created_by),'document':x.document,'state':x.state,
        'candidate_id':str(x.candidate_id) if private and x.candidate_id else None,'resolution_reason':x.resolution_reason}
        for x in db.scalars(qs.order_by(ReconstructionMissingClaim.created_at,ReconstructionMissingClaim.id))]
    value={**definition_view(batch),'my_user_id':str(actor_id),'can_submit_claim':role!='viewer','can_manage':role=='admin','can_inspect':private,'my_claims_or_review_queue':missing}
    if private:
        context=review_context(db,project,batch,actor_id)
        candidates=[candidate_view(db,project,batch,c) for c in candidate_rows(db,project,batch)]
        value.update(candidates=candidates,scope_review_hash=digest(context),scope_context=context,
            participants=sorted(active_people(db,project).values(),key=lambda p:p['display_name'].casefold()),
            allocations=[a for a in context['milestone']['allocations'] if a['status']=='active'])
        frozen=db.scalar(select(OpeningBalanceSnapshot).where(OpeningBalanceSnapshot.batch_id==batch.id))
        if frozen:
            if digest(frozen.record)!=frozen.record_hash:raise ApiError(409,'snapshot_integrity_error','The preserved opening balance fingerprint does not reconcile.')
            value['frozen_snapshot']={'id':str(frozen.id),'record':frozen.record,'record_hash':frozen.record_hash,
                'created_at':utc(frozen.created_at).isoformat()}
    return value
