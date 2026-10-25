from datetime import timedelta
from uuid import UUID,uuid4
import json
import pytest
from sqlalchemy import select,text,func
from sqlalchemy.exc import DBAPIError
from app.ai.models import AIConnection,AIJob,AIPrice,AIModel
from app.ai.jobs import tick,claim,execute,maintain
from app.ai.usage.calculation import token_cost
from app.core.config import Settings
from app.providers.contracts import ProviderError,ModelInfo,GenerationResult
from app.security.tokens import now
from tests.ai_helpers import start,price,queue_probe
from tests.auth_helpers import mutation,other_client,invite,accept

@pytest.mark.parametrize('args,expected',[((0,0,1,1),0),((1,1,1,1),1),((2048,256,1000000,2000000),2560),((24,5,1000000,2000000),34)])
def test_exact_token_estimates(args,expected):assert token_cost(*args)==expected

@pytest.mark.parametrize('changes',[{'ai_live_enabled':True},{'ai_paid_probes_enabled':True},
 {'ai_deployment_mode':'hosted'},{'ai_permitted_providers':['arbitrary']},
 {'ai_credential_root':'/tmp/same','ai_master_key_file':'/tmp/same/key'}])
def test_fail_closed_operator_configuration(changes):
    with pytest.raises(ValueError):Settings(db_password='synthetic-test-password',**changes)

@pytest.mark.parametrize('url',['http://openai.com/api/pricing','https://openai.com.evil.test/pricing','https://user:pass@openai.com/pricing','https://openai.com:invalid/pricing','javascript:alert(1)'])
def test_price_source_is_recorded_official_url_not_fetched(client,database,settings,tmp_path,url):
    x=start(client,database,settings,tmp_path,'openai')
    r=mutation(client,x['base']+'/prices',{'model_id':x['model']['id'],'input_rate':1000000,'output_rate':1000000,
        'source_reference':url,'reason':'Synthetic local pricing review','valid_until':(now()+timedelta(days=1)).isoformat()})
    assert r.status_code==422,r.text

def test_key_schema_and_errors_do_not_echo_credentials(client,database,settings,tmp_path):
    x=start(client,database,settings,tmp_path,'openai')
    body={**x['body'],'request_id':str(uuid4()),'api_key':'synthetic-invalid key\nheader'}
    r=mutation(client,x['path']+'/connections',body);assert r.status_code==409 and body['api_key'] not in r.text
    r=mutation(client,x['path']+'/connections',{**body,'unexpected':'synthetic secret'});assert r.status_code==422 and 'synthetic secret' not in r.text

def test_monthly_limit_cannot_reduce_below_held_reservation(client,database,settings,tmp_path):
    x=start(client,database,settings,tmp_path,'openai');price(client,x,True);queue_probe(client,x)
    r=mutation(client,x['base'],{'expected_version':1,'label':'Edited label','monthly_limit_microusd':1,
       'allow_project_use':True,'reason':'Test budget reduction guard'},method='patch')
    assert r.status_code==409

def test_revocation_before_dispatch_refunds_and_does_not_run(client,database,settings,tmp_path):
    x=start(client,database,settings,tmp_path,'openai');price(client,x,True);queue_probe(client,x)
    assert mutation(client,x['base']+'/revoke',{'expected_version':1,'reason':'Revoking before external call'}).status_code==200
    assert tick(database,settings,x['factory'],x['store']) is False
    assert x['adapter'].generate_calls==0 and client.get(x['base']+'/usage').json()['items'][0]['held_microusd']==0

def test_shared_settings_change_invalidates_queued_probe(client,database,settings,tmp_path):
    x=start(client,database,settings,tmp_path,'openai');price(client,x,True);queue_probe(client,x)
    r=mutation(client,x['base'],{'expected_version':1,'label':'Edited label','monthly_limit_microusd':100000,
       'allow_project_use':False,'reason':'Withdraw permission for project use'},method='patch')
    assert r.status_code==200 and r.json()['generation']==2
    tick(database,settings,x['factory'],x['store']);assert x['adapter'].generate_calls==0

def test_429_cooldown_applies_to_new_probe_requests(client,database,settings,tmp_path):
    x=start(client,database,settings,tmp_path,'openai');price(client,x,True);queue_probe(client,x)
    x['adapter'].error=ProviderError('rate_limited',retry_after=300)
    tick(database,settings,x['factory'],x['store'])
    response,_=queue_probe(client,x);assert response.status_code==202
    assert claim(database,settings) is None and x['adapter'].generate_calls==1

def test_unknown_billing_can_exceed_reserve_without_being_silently_clipped(client,database,settings,tmp_path):
    x=start(client,database,settings,tmp_path,'openai',limit=2560);price(client,x,True);queue_probe(client,x)
    x['adapter'].result=GenerationResult('{"ok":true}','synthetic-json-v1',None,'complete',5000,300)
    tick(database,settings,x['factory'],x['store'])
    assert client.get(x['base']+'/usage').json()['items'][0]['estimated_microusd']==5600
    r,_=queue_probe(client,x);assert r.status_code==409

def test_live_price_cannot_be_zero_and_quotes_cannot_skip_input_limits(client,database,settings,tmp_path):
    x=start(client,database,settings,tmp_path,'openai')
    r=mutation(client,x['base']+'/prices',{'model_id':x['model']['id'],'input_rate':0,'output_rate':0,
       'source_reference':'https://openai.com/api/pricing','reason':'Invalid zero live rate review','valid_until':(now()+timedelta(days=1)).isoformat()})
    assert r.status_code==422
    price(client,x,True)
    with database.session() as db:
        m=db.get(AIModel,UUID(x['model']['id']));m.document={**m.document,'input_limit':128};db.commit()
    assert client.get(x['base']+'/models/'+x['model']['id']+'/probe-quote').status_code==409

