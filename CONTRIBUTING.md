# Contributing

Open an issue describing the behavior and expected result using synthetic data.
Keep pull requests focused and run relevant checks. Do not execute code from a
repository under analysis. Never include local database state, credentials,
private repository captures, logs or personal screenshots.

Use Python 3.13 and Node 22 with the exact committed locks. Source verification:

```text
python scripts/check_publication.py
python scripts/verify_source.py
python scripts/verify_backlog.py
```

Backend: install apps/api/requirements-dev.lock and requirements-jobs.lock,
then run `python -m pytest -q` from apps/api. PostgreSQL tests require an explicitly
configured disposable loopback database ending in `_test`. Never use a personal
or shared application database for tests. Frontend: `npm ci`, `npm test`, and
`npm run build` from apps/web. Keep test outputs outside source deliveries.

Before a release, refresh release-manifest.json from tracked source files and run
scripts/verify_release.py. Maintain exact arithmetic, scoped access, immutable
credit history, independent review and the synthetic-finance boundary.
