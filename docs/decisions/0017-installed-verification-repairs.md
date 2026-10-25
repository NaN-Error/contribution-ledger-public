# ADR 0017 — Installed verification and targeted repairs

Date: September 22, 2026. Baseline: supplied 0.16.0-phase16 source. Candidate: 0.16.1-phase16. No migration change.

## Decisions

Complete actual dependency installation, typechecking/building, PostgreSQL, browser and recovery checks before handing the candidate back for fictional local use. Preserve the original folder and work in a separate copy. Record failed attempts and unavailable services separately from successful reruns.

Register the complete SQLAlchemy model graph when constructing `Database`. A standalone AI worker previously failed when a foreign key referenced a model registered only by other entry points. This registration performs no connection, migration or privilege grant. Test cold worker and operator entry points in separate processes.

Retain successful model-probe queue feedback in the catalog parent. Refreshing the model collection can unmount the individual model action component; its previous local notice disappeared before a user could see it. No catalog/profile authorization semantics change.

Prepare new synthetic database schemas for the previously uninvoked feature browser scripts. Use existing application commands, explicit local opt-ins, disabled live flags and preserved diagnostic state. Prepared finance views use a documented synthetic clock. Run those browser scripts in CI as well as the existing account workflow, which already invokes several subsidiary scripts.

Repair the historical-upgrade test by creating accounts before its guarded downgrade, checking retained phase-2 rows, then applying forward migrations twice before invoking current ORM code. A current session model is not a valid application for an old schema. Preserve every original migration byte.

Use actual Windows DACL principals for object-storage permission assertions. Keep native hard-link rejection; explicitly record the unsupported POSIX FIFO check on Windows. The Docker credential-volume staging command fails before writes on a non-POSIX host. Read-only mounted-secret fixtures use read-only files.

Preserve monorepo paths in the web Docker build stage and copy the gateway source imported by its tests. The runtime image still receives only the built assets and proxy. Preserve exact source bytes in Git so the same manifest works after either Windows or Linux checkout.

## Dependency repair

The baseline npm versions install and build without bypassing typechecking. Complete all 47 registry integrity values without changing frontend dependency versions.

An actual installed advisory scan requires deliberate Python updates: AnyIO 4.14.2, Click 8.3.3, cryptography 50.0.0, pydantic-settings 2.14.2, pytest 9.0.3 and Starlette 1.3.1. FastAPI 0.133.0 is the first later published release permitting that Starlette version. Align shared packaging at 26.0; pin installer pip 26.2 and Python container/CI runtime 3.13.14, matching the tested Python patch. Other dependency versions remain unchanged. The new environment passes `pip check` and the installed advisory rescan reports no known vulnerabilities. This is a point-in-time database result, not an independent security audit.

References: [PyPI version metadata](https://pypi.org/project/fastapi/0.133.0/), [Starlette advisories](https://github.com/Kludex/starlette/security/advisories), [cryptography advisories](https://github.com/pyca/cryptography/security/advisories), [AnyIO advisory](https://github.com/agronholm/anyio/security/advisories/GHSA-82r6-8w77-94w6), [Python filesystem semantics](https://docs.python.org/3.13/library/os.html#os.mkdir).

## Recovery and acceptance boundaries

The native recovery runner creates two new synthetic databases, captures a real PostgreSQL custom dump plus local objects/credential ciphertexts and separate masters, authenticates paired bundles, restores, reapplies forward migrations, replays the frozen distribution, decrypts retained credentials/factors and invalidates copied access. It preserves the source and starts no restored worker. A separate CI step exercises the actual Docker operator capture/restore route; its result must be recorded separately.

These checks do not establish provider permissions, real model quality, independent human review of actual work, a two-period pilot, production readiness or real financial authority. Finance stays synthetic-only. AI receives no new ledger, raw-evidence or finance permission. No source repository under evaluation is executed.

The actual Docker recovery rerun confirms the restricted transport repair: chmod runs before chown, so CAP_FOWNER is not needed after ownership is transferred. Keep all existing capability restrictions. Linux native-client setup uses the signed official PostgreSQL apt repository; upstream version checks tolerate package suffixes without accepting another major version. Current complete results are in docs/test_results.json.
