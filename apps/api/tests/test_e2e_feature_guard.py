import importlib.util
from pathlib import Path
import pytest
from app.core.config import Settings


def guard():
    path = Path(__file__).resolve().parents[3] / 'tests/e2e/feature_acceptance.py'
    spec = importlib.util.spec_from_file_location('feature_acceptance_guard', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.validate_target


def settings():
    return Settings(db_password='synthetic-fixture-password-1234', db_host='127.0.0.1',
                    db_name='acceptance_test', enable_development_tools=True)


def test_feature_fixture_requires_explicit_opt_in():
    with pytest.raises(ValueError, match='opt-in'):
        guard()(settings(), None)


@pytest.mark.parametrize('change', [
    {'db_name': 'retained_application'}, {'db_host': 'db.example.test'},
    {'github_enabled': True}, {'ai_live_enabled': True},
    {'ai_paid_probes_enabled': True}, {'ai_evidence_enabled': True},
])
def test_feature_fixture_rejects_retained_remote_or_live_targets(change):
    with pytest.raises(ValueError):
        guard()(settings().model_copy(update=change), '1')


def test_feature_fixture_requires_development_tools():
    with pytest.raises(PermissionError):
        guard()(settings().model_copy(update={'enable_development_tools': False}), '1')


def test_feature_fixture_accepts_explicit_local_synthetic_target():
    guard()(settings(), '1')


@pytest.mark.parametrize(('version', 'expected'), [
    ('pg_dump (PostgreSQL) 17.11\n', True),
    ('pg_restore (PostgreSQL) 17.11 (Debian 17.11-1.pgdg12+2)\n', True),
    ('pg_dump (PostgreSQL) 16.15\n', False),
    ('pg_dump (PostgreSQL) 18.6 (Ubuntu 18.6-1)\n', False),
])
def test_native_recovery_checks_upstream_version_before_package_suffix(monkeypatch, version, expected):
    import sys
    path = Path(__file__).resolve().parents[3] / 'tests/e2e'
    monkeypatch.syspath_prepend(str(path))
    spec = importlib.util.spec_from_file_location('native_recovery_version_guard', path / 'native_recovery_acceptance.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.is_postgresql_17_version(version) is expected
