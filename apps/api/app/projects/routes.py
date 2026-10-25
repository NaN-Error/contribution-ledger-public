from uuid import UUID, uuid4
from fastapi import APIRouter, Query
from sqlalchemy import select, func
from app.auth.dependencies import Db, Authenticated
from app.auth.models import User
from app.core.errors import ApiError
from app.projects.authorization import workspace_access, project_access, not_found
from app.projects.models import Workspace, WorkspaceMembership, Project, ProjectMembership, Invitation, AuditEvent
from app.projects.schemas import (WorkspaceCreate, ProjectCreate, ProjectUpdate, WorkspaceMemberUpdate,
    ProjectMemberCreate, ProjectMemberUpdate, InvitationCreate, ReasonInput)
from app.projects.service import (workspace_view, project_view, create_workspace,
    change_workspace_member, create_invitation, invitation_view)
from app.security.audit import audit
from app.security.tokens import now

router = APIRouter(prefix="/api/v1/workspaces", tags=["workspaces and projects"])


def member_view(member, user):
    return {"user_id": user.id, "display_name": user.display_name, "email": user.email,
        "account_active": user.is_active, "role": member.role, "status": member.status, "version": member.version}


@router.get("")
def workspaces(db: Db, identity: Authenticated):
    rows = db.execute(select(Workspace, WorkspaceMembership.role).join(WorkspaceMembership)
        .where(WorkspaceMembership.user_id == identity.user.id, WorkspaceMembership.status == "active")
        .order_by(Workspace.name, Workspace.id).limit(100))
    return {"items": [workspace_view(workspace, role) for workspace, role in rows]}


@router.post("", status_code=201)
def workspace_create(body: WorkspaceCreate, db: Db, identity: Authenticated):
    # Serialize per-account membership creation with invitation acceptance and
    # re-check disablement after acquiring the row lock.
    actor = db.scalar(select(User).where(User.id == identity.user.id).with_for_update()
        .execution_options(populate_existing=True))
    if not actor.is_active:
        raise ApiError(401, "authentication_required", "Sign in to continue.")
    # Explicit small-team bound, not a silent truncated list.
    if db.scalar(select(func.count()).select_from(WorkspaceMembership)
        .where(WorkspaceMembership.user_id == identity.user.id)) >= 100:
        raise ApiError(409, "workspace_limit", "This local pilot supports up to 100 memberships per account.")
    workspace = create_workspace(db, identity.user, body.name)
    db.commit()
    return workspace_view(workspace, "owner")


@router.get("/{workspace_id}")
def workspace_detail(workspace_id: UUID, db: Db, identity: Authenticated):
    workspace, member = workspace_access(db, workspace_id, identity.user.id)
    return workspace_view(workspace, member.role)


@router.get("/{workspace_id}/members")
def workspace_members(workspace_id: UUID, db: Db, identity: Authenticated):
    workspace_access(db, workspace_id, identity.user.id, manage=True)
    rows = db.execute(select(WorkspaceMembership, User).join(User)
        .where(WorkspaceMembership.workspace_id == workspace_id).order_by(User.display_name, User.id))
    return {"items": [member_view(member, user) for member, user in rows]}


@router.patch("/{workspace_id}/members/{user_id}")
def workspace_member_change(workspace_id: UUID, user_id: UUID, body: WorkspaceMemberUpdate, db: Db, identity: Authenticated):
    member = change_workspace_member(db, identity.user, workspace_id, user_id, body)
    db.commit()
    return member_view(member, db.get(User, user_id))


@router.get("/{workspace_id}/projects")
def projects(workspace_id: UUID, db: Db, identity: Authenticated):
    _, member = workspace_access(db, workspace_id, identity.user.id)
    if member.role in {"owner", "admin"}:
        rows = db.scalars(select(Project).where(Project.workspace_id == workspace_id).order_by(Project.name, Project.id))
        return {"items": [project_view(row, "admin") for row in rows]}
    rows = db.execute(select(Project, ProjectMembership.role).join(ProjectMembership,
        (ProjectMembership.project_id == Project.id) & (ProjectMembership.workspace_id == Project.workspace_id))
        .where(Project.workspace_id == workspace_id, ProjectMembership.user_id == identity.user.id,
            ProjectMembership.status == "active").order_by(Project.name, Project.id))
    return {"items": [project_view(row, role) for row, role in rows]}


