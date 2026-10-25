from datetime import timedelta
from uuid import uuid4,UUID
from app.providers.factory import ProviderFactory
from app.ai.jobs import tick,claim,execute
from app.security.tokens import now
from tests.phase6_helpers import environment
from tests.auth_helpers import mutation


def setup(client,database,settings,**kw):
    env=environment(client,database,settings,**kw);root=env['root']+'/ai'
    response=mutation(client,root+'/connections',{'request_id':str(uuid4()),'provider':'mock','label':'Synthetic assessment tester',
        'permission_reference':'Synthetic test fixture only; no external calls','monthly_limit_microusd':100000,
        'allow_project_use':True,'reason':'Test the evidence review workflow without paid requests'})
    assert response.status_code==201,response.text
    conn=response.json();factory=ProviderFactory(settings);store=client.app.state.ai_store if hasattr(client,'app') else client._transport.app.state.ai_store
    assert tick(database,settings,factory,store)
    models=client.get(root+'/connections/'+conn['id']+'/models').json()['items'];model=models[0]
    price=mutation(client,root+'/connections/'+conn['id']+'/prices',{'model_id':model['id'],'input_rate':0,'output_rate':0,
        'source_reference':'Synthetic provider uses no billable service','valid_until':(now()+timedelta(days=1)).isoformat(),
        'reason':'Explicitly reviewed free synthetic fixture'})
    assert price.status_code==201,price.text
    q=client.get(root+'/connections/'+conn['id']+'/models/'+model['id']+'/probe-quote');assert q.status_code==200,q.text
    quote=q.json()
    response=mutation(client,root+'/connections/'+conn['id']+'/models/'+model['id']+'/probe',
        {'request_id':str(uuid4()),'quote_hash':quote['quote_hash'],'confirmed_reservation_microusd':quote['specification']['reservation_microusd'],'payer_approved':True})
    assert response.status_code==202,response.text
    assert tick(database,settings,factory,store)
    response=mutation(client,root+'/profiles',{'connection_id':conn['id'],'model_id':model['id'],'title':'Explicit evidence review profile',
        'purpose':'evidence','max_output_tokens':4096,'data_policy_reference':'Synthetic project data-policy fixture; no external calls',
        'reason':'Approve a frozen evidence rubric for synthetic testing'})
    assert response.status_code==201,response.text
    profile=response.json()
    approved=mutation(client,root+'/profiles/'+profile['id']+'/approve',{'reviewed_hash':profile['fingerprint'],
        'expected_active_profile_id':None,'reason':'Review the fixed prompt, schema and synthetic model'})
    assert approved.status_code==200,approved.text
    env.update(ai=root,assessments=root+'/assessments',connection=conn,model=model,profile=profile,factory=factory,store=store)
    return env


def packet(env,**kw):
    current=env['client'].get(env['path']).json()
    body={'request_id':str(uuid4()),'package_id':current['id'],
        'deliverable_id':current['revision']['document']['deliverables'][0]['id'],'profile_id':env['profile']['id'],
        'expected_package_version':current['version'],'reason':'Inspect the exact submitted evidence packet before any disclosure',**kw}
    response=mutation(env['client'],env['assessments']+'/packets',body)
    assert response.status_code==201,response.text
    return response.json()


def plan(env,packet,**kw):
    response=mutation(env['client'],env['assessments']+'/plans',{'request_id':str(uuid4()),'packet_id':packet['id'],
        'reviewed_packet_hash':packet['content_hash'],'mode':'official','reason':'Review exact packet as an official synthetic assessment',**kw})
    assert response.status_code==201,response.text
    return response.json()


def grant(env,plan,actor=None,**kw):
    response=mutation(actor or env['client'],env['assessments']+'/plans/'+plan['id']+'/approve-data',
        {'reviewed_plan_hash':plan['content_hash'],'permission_reference':'Approved synthetic-data disclosure for this specific packet',
         'valid_until':(now()+timedelta(hours=1)).isoformat(),'packet_reviewed':True,'authorized_to_share':True,
         'reason':'The exact redacted packet and omissions were reviewed',**kw})
    return response


def enqueue(env,plan):
    path=env['assessments']+'/plans/'+plan['id']
    quote=env['client'].get(path+'/quote');assert quote.status_code==200,quote.text
    q=quote.json();body={'request_id':str(uuid4()),'quote_hash':q['quote_hash'],
        'confirmed_reservation_microusd':q['specification']['reservation_microusd'],'payer_approved':True}
    response=mutation(env['client'],path+'/run',body);assert response.status_code==202,response.text
    return response.json(),body


def complete(env,plan,factory=None):
    assert grant(env,plan).status_code==201
    job,_=enqueue(env,plan)
    item=claim(env['database'],env['settings'],UUID(job['id']));assert item
    execute(env['database'],env['settings'],factory or env['factory'],env['store'],item)
    detail=env['client'].get(env['assessments']+'/plans/'+plan['id']).json()
    assert detail['result_id'],detail
    response=env['client'].get(env['assessments']+'/results/'+detail['result_id']);assert response.status_code==200,response.text
    return response.json()
