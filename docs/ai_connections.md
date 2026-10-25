> **Phase-11 update:** For evidence assessments and current upgrade steps, read `ai_assessments.md` and `upgrade_phase11.md`. Old protocol-only profiles remain unchanged. New runs need separate disclosure/payer approvals, and existing AI worker grants must be refreshed. Current executed/deferred checks are in `test_results.json`.

# AI connections and model discovery

Phase 10 implements connections, catalog discovery, one fixed synthetic compatibility probe, cost controls and profile configuration. **It does not send work-package evidence to an AI or evaluate contributions.** The manual application continues to work without an AI key.

## Start with the no-cost provider

Use a fresh or upgraded local synthetic-development installation. Complete the existing owner setup only for a genuinely new database. Sign in normally on an existing installation. Read `upgrade_phase10.md` before replacing a running version.

From PowerShell inside `contribution-ledger/`, first run normal setup/start if this is a fresh extraction. Docker Desktop must be using Linux containers. Then run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\ai.ps1 -Action init
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\ai.ps1 -Action start
```

`init` generates a separate AI worker database password in the private `.env` only when absent, runs migrations, initializes the two AI storage volumes and provisions the restricted worker role. It stops optional workers and the API first. It never contacts an AI provider and never replaces an existing master key. If initialization stops on a privilege/storage error, inspect it locally; do not delete the database or master volume to make the error disappear. Successful initialization must be followed by `start` to restore the AI-enabled API.

`start` is explicit opt-in to the local AI worker. Default settings allow **only the synthetic provider**. It does not enable paid calls. The first image build needs internet downloads; clean-install, Docker and Windows acceptance remain unverified in this delivery.

Open `http://127.0.0.1:5173`, sign in, select a project and open **AI settings**. Create a connection using provider `mock`, a clear synthetic label, the non-secret permission/payer reference, a reason, and a zero-dollar monthly cap. Leave the API-key field empty. An ordinary viewer cannot create a connection.

Choose project sharing only when the project administrators/reviewers should inspect this connection and use it for profile configuration. Sharing does not let them charge your key. A private connection will not qualify for an official project profile.

Creating the connection queues a catalog read. The separate worker processes it; **Refresh status** and **Reload captured catalog** show its actual result. The synthetic model is `synthetic-json-v1`. If a job stays queued, check the worker rather than assuming discovery succeeded.

Select that model, open **Add a reviewed price version**, and save its zero input/output rates with a synthetic-source reference, expiration and reason. The fake provider is the only provider allowed a zero-rate review in this release. Preparing a quotation does not generate text. Inspect its exact fixed prompt and zero reservation, then choose **I approve this reservation and one synthetic probe**. The worker should finish it once and report a successful JSON protocol check. No provider is contacted.

After a passing probe, a project administrator can create a profile draft, review its complete pinned definition, data-policy reference and reason, then explicitly approve it. The interface labels the newest approval **last approved configuration**. It is not a contribution assessment. Refreshing the catalog or selecting a different model does not change the approved version. Phase 11 will add the evidence packet, rubric, assessment schema and reviewer experience.

## Three live adapters, disabled by default

OpenAI, Anthropic and Gemini adapters are present. A catalog is keyed to a particular authorized connection; the program cannot promise a globally exhaustive list of every company's models or your account's quotas. Adding a new provider company requires a reviewed adapter, not just catalog refresh.

Before live use, the operator and payer must establish that their own account, deployment and data use are permitted. This source supports only a deliberately configured customer-controlled deployment; there is no hosted-BYOK permission switch. Do not paste API keys into chat, screenshots, Git, support logs or ordinary project documents. Use API credentials, not consumer account passwords or browser-session tokens.

Edit the private local `.env` on the host, preserving all existing settings. Enable only approved providers, for example:

