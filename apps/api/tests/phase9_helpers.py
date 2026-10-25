"""Deterministic signed event fixtures; no live API or credential."""
import hashlib,hmac,json
from datetime import timedelta
from pathlib import Path
from uuid import UUID,uuid4
from sqlalchemy import select
from app.security.tokens import now
from app.integrations.github.sync_models import GitHubSyncConfig
from app.integrations.github.sync_service import schedule_one
from tests.auth_helpers import mutation
from tests.phase8_helpers import environment,run
SECRET=b'synthetic-signing-secret-at-least-32-bytes'

def signed(body,event='pull_request',delivery=None):
    raw=body if isinstance(body,bytes) else json.dumps(body,separators=(',',':')).encode()
    return raw,{'content-type':'application/json','x-github-event':event,
       'x-github-delivery':str(delivery or uuid4()),
       'x-hub-signature-256':'sha256='+hmac.new(SECRET,raw,hashlib.sha256).hexdigest()}

def event(action='synchronize',**overrides):
    return {'action':action,'installation':{'id':501},'repository':{'id':9001},
       'pull_request':{'number':1,'title':'THIS UNTRUSTED TITLE MUST NOT BE STORED AS API EVIDENCE'},**overrides}

def operational(body,event_name):
    body=dict(body)
    if event_name in {'installation','installation_repositories'}:
        body['installation']=dict(body['installation'],app_id=123)
        body.pop('repository',None);body.pop('pull_request',None)
    elif event_name=='repository':body.pop('pull_request',None)
    return body

def send(client,body=None,event_name='pull_request',delivery=None):
    raw,headers=signed(operational(body or event(),event_name),event_name,delivery)
    return client.post('/api/v1/github/webhook',content=raw,headers=headers)

def sync_environment(client,database,settings,tmp_path,package=False):
    e=environment(client,database,settings,package=package)
    settings.github_sync_enabled=True;settings.github_webhook_enabled=True
    secret_root=tmp_path/'signing';secret_root.mkdir()
    p=secret_root/'github-webhook-secret';p.write_bytes(SECRET);p.chmod(0o400)
    settings.github_secret_root=secret_root
    return e

def config_body(version=0,**changes):
    return {'expected_version':version,'enabled':True,'interval_minutes':360,'lookback_days':7,
      'request_limit':200,'entity_limit':50,'reviewed':True,'reason':'Enable fictional bounded synchronization',**changes}

def enable(client,root,overview,**changes):
    repo_id=overview['repositories'][0]['id']
    response=mutation(client,root+'/github/sync/'+repo_id,config_body(**changes),method='put')
    assert response.status_code==200,response.text
    return response.json()

def make_due(database,config_id):
    with database.session() as db:
        cfg=db.get(GitHubSyncConfig,UUID(config_id));cfg.next_due_at=now()-timedelta(seconds=1);db.commit()

def schedule(database,settings,config_id):
    make_due(database,config_id)
    assert schedule_one(database,settings,UUID(config_id))=='scheduled'
    with database.session() as db:
        return str(db.get(GitHubSyncConfig,UUID(config_id)).active_import_id)
