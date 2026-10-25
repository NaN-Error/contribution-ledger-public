# ADR 0019 — personal Windows startup

Accepted October 7, 2026 following the owner's explicit request for a complete
folder with one readable Start.cmd that prepares the app and opens repository
input without setup-code copying or developer-tool installations.

Reuse the existing Python/PostgreSQL/React application. Bundle isolated official
Python 3.13.16, Node 22.23.0 and the retained PostgreSQL 17.11 runtime. PostgreSQL's
PE imports also require the Microsoft C++ shared runtime. Check its minimum
version; if missing, download a pinned, signature-verified official installer
and open interactive Microsoft setup, retaining license/UAC approval. Do not
redistribute DLLs copied from this host, silently install it or restart Windows.
No floating dependency download or evaluated-repository execution runs during
startup. User data and encryption masters live outside the program folder
in a restricted Windows-user directory. Process ownership records and serialized
startup prevent duplicate launches; occupied foreign ports are never stopped.

Add migration 0018_desktop_profile; applied 0001–0017 remain frozen. An explicitly
enabled local operator command provisions a personal owner only when no owner or
users exist. It atomically records that desktop identity and creates an initial
workspace/project. Reopening rotates one hashed two-minute ticket. A same-origin
CSRF-protected browser POST consumes it once under database locks and uses normal
session rotation. URL fragments are cleared before API calls, not placed in query
strings or logs. Existing regular owners cannot be adopted. Disabled accounts,
MFA and independent credit review remain effective. Remote/staging desktop config
is rejected; ordinary source/team startup remains unchanged.

This mode explicitly treats the Windows user as the trusted local operator. It
does not defend against malicious processes already running as that user. Source,
runtime license/provenance and checksums support inspection; no independent
certification, signed installer, live AI quality or real financial readiness is
claimed. New packaging tests must cover fresh/repeated startup, ticket replay,
preservation, ports, errors and a browser reaching repository input.
