# GitHub synchronization and recovery

Phase 9 local-development instructions. Read `upgrade_phase9.md` before replacing a running installation. This optional deployment has not been exercised under Docker/PowerShell or with a live authorized GitHub App here. The manual ledger remains usable without it. Never put keys, secrets or real source material into chat.

## 1. Normal operation is unchanged

`scripts/start.ps1` starts the manual application and stops optional integrations before migration. It does not connect GitHub or enable a repository schedule. Existing owners sign in normally. Read `github_setup.md` for App registration and the read-only selected-repository authorization flow. For an existing phase-8 connection, reauthorize if its finite authority has expired.

## 2. Prepare the optional deployment

With the source folder open in PowerShell, initialize private local values:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\sync.ps1 -Action init
```

Linux/macOS equivalent: `bash scripts/sync.sh init`.

The command generates a missing 64-character random Redis password in `.env` and a missing `github-webhook-secret` in `.local/github-secrets/`. Existing values are not overwritten. No secret is printed or sent anywhere. Protect these files using your operating-system account permissions; Windows ACL hardening is your responsibility. The Redis password is distinct from both the database password and the GitHub signing secret. Do not use `docker compose config` output or environment dumps as public troubleshooting attachments.

For periodic synchronization alone, no public webhook URL is necessary. Webhook intake remains disabled unless `.env` explicitly contains `CL_GITHUB_WEBHOOK_ENABLED=true`. To enable it, privately configure the App's webhook secret to exactly match the generated file, then provision all current files with the existing stopped-service command:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\github.ps1 -Action provision
```

This copies the private key, client secret and optional signing secret into the protected GitHub-secret volume. Runtime mounts are read-only. Omitting the optional signing file during a later two-file provision preserves any signing file already stored; it does not revoke or remove it. Disable intake explicitly before retiring that secret. The provisioner is local and network-disabled. It does not change App settings at GitHub. Secret rotation requires stopping API/worker/gateway consumers, updating both sides consistently and restarting. This version does not support a two-secret overlap window; arrange a controlled pause and use reconciliation for missed events.

## 3. Start explicitly

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\sync.ps1 -Action start
```

Shell equivalent: `bash scripts/sync.sh start`.

The script stops earlier optional workers and the API, builds the exact source images, applies additive migrations, and starts the API/web app plus Celery, Redis, the database-owned scheduler and a local webhook gateway. It does not expose a domain or make GitHub contact localhost. First-time image/dependency downloads require internet. The optional lock is a candidate until this clean build succeeds; retain its error output privately if it fails.

Open the app's GitHub tab, then **Synchronization → Repository schedules**. An administrator must explicitly review and enable each connected repository. Choose an interval (60 minutes to seven days), lookback (1–90 days), data-request cap and entity cap. Defaults are six hours, seven days, 200 requests and 50 entities. These settings are not a guarantee that an entire repository fits the limits. Saving a change fences that schedule's unfinished run. Granting a GitHub connection does not enable synchronization by itself.

The application checks authorizer identity/admin permission before and after each data fetch. This adds verification requests beyond the displayed data-request budget. App access and the local sharing grant must remain valid; the latter still expires after at most 24 hours. Reauthorize and explicitly enable a paused schedule when appropriate.

## 4. Optional reachable webhook route

For local status: `sync.ps1 -Action status`. Gateway is `http://127.0.0.1:8010/api/v1/github/webhook` by default. It accepts only the exact POST route, bounded JSON raw bytes and GitHub signature/delivery/event headers. It strips browser cookies, authorization and forwarding headers; it cannot proxy the UI or arbitrary API routes. Unsigned requests cannot trigger imports.

GitHub cannot deliver to your private loopback address. For an authorized remote fixture test, an operator must configure a reachable HTTPS endpoint that forwards **only that route** to the gateway. `infra/webhook-nginx.example.conf` illustrates a single-route TLS reverse proxy, not an installation script. Supply your own hostname/certificate and network routing; do not publish the main UI/API, Redis or PostgreSQL. Complete the relevant security review first. No tunnel, DNS record, hosting purchase or certificate is created by this project.

Configure the App's webhook URL as your approved HTTPS route, secret as the private signing value, and subscribe only to implemented necessary events: pull requests, issues/comments, reviews/review comments, pushes and check runs/suites, together with applicable installation/repository events. See `webhook_api.md` for the exact supported event/action set. Check the current GitHub App subscription UI; this code does not change subscriptions for you.

GitHub's documented delivery response window is ten seconds. Intake does no GitHub/broker network work, but overloaded/unavailable databases can still fail or time out. A successful 202 means a durable local receipt/routing intent, not completed import or accepted work. GitHub does not guarantee automatic redelivery of failures; inspect its delivery UI and explicitly redeliver where appropriate. Local reconciliation is the fallback for missed signals.

## 5. Observe and recover

**Jobs and retries** shows checkpoint progress, attempt count, lease/delay information and terminal errors. **Signed deliveries** shows verified receipt fingerprints and scoped processing outcomes, not raw payloads. **Latest observations** shows the latest locally observed source pointer and timestamp, including unavailable roots. Configurations show last completed bounded capture, last omission-free bounded run and errors. Neither is a guarantee of complete/current remote data. A worker heartbeat updates when it handles a task; an idle worker need not have a recent heartbeat.

Duplicate or out-of-order events request live authoritative reads rather than patching source from their bodies. The outbox is committed before broker publication; lost messages are republished. Kill/restart tests and broker recovery must still be exercised on native Docker/Redis/PostgreSQL. Jobs use leases and fences; expired or cancelled workers cannot commit stale responses. GitHub retry delays are shared per repository, including newly requested imports. A new request cannot bypass a cooldown. Five execution failures exhaust automatic processing; inspect the cause before explicitly starting new bounded work. Re-enabling a schedule is a reviewed decision, not an infinite hidden retry loop.

Received installation removal/suspension or repository-removal events disable/fence the affected imports. Grants do not reactivate anything. Missed permission events are checked during future requests, but instantaneous global revocation is not promised. Already sent remote requests cannot be recalled; captured data remains governed by current local access and retention.

Latest source changes do not replace evidence pins. Inspect the new version, then explicitly attach it to the package using the existing evidence workflow. That operation may make unfinished submissions stale. Existing awards, disputes and saved hypothetical examples are never recomputed by synchronization.

## 6. Pause, stop and preserve data

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\sync.ps1 -Action pause
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\sync.ps1 -Action manual
```

`pause` stops optional workers, broker and gateway without deleting configuration. `manual` also returns the API/web app to the base-only configuration. Per-repository disabling in the UI cancels its active synchronization and ignores pending signals; resumption requires explicit review. Normal startup/stop scripts now stop optional integrations as well, including the earlier phase-8 polling worker.

Preserve `.env`, `postgres_data`, `evidence_data`, `github_secrets`, and protected host key/recovery files. Redis is deliberately disposable; it is not the source of contribution, evidence, task or financial truth. A powered-off deployment performs no synchronization. Check overdue work when it starts again; do not assume activity continued while off.
