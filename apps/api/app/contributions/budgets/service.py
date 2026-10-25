from uuid import UUID, uuid4
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.auth.models import User
from app.core.errors import ApiError
from app.projects.models import Project
from app.projects.authorization import not_found
from app.policies.schemas import UNIT_SCALE
from app.policies.service import digest, require_ready_policy, policy_view
from app.security.audit import audit
from app.contributions.budgets.models import Milestone, BudgetAllocation, BudgetAmendment, BudgetDecision
from app.contributions.budgets.schemas import MilestoneCreate, AmendmentCreate, AmendmentDecision
from app.contributions.budgets.calculation import preview_change, totals_view, validate_snapshot

MAX_MILESTONES = 200
MAX_AMENDMENTS = 500


def get_milestone(db: Session, project: Project, milestone_id: UUID, *, lock: bool = False) -> Milestone:
    query = select(Milestone).where(Milestone.id == milestone_id,
        Milestone.workspace_id == project.workspace_id, Milestone.project_id == project.id)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    item = db.scalar(query)
    if item is None:
        raise not_found()
    return item


def allocation_rows(db: Session, milestone: Milestone) -> list[BudgetAllocation]:
    return list(db.scalars(select(BudgetAllocation).where(BudgetAllocation.workspace_id == milestone.workspace_id,
        BudgetAllocation.project_id == milestone.project_id, BudgetAllocation.milestone_id == milestone.id)
        .order_by(BudgetAllocation.id).execution_options(populate_existing=True)))


def snapshot(db: Session, milestone: Milestone) -> dict:
    return {'milestone_id': str(milestone.id), 'policy_id': str(milestone.policy_id),
        'version': milestone.version, 'status': milestone.status, 'total_atoms': milestone.total_atoms,
        'reserve_floor_atoms': milestone.reserve_floor_atoms, 'allocated_atoms': milestone.allocated_atoms,
        'issued_atoms': milestone.issued_atoms,
        'allocations': [{'id': str(r.id), 'title': r.title, 'category': r.category, 'pool_key': r.pool_key,
            'atoms': r.atoms, 'issued_atoms': r.issued_atoms, 'status': r.status, 'version': r.version}
            for r in allocation_rows(db, milestone)]}


def milestone_view(db: Session, item: Milestone) -> dict:
    state = snapshot(db, item)
    validate_snapshot(state)
    return {'id': item.id, 'name': item.name, 'description': item.description, 'policy_id': item.policy_id,
        'status': item.status, 'version': item.version, 'created_by': item.created_by, 'created_at': item.created_at,
        'unit_scale': UNIT_SCALE, **totals_view(state),
        'notice': 'Planned units are not earned units. No person owns the unissued reserve.'}


def amendment_view(db: Session, milestone: Milestone, item: BudgetAmendment) -> dict:
    decision = db.get(BudgetDecision, item.id)
    return {'id': item.id, 'expected_version': item.expected_version, 'proposed_by': item.proposed_by,
        'reason': item.reason, 'created_at': item.created_at, 'change': item.change,
        'preview': item.preview, 'preview_hash': item.preview_hash,
        'state': ('approved' if decision and decision.decision == 'approve' else 'rejected' if decision else
                  'stale' if item.expected_version != milestone.version else 'pending'),
        'decision': None if not decision else {'decision': decision.decision, 'decided_by': decision.decided_by,
            'reason': decision.reason, 'resulting_version': decision.resulting_version, 'created_at': decision.created_at}}


def milestone_detail(db: Session, project: Project, item: Milestone, actor_id: UUID, *, history_offset: int = 0) -> dict:
    from app.policies.service import get_policy
    amendments = db.scalars(select(BudgetAmendment).where(BudgetAmendment.workspace_id == project.workspace_id,
        BudgetAmendment.project_id == project.id, BudgetAmendment.milestone_id == item.id)
        .order_by(BudgetAmendment.created_at.desc(), BudgetAmendment.id).offset(history_offset).limit(21)).all()
    return {**milestone_view(db, item), 'allocations': snapshot(db, item)['allocations'],
        'amendments': [amendment_view(db, item, row) for row in amendments[:20]],
        'history_offset': history_offset, 'next_history_offset': history_offset + 20 if len(amendments) > 20 else None,
        'policy': policy_view(db, project, get_policy(db, project, item.policy_id), actor_id)}


def create_milestone(db: Session, project: Project, actor: User, body: MilestoneCreate) -> Milestone:
    require_ready_policy(db, project, body.policy_id, for_new_milestone=True)
    if db.scalar(select(func.count()).select_from(Milestone).where(Milestone.project_id == project.id)) >= MAX_MILESTONES:
        raise ApiError(409, 'milestone_limit', 'This local pilot supports 200 milestones per project.')
    item = Milestone(id=uuid4(), workspace_id=project.workspace_id, project_id=project.id,
        policy_id=body.policy_id, name=body.name, description=body.description, created_by=actor.id)
    db.add(item); db.flush()
    audit(db, 'milestone.created', actor_id=actor.id, workspace_id=project.workspace_id,
        project_id=project.id, subject_id=item.id, reason=body.reason, details={'policy_id': str(item.policy_id)})
    propose_amendment(db, project, actor, item, AmendmentCreate(expected_version=1,
        change={'kind': 'initial_budget', 'total_atoms': body.total_atoms, 'reserve_floor_atoms': body.reserve_floor_atoms},
        reason=body.reason))
    return item


