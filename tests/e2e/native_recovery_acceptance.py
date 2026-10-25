"""Opt-in native PostgreSQL recovery drill with NEW synthetic databases only.

Requires CL_E2E_ALLOW_NATIVE_RECOVERY=1, loopback *_test configuration, disabled
live integrations, development tools, and PostgreSQL 17 pg_dump/pg_restore.
Creates two uniquely named databases and private ignored files; retains both.
Never backs up a user's configured database or starts restored application workers.
This exercises native tools and archive primitives, not Docker orchestration.
"""
from __future__ import annotations
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys
from unittest.mock import patch
from uuid import UUID, uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'apps/api'))
from feature_acceptance import validate_target


def is_postgresql_17_version(output: str) -> bool:
    # Debian appends its package revision after the upstream version.
    return re.search(r'\(PostgreSQL\) 17\.\d+(?:\s|$)', output) is not None


def main():
    from alembic import command
    from fastapi.testclient import TestClient
    import pytest
    from sqlalchemy import create_engine, text
    from app.core.config import get_settings
    from app.db.session import Database
    from app.db.migration import migration_config
    from app.main import create_app
    from app.auth.mfa_crypto import FactorCipher
    from app.auth.mfa_models import Authenticator
    from app.operations.archive import create_bundle, unpack_bundle, validate_pair
    from app.operations.verify import verify_retained, invalidate_recovered_access
    from app.operations.security import initialize_auth_key
    from app.security.tokens import now
    from app.ai.models import AIConnection
    from app.ai.connections.service import key_context
    from app.security.secrets.encrypted import EncryptedCredentialStore, initialize
    from tests.phase13_helpers import finance_environment, complete
    from tests.phase5_helpers import add as add_evidence

    original = get_settings()
    validate_target(original, os.environ.get('CL_E2E_ALLOW_NATIVE_RECOVERY'))
    commands = {name: shutil.which(name) for name in ('pg_dump', 'pg_restore')}
    for name, path in commands.items():
        if not path or not is_postgresql_17_version(subprocess.check_output([path, '--version'], text=True)):
            raise ValueError('Install PostgreSQL 17 client tools for this synthetic drill.')
    identity = uuid4().hex
    source_name, target_name = f'recovery_source_{identity}_test', f'recovery_target_{identity}_test'
    output = ROOT / '.local' / 'native-recovery' / identity
    output.mkdir(parents=True, mode=0o700)
    settings = original.model_copy(update={'db_name': source_name,
        'allowed_hosts': ['testserver'], 'allowed_origins': ['http://testserver'],
        'object_storage_root': str(output / 'source/objects'),
        'auth_master_key_file': str(output / 'source/auth-master/master.key'),
        'ai_master_key_file': str(output / 'source/ai-master/master.key'),
        'ai_credential_root': str(output / 'source/ai-credentials')})
    control = create_engine(original.database_url(), isolation_level='AUTOCOMMIT', hide_parameters=True)
    with control.connect() as connection:
        assert connection.execute(text('SHOW server_version')).scalar_one().startswith('17.')
        for name in (source_name, target_name):
            connection.execute(text(f'CREATE DATABASE "{name}"'))
    control.dispose()
    database = Database(settings)
    config = migration_config()
    with database.engine.begin() as connection:
        config.attributes['connection'] = connection
        command.upgrade(config, 'head')
    client = TestClient(create_app(settings, database), raise_server_exceptions=True)
    env = None
    restored = None
    report = {'status': 'failed', 'synthetic_only': True, 'native_postgresql': True,
        'source_database': source_name, 'restored_database': target_name,
        'docker_orchestration_verified': False, 'workers_started': False,
        'external_requests': 0, 'human_pilot_completed': False}
    try:
        # Use a real uploaded file instead of the helper's default text statement;
        # normal application upload, review and close commands still execute.
        with pytest.MonkeyPatch.context() as clock, patch('tests.phase6_helpers.add',
                lambda client, path: add_evidence(client, path, kind='file')):
            env = finance_environment(client, database, settings, clock)
            _, _, _, closed = complete(env, cents=100003)
        initialize_auth_key(database)
        initialize(settings.ai_master_key_file, settings.ai_credential_root)
        store = EncryptedCredentialStore(settings.ai_credential_root, settings.ai_master_key_file)
        uid = UUID(env['owner']['user']['id'])
        with database.session() as session:
            session.add(Authenticator(user_id=uid,
                encrypted_secret=FactorCipher(settings.auth_master_key_file).seal(uid, b'fictional-seed-bytes'),
                enabled=True, must_enroll=False, last_counter=-1, recovery_hashes=[], changed_at=now()))
            conn = AIConnection(id=uuid4(), workspace_id=UUID(env['owner']['workspace']['id']),
                project_id=UUID(env['owner']['project']['id']), owner_id=uid, request_id=uuid4(),
                provider='openai', label='Synthetic retained credential',
                permission_reference='Offline fixture only', next_refresh_at=now())
            conn.credential_ref = store.write('synthetic-api-key-never-sent', key_context(conn))
            session.add(conn)
            session.commit()
        before = verify_retained(database)
        assert before['counts']['distribution_closes'] == 1
        assert before['counts']['artifact_objects'] == before['counts']['finance_documents'] == 1
        assert before['counts']['ai_credentials'] == before['counts']['mfa_seeds'] == 1
        # No server, worker or scheduler was started. Close all command clients
        # before capture and dispose pooled connections; writers stay stopped.
        for actor in env['actors'].values():
            actor['client'].close()
        client.close()
        database.dispose()
        pg_env = {**os.environ, 'PGHOST': settings.db_host, 'PGPORT': str(settings.db_port),
            'PGUSER': settings.db_user, 'PGPASSWORD': settings.db_password.get_secret_value()}
        dump = output / 'source.dump'
        result = subprocess.run([commands['pg_dump'], '--format=custom', '--no-owner', '--no-acl',
            '--file', str(dump), '--dbname', source_name], env=pg_env, capture_output=True)
        if result.returncode or result.stderr:
            raise RuntimeError('Native synthetic dump failed or produced warnings; source retained.')
        data = {'database.dump': dump}
        for prefix, root in [('objects', settings.object_storage_root), ('ai-credentials', settings.ai_credential_root)]:
            for path in Path(root).rglob('*'):
                if path.is_file():
                    data[prefix + '/' + path.relative_to(root).as_posix()] = path
        recovery = {'auth-master/master.key': Path(settings.auth_master_key_file),
                    'ai-master/master.key': Path(settings.ai_master_key_file)}
        key = os.urandom(32)
        keyfile = output / 'external-key/recovery.key'
        keyfile.parent.mkdir(mode=0o700)
        with keyfile.open('xb') as handle:
            handle.write(key)
        keyfile.chmod(0o600)
        metadata = {'native_postgresql': True, 'synthetic_only': True}
        scratch = output / 'scratch'
        for kind, files in [('data', data), ('recovery', recovery)]:
            create_bundle(files, output / (kind + '.clb'), key, capture_id=str(UUID(identity)),
                kind=kind, metadata=metadata, scratch=scratch)
        a = unpack_bundle(output / 'data.clb', output / 'restored-data', key, scratch=scratch)
        b = unpack_bundle(output / 'recovery.clb', output / 'restored-keys', key, scratch=scratch)
        validate_pair(a, b)
        result = subprocess.run([commands['pg_restore'], '--exit-on-error', '--single-transaction',
            '--no-owner', '--no-acl', '--dbname', target_name, str(output / 'restored-data/database.dump')],
            env=pg_env, capture_output=True)
        if result.returncode or result.stderr:
            raise RuntimeError('Native isolated restoration failed or produced warnings; target retained.')
        restored_settings = settings.model_copy(update={'db_name': target_name, 'environment': 'test',
            'object_storage_root': str(output / 'restored-data/objects'),
            'ai_credential_root': str(output / 'restored-data/ai-credentials'),
            'auth_master_key_file': str(output / 'restored-keys/auth-master/master.key'),
            'ai_master_key_file': str(output / 'restored-keys/ai-master/master.key')})
        restored = Database(restored_settings)
        with restored.engine.begin() as connection:
            config.attributes['connection'] = connection
            command.upgrade(config, 'head')
        assert verify_retained(restored) == before
        invalidate_recovered_access(restored, 'INVALIDATE-RESTORED-ACCESS')
        with restored.engine.connect() as connection:
            assert connection.execute(text('SELECT count(*) FROM browser_sessions WHERE revoked_at IS NULL')).scalar_one() == 0
        assert verify_retained(restored) == before
        # Wrong-key rejection without replacing either retained master.
        wrong = output / 'wrong-test-master.key'
        wrong.write_bytes(os.urandom(32))
        wrong_settings = restored_settings.model_copy(update={'ai_master_key_file': str(wrong)})
        bad = Database(wrong_settings)
        try:
            with pytest.raises(Exception):
                verify_retained(bad)
        finally:
            bad.dispose()
        assert verify_retained(database) == before
        report.update(status='passed', verification=before, copied_access_invalidated=True,
            wrong_master_rejected=True, source_preserved=True, exact_close_cents=100003,
            close_id=closed['id'])
        print('Native paired recovery passed: PostgreSQL dump/restore, exact close replay, retained blobs, credential/MFA decryption and copied-session invalidation. Source preserved; no workers started.')
    finally:
        client.close()
        if env:
            for actor in env['actors'].values():
                actor['client'].close()
        database.dispose()
        if restored:
            restored.dispose()
        (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        print('Sanitized result: ' + str((output / 'report.json').relative_to(ROOT)))


if __name__ == '__main__':
    main()