@router.post("/{workspace_id}/projects", status_code=201)
def project_create(workspace_id: UUID, body: ProjectCreate, db: Db, identity: Authenticated):
    workspace_access(db, workspace_id, identity.user.id, manage=True, lock=True)
    if db.scalar(select(func.count()).select_from(Project).where(Project.workspace_id == workspace_id)) >= 100:
        raise ApiError(409, "project_limit", "This local pilot supports up to 100 projects per workspace.")
    project = Project(id=uuid4(), workspace_id=workspace_id, **body.model_dump())
    db.add(project)
    db.flush()
    audit(db, "project.created", actor_id=identity.user.id, workspace_id=workspace_id, project_id=project.id)
    db.commit()
    return project_view(project, "admin")


@router.get("/{workspace_id}/projects/{project_id}")
def project_detail(workspace_id: UUID, project_id: UUID, db: Db, identity: Authenticated):
    project, role = project_access(db, workspace_id, project_id, identity.user.id)
    return project_view(project, role)


@router.patch("/{workspace_id}/projects/{project_id}")
def project_change(workspace_id: UUID, project_id: UUID, body: ProjectUpdate, db: Db, identity: Authenticated):
    project, role = project_access(db, workspace_id, project_id, identity.user.id, manage=True, lock=True)
    if project.version != body.expected_version:
        raise ApiError(409, "stale_version", "Project settings changed. Refresh before editing again.")
    for field in ("name", "description", "timezone", "currency"):
        setattr(project, field, getattr(body, field))
    project.version += 1
    audit(db, "project.settings_changed", actor_id=identity.user.id, workspace_id=workspace_id,
        project_id=project_id, reason=body.reason, details={"version": project.version})
    db.commit()
    return project_view(project, role)


@router.get("/{workspace_id}/projects/{project_id}/members")
def project_members(workspace_id: UUID, project_id: UUID, db: Db, identity: Authenticated):
    project_access(db, workspace_id, project_id, identity.user.id, manage=True)
    rows = db.execute(select(ProjectMembership, User).join(User, User.id == ProjectMembership.user_id)
        .where(ProjectMembership.workspace_id == workspace_id, ProjectMembership.project_id == project_id)
        .order_by(User.display_name, User.id))
    return {"items": [member_view(member, user) for member, user in rows],
        "inherited_access": "Active workspace owners and administrators also have project administration access."}


@router.post("/{workspace_id}/projects/{project_id}/members", status_code=201)
def project_member_create(workspace_id: UUID, project_id: UUID, body: ProjectMemberCreate, db: Db, identity: Authenticated):
    project_access(db, workspace_id, project_id, identity.user.id, manage=True, lock=True)
    member = db.get(WorkspaceMembership, (workspace_id, body.user_id))
    user = db.get(User, body.user_id)
    if member is None or member.status != "active" or user is None or not user.is_active:
        raise not_found()
    if db.get(ProjectMembership, (workspace_id, project_id, body.user_id)):
        raise ApiError(409, "membership_exists", "This project membership already exists. Update its current version instead.")
    record = ProjectMembership(workspace_id=workspace_id, project_id=project_id, user_id=user.id, role=body.role)
    db.add(record)
    db.flush()
    audit(db, "project.member_added", actor_id=identity.user.id, workspace_id=workspace_id,
        project_id=project_id, subject_id=user.id, reason=body.reason, details={"role": body.role})
    db.commit()
    return member_view(record, user)


