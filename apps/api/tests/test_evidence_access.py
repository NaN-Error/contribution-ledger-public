from uuid import uuid4
import pytest
from tests.auth_helpers import mutation,invite,accept,other_client
from tests.phase5_helpers import evidence_environment,add,revise,command,metadata,file_input,png_bytes


def paths_for(path,record,snapshot_id):
    base=path+f"/evidence/{record['evidence_id']}/revisions"
    return [path+'/evidence',base,base+'/1',base+'/1/preview',base+'/1/image',base+'/1/download',
        path+'/evidence/snapshots',path+'/evidence/snapshots/'+snapshot_id]


def test_every_evidence_route_denies_other_project_and_workspace(client,database,settings):
    owner,root,path,package=evidence_environment(client,database)
    record=add(client,path,'file',file=file_input(png_bytes(),'character.png','image/png')).json()
    snap=client.get(path+'/evidence').json()['current_snapshot_id']
    inv=invite(client,owner['workspace']['id'])
    with other_client(settings,database) as outsider:
        accept(outsider,inv['token'])
        for url in paths_for(path,record,snap): assert outsider.get(url).status_code==404
        assert mutation(outsider,path+'/evidence',command(package)).status_code==404
        body={'metadata':record['document']['metadata'],'expected_revision':1,'expected_package_version':2,
            'request_id':str(uuid4()),'reason':'Attempt cross-project evidence replacement'}
        assert mutation(outsider,path+f"/evidence/{record['evidence_id']}/revisions",body).status_code==404
        other=mutation(outsider,'/api/v1/workspaces',{'name':'Unrelated synthetic workspace'}).json()
        project=mutation(outsider,f"/api/v1/workspaces/{other['id']}/projects",{'name':'Other game','timezone':'UTC','currency':'USD'}).json()
        foreign=f"/api/v1/workspaces/{other['id']}/projects/{project['id']}/work-packages/{package['id']}"
        for url in paths_for(path,record,snap): assert outsider.get(url.replace(path,foreign)).status_code==404


@pytest.mark.parametrize('role',['contributor','finance','viewer'])
def test_restricted_records_and_archived_packets_are_redacted(client,database,settings,role):
    owner,root,path,package=evidence_environment(client,database)
    record=add(client,path,'statement',metadata=metadata(visibility='restricted',title='Private synthetic claim')).json()
    snap=client.get(path+'/evidence').json()['current_snapshot_id']
    inv=invite(client,owner['workspace']['id'],project_id=owner['project']['id'],role=role)
    with other_client(settings,database) as member:
        accept(member,inv['token'])
        visible=member.get(path+'/evidence').json();assert visible['items']==[] and visible['restricted_entries']==1
        assert member.get(path+f"/evidence/{record['evidence_id']}/revisions/1").status_code==404
        hidden=member.get(path+'/evidence/snapshots/'+snap).json()
        assert hidden['redacted'] and hidden['document']['entries']==[{'restricted':True}]
        assert 'Private synthetic claim' not in str(hidden)
        changed=revise(client,path,record,metadata=metadata(visibility='project')).json()
        assert member.get(path+f"/evidence/{record['evidence_id']}/revisions/2").status_code==200
        assert member.get(path+f"/evidence/{record['evidence_id']}/revisions/1").status_code==404
        assert member.get(path+'/evidence/snapshots/'+snap).json()['redacted']
        # Changing current visibility back to restricted also protects formerly public history.
        revise(client,path,changed,metadata=metadata(visibility='restricted'))
        assert member.get(path+f"/evidence/{record['evidence_id']}/revisions/2").status_code==404


def test_reviewer_reads_restricted_evidence_but_cannot_revise_another_author(client,database,settings):
    owner,root,path,package=evidence_environment(client,database)
    record=add(client,path,metadata=metadata(visibility='restricted')).json()
    inv=invite(client,owner['workspace']['id'],project_id=owner['project']['id'],role='reviewer')
    with other_client(settings,database) as member:
        accept(member,inv['token'])
        assert member.get(path+f"/evidence/{record['evidence_id']}/revisions/1").status_code==200
        assert revise(member,path,record,text='Another person attempts to change the statement').status_code==403
        assert add(member,path,text='Reviewer note supplied as separate evidence.').status_code==201


@pytest.mark.parametrize('role',['viewer','finance','contributor'])
def test_unassigned_roles_cannot_add_evidence_or_retire(client,database,settings,role):
    owner,root,path,package=evidence_environment(client,database)
    record=add(client,path,'file').json()
    inv=invite(client,owner['workspace']['id'],project_id=owner['project']['id'],role=role)
    with other_client(settings,database) as member:
        accept(member,inv['token'])
        assert add(member,path).status_code==403
        assert mutation(member,path+f"/evidence/{record['evidence_id']}/revisions/1/retire",{
            'expected_package_version':2,'reviewed':True,'reason':'Unauthorized synthetic retirement request'}).status_code==403


def test_revoked_member_cannot_redownload_or_reopen_cached_url(client,database,settings):
    owner,root,path,package=evidence_environment(client,database)
    record=add(client,path,'file',file=file_input(png_bytes(),'image.png','image/png')).json()
    snap=client.get(path+'/evidence').json()['current_snapshot_id']
    inv=invite(client,owner['workspace']['id'],project_id=owner['project']['id'],role='reviewer')
    with other_client(settings,database) as member:
        user=accept(member,inv['token'])
        response=member.get(path+f"/evidence/{record['evidence_id']}/revisions/1/image")
        assert response.status_code==200 and 'no-store' in response.headers['cache-control']
        assert mutation(client,root+'/members/'+user['id'],{'role':'reviewer','status':'suspended',
            'expected_version':1,'reason':'Suspend a synthetic member before another download'},method='patch').status_code==200
        for url in paths_for(path,record,snap):assert member.get(url).status_code==404


def test_upload_requires_csrf_origin_and_obeys_special_body_bound(client,database):
    _,_,path,package=evidence_environment(client,database)
    body=command(package,'file',file=file_input(b'x'*100000))
    assert client.post(path+'/evidence',json=body).status_code==403
    csrf=client.get('/api/v1/auth/session').json()['csrf_token']
    assert client.post(path+'/evidence',json=body,headers={'Origin':'https://attacker.test','X-CSRF-Token':csrf}).status_code==403
    response=mutation(client,path+'/evidence',body);assert response.status_code==201,response.text
    too_large=client.post(path+'/evidence',content=b'x'*3_000_000,headers={'Origin':'http://testserver',
        'X-CSRF-Token':csrf,'Content-Type':'application/json'})
    assert too_large.status_code==413
    compressed=client.post(path+'/evidence',content=b'{}',headers={'Origin':'http://testserver',
        'X-CSRF-Token':csrf,'Content-Type':'application/json','Content-Encoding':'gzip'})
    assert compressed.status_code==415


def test_same_workspace_cannot_reference_another_projects_evidence(client,database):
    owner,root,path,package=evidence_environment(client,database)
    record=add(client,path).json()
    other=mutation(client,f"/api/v1/workspaces/{owner['workspace']['id']}/projects",{'name':'Second game','timezone':'UTC','currency':'USD'}).json()
    wrong=path.replace(owner['project']['id'],other['id'])
    assert client.get(wrong+f"/evidence/{record['evidence_id']}/revisions/1").status_code==404
