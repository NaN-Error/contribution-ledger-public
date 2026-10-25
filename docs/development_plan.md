**Current execution (October 4, 2026):** owner-authorized P17 implementation and developer verification are complete. Continue fictional owner acceptance and targeted defect repair, preserving every separately required external/live/human gate. See current verification and repository_analysis.md.

# Contribution ledger — phase-by-phase development plan

**Execution checkpoint (September 22, 2026):** core phases 1–14 and offline phase-15/16 tooling are present. P16B installed verification is recorded; continue fictional user testing and targeted defect repair. The human pilot and live integration checks remain open. See `project_status.md`, ADR 0016 and `release/readiness.md`. The original roadmap below is retained for scope history, not proof of acceptance.


**Planning version:** 0.2  
**Prepared:** September 13, 2026  
**Working project name:** Contribution ledger  
**Repository root:** `contribution-ledger/`  
**Status:** Installed candidate is ready for fictional local testing; external and human gates remain open. See project_status.md for executed results.
**Next verification batch:** P16B (preserve every earlier open verification check).
**Audience:** The project owner and the developer/AI assistant implementing the application together.

> Historical phase statuses and future-tense descriptions below record the original plan. Current routing is in `backlog.json`; do not restart completed implementation phases.

## How to use this plan

This plan converts the earlier product specification into 16 ordered implementation phases and 48 smaller delivery batches. A batch is a reviewable unit of work, not a time estimate and not a promise that exactly one conversation will finish it. Adjacent small batches can be delivered together when the result remains understandable and testable; large batches can be split without changing their phase ID.

The sequence in this document is the execution roadmap from now on. The earlier 0–8 phase numbering described broad product stages; the crosswalk at the end of this plan preserves the connection. The underlying product rules remain in `docs/reference/product_specification_v0_1.md`. If an implementation choice conflicts with the earlier specification, record an explicit architecture/policy decision instead of silently changing it.

The original planning package contained only documentation and fixtures. The current source contains the core application and offline evaluation/handoff tooling. The original acceptance requirements below remain in force; current batch states and execution evidence are in `backlog.json` and `project_status.md`. No earlier unperformed runtime or user check becomes verified merely by advancing feature implementation.

The user has explicitly deferred thorough acceptance testing until the project is completed. Continue source development in phase order while preserving every open exit test; do not convert pending acceptance into a passed result. In every delivery, report separately: implemented, tested in the available environment, requiring a local test, blocked by an external service, and not yet implemented. Never describe generated code as verified production software merely because its source files exist.

## 1. What we are building

A browser-based application for a small collaborative game team, initially around 3–10 contributors, with GitHub as its first integration and manual evidence for non-code work. Multiple repositories can belong to one project. Start with one project currency, USD, and one customer-controlled deployment; support multiple workspaces in the data model and permissions from the beginning.

The core workflow is:

`Evidence → optional AI assessment → human decision → finalized contribution units → deterministic revenue calculation`

The program will show what the team recognized under an agreed policy. It will not claim to discover anyone's objective economic worth, issue equity, or determine worker status. AI summarizes evidence, checks it against acceptance criteria, and suggests matters for review. It does not approve contribution credit or send money.

Two usage modes are included. **Prospective mode** budgets useful work before it is done. **Retrospective mode** imports an existing repository, suggests candidate outcomes, incorporates missing evidence, and creates a human-approved opening balance. Neither mode equates code volume with value.

The application must remain useful with AI turned off. Users may configure their own permitted AI connections in a customer-controlled deployment. Hosted collection of other people's credentials requires a provider-specific authorization/data-handling review before it is enabled. Provider terms must be checked again when implementing that adapter and before real deployment; this plan is not contractual permission.

### Initial deliverables

The completed limited-release scope includes accounts and team access; versioned policies; milestone budgets; work packages and independently acceptable deliverables; non-code artifacts; attribution proposals; reviews and disputes; an append-only contribution ledger; GitHub import and synchronization; three provider adapters with automatic model discovery; evidence-grounded AI assessments; historical reconstruction; contribution explanations; financial-period records; frozen distribution snapshots; safe CSV/JSON exports; external payment recording; and backup, restore, security, and operating instructions.

### Explicit exclusions

There will be no actual money movement, bank/card/wallet custody, tax filing, company-equity issuance, employee-worth ranking, global reputation score, native Android/iOS app, blockchain, public contributor marketplace, arbitrary hosted AI endpoint, or execution of code from an imported repository. No Figma, Discord, Blender, game-engine, storefront, or accounting-platform integration is required for the first release; manual artifacts cover those workflows.

An imported binary asset may be evidence, but its byte count is never a contribution score. An AI-generated code change may be valid work, but the system evaluates the accepted outcome and attribution rather than attempting to detect AI authorship.

## 2. Working technical baseline

The initial design is a **modular monolith**: one Python backend codebase with clear business modules, one frontend, PostgreSQL, and separate worker processes. Avoid microservices and a general-purpose workflow engine in the initial build.

| Layer | Proposed implementation | Responsibility |
|---|---|---|
| Backend | Python + FastAPI | Authentication, authorization, application commands, queries |
| Database | PostgreSQL | Policies, budgets, contribution events, finances, job state |
| Persistence | SQLAlchemy + Alembic | Models, transactions, schema migrations |
| Frontend | React + TypeScript | Browser application and explanations |
| Frontend build | Vite with one committed package-manager lock | Reproducible development/build workflow |
| Long-running jobs | Celery + Redis broker | Imports, sync, model refresh, AI requests, export jobs |
| Durable dispatch | PostgreSQL outbox and job tables | Recovery when API, worker, or broker fails |
| Evidence storage | Protected local adapter first; S3-compatible adapter before remote deployment | Artifacts and immutable snapshot/export objects |
| Secrets | Dedicated SecretStore abstraction and customer-controlled secret backend | GitHub and permitted provider credentials |
| Local environment | Docker Compose + PowerShell helper scripts | Reproducible startup from Windows/VS Code |
| Tests | Pytest, property-based arithmetic tests, frontend tests, Playwright browser tests | Domain, integration, contract, UI, and security checks |

These are implementation selections, not claims that this is the only valid stack. Choose compatible maintained versions during phase 1 and commit exact locks/container references. Do not upgrade dependencies or switch frameworks silently during a later feature batch.

Long-running imports and AI calls will use durable workers rather than relying on in-process request background work. FastAPI's documentation points to Celery and queue-backed tools for heavier independent processing [S1]. PostgreSQL, not Redis, is the source of truth for financial/contribution records and durable job state.

Local-first means the web app initially runs on the owner's computer. It does not mean data never leaves the computer: approved GitHub API calls and AI analysis contact external services. A remote team needs a deliberately configured reachable deployment; phase 14 supplies that runbook. A powered-off computer cannot keep refreshing model catalogs or receiving webhooks.

### Recommended service activation order

Phase 1 starts the web app, API, and PostgreSQL. Define worker/storage contracts early but activate components as needed. Phase 5 adds artifact storage. Phase 8 begins imports with the worker/outbox foundation; phase 9 completes scheduler/recovery behavior and webhook intake. Phase 10 adds the provider secret backend and AI-related jobs. This keeps the first startup simpler without rebuilding the architecture later.

GitHub App private keys in phase 8 use operator-provisioned mounted secrets through the same secret abstraction, never a temporary plaintext database field. Phase 10 expands that foundation to user-configured permitted AI connections. Secret mounts and volumes still need operating-system protection and protected recovery procedures; a container mount alone is not a security guarantee.

## 3. Rules that are fixed unless explicitly amended

**Budgets precede awards.** An accepted deliverable can issue only its approved budget. Subdividing a task never increases its parent's budget. Reserve units remain unissued until approved allocation; they never silently belong to an owner.

**Credit follows acceptance, not activity count.** Commits, reviews, issues, and uploads are evidence. A contributor receives units only through an authorized acceptance/allocation decision. Partial work uses separately budgeted deliverables, not an AI's guessed completion percentage.

**No circular authority.** The AI assesses evidence; it cannot write awards or finance records. A beneficiary is not the sole independent approver of their own award. Default review requires a non-beneficiary; teams without one must explicitly adopt a reviewed joint-approval policy or involve an external reviewer. The application must not waive the rule just to get a close through. Synthetic demo accounts do not satisfy real-world independence.

**Percentages have a scope.** Show finalized eligible units divided by finalized eligible units in the named pool, together with pending budget and the policy version. A temporary 100% of currently issued units is not necessarily a final 100% of a release.

**Finalized history is preserved.** Corrections use linked events; frozen distributions are not recomputed in place. A model upgrade, rewrite of code, departed contributor, or expired artifact cannot silently change historical credit or payments.

**Model availability is not evaluator approval.** Model catalogs refresh automatically; official profiles change only through a visible prospective approval process. Preserve the requested/returned model identifiers, prompt version, source snapshots, and human decisions.

**Exact money, explicit denominators.** Use integer minor currency units and fixed-scale integer contribution atoms. Never use binary floating-point balances. Unknown attribution and unresolved disputes block affected closes. An empty pool never silently pays the owner or gets redistributed.

**Simulation is not payment.** A what-if preview is not an approved close. An approved close is not an export. An export is not proof of payment. The first release records externally performed payments only.

**Real-use readiness is not a legal certificate.** Review actual compensation, intellectual-property, provider/data, and accounting arrangements with qualified support before real use. Store the team's decisions and agreement references; do not represent a software checkbox or score as legal ownership or compliance.

## 4. Milestones visible to the user

