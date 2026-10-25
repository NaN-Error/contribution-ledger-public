"""Optional real Celery/Redis contracts. Explicitly skipped without installed transport/tools."""
import importlib,os
from uuid import uuid4
from urllib.parse import urlsplit
import pytest

def configured_app(settings,monkeypatch):
    pytest.importorskip('celery',reason='Optional Celery transport is not installed; no broker/config execution claimed.')
    monkeypatch.setattr('app.core.config.get_settings',lambda:settings)
    return importlib.import_module('app.jobs.celery_app').make_celery(settings)

def test_actual_celery_configuration_is_json_only(settings,monkeypatch):
    app=configured_app(settings,monkeypatch)
    assert app.conf.task_serializer=='json' and app.conf.accept_content==['json']
    assert app.conf.task_acks_late and app.conf.worker_prefetch_multiplier==1
    assert app.conf.result_backend is None and not app.conf.worker_enable_remote_control
    assert app.conf.task_time_limit<180<app.conf.broker_transport_options['visibility_timeout']
    app.close()

def test_real_redis_message_roundtrip_uses_only_scoped_ids(settings,monkeypatch):
    value=os.environ.get('CL_TEST_BROKER_URL')
    if not value:pytest.skip('Real Redis roundtrip requires CL_TEST_BROKER_URL on loopback database 15.')
    url=urlsplit(value)
    if url.scheme!='redis' or url.hostname not in {'127.0.0.1','localhost'} or url.path!='/15':pytest.fail('Use a disposable loopback Redis database 15 only.')
    from pydantic import SecretStr
    settings.jobs_broker_url=SecretStr(value);app=configured_app(settings,monkeypatch)
    queue='ledger-test-'+uuid4().hex
    payload={'job_id':str(uuid4()),'workspace_id':str(uuid4()),'project_id':str(uuid4())}
    try:
        app.send_task('ledger.github.checkpoint',kwargs=payload,queue=queue,serializer='json',ignore_result=True,retry=False)
        with app.connection_for_read() as connection:
            q=connection.SimpleQueue(queue)
            try:
                msg=q.get(block=True,timeout=5);assert msg.payload[1]==payload;assert msg.headers['task']=='ledger.github.checkpoint';msg.ack()
            finally:q.clear();q.close()
    finally:app.close()
