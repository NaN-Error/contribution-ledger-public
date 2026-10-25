import hmac
from dataclasses import dataclass
from datetime import timedelta
from typing import Annotated
from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.auth.models import BrowserSession, User
from app.core.errors import ApiError
from app.security.tokens import csrf_for, now, token_hash, utc, valid_token


def get_db(request: Request):
    with request.app.state.database.session() as db:
        yield db


Db = Annotated[Session, Depends(get_db)]


@dataclass
class Identity:
    session: BrowserSession
    user: User | None
    raw_token: str


def find_identity(request: Request, db: Session) -> Identity | None:
    settings = request.app.state.settings
    raw = request.cookies.get(settings.session_cookie_name, "")
    if not valid_token(raw):
        return None
    session = db.scalar(select(BrowserSession).where(BrowserSession.token_hash == token_hash(raw, "session")))
    if session is None or session.revoked_at is not None or utc(session.expires_at) <= now():
        return None
    idle = settings.session_idle_minutes if session.user_id else 10
    if utc(session.last_seen_at) + timedelta(minutes=idle) <= now():
        return None
    user = db.get(User, session.user_id) if session.user_id else None
    if session.user_id and (user is None or not user.is_active):
        return None
    from app.auth.mfa_models import Authenticator
    factor=db.get(Authenticator,user.id) if user else None
    if user and session.mfa_verified_at is None and (settings.require_mfa or (factor and (factor.enabled or factor.must_enroll))):
        return None
    if session.pending_user_id:
        pending=db.get(User,session.pending_user_id)
        if pending is None or not pending.is_active:return None
    return Identity(session, user, raw)


def browser_identity(request: Request, db: Db) -> Identity:
    identity = find_identity(request, db)
    if identity is None:
        raise ApiError(401, "session_expired", "Your session expired or was revoked. Sign in again.")
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        provided = request.headers.get("X-CSRF-Token", "")
        if not hmac.compare_digest(provided.encode("utf-8"), csrf_for(identity.raw_token).encode("ascii")):
            raise ApiError(403, "csrf_rejected", "The security token is missing or stale. Reload before retrying.")
    return identity


Browser = Annotated[Identity, Depends(browser_identity)]


def authenticated(request: Request, db: Db, identity: Browser) -> Identity:
    if identity.user is None:
        raise ApiError(401, "authentication_required", "Sign in to continue.")
    # /auth/session polling itself never extends inactivity. Real application
    # requests count as activity, with a bounded write frequency.
    if utc(identity.session.last_seen_at) + timedelta(seconds=60) < now():
        identity.session.last_seen_at = now()
        db.commit()
    return identity


Authenticated = Annotated[Identity, Depends(authenticated)]
