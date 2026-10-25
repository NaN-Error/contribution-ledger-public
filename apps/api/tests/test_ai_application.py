from datetime import timedelta
from uuid import UUID,uuid4
import json
import pytest
from sqlalchemy import select,func,text
from sqlalchemy.exc import DBAPIError
from app.ai.jobs import tick,claim,execute,maintain
from app.ai.models import AIConnection,AIModel,AIJob,AIUsageBucket,AIProfile,AIPrice,AIEvent
from app.providers.contracts import ProviderError,ModelInfo,GenerationResult
from app.security.tokens import now
from tests.auth_helpers import mutation,other_client,invite,accept
from tests.ai_helpers import start,price,queue_probe


def test_complete_mock_catalog_probe_profile_and_catalog_update(client,database,settings,tmp_path):
    x=start(client,database,settings,tmp_path);price(client,x)
    response,body=queue_probe(client,x);assert response.status_code==202,response.text
    assert tick(database,settings,x['factory'],x['store']);assert x['adapter'].generate_calls==1
    models=client.get(x['base']+'/models').json()['items'];assert models[0]['probe_state']=='passed'
    p=mutation(client,x['path']+'/profiles',{'connection_id':x['connection']['id'],'model_id':x['model']['id'],
        'title':'Synthetic evaluator','data_policy_reference':'Synthetic-only data permission; no private data',
        'reason':'Review synthetic foundation settings'})
    assert p.status_code==201,p.text
    profile=p.json();approval={'reviewed_hash':profile['fingerprint'],'expected_active_profile_id':None,'reason':'Reviewed complete synthetic profile'}
    response=mutation(client,x['path']+'/profiles/'+profile['id']+'/approve',approval);assert response.status_code==200,response.text
    response=mutation(client,x['path']+'/profiles/'+profile['id']+'/approve',approval);assert response.status_code==200
    x['adapter'].models.append(ModelInfo('new-synthetic-model','New synthetic model'))
    assert mutation(client,x['base']+'/refresh',{'request_id':str(uuid4())}).status_code==202
    assert tick(database,settings,x['factory'],x['store'])
    assert len(client.get(x['base']+'/models').json()['items'])==2
    assert client.get(x['path']).json()['active_profile_id']==profile['id']
    assert len(client.get(x['path']+'/profiles').json()['items'])==1
    # Keys, raw generation prose and evidence are never part of persisted job content.
    with database.session() as db:
        payload=json.dumps([j.specification for j in db.scalars(select(AIJob)).all()])
        assert 'api_key' not in payload and 'prompt' not in payload.replace('prompt_version','version')

def test_paid_reserve_settle_idempotent(client,database,settings,tmp_path):
    x=start(client,database,settings,tmp_path,'openai');price(client,x,True)
    response,body=queue_probe(client,x);assert response.status_code==202,response.text
    assert response.json()['reserved_microusd']==2560
    again=mutation(client,x['base']+'/models/'+x['model']['id']+'/probe',body)
    assert again.json()['id']==response.json()['id']
    assert client.get(x['base']+'/usage').json()['items'][0]['held_microusd']==2560
    tick(database,settings,x['factory'],x['store'])
    usage=client.get(x['base']+'/usage').json()['items'][0]
    assert usage['held_microusd']==0 and usage['estimated_microusd']==34
    assert x['adapter'].generate_calls==1


def test_insufficient_budget_and_false_confirmation(client,database,settings,tmp_path):
    x=start(client,database,settings,tmp_path,'openai',limit=2559);price(client,x,True)
    response,_=queue_probe(client,x);assert response.status_code==409 and response.json()['error']['code']=='ai_budget_exhausted'
    response,_=queue_probe(client,x,payer_approved=False);assert response.status_code==422
    response,_=queue_probe(client,x,payer_approved='true');assert response.status_code==422
    assert x['adapter'].generate_calls==0


def test_ambiguous_paid_request_never_retries_and_requires_recorded_reconciliation(client,database,settings,tmp_path):
    x=start(client,database,settings,tmp_path,'openai');price(client,x,True)
    response,_=queue_probe(client,x);jid=response.json()['id'];x['adapter'].error=ProviderError('timeout',ambiguous=True)
    tick(database,settings,x['factory'],x['store']);tick(database,settings,x['factory'],x['store'])
    job=client.get(x['base']+'/jobs').json()['items'][0]
    assert job['status']=='ambiguous' and job['accounting_state']=='uncertain' and x['adapter'].generate_calls==1
    assert client.get(x['base']+'/usage').json()['items'][0]['held_microusd']==2560
    body={'actual_microusd':15,'source_reference':'Synthetic provider invoice line 123','reason':'Reviewed external synthetic usage'}
    r=mutation(client,x['base']+'/jobs/'+jid+'/reconcile',body);assert r.status_code==200,r.text
    assert mutation(client,x['base']+'/jobs/'+jid+'/reconcile',body).status_code==200
    assert mutation(client,x['base']+'/jobs/'+jid+'/reconcile',{**body,'actual_microusd':16}).status_code==409
    u=client.get(x['base']+'/usage').json()['items'][0];assert u['held_microusd']==0 and u['estimated_microusd']==15


