"""Explicit database-owned AI worker. Safe default: synthetic provider only."""
import argparse
import signal
import time
from app.core.config import get_settings
from app.db.session import Database
from app.providers.factory import ProviderFactory
from app.security.secrets.encrypted import EncryptedCredentialStore
from app.ai.jobs import tick


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--once',action='store_true');args=parser.parse_args()
    settings=get_settings();settings.require_local_foundation()
    db=Database(settings);factory=ProviderFactory(settings)
    store=EncryptedCredentialStore(settings.ai_credential_root,settings.ai_master_key_file)
    stop=False
    def halt(*_):
        nonlocal stop
        stop=True
    signal.signal(signal.SIGTERM,halt);signal.signal(signal.SIGINT,halt)
    try:
        while not stop:
            try:busy=tick(db,settings,factory,store)
            except Exception:
                # No raw external exception, connection URL or secret is printed.
                print('AI worker operation failed; inspect local job history and database readiness.',flush=True);busy=False
                if args.once:raise SystemExit(1)
            if args.once:break
            time.sleep(1 if busy else 5)
    finally:db.dispose()
if __name__=='__main__':main()
