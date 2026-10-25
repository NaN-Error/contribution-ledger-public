"""Check tracked source paths and Git ignore protections without reading local data.

This is a publication guard, not a credential/content scanner or authorization to
make a repository public. Scan full history and review hosting metadata separately.
"""
from pathlib import Path, PurePosixPath
import argparse, json, subprocess
from verify_release import private_source_path

ROOT = Path(__file__).resolve().parents[1]
PRIVATE_PROBES = [
    '.env', '.env.production', 'apps/api/.env.local',
    'personal-data/postgres-data/base/123/456',
    'custom/postgres-data/PG_VERSION', 'custom/pg_wal/00000001',
    'custom/auth-master/master.key', 'custom/ai-master/master.key',
    'custom/ai-credentials/ciphertext', 'custom/secrets/credential',
    'custom/github-secrets/github-client-secret', 'custom/uploads/image.png',
    'custom/github-master/master.key', 'custom/github-credentials/ciphertext',
    'custom/evidence-data/object', 'custom/.local/report.json',
    'custom/backups/capture.json', 'custom/exports/contributors.csv',
    'custom/logs/browser.json', 'custom/local-data/report.json',
    'custom/postgres-password.txt', 'custom/personal-installation.json',
    'custom/processes.json', 'custom/ports.json',
    'custom/private.db', 'custom/private.db-wal', 'custom/private.sqlite-journal',
    'custom/private.sqlite3-shm', 'custom/private.dump', 'custom/private.sql',
    'custom/private.sql.gz', 'custom/private.clb', 'custom/private.log',
    'custom/private.bak', 'custom/private.backup', 'custom/private.enc',
    'custom/private.pem', 'custom/private.key', 'custom/private.p12',
    'custom/private.pfx', 'custom/private.zip', 'custom/private.tar.gz',
    'custom/private.7z', 'custom/private.rar', 'runtime/python/python.exe',
    'apps/api/app/security/secrets/accidental.key',
    'apps/api/app/security/secrets/accidental-ciphertext',
    'apps/api/app/finance/exports/accidental.csv',
]
SOURCE_PROBES = ['.env.example', 'infra/ledger-privileges.sql',
    'apps/api/app/security/secrets/__init__.py',
    'apps/api/app/security/secrets/store.py',
    'apps/api/app/finance/exports/serialization.py', 'scripts/portable.ps1']


def check(root: Path) -> dict:
    tracked = subprocess.check_output(['git', 'ls-files', '-z'], cwd=root).decode().split('\0')
    forbidden = [name for name in tracked if name and private_source_path(PurePosixPath(name))]
    probes = PRIVATE_PROBES + SOURCE_PROBES
    result = subprocess.run(['git', 'check-ignore', '--no-index', '--stdin', '-z'],
        input=('\0'.join(probes) + '\0').encode(), stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, cwd=root)
    if result.returncode not in {0, 1}:
        raise ValueError('Git ignore inspection failed.')
    ignored = set(result.stdout.decode().split('\0'))
    missing = sorted(set(PRIVATE_PROBES) - ignored)
    source_ignored = sorted(set(SOURCE_PROBES) & ignored)
    return {'passed': not (forbidden or missing or source_ignored),
        'tracked_files_checked': sum(bool(name) for name in tracked),
        'private_path_probes': len(PRIVATE_PROBES), 'source_path_probes': len(SOURCE_PROBES),
        'forbidden_tracked_paths': forbidden, 'unprotected_private_paths': missing,
        'source_paths_incorrectly_ignored': source_ignored,
        'local_data_contents_read': False, 'full_history_secrets_scanned': False,
        'public_visibility_authorized': False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    args = parser.parse_args()
    result = check(args.root)
    print(json.dumps(result, indent=2))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
