from copy import deepcopy
from uuid import UUID, uuid4
import pytest
from sqlalchemy import select
from tests.auth_helpers import mutation, invite, accept, other_client
from tests.phase3_helpers import acknowledge, allocate
from tests.phase4_helpers import environment, create, scope, action, advance, edit
from tests.test_work_packages import setup_package
from app.contributions.work_packages.calculation import input_from_snapshot
from app.contributions.budgets.models import BudgetAllocation, Milestone


def test_all_package_routes_deny_an_unrelated_workspace_user(client,database,settings):
    owner,root,_,_,item=setup_package(client,database)
    item=advance(client,root,item,'approve_scope','start','submit')
    submission=item['recent_submissions'][0]['id'];package=root+f"/work-packages/{item['id']}"
    with other_client(settings,database) as outsider:
        inv=invite(client,owner['workspace']['id'],email='outsider@example.test')
        accept(outsider,inv['token']) # same workspace, NO access to this project
        for path in [root+'/work-packages',root+'/work-packages/options',package,package+'/revisions/1',package+'/submissions/'+submission]:
            assert outsider.get(path).status_code==404
        assert action(outsider,root,item,'withdraw').status_code==404
        assert edit(outsider,root,item).status_code==404
        own_workspace=mutation(outsider,'/api/v1/workspaces',{'name':'Separate unrelated workspace'}).json()
        other_project=mutation(outsider,f"/api/v1/workspaces/{own_workspace['id']}/projects",{'name':'Different game','timezone':'UTC','currency':'USD'}).json()
        foreign=f"/api/v1/workspaces/{own_workspace['id']}/projects/{other_project['id']}/work-packages/{item['id']}"
        assert outsider.get(foreign).status_code==404
        assert outsider.get(foreign+'/revisions/1').status_code==404
        assert outsider.get(foreign+'/submissions/'+submission).status_code==404


@pytest.mark.parametrize('role',['viewer','finance','reviewer','contributor'])
def test_regular_roles_cannot_approve_cancel_or_edit_someone_elses_scope(client,database,settings,role):
    owner,root,milestone,allocation,item=setup_package(client,database)
    inv=invite(client,owner['workspace']['id'],project_id=owner['project']['id'],role=role)
    with other_client(settings,database) as member:
        user=accept(member,inv['token'])
        visible=member.get(root+f"/work-packages/{item['id']}").json()
        assert not visible['can_edit']
        assert member.get(root+'/work-packages/options').json()['can_create']==(role=='contributor')
        assert action(member,root,item,'approve_scope').status_code==403
        assert action(member,root,item,'cancel').status_code==403
        assert edit(member,root,item).status_code==403
        if role!='contributor':
            fake_owner={**owner,'user':user}
            assert create(member,root,fake_owner,milestone,allocation).status_code==403


def test_assigned_coordinator_can_edit_start_submit_but_not_approve(client,database,settings):
    owner,root,_,_,item=setup_package(client,database)
    inv=invite(client,owner['workspace']['id'],project_id=owner['project']['id'])
    with other_client(settings,database) as member:
        user=accept(member,inv['token'])
        policy=client.get(root+'/policies').json()['items'][0]
        assert acknowledge(member,root,policy).status_code==200
        raw=input_from_snapshot(item['revision']['document']).model_dump(mode='json')
        raw['coordinator_id']=user['id'];raw['intended_contributor_ids'].append(user['id'])
        result=edit(client,root,item,raw);assert result.status_code==200,result.text
        item=result.json()
        result=edit(member,root,item);assert result.status_code==200,result.text
        item=result.json();assert action(member,root,item,'approve_scope').status_code==403
        item=advance(client,root,item,'approve_scope')
        item=advance(member,root,item,'start','submit')
        assert item['state']=='submitted' and item['issued_atoms']==0
        assert action(member,root,item,'request_changes').status_code==403
        item=advance(member,root,item,'withdraw')
        assert item['state']=='changes_requested'


