"""Work-package commands; callers hold workspace -> milestone -> package locks.

Administrative scope approval is planning approval, never acceptance of earned
credit. All state changes append events and all scope changes append revisions.
"""
from uuid import UUID, uuid4
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.auth.models import User
from app.core.errors import ApiError
from app.projects.authorization import not_found
from app.projects.models import Project
from app.policies.service import (current_participants, get_policy, require_ready_policy,
                                  policy_view, digest)
from app.contributions.budgets.models import BudgetAllocation, Milestone
from app.contributions.budgets.service import get_milestone
from app.contributions.work_packages.models import (WorkPackage, WorkPackageRevision,
    WorkPackageParticipant, WorkPackageEvent, WorkSubmission)
from app.contributions.work_packages.schemas import PackageCreate, ScopeEdit, PackageAction, ScopeInput
from app.contributions.work_packages.calculation import normalize_scope, scope_blockers
from app.security.audit import audit

MAX_PACKAGES = 200
MAX_REVISIONS = 500
MAX_EVENTS = 2000


def active_people(db: Session, project: Project) -> dict[str, dict]:
    roles = current_participants(db, project)
    users = db.scalars(select(User).where(User.id.in_(roles))) if roles else []
    return {str(u.id): {'user_id': str(u.id), 'display_name': u.display_name, 'role': roles[u.id]} for u in users}


def get_package(db: Session, project: Project, package_id: UUID, *, lock=False) -> WorkPackage:
    query = select(WorkPackage).where(WorkPackage.id == package_id,
        WorkPackage.workspace_id == project.workspace_id, WorkPackage.project_id == project.id)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    item = db.scalar(query)
    if item is None:
        raise not_found()
    return item


def lock_package(db: Session, project: Project, package_id: UUID) -> WorkPackage:
    found = get_package(db, project, package_id)
    get_milestone(db, project, found.milestone_id, lock=True)
    return get_package(db, project, package_id, lock=True)


def get_context(db: Session, project: Project, item: WorkPackage):
    milestone = get_milestone(db, project, item.milestone_id)
    allocation = db.scalar(select(BudgetAllocation).where(BudgetAllocation.id == item.allocation_id,
        BudgetAllocation.workspace_id == project.workspace_id, BudgetAllocation.project_id == project.id,
        BudgetAllocation.milestone_id == item.milestone_id).execution_options(populate_existing=True))
    revision = db.get(WorkPackageRevision, (item.id, item.scope_revision))
    if allocation is None or revision is None or milestone.policy_id != item.policy_id:
        raise ApiError(409, 'invalid_package_projection', 'Work-package references do not reconcile. Stop and inspect the stored records.')
    return milestone, allocation, revision


def append_revision(db: Session, project: Project, actor: User, item: WorkPackage,
                    allocation: BudgetAllocation, scope: ScopeInput, reason: str):
    if item.scope_revision > MAX_REVISIONS:
        raise ApiError(409, 'revision_limit', 'This pilot supports 500 scope revisions per package.')
    doc = normalize_scope(scope, allocation.atoms, active_people(db, project))
    policy = get_policy(db, project, item.policy_id)
    doc.update(milestone_id=str(item.milestone_id), allocation_id=str(item.allocation_id),
               policy_id=str(policy.id), policy_version=policy.version, policy_hash=policy.content_hash,
               category=allocation.category, pool_key=allocation.pool_key)
    row = WorkPackageRevision(package_id=item.id, number=item.scope_revision,
        workspace_id=project.workspace_id, project_id=project.id, allocation_version=allocation.version,
        document=doc, content_hash=digest(doc), created_by=actor.id, reason=reason)
    db.add(row); db.flush()
    for kind, ids in [('coordinator', [scope.coordinator_id]), ('intended', scope.intended_contributor_ids)]:
        for uid in ids:
            db.add(WorkPackageParticipant(package_id=item.id, scope_revision=row.number,
                user_id=uid, kind=kind, workspace_id=project.workspace_id, project_id=project.id))
    db.flush()
    return row


