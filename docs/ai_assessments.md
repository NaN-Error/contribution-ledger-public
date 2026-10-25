# AI-assisted evidence review

Phase 11 is optional. The manual review, contribution ledger and hypothetical revenue simulator work without an AI connection. This feature summarizes a bounded evidence packet; it does not measure objective worth, prove code correctness, select recipients, approve work, or pay anyone.

## Start with the no-cost synthetic provider

Use a local synthetic project. Read `upgrade_phase11.md` and `ai_connections.md`. Start the optional AI worker deliberately; normal startup remains manual-only. No API key is needed for the mock connection.

In **AI settings**, complete the existing discovery → explicit zero-price review → synthetic compatibility probe. After it succeeds, create and approve a **new evidence-review profile**, with a chosen output cap. The new UI creates evidence-review profiles. Existing phase-10 protocol-only profiles remain unchanged and are rejected for evidence runs; they cannot silently gain new authority. A compatibility probe is not a model-quality evaluation.

Create a work package, approve its scope, attach evidence, and submit it using the existing workflow. Select one unaccepted deliverable in **Work packages → AI-assisted evidence review**. Administrators and reviewers can inspect this area. Contributors do not receive general access to restricted review packets just because they contributed work.

The synthetic adapter deliberately returns `insufficient` for every criterion. It is a deterministic workflow fixture, not a model that evaluates the work. A real, authorized provider can return supported, contradicted or insufficient findings under the same validator; live execution has not been tested in this delivery.

## Packet preparation does not disclose anything

Choose the frozen profile, deliverable, evidence selection, additional repository-path exclusions, and a reason. Restricted evidence is excluded unless explicitly selected for inclusion by an authorized reviewer. No selection means all eligible entries, not no evidence. The exact submitted scope and evidence snapshot must still be current.

The initial extractor includes local contributor statements, bounded UTF-8 artifacts, descriptions of external links, and selected changes or text from explicitly pinned GitHub source versions. Statements and reported checks remain claims, not independently established facts. An external link's description is not its contents. The application does not fetch that URL, walk a repository, execute code/tests, decode game assets, inspect image pixels, or perform OCR. Raw images and unsupported files remain available through the original human-review interface but are omitted from the model input.

Limits: 24 source excerpts; 24,000 bytes of ASCII-encoded outbound JSON; each excerpt at most 120 lines / 6,000 UTF-8 bytes, with a 1,000-byte per-line ceiling. At most 12 file changes from a pinned source are considered. Overlong lines are omitted as whole lines rather than silently truncated. Limits and selection/exclusion reasons are counted in the packet. Oversized criteria cause an explicit error. The pilot caps packets at 2,000 per project.

Default repository exclusions cover environment files, secrets/credentials/private keys, .git, dependency directories/locks, payroll and similar paths. Additional glob patterns are available. Recognized keys, token assignments, emails, URLs and account identifiers are redacted; known contributor labels are replaced with package-local aliases. Structured budgets, revenue shares, contribution weights, salaries and activity scores are not included.

**Pattern redaction is not exhaustive.** A person's name or confidential information can still appear in arbitrary prose or code. Inspect the full exact payload before approving disclosure. Exclusion patterns do not constitute a guarantee against all possible private information. To change an immutable packet, revise the source/selection and prepare another packet.

The packet's local capture separately preserves the original scope/submission/evidence fingerprints, source revision mapping, criterion mapping and account-to-alias mapping. Those local provenance fields are not sent to the provider. Citation line numbers refer to the displayed redacted packet, not necessarily the original file's line numbers.

## Two separate approvals

1. Create a plan for an official-profile run or an advisory comparison. Official runs must use the currently approved project evidence profile. Advisory runs do not replace it. Each new run for the same deliverable and mode links the latest visible predecessor, even if a new packet was prepared. The reason and previous run remain recorded.
2. A current project administrator inspects the payload and explicitly approves disclosure to the named provider under an entered permission/data-handling reference. The grant is specific to one plan and expires within 24 hours. This records the administrator's declaration; it is not a legal conclusion or provider authorization.
3. The connection owner/payer, who must also currently have reviewer/administrator access to inspect this packet, reviews a current price quotation and explicitly approves one reservation/request. Project administration alone cannot spend another person's key.

Preparing, planning and granting disclosure do not call a model. Only the final payer-approved request enters the queue. The worker rechecks sharing, current roles, credential generation, model/probe/profile state, price validity, exact evidence freshness, grant expiry and revocation before dispatch and after receiving a response. The current operator live flags must also permit it.

