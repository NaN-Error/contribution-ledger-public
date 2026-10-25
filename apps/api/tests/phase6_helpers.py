"""Synthetic setup; session seeding bypasses login only, not application authorization."""
from contextlib import ExitStack
from uuid import UUID, uuid4
from fastapi.testclient import TestClient
from app.main import create_app
from app.auth.models import User
from app.auth.service import create_session
from app.projects.models import WorkspaceMembership, ProjectMembership
from tests.auth_helpers import bootstrap, mutation
from tests.phase3_helpers import base, policy_body, approve, acknowledge, active_milestone, allocate
from tests.phase4_helpers import scope, create, advance
from tests.phase5_helpers import add


def environment(client,database,settings,*,minimum=1,partial=False,evidence=True):
    client._transport.raise_server_exceptions=True
    owner=bootstrap(client,database);root=base(owner)
    actors={};wid=UUID(owner['workspace']['id']);pid=UUID(owner['project']['id'])
    for name,role in [('reviewer','reviewer'),('reviewer2','reviewer'),('reviewer3','reviewer'),
                      ('resolver','reviewer'),('contributor','contributor'),('viewer','viewer')]:
        actor_client=TestClient(create_app(settings,database),raise_server_exceptions=True)
        with database.session() as db:
            # No new password hashing needed for synthetic pre-authenticated actors.
            actor=User(id=uuid4(),email=f'{name}@example.test',display_name='Synthetic '+name,
                       password_hash=db.get(User,UUID(owner['user']['id'])).password_hash)
            db.add(actor);db.flush()
            db.add(WorkspaceMembership(workspace_id=wid,user_id=actor.id,role='member',status='active',version=1));db.flush()
            db.add(ProjectMembership(workspace_id=wid,project_id=pid,user_id=actor.id,role=role,status='active',version=1));db.flush()
            _,token=create_session(db,actor,settings);db.commit()
            actors[name]={'id':str(actor.id),'client':actor_client}
        actor_client.cookies.set(settings.session_cookie_name,token)
    data=policy_body(client,root);data['rules']['review']['minimum_independent_reviewers']=minimum
    result=mutation(client,root+'/policies',data);assert result.status_code==201,result.text
    policy=result.json();assert approve(client,root,policy).status_code==200
    assert acknowledge(client,root,policy).status_code==200
    for name,a in actors.items():
        if name!='viewer':assert acknowledge(a['client'],root,policy).status_code==200
    milestone=active_milestone(client,root,policy)
    milestone=allocate(client,root,milestone,atoms=100000)
    alloc=milestone['allocations'][0]
    planned=scope(owner['user']['id'])
    if partial:
        planned['deliverables'][0]['budget_atoms']=60000
        planned['deliverables'][0]['attribution']['entries'][0]['atoms']=60000
        second=scope(owner['user']['id'],40000)['deliverables'][0]
        second['title']='Independent test coverage';planned['deliverables'].append(second)
    result=create(client,root,owner,milestone,alloc,custom=planned);assert result.status_code==201,result.text
    package=result.json();path=root+'/work-packages/'+package['id']
    if evidence:
        result=add(client,path);assert result.status_code==201,result.text
        package=client.get(path).json()
    package=advance(client,root,package,'approve_scope','start','submit')
    return {'owner':owner,'root':root,'path':path,'package':package,'policy':policy,'actors':actors,
        'client':client,'database':database,'settings':settings}


def assignment_body(env,index=0,reviewers=None):
    options=env['client'].get(env['root']+'/reviews/options',params={'package_id':env['package']['id']}).json()
    target=options['items'][index]
    return {'request_id':str(uuid4()),'package_id':env['package']['id'],'deliverable_id':target['deliverable_id'],
        'expected_package_version':options['package_version'],'reviewed_target_hash':target['target_hash'],
        'reviewer_ids':reviewers or [env['actors']['reviewer']['id']],
        'reason':'Assign independent reviewers to the exact submitted evidence'}


def assign(env,index=0,reviewers=None):
    response=mutation(env['client'],env['root']+'/reviews',assignment_body(env,index,reviewers))
    assert response.status_code==201,response.text
    return response.json()


def decision_body(review,decision='accept'):
    refs=[r['ref'] for r in review['target']['evidence_sources'] if not r.get('restricted')]
    return {'request_id':str(uuid4()),'reviewed_target_hash':review['target_hash'],'decision':decision,
        'findings':[{'criterion_id':c['id'],'result':'supported' if decision=='accept' else 'insufficient',
            'evidence_refs':refs[:1],'explanation':'The synthetic evidence was inspected against this criterion.'} for c in review['target']['criteria']],
        'evidence_reviewed':True,'independent':True,'reason':'Human reviewer examined this exact packet and attribution'}


def vote(env,review,who='reviewer',decision='accept',body=None):
    reviewer=env['actors'][who]['client']
    response=mutation(reviewer,env['root']+'/reviews/'+review['id']+'/decisions',body or decision_body(review,decision))
    assert response.status_code==200,response.text
    return response.json()


def final_body(review):
    return {'request_id':str(uuid4()),'reviewed_decisions_hash':review['decisions_hash'],
        'reviewed':True,'reason':'Finalize the independent review quorum for this exact decision set'}


def finalize(env,review,who='reviewer',body=None):
    response=mutation(env['actors'][who]['client'],env['root']+'/reviews/'+review['id']+'/finalize',body or final_body(review))
    assert response.status_code==200,response.text
    return response.json()


def award(env,index=0):
    return finalize(env,vote(env,assign(env,index)))


def open_dispute(env,final):
    response=mutation(env['client'],env['root']+'/disputes',{'request_id':str(uuid4()),
        'award_id':final['finalized_record_id'],'reason':'The approved credit attribution omitted another contributor.'})
    assert response.status_code==201,response.text
    return response.json()


def resolver(env,dispute):
    response=mutation(env['client'],env['root']+'/disputes/'+dispute['id']+'/assignments',{
        'request_id':str(uuid4()),'reviewed_context_hash':dispute['context_hash'],
        'resolver_id':env['actors']['resolver']['id'],'reason':'Assign a resolver not involved in the original acceptance'})
    assert response.status_code==200,response.text
    return response.json()


def correction(env,dispute,disposition='reallocate',entries=None):
    if entries is None:entries=[{'user_id':env['owner']['user']['id'],'role':'implementation','atoms':60000},
        {'user_id':env['actors']['contributor']['id'],'role':'testing','atoms':40000}]
    body={'request_id':str(uuid4()),'reviewed_context_hash':dispute['context_hash'],'disposition':disposition,
        'attributions':entries if disposition=='reallocate' else [],'reviewer_ids':[env['actors']['resolver']['id']],
        'reason':'Resolve the documented attribution concern without changing the accepted budget'}
    response=mutation(env['actors']['resolver']['client'],env['root']+'/disputes/'+dispute['id']+'/proposals',body)
    assert response.status_code==201,response.text
    return response.json()