def record_event(db: Session, item: WorkPackage, actor: User, action: str, reason: str, details: dict | None = None):
    if item.version > MAX_EVENTS:
        raise ApiError(409, 'event_limit', 'This pilot supports 2,000 recorded changes per package.')
    payload = {'state': item.state, 'scope_revision': item.scope_revision, **(details or {})}
    db.add(WorkPackageEvent(id=uuid4(), workspace_id=item.workspace_id, project_id=item.project_id,
        package_id=item.id, scope_revision=item.scope_revision, package_version=item.version,
        actor_id=actor.id, action=action, reason=reason, details=payload))
    audit(db, 'work_package.' + action, actor_id=actor.id, workspace_id=item.workspace_id,
        project_id=item.project_id, subject_id=item.id, reason=reason,
        details={'version': item.version, 'scope_revision': item.scope_revision, 'state': item.state})
    db.flush()


def can_coordinate(item: WorkPackage, doc: dict, role: str, actor_id: UUID) -> bool:
    return role == 'admin' or (role != 'viewer' and doc['coordinator_id'] == str(actor_id))


def review_hash(item: WorkPackage, milestone: Milestone, allocation: BudgetAllocation,
                revision: WorkPackageRevision) -> str:
    return digest({'package_id': str(item.id), 'version': item.version, 'state': item.state,
        'scope_revision': revision.number, 'content_hash': revision.content_hash,
        'approved_revision': item.approved_revision, 'milestone_version': milestone.version,
        'allocation_id': str(allocation.id), 'allocation_version': allocation.version,
        'allocation_atoms': allocation.atoms, 'issued_atoms': allocation.issued_atoms})


def validate_review(item, milestone, allocation, revision, expected_version, reviewed_hash):
    if item.version != expected_version:
        raise ApiError(409, 'stale_version', 'The work package changed. Refresh before submitting another command.')
    if reviewed_hash != review_hash(item, milestone, allocation, revision):
        raise ApiError(409, 'review_hash_mismatch', 'The reviewed package or parent budget changed. Refresh and review again.')


def guard_unissued(allocation):
    if allocation.issued_atoms:
        raise ApiError(409, 'finalized_work_protected', 'This allocation has finalized credit. Phase 4 cannot amend or cancel it; use the later reviewed adjustment workflow.')


def revision_view(row: WorkPackageRevision) -> dict:
    return {'number': row.number, 'allocation_version': row.allocation_version, 'document': row.document,
        'content_hash': row.content_hash, 'created_by': row.created_by, 'reason': row.reason, 'created_at': row.created_at}


def package_summary(db: Session, project: Project, item: WorkPackage) -> dict:
    milestone, allocation, revision = get_context(db, project, item)
    doc = revision.document
    from app.contributions.reconstruction.models import ReconstructionCandidate
    historical = db.scalar(select(ReconstructionCandidate).where(ReconstructionCandidate.project_id == project.id, ReconstructionCandidate.package_id == item.id))
    return {'origin': 'retrospective' if historical else 'prospective',
        'reconstruction_batch_id': str(historical.batch_id) if historical else None, 'id': item.id, 'milestone_id': item.milestone_id, 'milestone_name': milestone.name,
        'allocation_id': allocation.id, 'policy_id': item.policy_id, 'state': item.state,
        'version': item.version, 'scope_revision': item.scope_revision, 'approved_revision': item.approved_revision,
        'title': doc['title'], 'category': doc['category'], 'pool_key': doc['pool_key'],
        'coordinator_id': doc['coordinator_id'], 'coordinator_name': doc['participant_labels'][doc['coordinator_id']],
        'budget_atoms': allocation.atoms, 'scope_budget_atoms': doc['budget_atoms'],
        'deliverable_atoms': doc['deliverable_atoms'], 'unplanned_atoms': doc['unplanned_atoms'],
        'issued_atoms': allocation.issued_atoms, 'created_at': item.created_at}