| Target milestone | Available after | What works |
|---|---|---|
| Runnable foundation | Phase 1 | Browser, API, database, startup scripts, tests |
| Manual contribution ledger | Phase 6 | Policy → package → evidence → review → units |
| First useful manual release | Phase 7 | Ledger plus deterministic hypothetical revenue distribution |
| Connected GitHub workflow | Phase 9 | Historical import, current evidence, attribution, reliable sync |
| AI-assisted review | Phase 11 | Configurable providers/models, evidence assessments, human decisions |
| Full original product workflow | Phase 12 | Existing-project reconstruction and approved contribution-share explanations |
| Auditable distribution records | Phase 13 | Statements, frozen allocations, exports, external-payment recording |
| Restricted deployment candidate | Phase 14 | Hardening, backup/restore, staged operation |
| Evaluated limited-release candidate | Phase 15 | Measured evaluator behavior and completed human shadow pilot |
| Limited invited release | Phase 16 | Tagged build, onboarding, guides, documented go-live decision |

These are future targets, not current release statuses. A phase being implemented is not enough: its acceptance tests and required human checks must also pass.

## 5. Ordered development phases

Each phase lists its intended outcome, delivery batches, planned code areas, acceptance tests, user-visible demonstration, and exclusions. Paths are planned module boundaries; actual new/modified/deleted filenames will be listed alphabetically with each code delivery.

## Phase 1 — Project foundation and local startup

**ID:** P01 · **Status:** implemented in source; verification open · **Dependency:** planning baseline

Create a real, runnable starting project, not a mockup. Establish the Windows/VS Code workflow, baseline decisions, automated checks, and a clear record of what has and has not been implemented.

### P01A — Baseline, environment, and repository

Create the monorepo, README, environment example, ignore rules, pinned dependency manifests and lockfiles, PowerShell helper scripts, development-plan documents, and a doctor command. Record the selected compatible runtime versions in an architecture decision. Build a local-only container configuration; use synthetic data and no external credentials.

**Verification:** The doctor command reports missing tools with actionable messages. A clean installation uses committed dependency locks. Secret files, database volumes, and local uploads are excluded from version control and delivery ZIPs.

### P01B — API, database, and migrations

Create FastAPI startup, validated configuration, PostgreSQL connection management, a migration baseline, health/readiness endpoints, request IDs, and sanitized error responses. Introduce the outbox/job and storage interfaces without starting external integrations. Include an explicit development-only seed/reset operation.

**Verification:** Fresh migrations succeed against PostgreSQL. Re-running them is safe. Readiness becomes unhealthy when the database is unavailable. Reset refuses a non-development environment and never runs during normal startup.

### P01C — Browser shell and test harness

Create the React/TypeScript shell, navigation structure, accessible shared inputs, loading/error/empty states, and a status screen that queries the real API. Add unit-test, API integration-test, frontend build, and browser smoke-test commands to CI. Document start, stop, logs, and recovery.

**Verification:** The browser shows actual API status rather than a hardcoded green indicator. Startup works from the supplied root directory. Container restart preserves a seeded database record. The application binds to localhost by default.

**Planned module paths:**

```text
apps/api/app/core/
apps/api/app/db/
apps/api/app/main.py
apps/api/migrations/
apps/web/src/
docs/
infra/
scripts/
tests/
```

**Phase exit tests:**

- A clean checkout reaches the status page using documented commands.
- No API key, GitHub installation, public domain, or paid provider is required.
- Implemented tests and locally unverified tests are separately reported.

**Demonstration:** Open the app locally, inspect healthy services, create a test record through the seed operation, restart, and confirm persistence.

**Not included in this phase:** No real login, contribution percentages, AI evaluator, or financial statements. Hidden future navigation does not pretend these features work.

---

## Phase 2 — Accounts, workspaces, and project access

**ID:** P02 · **Status:** implemented in source; verification open · **Dependency:** P01

Establish who may see and change each project before accepting private evidence or contribution claims.

### P02A — Sessions and account lifecycle

Implement an explicit first-owner bootstrap, password hashing through a maintained library, revocable server-side sessions, HttpOnly cookies, CSRF protection, login throttling, logout, and account disablement. Store only hashes of session and invitation tokens. Development and HTTPS cookie settings must be distinct. No permanent demo password is enabled in production.

**Verification:** Expired, revoked, and disabled-user sessions fail. Cross-origin state-changing requests without the required CSRF proof fail. Login errors do not disclose whether an unrelated account exists.

### P02B — Workspace and project authorization

Add workspaces, project memberships, invitations, scoped roles, and a central authorization service. Membership can be suspended without deleting historical contributor identity. Enforce workspace-scoped references in database relationships and in every API query. Audit role changes.

**Verification:** A user cannot read, edit, search, download, or export another workspace by guessing IDs. Removing membership revokes active access. Membership changes do not erase finalized historical credit.

### P02C — Team-management screens

Build setup, login, project selection, member/invitation management, and permission-aware navigation. For the local pilot, the administrator may copy a one-time expiring invitation; an email service is not required yet. Provide an auditable operator-assisted recovery procedure and display project timezone/currency settings.

**Verification:** Seed two isolated workspaces, five fictional contributors, and a separate non-beneficiary reviewer. Test invited-user acceptance, expired invites, role changes, and read-only access in browser sessions.

**Planned module paths:**

```text
apps/api/app/auth/
apps/api/app/projects/
apps/api/app/security/
apps/api/migrations/
apps/web/src/features/auth/
apps/web/src/features/projects/
tests/integration/auth/
```

**Phase exit tests:**

- Authorization is enforced on the server, not just by hiding buttons.
- Cross-workspace negative tests pass for every endpoint introduced so far.
- A project owner cannot bypass future conflict-of-interest rules merely by holding the owner role.

**Demonstration:** Invite a contributor and reviewer, sign in as each, and demonstrate both permitted actions and denied cross-project access.

**Not included in this phase:** Public self-service registration, subscription billing, enterprise SSO, and unaudited administrator impersonation.

---

## Phase 3 — Versioned policies and milestone budgets

**ID:** P03 · **Status:** implemented in source; verification open · **Dependency:** P02

Turn the agreed rules into explicit, versioned configuration before credit can be issued.

### P03A — Policy schema and draft templates

Define contribution and distribution policy schemas, scope categories, budget rules, review requirements, contribution eligibility, accounting timezone, and pool boundaries. Include draft templates for a release pool and a release/ongoing split. Example ratios are sandbox fixtures, not silently accepted project economics.

**Verification:** Invalid ratios, unsupported currency settings, ambiguous period boundaries, and incomplete required rules are rejected. Saving a draft does not activate it or create economic rights.

### P03B — Approval and acknowledgement

Add policy versions, approval records, participant acknowledgements, effective dates, agreement-document references, and prospective amendments. A policy change creates a new version; it does not overwrite the version used by an earlier award. The UI explains which participants still need to acknowledge the policy.

**Verification:** An unapproved policy cannot authorize credit finalization. Acknowledging version 1 does not acknowledge version 2. Changed economics do not recalculate frozen distributions.

### P03C — Budgets, reserves, and amendments

Create milestones and integer-backed unit budgets. Add reserves, planned allocations, and audited budget amendments. Show the effect of a proposed budget change on provisional shares. Use transactional locking for concurrent allocations. Do not assign unused reserve to the owner.

**Verification:** Two simultaneous allocations cannot overspend a milestone. Negative budgets fail. Unissued reserve is not included as contributor-owned units. Reducing a budget below already-issued units is rejected.

**Planned module paths:**

```text
apps/api/app/contributions/budgets/
apps/api/app/policies/
apps/api/migrations/
apps/web/src/features/milestones/
apps/web/src/features/policies/
tests/unit/policies/
```

**Phase exit tests:**

- Policy history is immutable through ordinary application routes.
- A milestone has a visible total, assigned budget, unissued reserve, and issued-unit total.
- Participants can distinguish proposed economics from approved economics.

**Demonstration:** Create a 1,000-unit example milestone, reserve 100 units, approve a policy, and attempt both a valid and an overspending amendment.

**Not included in this phase:** Automatic legal-contract generation, equity issuance, or claiming that an acknowledgement proves legal compliance.

---

## Phase 4 — Work packages and measurable deliverables

**ID:** P04 · **Status:** implemented in source; verification open · **Dependency:** P03

Let the team describe useful outcomes, allocate their budgets, and track progress without using commits as units of value.

### P04A — Work-package creation and editing

Build work-package list/detail/create/edit screens with category, coordinator, outcome, acceptance criteria, evidence requirements, intended contributors, policy reference, and approved budget. Use optimistic version checks to prevent overwriting another person's edits.

**Verification:** Stale edits produce a conflict response. Work packages cannot reference another project's milestone, policy, or contributor. Required outcome and evidence fields are validated.

### P04B — Subdeliverables and proposed attribution

Split packages into independently acceptable, budgeted deliverables. Permit direct unit allocations or percentage proposals that are converted into exact integer unit atoms. Separate implementation, review, testing, and design roles without imposing universal weights. Pending allocations are proposals, not earned units.

**Verification:** Child budgets remain within their parent. Contributor allocations sum exactly to the deliverable budget. Splitting a package cannot create more units. Unassigned shares remain explicit blockers rather than disappearing from the denominator.

### P04C — Progress workflow and submission

Add draft, budget-approved, in-progress, submitted, changes-requested, cancelled, and completed views. Record submission revisions. Reopening or changing approved scope creates an amendment. Keep state transitions server-controlled and show a timeline rather than editable free-text status.

**Verification:** Invalid transitions fail. Cancelling unaccepted work releases only unissued budget. Already-finalized awards cannot be deleted by cancelling a package. Every submission identifies the exact scope revision being reviewed.

