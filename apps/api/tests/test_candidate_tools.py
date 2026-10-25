import importlib.util
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[3]


def tool(name):
    spec=importlib.util.spec_from_file_location('candidate_'+name,ROOT/'scripts'/(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def sample_manifest(root):
    (root/'VERSION').write_text('synthetic-test')
    value={'version':'synthetic-test','archive_file_count':2,'files':[{'path':'VERSION','bytes':14,'sha256':hashlib.sha256(b'synthetic-test').hexdigest()}]}
    # Exact bytes reflect fixture rather than relying on the literal length.
    value['files'][0]['bytes']=len(b'synthetic-test')
    (root/'release-manifest.json').write_text(json.dumps(value));return value


def test_manifest_verifies_files_not_runtime(tmp_path):
    sample_manifest(tmp_path);result=tool('verify_release').verify(tmp_path)
    assert result['file_consistency_passed'] and result['checked_files']==1
    assert result['runtime_verified'] is False and result['release_authorized'] is False


def test_manifest_detects_changed_content(tmp_path):
    sample_manifest(tmp_path);(tmp_path/'VERSION').write_text('synthetic-bad!')
    assert not tool('verify_release').verify(tmp_path)['file_consistency_passed']


@pytest.mark.parametrize('name',['../escape','/etc/passwd','.env','secrets/key','x.pem','x.key','.local/report','C:\\secret','release-manifest.json',
    '.env.production','custom/secrets/token','personal-data/report.json',
    'custom/postgres-data/base/123/456','custom/pg_wal/0001','custom/auth-master/value',
    'custom/ai-credentials/value','custom/uploads/picture.png','custom/backups/data.json',
    'custom/exports/people.csv','postgres-password.txt','personal-installation.json',
    'processes.json','ports.json','private.db','private.db-wal','private.sqlite3-shm',
    'private.sqlite-journal','private.sql','private.sql.gz','private.log','private.pfx',
    'private.backup','private.zip','runtime/python/python.exe'])
def test_manifest_rejects_secret_or_unsafe_paths(tmp_path,name):
    value=sample_manifest(tmp_path);value['files'][0]['path']=name
    (tmp_path/'release-manifest.json').write_text(json.dumps(value))
    with pytest.raises(ValueError):tool('verify_release').verify(tmp_path)


def test_manifest_does_not_inspect_local_env(tmp_path):
    sample_manifest(tmp_path);(tmp_path/'.env').write_text('DO_NOT_READ=private')
    result=tool('verify_release').verify(tmp_path)
    assert result['file_consistency_passed'] and not result['unlisted_local_files_inspected']


def test_source_policy_preserves_secret_store_code_and_database_grants():
    from pathlib import PurePosixPath
    private = tool('verify_release').private_source_path
    assert not private(PurePosixPath('apps/api/app/security/secrets/store.py'))
    assert not private(PurePosixPath('apps/api/app/finance/exports/serialization.py'))
    assert not private(PurePosixPath('infra/ledger-privileges.sql'))
    assert not private(PurePosixPath('.env.example'))
    assert private(PurePosixPath('apps/api/app/security/secrets/accidental.key'))
    assert private(PurePosixPath('apps/api/app/finance/exports/accidental.csv'))


@pytest.mark.parametrize('name', ['../escape', '.env.production', 'custom/postgres-data/PG_VERSION'])
def test_windows_builder_refuses_private_manifest_before_creating_output(tmp_path, name):
    source = tmp_path / 'source'; source.mkdir()
    value = sample_manifest(source); value['files'][0]['path'] = name
    (source / 'release-manifest.json').write_text(json.dumps(value))
    output = tmp_path / 'distribution'
    result = subprocess.run([sys.executable, str(ROOT / 'scripts/build_windows_package.py'),
        '--source', str(source), '--output', str(output), '--python-archive', 'absent-python.zip',
        '--node-archive', 'absent-node.zip', '--postgres-archive', 'absent-postgres.zip',
        '--site-packages', 'absent-packages', '--web-dist', 'absent-web'],
        capture_output=True, text=True)
    assert result.returncode != 0
    assert 'Unsafe or duplicate source path' in result.stderr
    assert not output.exists()


def test_check_runner_does_not_inherit_live_configuration(monkeypatch):
    monkeypatch.setenv('CL_TEST_DATABASE_URL','sensitive')
    monkeypatch.setenv('CL_AI_LIVE_ENABLED','true')
    monkeypatch.setenv('CL_DB_PASSWORD','private')
    env=tool('check_candidate').safe_environment()
    assert not any(k.startswith('CL_') for k in env)
    assert env['PYTEST_DISABLE_PLUGIN_AUTOLOAD']=='1'


def test_check_commands_do_not_install_deploy_or_migrate():
    commands=tool('check_candidate').commands(ROOT)
    names={name for name,_,_ in commands}
    assert names=={'source_integrity','source_structure','synthetic_evaluation','backend_regression','frontend_helpers','frontend_build'}
    assert all('docker' not in c and 'install' not in c and 'migrate' not in c for _,c,_ in commands)
    assert 'backend_regression' not in {name for name,_,_ in tool('check_candidate').commands(ROOT,skip_backend=True)}


def test_evaluation_refuses_existing_output(tmp_path):
    from types import SimpleNamespace
    with pytest.raises(ValueError,match='output_already_exists'):
        tool('evaluate').run(SimpleNamespace(output=tmp_path))


def test_evaluation_cli_writes_no_raw_predictions(tmp_path):
    from types import SimpleNamespace
    out=tmp_path/'eval'
    report=tool('evaluate').run(SimpleNamespace(output=out,corpus=ROOT/'evals',split='calibration',allow_holdout=False,reason='',command='mock'))
    assert {p.name for p in out.iterdir()}=={'report.json','report.md','receipt.json'}
    assert report['human_pilot_periods_completed']==0


def test_empty_pilot_template_does_not_become_completed():
    data=json.loads((ROOT/'docs/pilot/observations_template.json').read_text())
    report=tool('pilot_summary').summarize(data)
    assert report['operator_declared_periods']==0 and report['observation_count']==0
    assert report['median_manual_minus_assisted_seconds'] is None
    assert report['human_pilot_verified'] is False


def pilot_data():
    return {'schema_version':'shadow-observations-v1',
      'periods':[{'id':'p1','start':'2026-08-01T00:00:00+00:00','end':'2026-08-15T00:00:00+00:00','compensation_unchanged':True,'record_reference':'local-record-1'},
                 {'id':'p2','start':'2026-08-15T00:00:00+00:00','end':'2026-09-01T00:00:00+00:00','compensation_unchanged':True,'record_reference':'local-record-2'}],
      'observations':[{'period_id':'p1','participant_alias':'reviewer-a','work_reference':'work-a','manual_seconds':120,'assisted_seconds':90,'changed_ai_finding':True,'reconstructed_distribution':None,'record_reference':'observation-a'}]}


def test_pilot_summary_is_descriptive_never_certification():
    report=tool('pilot_summary').summarize(pilot_data())
    assert report['operator_declared_periods']==2 and report['median_manual_minus_assisted_seconds']==30
    assert report['successful_reconstructions']['unknown']==1
    assert report['human_pilot_verified'] is False and report['deployment_authorized'] is False


@pytest.mark.parametrize('change',[
 lambda d:d['periods'][0].update(compensation_unchanged=False),
 lambda d:d['periods'][1].update(start='2026-08-10T00:00:00+00:00'),
 lambda d:d['periods'][0].update(start='2026-08-01T00:00:00'),
 lambda d:d['observations'].append(d['observations'][0]),
 lambda d:d['observations'][0].update(manual_seconds=-1),
 lambda d:d['observations'][0].update(changed_ai_finding='yes'),
 lambda d:d['observations'][0].update(period_id='unknown')])
def test_pilot_rejects_misleading_inputs(change):
    data=pilot_data();change(data)
    with pytest.raises(ValueError):tool('pilot_summary').summarize(data)


def test_docker_test_layout_preserves_repository_parents():
    source=(ROOT/'infra/api.Dockerfile').read_text()
    assert 'COPY --chown=appuser:appuser . /repo/' in source
    assert 'WORKDIR /repo/apps/api' in source
    web=(ROOT/'infra/web.Dockerfile').read_text()
    assert 'WORKDIR /repo/apps/web' in web
    assert 'COPY infra/webhook-gateway.mjs /repo/infra/webhook-gateway.mjs' in web


def test_onboarding_document_paths_exist():
    import re
    source=(ROOT/'apps/web/src/lib/onboarding.ts').read_text()
    for name in re.findall(r"documentation: '([^']+)'",source):
        assert (ROOT/name).is_file(),name
