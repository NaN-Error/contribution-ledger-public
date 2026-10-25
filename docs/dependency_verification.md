# Installed dependency verification

Current source: **0.16.2-phase16**, verified September 22, 2026. See ADR 0017 and docs/test_results.json for exact scope and results.

## Installed environments

The supplied original Python locks, including optional jobs, installed into a clean Windows Python 3.13.14 environment and passed `pip check`. The corrected pins then installed into a separate clean environment and passed `pip check`, focused regression, real browser scenarios and native paired recovery. Linux CI separately installs those exact locks and runs the complete backend suite with PostgreSQL 17.11 and Redis 7.4.11.

Portable Node 22.16.0/npm 10.9.2 installed the exact original frontend versions. All 47 package integrity entries were completed from their exact registry metadata; a fresh `npm ci` passed. All 436 Node tests and the complete `tsc --noEmit && vite build` passed on Windows and Linux. The application metadata changed to 0.16.1, but no frontend dependency version changed. The bundle-size warning is nonfatal.

The installed Python advisory scan found 31 records, including duplicate aliases, across seven distributions. Deliberate replacement pins are:

| Package | Original | Current |
|---|---|---|
| anyio | 4.13.0 | 4.14.2 |
| click | 8.1.8 | 8.3.3 |
| cryptography | 46.0.4 | 50.0.0 |
| fastapi | 0.128.2 | 0.133.0 |
| packaging | 25.0 in runtime/dev; 26.0 in jobs | 26.0 throughout |
| pydantic-settings | 2.14.1 | 2.14.2 |
| pip installer | 26.1.2 | 26.2 |
| pytest | 9.0.2 | 9.0.3 |
| starlette | 0.50.0 | 1.3.1 |

FastAPI 0.133.0 is the earliest later release whose metadata accepts the required Starlette version. Packaging alignment resolves the inherited jobs/runtime discrepancy. The API/container/CI Python pin is now 3.13.14, matching the tested Windows patch. Other dependency versions remain unchanged. Installed `pip-audit` and `npm audit` report zero known vulnerabilities at this checkpoint. These are point-in-time database checks, not independent security certification.

Starlette still accepts the pinned httpx test client but emits a deprecation warning for its future replacement. The tests run successfully; no unrelated client migration was introduced. Node image/CI stays 22.16.0, PostgreSQL stays 17.11 and Redis stays 7.4.11. Actual Docker images were built/pulled in Linux CI. Tags remain patch-version references rather than immutable digest pins; Python requirements are exact version locks, not complete artifact hash locks.

## Reproduce

```text
python -m pip install pip==26.2
python -m pip install --no-deps -r apps/api/requirements-dev.lock
python -m pip install --no-deps -r apps/api/requirements-jobs.lock
python -m pip check
cd apps/web
npm ci
npm test
npm run build
```

Use a separate environment and the documented disposable test database. Do not float versions or skip semantic checking to bypass a failed install. Advisory tooling is separate from application dependencies. Recorded original locks/reports remain historical provenance in the baseline commit and September 14 verification files.

Primary references: [FastAPI metadata](https://pypi.org/project/fastapi/0.133.0/), [Starlette advisories](https://github.com/Kludex/starlette/security/advisories), [cryptography advisories](https://github.com/pyca/cryptography/security/advisories), [AnyIO TLS advisory](https://github.com/agronholm/anyio/security/advisories/GHSA-82r6-8w77-94w6), [official PostgreSQL Ubuntu packages](https://www.postgresql.org/download/linux/ubuntu/). Registry downloads are build-time operations; the manual workflow needs no provider account.
