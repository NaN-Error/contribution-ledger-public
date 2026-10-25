# ADR 0011 — AI connections, encrypted credentials, and bounded probes

Date: September 14, 2026. Source: 0.10.0-phase10. Status: implemented in source; native/build/browser/live/security acceptance remains open. Supersedes no applied migration or contribution policy.

## Decision

Implement P10A/P10B/P10C as a provider foundation, not evidence evaluation. OpenAI, Anthropic and Gemini have independent adapters behind one bounded text/JSON contract; a deterministic synthetic provider implements the same contract without network or cost. Discovery is per connection. A model listing is neither an entitlement to use that model nor evidence of quality or fairness.

Do not add new SDK dependencies. Use the already-pinned cryptography dependency for AES-256-GCM and standard-library HTTPS for three fixed origins. Provider-specific authentication and request formats are explicit. No redirects, caller-controlled origins, external tools, arbitrary prompts, repository execution, raw reasoning capture, or automatic POST retries are allowed.

Only a single fixed synthetic JSON probe can generate text in phase 10. The submitted request cannot contain project source. Generation needs operator-enabled customer-controlled access, an allowed provider, an authorized payer, a reviewed price, a fresh quote, an atomic reservation, and explicit confirmation. The synthetic provider needs no live-provider flags or key but still exercises the quote/approval workflow. Evidence packets and real evaluation remain P11.

## Separate authorities

A connection has an owner who is also its payer. Its owner chooses whether project administrators/reviewers may inspect it for project use. A project administrator cannot spend another person's key simply because they hold a project role. Current participant access is rechecked before dispatch and completion. The owner or a project administrator can revoke a scoped connection; the administrator cannot retrieve its key. A profile approval is a separate project-management action and requires shared permitted access. No profile grants a right to send future project data by itself.

Store credentials encrypted outside the database. The master key lives in a separate operator-controlled mount; authenticated context binds each ciphertext to workspace, project, connection and provider. The database contains an opaque reference only. The backend never returns a credential or a partial key hint. Generation jobs contain scoped identifiers and frozen non-secret metadata. Master-key backup and provider-key rotation are distinct operations.

Rejected create/rotate operations remove newly written ciphertexts when failure is known before the database commit attempt. A process death or ambiguous commit can leave an encrypted orphan. Retain it for deliberate recovery rather than deleting potentially committed credentials. There is no automatic orphan collector in this phase. Revoke/rotate fence the database generation first, then attempt old-ciphertext deletion. External copies, old backups and already dispatched requests cannot be recalled.

## Job architecture amendment

The phase-9 outbox is explicitly foreign-keyed to GitHubImport. Do not abuse it with AI identifiers. Add an isolated PostgreSQL-owned AI job table and optional polling worker with transactional workspace locking, leases, bounded maintenance, and exact reservations. This is a deliberate interim modular-monolith decision, not a claim that AI uses Celery. Existing GitHub Celery/Redis transport remains unchanged. A future generalized transport can carry these AI IDs without changing their database authority or introducing paid retries.

Catalog reads retry at most three times for eligible transient failures, preserve the last complete successful catalog, and share a connection cooldown. Catalog creation, manual refresh and approximately daily refresh use the same job path while the deployment runs. A successful capture is bounded to 2,000 models and twenty provider pages; retained model history is bounded to 5,000 IDs. Exceeding those limits reports an incomplete capture without replacing the previous catalog.

A probe is marked dispatched before networking. A crash after that boundary becomes possibly billed, not silently retried. Lease expiry is 1,800 seconds; a running network request normally has much shorter transport deadlines. The scope/lease/generation is rechecked after networking. Revocation after dispatch suppresses qualification while preserving known or uncertain cost. PostgreSQL race tests exist but were not executed in the development container.

## Accounting and profiles

Internal API cost units are integer micro-US dollars, separate from contribution atoms and simulator cents. UTC calendar-month buckets are per connection, not project-wide or provider-account-wide. Prices are explicit immutable reviews with provider-source references and expiration no more than 31 days ahead. Unknown or expired prices block paid probes. Two-stage ceiling arithmetic conservatively reserves for 2,048 input and 256 output tokens, but is not a provider invoice guarantee.

Unknown billing retains the reservation; the payer can record a one-time reasoned reconciliation against an external billing reference. Returned usage can exceed a reservation; never hide the overage to make the local cap look effective. Up to five held/uncertain probes per connection are permitted, including ambiguous terminal jobs. Existing key usage elsewhere, taxes, special tiers and pricing mistakes are outside this local cap.

An approved profile preserves the requested model ID, provider, connection generation, model metadata fingerprint, successful synthetic probe, adapter/version/settings and data-policy reference. Approval requires a recent catalog (48 hours) and successful matching probe (seven days). Failed authentication/access/incompatibility can invalidate that qualification. Catalog changes do not approve, replace or delete profiles. Provider-side aliases can still change without a local configuration change. P10 profiles explicitly contain pending P11 prompt/schema/rubric identifiers and are not runnable evidence evaluators.

## Least-privilege boundary

The optional worker has a dedicated PostgreSQL role and only its required AI state plus restricted authorization reference reads. It has no evidence mount, GitHub credentials, contribution-event/financial grants, account write authority or profile-approval authority. A narrow SECURITY DEFINER workspace-lock function replaces the need to grant workspace UPDATE; its search path is fixed and PUBLIC execution revoked. The provisioning tool refuses an unrelated privileged role and checks effective table/column privileges. These native role grants have not been provisioned or verified here. The default API still uses the operator-owned database account; comprehensive deployment hardening remains P14.

## External references checked September 14, 2026

- OpenAI models: https://developers.openai.com/api/reference/resources/models/methods/list/
- OpenAI structured output: https://developers.openai.com/api/docs/guides/structured-outputs/
- Anthropic model list: https://platform.claude.com/docs/en/api/models/list
- Anthropic messages: https://platform.claude.com/docs/en/api/messages/create
- Gemini models: https://ai.google.dev/api/models
- Gemini generation: https://ai.google.dev/api/generate-content
- AES-GCM primitive: https://cryptography.io/en/latest/hazmat/primitives/aead/
- PostgreSQL revoke/column privileges: https://www.postgresql.org/docs/current/sql-revoke.html
- OpenAI services agreement: https://openai.com/policies/services-agreement/
- Gemini terms: https://ai.google.dev/gemini-api/terms

These references support API/security choices, not a blanket authorization for hosted BYOK, employment decisions, confidential-data sharing or real compensation. Recheck provider terms and actual account access before an authorized live test. No current model price or model name is silently hardcoded as a recommended live evaluator.
