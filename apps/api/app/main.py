from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException
from starlette.middleware.trustedhost import TrustedHostMiddleware
from app.core.config import BUILD_VERSION, Settings, get_settings
from app.core.errors import http_error, unexpected_error, validation_error
from app.core.observability import RequestContextMiddleware, configure_logging
from app.db.session import Database
from app.system.routes import router
from app.auth.routes import router as auth_router
from app.projects.routes import router as projects_router
from app.policies.routes import router as policies_router
from app.contributions.budgets.routes import router as budgets_router
from app.contributions.work_packages.routes import router as work_packages_router
from app.security.middleware import BrowserBoundaryMiddleware
from app.core.errors import ApiError, application_error
from app.storage.factory import create_storage
from app.evidence.routes import router as evidence_router
from app.reviews.routes import router as reviews_router
from app.finance.simulator.routes import router as simulator_router
from app.integrations.github.routes import router as github_router, callback_router as github_callback_router, evidence_router as github_evidence_router
from app.integrations.github.client import GitHubClient
from app.security.secrets.store import MountedSecretStore
from app.integrations.github.webhooks import router as github_webhook_router
from app.integrations.github.sync_routes import router as github_sync_router


from app.ai.routes import router as ai_router
from app.ai.assessments.routes import router as assessments_router
from app.contributions.reconstruction.routes import router as reconstruction_router
from app.reporting.routes import router as reporting_router
from app.analysis.routes import router as analysis_router
from app.analysis.capture import PublicRepositoryClient
from app.finance.periods.routes import router as finance_router
from app.providers.factory import ProviderFactory
from app.security.secrets.encrypted import EncryptedCredentialStore


def create_app(settings: Settings | None = None, database: Database | None = None, object_storage=None, github_client=None, ai_store=None, provider_factory=None, public_repository_client=None, repository_store=None, repository_transport=None) -> FastAPI:
    settings = settings or get_settings()
    settings.require_local_foundation()
    database = database or Database(settings)
    configure_logging()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Never migrate, seed, or reset on API startup.
        if settings.environment == "staging":
            from app.auth.mfa_crypto import FactorCipher
            from app.operations.privileges import verify_runtime_role
            FactorCipher(settings.auth_master_key_file).key()
            with database.engine.connect() as connection:
                verify_runtime_role(connection)
                from sqlalchemy import text
                if connection.execute(text("SELECT count(*) FROM users WHERE email LIKE 'phase2-%@example.test'")).scalar_one():
                    raise ValueError("Generated development accounts cannot be used in restricted staging.")
        yield
        database.dispose()

    app = FastAPI(title="Contribution ledger API", version=BUILD_VERSION,
                  description="Local invited-team pilot. Policies, work packages, private evidence, independent review, contribution credit, disputes and non-payable revenue simulations. Read-only GitHub evidence imports. No money movement.",
                  lifespan=lifespan, debug=False, redoc_url=None,
                  docs_url="/docs" if settings.environment in {"development","test"} else None,
                  openapi_url="/openapi.json" if settings.environment in {"development","test"} else None)
    app.state.database = database
    app.state.settings = settings
    app.state.object_storage = object_storage or create_storage(settings)
    app.state.github_client = github_client or GitHubClient(settings, MountedSecretStore(settings.github_secret_root))
    app.state.public_repository_client = public_repository_client or PublicRepositoryClient()
    app.state.repository_store = repository_store or EncryptedCredentialStore(settings.repository_credential_root,settings.repository_master_key_file)
    app.state.repository_transport = repository_transport
    app.state.ai_store = ai_store or EncryptedCredentialStore(settings.ai_credential_root, settings.ai_master_key_file)
    app.state.provider_factory = provider_factory or ProviderFactory(settings)
    app.add_exception_handler(ApiError, application_error)
    app.add_exception_handler(HTTPException, http_error)
    app.add_exception_handler(RequestValidationError, validation_error)
    app.add_exception_handler(Exception, unexpected_error)
    app.add_middleware(BrowserBoundaryMiddleware, allowed_origins=settings.allowed_origins)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)
    app.add_middleware(RequestContextMiddleware)
    app.include_router(router)
    app.include_router(auth_router)
    from app.auth.desktop import router as desktop_router
    app.include_router(desktop_router)
    from app.auth.mfa_routes import router as mfa_router
    app.include_router(mfa_router)
    app.include_router(projects_router)
    app.include_router(policies_router)
    app.include_router(budgets_router)
    app.include_router(work_packages_router)
    app.include_router(evidence_router)
    app.include_router(reviews_router)
    app.include_router(simulator_router)
    app.include_router(github_router)
    app.include_router(github_callback_router)
    app.include_router(github_evidence_router)
    app.include_router(github_webhook_router)
    app.include_router(github_sync_router)
    app.include_router(ai_router)
    app.include_router(assessments_router)
    app.include_router(reconstruction_router)
    app.include_router(reporting_router)
    app.include_router(analysis_router)
    app.include_router(finance_router)
    return app
