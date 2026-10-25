# ADR 0010 — signed hints, authoritative reconciliation and optional task transport

Date: September 14, 2026. Source implementation accepted for the local pilot; native/live acceptance remains open. Extends ADR 0009, not the economics policy.

## Decision

GitHub payloads are untrusted data until their exact bounded raw bytes pass the mounted-secret HMAC check. Even an authenticated event is only a routing hint. Store its identifier, body fingerprint, event/action, scoped target IDs and processing state, not its raw body, code or tokens. Signed revocations fence local jobs in the intake transaction. Grants never reactivate a disabled connection. Duplicate delivery IDs and repeated body hashes cannot create repeated effects; conflicting routing information is rejected.

Intake commits a durable `github_webhook_targets` intent before returning 202. A separate scheduler transaction consumes intents and creates the existing `github_imports`/`job_outbox` work atomically. This two-stage design removes broker/API network requests from intake while recovering crashes between receipt, job creation and publication. It is explicitly at-least-once, not exactly-once delivery.

PostgreSQL owns scope, due times, job states, checkpoints, cancellation, publication leases and worker fences. The optional Celery/Redis transport carries only a job UUID, workspace UUID and project UUID. No Celery Beat or result backend is used. Redis can lose every queued message; eligible database-owned work is republished. Worker hard time limit (160 seconds) is below the 180-second database claim lease, and the broker visibility interval is longer (240 seconds). Broker publication failure does not discard a job. Execution failures exhaust a five-failure cap and stop automatic processing; they do not silently restart forever.

Keep the phase-8 database-polling adapter as an explicitly selectable compatibility mode. New scripts stop it before enabling Celery. No two transports are intentionally started together, and shared database claims remain defensive against accidental overlap. Default startup stops optional integrations and remains manual-only.

## Authority and retention

Before and after each source fetch, verify the current installation plus the original authorizer's current repository-admin permission and numeric GitHub identity. A checked username alone is insufficient. Local user, connection, repository and lease versions are rechecked before commit. Signed installation removal/suspension, repository removal and specified repository changes disable connections or repositories, cancel in-flight commits and pause schedules. No received event can erase previously reviewed evidence or finalized credit.

This reduces the earlier phase-8 role-revocation gap, but cannot claim instantaneous observation of all external changes. A request may already have been sent when permissions change. The second check can still precede a later remote change by a small interval. Verified sharing authority still expires after at most 24 hours; reauthorization is required. Reauthorizing does not automatically reenable a paused schedule.

Captured source and explicit evidence pins are retained under the existing access/retention rules. A latest-observation pointer is not a legal truth or guaranteed current complete repository representation. New source versions produce a visible warning for older pins; only an explicit attachment changes evidence and triggers its normal stale-review rules.

## Reconciliation scope

Each explicitly enabled repository has an interval, lookback and finite request/entity budget. Defaults: six hours, seven days, 200 data requests, 50 entities. Reconciliation considers updated issues/PRs (not only their original creation dates), the current default-branch anchor, selected signed hints and a bounded round robin of previously captured older PR/issue roots. One active import per repository; existing historical imports block overlap. Missed events in the configured window or known-root pass can be repaired. This is not a complete all-branch scan or retroactive reconstruction of unknown old objects. Deleted child comments cannot always be independently tombstoned; omission and observation dates stay visible.

## Deployment choices

Optional packages are isolated in requirements-jobs.lock and a separate image. Candidate pins were checked against provider metadata but not clean-installed here. The added Redis server tag is 7.4.11-bookworm; no digest lock or native image validation is claimed. Existing runtime pins remain unchanged. Default credentials are still operator-owned; database-enforced worker/ledger role separation is a phase-14 gate, not a property claimed for this Compose file.

The gateway publishes only loopback port 8010 and forwards only the exact signed webhook POST path. A sample TLS reverse proxy can make that single route reachable on a separately authorized test host. It is not an automatic deployment, tunnel, domain registration or exposure of the UI. Redis has a separate password and no host port. Its internal state is disposable; preserve database, evidence and GitHub-secret volumes, plus private .env recovery material.

## References checked September 14, 2026

- GitHub: https://docs.github.com/en/webhooks/using-webhooks/validating-webhook-deliveries
- GitHub: https://docs.github.com/en/webhooks/using-webhooks/best-practices-for-using-webhooks
- GitHub: https://docs.github.com/en/rest/collaborators/collaborators#get-repository-permissions-for-a-user
- Celery: https://docs.celeryq.dev/en/stable/userguide/configuration.html
- Celery Redis: https://docs.celeryq.dev/en/stable/getting-started/backends-and-brokers/redis.html
- Package metadata: https://pypi.org/pypi/celery/5.6.3/json ; https://pypi.org/pypi/kombu/5.6.2/json ; https://pypi.org/pypi/redis/6.4.0/json
- Redis official image definitions: https://github.com/docker-library/official-images/blob/master/library/redis
- Official webhook schemas: https://github.com/octokit/webhooks/tree/main/payload-schemas/api.github.com
