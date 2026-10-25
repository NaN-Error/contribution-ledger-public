"""Read-only source archive verification. Does not install, launch, or reset anything.

A manifest verifies file consistency, not its author's identity or deployment
readiness. It deliberately does not read .env files, credentials, or local data.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]


def private_source_path(relative: PurePosixPath) -> bool:
    """Reject local state in a source manifest, independently of Git ignore rules."""
    parts = tuple(part.lower() for part in relative.parts)
    name = parts[-1]
    private_dirs = {'.local', '.git', 'node_modules', '.venv', 'uploads',
        'personal-data', 'postgres-data', 'pg_wal', 'pg_tblspc', 'auth-master',
        'ai-master', 'ai-credentials', 'github-master', 'github-credentials', 'github-secrets', 'evidence-data',
        'local-data', 'backups', 'exports', 'secrets', 'logs'}
    source_package = relative.suffix == '.py' and parts[:5] in {
        ('apps', 'api', 'app', 'security', 'secrets'),
        ('apps', 'api', 'app', 'finance', 'exports')}
    if any(part in private_dirs and not (source_package and part in {'secrets', 'exports'})
           for part in parts) or parts[0] == 'runtime':
        return True
    if name.startswith('.env') and relative.as_posix() != '.env.example':
        return True
    if name in {'postgres-password.txt', 'personal-installation.json', 'processes.json',
                'ports.json', 'github-client-secret', 'github-webhook-secret'}:
        return True
    if re.search(r'\.(?:db|sqlite3?)(?:-(?:wal|shm|journal))?$', name):
        return True
    if name.endswith(('.key', '.pem', '.dump', '.clb', '.p12', '.pfx', '.bak',
                      '.backup', '.enc', '.zip', '.7z', '.rar', '.tar', '.sql.gz',
                      '.tar.gz', '.tar.xz', '.tar.bz2')):
        return True
    if name.endswith('.sql') and relative.as_posix() != 'infra/ledger-privileges.sql':
        return True
    # Existing synthetic verification logs are reviewed historical source evidence.
    return name.endswith('.log') and parts[:2] != ('docs', 'verification')


def verify(root: Path) -> dict:
    manifest_path = root / 'release-manifest.json'
    if manifest_path.is_symlink() or not manifest_path.is_file() or manifest_path.stat().st_size > 4 * 1024 * 1024:
        raise ValueError('Missing or invalid release manifest.')
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    entries = manifest.get('files')
    if not isinstance(entries, list) or not 1 <= len(entries) <= 20000:
        raise ValueError('Invalid manifest inventory.')
    seen = set(); failures = []
    for item in entries:
        if not isinstance(item, dict) or set(item) != {'path', 'bytes', 'sha256'}:
            raise ValueError('Invalid manifest entry.')
        name = item['path']
        if not isinstance(name, str) or len(name) > 400:
            raise ValueError('Invalid source path.')
        relative = PurePosixPath(name)
        if (relative.is_absolute() or '..' in relative.parts or '\\' in name or ':' in name or
            str(relative) != name or name in seen or name == 'release-manifest.json' or
            private_source_path(relative)):
            raise ValueError('Unsafe or duplicate source path in manifest.')
        if type(item['bytes']) is not int or not 0 <= item['bytes'] <= 64 * 1024 * 1024 or not re.fullmatch(r'[a-f0-9]{64}', str(item['sha256'])):
            raise ValueError('Invalid content metadata.')
        seen.add(name); path = root / relative
        if (path.is_symlink() or not path.resolve().is_relative_to(root.resolve()) or
            not path.is_file() or path.stat().st_size != item['bytes']):
            failures.append({'path': name, 'failure': 'missing_or_size_mismatch'}); continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != item['sha256']:
            failures.append({'path': name, 'failure': 'hash_mismatch'})
    if manifest.get('archive_file_count') != len(entries) + 1:
        raise ValueError('Manifest file count does not match its inventory.')
    return {'version': manifest.get('version'), 'checked_files': len(entries),
            'file_consistency_passed': not failures, 'failures': failures,
            'unlisted_local_files_inspected': False, 'runtime_verified': False,
            'independent_signature_verified': False, 'release_authorized': False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        result = verify(args.root)
    except (OSError, ValueError, TypeError, KeyError, IndexError):
        print('Source verification rejected an unreadable or unsafe manifest. No local data was changed.')
        return 2
    print(json.dumps(result, indent=2))
    return 0 if result['file_consistency_passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
