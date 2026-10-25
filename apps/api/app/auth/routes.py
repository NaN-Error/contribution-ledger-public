from uuid import UUID, uuid4
from fastapi import APIRouter, Request, Response
from sqlalchemy import select, update, func
from sqlalchemy.exc import IntegrityError
from app.auth.dependencies import Db, Browser, Authenticated, find_identity
from app.auth.models import BrowserSession, RecoveryToken, User
from app.auth.schemas import (BootstrapInput, InviteAcceptInput, LoginInput,
    PasswordChangeInput, RecoveryInput, TokenInput)
from app.auth.service import create_session, installation, revoke_all, session_response
from app.core.errors import ApiError
from app.projects.models import Workspace, WorkspaceMembership, Project, ProjectMembership
from app.projects.service import create_workspace, resolve_invitation
from app.security.audit import audit
from app.security.passwords import hash_password, password_hasher, verify_password
from app.security.throttling import reserve_attempts
from app.security.tokens import now, token_hash, utc, valid_token

router = APIRouter(prefix="/api/v1/auth", tags=["accounts"])


def peer(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def rotate(db, request, response, identity, user):
    session, raw = create_session(db, user, request.app.state.settings, identity.session if identity else None)
    db.commit()
    return session_response(db, response, request.app.state.settings, session, raw, user, set_cookie=True)


@router.get("/session")
def session_status(request: Request, response: Response, db: Db):
    identity = find_identity(request, db)
    settings = request.app.state.settings
    if identity:
        return session_response(db, response, settings, identity.session, identity.raw_token, identity.user, set_cookie=False)
    reserve_attempts(db, [("session-peer:" + peer(request), 200)])
    session, raw = create_session(db, None, settings)
    db.commit()
    return session_response(db, response, settings, session, raw, None, set_cookie=True)


@router.post("/bootstrap")
def bootstrap(body: BootstrapInput, request: Request, response: Response, db: Db, identity: Browser):
    reserve_attempts(db, [("bootstrap-peer:" + peer(request), 10)])
    state = installation(db, lock=True)
    if (state.owner_user_id is not None or state.bootstrap_token_hash is None
        or state.bootstrap_expires_at is None or utc(state.bootstrap_expires_at) <= now()
        or not valid_token(body.token) or state.bootstrap_token_hash != token_hash(body.token, "bootstrap")):
        raise ApiError(400, "bootstrap_unavailable", "Setup is already complete, or the operator's setup token is invalid or expired.")
    user = User(id=uuid4(), email=body.email, display_name=body.display_name,
        password_hash=hash_password(body.password.get_secret_value()), is_active=True)
    db.add(user)
    db.flush()
    workspace = create_workspace(db, user, body.workspace_name)
    project = Project(id=uuid4(), workspace_id=workspace.id, name=body.project_name, timezone=body.timezone)
    db.add(project)
    db.flush()
    state.owner_user_id = user.id
    state.bootstrap_token_hash = state.bootstrap_expires_at = None
    audit(db, "installation.bootstrapped", actor_id=user.id, workspace_id=workspace.id)
    audit(db, "project.created", actor_id=user.id, workspace_id=workspace.id, project_id=project.id)
    return rotate(db, request, response, identity, user)


@router.post("/login")
def login(body: LoginInput, request: Request, response: Response, db: Db, identity: Browser):
    if identity.user is not None:
        raise ApiError(409, "already_signed_in", "Sign out before using a different account.")
    settings = request.app.state.settings
    reserve_attempts(db, [("login-email:" + body.email, settings.login_account_limit),
        ("login-peer:" + peer(request), settings.login_peer_limit)])
    user = db.scalar(select(User).where(User.email == body.email).with_for_update()
        .execution_options(populate_existing=True))
    valid = verify_password(user.password_hash if user else None, body.password.get_secret_value())
    if user is None or not valid or not user.is_active:
        # Same message for missing, disabled and incorrect-password accounts.
        audit(db, "auth.login_failed")
        db.commit()
        raise ApiError(401, "invalid_credentials", "The email or password is incorrect, or the account is unavailable.")
    if password_hasher().check_needs_rehash(user.password_hash):
        user.password_hash = hash_password(body.password.get_secret_value())
    audit(db, "auth.login", actor_id=user.id)
    return rotate(db, request, response, identity, user)


@router.post("/logout")
def logout(request: Request, response: Response, db: Db, identity: Browser):
    if identity.user:
        audit(db, "auth.logout", actor_id=identity.user.id)
    return rotate(db, request, response, identity, None)


@router.post("/password")
def change_password(body: PasswordChangeInput, request: Request, response: Response, db: Db, identity: Authenticated):
    reserve_attempts(db, [("reauth-user:" + str(identity.user.id), 10), ("reauth-peer:" + peer(request), 100)])
    user = db.scalar(select(User).where(User.id == identity.user.id).with_for_update().execution_options(populate_existing=True))
    if not user.is_active or not verify_password(user.password_hash, body.current_password.get_secret_value()):
        raise ApiError(400, "password_change_rejected", "The current password could not be verified.")
    if body.current_password.get_secret_value() == body.password.get_secret_value():
        raise ApiError(400, "password_unchanged", "Choose a different password.")
    user.password_hash = hash_password(body.password.get_secret_value())
    revoke_all(db, user.id)
    db.execute(update(RecoveryToken).where(RecoveryToken.user_id == user.id,
        RecoveryToken.consumed_at.is_(None)).values(consumed_at=now()))
    audit(db, "auth.password_changed", actor_id=user.id)
    return rotate(db, request, response, identity, user)


@router.get("/sessions")
def sessions(db: Db, identity: Authenticated):
    rows = db.scalars(select(BrowserSession).where(BrowserSession.user_id == identity.user.id,
        BrowserSession.revoked_at.is_(None), BrowserSession.expires_at > now())
        .order_by(BrowserSession.created_at.desc(), BrowserSession.id).limit(10))
    return {"items": [{"id": row.id, "created_at": row.created_at, "last_seen_at": row.last_seen_at,
        "expires_at": row.expires_at, "current": row.id == identity.session.id} for row in rows]}


@router.delete("/sessions/{session_id}")
def revoke_session(session_id: UUID, db: Db, identity: Authenticated):
    target = db.scalar(select(BrowserSession).where(BrowserSession.id == session_id,
        BrowserSession.user_id == identity.user.id).with_for_update())
    if target is None:
        raise ApiError(404, "not_found", "This session is not available.")
    target.revoked_at = now()
    audit(db, "auth.session_revoked", actor_id=identity.user.id, subject_id=session_id)
    db.commit()
    return {"revoked": True, "current": session_id == identity.session.id}


@router.post("/invitations/inspect")
def inspect_invitation(body: TokenInput, request: Request, db: Db, identity: Browser):
    reserve_attempts(db, [("invite-inspect-peer:" + peer(request), 100)])
    invitation = resolve_invitation(db, body.token)
    workspace = db.get(Workspace, invitation.workspace_id)
    project = db.get(Project, invitation.project_id) if invitation.project_id else None
    user = db.scalar(select(User).where(User.email == invitation.email))
    return {"email": invitation.email, "workspace_name": workspace.name,
        "project_name": project.name if project else None, "workspace_role": invitation.workspace_role,
        "project_role": invitation.project_role, "expires_at": invitation.expires_at,
        "existing_account": user is not None,
        "matching_account": bool(user and identity.user and user.id == identity.user.id)}


@router.post("/invitations/accept")
def accept_invitation(body: InviteAcceptInput, request: Request, response: Response, db: Db, identity: Browser):
    reserve_attempts(db, [("invite-accept-peer:" + peer(request), 30)])
    # Serialize account creation across workspaces in the small invited pilot.
    # This is a short database transaction, not a process-local mutex.
    state = installation(db, lock=True)
    if state.owner_user_id is None:
        raise ApiError(409, "setup_required", "Complete installation setup first.")
    invitation = resolve_invitation(db, body.token, lock=True)
    user = db.scalar(select(User).where(User.email == invitation.email).with_for_update()
        .execution_options(populate_existing=True))
    if user:
        if not user.is_active or not identity.user or identity.user.id != user.id:
            raise ApiError(403, "invited_account_required", "Sign in to the invited account before accepting this invitation.")
    else:
        if identity.user:
            raise ApiError(403, "invited_account_required", "Sign out before creating the invited account.")
        if body.password is None or body.display_name is None:
            raise ApiError(422, "account_details_required", "Enter a display name and a 15–128 character password.")
        user = User(id=uuid4(), email=invitation.email, display_name=body.display_name,
            password_hash=hash_password(body.password.get_secret_value()), is_active=True)
        db.add(user)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            raise ApiError(409, "account_changed", "Account state changed. Sign in and try accepting again.") from None
    member = db.get(WorkspaceMembership, (invitation.workspace_id, user.id), populate_existing=True)
    if member and member.status != "active":
        raise ApiError(409, "membership_suspended", "An administrator must explicitly restore the suspended membership.")
    if member is None:
        if db.scalar(select(func.count()).select_from(WorkspaceMembership)
            .where(WorkspaceMembership.user_id == user.id)) >= 100:
            raise ApiError(409, "workspace_limit", "This local pilot supports up to 100 memberships per account.")
        member = WorkspaceMembership(workspace_id=invitation.workspace_id, user_id=user.id,
            role=invitation.workspace_role)
        db.add(member)
        db.flush()
    # Invites grant first-time membership only. Existing workspace roles cannot
    # be escalated (or downgraded) through an old invitation.
    elif member.role != invitation.workspace_role:
        raise ApiError(409, "membership_changed", "Existing membership differs. Ask an administrator to update it explicitly.")
    if invitation.project_id:
        target = db.get(ProjectMembership, (invitation.workspace_id, invitation.project_id, user.id))
        if target and (target.status != "active" or target.role != invitation.project_role):
            raise ApiError(409, "project_membership_changed", "Existing project access differs. An administrator must update it explicitly.")
        if target is None:
            db.add(ProjectMembership(workspace_id=invitation.workspace_id, project_id=invitation.project_id,
                user_id=user.id, role=invitation.project_role))
    invitation.status, invitation.accepted_by, invitation.accepted_at = "accepted", user.id, now()
    audit(db, "invitation.accepted", actor_id=user.id, workspace_id=invitation.workspace_id,
        project_id=invitation.project_id, subject_id=invitation.id,
        details={"workspace_role": member.role, "project_role": invitation.project_role})
    return rotate(db, request, response, identity, user)


@router.post("/recover")
def recover(body: RecoveryInput, request: Request, response: Response, db: Db, identity: Browser):
    reserve_attempts(db, [("recovery-peer:" + peer(request), 10)])
    invalid = ApiError(400, "recovery_invalid", "This recovery token is invalid, expired, or no longer authorized.")
    if not valid_token(body.token):
        raise invalid
    recovery = db.scalar(select(RecoveryToken).where(RecoveryToken.token_hash == token_hash(body.token, "recovery")))
    if recovery is None:
        raise invalid
    user = db.scalar(select(User).where(User.id == recovery.user_id).with_for_update().execution_options(populate_existing=True))
    recovery = db.scalar(select(RecoveryToken).where(RecoveryToken.id == recovery.id).with_for_update()
        .execution_options(populate_existing=True))
    if not user.is_active or recovery.consumed_at is not None or utc(recovery.expires_at) <= now():
        raise invalid
    user.password_hash = hash_password(body.password.get_secret_value())
    db.execute(update(RecoveryToken).where(RecoveryToken.user_id == user.id,
        RecoveryToken.consumed_at.is_(None)).values(consumed_at=now()))
    revoke_all(db, user.id)
    audit(db, "auth.recovery_completed", actor_id=user.id)
    # Recovery does not automatically sign in or act as the operator.
    return rotate(db, request, response, identity, None)
