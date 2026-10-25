"""The only registered worker entrypoint accepts exact scoped IDs, not commands."""
from uuid import UUID
from app.jobs.celery_app import celery_app
from app.core.config import get_settings
from app.db.session import Database
from app.security.secrets.store import MountedSecretStore
from app.integrations.github.client import GitHubClient
from app.integrations.github.models import GitHubImport
from app.integrations.github.importer import step
from app.jobs.dispatch import heartbeat


from app.jobs.checkpoint import run_checkpoint


@celery_app.task(name='ledger.github.checkpoint',ignore_result=True)
def checkpoint(job_id,workspace_id,project_id):
    settings=get_settings();settings.require_local_foundation()
    database=Database(settings)
    try:
        client=GitHubClient(settings,MountedSecretStore(settings.github_secret_root))
        result=run_checkpoint(database,settings,client,job_id,workspace_id,project_id)
        heartbeat(database,'github-worker',result)
        return result
    finally:database.dispose()
