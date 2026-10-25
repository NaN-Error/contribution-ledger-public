# Financial records and distributions

**Source phase 13. Synthetic development only.** This is not a bank connection, company accounting suite, tax form, equity registry, payroll approval, or production-ready compensation system. The implementation deliberately refuses `synthetic_only=false`; no configuration switch enables real payouts. Phase 14 operational/security work and the later human agreement/go-live review remain separate gates.

## What the records mean

A hypothetical simulator example, a reviewed financial proposal, an approved frozen distribution, a download, and a reported external transfer are different objects. Creating or exporting any of them cannot issue contribution units or move money. Contribution awards still come only from the independent acceptance workflow. This phase's approved distributions are permanently labeled synthetic.

Project administrators and finance members can inspect supporting statements, financial entries, proposals, complete closes, and payment declarations. Only administrators create periods, approve/reject/void financial entries, approve proposals, and void mistaken transfer declarations. Administrators can approve their own financial submissions under the existing documented-project-admin policy; this is not a new two-person financial quorum. It cannot bypass the independent contribution reviewers.

Other current project members can see period availability and their own closed contributor statement. They cannot read another recipient's statement, financial source documents, or the complete audit bundle. A departed participant retains historical credit but does not retain application access; an administrator may provide their statement through an authorized external process.

## 1. Open an accounting month

Open a project → **Financial records** → **Create period**. Choose a ready source-credit policy and a ready calculation policy, a month, a reviewed agreement reference, and the explicit carryforward confirmation. The calculation policy supplies USD, timezone, gross/net basis, permitted deductions and pool weights. The source policy selects the original accepted work.

This initial finance implementation has one stream per project. After the first month, months must be consecutive, the previous month must be closed, and the timezone and source-credit policy cannot change. A different approved calculation-policy version can apply prospectively. A different game, sequel or separate release economics needs another project for now. The first period starts with zero reserve/deficit; undocumented opening cash or debt is not inferred.

An open period can receive draft records before its month ends. Final closing requires that the entire calendar month has ended in the selected timezone. Acceptance dates are not backdated for convenient testing. Supplied automated fixtures simulate a later clock in isolated tests; they do not change an operator's clock or application database. Opening an incorrectly scoped period has no delete/rebind shortcut; use a disposable project during development.

## 2. Attach supporting documentation

Financial statements use the existing protected object-storage adapter and `evidence_data` volume. They are separate financial records, not ordinary project-visible work evidence. Accepted formats are UTF-8 TXT/MD/CSV/JSON up to 256 KiB and supported static PNG/JPEG/WebP up to 2 MiB, subject to the existing filename, pixel and decoded-content checks. Native PDF, spreadsheets, archives, executables and remote fetching are not implemented. A description is not proof of an external receipt.

Text previews are plain text and explicitly indicate truncation. Image originals are download-only in this initial finance UI. Downloads recheck current access, backend, byte size and SHA-256. Original bytes are not malware-scanned and may retain metadata. Storage is private, not a promise that previously downloaded copies disappear after access removal. Keep these documents and the database in coordinated backups.

## 3. Record and approve entries

Every entry includes a supporting-document ID, positive integer cents, source-account/provider name, statement reference, unique line reference, description, kind, and reason. Amount direction follows the kind:

| Kind | Effect |
|---|---|
| Receipt | Adds cash on the declared gross or net basis |
| Deduction | Subtracts a separately documented, policy-permitted cost |
| Reserve hold | Removes funds from current distribution and adds them to the unallocated reserve |
| Reserve release | Moves existing reserve back into distributable cash |
| Adjustment credit/debit | Changes a later period's cash, explicitly linked to an approved entry in an earlier closed period |

Nothing affects a close until an administrator reviews the exact entry and supporting document and approves it. Rejected entries remain in history and have no cash effect. An approved entry in an open period can be voided with a new reasoned decision. Rejected or voided history is not edited. A corrected declaration uses a new, explicit source-line/correction identifier. References remain reserved, including after rejection or voiding.

Duplicate protection uses normalized source account + statement reference + line reference across the project. Case, repeated spaces and Unicode compatibility variants cannot create another copy of that identity. It is not fraud detection: different invented identifiers for the same transaction still require human source review.

### Gross and net receipts

A receipt must match the calculation policy. Gross receipts cannot list fees as already removed. Net storefront settlements must explicitly mark platform fees already deducted; also identify other removed components such as refunds/taxes. A settlement-related deduction must reference its receipt. A category already removed from that net receipt cannot be deducted again. Other deductions require an explicit separate-charge declaration and an allowed policy category. Linked receipts must be approved before close.

The application verifies the declared structure, not the actual storefront account. It cannot determine whether a person mislabeled a receipt or overstated an expense. Reference an accurately scoped source account when different storefront accounts reuse statement/line numbers.

### Canonical receipt CSV

The CSV path is only a bounded manual receipt import, not a vendor-specific statement connector. Its exact header is:

```csv
line_reference,amount_cents,description
sample-001,100000,Synthetic net storefront settlement
sample-002,25000,Second synthetic settlement
```

A single selected document, source, statement reference and basis apply to all rows. At most 200 rows/entries per period; amounts must be positive ASCII integer cents. Formulas, decimals, mixed columns and invalid rows are rejected. One failed row or duplicate rolls back the whole command. Replaying the same complete request returns its original rows; changing its contents under the same request ID is rejected. Importing never approves entries.

## 4. Reserve and deficit treatment

The preceding frozen period carries its reserve and negative deficit forward exactly once. Conceptually:

`net = previous deficit + receipts + credit corrections + reserve releases - deductions - debit corrections - reserve holds`