def test_reviewer_may_request_changes_not_issue_approval(client,database,settings):
    owner,root,_,_,item=setup_package(client,database)
    inv=invite(client,owner['workspace']['id'],project_id=owner['project']['id'],role='reviewer')
    with other_client(settings,database) as reviewer:
        accept(reviewer,inv['token'])
        acknowledge(reviewer,root,client.get(root+'/policies').json()['items'][0])
        item=advance(client,root,item,'approve_scope','start','submit')
        result=action(reviewer,root,item,'request_changes');assert result.status_code==200,result.text
        assert result.json()['state']=='changes_requested' and result.json()['issued_atoms']==0


def test_removed_access_cannot_read_archived_scope_or_submit(client,database,settings):
    owner,root,_,_,item=setup_package(client,database)
    inv=invite(client,owner['workspace']['id'],project_id=owner['project']['id'],role='reviewer')
    with other_client(settings,database) as member:
        user=accept(member,inv['token'])
        path=root+f"/work-packages/{item['id']}"
        assert member.get(path).status_code==200
        assert mutation(client,root+'/members/'+user['id'],{'role':'reviewer','status':'suspended',
            'expected_version':1,'reason':'Suspend this synthetic project membership'},method='patch').status_code==200
        assert member.get(path).status_code==404
        assert member.get(path+'/revisions/1').status_code==404
        assert action(member,root,item,'request_changes').status_code==404


def test_foreign_participant_rejected_without_disclosing_identity(client,database):
    owner,root,milestone,allocation=environment(client,database)
    raw=scope(owner['user']['id']);raw['coordinator_id']=str(uuid4())
    result=create(client,root,owner,milestone,allocation,raw)
    assert result.status_code==422 and result.json()['error']['code']=='participant_unavailable'
    assert raw['coordinator_id'] not in result.text


def test_wrong_milestone_and_cross_project_allocation_cannot_be_bound(client,database):
    owner,root,milestone,allocation=environment(client,database)
    bad={**milestone,'id':str(uuid4())}
    assert create(client,root,owner,bad,allocation).status_code==404
    project=mutation(client,f"/api/v1/workspaces/{owner['workspace']['id']}/projects",{'name':'Second isolated project','timezone':'UTC','currency':'USD'}).json()
    otherroot=f"/api/v1/workspaces/{owner['workspace']['id']}/projects/{project['id']}"
    assert create(client,otherroot,owner,milestone,allocation).status_code==404
    assert create(client,root,owner,milestone,{**allocation,'id':str(uuid4())}).status_code==404


def test_missing_policy_acknowledgement_blocks_scope_approval_not_draft_correction(client,database,settings):
    owner,root,_,_,item=setup_package(client,database)
    inv=invite(client,owner['workspace']['id'],project_id=owner['project']['id'])
    with other_client(settings,database) as member:
        accept(member,inv['token'])
        result=action(client,root,item,'approve_scope')
        assert result.status_code==409 and result.json()['error']['code']=='acknowledgements_required'
        revised=edit(client,root,item);assert revised.status_code==200,revised.text
        assert any('policy' in message for message in revised.json()['blockers'])


def test_finalized_projection_cannot_be_erased_by_cancel_or_edit(client,database):
    _,root,milestone,allocation,item=setup_package(client,database)
    # Simulate a future ledger-owned projection. No phase-4 API can write this.
    with database.session() as db:
        db.get(BudgetAllocation,UUID(allocation['id'])).issued_atoms=100
        db.get(Milestone,UUID(milestone['id'])).issued_atoms=100
        db.commit()
    item=client.get(root+f"/work-packages/{item['id']}").json()
    assert item['issued_atoms']==100 and not item['can_edit']
    assert action(client,root,item,'cancel').json()['error']['code']=='finalized_work_protected'
    assert edit(client,root,item).json()['error']['code']=='finalized_work_protected'
    assert client.get(root+'/milestones/'+milestone['id']).json()['issued_atoms']==100


def test_stale_parent_version_even_without_changed_scope_is_detected(client,database):
    owner,root,milestone,_,item=setup_package(client,database)
    allocate(client,root,milestone,atoms=10_000,title='Other planned task')
    result=action(client,root,item,'approve_scope')
    assert result.status_code==409 and result.json()['error']['code']=='review_hash_mismatch'


def test_pending_submission_requires_matching_csrf_and_origin(client,database):
    _,root,_,_,item=setup_package(client,database)
    response=client.post(root+f"/work-packages/{item['id']}/actions",json={'action':'cancel'})
    assert response.status_code==403
