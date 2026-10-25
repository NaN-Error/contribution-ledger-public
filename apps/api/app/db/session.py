from functools import cached_property
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker
from app.core.config import Settings


class Database:
    """Runtime is PostgreSQL only; an injected engine supports isolated unit tests."""
    def __init__(self, settings: Settings, engine: Engine | None = None) -> None:
        # Operators and workers start independently of FastAPI and Alembic.
        # Register the complete graph before any ORM flush resolves foreign keys.
        # This imports table definitions only; it neither connects nor migrates.
        from app.db import models  # noqa: F401
        self.settings = settings
        self._provided_engine = engine

    @cached_property
    def engine(self) -> Engine:
        if self._provided_engine is not None:
            return self._provided_engine
        return create_engine(self.settings.database_url(), pool_pre_ping=True,
            pool_size=5, max_overflow=5, pool_timeout=3,
            connect_args={"connect_timeout": 3, "options": "-c statement_timeout=3000"},
            hide_parameters=True)

    def session(self) -> Session:
        return sessionmaker(bind=self.engine, expire_on_commit=False)()

    def dispose(self) -> None:
        if "engine" in self.__dict__:
            self.engine.dispose()
