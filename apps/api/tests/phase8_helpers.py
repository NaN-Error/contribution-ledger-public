"""Synthetic GitHub transport and application fixtures. Never a live provider."""
from copy import deepcopy
from datetime import timedelta
from urllib.parse import parse_qs,urlsplit
from uuid import uuid4,UUID
from sqlalchemy import select
from app.integrations.github.client import GitHubError
from app.integrations.github.models import GitHubImport,GitHubRepository
from app.integrations.github.importer import step
from app.security.tokens import now
from tests.auth_helpers import mutation,bootstrap
from tests.phase5_helpers import evidence_environment

SHA_A='a'*40
SHA_B='b'*40
GH_USER={'id':7001,'login':'fictional-author','type':'User'}
GH_MERGER={'id':7002,'login':'fictional-merger','type':'User'}
GH_BOT={'id':7003,'login':'fictional-check-bot[bot]','type':'Bot'}
REPO={'id':9001,'full_name':'synthetic/game','private':True,'default_branch':'main','permissions':{'admin':True}}
STAMP='2026-09-10T12:00:00Z'

def commit(sha=SHA_A):
    return {'sha':sha,'author':GH_USER,'committer':GH_MERGER,'parents':[{'sha':SHA_B}],
        'commit':{'message':'Synthetic reconnection implementation\n\nCo-authored-by: Fictional helper <helper@example.test>',
        'author':{'name':'Unverified author','email':'owner@example.test','date':STAMP},
        'committer':{'name':'Unverified committer','email':'committer@example.test','date':STAMP},
        'verification':{'verified':False,'reason':'unsigned'}},
        'files':[{'filename':'game/net.py','sha':SHA_B,'status':'modified','additions':5,'deletions':2,'patch':'@@ -1 +1 @@\n-old\n+new'}]}

def pull():
    return {'number':1,'title':'Synthetic reconnection PR','body':'A fixture, not actual game source.',
      'created_at':STAMP,'updated_at':STAMP,'state':'closed','merged':True,'user':GH_USER,'merged_by':GH_MERGER,
      'head':{'sha':SHA_A,'ref':'feature'},'base':{'sha':SHA_B,'ref':'main'},'merge_commit_sha':SHA_A,'commits':1,'changed_files':1}

class FakeGitHub:
    def __init__(self):
        self.calls=[];self.verify_calls=0;self.on_get=None;self.error=None;self.pull_title=None
        self.head_changed=False;self.more_for=set();self.empty=False;self.no_repo_admin=False
    def ensure_configured(self): pass
    def authorize_url(self,state):return 'https://github.com/login/oauth/authorize?state='+state+'&code_challenge_method=S256&code_challenge=fixture'
    def verify_authorization(self,code,state,installation_id):
        self.verify_calls+=1
        if installation_id!=501:raise GitHubError('github_installation_not_authorized')
        if self.error:raise self.error
        return {'github_user_id':7001,'github_login':'fictional-author','installation_id':501,'account':'synthetic',
                'repositories':[{'github_id':9001,'full_name':'synthetic/game','private':True,'default_branch':'main'}]}
    def check_repository_authority(self,token,repo,connection):
        assert token=='synthetic-in-memory-token'
        if self.no_repo_admin:raise GitHubError('github_authority_revoked')
    def repository_token(self,installation_id,repository_id):
        assert installation_id==501 and repository_id==9001
        return 'synthetic-in-memory-token'
    def get(self,token,path,params=None):
        assert token=='synthetic-in-memory-token'
        self.calls.append((path,deepcopy(params)))
        if self.on_get:self.on_get(path)
        if self.error:raise self.error
        base='/repos/synthetic/game'
        if path==base:return deepcopy(REPO),False
        if path==base+'/pulls':data=[pull()]
        elif path==base+'/issues':data=[{'number':2,'title':'Synthetic issue','body':'Repro steps','created_at':STAMP,'updated_at':STAMP,'user':GH_USER},dict(pull(),pull_request={'url':'ignored'})]
        elif path==base+'/issues/2':data={'number':2,'title':'Synthetic issue','body':'Repro steps','created_at':STAMP,'updated_at':STAMP,'user':GH_USER}
        elif path==base+'/commits':data=[] if self.empty else [commit()]
        elif path==base+'/pulls/1':
            data=pull()
            if self.pull_title:data['title']=self.pull_title
            if self.head_changed:data['head']['sha']='c'*40
        elif path==base+'/pulls/1/files':data=commit()['files']
        elif path==base+'/pulls/1/commits':data=[commit()]
        elif path==base+'/pulls/1/reviews':data=[{'id':8001,'body':'Synthetic review','state':'APPROVED','user':GH_MERGER,'commit_id':SHA_A,'submitted_at':STAMP}]
        elif path in {base+'/issues/1/comments',base+'/issues/2/comments'}:data=[{'id':8100+int(path.split('/')[-2]),'body':'Synthetic observation','user':GH_USER,'created_at':STAMP}]
        elif path==base+'/pulls/1/comments':data=[{'id':8201,'body':'Synthetic inline review','user':GH_MERGER,'commit_id':SHA_A,'created_at':STAMP}]
        elif path==base+'/commits/'+SHA_A:data=commit()
        elif path==base+'/commits/'+SHA_A+'/check-runs':data={'check_runs':[{'id':8301,'name':'Synthetic check','status':'completed','conclusion':'success','head_sha':SHA_A,'app':GH_BOT}]}
        else:raise AssertionError('Unexpected synthetic endpoint '+path)
        return deepcopy(data),path in self.more_for

