from datetime import timedelta
from uuid import UUID, uuid4
from sqlalchemy import select, update, or_
from sqlalchemy.orm import Session
from fastapi import Response
from app.auth.models import BrowserSession, InstallationState, User
from app.auth.schemas import UserView
from app.core.config import Settings
from app.core.errors import ApiError
from app.security.tokens import csrf_for, new_token, now, token_hash


def installation(db: Session, *, lock: bool = False) -> InstallationState:
    stmt = select(InstallationState).where(InstallationState.id == 1)
    if lock:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    result = db.scalar(stmt)
    if result is None:
        raise ApiError(503, "migration_required", "Apply the database migration before continuing.")
    return result


def revoke_all(db: Session, user_id: UUID):
    db.execute(update(BrowserSession).where(or_(BrowserSession.user_id == user_id, BrowserSession.pending_user_id == user_id),
        BrowserSession.revoked_at.is_(None)).values(revoked_at=now()))


def create_session(db: Session, user: User | None, settings: Settings,
                   previous: BrowserSession | None = None, *, mfa_passed: bool = False) -> tuple[BrowserSession, str]:
    if previous is not None:
        previous.revoked_at = now()
    token = new_token()
    instant = now()
    from app.auth.mfa_models import Authenticator
    factor=db.get(Authenticator,user.id) if user else None
    pending=bool(user and not mfa_passed and (settings.require_mfa or (factor and (factor.enabled or factor.must_enroll))))
    lifetime = 5 if pending else settings.session_absolute_minutes if user else 10
    session = BrowserSession(id=uuid4(), token_hash=token_hash(token, "session"),
        user_id=user.id if user and not pending else None,
        pending_user_id=user.id if pending else None,
        mfa_verified_at=instant if user and mfa_passed else None,
        created_at=instant, last_seen_at=instant,
        expires_at=instant + timedelta(minutes=lifetime))
    if user:
        old = list(db.scalars(select(BrowserSession).where(or_(BrowserSession.user_id == user.id, BrowserSession.pending_user_id == user.id),
            BrowserSession.revoked_at.is_(None), BrowserSession.expires_at > instant)
            .order_by(BrowserSession.created_at.desc(), BrowserSession.id)))
        for extra in old[9:]:
            extra.revoked_at = instant
    db.add(session)
    db.flush()
    return session, token


def session_response(db: Session, response: Response, settings: Settings,
                     session: BrowserSession, raw: str, user: User | None, *, set_cookie: bool) -> dict:
    if set_cookie:
        response.set_cookie(settings.session_cookie_name, raw, httponly=True,
            secure=settings.secure_cookies, samesite="lax", path="/",
            max_age=(settings.session_absolute_minutes if user else 10) * 60)
    from app.auth.mfa_models import Authenticator
    factor=db.get(Authenticator, session.pending_user_id or session.user_id) if (session.pending_user_id or session.user_id) else None
    return {"mfa_required": session.pending_user_id is not None,
        "mfa_enrolled": bool(factor and factor.enabled),
        "user": UserView.model_validate(user).model_dump(mode="json") if user and session.user_id else None,
        "csrf_token": csrf_for(raw), "session_id": str(session.id),
        "expires_at": session.expires_at,
        "bootstrap_required": installation(db).owner_user_id is None,
        "password_min_length": 15}