`distributable = max(net, 0)`; `next deficit = min(net, 0)`.

`next reserve = previous reserve + holds - releases`.

An unfunded new reserve hold or reserve overdraw blocks close. Negative cash is retained even when the distribution is zero. Reserve is unowned cash, never automatically an administrator's contribution units or personal payout. Capital priority, interest, loans and tax accounting are not automatically derived from free-text agreements; this is not a full accounting engine.

Example: receipt 1,000 cents and approved deduction 1,600 cents produce zero distributable and a -600-cent carryforward. Next month, 1,000 cents of receipts first absorb that deficit; a 200-cent funded reserve hold leaves 200 cents to distribute and 200 cents reserved.

## 5. Freeze release shares and close

Open **Close review and history**, calculate a fresh preview, inspect amounts, scope, source records, pending work, roundoff, and all blockers. Save a reviewed proposal. An administrator separately opens that preserved proposal, reviews it and explicitly approves or rejects it. The server reconstructs and compares current inputs before approval; an old preview cannot silently authorize changed records.

The first close freezes the release-award roster and its current accepted attribution. It blocks unresolved release disputes, unfinished release allocations, unarchived historical batches, missing eligible release credit, or release work accepted beyond the selected cutoff. Later closes use that frozen release roster. New awards never silently dilute it. Ongoing units follow original acceptance within the current accounting month; corrections do not turn old work into new activity.

All required positive-weight pools need valid denominators under the current `block_close` policy, even if little or no cash is being distributed. An empty or disputed pool does not pay the owner or silently redirect its amount. A blocked preview cannot become a close. The simulator remains available for clearly labeled incomplete examples.

Each close preserves financial records/decisions, source references/hashes, selected policy contents, ledger events and revision, eligible work, release share snapshot, carryforward, exact calculator input and output, and scope notices. Phase 7's calculation engine is reused unchanged: allocate exact cents between pools, then among recipients, with deterministic largest-remainder tie-breaking. No AI call is involved. One period can have only one close; re-export cannot create another obligation.

### Correcting release attribution

Resolve an accepted-work attribution dispute through the existing independent process. If the frozen roster's event history has changed, a later close is blocked until an administrator reviews and approves a **prospective release correction**. That successor retains the same award IDs and total units; it cannot add work, dilute the original denominator, or rewrite old closes.

The corrected release version applies only to later closes. A past 100%-Alice close remains exactly that historical record even if a later approved correction recognizes Alice 60% / Bob 40% for future closes. The system does not automatically charge Alice, reimburse Bob, create a supplemental prior-period obligation or claw back a completed payment. Such economic resolution needs its own documented process outside this initial feature.

## 6. Exports and statements

Administrators/finance members can download the frozen distribution as CSV, JSON or a deterministic audit ZIP. The JSON preserves exact calculation inputs/output, original names, source metadata/hashes, closing actor and IDs referring to the preserved governance records. Detailed proposal/approval reasons remain inspectable through proposal history; the bundle is a distribution replay package, not a complete external audit of every authorization or source file. Original document bytes and current payment declarations are not embedded.

CSV is quoted and all untrusted display names have a visible `text: ` prefix, with control characters replaced. JSON keeps the original names. Consumers must preserve text labels and not deliberately reinterpret edited cells as formulas. A hash/manifest detects accidental changes but is not an external signature or a defense against an all-powerful database administrator.

With the project Python dependencies installed, an administrator can also replay an exported `distribution.json` without a running API, database connection or provider:

```text
python scripts/replay_distribution.py path/to/distribution.json
```

This checks the preserved calculation and hashes, not external financial truth or signatures. Corrupted/inconsistent exports fail without printing confidential record contents.

A contributor's statement shows their frozen share, pool math and current external-payment declarations. Administrative full exports are private; do not publish the audit ZIP as if it were a public leaderboard. Repeated export of the same close yields the same bytes. Exporting does not mark anyone paid.

## 7. Record externally completed payments

Select a positive recipient amount in a frozen close. Enter a positive amount, provider namespace, unique external reference, and explicitly offset completion timestamp. The declaration must refer to a completed transfer after that close and not in the future. No bank credentials or actual transfer command are present.

Partial declarations show outstanding amounts. An overpayment requires an extra acknowledgement and remains separately visible; it does not increase the original distribution. The same normalized provider/reference cannot be used twice in the project, even after voiding. This initial one-recipient transfer-reference model does not split a single bulk bank-transfer ID among several recipients; use distinct documented line references from the external system.

Only an administrator can void a mistaken declaration. That adds a correction record and preserves the old reference and record; it does not reverse money. The UI distinguishes not recorded, partially recorded, fully recorded and overpayment recorded. None is external bank verification. Frozen-distribution export bytes remain unchanged as declarations evolve.

## Capacity and remaining limits

One USD source-policy/timezone stream per project; at most 240 periods, 200 entries per period, 60 documents per period, 60 proposals per period, 500 payment declarations per close. Request JSON is normally 64 KiB; only supporting-document uploads use the existing larger bounded allowance. Canonical CSV must fit the full JSON cap, including metadata. Financial amounts/aggregates use exact bounded integer cents up to 1,000,000,000,000. Existing contribution-reconstruction limits also apply; oversized scopes fail rather than silently truncate.

Export JSON/audit bundles have an 8 MiB output bound; a larger permitted underlying snapshot may require a future paginated/bounded-export enhancement. No large-export worker or lifecycle-retention erasure job is implemented here. The default local API database connection remains operator-owned pending phase-14 provisioning/hardening. Native PostgreSQL locks/grants, actual UI rendering, operational backup/restore, real bank documentation and human acceptance are not proven by SQLite or mock tests.
