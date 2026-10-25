"""Explicit local operator provisioning and one-use desktop sign-in. Never remote auto-login."""
from datetime import datetime, timedelta
from uuid import UUID, uuid4
from fastapi import APIRouter, Request, Response
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Uuid, select
from sqlalchemy.orm import Mapped, mapped_column
from app.auth.dependencies import Browser, Db
from app.auth.models import User
from app.auth.schemas import TokenInput
from app.auth.service import installation
from app.core.errors import ApiError
from app.db.base import Base
from app.projects.models import Project
from app.projects.service import create_workspace
from app.security.audit import audit
from app.security.passwords import hash_password
from app.security.throttling import reserve_attempts
from app.security.tokens import new_token, now, token_hash, utc, valid_token


class DesktopProfile(Base):
    __tablename__ = 'desktop_profiles'
    __table_args__ = (CheckConstraint('id = 1', name='desktop_singleton'),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey('users.id'), nullable=False, unique=True)
    ticket_hash: Mapped[str | None] = mapped_column(String(64))
    ticket_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


def require_desktop(settings):
    if not settings.desktop_enabled or settings.environment not in {'development', 'test'}:
        raise ApiError(404, 'desktop_disabled', 'Desktop access is not enabled for this installation.')


def desktop_ticket(database):
    """Only called by the local launcher. A regular existing owner is never adopted."""
    require_desktop(database.settings)
    with database.session() as db:
        state = installation(db, lock=True)
        profile = db.get(DesktopProfile, 1)
        if profile is None:
            if state.owner_user_id is not None or db.scalar(select(User.id).limit(1)) is not None:
                raise ApiError(409, 'desktop_existing_owner', 'Use normal sign-in for this existing installation. No accounts were changed.')
            user = User(id=uuid4(), email='personal@desktop.invalid', display_name='Local user',
                        password_hash=hash_password(new_token() + new_token()), is_active=True)
            db.add(user)
            db.flush()
            workspace = create_workspace(db, user, 'Personal workspace')
            project = Project(id=uuid4(), workspace_id=workspace.id, name='My repositories', timezone='UTC')
            db.add(project)
            db.flush()
            state.owner_user_id = user.id
            state.bootstrap_token_hash = state.bootstrap_expires_at = None
            profile = DesktopProfile(id=1, user_id=user.id)
            db.add(profile)
            audit(db, 'desktop.initialized', actor_id=user.id, workspace_id=workspace.id,
                  reason='Local operator selected personal desktop startup.')
            audit(db, 'project.created', actor_id=user.id, workspace_id=workspace.id, project_id=project.id)
        user = db.get(User, profile.user_id)
        if user is None or not user.is_active or state.owner_user_id != profile.user_id:
            raise ApiError(409, 'desktop_unavailable', 'The personal profile is unavailable. No account recovery was performed.')
        ticket = new_token()
        profile.ticket_hash = token_hash(ticket, 'desktop')
        profile.ticket_expires_at = now() + timedelta(minutes=2)
        audit(db, 'desktop.ticket_issued', actor_id=user.id)
        db.commit()
        return ticket


router = APIRouter(prefix='/api/v1/auth/desktop', tags=['accounts'])


@router.post('/login')
def desktop_login(body: TokenInput, request: Request, response: Response, db: Db, identity: Browser):
    require_desktop(request.app.state.settings)
    reserve_attempts(db, [('desktop-peer:' + (request.client.host if request.client else 'unknown'), 20)])
    state = installation(db, lock=True)
    profile = db.scalar(select(DesktopProfile).where(DesktopProfile.id == 1).with_for_update()
                        .execution_options(populate_existing=True))
    if (profile is None or profile.ticket_hash is None or profile.ticket_expires_at is None
        or utc(profile.ticket_expires_at) <= now() or not valid_token(body.token)
        or profile.ticket_hash != token_hash(body.token, 'desktop') or state.owner_user_id != profile.user_id):
        raise ApiError(400, 'desktop_ticket_unavailable', 'Open Start.cmd again to obtain a fresh desktop session.')
    user = db.get(User, profile.user_id, populate_existing=True)
    if user is None or not user.is_active:
        raise ApiError(400, 'desktop_ticket_unavailable', 'The personal profile is unavailable.')
    if identity.user is not None and identity.user.id != user.id:
        raise ApiError(409, 'already_signed_in', 'Sign out of the other account before opening the personal dashboard.')
    profile.ticket_hash = profile.ticket_expires_at = None
    audit(db, 'desktop.login', actor_id=user.id)
    # Ordinary rotation preserves MFA enrollment/challenge and disabled-user checks.
    from app.auth.routes import rotate
    return rotate(db, request, response, identity, user)