```dotenv
CL_AI_DEPLOYMENT_MODE=customer_controlled
CL_AI_LIVE_ENABLED=true
CL_AI_PERMITTED_PROVIDERS=["openai","anthropic","gemini"]
CL_AI_PAID_PROBES_ENABLED=false
```

Then restart with `scripts/ai.ps1 -Action start`. This allows permitted credential setup and model-list requests, **not generation**. Connecting a live provider transmits its key to the operator-controlled local backend over the local application connection. The backend encrypts it before storing it. There is no remote/public secure deployment implied by this local setup.

The key field is cleared in the interface and is never returned by the API. The key owner remains the payer. The data-policy and permission-reference fields must contain non-secret agreement references; they are not secret storage or legal validation.

For a separately authorized, potentially billable compatibility test, set `CL_AI_PAID_PROBES_ENABLED=true`, restart the explicitly enabled worker/API, review a current model-specific price, prepare the quote and approve that **one** probe. Do not enable this merely to explore the UI. The code has no automatic paid test, nightly generation, arbitrary prompt field or contribution-scoring endpoint in phase 10.

## Prices and spending

Model catalogs are not price lists. The owner records input/output USD prices per one million tokens, an official provider-source URL and a review reason. The source is a reference, not automatically fetched or guaranteed correct. Reviews expire within 31 days. Unknown/expired prices block generation; credentials and model IDs are never sent to a price lookup service.

Quotes reserve an exact number of micro-US dollars (one dollar = 1,000,000 micro-US dollars) using 2,048 input tokens and at most 256 output tokens. This is a conservative allowance for the fixed small probe, not exact tokenizer metering or an invoice ceiling. The UI requires review of a fresh quote and explicit payer confirmation. A changed key, price, catalog, adapter, month or model can invalidate a queued quote.

The monthly cap is per connection and UTC month. It covers tracked estimates plus held/uncertain amounts. It is **not** a global cap for the provider account, project, duplicate keys, taxes, special tiers or unrelated applications. A reported charge above the reservation is recorded rather than clipped. Unknown pricing components stay uncertain.

When a request may have been billed, its reservation stays held. It is not automatically sent again. Check the provider's billing independently; the owner can record one reasoned reconciliation with the observed amount and external reference. That is a payer declaration, not an automatically verified invoice. Do not enter zero simply to release the cap.

## Sharing, rotation and revocation

The owner can change the cap/sharing, rotate a live key, or revoke the connection. Administrators may perform scoped emergency revocation through the API but cannot spend or retrieve another owner's key. A removed owner or revoked generation stops newly eligible jobs. A sent network request may still be billed.

Rotation stores a new encrypted credential and increments the connection generation. Recheck its catalog and probe, then approve a successor profile as appropriate. Old profile/operation records remain preserved. Revocation fences access before attempting ciphertext deletion. The returned result distinguishes deletion failure; revoke the provider-side key separately. Neither operation deletes provider logs, backups or copies outside this deployment.

## Other operations

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\ai.ps1 -Action status
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\ai.ps1 -Action logs
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\ai.ps1 -Action pause
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\ai.ps1 -Action manual
```

`pause` deliberately stops all labeled optional integration workers, including GitHub, to fence upgrades consistently. `manual` also restores the normal manual-only API/web configuration without deleting data. While workers are stopped, queued work is not processed and no daily refresh occurs. Expired dispatched probes are marked uncertain when recovery runs, not retried.

To run already-configured GitHub synchronization and AI together, use `-WithGitHubSync` with the AI start command; follow the GitHub setup first. Do not alternate separate overlay start commands and assume both configurations remain active. Shell equivalents are `bash scripts/ai.sh init`, `start`, `status`, `logs`, `pause`, `manual`, with `--with-github-sync` as the second argument when needed.

Read `ai_operations.md` for separate master/ciphertext backups, worker privileges, bounded jobs, and recovery. Existing localhost-only/synthetic-use restrictions remain. An API key is not required to test the fake workflow.
