"""Optional, JSON-only task transport. Import only in the jobs deployment.

No result backend, no pickle, no credentials or source blobs in messages. The
application scheduler and PostgreSQL, not Celery Beat, own periodic task state.
"""
from celery import Celery
from app.core.config import get_settings


def make_celery(settings):
    app=Celery('contribution_ledger_jobs',broker=settings.jobs_broker_url.get_secret_value(),
               include=['app.workers.tasks'])
    app.conf.update(
        task_serializer='json',accept_content=['json'],result_serializer='json',
        task_ignore_result=True,result_backend=None,task_default_queue='github-source',
        task_routes={'ledger.github.checkpoint':{'queue':'github-source'}},
        task_acks_late=True,task_reject_on_worker_lost=True,
        task_acks_on_failure_or_timeout=True,worker_prefetch_multiplier=1,
        task_soft_time_limit=140,task_time_limit=160,
        broker_connection_timeout=5,broker_connection_retry_on_startup=True,
        broker_transport_options={'visibility_timeout':240,'socket_timeout':5,'socket_connect_timeout':5},
        task_publish_retry=False,worker_send_task_events=False,
        worker_enable_remote_control=False,timezone='UTC',enable_utc=True,
    )
    return app


celery_app=make_celery(get_settings())
