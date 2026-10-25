# Coordinated backup and isolated recovery

## Scope and trust

The implemented host command supports the supplied Docker Compose PostgreSQL **17** deployment with **local object storage**. It refuses external S3 configurations and unknown persistent volumes rather than mislabeling a partial backup as complete. A cloud object store needs a separately verified, version-aware coordinated capture procedure; that automation is not included.

Run only as the authorized operator on a trusted host. All application writers and credential rotators must be in the inspected Compose deployment and all other operators must agree not to write during capture. The tool cannot discover an unrelated direct SQL session, an unlabelled writer, a process outside Compose or a remote copy job. Stop those explicitly. Docker/host administrators remain trusted.

Use the project's installed Python environment, its existing `cryptography` dependency, Docker CLI, locally built `contribution-ledger-api:0.16.2-phase16` helper image, and the installed database image. Helpers use `--pull never`; backup is not the time to silently obtain different executable images. Record verified image digests separately. The helper source and actual Linux Docker route were exercised in this delivery; Windows Docker Desktop and real deployment cutover remain separate.

Only restore **your trusted captured database**. PostgreSQL notes that restoring a dump can execute code originating in that database. Encryption authenticates possession of the recovery key, not the trustworthiness of the original database or its unrestricted administrator.

## Three separately controlled requirements

A capture produces `data.clb`, containing the custom PostgreSQL dump and local evidence/credential-ciphertext volumes; `recovery.clb`, containing configured master/signing-secret volumes and operator configuration; and a non-secret `capture.json` status record. Both encrypted bundles share an authenticated capture identity. Keep the recovery bundle separately controlled from the normal data archive. Keep the external 32-byte recovery key in a third protected location.

A source ZIP, `.env` alone, database dump alone, or encrypted credentials without their master is not a complete recovery set. Once enrolled, `auth_master` is as important as `ai_master`. Financial document bytes use `evidence_data`. Optional `github_secrets` contains signing/client material.

Both bundles are initially written to the new capture directory to permit pair verification. Move the recovery bundle to the separately controlled location immediately afterward using the operator's secure storage process. The program does not upload backups, manage an offsite service, escrow the key, or prove that two copies are independently controlled.

The archive format uses AES-256-GCM authenticated frames with a random per-bundle HKDF-derived key, an authenticated terminal frame, bounded inventories and per-file SHA-256 checks. This is a small **application-specific format**, not an independently reviewed backup encryption standard. Preserve this source/tool version so future recovery can read the format. Do not use these endpoints for arbitrary untrusted archives; there is no backup-upload API.

## Protect plaintext scratch and permissions

Choose scratch on an encrypted, operator-only disk outside the source repository. The dump, temporary ZIPs, tar files and authenticated unpacked files exist as plaintext there during the command. Temporary-directory cleanup is not secure erasure and does not remove journal, snapshot, swap or backup copies. A local filesystem administrator can still read them while the process runs.

The key, scratch and archive locations must be separate and outside the repository; symbolic links are rejected. POSIX paths are created privately. On Windows, set and verify NTFS ACLs and volume encryption yourself before running the commands. Avoid synchronized folders. Do not put secrets in command-line values or transcripts. A key **path** is accepted; plaintext passwords and key values are not command arguments.

## Capture example

Example paths are placeholders on an operator-protected disk. Do not use a shared disk without applying its access policy first. From the source root, with project Python dependencies installed:

```powershell
python scripts/recovery.py keygen --key-file C:\LedgerRecovery\keys\recovery.key
python scripts/recovery.py backup --project contribution-ledger --env-file .env --key-file C:\LedgerRecovery\keys\recovery.key --scratch C:\LedgerRecovery\scratch --output C:\LedgerRecovery\captures\before-phase14 --confirm STOP-WRITERS:contribution-ledger
```

`keygen` refuses to overwrite an existing key and never prints it. Keep the key for those bundles; generating a different key does not rotate existing archives.

The backup preflight checks configuration inputs, project identity, a running database, recognized volume inventory, local storage and helper image. It stops all other labelled project containers, including API, web, optional workers and schedulers. It leaves writers stopped, even after success or error. It does not remove containers or volumes.

It runs `pg_dump --format=custom --no-owner --no-acl`, rejecting command failure or dump warnings; captures every recognized non-database volume; encrypts both bundles; then fully authenticates, enumerates and hashes both bundles again. `capture.json` can report **archive integrity verified**, never **native restore verified** merely from capture.