**Planned module paths:**

```text
apps/api/app/contributions/work_packages/
apps/api/migrations/
apps/web/src/features/work-packages/
tests/integration/work_packages/
```

**Phase exit tests:**

- Code, art, QA, maintenance, research, and marketing use the same outcome-based workflow.
- Every accepted portion can later be traced to a pre-approved or explicitly retrospective budget.
- No provisional allocation is presented as a finalized share.

**Demonstration:** Create networking, animation, and QA packages, divide one into independently acceptable parts, and show that only planned budgets have changed.

**Not included in this phase:** Automatic awards from task completion buttons, inferred labor hours, or generated complexity scores.

---

## Phase 5 — Manual evidence and secure artifact handling

**ID:** P05 · **Status:** implemented in source; verification open · **Dependency:** P04

Make non-code contributions first-class and establish the evidence boundary used by both humans and AI.

### P05A — Evidence records and uploads

Implement source links, contributor statements, and bounded artifact uploads with author/provenance claims, category, date, confidentiality, file hash, size, and processing status. Start with safe text and raster-image handling; other approved formats may remain download-only. Store external links without automatically fetching arbitrary URLs.

**Verification:** Unauthorized uploads, excessive sizes, unexpected file types, traversal filenames, and workspace-crossing evidence links are rejected. A declared author is a claim, not automatically a verified identity.

### P05B — Reviewable evidence interface

Add an evidence timeline, safe text/image previews, attribution statements, notes, and protected downloads. Introduce a local protected-storage implementation behind an object-storage interface and a production S3-compatible adapter/test contract. Record missing, inaccessible, and excluded evidence explicitly.

**Verification:** A removed member cannot open a download URL or cached preview. Malicious HTML/Markdown is not executed. Files do not become public simply because their URLs are hard to guess.

### P05C — Immutable evidence snapshots

Create content-addressed review snapshots linking package revision, acceptance criteria, artifacts, and omission lists. Subsequent uploads produce a new snapshot and mark affected unfinished reviews stale. Separate evidence retention from finalized accounting retention.

**Verification:** Changing an artifact invalidates the current review snapshot without changing an archived one. Deleted or unavailable evidence is labeled unavailable. Finalized unit totals are not silently recalculated when raw evidence retention expires.

**Planned module paths:**

```text
apps/api/app/evidence/
apps/api/app/storage/
apps/api/migrations/
apps/web/src/features/evidence/
tests/integration/evidence/
```

**Phase exit tests:**

- An artist and tester can submit useful evidence without a repository connection.
- Every review uses a specified package revision and evidence snapshot.
- The application never executes uploaded programs, macros, game projects, or repository scripts.

**Demonstration:** Attach a character image, test report, and design statement; submit them; replace one artifact; show the new revision and stale-review warning.

**Not included in this phase:** Automatic Blender/Unreal parsing, archive extraction, broad URL crawling, PDF/OCR analysis, or file-size-based contribution valuation.

---

## Phase 6 — Human review, disputes, and contribution ledger

**ID:** P06 · **Status:** not started · **Dependency:** P05

Convert authorized human decisions into durable contribution credit with precise arithmetic and a usable explanation of every award.

### P06A — Review queue and decisions

Build reviewer assignments, conflict checks, supported/unsupported acceptance criteria, requests for additional evidence, reasoned allocation decisions, and participant notification records. Bind approvals to the exact package, allocation, policy, and evidence revisions. Any material change invalidates outstanding approval.

**Verification:** A beneficiary cannot be the sole independent approver of their own award. A changed allocation cannot reuse old approval. The UI displays evidence before the final approval action and requires a reason.

### P06B — Award transactions and projections

Create an append-only contribution-event ledger and derived balances. Finalizing accepted deliverables issues exact integer unit atoms in one transaction, checks budgets, and records idempotency keys. Use a dedicated ledger write path and database permissions; workers performing AI analysis will not receive this authority.

**Verification:** Repeated commands and concurrent approvals cannot double-issue units. The issued sum equals the accepted budget. Rebuilding balances from events reproduces the stored projection exactly. Ordinary update/delete attempts on finalized events fail.

### P06C — Disputes, adjustments, and contributor views

Build dispute filing, supplementary evidence, assigned resolver, reasoned resolution, linked adjustment events, and personal/project contribution views. Display finalized units, pending claims, disputed amounts, exact pool denominator, and policy version. Record participant departures without erasing history.

**Verification:** An unresolved dispute prevents the affected pool's eventual close. Corrections add events and preserve the original award. An adjustment that would create an invalid negative entitlement is blocked for explicit resolution rather than causing negative payouts.

**Planned module paths:**

```text
apps/api/app/ledger/
apps/api/app/reviews/
apps/api/migrations/
apps/web/src/features/contributions/
apps/web/src/features/reviews/
tests/integration/ledger/
```

**Phase exit tests:**

- Manual contribution accounting works with GitHub and AI completely disabled.
- Each awarded unit has a package, evidence, policy, decision, and actor trail.
- The team can inspect and dispute attribution without an administrator editing balances by hand.

**Demonstration:** Accept the networking behavior but not its unfinished tests; award only its accepted units; repeat approval; open a dispute; and demonstrate linked correction history.

**Not included in this phase:** AI-controlled finalization, automatic retroactive penalties for rewrites, or an endpoint that directly sets an arbitrary final personal percentage.

---

## Phase 7 — Revenue simulator and first useful manual release

**ID:** P07 · **Status:** implemented in source; environment/user verification open · **Dependency:** P06

Make the accounting consequences visible early, using a reusable pure calculation engine and clearly labeled hypothetical amounts.

### P07A — Deterministic distribution engine

Implement single-currency calculations using integer minor units and exact ratios. Normalize shares separately within each eligible pool. Apply a documented largest-remainder allocation with a stable tie-breaker, first among pools and then among recipients. Return every intermediate amount needed for explanation.

**Verification:** One cent among three contributors, uneven pools, zero denominators, negative distributable inputs, and large totals behave as specified. Line sums exactly match authorized amounts. The input ordering does not change a tie-breaker.

### P07B — What-if interface

Build a simulator for an explicitly hypothetical distributable amount, approved or draft policy, and current contribution snapshot. Show provisional percentages, unissued planned units, pool weights, and a per-person calculation explanation. Label simulations non-payable and keep them separate from later financial-close records.

**Verification:** Editing a scenario never issues contribution units or creates a payment obligation. Scenario URLs respect workspace authorization. A preview shows the exact ledger revision it used.

### P07C — Regression fixtures and manual milestone

Create 20–30 synthetic policy/accounting fixtures and end-to-end scenarios covering programming, art, QA, research, departures, unfinished work, and disputes. Package the first useful internal milestone as a manual ledger with revenue previews. Document its remaining limitations.

**Verification:** The agreed five-person $10,000 example yields $2,750, $2,350, $2,000, $1,650, and $1,250. The database can be reconstructed and the same simulator result obtained without external calls.

**Planned module paths:**

```text
apps/api/app/finance/calculation/
apps/web/src/features/simulator/
tests/e2e/
tests/fixtures/
tests/unit/finance/
```

**Phase exit tests:**

- The first genuinely useful milestone exists at the end of this phase.
- Simulations and prospective shares are not labeled paid, owed, frozen, or legally vested.
- The same engine will be reused for phase 13 rather than rewritten.

**Demonstration:** Walk five contributors through approved units and a $10,000 hypothetical distribution, then change only the hypothetical amount and inspect the explanation.

**Not included in this phase:** Financial receipt imports, final accounting closes, bank transfers, tax forms, and permanent release-share freezing.

---

## Phase 8 — GitHub App and historical evidence import

**ID:** P08 · **Status:** implemented in source; verification open (see ADR 0009 and project_status.md) · **Dependency:** P07

Connect a selected repository and reconstruct its reviewable history without treating GitHub activity as automatic compensation.

### P08A — GitHub App connection

Implement customer-controlled GitHub App registration/configuration, installation association, selected-repository authorization, short-lived installation token handling, and connection status. Keep login identity separate from repository installation. Use only the currently documented read permissions required by implemented endpoints.

**Verification:** An unapproved installation cannot be attached by guessing its ID. The backend proves the installation belongs to the authorized connection flow. Revoked or missing permissions produce actionable errors; no code-write permissions are requested.

### P08B — Resumable history import

Import bounded PRs, issues, reviews, commits, and check metadata with pagination, repository/date selection, checkpoints, cancellation, retry limits, and completeness reporting. Preserve exact revisions and the import-as-of instant. Store large/binary/missing-diff states instead of pretending the source is complete.

**Verification:** An interrupted import resumes without duplicate source versions. Rate limits pause rather than spin. A pre-cutoff PR updated later is handled through a documented refresh/reconciliation strategy. No import issues units.

### P08C — Identity and evidence linking

Create stable external identity mappings, reviewable email/co-author claims, unknown/bot identities, and manual link/unlink decisions. Connect imported artifacts to existing work packages. Show activity statistics only with named metrics and denominators, never a composite personal-worth ranking.

**Verification:** Squash merges, multiple emails, direct commits, bots, and a different merger are represented without assuming the merger authored everything. One PR linked twice does not create duplicate credit.

**Planned module paths:**

```text
apps/api/app/evidence/sources/
apps/api/app/integrations/github/
apps/api/app/workers/
apps/web/src/features/github/
tests/contract/github/
```

**Phase exit tests:**

- A real authorized test repository can be imported and inspected alongside a fully mocked fixture repository.
- One game project can hold multiple repository records, though one repository is the first end-to-end test.
- Historical gaps and unknown identities are visible to reviewers.

