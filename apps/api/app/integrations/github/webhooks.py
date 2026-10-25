"""Signed intake commits routing intents before acknowledging delivery.

Revocations fence work immediately in the same transaction; grants/unsuspends
NEVER reactivate a connection. No GitHub API, broker, or ledger call occurs here.
"""
from uuid import uuid4
from datetime import timedelta
from sqlalchemy import select, func, or_
from sqlalchemy.exc import IntegrityError
from fastapi import APIRouter, Request
from starlette.concurrency import run_in_threadpool
from app.auth.dependencies import Db
from app.core.errors import ApiError
from app.projects.models import Workspace
from app.security.tokens import now, utc
from app.security.audit import audit
from app.security.secrets.store import MountedSecretStore, SecretUnavailable
from app.integrations.github.models import GitHubConnection, GitHubRepository, GitHubImport
from app.integrations.github.sync_models import WebhookDelivery, WebhookTarget, GitHubSyncConfig
from app.integrations.github.webhook_protocol import parse_signed, WEBHOOK_PATH

router = APIRouter(tags=['signed-github-webhook'])
ACTIVE = ('queued','running','paused','failed')


def duplicate(db, envelope, app_id):
    prior = db.scalar(select(WebhookDelivery).where(WebhookDelivery.app_id == app_id,
        or_(WebhookDelivery.delivery_key == envelope.delivery_key, WebhookDelivery.payload_hash == envelope.payload_hash)))
    if prior is not None:
        if prior.payload_hash != envelope.payload_hash or prior.event != envelope.event or prior.action != envelope.action:
            raise ApiError(409,'github_delivery_conflict','A delivery identifier or signed body was reused with different routing information.')
        return True
    return False


def fence_repository(db, repo, code):
    """Caller holds workspace lock. Fences in-flight commits, not just the UI."""
    repo.enabled = False; repo.version += 1
    for job in db.scalars(select(GitHubImport).where(GitHubImport.repository_id == repo.id,
            GitHubImport.state.in_(ACTIVE)).with_for_update()):
        job.state = 'cancelled'; job.version += 1; job.lease_token = None; job.lease_until = None
        job.error_code = code; job.finished_at = now()
    config = db.scalar(select(GitHubSyncConfig).where(GitHubSyncConfig.repository_id == repo.id))
    if config:
        config.enabled = False; config.version += 1; config.last_error = code; config.updated_at = now()
    for signal in db.scalars(select(WebhookTarget).where(WebhookTarget.repository_id == repo.id,
            WebhookTarget.state == 'pending')):
        signal.state = 'ignored'; signal.note = code


def accept_delivery(db, envelope, settings):
    if duplicate(db,envelope,settings.github_app_id): return {'accepted':True,'duplicate':True}
    if db.scalar(select(func.count()).select_from(WebhookDelivery)) >= settings.github_webhook_receipt_limit:
        raise ApiError(503,'github_receipt_capacity','The bounded webhook receipt store requires operator attention.')
    connections = db.scalars(select(GitHubConnection).where(GitHubConnection.app_id == settings.github_app_id,
        GitHubConnection.installation_id == envelope.installation_id)).all()
    # All project writers share this lock order. Network work is never inside it.
    workspace_ids = sorted({c.workspace_id for c in connections}, key=str)
    for wid in workspace_ids:
        db.scalar(select(Workspace).where(Workspace.id==wid).with_for_update())
    connections = db.scalars(select(GitHubConnection).where(GitHubConnection.app_id == settings.github_app_id,
        GitHubConnection.installation_id == envelope.installation_id).execution_options(populate_existing=True)).all()
    receipt = WebhookDelivery(id=uuid4(),app_id=settings.github_app_id,delivery_key=envelope.delivery_key,
        payload_hash=envelope.payload_hash,body_bytes=envelope.body_bytes,event=envelope.event,action=envelope.action,
        installation_id=envelope.installation_id,disposition='accepted_supported' if envelope.supported else 'ignored_unsupported',received_at=now())
    db.add(receipt); db.flush() # Unique identifiers also serialize racing duplicates.
    matches = 0
    for conn in sorted(connections,key=lambda c:str(c.id)):
        query = select(GitHubRepository).where(GitHubRepository.connection_id==conn.id)
        if envelope.event != 'installation':
            query = query.where(GitHubRepository.github_id.in_(envelope.repository_ids))
        repos = db.scalars(query.order_by(GitHubRepository.id).execution_options(populate_existing=True)).all()
        if envelope.revoke and envelope.event == 'installation':
            conn.enabled=False; conn.version+=1; conn.last_error=envelope.revoke
        for repo in repos:
            state,note='ignored','event_not_enabled'
            if envelope.revoke:
                fence_repository(db,repo,envelope.revoke)
                state,note='processed',envelope.revoke
            elif envelope.supported and envelope.targets:
                cfg = db.scalar(select(GitHubSyncConfig).where(GitHubSyncConfig.repository_id==repo.id))
                if cfg and cfg.enabled and repo.enabled and conn.enabled and utc(conn.verified_until)>now():
                    count=db.scalar(select(func.count()).select_from(WebhookTarget).where(
                        WebhookTarget.repository_id==repo.id,WebhookTarget.state=='pending'))
                    if count < 1000:
                        state,note='pending','awaiting_authoritative_fetch'
                    else:
                        note='signal_capacity_reconciliation_required'
                    # Debounce; an existing earlier due time is never postponed.
                    cfg.next_due_at=min(utc(cfg.next_due_at),now()+timedelta(seconds=30))
            db.add(WebhookTarget(workspace_id=repo.workspace_id,project_id=repo.project_id,
                repository_id=repo.id,delivery_id=receipt.id,targets=list(envelope.targets),state=state,
                note=note,created_at=now()))
            matches += 1
            if envelope.revoke:
                audit(db,'github.webhook_revocation',workspace_id=repo.workspace_id,project_id=repo.project_id,
                    subject_id=repo.id,reason='Signed revocation fenced imports; captured evidence and finalized credit remain unchanged.',
                    details={'delivery_id':str(receipt.id),'code':envelope.revoke})
    db.flush()
    return {'accepted':True,'duplicate':False}


@router.post(WEBHOOK_PATH,status_code=202)
async def intake(request:Request,db:Db):
    settings=request.app.state.settings
    if not settings.github_enabled or not settings.github_webhook_enabled:
        raise ApiError(404,'not_found','This endpoint is not enabled.')
    try:
        secret=MountedSecretStore(settings.github_secret_root).read('github-webhook-secret')
    except SecretUnavailable:
        raise ApiError(503,'github_webhook_secret_unavailable','Webhook verification is not configured.') from None
    envelope=parse_signed(await request.body(),request.scope.get('headers',[]),secret,settings.github_app_id)
    return await run_in_threadpool(commit_delivery,db,envelope,settings)


def commit_delivery(db,envelope,settings):
    try:
        result=accept_delivery(db,envelope,settings)
        db.commit();return result
    except IntegrityError:
        db.rollback()
        if duplicate(db,envelope,settings.github_app_id):
            return {'accepted':True,'duplicate':True}
        raise ApiError(503,'github_intake_retry','The delivery could not be durably accepted. Retry later.') from None