`--recovery-file logical-name=path` adds another bounded private configuration input. Use it for a verified runtime worker configuration or TLS material where required; there is no automatic crawl for secrets. For the separate staging project, specify its exact project name and `.local/staging/operator.env`, and deliberately include its TLS certificate/key and readiness/operator records as recovery inputs. The standalone staging configuration is not discoverable by inspecting the normal pilot.

After a failed capture, preserve the source and inspect whether any writers remain stopped. A partial output with no successful `capture.json` is not a completed backup. Use a new destination for a new attempt. Do not blindly resume work or delete volumes.

## Isolated native restore example

Use a new `ledger-restore-*` name. The target cannot already have containers or volumes. The restore needs both bundles, the external key and their recorded PostgreSQL image locally available:

```powershell
python scripts/recovery.py restore --target ledger-restore-drill01 --data C:\LedgerRecovery\captures\before-phase14\data.clb --recovery C:\LedgerRecovery\protected\before-phase14-recovery.clb --key-file C:\LedgerRecovery\keys\recovery.key --scratch C:\LedgerRecovery\scratch --output C:\LedgerRecovery\drills\drill01 --confirm RESTORE-ISOLATED:ledger-restore-drill01
```

It authenticates the pair and validates inventory before creating a target. File extraction rejects traversal, absolute paths, symlinks, hardlinks, devices, duplicate entries and excessive size/count. Recovery is limited to 100,000 files and a 20 GiB framed bundle; larger installations need another reviewed approach.

The tool restores only new volumes, starts PostgreSQL with `--network none` and **no host port**, and runs helper containers in that isolated database network namespace. No UI, broker, webhook, integration worker or paid call is started. It uses `pg_restore --exit-on-error --single-transaction`, then applies current forward migrations.

The verifier reconstructs contribution projections, reproduces every frozen distribution, hashes every required retained local artifact and finance document, decrypts active provider credentials, and decrypts retained MFA seeds. It never displays the decrypted secrets or calls their providers. Intentionally retired objects are counted separately. A missing required blob or wrong key fails verification.

Only after these checks does the isolated workflow invalidate copied browser sessions, recovery tokens, pending invitations and first-owner setup tokens. Passwords, MFA identities and contribution/financial history remain. A successful `restore-report.json` records actual counts, no published ports, no workers, and native verification. A failed target is left isolated for inspection; it is not removed automatically.

The captured database image is restored as captured, including an older patch when drilling a pre-upgrade backup. Keep it isolated. Test its deliberate patch upgrade separately before any cutover. No source database is downgraded or overwritten.

## Restore does not equal cutover

The restore creates a private `isolated-runtime.env` with new database credentials. It preserves original configuration for review but never applies it automatically. Service roles, grants, database function ACLs, outside secrets, certificates, DNS, invitations and worker scheduling require explicit review and reprovisioning. `--no-acl` means source privilege grants are **not** a recovered least-privilege proof.

Before deliberate cutover: preserve the source untouched; verify the new image digests and dependencies; provision/recheck all required roles and function grants; revoke copied access; validate the restored UI and MFA; check artifact previews, every distribution replay and external-key status; review retained packet data; rotate any externally compromised credentials; confirm all integration jobs remain paused. Use the restricted staging gate, not an automatic network switch. Record operator, date, capture ID, target ID, checks and unresolved limits.

No in-place restore command, source deletion, automatic compensation mode, uptime guarantee or production approval is provided. Rollback of immutable migrations with real rows uses this coordinated recovery route, not destructive Alembic downgrades.

## Verification in this source delivery

September 22, 2026: the native PostgreSQL 17.11 drill passed using two new synthetic databases. It captured/authenticated paired archives, restored a real custom dump plus local objects and separate masters, reapplied forward migrations, reproduced a 100,003-cent frozen financial close, verified one uploaded evidence object and one financial document, decrypted one synthetic credential and one MFA seed, invalidated copied sessions and rejected a wrong master. The source remained intact and no restored worker started.

The actual Docker operator route separately passed stopped-writer backup and restoration into fresh volumes with `--network none`, no published ports and no restored application/worker. Its marker database proves orchestration; the richer financial fixture above proves native retained-state replay. During verification, a real restricted-volume import failure was fixed by applying permissions before transferring ownership, preserving the existing capability restrictions.

The full backend suite also exercises tampered/missing bundles, unsafe archive members, missing retained documents and recovery boundaries. These are synthetic tests, not an S3 capture, independent encryption audit, Windows Docker Desktop execution or live cutover. Read `docs/test_results.json` for the exact results and separate boundaries.

Primary operational references: https://www.postgresql.org/docs/current/app-pgdump.html and https://www.postgresql.org/docs/current/app-pgrestore.html .
