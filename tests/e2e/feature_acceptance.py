"""Prepare isolated synthetic fixtures and execute the remaining rendered checks.

Requires installed locks, built frontend, Chromium, loopback PostgreSQL *_test,
development tools and CL_E2E_ALLOW_FEATURE_FIXTURES=1. Creates a NEW schema and
private .local directory on every run. Never resets accounts or removes schemas.
No live GitHub/provider calls, screenshots, paid requests or real payments.
The temporary loopback API and web processes stop when this runner exits.
"""
from __future__ import annotations

import importlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
from unittest.mock import patch
from uuid import UUID, uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'apps/api'))
sys.path.insert(0, str(ROOT / 'scripts'))


def validate_target(settings, opt_in: str | None) -> None:
    if opt_in != '1':
        raise ValueError('Explicit synthetic feature-fixture opt-in is required.')
    settings.require_development_tools()
    if settings.db_host not in {'127.0.0.1', 'localhost'} or not settings.db_name.endswith('_test'):
        raise ValueError('Use only a disposable loopback PostgreSQL *_test database.')
    if settings.github_enabled or settings.ai_live_enabled or settings.ai_paid_probes_enabled or settings.ai_evidence_enabled:
        raise ValueError('All live integrations must be disabled for these fixtures.')


def rendered(module: str, values: dict[str, str], report: dict, path: Path) -> None:
    with patch.dict(os.environ, values):
        importlib.import_module(module).main()
    report['checks'][module] = 'passed'
    path.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')


