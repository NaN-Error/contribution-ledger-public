from datetime import timedelta
from uuid import uuid4
from app.security.tokens import now
from app.security.secrets.encrypted import EncryptedCredentialStore,initialize
from app.providers.mock import MockProvider
from app.providers.contracts import ModelInfo,GenerationResult
from app.ai.jobs import tick
from tests.auth_helpers import bootstrap,mutation

class Adapter:
    def __init__(self):
        self.models=[ModelInfo('synthetic-json-v1','Synthetic text',8192,1024,True,True)]
        self.result=GenerationResult('{"ok":true}','synthetic-json-v1','request_fixture','complete',24,5)
        self.error=None;self.catalog_error=None;self.before_return=None;self.catalog_calls=0;self.generate_calls=0
    def list_models(self,key):
        self.catalog_calls+=1
        if self.catalog_error:raise self.catalog_error
        return self.models
    def generate(self,key,request):
        self.generate_calls+=1
        assert 'compatibility test using synthetic data only' in request.prompt
        if self.before_return:self.before_return()
        if self.error:raise self.error
        return self.result
class Factory:
    def __init__(self,adapter):self.adapter=adapter
    def get(self,provider):return self.adapter

def start(client,database,settings,tmp_path,provider='mock',limit=100000,share=True):
    client._transport.raise_server_exceptions=True
    account=bootstrap(client,database)
    path=f"/api/v1/workspaces/{account['workspace']['id']}/projects/{account['project']['id']}/ai"
    initialize(str(tmp_path/'master'/'key'),str(tmp_path/'cipher'))
    store=EncryptedCredentialStore(str(tmp_path/'cipher'),str(tmp_path/'master'/'key'));client.app.state.ai_store=store
    adapter=Adapter();factory=Factory(adapter)
    if provider!='mock':
        settings.ai_deployment_mode='customer_controlled';settings.ai_live_enabled=True
        settings.ai_paid_probes_enabled=True;settings.ai_permitted_providers=[provider]
    body={'request_id':str(uuid4()),'provider':provider,'label':'Synthetic connection','reason':'Test a synthetic connection',
          'permission_reference':'Synthetic permitted payer approval','monthly_limit_microusd':limit,'allow_project_use':share}
    if provider!='mock':body['api_key']='synthetic-never-live-test-key'
    response=mutation(client,path+'/connections',body);assert response.status_code==201,response.text
    connection=response.json();base=path+'/connections/'+connection['id']
    assert tick(database,settings,factory,store)
    model=client.get(base+'/models').json()['items'][0]
    return dict(account=account,path=path,base=base,connection=connection,model=model,store=store,adapter=adapter,factory=factory,body=body)

def price(client,ctx,live=False):
    body={'model_id':ctx['model']['id'],'input_rate':1000000 if live else 0,'output_rate':2000000 if live else 0,
       'source_reference':'https://openai.com/api/pricing/' if live else 'Synthetic zero-cost reference',
       'valid_until':(now()+timedelta(days=1)).isoformat(),'reason':'Reviewed synthetic test pricing'}
    response=mutation(client,ctx['base']+'/prices',body);assert response.status_code==201,response.text
    return response.json()

def queue_probe(client,ctx,**changes):
    url=ctx['base']+'/models/'+ctx['model']['id']
    response=client.get(url+'/probe-quote');assert response.status_code==200,response.text
    q=response.json();body={'request_id':str(uuid4()),'quote_hash':q['quote_hash'],
        'confirmed_reservation_microusd':q['specification']['reservation_microusd'],'payer_approved':True,**changes}
    response=mutation(client,url+'/probe',body)
    return response,body
