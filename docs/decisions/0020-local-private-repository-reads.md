# ADR 0020 — direct local private repository analysis

Accepted October 7, 2026 after the owner's request to improve usability, review
publication privacy, and test authorized public repositories plus the private
contribution-ledger repository. The owner selected MIT for the application.

Keep public link reads credential-free. Add an explicitly enabled, loopback-only
development/test connection to the same dashboard. Use a fine-grained token or
the personal desktop's existing GitHub CLI account. A registered GitHub App
remains the existing team import path; no embedded OAuth client identity or
public hosted credential collection is introduced.

Migration 0019 adds a project/owner-scoped connection. Freeze applied 0001–0018.
Connections require explicit selected repository URLs and expire locally after
30 days. Only the owner can reconnect or use their connection to create a run.
An already authorized project's administrators can advance its creator's run
while that creator still has administrator access. Captured drafts retain the
existing administrator/reviewer boundary; contributor sharing remains a separate
exact reviewed disclosure. No private source is sent to an AI provider.

Token ciphertext uses the existing authenticated context-bound store, with a
separate GitHub master and credential directory. Tokens never enter database
JSON, report snapshots, audit details, error bodies or build artifacts. Track
pre-commit ciphertext writes; retain ambiguous-commit writes for deliberate
recovery. Rotation/revocation cleans prior ciphertext only after database commit.
Do not overwrite a retained master or initialize over orphaned ciphertext.

CLI tokens stay in memory. Use fixed github.com and the recorded account name;
ignore inherited CI token environment variables. CLI discovery/execution is
limited to opt-in personal desktop mode, with an eight-second command timeout.
No login, install or account mutation runs automatically. The CLI account may
have broader upstream permission; the application only performs fixed-origin,
bounded GETs to explicitly selected repository paths.

Recheck current project access, connection state, version, expiration and operator
flags before and after each network checkpoint. A changed/revoked connection
discards its response and produces an actionable failed run. Reconnection can
resume retained checkpoints. Existing capture byte/source/request bounds remain.
No automatic credit, code execution or real financial operation is added.

An explicit activity-date preview reads at most two requests per selected
repository under a sixty-second deadline. Empty/unavailable commit history is
reported without inventing contributors. Current-day UI ranges stop at request
time. Advanced project pages load on demand; input/connection UI is separated
from report exploration.

Publication preparation normalizes machine paths in current source reports and
adds MIT. Original historical evidence stays in private local storage. Any
history replacement, repository visibility change or new public repository
requires a concrete separately reviewed publishing action.
