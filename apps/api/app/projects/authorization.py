"""All protected project operations resolve current membership in the requested scope."""
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.auth.models import User
from app.core.errors import ApiError
from app.projects.models import Workspace, WorkspaceMembership, Project, ProjectMembership


def not_found():
    return ApiError(404, "not_found", "This resource is not available in your current access scope.")


def workspace_access(db: Session, workspace_id: UUID, user_id: UUID, *, manage: bool = False,
                     lock: bool = False) -> tuple[Workspace, WorkspaceMembership]:
    # Acquire the tenant lock before re-reading permissions for any mutation.
    query = select(Workspace).where(Workspace.id == workspace_id)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    workspace = db.scalar(query)
    member = db.scalar(select(WorkspaceMembership).join(User, User.id == WorkspaceMembership.user_id)
        .where(WorkspaceMembership.workspace_id == workspace_id, WorkspaceMembership.user_id == user_id,
            WorkspaceMembership.status == "active", User.is_active.is_(True))
        .execution_options(populate_existing=True))
    if workspace is None or member is None:
        raise not_found()
    if manage and member.role not in {"owner", "admin"}:
        raise ApiError(403, "permission_denied", "Workspace administration is required for this action.")
    return workspace, member


def project_access(db: Session, workspace_id: UUID, project_id: UUID, user_id: UUID,
                   *, manage: bool = False, lock: bool = False) -> tuple[Project, str]:
    _, workspace_member = workspace_access(db, workspace_id, user_id, lock=lock)
    project = db.scalar(select(Project).where(Project.id == project_id, Project.workspace_id == workspace_id)
        .execution_options(populate_existing=True))
    if project is None:
        raise not_found()
    if workspace_member.role in {"owner", "admin"}:
        role = "admin"
    else:
        member = db.get(ProjectMembership, (workspace_id, project_id, user_id), populate_existing=True)
        if member is None or member.status != "active":
            raise not_found()
        role = member.role
    if manage and role != "admin":
        raise ApiError(403, "permission_denied", "Project administration is required for this action.")
    return project, role


def is_independent_reviewer(user_id: UUID, beneficiary_ids: set[UUID]) -> bool:
    # Future acceptance paths must ALSO check the review policy and permission.
    # No owner/admin shortcut can satisfy this independence test.
    return user_id not in beneficiary_ids
