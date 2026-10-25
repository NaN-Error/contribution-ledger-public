"""Explicit operator-only staging into a private Docker secret volume.

The host staging folder still needs Windows ACL/Unix protection. Its file mode is
not treated as a useful Windows ACL signal; the destination has enforced POSIX
permissions and is mounted read-only by runtime containers. No API exposes this.
"""
import argparse
import os
from pathlib import Path
from uuid import uuid4
from app.security.secrets.store import SecretUnavailable,MountedSecretStore
from app.integrations.github.client import app_jwt

CONFIRM='PROVISION GITHUB SECRETS'

def stage(source:Path,destination:Path,*,confirmed:str,uid:int=10001,gid:int=10001):
    if confirmed!=CONFIRM:raise SecretUnavailable()
    # This command targets a POSIX Docker volume, not a Windows host folder.
    # Fail before reading/staging anything when ownership cannot be enforced.
    if os.name != 'posix':raise SecretUnavailable()
    if source.is_symlink() or destination.is_symlink():raise SecretUnavailable()
    values={}
    for name in sorted(MountedSecretStore.allowed_names):
        path=source/name
        if name=='github-webhook-secret' and not path.exists():continue
        if path.is_symlink() or not path.is_file() or path.stat().st_size>16384:raise SecretUnavailable()
        data=path.read_bytes().strip()
        if not data or len(data)>16384:raise SecretUnavailable()
        values[name]=data
    # Validate both files before replacing either destination. No secret is printed.
    app_jwt('provision-validation-only',values['github-private-key.pem'])
    secret=values['github-client-secret']
    if len(secret)>1024 or any(b<33 or b>126 for b in secret):raise SecretUnavailable()
    if 'github-webhook-secret' in values:
        webhook=values['github-webhook-secret']
        if not 32<=len(webhook)<=256 or any(b<33 or b>126 for b in webhook):raise SecretUnavailable()
    destination.mkdir(parents=True,exist_ok=True)
    if destination.is_symlink() or not destination.is_dir():raise SecretUnavailable()
    os.chmod(destination,0o700)
    for name,data in values.items():
        temporary=destination/('.staged-'+uuid4().hex)
        try:
            fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o400)
            with os.fdopen(fd,'wb') as handle:handle.write(data);handle.flush();os.fsync(handle.fileno())
            os.chown(temporary,uid,gid);os.chmod(temporary,0o400)
            os.replace(temporary,destination/name)
        finally:temporary.unlink(missing_ok=True)
    os.chown(destination,uid,gid)
    # Atomic per-file replacements, not an atomic two-file rotation: stop consumers
    # before provisioning and repeat after an interrupted staging operation.

def main():
    parser=argparse.ArgumentParser(description='Stage operator files into a private secret volume; stop API/worker first.')
    parser.add_argument('--confirm',required=True);args=parser.parse_args()
    try:stage(Path('/source-secrets'),Path('/target-secrets'),confirmed=args.confirm)
    except (OSError,SecretUnavailable):
        print('Secret provisioning failed. Inspect host access, source files and volume permissions. No credential value was displayed.');return 2
    print('GitHub credential files provisioned with restricted permissions. Keep this volume and its backups private.');return 0

if __name__=='__main__':raise SystemExit(main())