def package_detail(db: Session, project: Project, item: WorkPackage, actor_id: UUID, role: str, *, history_offset=0) -> dict:
    milestone, allocation, revision = get_context(db, project, item)
    doc = revision.document
    people = active_people(db, project)
    policy = policy_view(db, project, get_policy(db, project, item.policy_id), actor_id)
    blockers = scope_blockers(doc, set(people))
    if not policy['ready_for_pinned_work']:
        blockers.append('The pinned policy is not currently ready: check approval, effective time and required acknowledgements.')
    if item.state != 'cancelled' and (allocation.atoms != doc['budget_atoms'] or allocation.version != revision.allocation_version):
        blockers.append('The scope snapshot does not match its approved parent allocation. Stop and inspect the budget history.')
    if allocation.issued_atoms:
        blockers.append('Finalized credit is preserved. Use independent review for remaining deliverables and disputes for corrections; scope edits/cancellation remain blocked.')
    coordinating = can_coordinate(item, doc, role, actor_id)
    can_edit = coordinating and item.state in {'draft', 'budget_approved', 'in_progress', 'changes_requested'} and not allocation.issued_atoms
    actions = []
    if role == 'admin' and item.state == 'draft' and not blockers:
        actions.append('approve_scope')
    if coordinating and item.state == 'budget_approved' and not blockers:
        actions.append('start')
    if coordinating and item.state == 'in_progress' and not blockers:
        actions.append('submit')
    if item.state == 'submitted' and not allocation.issued_atoms:
        if role in {'admin', 'reviewer'}:
            actions.append('request_changes')
        if coordinating:
            actions.extend(['withdraw', 'refresh_submission'])
    if role == 'admin' and item.state in {'draft', 'budget_approved', 'in_progress', 'changes_requested'} and not allocation.issued_atoms:
        actions.append('cancel')
    from app.ledger.service import can_extend_partial_evidence
    if coordinating and can_extend_partial_evidence(db,item,allocation):
        actions.append('refresh_submission')
    events = db.scalars(select(WorkPackageEvent).where(WorkPackageEvent.package_id == item.id)
        .order_by(WorkPackageEvent.package_version.desc()).offset(history_offset).limit(21)).all()
    submissions = db.scalars(select(WorkSubmission).where(WorkSubmission.package_id == item.id)
        .order_by(WorkSubmission.package_version.desc()).limit(10)).all()
    return {**package_summary(db, project, item), 'revision': revision_view(revision),
        'allocation_version': allocation.version, 'review_hash': review_hash(item, milestone, allocation, revision),
        'blockers': blockers, 'can_edit': can_edit, 'allowed_actions': actions,
        'policy': {'id': policy['id'], 'version': policy['version'], 'title': policy['title'],
                   'state': policy['state'], 'ready': policy['ready_for_pinned_work']},
        'history': [{'id': e.id, 'version': e.package_version, 'scope_revision': e.scope_revision,
                     'actor_id': e.actor_id, 'action': e.action, 'reason': e.reason,
                     'details': e.details, 'created_at': e.created_at} for e in events[:20]],
        'history_offset': history_offset, 'next_history_offset': history_offset + 20 if len(events) > 20 else None,
        'recent_submissions': [{'id': s.id, 'scope_revision': s.scope_revision, 'package_version': s.package_version,
            'submitted_by': s.submitted_by, 'snapshot_hash': s.snapshot_hash, 'created_at': s.created_at} for s in submissions],
        'notice': 'Scope allocations are proposals. Issued units come only from finalized independent reviews. Submission captures scope and evidence, not automatic acceptance.'}


