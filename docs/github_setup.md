# GitHub setup for the local pilot

Source version `0.8.0-phase8`. This is an optional, customer-controlled integration. The manual contribution workflow still runs with GitHub disabled. No user has to provide credentials until deliberately testing this integration. Never put private keys, client secrets, temporary OAuth codes or bearer tokens in chat, issue comments, source control, screenshots or release archives.

## 1. Start and preserve the manual installation

Use the existing `scripts/start.ps1` or `scripts/start.sh` procedure first. Existing owners keep their account; do not bootstrap again. Read `upgrade_phase8.md` and preserve the database and evidence volumes. Use a synthetic test project and a small repository whose owner authorizes this test. This is not a public hosted service or an invitation to import third-party private code.

## 2. Register an operator-controlled GitHub App

In GitHub account or organization settings, open Developer settings → GitHub Apps → New GitHub App. GitHub's interface and organization approval rules can differ; the current primary references are at the end of this guide. Use a descriptive local-development name and the application's local homepage. Set the **user authorization callback URL** to exactly:

```text
http://127.0.0.1:5173/github/callback
```

Use your configured web port instead of 5173 when different. Keep the spelling `127.0.0.1` consistent when opening the ledger; `localhost` is a different browser-cookie origin. This is a browser redirect back to your own computer, not a publicly reachable webhook. No tunnel or public webhook is needed in phase 8.

Leave automatic OAuth authorization during installation disabled: this application starts its own session-bound state/PKCE flow after a local administrator signs in. Device flow is unused. Disable the webhook's Active option for this phase; phase 9 adds its receiver. Do not paste the callback URL as a working webhook URL.

Set **repository permissions** to read-only for Contents, Issues, Pull requests and Checks. Metadata read is required as well. Request no write, administration, organization, or account permissions. The implementation deliberately rejects installations with write permissions rather than quietly using a more powerful installation. Keep expiring user tokens enabled. Restrict where the app can be installed as appropriate for the pilot; do not advertise this development app for public use.

Create the app, note its numeric **App ID** and distinct **Client ID**, generate a **client secret**, and generate/download the **RSA private key**. Install the app on the authorized account/organization, choosing **Only select repositories** and the intended test repository. Organization approval or an active SAML session may be required by that organization. The connection flow only offers repositories where the authorizing GitHub user is reported as an administrator; ordinary read access is not sufficient permission to share a private repository into this project.

The **installation ID** is different from the App ID. It is the numeric ID shown in the installed-app configuration URL/installation information. It will be entered into the browser later and is not treated as authorization by itself.

## 3. Stage credentials without putting them into `.env`

Create `.local/github-secrets/` beneath the project root. This directory is ignored by version control and Docker build context. Save the original RSA PEM as `github-private-key.pem`, and save only the generated client-secret value as a plain UTF-8/ASCII file named `github-client-secret`, without an extension or byte-order mark. A trailing newline is accepted. Do not save a token, JSON object, quoted value or the App ID in that file.

Protect this staging directory with your operating system's access controls. On Windows, use the directory's Properties → Security settings to restrict it to the operator and required system administrators; avoid public/shared or automatically cloud-synchronized directories. On Unix, restrict the directory to mode 0700 and files to 0600. A gitignore rule is not access control. The downloaded original and backup copies are secrets too.

Only these **non-secret** values belong in the existing `.env`:

```dotenv
CL_GITHUB_APP_ID=YOUR_NUMERIC_APP_ID
CL_GITHUB_CLIENT_ID=YOUR_APP_CLIENT_ID
CL_GITHUB_AUTHORIZATION_HOURS=24
CL_GITHUB_PROJECT_QUOTA_BYTES=134217728
```

Replace the first two placeholders with the actual IDs. Preserve the existing database password and other settings. The optional Compose overlay explicitly enables GitHub; normal base startup leaves it off.

