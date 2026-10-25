"""Transport-independent scoped checkpoint entrypoint."""
from uuid import UUID
from app.integrations.github.models import GitHubImport
from app.integrations.github.importer import step


def run_checkpoint(database,settings,client,job_id,workspace_id,project_id):
    try:j,w,p=UUID(job_id),UUID(workspace_id),UUID(project_id)
    except (ValueError,TypeError,AttributeError):return 'invalid_message'
    if not settings.github_enabled or not settings.github_sync_enabled:return 'disabled'
    with database.session() as db:
        job=db.get(GitHubImport,j)
        if job is None or (job.workspace_id,job.project_id)!=(w,p):return 'scope_rejected'
    # step revalidates current local roles, App selection and the real GitHub
    # authorizer before/after network work; possession of a broker ID isn't access.
    return step(database,settings,client,j)

