# Ledger integrity and operator procedures

This build is a local synthetic pilot. Application role checks and immutable-table triggers are not a security certification. Default Compose's database account owns its schema; it is powerful. Before remote use, split migration, runtime, analysis and repair identities, review all inherited/default privileges, and run the native permission tests. infra/ledger-privileges.sql is optional psql provisioning for the new tables only and is never invoked on startup. Grant no credit-writer role to future AI workers. Do not expose PostgreSQL publicly or paste connection secrets into chat.

## Check without writing

From the project root, use the actual workspace and project UUIDs:

```powershell
docker compose exec api python -m app.cli check-credit --workspace-id WORKSPACE_UUID --project-id PROJECT_UUID
```

The JSON result identifies projection differences without dumping private artifacts or credentials. Exit 0 means consistent; exit 1 indicates a failed/refused check or drift. The administrator's `/contributions/integrity` API provides the same read-only accounting check. Neither is a global database audit or proof that original decisions were fair.

## Rebuild derived projections only

Back up and inspect the cause of any drift first. This command does not choose new recipients, rewrite awards or delete ledger entries:

```powershell
docker compose exec api python -m app.cli check-credit --workspace-id WORKSPACE_UUID --project-id PROJECT_UUID --repair --confirm "REBUILD-PROJECTIONS:PROJECT_UUID" --reason "Explain the authorized cache reconstruction here."
```

Replace PROJECT_UUID in both places with the same actual UUID. A literal placeholder, wrong confirmation, wrong scope or short reason is refused. Locks use the same tenant→milestone→package ordering as normal writes. Before/after differences are recorded, then the derived balances and issued projections are rebuilt in one transaction from immutable events/awards. Contradictory or negative ledger history or awards beyond budgets require explicit investigation; a rebuild cannot legitimize invalid source records. The routine is an operator-only CLI, not a web endpoint or a future AI capability.

## Preservation and backups

Preserve `.env`, `postgres_data`, `evidence_data`, configuration and protected recovery material. Database rows contain decisions, artifacts metadata, immutable snapshots, credit events and deny-on-retirement state. Artifact bytes live separately. Restoring only one store can produce unavailable evidence; do not reinterpret that as zero credit. Expired/retired raw files cannot silently reduce accounting balances. Old distributions in later phases must reconstruct from stored decisions without AI calls.

An infrastructure operator can still alter a database outside ordinary privileges, destroy disks or restore an older backup. Append-only application history is not cryptographic tamper-proof storage. Keep verified backups, controlled administrator access, independent review and operating logs. Actual restore, native DB-role tests and external S3 retention remain future acceptance gates.
