# Incident and credential response

**Stop and contain first.** Do not let the model or application decide whether someone loses their compensation. Record the incident ID, operator, affected deployment, discovery time and what is known versus suspected. Never put live keys, source packets, MFA secrets, tokens or passwords in a shared issue.

Stop the affected optional workers/schedulers and edge gateway. A local application stop is not provider-side revocation; use the provider's account controls to revoke an exposed key. An already dispatched request may still be billed or retained remotely. Preserve uncertain-billing reservations; reconcile them rather than automatically retrying. Preserve the source database, protected audit trail and the relevant observed revisions. Disable affected local accounts or connections through the existing explicit controls, preserving contribution identities.

For an account incident, revoke sessions and use the established account recovery process with separate identity verification. Resetting a password must not remove MFA. Lost factors use `reset-mfa`, which forces re-enrollment instead of granting bypass access. Root/host compromise also exposes master keys and in-memory values; encrypting the database does not solve it. Restore into an isolated clean host, never over the only source copy.

For suspected ledger or financial inconsistency, keep affected closes blocked and run the read-only credit and frozen-distribution replay checks. Save their bounded reports. Use the existing linked dispute/adjustment records. Do not fix accounting history with ad hoc UPDATE/DELETE or replace a financial export because it is inconvenient.

For a compromised artifact, use its explicit retirement control and preserve the deletion outcome. Failed physical deletion is retried through the documented operation, not recorded as success. Inform authorized recipients that already downloaded copies, snapshots, AI packets, provider data and backups are distinct retained copies. Retirement cannot recall them.

Before resuming, record scope, corrected cause, image/dependency review, account/provider-key state, secret-store permissions, restored integrity reports and a bounded repeated test. Re-enable integrations one at a time through current authorizations; watch for stale jobs and uncertain bills. An incident close does not authorize real use or certify that no data escaped.
