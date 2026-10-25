"""Phase-8 DB-backed worker. Real broker dispatch/reconciliation belongs to phase 9."""
import argparse
import json
import time
from uuid import UUID
from app.core.config import get_settings
from app.db.session import Database
from app.security.secrets.store import MountedSecretStore
from app.integrations.github.client import GitHubClient
from app.integrations.github.importer import step


def main():
    parser=argparse.ArgumentParser(description='Process authorized GitHub import checkpoints. Never executes repository code.')
    parser.add_argument('--loop',action='store_true',help='Continue polling while this process is running.')
    parser.add_argument('--max-steps',type=int,default=1,help='Bounded steps without --loop; default 1.')
    parser.add_argument('--job',type=UUID,help='Process only this local import UUID.')
    args=parser.parse_args()
    if not 1<=args.max_steps<=10000: parser.error('--max-steps must be between 1 and 10000')
    settings=get_settings();settings.require_local_foundation()
    if not settings.github_enabled:
        print(json.dumps({'state':'disabled','message':'GitHub is not configured. The manual application remains available.'}));return 2
    database=Database(settings)
    client=GitHubClient(settings,MountedSecretStore(settings.github_secret_root))
    try:
        iterations=0
        while args.loop or iterations<args.max_steps:
            state=step(database,settings,client,args.job)
            print(json.dumps({'worker':'github-import','state':state}),flush=True)
            iterations+=1
            if not args.loop and state=='idle': break
            time.sleep(5 if state=='idle' else 1)
        return 0
    except KeyboardInterrupt:
        return 0
    finally:database.dispose()


if __name__=='__main__':
    raise SystemExit(main())
