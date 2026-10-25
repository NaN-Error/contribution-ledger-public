# Private evidence storage operations

The default is local storage; no cloud account, network call or API key is required. This remains a development/test pilot. Do not expose it publicly or call its optional S3 adapter a verified production deployment.

## Default Docker configuration

The API runs as UID 10001 with a read-only container filesystem except approved temporary paths and its private evidence volume. `evidence_data` mounts at `/var/lib/contribution-ledger/evidence` **only in the API service**. The image creates the destination with owner appuser and mode 0700. Named-volume ownership initialization and Windows Docker behavior still require an actual runtime test. The web service never mounts this store; there is no static artifact directory.

`CL_OBJECT_STORAGE_BACKEND=local`, `CL_OBJECT_STORAGE_ROOT=/var/lib/contribution-ledger/evidence` and a 256 MiB recorded-object allowance are set explicitly by `compose.yaml`. Container restarts and normal `stop` preserve both `postgres_data` and `evidence_data`. `docker compose down --volumes` is destructive; do not use it during an upgrade.

For native development, set `CL_OBJECT_STORAGE_ROOT` to a private absolute directory. The default relative `.local/evidence` resolves against the API working directory, normally `apps/api`. The updated ignore rules exclude nested `.local` directories. Do not point the store at the frontend webroot, a public share, a symlink or an unrelated existing data directory. OS administrators are trusted; filesystem checks are not a sandbox against the operator.

Blob names are generated object UUIDs below a workspace UUID directory, never original filenames. Writes use exclusive creation and owner-only file mode; reads reject non-regular files, links, size mismatches and checksum changes. Only verified bounded bytes are delivered. Synchronous processing is appropriate to this small pilot's limits; it is not a high-throughput media service.

## Optional S3-compatible adapter

`S3ObjectStorage` uses an injected official boto3 client. Runtime `create_storage` can build it from operator-only configuration:

| Setting | Meaning |
|---|---|
| `CL_OBJECT_STORAGE_BACKEND` | `s3` selects the optional adapter |
| `CL_S3_BUCKET` | Dedicated existing private bucket; no bucket is automatically created |
| `CL_S3_REGION` | SDK region, default `us-east-1` |
| `CL_S3_PREFIX` | Scoped key prefix, default `evidence-v1` |
| `CL_S3_ENDPOINT` | Optional HTTPS origin for a compatible service; omit for the SDK's AWS endpoint |
| SDK credential configuration | An operator-mounted private credentials source or appropriate deployment identity; never a browser field or source-code string |

The supplied Compose file intentionally fixes the local configuration. Adding `CL_S3_*` to `.env` alone does not switch it. An operator must explicitly override the **API service environment** and mount/configure the credential source when choosing S3. No real credentials or operational S3 override are packaged. Do not paste keys into chat. Normal startup scripts use the stock local Compose file; a custom S3 deployment must consistently use its own reviewed override.

The adapter uses bounded PutObject with `IfNoneMatch='*'`, object length and SHA-256 metadata; HeadObject verifies size/metadata; GetObject verifies full bytes; DeleteObject attempts physical retirement. No public-read ACL, bucket creation, arbitrary request-controlled URL or presigned URL is generated. Keys include workspace and object UUIDs. Scope authorization remains in the API/database, not in obscurity of keys.

Require a private bucket, TLS, suitable server-side encryption, restricted credentials and reviewed backup/version lifecycle. Application credentials should have only the required object read/write/delete rights on the dedicated prefix; no bucket-policy/admin rights. S3-compatible implementations must support the adapter's conditional-write and metadata behavior. SDK endpoint/network retries do not imply an application mutation succeeded. Same request-ID replay handles a lost application response.

**Only stubbed SDK contract tests have been executed.** There was no connection to AWS, MinIO or another live provider. Test endpoint/credentials, access denial, object metadata, conditional create, timeouts, deletion/version retention and restore in a disposable permitted bucket before real use. Enabling remote storage sends allowed artifacts to that configured service; local-first no longer means all bytes stay on your computer. Team authorization/data agreements must cover it.

Switching the backend does not migrate existing objects. Every DB object record retains its backend; mismatches are surfaced as unavailable rather than looked up in an arbitrary new location. A reviewed data migration is future work. Keep the previous store and relevant backups until any migration and preservation checks are completed.

## Transaction and failure boundaries

The database owns evidence identity, access, versioning, retirement and snapshots. Blobs are immutable but are not in the database transaction. Known failed transactions attempt cleanup of only objects created by that request. Exclusive-create collisions never delete an existing object's bytes.

Before an attempted database commit, created objects are preserved: an ambiguous commit response must not lead to deleting an object that might have a committed reference. Process crashes, failed cleanup, S3 response loss and ambiguous commits may leave private **orphan objects**. There is no automatic orphan sweep in this release. Monitor actual storage usage as well as recorded quota, and do not delete anything by filename guessing. A reviewed sweep must reconcile DB references, snapshots, active/incomplete requests, store versions and backup requirements with a safety delay; background reconciliation belongs with later durable jobs/operations.

Retirement first commits a denial record, then deletes original/preview objects. On failure, application access is still blocked. An administrator can refresh and repeat the command to retry deletion. A tombstone is never automatically removed when an object is recreated externally. Versioned buckets and backups may retain old bytes; inspect provider lifecycle controls separately.

Packet availability checks are bounded but can involve several store calls per entry. Live latency/load checks, connection/read timeout tuning and durable worker behavior are unverified. Full file integrity is checked on delivery, not merely on snapshot availability display.

## Preservation and recovery

Back up the database **and** the complete protected artifact store with a consistent retention plan. A database-only backup preserves claims/hashes but not file bytes. A store-only backup preserves bytes without the authoritative access/retirement/history state. Full tested backup/restore automation remains phase 14.

For a disposable recovery test: stop mutating API traffic, capture both stores and required configuration securely, restore to a separate local installation, apply only the required forward migrations, verify existing sessions/permissions carefully, and compare exact downloaded original hashes and historical snapshot fingerprints. Confirm retired artifacts remain denied. Never overwrite the live installation to test restore.

Readiness currently covers the API/database/migration baseline, not a complete storage-health guarantee. Storage failures are surfaced by evidence operations. Do not assume the green database indicator means a configured bucket/root is accessible.