**Demonstration:** Import a small permitted repository, map two authors, inspect a co-authored PR, attach it to a package, and confirm balances remain unchanged.

**Not included in this phase:** Inferring missing non-code work, running builds from imported repositories, or issuing an automatic opening balance.

---

## Phase 9 — Reliable synchronization and job processing

**ID:** P09 · **Status:** not started · **Dependency:** P08

Keep GitHub evidence current and establish the durable job infrastructure shared by later AI and export tasks.

### P09A — Webhook intake

Verify raw-body webhook signatures, validate event/action/installation/repository, deduplicate delivery IDs, and persist the accepted delivery with an outbox record in one transaction. Respond after durable acceptance; perform full fetching in workers. Keep the signing secret out of URLs and logs.

**Verification:** Forged signatures fail. Redelivered valid events do not create duplicate effects. A crash between database persistence and broker publication is recovered from the outbox.

### P09B — Worker lifecycle and scheduler

Complete Celery/broker dispatch, database-owned job state, leases, bounded retries, rate-limit backoff, dead-letter handling, cancellation, and observable failure reasons. Activate scheduled reconciliation. Queue payloads contain scoped IDs, not source-code blobs or credentials.

**Verification:** Killed workers can resume safe operations. Two schedulers cannot dispatch the same periodic task twice. Job handlers recheck current authorization and credential status before external requests.

### P09C — Reconciliation and freshness UI

Reconcile missed events, re-fetch authoritative versions after out-of-order events, process uninstall/repository-removal events, and display last-successful sync, backlog, incomplete artifacts, and stale reviews. Document a secure reachable webhook endpoint for local testing or an optional staging setup.

**Verification:** Missing webhooks are repaired. An older event cannot overwrite newer authoritative state. Revocation stops future fetches and triggers the configured retention/access response. New evidence does not change historical finalized awards.

**Planned module paths:**

```text
apps/api/app/integrations/github/
apps/api/app/jobs/
apps/api/app/workers/
apps/web/src/features/jobs/
infra/
tests/integration/jobs/
```

**Phase exit tests:**

- Accepted deliveries remain traceable through processing and failure states.
- At-least-once delivery is handled with idempotent effects; the app does not assume exactly-once network delivery.
- The scheduler runs only while the deployment is operating and checks overdue tasks after restart.

**Demonstration:** Replay a webhook, stop a worker, create another source change, restart, and show one current evidence version with no duplicated credit.

**Not included in this phase:** Always-on operation while the user's computer is powered off, public deployment without HTTPS/security setup, and running repository code.

---

## Phase 10 — AI connections, provider adapters, and live model catalog

**ID:** P10 · **Status:** not started · **Dependency:** P09

Implement user-controlled permitted API connections, automatic discovery of available models, and a project-approved evaluator profile without hardcoding current model names.

### P10A — Provider contract, secrets, and mock provider

Define a provider adapter and normalized request/response/error contracts. Add a dedicated SecretStore interface, a customer-controlled encrypted secret backend with its master key outside the database and archives, credential identifiers and payer ownership permissions, revocation, and masked settings. Start with a deterministic fake provider for no-cost tests. Hosted BYOK remains disabled pending provider-specific authorization review.

**Verification:** Stored secrets are never returned to users, printed in logs, included in prompts, or passed in ordinary job payloads. A connection owner can revoke access. Permission to pay for a call does not itself authorize sending project source code.

### P10B — First live provider and budget controls

Implement OpenAI as the initial adapter, subject to the project's permitted deployment. Add connection validation, model discovery, explicit small compatibility probes, pricing records, usage estimation, atomic spend reservations, bounded output, and usage reconciliation. Treat an ambiguous timeout as possibly billed; do not blindly repeat paid requests.

**Verification:** Invalid credentials, denied model access, unknown pricing, timeouts, refusals, output truncation, and rate limits have distinct states. Concurrent jobs cannot reserve the same remaining budget. No live paid test runs without explicit local configuration and payer approval.

### P10C — Anthropic, Gemini, and evaluator profiles

Add the other two adapters one at a time under the same contract tests. Normalize per-connection catalogs and capabilities; refresh at connection creation, manual request, and roughly daily while running. Keep last-known-good entries after transient failure. Build profile approval/versioning, model selection, data-sharing controls, and profile-locked official runs.

**Verification:** A newly listed model appears as an option but never replaces the official evaluator. Incompatible modalities are filtered out. Missing capability/price data stays unknown. Revoked credentials stop queued requests; already-dispatched calls are tracked separately.

**Planned module paths:**

```text
apps/api/app/ai/profiles/
apps/api/app/ai/usage/
apps/api/app/providers/
apps/api/app/security/secrets/
apps/web/src/features/ai-settings/
tests/contract/providers/
```

**Phase exit tests:**

- OpenAI, Anthropic, and Gemini each pass adapter contract tests; live smoke results are individually recorded.
- Catalog updates and official evaluator updates are distinct operations.
- The entire manual product still works with no key or when every provider is unavailable.

**Demonstration:** Configure a permitted connection locally, refresh models, select a compatible model, approve a profile, and simulate a newly discovered model without changing that profile.

**Not included in this phase:** Pasting secrets into chat, arbitrary remote provider URLs, automatic onboarding of new AI companies, automatic price guessing, or claims of a guaranteed total provider-invoice cap.

---

## Phase 11 — Evidence-grounded AI review

**ID:** P11 · **Status:** not started · **Dependency:** P10

Use AI to explain the work and assess evidence against agreed outcomes while preserving human approval and deterministic credit accounting.

### P11A — Bounded evidence packets

Build packets from exact work-package/policy/evidence revisions. Redact secrets and unnecessary personal identifiers, neutralize contributor display identities where practical, select relevant code context, record omitted material, and estimate cost. Do not send salaries, current revenue shares, popularity measures, or unrelated project data.

**Verification:** Cross-workspace evidence and excluded paths never enter a packet. Large inputs produce explicit omissions or a needs-evidence status rather than silent truncation. Packet hashes change when relevant source content changes.

### P11B — Structured assessments and validation

Implement versioned prompts and output schemas for outcome summaries, supported/contradicted/insufficient criteria, proposed roles, overlap flags, questions, and evidence references. Validate all referenced IDs and output types, record provider/model/usage/request metadata, and keep the model limited to assessment writes. Citation existence checks do not prove a claim is true; human review remains required.

**Verification:** Invented IDs, unauthorized identities, malformed JSON, provider refusals, and truncated responses cannot become awards. Repository instructions to award money have no executable route. Raw reasoning traces are not required; save task-relevant conclusions and evidence.

### P11C — AI-assisted reviewer experience

Show an assessment beside original evidence and allow accept, modify, reject, or request evidence with reasons. Separate advisory/private comparisons from official project-profile runs. Retain official reruns and their reasons. Cache only within the authorized workspace and exact packet/profile versions.

**Verification:** Choosing a more favorable model does not replace the official profile. An outage leaves manual review available. Evidence changes mark unfinished assessments stale. The reviewer can trace each accepted observation to the original artifact.

**Planned module paths:**

```text
apps/api/app/ai/assessments/
apps/api/app/ai/packets/
apps/api/app/ai/validation/
apps/web/src/features/assessments/
evals/
tests/integration/ai/
```

**Phase exit tests:**

- AI creates review suggestions, not ledger events, economic entitlements, or payment commands.
- Missing evidence is not converted into zero contribution.
- Model explanations and reviewer decisions are both archived, including disagreement.

**Demonstration:** Analyze a networking package with an intentionally missing test; show a needs-evidence finding, attach the test, rerun under the same profile, and have a human finalize the decision.

**Not included in this phase:** Objective worth percentages, guaranteed code correctness, inferred hours, automatic ownership, or a claim that several agreeing models prove fairness.

---

## Phase 12 — Existing-project reconstruction and contribution dashboards

**ID:** P12 · **Status:** not started · **Dependency:** P11

Deliver the original connect-a-project experience: reconstruct candidate contributions from history, let people correct the reconstruction, and produce an approved opening balance.

### P12A — Candidate work-package grouping

Group imported activity using explicit issue/PR relationships, milestones, source references, and optional AI suggestions. Allow reviewers to merge, split, reassign, and reject candidates. Preserve grouping provenance and evidence coverage. Suggested unit ranges use the team's agreed examples, not a universal impact formula.

**Verification:** Artificially splitting commits/PRs does not multiply an approved outcome budget. The same evidence cannot silently create duplicated awards. Binary or missing history appears as a limitation, not absence of work.

### P12B — Opening-balance review

Create a batch of retrospective packages under an explicitly approved historical scope and unit budget. Invite missing-role contributions, resolve unknown identities, compare alternative allocations, and approve the opening balance through the existing human review and ledger path. Require before/after dilution visibility.

**Verification:** Unknown attribution and active disputes block the affected balance freeze. Re-importing does not re-award opening credit. Historical approvals retain the retrospective policy and do not pretend a prior agreement existed.

### P12C — Project and contributor explanations

Build dashboards for observed activity, finalized contribution share by pool, pending/unresolved work, categories, evidence sufficiency, and optional simulated revenue. Explain each percentage's numerator, denominator, scope, date, and policy. Provide filters without global personal rankings or a pseudo-objective meaningfulness score.

**Verification:** Filters do not silently change the denominator label. A person with non-code work is represented alongside programmers. Unsupported AI observations remain separate from accepted contribution decisions.

**Planned module paths:**

```text
apps/api/app/contributions/reconstruction/
apps/api/app/reporting/
apps/web/src/features/overview/
apps/web/src/features/reconstruction/
tests/e2e/reconstruction/
```

**Phase exit tests:**