def create_package(db: Session, project: Project, actor: User, role: str, body: PackageCreate, *, reconstruction_candidate_id: UUID | None = None) -> WorkPackage:
    if role not in {'admin', 'contributor'}:
        raise ApiError(403, 'permission_denied', 'A project administrator or contributor can create a work package.')
    milestone = get_milestone(db, project, body.milestone_id, lock=True)
    from app.contributions.reconstruction.service import reserved_milestone_guard
    reserved_milestone_guard(db, project, milestone.id, reconstruction_candidate_id)
    require_ready_policy(db, project, milestone.policy_id)
    allocation = db.scalar(select(BudgetAllocation).where(BudgetAllocation.id == body.allocation_id,
        BudgetAllocation.workspace_id == project.workspace_id, BudgetAllocation.project_id == project.id,
        BudgetAllocation.milestone_id == milestone.id).with_for_update().execution_options(populate_existing=True))
    if allocation is None:
        raise not_found()
    if milestone.status != 'active' or allocation.status != 'active' or not allocation.atoms:
        raise ApiError(409, 'approved_allocation_required', 'Approve a positive planning allocation in an active milestone first.')
    if allocation.version != body.expected_allocation_version:
        raise ApiError(409, 'stale_allocation', 'The selected allocation changed. Refresh the available budgets.')
    guard_unissued(allocation)
    if db.scalar(select(WorkPackage.id).where(WorkPackage.allocation_id == allocation.id)):
        raise ApiError(409, 'allocation_already_linked', 'This allocation already belongs to a work package, including any archived package.')
    count = db.scalar(select(func.count()).select_from(WorkPackage).where(WorkPackage.project_id == project.id))
    if count >= MAX_PACKAGES:
        raise ApiError(409, 'package_limit', 'This local pilot supports 200 work packages per project.')
    item = WorkPackage(id=uuid4(), workspace_id=project.workspace_id, project_id=project.id,
        milestone_id=milestone.id, allocation_id=allocation.id, policy_id=milestone.policy_id,
        created_by=actor.id, state='draft', version=1, scope_revision=1)
    db.add(item); db.flush()
    append_revision(db, project, actor, item, allocation, body.scope, body.reason)
    record_event(db, item, actor, 'created', body.reason, {'allocation_id': str(allocation.id)})
    return item


def edit_scope(db: Session, project: Project, actor: User, role: str, item: WorkPackage, body: ScopeEdit):
    milestone, allocation, revision = get_context(db, project, item)
    validate_review(item, milestone, allocation, revision, body.expected_version, body.reviewed_hash)
    guard_unissued(allocation)
    if not can_coordinate(item, revision.document, role, actor.id):
        raise ApiError(403, 'permission_denied', 'Only a project administrator or the current coordinator can amend this scope.')
    if item.state not in {'draft', 'budget_approved', 'in_progress', 'changes_requested'}:
        raise ApiError(409, 'invalid_transition', 'Withdraw a submitted package before amending it. Cancelled or completed packages cannot be edited here.')
    previous = item.scope_revision
    item.approved_revision = None
    item.state = 'draft'
    item.scope_revision += 1
    item.version += 1
    append_revision(db, project, actor, item, allocation, body.scope, body.reason)
    record_event(db, item, actor, 'scope_amended', body.reason, {'previous_scope_revision': previous, 'fresh_approval_required': True})