A pending or revoked plan cannot be renewed in place. Create a reasoned successor under the latest current evidence/profile. Advisory run details are visible to their requester, payer and project administrators; they are not private from administrators. Authorized reviewers can inspect official runs. Preparing a packet itself is a project reviewer/admin action, not an individually secret notebook.

## Live evidence remains separately disabled

Defaults retain `CL_AI_LIVE_ENABLED=false`, `CL_AI_PAID_PROBES_ENABLED=false` and the new `CL_AI_EVIDENCE_ENABLED=false`. The synthetic provider works with all three false. Enabling live catalogs/probes alone still cannot transmit project evidence. The new evidence flag requires both earlier live/paid settings; valid provider/data arrangements and the two per-run human approvals remain necessary. Do not paste API keys or actual confidential packets into chat for testing.

Providers receive separate fixed system instructions and the redacted packet as untrusted input, with a closed structured-output schema. No tools, browsing, external calls, arbitrary prompt field, repository execution, automatic model fallback, or credit/finance capabilities are exposed to the model.

## Inspecting a result

The result preserves the requested/returned model identifiers, provider request identifier when available, token usage, exact packet/profile/prompt/schema/rubric fingerprints, mode and synthetic flag. Each criterion must be represented once with a supported, contradicted or insufficient finding. Positive/contradictory findings require valid supplied source-line references. Role observations use only known aliases. Potential-overlap observations require at least two supplied sources and are limited to this packet, not a whole-project duplicate search.

Malformed JSON, duplicate keys, invented sources/lines/criteria/people, extra commands, truncated output and refusals cannot become valid findings or awards. Raw invalid output is discarded; bounded status/usage metadata remains. Valid source references prove only that those lines were supplied, **not that the interpretation is true**. The application does not record model hidden reasoning traces. Ordinary provider-job metadata contains result IDs and statuses, not packet text or assessment explanations.

Every visible run remains in history; a more favorable advisory result does not change the official profile. There is no cross-project output cache or automatic rerun. Archived results remain available when evidence changes, but are visibly stale for further review. New source uploads, revised submission or finalization cannot rewrite a stored response or prior contribution credit.

## Human observations are not acceptance

In an independent review round assigned to you, inspect original evidence beside the finding. An authorized independent reviewer can agree with the observation, record a modification, reject it, or request evidence, with a reason. These append commentary and preserve the model's original output. They do not prefill or submit the separate acceptance form, create ReviewDecision records, or award units. Current scope/submission/evidence, reviewer assignment, independence and criterion mapping are checked again.

The existing independent-review quorum and explicit finalization remain required. A human can accept work despite an `insufficient` synthetic result, or reject a model's `supported` result. AI availability is never a prerequisite for manual accounting. After a deliverable receives credit, its prior assessment remains historical and cannot initiate new credit.

## Spending and interrupted work

The byte-based input allowance is deliberately conservative, not provider-tokenizer accounting. A reviewed exact micro-USD reservation is created using the existing per-connection UTC-month allowance. Missing or expired prices, model limits and incompatible profiles block the request. Actual known usage is reconciled; unexpected costs remain visible. This does not guarantee a provider invoice cap or cover other account usage/taxes.

After durable dispatch, generation is never retried automatically. A timeout, lost worker or otherwise uncertain billing outcome retains the reservation until reasoned payer reconciliation. A response arriving after revocation cannot be retained as an authorized assessment; known usage may still be charged. No software operation can recall a request already delivered to the provider or delete their external records. Inspect existing AI job/accounting history before authorizing another run.

## Retention and operations

A packet is a **separate immutable redacted-text copy** in the database. Retiring the original uploaded bytes does not erase that copy, the earlier result, backups or provider copies. Decide acceptable data/retention scope before packet creation and disclosure. Do not promise that source retirement erases assessment history. General retention/export/deletion policy needs further security and operating review before real deployment.

The API prepares packets with current source permissions. The worker reads sealed packets and returns assessment records; its provided database grants do not authorize raw artifact/evidence reads, contribution awards, financial writes or account mutations. A narrow native boolean function checks freshness without exposing underlying records. Native grants, database-role operation, complete backup restoration, real providers and browser rendering remain unverified. The operator-owned API still requires the broader phase-14 privilege/security work.

Official rerun lineage is project-wide for each deliverable. Advisory lineage is per requester, so a private peer run cannot leak its identifier or block another reviewer. Administrators retain access to all advisory histories. Plan history supports `mine=true` to select the current requester.