Run from PowerShell in the project root:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\github.ps1 -Action provision
```

Read the prompt and type `PROVISION GITHUB SECRETS` only when ready. This explicitly stops the API and import worker, validates both credential files, and copies them into the private `github_secrets` Docker volume with restrictive Linux permissions. Runtime API and worker containers mount that volume read-only. This avoids mistaking Windows bind-mount permission bits for useful Windows ACL protection. The provisioning container has no network and is the only supplied service with a writable secret mount. No credentials are printed.

The two replacements are atomic per file, not atomic as a pair. Keep consumers stopped during rotation. After an interrupted provision, fix the cause and rerun before starting services. The volume is not encrypted by this feature; Docker administrators, host administrators and unprotected backups remain trusted boundaries. Protect both host staging files and volume recovery material.

Then start the explicitly enabled services:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\github.ps1 -Action start
```

Linux/macOS equivalents are `bash scripts/github.sh provision` and `bash scripts/github.sh start`. First-time builds need package/image download access. These scripts are supplied but Docker/Windows execution has not been verified in the current build environment.

## 4. Authorize and select repositories

Open the ledger at the exact callback origin, sign in as a project administrator, select the project, and open **GitHub**. Enter the installation ID and a reason for the connection. Continue to GitHub, authorize using the intended account, and return to the callback screen. Verify the returned authorization explicitly, then inspect the account/installation and offered repository list. Select the repository or repositories to share and confirm the reason and sharing choice.

The backend checks the current local session, a one-use 10-minute state value, PKCE, accessible GitHub installations, App ownership and read permissions, and the user's repository-administrator flag. The saved repository selection must come from the reviewed proof. A guessed installation ID, another user's state, expired proof, altered hash or arbitrary repository list cannot complete this flow.

The callback query is removed from the browser URL before API verification; the temporary code is held in memory, not browser storage. Refreshing, signing out or losing that memory requires a new authorization attempt. Failed/ambiguous exchanges are not blindly retried with the same code. No GitHub user token or refresh token is stored in the database. Discarding a token is not the same as revoking the GitHub authorization grant; manage that grant in GitHub when appropriate.

The verified sharing authority lasts at most 24 hours, configurable to 1–24 hours for the pilot. Before expiry, the installation/repository access and local project authority are checked again as work proceeds, but GitHub **user-role changes are not observed in real time** because no user token is retained. Reauthorize after expiry. This local expiry is not GitHub's bearer-token lifetime. Phase 9 adds revocation/event reconciliation; do not regard the current profile as production authorization monitoring.

## 5. Run, pause and disconnect

Creating an import is explicit and separate from connecting repositories. The worker must be running to process saved jobs. Use `-Action status` to inspect services, `-Action logs` to follow sanitized worker logs, `-Action pause` to stop the worker, or `-Action step` to run one checkpoint. Queued state remains in PostgreSQL. A powered-off computer does not import anything.

Use the browser's **Disconnect** for a specific connection: it disables selected repositories and cancels unfinished associated imports while retaining captured evidence. GitHub-side App uninstall/repository removal is separate. To disable all external GitHub calls on this installation, use `-Action manual`: it stops the separate worker and recreates the base API/web without the GitHub profile. Do not assume starting the base API alone will stop an already-running worker.

After credential rotation, provision with consumers stopped, restart, and begin fresh authorization attempts. For a GitHub-side revocation, revoke the credential/installation there as appropriate as well. Captured history, explicit work-package links, database backups and previously downloaded copies are not erased by disconnecting.

## Primary references checked September 14, 2026

These describe provider behavior, not a claim that a live test succeeded:

- Registration and permissions: https://docs.github.com/en/apps/creating-github-apps/registering-a-github-app/registering-a-github-app
- OAuth state/PKCE/user authorization: https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/generating-a-user-access-token-for-a-github-app
- Installation/user-accessible repositories: https://docs.github.com/en/rest/apps/installations
- Installation token scoping: https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/generating-an-installation-access-token-for-a-github-app
- JWT authentication: https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/generating-a-json-web-token-jwt-for-a-github-app

The implementation pins REST API version `2026-03-10`. Recheck provider documentation before a deployment or changing the adapter. GitHub.com is the only supported host; GitHub Enterprise Server/custom URLs are not supported.
