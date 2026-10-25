# Accounts, roles, and operator actions

## Setup and sessions

The trusted host operator issues a single-use, one-hour setup token using `scripts/setup-owner.ps1`. Its hash and expiry are stored in the database. Browser setup creates the first account, one workspace and one project in one transaction. There is no public registration and no default password. Normal startup does not regenerate credentials.

A signed-in browser uses an opaque HttpOnly cookie, never a JWT or a token in localStorage. Passwords use Argon2id. Session, invitation and recovery secrets are stored as purpose-separated hashes. The CSRF synchronizer token is held only in page memory. Signed-in sessions expire after 30 minutes without application activity or eight hours overall by default; background session checks do not extend inactivity. At most ten unrevoked, not-absolutely-expired sessions are retained per account. The sessions screen notes that a listed session may already be idle-expired.

Sign-out revokes the current session. Password change requires the current password, revokes previous sessions and recovery tokens, and rotates the current cookie. Revoking another listed session affects that session's subsequent requests. Already received content cannot be erased from another browser's memory or downloads by revocation.

## Access matrix

| Role | Scope and present authority |
|---|---|
| Workspace owner | Own workspace, all its projects, invitations, membership administration; may assign another owner. Cannot remove the last active owner. |
| Workspace administrator | Own workspace/projects and ordinary memberships; cannot grant/change owner or administrator membership. |
| Workspace member | Workspace name and explicitly granted projects, not the team roster/invitations/audit administration. |
| Project administrator | Settings and explicit project grants for that project, using already-active workspace members. No automatic workspace-administrator powers. |
| Project contributor, reviewer, finance, viewer | Separate stored role identities; currently read-only project detail. Their feature-specific write permissions arrive in later phases. |
| Host operator | Authorized local CLI setup/recovery/disable/enable/pruning and synthetic fixtures. No HTTP impersonation endpoint and no automatic browser access to every workspace. |

An account may create another workspace and becomes its owner. This does not reveal anyone else's workspace. Up to 100 memberships per account and 100 projects per workspace are supported in the local pilot; project/team lists target small teams. Invitation and audit histories are paginated. Scopes are checked on the server using active membership and workspace-bound references. Missing/inaccessible foreign records return 404 instead of confirming their contents. Having admin status does not satisfy independent-review requirements; actual award/review endpoints do not exist yet.

## Invitations

Open a workspace → Invitations. Select an email, workspace role, optional initial project/role, expiry (1–168 hours), and reason. The new token/link appears only in the creation response and can be hidden immediately. Send it privately to the intended person after checking their identity. No email is sent. A link to localhost reaches only the same computer; use separate browser profiles for local tests rather than making the app public.

The invited person checks the invitation, then creates their account with the invited email or signs in to the matching existing account. The invitation does not change an existing password. The server checks token state/expiry, current issuer authority, account status and scope again at acceptance. Tokens are single-use; a new pending invitation for the same email/workspace revokes the older one. Existing memberships are not silently promoted or reactivated. After acceptance, use membership management for later changes; revoking the old invitation does not remove the accepted account.

Secrets are removed from the fragment after page initialization and not stored in browser storage. Browsers/extensions/clipboard users may still have seen the link: treat it as a credential. Reloading an unfinished invitation screen may require privately pasting its token again.

## Changes, suspension, and history

Administrators submit a reason and expected version. Stale updates return 409 instead of overwriting a newer decision. Workspace suspension revokes the user's current sessions, suspends explicit project grants, and revokes pending invitations they issued in that workspace. The user may sign in again but has no access to the suspended workspace. Restoring workspace membership does not silently restore old project grants; restore those explicitly. A project-only suspension denies future project requests without erasing identity.

Changing a project grant cannot remove inherited workspace-administrator powers; change the workspace role instead. Active-owner checks prevent orphaning a workspace. Audit events record actor, target, scope, reason, and approved change metadata. Database triggers reject ordinary UPDATE/DELETE of audit rows. This is not protection against an all-powerful database operator and not a legal signature. All historical contributor identities are retained; actual financial/contribution history comes later.

## Recovery and global disablement

The operator must verify the person's identity and their own authority using a trusted channel before running:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\account.ps1 -Action recover -Email "person@example.test" -Reason "Verified account owner requested recovery"
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\account.ps1 -Action disable -Email "person@example.test" -Reason "Authorized operator suspended this account"
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\account.ps1 -Action enable -Email "person@example.test" -Reason "Authorized operator restored this account"
```

The wrapper asks you to retype the account email. Recovery prints a one-time 30-minute token, invalidates older recovery tokens and revokes existing sessions. Give it only to the verified account owner. They use Account recovery to set their own password and then sign in normally. Recovery is not automatic sign-in and never enables a disabled account. Issuing a recovery token alone does not replace the current password; completing recovery does. Global disablement rejects a last-active-owner account until another active owner has been assigned in each affected workspace.

Disable/enable is local-operator-only, audited, and revokes sessions. Disabling also revokes pending invitations issued by the account. Enabling does not remove separately suspended workspace/project memberships. No reset password is put in command-line arguments or chosen for the user by the operator. No self-service email reset, MFA or enterprise SSO is implemented.

Linux/macOS: `bash scripts/manage.sh account recover person@example.test "Verified account owner requested recovery"`; replace recover with disable or enable as appropriate. `bash scripts/manage.sh prune-auth` removes session/recovery records expired over seven days ago, never audit history. It is manual until the scheduler phase.

## Synthetic team

After first-owner setup, `scripts/seed-team.ps1` (or `bash scripts/manage.sh seed-team`) asks for `CREATE SYNTHETIC TEAM`. With development tools explicitly enabled, it creates two isolated workspaces, two owners, five contributors and a separate fictional reviewer, and prints random passwords once. Repeating the command is refused rather than resetting passwords. Synthetic accounts never establish independence for real reviews. The first real owner does not automatically gain browser access to the synthetic workspaces.
