# ADR 0012 — Sealed evidence assessments with separate disclosure and spending

Date: 2026-09-14. Status: implemented in source; native/live/browser/security verification open. Supersedes no earlier accepted-credit or financial rule.

## Decision

Extend the phase-10 scoped AI queue rather than introducing a second generation dispatcher or using GitHub-specific job IDs. A new immutable plan binds a concrete evidence profile and packet; a scoped AI job must reference that plan. The API prepares selected redacted text using existing evidence access. A distinct administrator disclosure grant and connection-owner spending approval are required. Official plans must match the current approved profile; advisory runs never change it. Existing protocol-only profiles remain unchanged.

The worker can access sealed records and a boolean freshness function but cannot fetch original artifacts, browse repositories, approve reviews or issue contribution/financial records. Dispatch is committed before generation. Ambiguous outcomes retain held estimates and are never automatically regenerated. The same service checks current authorization both sides of the network call.

Output is a closed evidence schema with real criterion/source/line IDs, unknown evidence expressed as insufficient, and no compensation score. Validation rejects unsupported identifiers and extra commands but cannot establish that an interpretation is true. Reviewer commentary preserves disagreements separately from the existing independent acceptance quorum and finalization.

## Boundaries and tradeoffs

Text-only packets keep outgoing data inspectable; images and external links are explicit omissions. This sacrifices visual assessment and broad architecture context. Best-effort redaction can miss private prose; human exact-payload review is mandatory. Text packets/results are separate retained copies and are not erased by retirement of original artifacts.

A payer must have current reviewer/admin access to inspect the packet. Advisory plans are private from ordinary reviewers, not from project administrators. Reruns link the latest same-deliverable/mode plan across packet/profile changes; no automatic cache or favorable-result replacement. All prior runs remain preserved. Immediate global revocation and guaranteed invoice caps are impossible to infer from an already-dispatched request; late unauthorized responses are discarded while known costs remain accountable.

Schema/pricing/live compatibility remains subject to current provider behavior and controlled testing. No live response, model-quality benchmark, security audit, PostgreSQL role or deployed worker recovery was verified in this delivery. Phase 15 will measure evaluator usefulness; syntax/schema validity is not fairness.

## Migration and verification

0011 adds six sealed history tables and a scoped link in ai_jobs. No applied migration changes. Its SQLite test branch explicitly starts a real DDL transaction before rebuilding a referenced populated parent, keeps foreign keys enabled, checks all foreign keys, then clears the verified rebuild deferral. PostgreSQL uses native ALTER TABLE. A boolean SECURITY DEFINER function has a fixed search path and revoked public execution; privileged operator initialization grants only the intended worker. Populated history prevents destructive downgrade.

References used while implementing protocol boundaries (not live tests):

- OpenAI structured outputs: https://developers.openai.com/api/docs/guides/structured-outputs
- Anthropic structured outputs: https://platform.claude.com/docs/en/build-with-claude/structured-outputs
- Gemini structured outputs: https://ai.google.dev/gemini-api/docs/structured-output
- OWASP prompt injection prevention: https://cheatsheetseries.owasp.org/cheatsheets/LLM_Prompt_Injection_Prevention_Cheat_Sheet.html
- SQLAlchemy SQLite transaction mode: https://docs.sqlalchemy.org/20/dialects/sqlite.html
- SQLite deferred foreign keys: https://sqlite.org/pragma.html#pragma_defer_foreign_keys

Official rerun lineage is project-wide for each deliverable. Advisory lineage is per requester, so a private peer run cannot leak its identifier or block another reviewer. Administrators retain access to all advisory histories. Plan history supports `mine=true` to select the current requester.