- The original product loop is complete: connect history → review evidence → agree credit → see contribution and hypothetical revenue shares.
- Prospective and retrospective work are visibly distinguishable.
- The application can show useful results without asserting it found every contribution.

**Demonstration:** Import a fictional existing game, let AI suggest outcomes, add an artist's missing evidence, approve a corrected opening balance, and explain each contributor's share.

**Not included in this phase:** Automatic compensation from history alone, global cross-project scores, or hiding uncertainty behind decimal precision.

---

## Phase 13 — Financial records, frozen distributions, and exports

**ID:** P13 · **Status:** not started · **Dependency:** P12

Extend the existing simulator into auditable accounting-period closes without custody of funds or automatic payments.

### P13A — Periods and reconciled financial records

Add accounting periods, project-timezone cutoffs, statement attachments, receipts with explicit gross/net basis, approved deductions, reserve movements, and agreed deficit carryforward. Track money received separately from contribution units. Add duplicate-import identifiers for supported manual/CSV entry paths. Prevent double deductions from already-net receipts.

**Verification:** The same statement entry cannot be silently imported twice. A negative net balance remains recorded even when the distributable amount is zero. Unsupported or unapproved expenses do not reduce distributions.

### P13B — Share snapshots and close workflow

Freeze release-pool membership/shares at an approved release close, then use those shares with separately eligible ongoing-period units. Add preflight blockers, close approval, immutable financial/policy/ledger snapshots, and concurrency-safe finalization. Reuse phase 7's calculator. Revisions after a close are linked adjustments, not silent recomputation.

**Verification:** Disputed units, unresolved attribution, unapproved finance entries, incomplete required acknowledgements, and zero-denominator pools without an agreed handling rule block the relevant close. Concurrent close requests produce one snapshot. Historical replay needs no AI call.

### P13C — Statements, exports, and external payment records

Generate per-contributor statements, CSV/JSON exports, calculation explanations, hashes, and audit bundles. Escape spreadsheet-formula-like untrusted text. Add externally supplied payment references, amounts, partial payments, status, and reconciliation. Re-export the same frozen snapshot without recreating obligations.

**Verification:** All allocations reconcile to the authorized distributable amount, including explicit held amounts where policy permits. Exported is not paid. Duplicate external reference submissions are detected. Later corrections preserve both the original close and payment history.

**Planned module paths:**

```text
apps/api/app/finance/close/
apps/api/app/finance/exports/
apps/api/app/finance/periods/
apps/web/src/features/distributions/
tests/integration/finance/
```

**Phase exit tests:**

- Past distributions reproduce exactly from stored approved records and calculator version.
- No bank, wallet, card, tax filing, or equity issuance exists in this version.
- Real-use mode remains gated by operational readiness and documented human approval of the actual agreements; a checkbox is not a legal certification.

**Demonstration:** Enter a synthetic net statement, close a period, explain an exact distribution, export it twice, record a partial external payment, and replay the unchanged historical result.

**Not included in this phase:** Automatic money movement, automatic clawbacks, multi-currency conversion, company accounting in full, or legal/tax advice generated by the score.

---

## Phase 14 — Security hardening, backup recovery, and staging

**ID:** P14 · **Status:** not started · **Dependency:** P13

Validate the security already built into prior phases and prepare a controlled, recoverable deployment before onboarding a real team.

### P14A — Adversarial access and input tests

Audit authorization across APIs, files, search, exports, jobs, caches, and logs. Test CSRF, injection, upload abuse, malicious markup, formula injection, rate limits, and provider endpoint restrictions. Verify AI worker database permissions and secret access boundaries. Review dependencies and container configuration.

**Verification:** Critical cross-workspace, secret-exposure, and ledger-integrity defects block release. Prompt-injection test failures cannot cause privileged actions because the model has no such capabilities. General telemetry contains no raw credentials or confidential prompts.

### P14B — Backup, restore, and upgrades

Implement coordinated backups for PostgreSQL, evidence objects, configuration, and protected key material through an operator-controlled process. Test restoration into an isolated environment, calculator replay, migration upgrades from the prior tag, and recovery after a failed migration. Document which rollback paths require restore rather than an unsafe downgrade.

**Verification:** A restored project reproduces finalized distributions and can decrypt its required retained secrets only with the separately controlled recovery material. A database-only backup is not labeled a complete system backup. Destructive reset is disabled outside development.

### P14C — Restricted staging and operational controls

Provide a controlled staging/production configuration with HTTPS, no development accounts, secure cookie settings, protected service ports, health checks, secret injection, bounded workers, and operational logs. Add stronger administrator authentication such as tested MFA before remote real-use access. Include retention/export/delete workflows and incident procedures.

**Verification:** Only approved public endpoints are exposed. Debug routes and broad CORS are absent. Disabling an integration stops new jobs. An operator completes documented restore and credential-rotation drills in staging.

**Planned module paths:**

```text
apps/api/app/operations/
apps/api/app/security/
docs/runbooks/
infra/
scripts/
tests/security/
```

**Phase exit tests:**

- No unresolved critical security or accounting defect is accepted for the pilot.
- Restore and upgrade procedures have executed results, not only written instructions.
- Staging is a deliberate user-controlled deployment, not an unannounced public publication.

**Demonstration:** Rotate a test credential, restore an isolated backup, replay a financial snapshot, and demonstrate that unauthorized users and workers cannot access restricted data.

**Not included in this phase:** Claims of independent certification, tamper-proof administration, a guaranteed uptime SLA, or public SaaS launch.

---

## Phase 15 — Evaluator validation and shadow pilot

**ID:** P15 · **Status:** not started · **Dependency:** P14

Find out whether the system actually improves contribution review before using its AI suggestions around real earnings.

### P15A — Evaluation corpus and reporting

Expand to at least 100 varied synthetic or authorized cases with reviewer references, honest disagreements, and a separately held-out set. Include non-code work, small critical fixes, large routine work, prototypes, paid/AI-assisted contributions, and missing artifacts. Version the dataset and run the same packets against proposed evaluator changes.

**Verification:** Report criterion support, unsupported claims, invalid output, omission rate, reviewer changes, latency, and usage cost separately. A single aggregate score cannot excuse a permission or accounting defect.

### P15B — Robustness and failure drills

Test name/order sensitivity, verbosity changes, formatting churn, PR splitting, model substitutions, retired models, outages, ambiguous billing timeouts, and budget reservation races. Compare AI-assisted review with the existing manual baseline. Record limitations and thresholds before evaluating the holdout.

**Verification:** No money changes based on the benchmark itself. Failing core security/accounting tests blocks release. AI disagreements remain visible and resolved by people; no fabricated fairness guarantee is published.

### P15C — Two-period shadow pilot

Have the participating team run at least two complete review periods using the application while existing compensation arrangements remain unchanged. Collect participant feedback, disputes, review time, missing-role evidence, and independent reconstruction attempts. Record real completion evidence; synthetic tests alone do not mark a human pilot finished.

**Verification:** Participants can explain their proposed allocations and appeal them. The product provides enough administrative benefit compared with the manual ledger to justify continued use. Remaining disagreements and limitations are documented.

**Planned module paths:**

```text
docs/pilot/
evals/adversarial/
evals/fixtures/
evals/holdout/
evals/reports/
tests/resilience/
```

**Phase exit tests:**

- Actual pilot observations, not assumptions, determine whether AI-assisted real use should proceed.
- Provider credential/data arrangements and actual team agreements have been reviewed before the relevant go-live decision.
- No phase is labeled passed merely because code was generated.

**Demonstration:** Compare a manual decision with an AI-assisted decision on the same package and reconstruct a proposed period distribution independently.

**Not included in this phase:** Claiming universal evaluator accuracy, substituting fictitious users for a completed human pilot, or automatically changing compensation during the pilot.

---

## Phase 16 — Limited release and maintainable handoff

**ID:** P16 · **Status:** not started · **Dependency:** P15

Package the tested product for a small invited team, with clear operating instructions and separately documented approval for any real use.

### P16A — Onboarding and product finishing

Complete onboarding for project policy, team members, repository connection, AI connection, opening balance, and first review. Improve keyboard navigation, mobile-browser usability, empty states, error recovery, and plain-language explanations. Finish operator and contributor guides.

**Verification:** A new invited team can complete a synthetic setup without undocumented developer intervention. Every percentage is labeled. Manual mode is discoverable and fully functional.

### P16B — Release package and upgrade path

Produce a tagged source release, locked dependencies, migrations, configuration examples, backup/restore scripts, deployment instructions, release notes, and a verified test report. Include an explicit list of external checks performed by the user versus tests run in the development environment.

**Verification:** Install the release into a fresh environment and upgrade a retained prior-version fixture. Neither route overwrites local secrets or database data. Every bundled file has a purpose and the manifest matches the actual release.

### P16C — Go-live checklist and maintenance baseline

Run a final feature, permission, financial, provider-arrangement, agreement, backup, and pilot checklist. Keep actual-compensation mode disabled until the responsible people approve their deployment and rules. Define incident contacts, review cadence, model/profile upgrade gates, dependency maintenance, and a prioritized post-beta backlog.

**Verification:** The app does not present technical release completion as legal approval. Public signup, custody of funds, and autonomous payouts remain absent. The team has a rollback/recovery procedure and knows which limitations remain.

**Planned module paths:**

```text
apps/web/src/features/onboarding/
docs/release/
docs/runbooks/
docs/user-guide/
infra/
tests/e2e/
```

**Phase exit tests:**

- A limited invited deployment is reproducible and recoverable.
- All required tests have recorded results and all unresolved non-critical limitations are disclosed.
- The next version starts from a saved tagged baseline, not an incomplete chat transcript.