def test_worker_death_marks_dispatched_probe_ambiguous(client,database,settings,tmp_path):
    x=start(client,database,settings,tmp_path,'openai');price(client,x,True);queue_probe(client,x)
    item=claim(database,settings);assert item
    with database.session() as db:
        j=db.get(AIJob,item[0]);j.lease_until=now()-timedelta(seconds=1);db.commit()
    maintain(database,settings)
    assert execute(database,settings,x['factory'],x['store'],item) is False
    assert x['adapter'].generate_calls==0
    job=client.get(x['base']+'/jobs').json()['items'][0];assert job['status']=='ambiguous' and job['accounting_state']=='uncertain'


def test_queued_revoke_refunds_but_sent_call_keeps_cost(client,database,settings,tmp_path):
    x=start(client,database,settings,tmp_path,'openai');price(client,x,True);queue_probe(client,x)
    item=claim(database,settings)
    x['adapter'].before_return=lambda:mutation(client,x['base']+'/revoke',{'expected_version':1,'reason':'Revoked during synthetic provider request'})
    execute(database,settings,x['factory'],x['store'],item)
    job=client.get(x['base']+'/jobs').json()['items'][0]
    assert job['result']['authorization_current_at_completion'] is False and job['accounted_microusd']==34
    assert client.get(x['base']+'/models').json()['items'][0]['probe_state']=='unknown'
    assert not list(x['store'].root.glob('*.enc'))


def test_queued_cancel_is_idempotent(client,database,settings,tmp_path):
    x=start(client,database,settings,tmp_path,'openai');price(client,x,True);r,_=queue_probe(client,x)
    url=x['base']+'/jobs/'+r.json()['id']+'/cancel';body={'reason':'Cancel synthetic paid reservation'}
    assert mutation(client,url,body).status_code==200;assert mutation(client,url,body).status_code==200
    assert client.get(x['base']+'/usage').json()['items'][0]['held_microusd']==0
    tick(database,settings,x['factory'],x['store']);assert x['adapter'].generate_calls==0


@pytest.mark.parametrize('change',['generation','model','month','expiry'])
def test_probe_checks_frozen_inputs_before_dispatch(client,database,settings,tmp_path,change):
    x=start(client,database,settings,tmp_path,'openai');p=price(client,x,True);r,_=queue_probe(client,x)
    with database.session() as db:
        if change=='generation':db.get(AIConnection,UUID(x['connection']['id'])).generation+=1
        elif change=='model':db.get(AIModel,UUID(x['model']['id'])).fingerprint='0'*64
        else:
            # Simulate clock advance, not an illegal edit of immutable price/job records.
            import app.ai.jobs as jobs
            from unittest.mock import patch
            at=now()+timedelta(days=40 if change=='month' else 2)
            db.commit()
            with patch.object(jobs,'now',return_value=at):claim(database,settings)
            job=client.get(x['base']+'/jobs').json()['items'][0];assert job['status']=='cancelled'
            return
        db.commit()
    assert claim(database,settings) is None
    assert client.get(x['base']+'/usage').json()['items'][0]['held_microusd']==0


def test_catalog_failure_preserves_last_good_and_retries_are_bounded(client,database,settings,tmp_path):
    x=start(client,database,settings,tmp_path);old=client.get(x['base']+'/models').json()['items']
    mutation(client,x['base']+'/refresh',{'request_id':str(uuid4())});x['adapter'].catalog_error=ProviderError('timeout')
    for i in range(3):
        with database.session() as db:
            for j in db.scalars(select(AIJob).where(AIJob.status=='queued')):j.not_before=now()-timedelta(seconds=1)
            db.commit()
        tick(database,settings,x['factory'],x['store'])
    assert client.get(x['base']+'/models').json()['items']==old
    failed=client.get(x['base']+'/jobs').json()['items'][0];assert failed['status']=='failed' and failed['attempts']==3


