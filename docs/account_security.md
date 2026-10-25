# Authenticator protection

## What the account workflow does

The user re-enters their password, receives a private setup key, adds a time-based account in an authenticator app, then proves possession by entering the current six-digit code. Parameters are SHA-1, six digits, 30 seconds. The app never sends the secret to a QR-code service and does not generate external requests during enrollment.

The setup key is returned only for that enrollment response. It is stored encrypted with AES-256-GCM under the separate `auth_master` key and bound to the account's immutable ID. A pending enrollment expires after ten minutes. It does not enable protection until confirmed. Re-enrollment cannot overwrite an already enabled factor.

Confirmation revokes earlier sessions and issues ten random, 128-bit recovery codes. Their hashes, not their plaintext, are stored. The browser displays them once in an explicit private-save screen; they are not put in local storage or an exported application report. Store them separately from the authenticator, and do not paste them, the setup key, a password or a current code into chat or an issue report.

A later correct password creates a **five-minute pre-authentication session with no authenticated project user**. It cannot read projects, evidence, finance, account settings or privileged integrations. A current unused authenticator code or a single-use recovery code is required to rotate it into a full session. Recovery codes are not password substitutes.

Each accepted time step is consumed; the same code cannot be reused for another login in that step. Clock tolerance is one adjacent step. Enrollment consumes its step too, so an immediate logout/login may require the next code. Keep the operator and authenticator clocks correct; the product does not change clock settings itself.

Failed attempts are bounded by account and peer rate limits. CSRF and exact-origin checks apply to the factor routes. Session and factor locks serialize the critical operations in PostgreSQL; native concurrency tests are supplied but remain unexecuted here. SQLite tests cannot prove cross-process serialization.

## Local versus restricted staging

Local users may leave MFA disabled. Once enabled, it is enforced on their subsequent sessions even if the deployment does not require it globally. Disabling a local factor requires the current password and an unused second factor, and revokes sessions.

Restricted staging requires MFA for **all** accounts, including administrators, before project access. It cannot be disabled there through the UI. Existing non-MFA sessions are not promoted into verified sessions. First-owner and invitation setup still use their existing one-time private tokens; setup does not bypass mandatory enrollment.

## Lost factor or key

A password reset does not disable MFA. Use an unused recovery code with the password, or contact the operator for independently verified recovery. A lost authenticator and lost codes require an explicit account-specific operator command:

```powershell
docker compose exec -T api python -m app.cli reset-mfa --email person@example.test --reason "Verified the intended account owner using the agreed recovery procedure" --confirm "RESET-MFA:person@example.test"
```

The command is an operator tool, not an HTTP endpoint. Verify the actual person through the team's agreed separate channel before running it. A reason string does not prove identity. The reset revokes sessions, records an operator audit event, and requires fresh enrollment even on a local deployment; it does not grant a password-only session project access.

For restricted staging, execute the command through its documented operator service, not its limited API role. Do not substitute an administrator's factor for the user's identity.

If the **master file** is missing or wrong, restore the original file from protected recovery material before verifying factors. Initialization refuses to replace a missing key over existing factor ciphertext. In this version, even recovery-code verification first needs the retained factor key to be available. No automatic online MFA-master rotation is implemented; use the coordinated runbook rather than replacing the file by hand.

## Security boundary

Time-based authenticator codes improve the password-only boundary but are **not phishing-resistant**. A phisher can relay a current code. The operator, database superuser, host administrator, compromised application process or a malicious browser can still undermine the system. Seeds in process memory, already displayed secrets and old backups are not recalled by revocation. The Windows operator must apply suitable NTFS ACLs; POSIX mode flags alone do not establish Windows access control.

The implementation follows the protocol in RFC 6238 and checks its published SHA-1 test vectors. It has not received an independent MFA or cryptographic security audit. Primary references: https://www.rfc-editor.org/rfc/rfc6238 and https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html .

## API additions

All routes use the existing same-origin cookie/CSRF boundary. `GET /api/v1/auth/mfa/status` shows the current account's factor state and master availability, never its secret. `POST /enroll` (under that prefix) accepts a password. `POST /confirm` accepts a code and returns a rotated session with one-time recovery codes. `POST /verify` accepts a code for a password-verified pending session. `POST /disable` accepts password plus code and is refused when mandatory MFA applies. `/api/v1/auth/session` adds `mfa_required` and `mfa_enrolled`; a pending session's `user` is null.