**Demonstration:** Install the tagged build, onboard a fictional five-person team, reproduce the complete GitHub/AI/manual/preview/export workflow, and inspect the readiness checklist.

**Not included in this phase:** General public SaaS, automatic payment execution, broad employee monitoring, equity administration, or unsupported integrations.

---

## 6. Data model and module contracts

### 6.1 Core entity groups

Create tables through migrations as their features arrive, not dozens of empty speculative tables in phase 1. Every tenant-owned entity carries `workspace_id`. Use scoped references and authorization checks to prevent linking records across workspaces.

| Phase | Entity group | Minimum important information |
|---|---|---|
| 1 | schema/version, outbox/job foundation | Schema revision, job identity, timestamps, attempt/status |
| 2 | users, sessions, invitations, workspaces, projects, memberships | Stable identity, token hashes, role, status, project timezone/currency |
| 3 | policy_versions, approvals, acknowledgements, milestones, budget_events | Immutable rules, effective instant, actors, budget/reserve atoms |
| 4 | work_packages, deliverables, allocation_proposals, package_revisions | Outcome, acceptance criteria, units, scope version, proposed recipients |
| 5 | evidence_objects, evidence_links, evidence_snapshots | Source, hash, permissions, provenance, content references, omissions |
| 6 | review_cases, review_decisions, disputes, contribution_events, balance_projections | Exact approved revisions, reason, actor, units, correction links |
| 7 | simulation_scenarios | Hypothetical amount, input snapshot, algorithm version, no payment authority |
| 8 | github_installations, repositories, external_identities, source_objects, import_runs | Stable external IDs, access scope, source versions, checkpoints |
| 9 | webhook_deliveries, outbox_events, jobs, sync_cursors | Delivery uniqueness, durable dispatch, retry/lease state, freshness |
| 10 | provider_connections, secret_references, model_entries, profile_versions, pricing_versions, usage_reservations | Owner/payer, allowed project, permitted data class, catalog facts, approved configuration |
| 11 | evidence_packets, assessment_runs, assessment_outputs, validation_findings | Exact input/output/model/prompt versions, evidence references, usage, errors |
| 12 | reconstruction_batches, candidate_packages, opening_balance_decisions | Historical scope, grouping provenance, conflicts, approval links |
| 13 | accounting_periods, financial_entries, release_share_snapshots, distribution_snapshots, distribution_lines, exports, payment_records | Receipt basis, approvals, exact amounts, held amount, immutable input/output, external references |
| 14 | retention_jobs, backup_manifests, incident_records | Operator actions, restore evidence, controlled deletion/export state |
| 15–16 | evaluation/pilot/release records | Prefer versioned files for non-sensitive test results; keep real participant feedback appropriately restricted |

### 6.2 Representation and arithmetic

Represent one contribution unit as **1,000 unit atoms**, with at most three decimal places, as selected in ADR 0004. This supersedes the original 10,000-atom planning proposal; existing data semantics are unchanged. Store atoms as signed 64-bit integers with explicit application range checks; no fractional atom is allowed. Exact integer sums remain authoritative even when display rounding hides small differences.

Use integer cents for USD distributions. Encode potentially large money/unit integers as decimal strings at the JSON boundary so frontend number conversion cannot silently lose precision. The frontend formats values; the backend owns all authoritative arithmetic. Use exact rational shares until the final apportionment stage.

Percentage entry can use basis points for two-decimal precision, or accept direct unit atoms. Convert proposals into exact amounts with the same documented allocation procedure. A 100-unit deliverable divided into thirds must sum to exactly 100 units, with residual atoms assigned by an explicit stable tie-breaker. Do not independently round each recipient and lose or create value.

A pool's share for contributor `i` is:

`finalized_eligible_atoms(i, pool) / total_finalized_eligible_atoms(pool)`

For an illustrative two-pool distribution, allocate the total among release and ongoing pools according to approved weights, then allocate each pool among its recipients. Use largest remainders and stable contributor/pool IDs for ties. This can differ by a cent from a naive single floating-point formula; the prescribed two-stage algorithm, its tie-breaker, and version are part of the policy/calculator record.

Eligibility is determined by a documented event, initially acceptance/finalization as defined by policy, not whichever Git timestamp gives a preferable result. Store UTC instants; display and cut periods using the project's named timezone. Use half-open periods `[start, end)` so a boundary event is counted at most once. America/Puerto_Rico may be the initial displayed timezone; it must be configurable before accounting records lock it.

Release shares freeze at an explicit release close. Ongoing shares are calculated separately for each defined period. Never add unrelated milestone or period unit scales together without a recorded normalization agreement.

### 6.3 Lifecycle separation

Do not make one giant status field represent every process.

- Work package: draft → budget-approved → in-progress → submitted → changes-requested/accepted/cancelled.
- Review: pending → evidence-ready → in-review → decision-ready → finalized, with needs-evidence/disputed/stale branches.
- Contribution: proposed allocation → approved issuance → immutable event, with linked adjustment events.
- AI run: queued → budget-reserved → dispatched → succeeded/failed/uncertain-billing/cancelled, followed by output validation and human review.
- Accounting period: open → closing → ready/blocked → approved → frozen.
- Export/payment: separate records linked to a frozen distribution; may represent repeated downloads, partial external payments, and reconciliation without editing the frozen calculation.

Each transition requires a server-side command with current authorization, expected resource version, and an idempotency identity when duplicate effects would matter. A UI dropdown must not set an arbitrary backend state.

### 6.4 Atomic award transaction

The final-award operation checks current actor authority, recipient conflicts, exact package/policy/evidence/allocation revisions, required approvals, available budget, and allocation sum. Lock relevant budget/deliverable rows in a consistent order; write the award event, its lines, projection update, and notification/outbox event atomically. A unique operation key returns the existing result for an identical retry and rejects a different payload reusing the same key.

Database checks can enforce local nonnegative/range/uniqueness rules. Multi-row sums require transaction logic and locks; do not assume a simple row-level CHECK constraint enforces an aggregate budget. Add concurrent integration tests against PostgreSQL, not only a different local database.

Keep immutable business events and mutable read projections separate. This is not a requirement to event-source every user setting. The financial/contribution records get the stronger append-only treatment; ordinary editable drafts use normal versioned tables.

### 6.5 Close transaction and accounting boundaries

Build a snapshot of the finalized contribution events, pool rules, release-share snapshot, period financial records, held amounts, and calculator version. Run preflight blockers. Acquire the relevant locks, verify that revisions have not changed since approval, persist the frozen distribution and all lines in one transaction, and issue a unique close identity.

A changed input invalidates a draft preview. A finalized close is never recomputed in place. A refund, discovered expense, corrected contribution, or mistaken payment after a close is handled by a linked adjustment under the agreed policy. No automatic contributor debt or bank withdrawal is created.

Record negative net cash/deficits separately even when a period's distributable amount is zero. A zero-unit pool may retain an explicitly approved held amount; otherwise close is blocked. Every frozen total satisfies:

`recipient allocations + explicitly held amounts = authorized distributable amount`

The app is a distribution subledger, not a complete business general ledger or a tax system.

## 7. GitHub integration contracts

Use a customer-controlled GitHub App with the least documented read permissions needed for the implemented endpoints. Keep source installation authorization separate from application login. Resolve repository access on the server rather than trusting an arbitrary installation ID sent by the browser.

Historical import starts with a bounded selected repository and date range. Fetch authoritative PR, issue, commit, review, and check metadata. Use a separate checkpoint for each resource type, record the import-as-of time, and reconcile records updated during import. Preserve external stable IDs and immutable source revisions. Do not use a changed GitHub username as a new person automatically.

Webhook intake must verify signatures, inspect the event/action, persist delivery plus outbox atomically, and deduplicate by delivery ID. GitHub documents a 10-second response expectation and recommends queue-based processing; this design responds promptly after durable intake rather than completing the import inside the request [S2].

Treat webhooks as update signals, not the only truth. Workers fetch authoritative state, and scheduled reconciliation repairs missed deliveries. Uninstall/revocation changes processing and evidence-access policy. Store a documented retention decision rather than silently retaining everything forever or deleting frozen accounting history.

Map unknown authors, co-author trailers, pair work, bots, multiple emails, squash merges, direct pushes, and cherry-pick/backport duplication as reviewable claims. A merge-button click is not complete authorship evidence. One PR may support multiple distinct outcomes, but neither link count nor source-object count grants units.

Exclude irrelevant generated/vendor/formatting churn from volume summaries while preserving a potentially valuable maintenance or dependency-security outcome. Mark API truncation, missing patches, binary content, and unavailable LFS objects explicitly. Do not run the repository, invoke its hooks, download all external submodules, or install its dependencies to analyze it in the first release.

For local development, historical pull imports can run without an inbound webhook. Webhook testing needs a deliberately configured reachable endpoint. A secured staging endpoint or user-approved tunnel is an operational prerequisite, not a reason to expose every local service.

## 8. Provider discovery and assessment contracts

### 8.1 Adapter interface

Use a small application-owned contract rather than a framework that hides important provider differences:

```text
validate_connection(secret_ref) -> ConnectionValidation
list_models(connection, cursor) -> ModelPage
get_capabilities(connection, model_id) -> CapabilityRecord
estimate_usage(packet, profile) -> UsageEstimate
analyze(packet, profile, request_identity) -> NormalizedProviderResult
normalize_error(response_or_exception) -> ProviderError
reconcile_usage(result) -> UsageRecord
```

