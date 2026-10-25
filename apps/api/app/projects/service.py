from datetime import timedelta
from uuid import UUID, uuid4
from sqlalchemy import select, update, func
from sqlalchemy.orm import Session
from app.auth.models import User
from app.auth.service import revoke_all
from app.core.errors import ApiError
from app.projects.authorization import workspace_access, project_access, not_found
from app.projects.models import Workspace, WorkspaceMembership, Project, ProjectMembership, Invitation
from app.projects.schemas import InvitationCreate, WorkspaceMemberUpdate
from app.security.audit import audit
from app.security.tokens import new_token, now, token_hash, utc, valid_token


def workspace_view(workspace: Workspace, role: str) -> dict:
    return {"id": workspace.id, "name": workspace.name, "role": role,
        "can_manage": role in {"owner", "admin"}}


def project_view(project: Project, role: str) -> dict:
    return {"id": project.id, "workspace_id": project.workspace_id, "name": project.name,
        "description": project.description, "timezone": project.timezone, "currency": project.currency,
        "version": project.version, "role": role, "can_manage": role == "admin"}


def create_workspace(db: Session, actor: User, name: str) -> Workspace:
    workspace = Workspace(id=uuid4(), name=name)
    db.add(workspace)
    db.flush()
    db.add(WorkspaceMembership(workspace_id=workspace.id, user_id=actor.id, role="owner"))
    db.flush()
    audit(db, "workspace.created", actor_id=actor.id, workspace_id=workspace.id)
    return workspace


def change_workspace_member(db: Session, actor: User, workspace_id: UUID, user_id: UUID,
                            body: WorkspaceMemberUpdate) -> WorkspaceMembership:
    _, manager = workspace_access(db, workspace_id, actor.id, manage=True, lock=True)
    member = db.get(WorkspaceMembership, (workspace_id, user_id), populate_existing=True)
    if member is None:
        raise not_found()
    if member.version != body.expected_version:
        raise ApiError(409, "stale_version", "Membership changed. Refresh and review the latest version.")
    if manager.role != "owner" and (member.role != "member" or body.role != "member"):
        raise ApiError(403, "owner_required", "Only a workspace owner can change administrative membership.")
    if member.role == "owner" and member.status == "active" and (body.role != "owner" or body.status != "active"):
        others = db.scalar(select(func.count()).select_from(WorkspaceMembership).join(User)
            .where(WorkspaceMembership.workspace_id == workspace_id, WorkspaceMembership.role == "owner",
                WorkspaceMembership.status == "active", WorkspaceMembership.user_id != user_id, User.is_active.is_(True)))
        if not others:
            raise ApiError(409, "last_owner", "Assign another active workspace owner before removing this owner's access.")
    before = {"role": member.role, "status": member.status}
    member.role, member.status = body.role, body.status
    member.version += 1
    if body.status == "suspended":
        # Reinstating a workspace does NOT silently reinstate old project grants.
        db.execute(update(ProjectMembership).where(ProjectMembership.workspace_id == workspace_id,
            ProjectMembership.user_id == user_id).values(status="suspended", version=ProjectMembership.version + 1))
        db.execute(update(Invitation).where(Invitation.workspace_id == workspace_id,
            Invitation.inviter_id == user_id, Invitation.status == "pending").values(status="revoked"))
        revoke_all(db, user_id)
    audit(db, "workspace.membership_changed", actor_id=actor.id, workspace_id=workspace_id,
        subject_id=user_id, reason=body.reason, details={"before": before,
            "after": {"role": member.role, "status": member.status}, "version": member.version})
    return member


def invitation_view(invitation: Invitation) -> dict:
    status = "expired" if invitation.status == "pending" and utc(invitation.expires_at) <= now() else invitation.status
    return {"id": invitation.id, "email": invitation.email, "workspace_role": invitation.workspace_role,
        "project_id": invitation.project_id, "project_role": invitation.project_role, "status": status,
        "expires_at": invitation.expires_at, "created_at": invitation.created_at}


def create_invitation(db: Session, actor: User, workspace_id: UUID, body: InvitationCreate) -> tuple[Invitation, str]:
    _, manager = workspace_access(db, workspace_id, actor.id, manage=True, lock=True)
    if body.workspace_role == "admin" and manager.role != "owner":
        raise ApiError(403, "owner_required", "Only a workspace owner can invite a workspace administrator.")
    if body.project_id:
        project_access(db, workspace_id, body.project_id, actor.id, manage=True)
    existing_user = db.scalar(select(User).where(User.email == body.email))
    if existing_user:
        existing_member = db.get(WorkspaceMembership, (workspace_id, existing_user.id))
        if not existing_user.is_active or (existing_member and existing_member.status != "active"):
            raise ApiError(409, "membership_suspended", "Restore the account and membership explicitly before inviting it.")
    # One currently valid invitation per email/workspace, regardless of project.
    db.execute(update(Invitation).where(Invitation.workspace_id == workspace_id,
        Invitation.email == body.email, Invitation.status == "pending").values(status="revoked"))
    token = new_token()
    invitation = Invitation(id=uuid4(), workspace_id=workspace_id, project_id=body.project_id,
        inviter_id=actor.id, email=body.email, workspace_role=body.workspace_role,
        project_role=body.project_role, token_hash=token_hash(token, "invite"),
        expires_at=now() + timedelta(hours=body.expires_in_hours))
    db.add(invitation)
    db.flush()
    audit(db, "invitation.created", actor_id=actor.id, workspace_id=workspace_id,
        project_id=body.project_id, subject_id=invitation.id, reason=body.reason,
        details={"workspace_role": body.workspace_role, "project_role": body.project_role})
    return invitation, token


def resolve_invitation(db: Session, token: str, *, lock: bool = False) -> Invitation:
    invalid = ApiError(400, "invitation_invalid", "This invitation is invalid, expired, revoked, or no longer authorized.")
    if not valid_token(token):
        raise invalid
    # Read the scope, then acquire its lock before the invitation row, matching
    # create/revoke/member-update lock order and preventing accept/revoke races.
    invitation = db.scalar(select(Invitation).where(Invitation.token_hash == token_hash(token, "invite")))
    if invitation is None:
        raise invalid
    if lock:
        db.scalar(select(Workspace).where(Workspace.id == invitation.workspace_id).with_for_update())
        invitation = db.scalar(select(Invitation).where(Invitation.id == invitation.id).with_for_update()
            .execution_options(populate_existing=True))
    if invitation.status != "pending" or utc(invitation.expires_at) <= now():
        raise invalid
    issuer = db.get(User, invitation.inviter_id, populate_existing=True)
    member = db.get(WorkspaceMembership, (invitation.workspace_id, invitation.inviter_id), populate_existing=True)
    if issuer is None or not issuer.is_active or member is None or member.status != "active" or member.role not in {"admin", "owner"}:
        raise invalid
    if invitation.workspace_role == "admin" and member.role != "owner":
        raise invalid
    return invitation
