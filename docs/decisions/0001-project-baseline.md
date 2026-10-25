# Decision 0001 — Proposed initial project baseline

Status: proposed development baseline; not a team compensation agreement.
Date: September 13, 2026.

Use the working name Contribution ledger and repository contribution-ledger/. Build for Windows/VS Code local development with a customer-controlled browser-based deployment. Start with a small game team, GitHub evidence, manual artifacts, one currency (USD), and separate release/ongoing pools where explicitly agreed.

Use Python/FastAPI, PostgreSQL, SQLAlchemy/Alembic, React/TypeScript, durable queue-backed workers, an object-storage abstraction, and a dedicated secret-store interface. Choose and lock compatible maintained versions during phase 1. No runtime versions are claimed as already installed.

Keep approved economic policy, observed activity, AI recommendations, finalized contribution credit, frozen distributions, and recorded external payments separate. The AI has no authority to issue units or pay contributors.

Adopt the 16-phase roadmap in docs/development_plan.md for implementation. Keep the earlier specification as reference. Begin with a no-key manual foundation, not a whole-repository AI scorer.

Consequences: users can validate the contribution rules and arithmetic before external automation; the tool remains useful without an AI subscription; later hosted operation and actual payments remain separate scopes. More initial work is required for approvals, auditability, and transaction tests than for a simple Git statistics dashboard.

Amendment rule: material changes to these engineering choices need an updated decision record. Actual compensation rules require their own human agreement/approval process and cannot be inferred from this engineering decision.