Provider errors distinguish invalid credentials, denied model access, unavailable model, invalid request, timeout, rate limit, transient service failure, refusal, malformed output, and possible billing without a confirmed result. Retry only when it is safe; for an ambiguous paid call, use provider-supported idempotency/retrieval where available or pause for reconciliation instead of blind automatic duplication.

OpenAI, Anthropic, and Gemini publish model-list endpoints [S3–S5]. Refresh using the authorized connection and current documented pagination/authentication. Do not hardcode model names from this plan. New model entries are catalog changes; a new provider company still requires implementation and tests.

### 8.2 Catalog fields

Retain provider, model ID, display name, known modalities, supported methods, known token limits, structured-output compatibility, source metadata, last successful discovery, last compatibility check, availability/deprecation state, and the connection's authorization scope. Capability unknown is not capability false, and it is not permission to guess from a name.

Use separate records for discovered availability, actually checked request compatibility, and project approval. Small compatibility probes require a permitted connection and a budget. Do not send confidential source just to test whether a connection works.

Catalog refresh happens at connection setup, explicit request, approximately daily while the instance runs, and when recovery requires it. A failed refresh retains the prior catalog with a stale warning. A missing model pauses affected official runs or uses only an already-approved fallback; it never silently changes the evaluator.

### 8.3 Secret and data controls

API credentials must stay in backend-controlled secret handling, not browser persistence or source control. OpenAI's published key-safety guidance specifically warns against client-side deployment and recommends backend handling [S6]. Log redaction, narrow access, rotation/revocation, protected backups, and masked status screens are required from the first live connection.

A hosted BYOK offering remains a separate enabled-by-review configuration. The model selector must identify which provider will receive the packet, who pays, and whether the project's data policy authorizes that transfer. A participant with an API key is not automatically authorized to send every repository or artifact to that provider.

Store external provider requests/outputs only as needed under the agreed retention policy. Do not send secrets, pay rates, current personal shares, unrelated workspaces, or unnecessary identifiers. Distinguish provider training policy from retention; do not infer one from the other.

### 8.4 Budget controls

Pricing data is separate from model discovery. Store its source, effective date, currency, billable categories, and verification status. Unknown cost blocks dispatch unless a payer explicitly supplies an approved conservative rate configuration. The UI states that estimates and local limits are not a guaranteed provider invoice cap.

Reserve expected maximum cost in a database transaction before dispatch. Track in-flight reservations, retries, output limits, cached billing categories, and actual reported usage. Reconcile reservations without freeing an uncertain potentially billed request prematurely. A job cancelled before dispatch releases its reservation; a cancelled already-dispatched request may still have usage.

### 8.5 Assessment output

The normalized output contains schema/profile/packet IDs; a summary; supported, contradicted, or insufficient-evidence criterion findings; evidence references; suggested contributor roles with unresolved claims; overlap/quality flags; questions; and a recommendation to review, obtain evidence, or involve a specialist.

The model cannot return a ledger command, final payout, or arbitrary user ID as an action. Validate that every reference exists in the authorized packet. This validation proves reference membership, not factual support; human review still checks the claim. Evidence-sufficiency labels must not be displayed as statistically calibrated probabilities.

Store task-relevant responses and rationale/evidence, not a requirement to expose a provider's hidden reasoning. Preserve requested and returned model IDs, provider request ID, prompt/schema/adapter/settings versions, exact packet hash, token usage, cost estimate, validation findings, and human decision. Reproducible distributions rely on archived approved decisions, not on asking the model to produce an identical answer later.

OWASP describes indirect prompt injection through external content such as repository files and documents [S7]. The mitigation here is architectural: no financial tools, no ledger credentials, constrained outputs, no unrestricted execution, least-privilege workers, and human approval. Delimiters and prompt wording alone are not the security boundary.

## 9. Proposed application API groups

These are endpoints for the application we will build, not existing GitHub or provider APIs. The exact schema will be generated from the implemented FastAPI application. Use `/api/v1`, scoped authorization, cursor pagination, expected versions, and consistent error shapes.

```text
POST   /api/v1/auth/login
POST   /api/v1/auth/logout
GET    /api/v1/auth/me
POST   /api/v1/workspaces/{id}/invitations
GET    /api/v1/projects
POST   /api/v1/projects
POST   /api/v1/projects/{id}/policy-versions
POST   /api/v1/policy-versions/{id}/approve
POST   /api/v1/projects/{id}/milestones
POST   /api/v1/milestones/{id}/budget-amendments
POST   /api/v1/work-packages
POST   /api/v1/work-packages/{id}/submit
POST   /api/v1/work-packages/{id}/evidence
POST   /api/v1/review-cases/{id}/decisions
POST   /api/v1/review-cases/{id}/finalize
POST   /api/v1/review-cases/{id}/disputes
GET    /api/v1/projects/{id}/contributions
POST   /api/v1/projects/{id}/simulations
POST   /api/v1/integrations/github/imports
POST   /api/v1/webhooks/github
GET    /api/v1/jobs/{id}
POST   /api/v1/jobs/{id}/cancel
POST   /api/v1/provider-connections
POST   /api/v1/provider-connections/{id}/validate
POST   /api/v1/provider-connections/{id}/refresh-models
GET    /api/v1/provider-connections/{id}/models
DELETE /api/v1/provider-connections/{id}
POST   /api/v1/evaluator-profiles
POST   /api/v1/evaluator-profiles/{id}/approve
POST   /api/v1/work-packages/{id}/assessments
POST   /api/v1/projects/{id}/reconstruction-batches
POST   /api/v1/reconstruction-batches/{id}/submit
POST   /api/v1/projects/{id}/accounting-periods
POST   /api/v1/accounting-periods/{id}/financial-entries
POST   /api/v1/accounting-periods/{id}/preview
POST   /api/v1/accounting-periods/{id}/close
GET    /api/v1/distributions/{id}
POST   /api/v1/distributions/{id}/exports
POST   /api/v1/distributions/{id}/payment-records
GET    /api/v1/projects/{id}/audit-events
```

Every command that can issue units, change an approved allocation, close a period, or record a payment uses explicit authorization and idempotency. Validation failures produce useful errors, not a silent partial operation. No endpoint directly assigns a user's final project percentage or reveals a stored credential.

## 10. Repository structure and coding conventions

```text
contribution-ledger/
  .github/workflows/
  AGENTS.md
  CHANGELOG.md
  README.md
  apps/
    api/
      app/
        ai/
        api/
        auth/
        contributions/
        core/
        db/
        evidence/
        finance/
        integrations/github/
        jobs/
        ledger/
        operations/
        policies/
        projects/
        providers/
        reporting/
        reviews/
        security/
        storage/
        workers/
      migrations/
      pyproject.toml
      uv.lock
    web/
      src/
        components/
        features/
        lib/
        routes/
      package.json
      package-lock.json
  docs/
    backlog.json
    decisions/
    development_plan.md
    project_status.md
    reference/
    runbooks/
  evals/
    adversarial/
    fixtures/
    holdout/
    reports/
  infra/
  scripts/
  tests/
    contract/
    e2e/
    fixtures/
    integration/
    security/
    unit/
```

Only create code directories when their implementation needs them. Keep shared business logic in backend services and pure domain functions, not duplicated in route handlers, workers, and React. The frontend must not be authoritative for permissions, credit, or money. Use type hints, input validation, clear errors, transaction boundaries, and tested adapters.

Use one agreed Python dependency manager and one frontend package manager, reflected in committed locks; the above `uv.lock` and `package-lock.json` paths are the proposed default. Verify their tooling at implementation time. Avoid ad hoc dependency installation scripts that bypass those locks.

Each feature module should generally expose typed schemas, a service/command layer, persistence models/queries, and routes. It need not be forced into a large abstract framework. New migration files are added sequentially; do not edit a migration already applied to a user's database.

Tests use synthetic data by default. Paid/live integration tests are opt-in, individually reported, and require authorized credentials supplied locally. Never bundle secrets or real private repository code into a general test fixture.

### Exact phase-1 starting file inventory

The first delivery will introduce or update the following files as needed across P01A–P01C. This is the target inventory, not a claim the files already exist in this planning archive. Final delivery manifests will reflect the actual paths and selected tool versions.

```text
.env.example
.github/workflows/ci.yml
.gitignore
AGENTS.md
CHANGELOG.md
README.md
apps/api/Dockerfile
apps/api/alembic.ini
apps/api/app/__init__.py
apps/api/app/core/config.py
apps/api/app/core/errors.py
apps/api/app/core/logging.py
apps/api/app/db/base.py
apps/api/app/db/session.py
apps/api/app/main.py
apps/api/migrations/env.py
apps/api/migrations/script.py.mako
apps/api/pyproject.toml
apps/api/uv.lock
apps/web/Dockerfile
apps/web/index.html
apps/web/package-lock.json
apps/web/package.json
apps/web/src/App.tsx
apps/web/src/lib/api.ts
apps/web/src/main.tsx
apps/web/src/styles.css
apps/web/tsconfig.json
apps/web/vite.config.ts
docker-compose.yml
docs/backlog.json
docs/decisions/0001-project-baseline.md
docs/development_plan.md
docs/project_status.md
scripts/doctor.ps1
scripts/start-dev.ps1
scripts/stop-dev.ps1
scripts/test.ps1
tests/integration/test_health.py
tests/unit/test_configuration.py
```

Any additional first migration, frontend test configuration, or container entrypoint belongs in the actual manifest. Do not claim this provisional inventory is exhaustive after implementation changes it.

## 11. Collaboration and delivery protocol

Before a batch, read `docs/project_status.md`, `docs/backlog.json`, applicable decisions, and the current source. For the first implementation no existing app code is needed; for later edits use the exact files from the current tested baseline. Do not modify an imagined or outdated copy. When current files are missing, obtain the relevant files/current ZIP before replacing them.