def configure(settings,client):
    client._transport.raise_server_exceptions=True
    settings.github_enabled=True;settings.github_app_id=123;settings.github_client_id='Iv1.synthetic'
    settings.github_callback_url='http://testserver/github/callback'
    fake=FakeGitHub();client.app.state.github_client=fake
    return fake

def flow(client,root):
    response=mutation(client,root+'/github/authorize',{'installation_id':501,'reason':'Review synthetic repository authorization'})
    assert response.status_code==201,response.text
    state=parse_qs(urlsplit(response.json()['authorize_url']).query)['state'][0]
    return state

def authorize(client,root):
    state=flow(client,root)
    response=mutation(client,'/api/v1/github/callback',{'state':state,'code':'synthetic-code-12345'})
    assert response.status_code==200,response.text
    proof=response.json()
    response=mutation(client,'/api/v1/github/connect',{'flow_id':proof['flow_id'],'reviewed_proof_hash':proof['proof_hash'],
      'repository_ids':[9001],'reason':'Share the selected synthetic source repository','sharing_confirmed':True})
    assert response.status_code==201,response.text
    return client.get(root+'/github').json()

def environment(client,database,settings,package=False):
    if package:owner,root,path,pkg=evidence_environment(client,database)
    else:
        owner=bootstrap(client,database);root=f"/api/v1/workspaces/{owner['workspace']['id']}/projects/{owner['project']['id']}";path=pkg=None
    fake=configure(settings,client);overview=authorize(client,root)
    return owner,root,fake,overview,path,pkg

def import_body(repo,**overrides):
    return {'repository_id':repo,'start_at':'2026-09-01T00:00:00Z','end_before':'2026-09-12T00:00:00Z',
       'request_limit':200,'entity_limit':20,'request_id':str(uuid4()),'reason':'Capture a bounded fictional history','reviewed':True,**overrides}

def queue(client,root,overview,**overrides):
    body=import_body(overview['repositories'][0]['id'],**overrides)
    response=mutation(client,root+'/github/imports',body)
    assert response.status_code==201,response.text
    return response.json(),body

def run(database,settings,fake,job_id,max_steps=100):
    results=[]
    for _ in range(max_steps):
        result=step(database,settings,fake,UUID(job_id));results.append(result)
        if result in {'completed','completed_incomplete','failed','paused','cancelled','idle','discarded'}:break
    return results

def due(database,job_id):
    with database.session() as db:
        job=db.get(GitHubImport,UUID(job_id));job.next_attempt_at=now()-timedelta(seconds=1)
        db.get(GitHubRepository,job.repository_id).retry_not_before=now()-timedelta(seconds=1);db.commit()
