import hashlib
import json
from uuid import UUID, uuid4
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.auth.models import User
from app.core.errors import ApiError
from app.projects.authorization import not_found
from app.projects.models import Project, ProjectMembership, WorkspaceMembership
from app.policies.models import PolicyVersion, PolicyApproval, PolicyAcknowledgement, PolicyParticipant
from app.policies.schemas import PolicyCreate, PolicyApprove, PolicyAcknowledge
from app.security.audit import audit
from app.security.tokens import now, utc

MAX_POLICY_VERSIONS = 200


def digest(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()


def get_policy(db: Session, project: Project, policy_id: UUID) -> PolicyVersion:
    item = db.scalar(select(PolicyVersion).where(PolicyVersion.id == policy_id,
        PolicyVersion.workspace_id == project.workspace_id, PolicyVersion.project_id == project.id))
    if item is None:
        raise not_found()
    return item


def latest_policy(db: Session, project: Project) -> PolicyVersion | None:
    return db.scalar(select(PolicyVersion).where(PolicyVersion.workspace_id == project.workspace_id,
        PolicyVersion.project_id == project.id).order_by(PolicyVersion.version.desc()).limit(1))


def current_candidate(db: Session, project: Project) -> UUID | None:
    # The latest approved version whose effective instant has arrived is the
    # candidate. Missing acknowledgements do not silently fall back to old rules.
    return db.scalar(select(PolicyVersion.id).join(PolicyApproval, PolicyApproval.policy_id == PolicyVersion.id)
        .where(PolicyVersion.workspace_id == project.workspace_id, PolicyVersion.project_id == project.id,
               PolicyApproval.effective_at <= now()).order_by(PolicyVersion.version.desc()).limit(1))


def current_participants(db: Session, project: Project) -> dict[UUID, str]:
    """All currently active non-viewer effective project participants, not a hand-picked signer list."""
    rows = db.execute(select(WorkspaceMembership, User).join(User)
        .where(WorkspaceMembership.workspace_id == project.workspace_id,
               WorkspaceMembership.status == 'active', User.is_active.is_(True)))
    grants = {p.user_id: p for p in db.scalars(select(ProjectMembership).where(
        ProjectMembership.workspace_id == project.workspace_id, ProjectMembership.project_id == project.id,
        ProjectMembership.status == 'active'))}
    result = {}
    for member, _ in rows:
        if member.role in {'owner', 'admin'}:
            result[member.user_id] = 'admin'
        elif member.user_id in grants and grants[member.user_id].role != 'viewer':
            result[member.user_id] = grants[member.user_id].role
    return result


def acknowledgement_state(db: Session, project: Project, policy: PolicyVersion) -> dict:
    snapshots = {row.user_id: row.role_at_creation for row in db.scalars(select(PolicyParticipant)
        .where(PolicyParticipant.policy_id == policy.id))}
    current = current_participants(db, project)
    required = set(snapshots) | set(current)
    acks = {row.user_id: row for row in db.scalars(select(PolicyAcknowledgement).where(
        PolicyAcknowledgement.policy_id == policy.id))}
    users = {u.id: u for u in db.scalars(select(User).where(User.id.in_(required)))} if required else {}
    members = []
    for user_id in sorted(required, key=str):
        user = users[user_id]
        ack = acks.get(user_id)
        members.append({'user_id': user_id, 'display_name': user.display_name,
            'role': current.get(user_id, snapshots.get(user_id)), 'required_at_creation': user_id in snapshots,
            'currently_required': user_id in current, 'acknowledged_at': ack.created_at if ack else None})
    missing = sorted(required - set(acks), key=str)
    return {'participants': members, 'missing_user_ids': missing, 'complete': not missing,
        'note': 'Suspending an unacknowledged participant does not remove their snapshot requirement. Create a reviewed successor version instead.'}


def policy_view(db: Session, project: Project, policy: PolicyVersion, actor_id: UUID) -> dict:
    approval = db.get(PolicyApproval, policy.id)
    ack_state = acknowledgement_state(db, project, policy)
    effective = bool(approval and utc(approval.effective_at) <= now())
    candidate = current_candidate(db, project)
    ready = effective and ack_state['complete']
    latest = latest_policy(db, project)
    return {'id': policy.id, 'version': policy.version, 'predecessor_id': policy.predecessor_id,
        'title': policy.title, 'rules': policy.rules, 'agreement_reference': policy.agreement_reference,
        'reason': policy.reason, 'content_hash': policy.content_hash, 'created_by': policy.created_by,
        'created_at': policy.created_at, 'is_latest_revision': policy.id == latest.id,
        'approval': None if approval is None else {'approved_by': approval.approved_by,
            'reason': approval.reason, 'created_at': approval.created_at, 'effective_at': approval.effective_at},
        'acknowledgements': ack_state,
        'my_acknowledgement': db.get(PolicyAcknowledgement, (policy.id, actor_id)) is not None,
        'state': ('draft' if not approval else 'scheduled' if not effective else
                  'awaiting_acknowledgements' if not ack_state['complete'] else
                  'effective' if candidate == policy.id else 'historical'),
        'is_current_candidate': candidate == policy.id, 'ready_for_pinned_work': ready,
        'usable_for_new_milestones': ready and candidate == policy.id,
        'notice': 'Software acknowledgement records review of this version. It does not issue credit, equity, or certify an agreement.'}


def create_policy(db: Session, project: Project, actor: User, body: PolicyCreate) -> PolicyVersion:
    # Caller holds the existing tenant lock, also used by membership changes.
    latest = latest_policy(db, project)
    version = latest.version if latest else 0
    if version != body.expected_latest_version:
        raise ApiError(409, 'stale_version', 'A newer policy revision exists. Refresh and review it before saving.')
    if version >= MAX_POLICY_VERSIONS:
        raise ApiError(409, 'policy_limit', 'This local pilot supports 200 policy versions per project.')
    if body.rules.currency != project.currency or body.rules.timezone != project.timezone:
        raise ApiError(422, 'policy_project_settings', 'New policy currency and timezone must match the current project settings.')
    participants = current_participants(db, project)
    rules = body.rules.model_dump(mode='json')
    payload = {'version': version + 1, 'predecessor_id': str(latest.id) if latest else None,
        'title': body.title, 'rules': rules, 'agreement_reference': body.agreement_reference,
        'participants': [{'user_id': str(k), 'role': participants[k]} for k in sorted(participants, key=str)]}
    policy = PolicyVersion(id=uuid4(), workspace_id=project.workspace_id, project_id=project.id,
        predecessor_id=latest.id if latest else None, version=version + 1, title=body.title,
        rules=rules, agreement_reference=body.agreement_reference, created_by=actor.id,
        reason=body.reason, content_hash=digest(payload))
    db.add(policy); db.flush()
    for user_id, role in participants.items():
        db.add(PolicyParticipant(policy_id=policy.id, user_id=user_id, workspace_id=project.workspace_id,
            project_id=project.id, role_at_creation=role))
    db.flush()
    audit(db, 'policy.revision_created', actor_id=actor.id, workspace_id=project.workspace_id,
        project_id=project.id, subject_id=policy.id, reason=body.reason,
        details={'version': policy.version, 'content_hash': policy.content_hash,
                 'required_participant_count': len(participants)})
    return policy


def approve_policy(db: Session, project: Project, actor: User, policy: PolicyVersion, body: PolicyApprove):
    if body.reviewed_content_hash != policy.content_hash:
        raise ApiError(409, 'review_hash_mismatch', 'Review the exact current policy content before approving.')
    if db.get(PolicyApproval, policy.id):
        raise ApiError(409, 'already_approved', 'This version is already approved. Its approval cannot be overwritten.')
    latest = latest_policy(db, project)
    if policy.id != latest.id or latest.version != body.expected_latest_version:
        raise ApiError(409, 'stale_version', 'Only the newest policy revision can receive a new approval.')
    # Membership changes before approval require a new, visible participant snapshot.
    snapshot = {p.user_id for p in db.scalars(select(PolicyParticipant).where(PolicyParticipant.policy_id == policy.id))}
    if snapshot != set(current_participants(db, project)):
        raise ApiError(409, 'participant_set_changed', 'Project participants changed. Create a successor revision before approval.')
    instant = now()
    effective_at = body.effective_at or instant
    if effective_at < instant:
        raise ApiError(422, 'retroactive_policy', 'An approval cannot be backdated. Choose immediate or a future offset-aware time.')
    previous = db.scalar(select(func.max(PolicyApproval.effective_at)).where(
        PolicyApproval.workspace_id == project.workspace_id, PolicyApproval.project_id == project.id))
    if previous and effective_at <= utc(previous):
        raise ApiError(409, 'effective_order', 'Successor policies must start after every previously approved effective time.')
    db.add(PolicyApproval(policy_id=policy.id, workspace_id=project.workspace_id, project_id=project.id,
        approved_by=actor.id, reviewed_content_hash=policy.content_hash, reason=body.reason, effective_at=effective_at))
    audit(db, 'policy.approved', actor_id=actor.id, workspace_id=project.workspace_id,
        project_id=project.id, subject_id=policy.id, reason=body.reason,
        details={'version': policy.version, 'content_hash': policy.content_hash, 'effective_at': effective_at.isoformat()})
    db.flush()


def acknowledge_policy(db: Session, project: Project, actor: User, policy: PolicyVersion, body: PolicyAcknowledge):
    if body.reviewed_content_hash != policy.content_hash:
        raise ApiError(409, 'review_hash_mismatch', 'Acknowledge only the exact policy version you reviewed.')
    if not db.get(PolicyApproval, policy.id):
        raise ApiError(409, 'policy_not_approved', 'Wait for administrative approval before acknowledging this version.')
    if db.get(PolicyAcknowledgement, (policy.id, actor.id)):
        return  # Safe replay of exactly this actor/version/hash; no duplicate audit event.
    db.add(PolicyAcknowledgement(policy_id=policy.id, user_id=actor.id, workspace_id=project.workspace_id,
        project_id=project.id, reviewed_content_hash=policy.content_hash))
    audit(db, 'policy.acknowledged', actor_id=actor.id, workspace_id=project.workspace_id,
        project_id=project.id, subject_id=policy.id, details={'version': policy.version, 'content_hash': policy.content_hash})
    db.flush()


def require_ready_policy(db: Session, project: Project, policy_id: UUID, *, for_new_milestone: bool = False) -> PolicyVersion:
    policy = get_policy(db, project, policy_id)
    approval = db.get(PolicyApproval, policy.id)
    if approval is None or utc(approval.effective_at) > now():
        raise ApiError(409, 'policy_not_effective', 'An approved, effective policy is required before committing a budget.')
    if not acknowledgement_state(db, project, policy)['complete']:
        raise ApiError(409, 'acknowledgements_required', 'Required participants must acknowledge this exact policy version first.')
    if for_new_milestone and current_candidate(db, project) != policy.id:
        raise ApiError(409, 'policy_superseded', 'New milestones must use the current effective policy, not a historical version.')
    return policy
