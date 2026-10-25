from typing import Literal
from uuid import UUID
from pydantic import Field, model_validator
from app.auth.schemas import Input, Name, Email, Reason, Timezone

WorkspaceRole = Literal["owner", "admin", "member"]
ProjectRole = Literal["admin", "contributor", "reviewer", "finance", "viewer"]
MemberStatus = Literal["active", "suspended"]


class WorkspaceCreate(Input):
    name: Name


class ProjectCreate(Input):
    name: Name
    description: str = Field(default="", max_length=1000)
    timezone: Timezone = "UTC"
    currency: Literal["USD"] = "USD"


class ProjectUpdate(ProjectCreate):
    expected_version: int = Field(ge=1)
    reason: Reason


class WorkspaceMemberUpdate(Input):
    role: WorkspaceRole
    status: MemberStatus
    expected_version: int = Field(ge=1)
    reason: Reason


class ProjectMemberCreate(Input):
    user_id: UUID
    role: ProjectRole
    reason: Reason


class ProjectMemberUpdate(Input):
    role: ProjectRole
    status: MemberStatus
    expected_version: int = Field(ge=1)
    reason: Reason


class InvitationCreate(Input):
    email: Email
    workspace_role: Literal["admin", "member"] = "member"
    project_id: UUID | None = None
    project_role: ProjectRole | None = None
    expires_in_hours: int = Field(default=72, ge=1, le=168)
    reason: Reason

    @model_validator(mode="after")
    def paired_project(self):
        if (self.project_id is None) != (self.project_role is None):
            raise ValueError("A project and a project role must be provided together.")
        return self


class ReasonInput(Input):
    reason: Reason