@router.patch("/{workspace_id}/projects/{project_id}/members/{user_id}")
def project_member_change(workspace_id: UUID, project_id: UUID, user_id: UUID, body: ProjectMemberUpdate, db: Db, identity: Authenticated):
    project_access(db, workspace_id, project_id, identity.user.id, manage=True, lock=True)
    member = db.get(ProjectMembership, (workspace_id, project_id, user_id))
    if member is None:
        raise not_found()
    if member.version != body.expected_version:
        raise ApiError(409, "stale_version", "Project membership changed. Refresh and review it again.")
    target_ws = db.get(WorkspaceMembership, (workspace_id, user_id))
    user = db.get(User, user_id)
    if body.status == "active" and (not user.is_active or target_ws.status != "active"):
        raise ApiError(409, "membership_suspended", "Restore the account and workspace membership first.")
    if target_ws.role in {"owner", "admin"}:
        raise ApiError(409, "inherited_access", "Workspace administrators retain inherited access. Change their workspace role instead.")
    before = {"role": member.role, "status": member.status}
    member.role, member.status, member.version = body.role, body.status, member.version + 1
    audit(db, "project.membership_changed", actor_id=identity.user.id, workspace_id=workspace_id,
        project_id=project_id, subject_id=user_id, reason=body.reason,
        details={"before": before, "after": {"role": member.role, "status": member.status}, "version": member.version})
    db.commit()
    return member_view(member, user)


@router.get("/{workspace_id}/invitations")
def invitations(workspace_id: UUID, db: Db, identity: Authenticated, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)):
    workspace_access(db, workspace_id, identity.user.id, manage=True)
    rows = db.scalars(select(Invitation).where(Invitation.workspace_id == workspace_id)
        .order_by(Invitation.created_at.desc(), Invitation.id).offset(offset).limit(limit + 1)).all()
    return {"items": [invitation_view(row) for row in rows[:limit]],
        "next_offset": offset + limit if len(rows) > limit else None}


@router.post("/{workspace_id}/invitations", status_code=201)
def invitation_create(workspace_id: UUID, body: InvitationCreate, db: Db, identity: Authenticated):
    invitation, token = create_invitation(db, identity.user, workspace_id, body)
    db.commit()
    # This is the ONLY response exposing the bearer token. No server-side URL log.
    return {**invitation_view(invitation), "token": token, "accept_fragment": "#invite/" + token}


@router.delete("/{workspace_id}/invitations/{invitation_id}")
def invitation_revoke(workspace_id: UUID, invitation_id: UUID, body: ReasonInput, db: Db, identity: Authenticated):
    workspace_access(db, workspace_id, identity.user.id, manage=True, lock=True)
    invitation = db.scalar(select(Invitation).where(Invitation.id == invitation_id,
        Invitation.workspace_id == workspace_id).with_for_update())
    if invitation is None:
        raise not_found()
    if invitation.status == "accepted":
        raise ApiError(409, "already_accepted", "This invitation was accepted. Manage the member's access instead.")
    if invitation.status != "revoked":
        invitation.status = "revoked"
        audit(db, "invitation.revoked", actor_id=identity.user.id, workspace_id=workspace_id,
            subject_id=invitation.id, reason=body.reason)
    db.commit()
    return invitation_view(invitation)


@router.get("/{workspace_id}/audit")
def audit_log(workspace_id: UUID, db: Db, identity: Authenticated, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)):
    workspace_access(db, workspace_id, identity.user.id, manage=True)
    rows = db.scalars(select(AuditEvent).where(AuditEvent.workspace_id == workspace_id)
        .order_by(AuditEvent.created_at.desc(), AuditEvent.id).offset(offset).limit(limit + 1)).all()
    return {"items": [{"id": row.id, "created_at": row.created_at, "actor_id": row.actor_id,
        "action": row.action, "subject_id": row.subject_id, "project_id": row.project_id,
        "reason": row.reason, "details": row.details} for row in rows[:limit]],
        "next_offset": offset + limit if len(rows) > limit else None}