def main() -> None:
    from alembic import command
    from fastapi.testclient import TestClient
    import httpx
    import pytest
    from sqlalchemy import create_engine, text
    import uvicorn
    from app.core.config import get_settings
    from app.db.migration import migration_config
    from app.db.session import Database
    from app.main import create_app
    from app.projects.models import Project
    from app.security.tokens import now
    from tests.auth_helpers import PASSWORD, mutation
    from tests.phase11_helpers import setup, packet, plan, complete as assess
    from tests.phase6_helpers import assign, resolver, correction, vote, finalize
    from tests.phase13_helpers import advance_clock, complete as financial_close
    from tests.phase3_helpers import active_milestone
    from tests.phase12_helpers import approve as approve_history, manual, imported
    from replay_distribution import replay

    original = get_settings()
    validate_target(original, os.environ.get('CL_E2E_ALLOW_FEATURE_FIXTURES'))
    node = shutil.which('node')
    if node is None or not (ROOT / 'apps/web/dist/index.html').is_file():
        raise ValueError('Install Node and complete npm run build before browser acceptance.')
    schema = 'browser_fixture_' + uuid4().hex
    output = ROOT / '.local' / 'feature-acceptance' / schema
    output.mkdir(parents=True, exist_ok=False)
    report_path = output / 'report.json'
    report = {'schema': schema, 'checks': {}, 'synthetic_only': True,
              'live_requests': 0, 'human_pilot_completed': False,
              'boundary': 'Fictional multi-account UI checks; fixture preparation uses application commands. Financial preparation uses a synthetic period-end clock.'}
    # Distinct fixed loopback ports keep this independent of the main CI stack.
    api_port, web_port = 18001, 15174
    base = f'http://127.0.0.1:{web_port}'
    settings = original.model_copy(update={
        'allowed_hosts': ['127.0.0.1', 'localhost', 'testserver'],
        'allowed_origins': ['http://testserver', base],
        'object_storage_root': str(output / 'objects'),
        'auth_master_key_file': str(output / 'auth-master/master.key'),
        'ai_master_key_file': str(output / 'ai-master/master.key'),
        'ai_credential_root': str(output / 'ai-credentials'),
    })
    control = create_engine(settings.database_url(), hide_parameters=True)
    with control.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(settings.database_url(), hide_parameters=True, pool_size=10,
        connect_args={'options': f'-c search_path={schema} -c statement_timeout=10000'})
    database = Database(settings, engine)
    config = migration_config()
    with engine.begin() as connection:
        config.attributes['connection'] = connection
        command.upgrade(config, 'head')
    app = create_app(settings, database)
    client = TestClient(app, raise_server_exceptions=True)
    server = None
    thread = None
    web = None
    environment = None
    web_log = (output / 'web.log').open('w', encoding='utf-8')
    try:
        environment = setup(client, database, settings)
        env = environment
        with database.session() as session:
            session.get(Project, UUID(env['owner']['project']['id'])).name = 'Synthetic feature acceptance'
            session.commit()
        result = assess(env, plan(env, packet(env)))
        review = assign(env)
        # The submitting beneficiary remains forbidden from independent review.
        from tests.phase6_helpers import decision_body
        assert mutation(client, env['root'] + '/reviews/' + review['id'] + '/decisions', decision_body(review)).status_code == 403
        report['checks']['fixture_mock_assessment_and_self_review_boundary'] = 'passed'
        server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=api_port,
            access_log=False, proxy_headers=False, log_level='warning'))
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        deadline = time.monotonic() + 30
        while not server.started:
            if not thread.is_alive() or time.monotonic() > deadline:
                raise RuntimeError('Isolated API did not start; check the loopback port.')
            time.sleep(0.1)
        web_env = {**os.environ, 'CL_API_TARGET': f'http://127.0.0.1:{api_port}',
                   'CL_WEB_INTERNAL_PORT': str(web_port), 'CL_BIND_HOST': '127.0.0.1',
                   'CL_WEB_ALLOWED_HOSTS': '["127.0.0.1","localhost"]'}
        web = subprocess.Popen([node, 'server.mjs'], cwd=ROOT / 'apps/web', env=web_env,
            stdout=web_log, stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        deadline = time.monotonic() + 30
        while True:
            if web.poll() is not None:
                raise RuntimeError('Isolated web server exited; check its loopback port.')
            try:
                response = httpx.get(base + '/health/ready', timeout=2)
                if response.status_code == 200:
                    break
            except httpx.RequestError:
                pass
            if time.monotonic() > deadline:
                raise RuntimeError('Isolated browser stack did not become ready.')
            time.sleep(0.1)
        values = {'CL_E2E_BASE_URL': base,
            'CL_E2E_WORKSPACE_ID': env['owner']['workspace']['id'],
            'CL_E2E_PROJECT_ID': env['owner']['project']['id'],
            'CL_E2E_PACKAGE_ID': env['package']['id'], 'CL_E2E_RESULT_ID': result['id'],
            'CL_E2E_REVIEW_ID': review['id'], 'CL_E2E_SOURCE_POLICY_ID': env['policy']['id'],
            'CL_E2E_REVIEWER_EMAIL': 'reviewer@example.test', 'CL_E2E_REVIEWER_PASSWORD': PASSWORD,
            'CL_E2E_EMAIL': 'owner@example.test', 'CL_E2E_PASSWORD': PASSWORD,
            'CL_E2E_FINANCE_EMAIL': 'owner@example.test', 'CL_E2E_FINANCE_PASSWORD': PASSWORD,
            **{'CL_E2E_ALLOW_' + name: '1' for name in ('ASSESSMENT', 'CREDIT', 'SIMULATOR', 'FINANCE', 'RECONSTRUCTION')}}
        rendered('assessment_smoke', values, report, report_path)
        rendered('credit_smoke', values, report, report_path)
        dispute = client.get(env['root'] + '/disputes').json()['items'][0]
        dispute = client.get(env['root'] + '/disputes/' + dispute['id']).json()
        resolution = vote(env, correction(env, resolver(env, dispute)), who='resolver')
        finalize(env, resolution, who='resolver')
        assert client.get(env['root'] + '/contributions').json()['total_issued_atoms'] == 100000
        assert client.get(env['root'] + '/contributions/integrity').json()['consistent']
        report['checks']['linked_correction_exact_total'] = 'passed'
        rendered('simulator_smoke', values, report, report_path)
        env['month'] = now().strftime('%Y-%m')
        env['finance'] = env['root'] + '/finance'
        with pytest.MonkeyPatch.context() as clock:
            advance_clock(env, env['month'], clock)
            period, _, _, closed = financial_close(env, cents=100003)
        values['CL_E2E_PERIOD_ID'] = period['id']
        exported = client.get(env['finance'] + '/closes/' + closed['id'] + '/export?format=json')
        assert exported.status_code == 200
        export_path = output / 'synthetic-distribution.json'
        export_path.write_bytes(exported.content)
        assert replay(export_path)['amount_cents'] == 100003
        report['checks']['synthetic_financial_close_and_offline_replay'] = 'passed'
        rendered('finance_smoke', values, report, report_path)
        milestone = active_milestone(client, env['root'], env['policy'])
        body = {'request_id': str(uuid4()), 'milestone_id': milestone['id'],
            'title': 'Synthetic historical game opening', 'start_at': '2026-09-01T00:00:00Z',
            'end_before': '2026-09-12T00:00:00Z',
            'historical_scope': 'Fictional captured source and missing non-code work only.',
            'agreement_reference': 'Synthetic reconstruction fixture, no real agreement.',
            'reason': 'Exercise historical grouping without awarding units'}
        created = mutation(client, env['root'] + '/reconstruction', body)
        assert created.status_code == 201, created.text
        env['batch'] = created.json()
        env['base'] = env['root'] + '/reconstruction/' + env['batch']['id']
        approve_history(env)
        manual(env)
        imported(env)  # Injected FakeGitHub; no external connection or repository execution.
        values['CL_E2E_BATCH_ID'] = env['batch']['id']
        rendered('reconstruction_smoke', values, report, report_path)
        assert client.get(env['root'] + '/contributions').json()['total_issued_atoms'] == 100000
        report['checks']['mock_repository_grouping_did_not_award_credit'] = 'passed'
        report['status'] = 'passed'
        print('All five prepared feature browser checks passed. Fixtures are synthetic; no human pilot or live provider validation is claimed.')
    except BaseException:
        report['status'] = 'failed'
        raise
    finally:
        if web is not None and web.poll() is None:
            web.terminate()
            try:
                web.wait(timeout=10)
            except subprocess.TimeoutExpired:
                web.kill()
                web.wait()
        if server is not None:
            server.should_exit = True
        if thread is not None:
            thread.join(timeout=15)
        if environment:
            for actor in environment['actors'].values():
                actor['client'].close()
        client.close()
        database.dispose()
        control.dispose()
        web_log.close()
        report_path.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        print('Sanitized result: ' + str(report_path.relative_to(ROOT)))


if __name__ == '__main__':
    main()
