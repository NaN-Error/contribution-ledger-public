> **Phase-11 update:** For evidence assessments and current upgrade steps, read `ai_assessments.md` and `upgrade_phase11.md`. Old protocol-only profiles remain unchanged. New runs need separate disclosure/payer approvals, and existing AI worker grants must be refreshed. Current executed/deferred checks are in `test_results.json`.

# AI provider-foundation API

All routes are below `/api/v1/workspaces/{workspace_id}/projects/{project_id}/ai`. Existing authenticated session, current project membership, exact-origin/CSRF rules and sanitized error handling apply. IDs are opaque UUIDs and tenant/project scope is rechecked; a guessed ID is not authorization. Mutation schemas reject extra fields. Secrets must never appear in URLs.

## Connections and catalogs

| Method and suffix | Required role/authority | Result |
|---|---|---|
| GET empty suffix | Current project member | Visible connections, operator flags, profile pointer; private connections filtered |
| POST `/connections` | Current non-viewer creating their own payer connection | Connection plus queued catalog; no generation |
| PATCH `/connections/{connection}` | Owner; expected version | Reviewed label/cap/sharing change |
| POST `/connections/{connection}/rotate` | Owner; expected version | New encrypted key generation; old deletion status |
| POST `/connections/{connection}/revoke` | Owner or project admin; expected version | Disabled generation before best-effort ciphertext deletion |
| POST `/connections/{connection}/refresh` | Owner | Idempotent catalog job |
| GET `/connections/{connection}/models` | Owner, or shared project admin/reviewer | Stored catalog page, model UUID/remote ID, unknown/confirmed capabilities and probe state |
| GET `/connections/{connection}/events` | Same connection read scope | Immutable sanitized operation events |

Connection creation takes `request_id`, `provider` (`mock`, `openai`, `anthropic`, `gemini`), `label`, `permission_reference`, `reason`, exact integer `monthly_limit_microusd`, strict boolean `allow_project_use`, and a `SecretStr` API key only for live providers. The maximum cap is 1,000,000,000 micro-USD ($1,000) per connection. Request-id repetition must match the original non-secret intent; use rotation to change a key. A key is never returned or partially displayed.

Connection updates require `expected_version`; stale edits return a conflict. Sharing does not grant billing permission. Global account/provider support is not inferred from a model name. There are no arbitrary endpoints or provider-company creation routes.

## Pricing, quotes and jobs

| Method and suffix | Authority | Behavior |
|---|---|---|
| GET `/connections/{connection}/prices` | Connection read scope | Immutable price reviews, 50/page |
| POST `/connections/{connection}/prices` | Owner | `model_id`, integer `input_rate`, `output_rate`, official `source_reference`, aware `valid_until`, reason |
| GET `/connections/{connection}/models/{model}/probe-quote` | Owner | Non-generating quote with fixed prompt, exact reservation and fingerprint |
| POST `/connections/{connection}/models/{model}/probe` | Owner/payer | `request_id`, `quote_hash`, `confirmed_reservation_microusd`, literal boolean `payer_approved=true` |
| GET `/connections/{connection}/jobs` | Connection read scope | Captured status/usage/result summaries, 50/page |
| POST `/connections/{connection}/jobs/{job}/cancel` | Owner | Queued-only cancellation with reason; dispatched calls not cancellable |
| POST `/connections/{connection}/jobs/{job}/reconcile` | Owner | Terminal uncertain usage only; exact `actual_microusd`, external source reference, reason |
| GET `/connections/{connection}/usage` | Connection read scope | UTC month, held and estimated micro-USD, 24/page |

Rates are **micro-USD per one million tokens**, not cents, contribution units or cost per token. For example, a reviewed $2 per million input tokens is `input_rate=2000000`. The owner-facing interface converts decimal dollars exactly. This is a unit example, not a current provider price. The ceiling formula is `(tokens * rate + 999999) // 1000000`, separately for input and output. Quote output is bounded to 256 tokens; the reservation uses a 2,048-token input allowance.

Model/price scopes, current generation, current local authority, operator flags and quote fingerprint are checked at enqueue and dispatch. There are no request-body prompt or evidence fields. A repeated matching probe request ID returns its original job, not a second paid call. Different parameters using the same ID conflict.

Job states are `queued`, `running`, `succeeded`, `failed`, `ambiguous`, `cancelled`. These are distinct from accounting state (`held`, `uncertain`, settled/released states in the response). A failed protocol check can have a known charge, and a terminal result can retain unknown billing. Do not equate job failure with a refund. Reconciliation is immutable and idempotent for the same declaration; it does not claim automatic billing verification.

The body of the only generation prompt is synthetic. Provider response prose/hidden reasoning and raw error bodies are not retained. Successful compatible JSON is summarized as the protocol result with safe model/usage metadata. Refusals, truncated responses, unknown usage, denied access, timeouts and cooldowns remain distinct.

## Profiles

| Method and suffix | Authority | Behavior |
|---|---|---|
| GET `/profiles` | Current project member | Immutable drafts/approvals, newest first, 25/page; no key |
| POST `/profiles` | Project admin | Connection/model/title/data-policy reference/reason; needs shared authorized connection and current successful synthetic qualification |
| POST `/profiles/{profile}/approve` | Project admin | Reviewed definition hash, expected previous approved profile ID, reason |

Profile approval requires a catalog within 48 hours, a matching successful probe within seven days, current payer access/sharing, exact credential generation and approved model metadata. It never runs an AI. P10 definitions explicitly leave evidence prompt/schema/rubric identifiers pending P11. There is no profile overwrite or hidden fallback route. A last-approved profile can remain in history after its model becomes unavailable.

Most list routes accept a bounded integer `offset` and return `next_offset`; models also accept `limit` up to 200. The UI displays bounded recent history; the API supports the documented continuation. No HTML execution or secret-bearing provider URLs are returned.

## Failure interpretation

Normal errors use the existing sanitized API envelope, not provider error text or keys. Useful categories include authorization/not-found, stale version/fingerprint, disabled provider/deployment, incompatible model, incomplete catalog, unknown/expired price, insufficient cap, excessive outstanding jobs, rate limit, timeout, refusal, truncated or malformed output, and uncertain billing. Retry only a safe user action after inspecting current state. **Never blindly repeat an ambiguously billed generation request.** A new explicit probe is a new payer decision; the prior reservation must remain accounted for.
