"""Interfaces only. Durable PostgreSQL outbox and workers are implemented in phases 8–9."""
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True)
class JobRequest:
    job_id: UUID
    workspace_id: UUID
    kind: str
    reference_ids: tuple[UUID, ...]
    idempotency_key: str


class TransactionalOutbox(Protocol):
    def add_in_transaction(self, request: JobRequest) -> None:
        """Persist with the caller's transaction, never publish secrets or source blobs."""
        ...


class JobDispatcher(Protocol):
    def dispatch(self, job_id: UUID) -> None:
        """At-least-once dispatch; a handler must enforce idempotent effects."""
        ...
