# ADR 0002 — Phase 1 foundation

Date: September 13, 2026
Status: Implemented in source; clean-install and complete-stack verification pending.

## Decisions

Use the planned modular FastAPI/PostgreSQL backend and React/TypeScript/Vite frontend. Pin versions in committed files; see dependency verification for provenance and remaining limitations. Keep web/API/PostgreSQL as the only active services. Storage and durable-job/outbox contracts exist but implementations wait for their planned phases.

Use an application factory with explicit validated settings, no implicit application `.env` loading, and no startup mutations. Expose separate liveness and readiness endpoints. Readiness verifies connectivity, the Alembic revision and the marker table; it never repairs schemas. Operator migrations run as a separate explicit step with a PostgreSQL advisory transaction lock. Alembic and the synthetic marker are the only schema objects introduced.

Use a minimal dependency-free Node static server for the built frontend and a read-only same-origin API proxy. This avoids adding a reverse-proxy package to the initial deployment. Backend and frontend validate hostnames. The containers use non-root application users, read-only root filesystems and loopback-only published ports. PostgreSQL remains internal. These controls are not authentication or a security audit.

The only mutation in phase 1 is a command-line synthetic marker. Seed is idempotent. Reset requires explicit development mode, enabled development tools and an exact confirmation. It deletes no schema or unrelated rows. Keep local SQLAlchemy SQLite fixtures for fast unit tests while requiring a separate actual PostgreSQL suite for database acceptance.

## Runtime baseline

Python 3.13.5; Node 22.16.0; PostgreSQL 17.7 image reference; FastAPI 0.128.2; SQLAlchemy 2.0.50; Alembic 1.18.4; psycopg 3.3.3; React/React DOM 19.3.0; Vite 8.3.0; TypeScript 5.8.3. No silent runtime updates are authorized by this record.

## Known limits and handoff

No production/staging use, accounts, workspaces, contributions, GitHub, AI, artifact uploads, worker execution, or financial operations. No real hosted provider credentials exist. Initial `.env` database credentials are protected by the operator's filesystem and excluded from deliveries, not encrypted by an application secret store.

The React interface is implemented but was not rendered from an installed build here. PostgreSQL, Docker, PowerShell, full TypeScript checking and dependency artifact installation await a capable environment. Continue with P02A only while preserving those verification gaps as open items; do not mark them passed merely to advance feature development.