def prepare_preview(db: Session, project: Project, item: Milestone, body: AmendmentCreate, *, cancelling_package_id: UUID | None = None) -> dict:
    if item.version != body.expected_version:
        raise ApiError(409, 'stale_version', 'The milestone changed. Refresh and review a new preview.')
    policy = require_ready_policy(db, project, item.policy_id, for_new_milestone=item.status == 'draft')
    change = body.change.model_dump(mode='json')
    from app.contributions.work_packages.budget_links import guard_change
    guard_change(db, project, item, change, cancelling_package_id=cancelling_package_id)
    preview = preview_change(snapshot(db, item), change, policy.rules)
    return {'preview': preview, 'preview_hash': digest({'change': change, 'preview': preview})}


def propose_amendment(db: Session, project: Project, actor: User, item: Milestone, body: AmendmentCreate, *, cancelling_package_id: UUID | None = None) -> BudgetAmendment:
    result = prepare_preview(db, project, item, body, cancelling_package_id=cancelling_package_id)
    if db.scalar(select(func.count()).select_from(BudgetAmendment).where(BudgetAmendment.milestone_id == item.id)) >= MAX_AMENDMENTS:
        raise ApiError(409, 'amendment_limit', 'This local pilot supports 500 proposals per milestone.')
    row = BudgetAmendment(id=uuid4(), workspace_id=project.workspace_id, project_id=project.id,
        milestone_id=item.id, proposed_by=actor.id, expected_version=item.version,
        change=body.change.model_dump(mode='json'), preview=result['preview'], preview_hash=result['preview_hash'], reason=body.reason)
    db.add(row); db.flush()
    audit(db, 'budget.amendment_proposed', actor_id=actor.id, workspace_id=project.workspace_id,
        project_id=project.id, subject_id=row.id, reason=body.reason,
        details={'milestone_id': str(item.id), 'expected_version': item.version, 'preview_hash': row.preview_hash,
                 'kind': row.change['kind']})
    return row


def decide_amendment(db: Session, project: Project, actor: User, milestone: Milestone,
                     amendment_id: UUID, body: AmendmentDecision, *, cancelling_package_id: UUID | None = None) -> BudgetAmendment:
    row = db.scalar(select(BudgetAmendment).where(BudgetAmendment.id == amendment_id,
        BudgetAmendment.workspace_id == project.workspace_id, BudgetAmendment.project_id == project.id,
        BudgetAmendment.milestone_id == milestone.id))
    if row is None:
        raise not_found()
    if db.get(BudgetDecision, row.id):
        raise ApiError(409, 'already_decided', 'This proposal already has a final decision. Refresh its history.')
    if body.reviewed_preview_hash != row.preview_hash:
        raise ApiError(409, 'review_hash_mismatch', 'Review the stored before-and-after preview before deciding.')
    if body.expected_version != milestone.version:
        raise ApiError(409, 'stale_version', 'The milestone changed. Refresh its current revision.')
    if body.decision == 'approve':
        fresh = prepare_preview(db, project, milestone, AmendmentCreate(expected_version=row.expected_version,
            change=row.change, reason=row.reason), cancelling_package_id=cancelling_package_id)
        if fresh['preview_hash'] != row.preview_hash:
            raise ApiError(409, 'preview_changed', 'The current budget no longer matches this preview. Submit a new proposal.')
        after = fresh['preview']['after']
        # This is the only phase-3 path changing approved planning amounts.
        # No participant balance, contribution event or financial row exists here.
        for key in ('status', 'version', 'total_atoms', 'reserve_floor_atoms', 'allocated_atoms'):
            setattr(milestone, key, after[key])
        kind = row.change['kind']
        if kind == 'allocate':
            db.add(BudgetAllocation(id=row.id, workspace_id=project.workspace_id, project_id=project.id,
                milestone_id=milestone.id, title=row.change['title'], category=row.change['category'],
                pool_key=row.change['pool_key'], atoms=row.change['atoms']))
        elif kind in {'resize_allocation', 'cancel_allocation'}:
            allocation_id = row.change['allocation_id']
            target = next(r for r in allocation_rows(db, milestone) if str(r.id) == allocation_id)
            new = next(r for r in after['allocations'] if r['id'] == allocation_id)
            target.atoms, target.status, target.version = new['atoms'], new['status'], new['version']
        db.flush()
        validate_snapshot(snapshot(db, milestone))
        if kind == 'resize_allocation':
            from app.contributions.work_packages.budget_links import after_resize
            after_resize(db, project, actor, UUID(row.change['allocation_id']), body.reason)
    # Rejecting a stale proposal is allowed after refreshing the current version;
    # it changes history only, never the approved budget.
    db.add(BudgetDecision(amendment_id=row.id, workspace_id=project.workspace_id, project_id=project.id,
        milestone_id=milestone.id, decided_by=actor.id, decision=body.decision,
        reviewed_preview_hash=row.preview_hash, reason=body.reason, resulting_version=milestone.version))
    audit(db, 'budget.amendment_' + ('approved' if body.decision == 'approve' else 'rejected'),
        actor_id=actor.id, workspace_id=project.workspace_id, project_id=project.id, subject_id=row.id,
        reason=body.reason, details={'milestone_id': str(milestone.id), 'resulting_version': milestone.version,
            'preview_hash': row.preview_hash, 'kind': row.change['kind']})
    db.flush()
    return row