def test_complete_empty_catalog_marks_old_models_unavailable(client,database,settings,tmp_path):
    x=start(client,database,settings,tmp_path);x['adapter'].models=[]
    mutation(client,x['base']+'/refresh',{'request_id':str(uuid4())});tick(database,settings,x['factory'],x['store'])
    m=client.get(x['base']+'/models').json()['items'][0];assert m['available'] is False and m['probe_state']=='unknown'

def test_duplicate_model_catalog_preserves_old_capture(client,database,settings,tmp_path):
    x=start(client,database,settings,tmp_path);before=client.get(x['base']+'/models').json()
    x['adapter'].models*=2;mutation(client,x['base']+'/refresh',{'request_id':str(uuid4())});tick(database,settings,x['factory'],x['store'])
    assert client.get(x['base']+'/models').json()==before

def test_profile_requires_project_sharing_and_successful_protocol_probe(client,database,settings,tmp_path):
    x=start(client,database,settings,tmp_path,share=False)
    body={'connection_id':x['connection']['id'],'model_id':x['model']['id'],'title':'Unapproved profile',
       'data_policy_reference':'Synthetic project permission reference','reason':'Draft configuration for testing'}
    assert mutation(client,x['path']+'/profiles',body).status_code==409
    price(client,x);queue_probe(client,x);tick(database,settings,x['factory'],x['store'])
    assert mutation(client,x['path']+'/profiles',body).status_code==409

def test_model_change_requires_successor_profile(client,database,settings,tmp_path):
    x=start(client,database,settings,tmp_path);price(client,x);queue_probe(client,x);tick(database,settings,x['factory'],x['store'])
    profile=mutation(client,x['path']+'/profiles',{'connection_id':x['connection']['id'],'model_id':x['model']['id'],
       'title':'Original draft','data_policy_reference':'Synthetic explicit data-sharing review','reason':'Review original model configuration'}).json()
    x['adapter'].models=[ModelInfo('synthetic-json-v1','Changed synthetic model',8192,1024,True,True)]
    mutation(client,x['base']+'/refresh',{'request_id':str(uuid4())});tick(database,settings,x['factory'],x['store'])
    response=mutation(client,x['path']+'/profiles/'+profile['id']+'/approve',{'reviewed_hash':profile['fingerprint'],
      'expected_active_profile_id':None,'reason':'Attempt approval after model metadata changed'})
    assert response.status_code==409

def test_raw_frozen_job_edit_and_connection_rebinding_are_denied(client,database,settings,tmp_path):
    x=start(client,database,settings,tmp_path)
    for statement in ["UPDATE ai_jobs SET specification='{}'", "UPDATE ai_jobs SET reserved_microusd=99", 'DELETE FROM ai_connections',"UPDATE ai_connections SET provider='openai'"]:
        with pytest.raises(DBAPIError),database.engine.begin() as conn:conn.execute(text(statement))


def test_rejected_new_connection_cleans_uncommitted_ciphertext(client,database,settings,tmp_path,monkeypatch):
    x=start(client,database,settings,tmp_path,'openai')
    from app.ai.connections import service
    from app.core.errors import ApiError
    def failure(*args,**kwargs):raise ApiError(409,'synthetic_rejection','Synthetic setup rejected before commit.')
    monkeypatch.setattr(service,'enqueue_catalog',failure)
    before=set(x['store'].root.glob('*.enc'))
    response=mutation(client,x['path']+'/connections',{**x['body'],'request_id':str(uuid4())})
    assert response.status_code==409 and set(x['store'].root.glob('*.enc'))==before
    assert len(client.get(x['path']).json()['connections'])==1


def test_failed_rotation_preserves_old_key_and_cleans_new_ciphertext(client,database,settings,tmp_path,monkeypatch):
    x=start(client,database,settings,tmp_path,'openai')
    from app.ai.connections import service
    from app.core.errors import ApiError
    def failure(*args,**kwargs):raise ApiError(409,'synthetic_rejection','Synthetic rotation rejected before commit.')
    monkeypatch.setattr(service,'enqueue_catalog',failure)
    before=set(x['store'].root.glob('*.enc'))
    response=mutation(client,x['base']+'/rotate',{'expected_version':1,'api_key':'replacement-synthetic-only','reason':'Test failed key replacement'})
    assert response.status_code==409 and set(x['store'].root.glob('*.enc'))==before
    assert client.get(x['path']).json()['connections'][0]['generation']==1


def test_completed_unknown_usage_counts_toward_unresolved_limit(client,database,settings,tmp_path):
    x=start(client,database,settings,tmp_path);price(client,x)
    x['adapter'].result=GenerationResult('{"ok":true}','synthetic-json-v1',None,'complete',None,None)
    for _ in range(5):
        response,_=queue_probe(client,x);assert response.status_code==202
        tick(database,settings,x['factory'],x['store'])
    response,_=queue_probe(client,x);assert response.status_code==409
    assert response.json()['error']['code']=='ai_unresolved_limit'


def test_explicit_access_failure_invalidates_previous_qualification(client,database,settings,tmp_path):
    x=start(client,database,settings,tmp_path);price(client,x);queue_probe(client,x);tick(database,settings,x['factory'],x['store'])
    assert client.get(x['base']+'/models').json()['items'][0]['probe_state']=='passed'
    x['adapter'].error=ProviderError('permission');queue_probe(client,x);tick(database,settings,x['factory'],x['store'])
    assert client.get(x['base']+'/models').json()['items'][0]['probe_state']=='failed'
