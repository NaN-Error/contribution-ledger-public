# ADR 0014: exact financial closes without money movement

Date: 2026-09-14. Status: implemented in source; native/installed/browser/security/user gates open.

## Decisions

Separate eleven append-only resources: periods, documents, entries, entry decisions, receipt imports, release snapshots, close proposals, approvals, distribution closes, external-payment declarations and declaration voids. Derive status, never update approved history. Every reference is project/workspace scoped. Share the existing workspace transaction lock with policy, membership and ledger mutations; enforce unique source identities and idempotent command identities in the database.

Reuse the phase-7 largest-remainder engine without altering its original simulator contract. Add a pure signed cash waterfall with exact cents and explicit reserve/deficit carryforward. The `hypothetical`/`payable=false` trace returned by that engine remains a non-executable calculation; the surrounding approved close is still hard-labeled synthetic and separate from old simulator examples.

One sequential USD source-credit/timezone stream per project. First close freezes eligible release awards after required work/reconstruction is complete. Later attribution corrections require a separately reviewed successor with the same award roster and budget; future closes only. Newly added release work is not a way to dilute that roster. A separate game/release economics requires another project in this initial scope. Ongoing credit is scoped to original acceptance month, not correction date.

All required pools obey the current block-on-empty/dispute policy. Negative financial balances are retained rather than replaced with zero. Reserves are unowned cash and cannot be overdrawn or created unfunded. Expense semantics are constrained by the declared gross/net basis, permitted categories and linked source declarations. Human approval cannot be replaced with inferred bank truth.

Financial source material is administrator/finance-only, distinct from ordinary work evidence. Other current members may inspect their own closed statement. Use the existing protected storage contract; text preview and original download only, no PDF extraction, crawling or automatic source interpretation. Attachments are immutable financial source records; retention erasure and coordinated recovery remain later operational work.

CSV uses visible text-prefixing, quoting and control replacement for untrusted names. JSON preserves exact names and frozen inputs; ZIP adds deterministic members and hashes. These are replay/inspection artifacts, not externally signed legal statements. Exporting never creates a payment. Payment records describe externally completed fictional transfers with unique references, explicit times and partial/overpayment states. Voids correct mistaken records, not transactions.

No production-mode switch or bank connector is added. Real-use economics need completed operational and human agreement review. Administrators can approve finance records under the existing policy; this is not a new independent financial-quorum requirement and must not be confused with independent contribution acceptance.

## Tradeoffs and limitations

A conservative immutable period cannot be silently re-scoped after creation. Whole CSV imports are bounded to 200 entries/period rather than general-purpose vendor ingestion. Late cash corrections enter the next available sequential period and do not auto-reassign earlier recipients or claw back money. The project source-policy freeze intentionally prevents accidental mixing; more flexible negotiated scopes require a later design, not an implicit denominator change.

Synchronous bounded previews/replay are used rather than adding financial task authority to the AI/GitHub workers. Export size is bounded; large-export streaming/worker processing is not claimed. Metadata hashes and trigger guards do not defeat an all-powerful operator. Database lock semantics and migration/grant behavior require real PostgreSQL tests; passing SQLite fixtures is not sufficient evidence.

References checked while implementing the boundaries: PostgreSQL explicit locking documentation (`https://www.postgresql.org/docs/current/explicit-locking.html`) and OWASP CSV injection guidance (`https://community.owasp.org/attacks/CSV_Injection`). These support locking/serialization and untrusted-text precautions, not a claim of a completed security audit or universal spreadsheet behavior.
