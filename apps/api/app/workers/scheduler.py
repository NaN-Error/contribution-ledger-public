"""Explicitly running scheduler/outbox dispatcher. Safe to restart; no catch-up storm."""
import argparse
import json
import time
from app.core.config import get_settings
from app.db.session import Database
from app.jobs.dispatch import CeleryPublisher,publish_one,heartbeat
from app.integrations.github.sync_service import schedule_due


def cycle(database,settings,publisher):
    scheduled=schedule_due(database,settings)
    results=[]
    if settings.github_enabled and settings.github_sync_enabled:
        for _ in range(20):
            result=publish_one(database,publisher);results.append(result)
            if result in {'idle','broker_unavailable'}:break
    status='broker_unavailable' if 'broker_unavailable' in results else 'running'
    heartbeat(database,'github-scheduler',status)
    return {'scheduler':status,'scheduled':scheduled.count('scheduled'),'dispatch':results}


def main():
    parser=argparse.ArgumentParser(description='Run the explicit GitHub scheduler and transactional outbox publisher.')
    parser.add_argument('--loop',action='store_true')
    args=parser.parse_args();settings=get_settings();settings.require_local_foundation()
    if not settings.github_enabled or not settings.github_sync_enabled:
        print(json.dumps({'state':'disabled'}));return 2
    from app.jobs.celery_app import make_celery
    publisher=CeleryPublisher(make_celery(settings));database=Database(settings)
    try:
        while True:
            try:print(json.dumps(cycle(database,settings,publisher)),flush=True)
            except Exception:print(json.dumps({'scheduler':'database_or_configuration_unavailable'}),flush=True)
            if not args.loop:break
            time.sleep(5)
        return 0
    except KeyboardInterrupt:return 0
    finally:database.dispose()


if __name__=='__main__':raise SystemExit(main())