def perform_action(db: Session, project: Project, actor: User, role: str, item: WorkPackage, body: PackageAction, object_storage=None):
    milestone, allocation, revision = get_context(db, project, item)
    validate_review(item, milestone, allocation, revision, body.expected_version, body.reviewed_hash)
    from app.ledger.service import can_extend_partial_evidence
    if body.action != 'refresh_submission' or not can_extend_partial_evidence(db,item,allocation):
        guard_unissued(allocation)
    coordinating = can_coordinate(item, revision.document, role, actor.id)
    admin_actions = {'approve_scope', 'cancel'}
    if (body.action in admin_actions and role != 'admin') or (body.action in {'start','submit','withdraw','refresh_submission'} and not coordinating) or (body.action == 'request_changes' and role not in {'admin','reviewer'}):
        raise ApiError(403, 'permission_denied', 'Your project role or coordinator assignment does not permit this action.')
    allowed_states = {'approve_scope': {'draft'}, 'start': {'budget_approved'}, 'submit': {'in_progress'},
        'request_changes': {'submitted'}, 'withdraw': {'submitted'}, 'refresh_submission': {'submitted'},
        'cancel': {'draft', 'budget_approved', 'in_progress', 'changes_requested'}}
    if item.state not in allowed_states[body.action]:
        raise ApiError(409, 'invalid_transition', 'This action is not valid from the current work-package state.')
    if body.action in {'approve_scope', 'start', 'submit', 'refresh_submission'}:
        require_ready_policy(db, project, item.policy_id)
        blockers = scope_blockers(revision.document, set(active_people(db, project)))
        if blockers:
            raise ApiError(409, 'scope_incomplete', ' '.join(blockers))
        if allocation.status != 'active' or revision.allocation_version != allocation.version or revision.document['budget_atoms'] != allocation.atoms:
            raise ApiError(409, 'scope_budget_changed', 'The scope does not match its current parent budget. Amend it before continuing.')
    previous_state = item.state
    details = {'from_state': previous_state, 'reviewed_hash': body.reviewed_hash, 'content_hash': revision.content_hash}
    if body.action == 'approve_scope':
        item.approved_revision = item.scope_revision
        item.state = 'budget_approved'
    elif body.action == 'start':
        item.state = 'in_progress'
    elif body.action in {'submit', 'refresh_submission'}:
        if item.approved_revision != item.scope_revision:
            raise ApiError(409, 'approval_required', 'This exact scope revision needs planning approval first.')
        from app.evidence.service import capture_snapshot
        evidence_snapshot = capture_snapshot(db, item, actor, object_storage, 'Evidence packet captured for a human readiness declaration.')
        item.state = 'submitted'
        payload = {'scope_revision': revision.number, 'scope_content_hash': revision.content_hash,
            'scope': revision.document, 'policy_id': str(item.policy_id), 'policy_hash': revision.document['policy_hash'],
            'allocation_id': str(allocation.id), 'allocation_version': allocation.version,
            'budget_atoms': allocation.atoms, 'package_version': item.version + 1,
            'submitted_by': str(actor.id), 'submission_note': body.reason,
            'evidence_snapshot_id': str(evidence_snapshot.id), 'evidence_snapshot_hash': evidence_snapshot.content_hash,
            'evidence_status': 'captured_unreviewed',
            'notice': 'Readiness declaration with an immutable evidence packet, including omissions. No independent acceptance, earned credit or money is created.'}
        submission = WorkSubmission(id=uuid4(), workspace_id=project.workspace_id, project_id=project.id,
            package_id=item.id, scope_revision=item.scope_revision, package_version=item.version + 1,
            submitted_by=actor.id, snapshot=payload, snapshot_hash=digest(payload))
        db.add(submission)
        details['submission_id'] = str(submission.id)
        details['snapshot_hash'] = submission.snapshot_hash
    elif body.action in {'request_changes', 'withdraw'}:
        item.state = 'changes_requested'
        item.approved_revision = None
        details['fresh_scope_revision_required'] = True
    elif body.action == 'cancel':
        # Explicit human confirmation above authorizes BOTH the cancellation and
        # its linked planning-budget decision in this single transaction.
        from app.contributions.budgets.schemas import AmendmentCreate, AmendmentDecision
        from app.contributions.budgets.service import propose_amendment, decide_amendment
        released = allocation.atoms
        proposal = propose_amendment(db, project, actor, milestone,
            AmendmentCreate(expected_version=milestone.version,
                change={'kind': 'cancel_allocation', 'allocation_id': allocation.id}, reason=body.reason),
            cancelling_package_id=item.id)
        decide_amendment(db, project, actor, milestone, proposal.id,
            AmendmentDecision(decision='approve', expected_version=milestone.version,
                reviewed_preview_hash=proposal.preview_hash, reason=body.reason), cancelling_package_id=item.id)
        item.state = 'cancelled'
        item.approved_revision = None
        details.update(released_atoms=released, budget_amendment_id=str(proposal.id))
    item.version += 1
    record_event(db, item, actor, {'approve_scope': 'scope_approved', 'start': 'started', 'submit': 'submitted',
        'request_changes': 'changes_requested', 'withdraw': 'withdrawn', 'cancel': 'cancelled', 'refresh_submission': 'evidence_resubmitted'}[body.action], body.reason, details)
