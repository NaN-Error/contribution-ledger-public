from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL

BUILD_VERSION = "0.17.8-phase17"


class Settings(BaseSettings):
    """Only CL_-prefixed variables are consumed; no implicit .env loading."""

    model_config = SettingsConfigDict(
        env_prefix="CL_", extra="ignore", hide_input_in_errors=True
    )
    environment: Literal["development", "test", "staging", "production"] = "development"
    enable_development_tools: bool = False
    desktop_enabled: bool = False

    @model_validator(mode="after")
    def desktop_policy(self):
        from urllib.parse import urlsplit
        if self.desktop_enabled and (self.environment not in {"development", "test"}
            or any(urlsplit(origin).hostname not in {"127.0.0.1", "localhost", "::1"} for origin in self.allowed_origins)
            or any(host not in {"127.0.0.1", "localhost", "[::1]"} for host in self.allowed_hosts)):
            raise ValueError("Personal desktop access requires exclusively loopback development/test origins and hosts.")
        return self
    # Explicit browser action required for each public read; no account credential is used.
    repository_public_reads_enabled: bool = True
    repository_private_reads_enabled: bool = False
    repository_credential_root: str = '.local/github-credentials'
    repository_master_key_file: str = '.local/github-master/master.key'

    @model_validator(mode='after')
    def repository_read_policy(self):
        from pathlib import Path
        from urllib.parse import urlsplit
        local_hosts = {'127.0.0.1','localhost','[::1]'}
        if self.environment=='test': local_hosts.add('testserver')
        if self.repository_private_reads_enabled and (self.environment not in {'development','test'}
            or any(urlsplit(origin).hostname not in {'127.0.0.1','localhost','::1',*({'testserver'} if self.environment=='test' else set())} for origin in self.allowed_origins)
            or any(host not in local_hosts for host in self.allowed_hosts)):
            raise ValueError('Direct private repository credentials require a local development/test installation.')
        if not self.repository_credential_root.strip() or not self.repository_master_key_file.strip() or Path(self.repository_master_key_file).absolute().is_relative_to(Path(self.repository_credential_root).absolute()):
            raise ValueError('Separate private GitHub credential and master-key locations are required.')
        return self
    # This is a restricted synthetic staging opt-in, not real-use authorization.
    restricted_staging_enabled: bool = False
    require_mfa: bool = False
    auth_master_key_file: str = '.local/auth-master/master.key'

    db_host: str = "127.0.0.1"
    db_port: int = Field(default=5432, ge=1, le=65535)
    db_name: str = "contribution_ledger"
    db_user: str = "contribution_ledger"
    db_password: SecretStr
    allowed_hosts: list[str] = ["localhost", "127.0.0.1", "[::1]", "api"]

    allowed_origins: list[str] = ["http://127.0.0.1:5173", "http://localhost:5173"]
    secure_cookies: bool = False
    session_absolute_minutes: int = Field(default=480, ge=15, le=1440)
    session_idle_minutes: int = Field(default=30, ge=5, le=120)
    login_account_limit: int = Field(default=10, ge=3, le=30)
    login_peer_limit: int = Field(default=100, ge=10, le=500)

    ai_deployment_mode: Literal['disabled', 'customer_controlled'] = 'disabled'
    ai_live_enabled: bool = False
    ai_paid_probes_enabled: bool = False
    ai_evidence_enabled: bool = False
    ai_permitted_providers: list[Literal['openai', 'anthropic', 'gemini']] = []
    ai_credential_root: str = '.local/ai-credentials'
    ai_master_key_file: str = '.local/ai-master/master.key'

    @model_validator(mode='after')
    def ai_policy(self):
        if self.ai_live_enabled and (self.ai_deployment_mode != 'customer_controlled' or not self.ai_permitted_providers):
            raise ValueError('Live AI requires a customer-controlled deployment and explicitly permitted providers.')
        if self.ai_paid_probes_enabled and not self.ai_live_enabled:
            raise ValueError('Paid probes require explicitly enabled live AI.')
        if self.ai_evidence_enabled and not (self.ai_live_enabled and self.ai_paid_probes_enabled):
            raise ValueError('Live evidence disclosure requires explicitly enabled live generation.')
        if not self.ai_credential_root.strip() or not self.ai_master_key_file.strip():
            raise ValueError('Separate credential and master-key locations are required.')
        from pathlib import Path
        if Path(self.ai_master_key_file).absolute().is_relative_to(Path(self.ai_credential_root).absolute()):
            raise ValueError('The master key must be outside the encrypted credential directory.')
        return self

    github_enabled: bool = False
    github_app_id: int = Field(default=0, ge=0, le=2**53-1)
    github_client_id: str = ''
    github_callback_url: str = 'http://127.0.0.1:5173/github/callback'
    github_secret_root: str = '.local/secrets'
    github_authorization_hours: int = Field(default=24, ge=1, le=24)
    github_webhook_enabled: bool = False
    github_sync_enabled: bool = False
    github_webhook_receipt_limit: int = Field(default=100000, ge=100, le=1000000)
    github_project_run_limit: int = Field(default=10000, ge=500, le=100000)
    jobs_broker_url: SecretStr = SecretStr('redis://redis:6379/0')

    @model_validator(mode='after')
    def job_policy(self):
        from urllib.parse import urlsplit
        if (self.github_webhook_enabled or self.github_sync_enabled) and not self.github_enabled:
            raise ValueError('GitHub must be configured before enabling signed intake or synchronization.')
        broker = urlsplit(self.jobs_broker_url.get_secret_value())
        if broker.scheme not in {'redis','rediss'} or not broker.hostname or broker.query or broker.fragment:
            raise ValueError('Use an operator-controlled Redis broker URL, never an arbitrary task service.')
        return self

    github_project_quota_bytes: int = Field(default=134217728, ge=1048576, le=536870912)

    @model_validator(mode='after')
    def github_policy(self):
        if self.github_enabled:
            import re
            from urllib.parse import urlsplit
            p = urlsplit(self.github_callback_url)
            if not self.github_app_id or not re.fullmatch(r'[A-Za-z0-9_.-]{3,100}', self.github_client_id):
                raise ValueError('GitHub App ID and client ID must be explicitly configured.')
            if (p.username or p.password or p.query or p.fragment or p.path != '/github/callback'
                or f'{p.scheme}://{p.netloc}' not in self.allowed_origins):
                raise ValueError('The GitHub callback must be the configured application origin and /github/callback path.')
            if not self.github_secret_root.strip():
                raise ValueError('A protected GitHub secret mount is required.')
        return self

    object_storage_backend: Literal['local', 's3'] = 'local'
    object_storage_root: str = '.local/evidence'
    evidence_workspace_quota_bytes: int = Field(default=268435456, ge=10485760, le=1073741824)
    s3_bucket: str = ''
    s3_region: str = 'us-east-1'
    s3_endpoint: str | None = None
    s3_prefix: str = 'evidence-v1'

    @model_validator(mode='after')
    def storage_policy(self):
        if not self.object_storage_root.strip():
            raise ValueError('An explicit private object-storage directory is required.')
        if self.object_storage_backend == 's3' and not self.s3_bucket:
            raise ValueError('An operator-configured private S3 bucket is required.')
        if self.s3_endpoint:
            from urllib.parse import urlsplit
            parsed = urlsplit(self.s3_endpoint)
            if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
                or parsed.path not in {'', '/'} or parsed.query or parsed.fragment):
                raise ValueError('An S3-compatible endpoint must be an HTTPS origin without credentials or paths.')
        return self

    @field_validator("allowed_origins")
    @classmethod
    def explicit_origins(cls, value: list[str]) -> list[str]:
        from urllib.parse import urlsplit
        if not value:
            raise ValueError("At least one explicit browser origin is required.")
        for origin in value:
            parsed = urlsplit(origin)
            if (parsed.scheme not in {"http", "https"} or not parsed.hostname
                or parsed.username or parsed.password or parsed.path or parsed.query
                or parsed.fragment or "*" in origin or parsed.netloc.endswith(":")):
                raise ValueError("Use exact HTTP(S) origins, without paths or wildcards.")
            try:
                parsed.port
            except ValueError:
                raise ValueError("Origin contains an invalid port.") from None
        return value

    @model_validator(mode="after")
    def cookie_policy(self):
        if self.session_idle_minutes > self.session_absolute_minutes:
            raise ValueError("Idle timeout must not exceed the absolute timeout.")
        if self.environment in {"staging", "production"} and (
            not self.secure_cookies or any(not origin.startswith("https://") for origin in self.allowed_origins)
        ):
            raise ValueError("Remote environments require HTTPS origins and secure cookies.")
        return self

    @property
    def session_cookie_name(self) -> str:
        if self.desktop_enabled:
            return "__Host-cl_desktop_session" if self.secure_cookies else "cl_desktop_session"
        return "__Host-cl_session" if self.secure_cookies else "cl_session"

    @field_validator("db_name", "db_user")
    @classmethod
    def database_identifiers(cls, value: str) -> str:
        # The restriction also keeps shell/Compose setup unambiguous.
        import re
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,62}", value):
            raise ValueError("Use lowercase letters, digits and underscores; start with a letter.")
        return value

    @field_validator("db_password")
    @classmethod
    def non_placeholder_password(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value()) < 16 or value.get_secret_value().startswith("REPLACE_"):
            raise ValueError("Generate a local database password using the initialization script.")
        return value

    @field_validator("allowed_hosts")
    @classmethod
    def no_wildcard_hosts(cls, value: list[str]) -> list[str]:
        if not value or any("*" in host or not host for host in value):
            raise ValueError("Explicit allowed hosts are required; wildcards are not accepted.")
        return value

    def database_url(self) -> URL:
        return URL.create(
            "postgresql+psycopg", username=self.db_user,
            password=self.db_password.get_secret_value(), host=self.db_host,
            port=self.db_port, database=self.db_name,
        )

    def require_local_foundation(self) -> None:
        if self.environment in {"development", "test"}:
            return
        if self.environment == "staging" and self.restricted_staging_enabled:
            if (not self.require_mfa or self.enable_development_tools or not self.secure_cookies
                or len(self.allowed_origins)!=1 or not self.allowed_origins[0].startswith("https://")):
                raise ValueError("Restricted staging requires MFA and disabled development tools.")
            if self.github_enabled or self.ai_live_enabled or self.ai_deployment_mode != "disabled":
                raise ValueError("Initial restricted staging is manual-only; external integrations remain disabled.")
            return
        raise ValueError("This remains a local pilot unless restricted synthetic staging is explicitly configured; production is blocked.")

    def require_development_tools(self) -> None:
        if self.environment != "development" or not self.enable_development_tools:
            raise PermissionError("Development tools require development mode and explicit enablement.")


@lru_cache
def get_settings() -> Settings:
    return Settings()
