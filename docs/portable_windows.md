# Personal Windows package

Extract the complete Windows x64 package and double-click Start.cmd. It bundles
Python, Node and PostgreSQL; it does not require Docker or system installations.
Startup creates a private personal profile, Personal workspace and My repositories
project on a fresh database. A two-minute one-use ticket opens the repository
dashboard without signup or setup-code copying. Paste a public repository link,
choose dates and explicitly start analysis. Public reads need no GitHub credentials.

Saved state belongs to the Windows user under
`%LOCALAPPDATA%\ContributionLedger\Personal`. Startup preserves it. Stop.cmd stops
owned processes and preserves every saved database/evidence/master. Closing the
browser keeps the app running. Start.cmd opens a fresh session after sign-out.
Move the program folder only while stopped; data stays in its separate location.

The desktop flag is off by default. It is accepted only for loopback local/test
settings. Existing regular owners are never adopted, recovered, reset or logged
in by personal startup. Use the ordinary account/team workflow for retained
installations. Desktop tickets use the same session rotation, CSRF, origin,
membership, disabled-account and MFA boundaries as ordinary accounts. Enabling
an authenticator still requires its normal challenge. The generated personal
password is random and unretained; desktop sign-in is authorized by the local
operator through a ticket. This is personal local access, not a team password.

Python/Node/PostgreSQL are bundled. If Windows lacks the C++ shared runtime,
Start downloads the pinned official Microsoft installer, verifies its checksum
and publisher signature, and opens normal interactive setup for license/UAC
approval. It never accepts those choices silently or restarts Windows. No runtime
download occurs when the prerequisite is already present. The shared C++ installer
is not redistributed in this archive; no DLLs are copied from the operating system.

Startup makes no GitHub/provider requests. GitHub analysis
begins only after the user confirms the URL/dates. Private repositories and live
AI retain their separate authorization/setup requirements. Imported code is never
executed. Credit still requires independent review; finance is synthetic-only.

Inspect Start.cmd, scripts/portable.ps1 and the included application source.
runtime-manifest.json records every bundled file and archive provenance.
scripts/windows-runtime-lock.json pins build inputs. Third-party licenses accompany
the runtimes. Integrity hashes are not an independent audit or publisher signature.

Build with scripts/build_windows_package.py using a sanitized manifest/source,
the pinned archives, exact installed runtime dependencies and compiled web dist.
The builder refuses an existing output directory. User/private data is never
copied into a distribution. The source ZIP intentionally lacks runtime binaries;
new users need the complete Windows package, not the developer source ZIP.

Supported target is Windows x64 with Windows PowerShell 5.1 and a normal browser.
Actual executed platform checks and separate unperformed clean-machine testing
are listed in the dated verification record. No Windows ARM build is claimed.

Runtime publisher references: [Python 3.13.16](https://www.python.org/downloads/release/python-31316/),
[Node 22.23.0](https://nodejs.org/en/blog/release/v22.23.0),
[PostgreSQL Windows distribution](https://www.postgresql.org/download/windows/), and
[Microsoft C++ setup/deployment](https://learn.microsoft.com/en-us/cpp/windows/redistributing-visual-cpp-files?view=msvc-170).
The C++ setup download is pinned by checksum and its Microsoft Authenticode
publisher is checked before execution. Installation remains interactive.

First startup may take several minutes on a busy disk while the local database is prepared. Keep the startup window open until Ready appears. Future launches reuse saved state. Stop may wait for a database checkpoint; it never deletes the data.
