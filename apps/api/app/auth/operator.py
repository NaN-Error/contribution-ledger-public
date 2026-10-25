"""Local operator tools. No HTTP endpoint grants operator powers or impersonates users."""
from datetime import timedelta
from uuid import UUID, uuid4, uuid5, NAMESPACE_URL
from sqlalchemy import select, update, func, delete
from app.auth.models import User, RecoveryToken, BrowserSession, ThrottleBucket
from app.auth.schemas import email_address
from app.auth.service import installation, revoke_all
from app.core.errors import ApiError
from app.db.session import Database
from app.projects.models import Workspace, WorkspaceMembership, Project, ProjectMembership, Invitation
from app.projects.service import create_workspace
from app.security.audit import audit
from app.security.passwords import hash_password
from app.security.tokens import new_token, token_hash, now


def check_reason(reason: str):
    if not 8 <= len(reason.strip()) <= 500:
        raise ValueError("An operator reason of 8 to 500 characters is required.")


def setup_token(database: Database) -> str:
    database.settings.require_local_foundation()
    with database.session() as db:
        state = installation(db, lock=True)
        if state.owner_user_id is not None:
            raise ApiError(409, "setup_complete", "Setup is complete. Use the audited account-recovery command instead.")
        token = new_token()
        state.bootstrap_token_hash = token_hash(token, "bootstrap")
        state.bootstrap_expires_at = now() + timedelta(hours=1)
        audit(db, "operator.bootstrap_token_issued", reason="Local operator requested a one-hour setup token.")
        db.commit()
        return token


def recovery_token(database: Database, email: str, reason: str) -> str:
    check_reason(reason)
    database.settings.require_local_foundation()
    with database.session() as db:
        user = db.scalar(select(User).where(User.email == email_address(email)).with_for_update())
        if user is None or not user.is_active:
            raise ApiError(400, "account_unavailable", "An active account is required. Recovery never re-enables disabled accounts.")
        db.execute(update(RecoveryToken).where(RecoveryToken.user_id == user.id,
            RecoveryToken.consumed_at.is_(None)).values(consumed_at=now()))
        revoke_all(db, user.id)
        token = new_token()
        db.add(RecoveryToken(user_id=user.id, token_hash=token_hash(token, "recovery"),
            expires_at=now() + timedelta(minutes=30)))
        audit(db, "operator.recovery_issued", subject_id=user.id, reason=reason)
        db.commit()
        return token


def set_account_active(database: Database, email: str, active: bool, reason: str):
    check_reason(reason)
    database.settings.require_local_foundation()
    with database.session() as db:
        user = db.scalar(select(User).where(User.email == email_address(email)))
        if user is None:
            raise ApiError(404, "not_found", "This account does not exist.")
        memberships = list(db.scalars(select(WorkspaceMembership).where(WorkspaceMembership.user_id == user.id)))
        # Workspace then user lock order matches scoped mutations and invitation acceptance.
        for workspace_id in sorted({member.workspace_id for member in memberships}, key=str):
            db.scalar(select(Workspace).where(Workspace.id == workspace_id).with_for_update())
        user = db.scalar(select(User).where(User.id == user.id).with_for_update().execution_options(populate_existing=True))
        memberships = list(db.scalars(select(WorkspaceMembership).where(WorkspaceMembership.user_id == user.id)
            .execution_options(populate_existing=True)))
        if not active:
            for member in memberships:
                if member.role == "owner" and member.status == "active":
                    others = db.scalar(select(func.count()).select_from(WorkspaceMembership).join(User)
                        .where(WorkspaceMembership.workspace_id == member.workspace_id,
                            WorkspaceMembership.role == "owner", WorkspaceMembership.status == "active",
                            WorkspaceMembership.user_id != user.id, User.is_active.is_(True)))
                    if not others:
                        raise ApiError(409, "last_owner", "Assign another active owner in each owned workspace before disabling this account.")
        user.is_active = active
        revoke_all(db, user.id)
        db.execute(update(RecoveryToken).where(RecoveryToken.user_id == user.id,
            RecoveryToken.consumed_at.is_(None)).values(consumed_at=now()))
        if not active:
            db.execute(update(Invitation).where(Invitation.inviter_id == user.id,
                Invitation.status == "pending").values(status="revoked"))
        audit(db, "operator.account_enabled" if active else "operator.account_disabled", subject_id=user.id, reason=reason)
        db.commit()


def prune_auth(database: Database):
    with database.session() as db:
        cutoff = now() - timedelta(days=7)
        sessions = db.execute(delete(BrowserSession).where(BrowserSession.expires_at < cutoff)).rowcount
        tokens = db.execute(delete(RecoveryToken).where(RecoveryToken.expires_at < cutoff)).rowcount
        window = int(now().timestamp()) // 900
        db.execute(delete(ThrottleBucket).where(ThrottleBucket.window < window - 2))
        audit(db, "operator.expired_auth_pruned", details={"sessions": sessions, "recovery_tokens": tokens})
        db.commit()
    return {"expired_sessions_removed": sessions, "expired_recovery_tokens_removed": tokens}


def seed_team(database: Database, confirmation: str) -> dict:
    database.settings.require_development_tools()
    if confirmation != "CREATE SYNTHETIC TEAM":
        raise PermissionError("Explicit synthetic-team confirmation is required.")
    demo_id = uuid5(NAMESPACE_URL, "contribution-ledger:phase2-demo-a")
    with database.session() as db:
        state = installation(db, lock=True)
        if state.owner_user_id is None:
            raise ApiError(409, "setup_required", "Complete the first-owner setup before creating an optional demo team.")
        if db.get(Workspace, demo_id):
            raise ApiError(409, "demo_exists", "The synthetic team already exists. Passwords will not be reset or reprinted.")
        accounts = []
        people = []
        names = ["Demo owner A", "Demo owner B", "Demo Alice", "Demo Bob", "Demo Carla", "Demo Diego", "Demo Erin", "Demo independent reviewer"]
        suffix = uuid4().hex[:8]
        for index, name in enumerate(names):
            password = new_token()
            user = User(id=uuid4(), display_name=name, email=f"phase2-{index}-{suffix}@example.test",
                password_hash=hash_password(password), is_active=True)
            db.add(user)
            people.append(user)
            accounts.append({"name": name, "email": user.email, "password": password})
        db.flush()
        first = Workspace(id=demo_id, name="Synthetic team A")
        second = Workspace(id=uuid4(), name="Synthetic team B")
        db.add_all([first, second]); db.flush()
        for i, person in enumerate(people):
            workspace = second if i == 1 else first
            db.add(WorkspaceMembership(workspace_id=workspace.id, user_id=person.id,
                role="owner" if i < 2 else "member"))
        db.flush()
        game_a = Project(id=uuid4(), workspace_id=first.id, name="Synthetic game A")
        game_b = Project(id=uuid4(), workspace_id=second.id, name="Synthetic game B")
        db.add_all([game_a, game_b]); db.flush()
        for person in people[2:]:
            db.add(ProjectMembership(workspace_id=first.id, project_id=game_a.id, user_id=person.id,
                role="reviewer" if person == people[-1] else "contributor"))
        audit(db, "operator.synthetic_team_created", workspace_id=first.id,
            reason="Explicit development-only synthetic team command; no real review independence is established.")
        db.commit()
        return {"warning": "Synthetic test credentials shown only once. Never use these accounts as independent reviewers of real work.",
            "accounts": accounts, "workspace_a": str(first.id), "workspace_b": str(second.id)}