Deliver a ZIP with the complete `contribution-ledger/` relative paths for changed files, including full file contents rather than isolated snippets. Provide the source baseline/tag, target batch, and an alphabetical manifest of created, modified, and deleted files. Include any required migration and exact Windows commands to run. Do not include `.env`, secrets, uploads, database volumes, node_modules, virtual environments, or unrelated private files.

Use `delivery.json` or an equivalent manifest to record the expected base version, file hashes, replacements, required deletions, migrations, tests performed, and local checks. If a replacement would overwrite user edits, stop and reconcile rather than blindly patching. A deletion manifest must be applied explicitly; a ZIP alone does not delete obsolete files.

After extraction, the owner runs the documented startup/build and practical checklist. Bugs found in that batch are fixed before moving on. Update the progress documents only to reflect evidence: `implemented_pending_verification` is different from `verified`. External-account and human-pilot gates can remain `awaiting_external_validation` without claiming they passed.

The assistant can create source files, migrations, tests, configuration, documentation, and ZIP deliveries, and run tests supported by the available environment. The owner performs local Windows/browser tests and authorized real-provider/GitHub tests that are not available in the development environment. Accounts, private keys, provider charges, public deployments, and real compensation approvals remain under the owner's control. No source generation by itself establishes production readiness.

### Standard batch response

A code-delivery response should identify the batch and outcome; give its ZIP; list paths alphabetically; explain changes; give setup/migration/run commands; state actual test results and remaining checks; include a small hands-on acceptance checklist; and update the next action. Avoid unrelated feature changes and silently renamed concepts.

### Continuation record

`docs/project_status.md` should always include the current phase/batch, last verified source tag, schema version, exact dependency/runtime versions, local startup command, features implemented, tests executed, remaining checks, active blockers, and the next task. `AGENTS.md` stores development boundaries and workflow rules, not credentials. `docs/backlog.json` provides machine-readable status and acceptance criteria.

This is what prevents a new chat or development agent from needing to reconstruct the project from conversation history. The repository, not memory alone, is the source of truth.

## 12. Cross-phase test strategy

### Domain and database tests

Use pure tests for arithmetic/state transitions and real PostgreSQL integration tests for locking, idempotency, scoped references, and migrations. Test all critical financial invariants, not only happy-path examples. Property-based tests should vary unit totals, recipients, pool splits, smallest/largest amounts, and input ordering. Enforce exact sum conservation.

### Authorization matrix

For every resource type, test owner, contributor, independent reviewer, finance operator, read-only auditor, suspended member, unauthenticated caller, and same-role member of a different workspace. Test authorization again in background jobs and download/export handlers. An administrative role may operate the app without acquiring permission to self-approve awards or reveal another connection's secret.

### Adapter and resilience tests

Recorded mocked fixtures test pagination, unavailable resources, GitHub identity edge cases, retries, webhook replay/out-of-order arrival, revoked installations, and provider errors. Opt-in live smoke tests show what was truly verified with each account. Test crash-after-persist/before-dispatch and crash-after-external-call/before-recording-result separately; the second can have billing consequences.

### Security/evaluator tests

Include malicious repository instructions, encoded instructions, fabricated citation IDs, changes in contributor name/order, unreasonably verbose submissions, generated-code volume, large/omitted diffs, stale check SHAs, non-code contributions, and unsupported business-impact claims. Separate deterministic authorization/accounting failures from model-quality disagreements. A reference-valid output can still be wrong.

### Operational tests

Restore complete backups to a new environment, upgrade from the previous release, rotate/revoke keys, recover failed jobs, run with the broker unavailable, and replay frozen distributions without providers. Test that retention/deletion does not silently change finalized totals, and disclose when evidence needed for future factual inspection is no longer available.

### Minimum always-on regression cases

| Case | Required behavior |
|---|---|
| Same approval submitted twice | One award effect |
| Two concurrent approvals against the same budget | Cannot overspend |
| One package divided into ten | No budget inflation |
| Missing contributor allocation | Explicit blocker |
| Artist without Git activity | Can receive reviewed credit |
| Merger differs from author | No automatic authorship assignment |
| Same evidence imported twice | No duplicate award |
| Repo comment requests 100% credit | No privileged AI action |
| Provider returns invented evidence ID | Invalid assessment reference |
| New model appears | Catalog only; official profile unchanged |
| Provider times out after possible billing | Reconcile/flag, no blind paid retry |
| Contributor/worker requests another workspace | Denied |
| One cent must be divided | Exact total conserved |
| Net receipt already includes platform deductions | No second deduction |
| Negative period result | Zero distributable if applicable; deficit retained |
| Disputed units at close | Affected close blocked |
| No eligible pool units | Agreed held handling or blocker, never silent redistribution |
| Distribution exported twice | Same frozen snapshot, no new obligation |
| Partial external payment | Only recorded amount marked reconciled |
| Model no longer exists | Historical arithmetic still reproduces |
| Evidence changes after approval | Draft review stale; historical frozen decision preserved |

## 13. Decisions that must be resolved at the appropriate stage

We do not need to delay phase 1 for a permanent brand name, domain, hosting vendor, payment system, every provider, or a final commercial pricing model. Use the working name and customer-controlled local setup.

Before real policy activation, the team chooses the project's actual pool weights, review independence/joint-approval rule, eligibility, cash-compensation treatment, unit-budget process, participant departures, reserve/deficit handling, and agreement references. Sandbox defaults are clearly marked and never applied to real economics merely because a form was prefilled.

Before live GitHub testing, the owner provides an authorized test repository and configures the App in their own account. Before each paid AI test, the payer chooses the permitted provider/connection, approves source-data handling, and supplies credentials locally. Do not request them in chat. A small synthetic packet should be the first live call.

Before remote deployment, choose the host and storage/secret backend, confirm HTTPS and access controls, test backups, and supply infrastructure costs from actual vendor information. No deployment purchase is needed to write the first phases. Before real compensation use, complete the documented human pilot and arrangement review; the application does not decide whether the collaborators are employees, contractors, owners, or another legal category.

## 14. Scope after the limited release

Only after the core workflow proves useful, prioritize a separate expansion phase: GitLab/task-manager imports, richer asset previews, additional permitted providers, self-hosted local models, approved hosted credential flows, enterprise identity, multicurrency, storefront/accounting imports, or mobile application packaging.

Actual payment execution is not a small toggle. It requires a separate project for financial-provider integration, participant identity/compliance requirements, payout failures/refunds, accounting reconciliation, permissions, security, and legal review. Equity management and broad HR usage are also outside this release.

Public SaaS would add another operational scope: tenant onboarding, subscription billing, public abuse controls, support, stronger isolation reviews, permitted provider funding/delegation, and service operations. Do not let these delay the initial team's useful private tool.

## 15. Crosswalk from the earlier specification

| Earlier broad stage | New implementation phases |
|---|---|
| 0: policy and fixtures | Phase 1 baseline; phase 3 policies; phases 7 and 15 fixtures/evaluation |
| 1: foundation | Phases 1–2; worker/storage activation across phases 5, 8–9 |
| 2: manual ledger | Phases 3–6 |
| 3: GitHub evidence | Phases 8–9 and retrospective workflow in phase 12 |
| 4: provider registry | Phase 10 |
| 5: AI-assisted review | Phase 11 |
| 6: revenue simulation/close | Early simulator in phase 7; finalized records in phase 13 |
| 7: adversarial validation | Tests in every phase; full hardening in phases 14–15 |
| 8: shadow pilot/limited release | Phases 15–16 |

The intentional sequencing change is an earlier simulator. It lets the team validate the contribution policy and arithmetic before complex GitHub/AI analysis can obscure an accounting problem. The engine is reused, not reimplemented.

## 16. Primary technical references

Checked September 13, 2026. These support specific API/security facts, not the proposed unit scale, project phases, release ratios, or claims of validated fairness. Recheck implementation details and provider terms when building the relevant feature. Model examples in current provider pages are not commitments to use those models.

[S1] FastAPI, Background Tasks, caveat about heavier processing and Celery. `https://fastapi.tiangolo.com/tutorial/background-tasks/`

[S2] GitHub, Best practices for using webhooks: secrets, HTTPS, timely responses, queues, event checks, and delivery IDs. `https://docs.github.com/en/webhooks/using-webhooks/best-practices-for-using-webhooks`

[S3] OpenAI, List models API reference. `https://developers.openai.com/api/reference/resources/models/methods/list/`

[S4] Anthropic, List Models API reference. `https://platform.claude.com/docs/en/api/models/list`

[S5] Google, Gemini Models API reference. `https://ai.google.dev/api/models`

[S6] OpenAI, Best Practices for API Key Safety. `https://help.openai.com/en/articles/5112595-best-practices-for-api-key-safety`

[S7] OWASP, LLM Prompt Injection Prevention Cheat Sheet. `https://cheatsheetseries.owasp.org/cheatsheets/LLM_Prompt_Injection_Prevention_Cheat_Sheet.html`

The earlier specification is retained as the project's source document, not as evidence of implementation. Its older source list should be independently rechecked before relying on any current contractual, legal, or API statement.

## 17. Historical first implementation request

The original planning request was **Phase 1, starting with P01A: baseline, environment, and repository**. It is retained for provenance only. Current continuation work is P16B installation, verification and targeted defect repair; see the checkpoint at the top of this document.

The phase is finished only when the actual application starts locally, reports its real health, persists data, and its required checks have recorded results. Nothing in this documentation package marks that implementation as already done.
