from uuid import uuid4
from tests.auth_helpers import mutation
from tests.phase3_helpers import active_milestone,allocate
from tests.phase4_helpers import scope,advance
from tests.phase5_helpers import add
from tests.phase6_helpers import environment as prior_environment,award
from tests.phase8_helpers import configure,authorize,queue,run


def command(batch,**extra):
    return {'request_id':str(uuid4()),'expected_version':batch['version'],
        'reason':'Explicit human review of historical reconstruction',**extra}


def refresh(env):
    env['batch']=env['client'].get(env['base']).json()
    return env['batch']


def call(env,suffix,body,*,expected=200,client=None):
    response=mutation(client or env['client'],env['base']+suffix,body)
    assert response.status_code==expected,response.text
    if 'batch' in response.json():env['batch']=response.json()['batch']
    return response.json()


def environment(client,database,settings):
    env=prior_environment(client,database,settings)
    milestone=active_milestone(client,env['root'],env['policy'],total=1000000,reserve=100000)
    body={'request_id':str(uuid4()),'milestone_id':milestone['id'],'title':'Historical game opening',
        'start_at':'2026-09-01T00:00:00Z','end_before':'2026-09-12T00:00:00Z',
        'historical_scope':'Reconstruct the explicitly selected historical game work, including non-code omissions.',
        'agreement_reference':'Reviewed retrospective allocation agreement, not an assertion it existed in the past.',
        'reason':'Define a bounded historical scope under reviewed rules'}
    response=mutation(client,env['root']+'/reconstruction',body)
    assert response.status_code==201,response.text
    env['batch']=response.json();env['base']=env['root']+'/reconstruction/'+env['batch']['id']
    env['batch_create_body']=body
    return env


def approve(env):
    refresh(env)
    return call(env,'/approve-scope',command(env['batch'],reviewed=True,reviewed_hash=env['batch']['scope_review_hash']))


def manual(env,title='Historical character artwork',category='art'):
    result=call(env,'/candidates',command(env['batch'],document={'title':title,'category':category,
        'summary':'Manually documented contribution with independently reviewable historical evidence.',
        'unresolved_questions':[],'identity_resolutions':[]}),expected=201)
    cid=result['result']['candidate_id'];return next(c for c in env['batch']['candidates'] if c['id']==cid)


def imported(env):
    fake=configure(env['settings'],env['client']);overview=authorize(env['client'],env['root'])
    job,_=queue(env['client'],env['root'],overview)
    assert run(env['database'],env['settings'],fake,job['id'])[-1] in {'completed','completed_incomplete'}
    result=call(env,'/group-import',command(env['batch'],import_id=job['id']))
    return job,result


def promotion_body(env,candidate,allocation):
    planned=scope(env['owner']['user']['id'],allocation['atoms'])
    planned['title']=candidate['document']['title']
    return command(env['batch'],candidate_id=candidate['id'],allocation_id=allocation['id'],
        expected_allocation_version=allocation['version'],scope=planned,
        reviewed_hash=candidate['review_hash'],reviewed=True,project_sharing_confirmed=True)


def allocate_for(env,candidate,atoms=100000):
    milestone=env['client'].get(env['root']+'/milestones/'+env['batch']['milestone_id']).json()
    old={a['id'] for a in milestone['allocations']}
    updated=allocate(env['client'],env['root'],milestone,atoms=atoms,title=candidate['document']['title'],category=candidate['document']['category'])
    return next(a for a in updated['allocations'] if a['id'] not in old)


def promote(env,candidate):
    allocation=allocate_for(env,candidate);refresh(env)
    candidate=next(c for c in env['batch']['candidates'] if c['id']==candidate['id'])
    result=call(env,'/promote',promotion_body(env,candidate,allocation),expected=201)
    package=env['client'].get(env['root']+'/work-packages/'+result['result']['package_id']).json()
    return package


def accept_package(env,package):
    path=env['root']+'/work-packages/'+package['id']
    if not env['client'].get(path+'/evidence').json().get('items'):
        response=add(env['client'],path);assert response.status_code==201,response.text
    package=env['client'].get(path).json()
    package=advance(env['client'],env['root'],package,'approve_scope','start','submit')
    changed={**env,'path':path,'package':package}
    final=award(changed)
    refresh(env)
    return changed,final
