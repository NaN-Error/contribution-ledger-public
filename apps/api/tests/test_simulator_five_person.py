"""Complete synthetic manual pipeline: non-code work -> independent credit -> USD example."""
from tests.auth_helpers import mutation
from tests.phase3_helpers import draft,approve,acknowledge,active_milestone,allocate
from tests.phase4_helpers import scope,create,advance
from tests.phase5_helpers import add,metadata,file_input,png_bytes
from tests.phase6_helpers import environment,award
from tests.phase7_helpers import preview,save


def test_five_person_actual_manual_credit_pipeline(client,database,settings):
    env=environment(client,database,settings)
    policy=draft(client,env['root'],version=1,key=1)
    assert approve(client,env['root'],policy).status_code==200
    assert acknowledge(client,env['root'],policy).status_code==200
    for name,actor in env['actors'].items():
        if name!='viewer':assert acknowledge(actor['client'],env['root'],policy).status_code==200
    env['policy']=policy
    milestone=active_milestone(client,env['root'],policy)
    people=[env['owner']['user']['id'],env['actors']['contributor']['id'],env['actors']['reviewer2']['id'],
            env['actors']['reviewer3']['id'],env['actors']['resolver']['id']]
    for pool,category,weights in [('release','art',[35,25,20,15,5]),('ongoing','research',[10,20,20,20,30])]:
        milestone=client.get(env['root']+'/milestones/'+milestone['id']).json()
        previous={a['id'] for a in milestone['allocations']}
        milestone=allocate(client,env['root'],milestone,atoms=100000,pool=pool,category=category,
            title=f'Synthetic {category} contribution outcome')
        allocation=next(a for a in milestone['allocations'] if a['id'] not in previous)
        plan=scope(people[0]);plan['title']=f'Synthetic {category} package'
        plan['intended_contributor_ids']=people
        plan['deliverables'][0]['attribution']['entries']=[{'user_id':uid,'role':'implementation','atoms':weight*1000}
                                                          for uid,weight in zip(people,weights)]
        response=create(client,env['root'],env['owner'],milestone,allocation,custom=plan)
        assert response.status_code==201,response.text
        package=response.json();path=env['root']+'/work-packages/'+package['id']
        if category=='art':
            response=add(client,path,kind='file',metadata=metadata(category='art'),
                         file=file_input(png_bytes(),'synthetic-character.png','image/png'))
        else:
            response=add(client,path,kind='statement',metadata=metadata(category='research'),
                text='Synthetic documented investigation outcome; not a claim about a real product.')
        assert response.status_code==201,response.text
        package=client.get(path).json()
        env['package']=advance(client,env['root'],package,'approve_scope','start','submit');env['path']=path
        award(env)
    record=preview(env)
    assert record['result']['status']=='calculated'
    actual={p['user_id']:p['amount_cents'] for p in record['result']['people']}
    assert [actual[uid] for uid in people]==[275000,235000,200000,165000,125000]
    assert record['snapshot']['source_award_count']==2
    assert record['snapshot']['pending_planned_atoms']==0
    assert all(p['denominator_atoms']==100000 for p in record['result']['pools'])
    stored=save(env,record)
    read=client.get(env['root']+'/simulator/scenarios/'+stored['id']).json()
    assert read['record']['result']==record['result']
    assert client.get(env['root']+'/contributions').json()['total_issued_atoms']==200000