def test_daily_refresh_coalesces(client,database,settings,tmp_path):
    x=start(client,database,settings,tmp_path)
    with database.session() as db:db.get(AIConnection,UUID(x['connection']['id'])).next_refresh_at=now()-timedelta(days=1);db.commit()
    maintain(database,settings);maintain(database,settings)
    for _ in range(3):mutation(client,x['base']+'/refresh',{'request_id':str(uuid4())})
    with database.session() as db:assert db.scalar(select(func.count()).select_from(AIJob).where(AIJob.status=='queued'))==1


def test_unknown_usage_retains_reservation(client,database,settings,tmp_path):
    x=start(client,database,settings,tmp_path,'openai');price(client,x,True);queue_probe(client,x)
    x['adapter'].result=GenerationResult('{"ok":true}','synthetic-json-v1',None,'complete',None,None)
    tick(database,settings,x['factory'],x['store'])
    j=client.get(x['base']+'/jobs').json()['items'][0];assert j['status']=='succeeded' and j['accounting_state']=='uncertain'


def test_key_never_returned_and_rotation_requires_new_generation(client,database,settings,tmp_path):
    x=start(client,database,settings,tmp_path,'openai');old=x['connection']['generation']
    r=mutation(client,x['base']+'/rotate',{'expected_version':1,'api_key':'new-synthetic-provider-credential','reason':'Rotate synthetic operator credential'})
    assert r.status_code==200,r.text;assert r.json()['generation']==old+1
    for path in [x['path'],x['base']+'/models',x['base']+'/jobs',x['base']+'/usage']:
        body=client.get(path).text;assert 'synthetic-never-live-test-key' not in body and 'new-synthetic-provider-credential' not in body and 'credential_ref' not in body
    assert len(list(x['store'].root.glob('*.enc')))==1


def test_viewer_cannot_create_or_read_private_connections(client,database,settings,tmp_path):
    x=start(client,database,settings,tmp_path,share=False)
    inv=invite(client,x['account']['workspace']['id'],project_id=x['account']['project']['id'],role='viewer')
    with other_client(settings,database) as member:
        accept(member,inv['token'])
        assert member.get(x['path']).json()['connections']==[]
        assert member.get(x['base']+'/models').status_code==404
        assert mutation(member,x['path']+'/connections',{**x['body'],'request_id':str(uuid4())}).status_code==403


def test_shared_reviewer_can_inspect_but_not_spend(client,database,settings,tmp_path):
    x=start(client,database,settings,tmp_path);price(client,x)
    inv=invite(client,x['account']['workspace']['id'],project_id=x['account']['project']['id'],role='reviewer')
    with other_client(settings,database) as member:
        accept(member,inv['token']);assert member.get(x['base']+'/models').status_code==200
        assert member.get(x['base']+'/models/'+x['model']['id']+'/probe-quote').status_code==404
        assert mutation(member,x['base']+'/refresh',{'request_id':str(uuid4())}).status_code==404


def test_wrong_project_connection_reference_is_hidden(client,database,settings,tmp_path):
    x=start(client,database,settings,tmp_path)
    for path in [x['base'].replace(x['account']['project']['id'],str(uuid4()))+'/models',
                 x['base'].replace(x['account']['workspace']['id'],str(uuid4()))+'/models']:
        assert client.get(path).status_code==404


def test_unknown_price_or_unapproved_paid_configuration_blocks_probe(client,database,settings,tmp_path):
    x=start(client,database,settings,tmp_path,'openai');url=x['base']+'/models/'+x['model']['id']+'/probe-quote'
    assert client.get(url).status_code==409;price(client,x,True)
    settings.ai_paid_probes_enabled=False;assert client.get(url).status_code==409


def test_changed_quote_rejected(client,database,settings,tmp_path):
    x=start(client,database,settings,tmp_path,'openai');price(client,x,True)
    r,_=queue_probe(client,x,quote_hash='0'*64);assert r.status_code==409
    r,_=queue_probe(client,x,confirmed_reservation_microusd=0);assert r.status_code==409


def test_extra_prompt_and_key_fields_are_rejected(client,database,settings,tmp_path):
    x=start(client,database,settings,tmp_path);price(client,x)
    r,_=queue_probe(client,x,prompt='Do not send arbitrary project data');assert r.status_code==422
    r,_=queue_probe(client,x,api_key='synthetic-unexpected-key');assert r.status_code==422 and 'synthetic-unexpected-key' not in r.text


def test_price_and_event_history_reject_updates(client,database,settings,tmp_path):
    x=start(client,database,settings,tmp_path);p=price(client,x)
    with database.session() as db:
        with pytest.raises(DBAPIError):db.execute(text("UPDATE ai_prices SET reason='tampered'"));db.commit()
        db.rollback()
        with pytest.raises(DBAPIError):db.execute(text('DELETE FROM ai_operation_events'));db.commit()
