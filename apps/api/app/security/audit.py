from uuid import UUID
from sqlalchemy.orm import Session
from app.projects.models import AuditEvent


def audit(db: Session, action: str, *, actor_id: UUID | None = None,
          workspace_id: UUID | None = None, project_id: UUID | None = None,
          subject_id: UUID | str | None = None, reason: str = "", details: dict | None = None) -> None:
    # Call sites construct an allowlisted summary, never request bodies or tokens.
    db.add(AuditEvent(action=action, actor_id=actor_id, workspace_id=workspace_id,
        project_id=project_id, subject_id=str(subject_id) if subject_id else None,
        reason=reason, details=details or {}))
