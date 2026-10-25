from copy import deepcopy
from uuid import UUID, uuid4
import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DatabaseError
from tests.auth_helpers import mutation
from tests.phase3_helpers import proposal, decision
from tests.phase4_helpers import environment, scope, create, action, advance, edit
from app.contributions.work_packages.models import WorkPackageRevision, WorkPackageEvent, WorkSubmission


def setup_package(client,database):
    owner,root,milestone,allocation=environment(client,database)
    result=create(client,root,owner,milestone,allocation)
    assert result.status_code==201,result.text
    return owner,root,milestone,allocation,result.json()


def test_lifecycle_revisions_and_submissions_never_award_credit(client,database):
    _,root,milestone,_,item=setup_package(client,database)
    assert item['state']=='draft' and item['issued_atoms']==0
    original=deepcopy(item['revision'])
    item=advance(client,root,item,'approve_scope','start','submit')
    assert item['state']=='submitted' and len(item['recent_submissions'])==1
    sid=item['recent_submissions'][0]['id']; path=root+f"/work-packages/{item['id']}"
    stored=client.get(path+'/submissions/'+sid).json()
    assert stored['snapshot']['evidence_status']=='captured_unreviewed'
    assert edit(client,root,item).status_code==409
    item=advance(client,root,item,'withdraw')
    assert item['state']=='changes_requested'
    assert action(client,root,item,'approve_scope').status_code==409
    revised=edit(client,root,item);assert revised.status_code==200,revised.text
    item=revised.json();assert item['scope_revision']==2 and item['approved_revision'] is None
    item=advance(client,root,item,'approve_scope','start','submit')
    assert item['issued_atoms']==0 and len(item['recent_submissions'])==2
    assert client.get(path+'/revisions/1').json()==original
    assert client.get(path+'/submissions/'+sid).json()==stored
    assert client.get(root+'/milestones/'+milestone['id']).json()['issued_atoms']==0


def test_duplicate_binding_and_stale_create_fail(client,database):
    owner,root,milestone,allocation,item=setup_package(client,database)
    assert create(client,root,owner,milestone,allocation).status_code==409
    assert action(client,root,item,'start').status_code==409
    assert action(client,root,item,'submit').status_code==409


def test_stale_edits_and_review_hashes_fail(client,database):
    _,root,_,_,item=setup_package(client,database)
    assert edit(client,root,item,reviewed_hash='0'*64).status_code==409
    changed=edit(client,root,item);assert changed.status_code==200,changed.text
    assert edit(client,root,item).status_code==409
    assert action(client,root,item,'approve_scope').status_code==409


def test_amending_approved_scope_invalidates_approval(client,database):
    _,root,_,_,item=setup_package(client,database)
    item=advance(client,root,item,'approve_scope','start')
    changed=edit(client,root,item);assert changed.status_code==200,changed.text
    item=changed.json()
    assert item['state']=='draft' and item['approved_revision'] is None
    assert action(client,root,item,'submit').status_code==409
    assert item['history'][0]['action']=='scope_amended'


def test_cancel_releases_only_unissued_budget_with_linked_decision(client,database):
    _,root,milestone,_,item=setup_package(client,database)
    before=client.get(root+'/milestones/'+milestone['id']).json()
    result=action(client,root,item,'cancel');assert result.status_code==200,result.text
    item=result.json();assert item['state']=='cancelled' and item['budget_atoms']==0
    assert item['scope_budget_atoms']==100_000 and item['issued_atoms']==0
    after=client.get(root+'/milestones/'+milestone['id']).json()
    assert after['available_atoms']==before['available_atoms']+100_000
    assert after['reserve_floor_atoms']==before['reserve_floor_atoms']
    assert item['history'][0]['details']['budget_amendment_id']
    assert action(client,root,item,'cancel').status_code==409
    assert edit(client,root,item).status_code==409


def test_linked_budget_cannot_bypass_scope_and_resize_rebinds_draft(client,database):
    _,root,milestone,allocation,item=setup_package(client,database)
    cancel=proposal(client,root,milestone,{'kind':'cancel_allocation','allocation_id':allocation['id']})
    assert cancel.status_code==409 and cancel.json()['error']['code']=='linked_package'
    too_small=proposal(client,root,milestone,{'kind':'resize_allocation','allocation_id':allocation['id'],'atoms':99_999})
    assert too_small.status_code==409
    resize=proposal(client,root,milestone,{'kind':'resize_allocation','allocation_id':allocation['id'],'atoms':120_000})
    assert resize.status_code==201,resize.text
    result=decision(client,root,milestone,resize.json());assert result.status_code==200,result.text
    changed=client.get(root+f"/work-packages/{item['id']}").json()
    assert changed['scope_revision']==2 and changed['version']==2 and changed['budget_atoms']==120_000
    assert changed['unplanned_atoms']==20_000 and changed['blockers']
    assert action(client,root,item,'approve_scope').status_code==409


def test_resize_approved_package_requires_visible_amendment(client,database):
    _,root,milestone,allocation,item=setup_package(client,database)
    item=advance(client,root,item,'approve_scope')
    result=proposal(client,root,milestone,{'kind':'resize_allocation','allocation_id':allocation['id'],'atoms':120_000})
    assert result.status_code==409 and result.json()['error']['code']=='package_amendment_required'


def test_proposal_from_before_binding_is_rechecked_on_approval(client,database):
    owner,root,milestone,allocation=environment(client,database)
    old=proposal(client,root,milestone,{'kind':'cancel_allocation','allocation_id':allocation['id']}).json()
    result=create(client,root,owner,milestone,allocation);assert result.status_code==201,result.text
    result=decision(client,root,milestone,old)
    assert result.status_code==409 and result.json()['error']['code']=='linked_package'


@pytest.mark.parametrize('kind',['no_deliverables','unassigned_units','incomplete_percent','unplanned_budget'])
def test_incomplete_plans_save_as_drafts_but_cannot_be_approved(client,database,kind):
    owner,root,milestone,allocation=environment(client,database)
    raw=scope(owner['user']['id'])
    if kind=='no_deliverables':raw['deliverables']=[]
    elif kind=='unassigned_units':raw['deliverables'][0]['attribution']['entries']=[]
    elif kind=='incomplete_percent':raw['deliverables'][0]['attribution']={'mode':'percent','entries':[]}
    elif kind=='unplanned_budget':raw['deliverables'][0]['budget_atoms']=60_000;raw['deliverables'][0]['attribution']['entries'][0]['atoms']=60_000
    result=create(client,root,owner,milestone,allocation,raw);assert result.status_code==201,result.text
    item=result.json();assert item['blockers'] and 'approve_scope' not in item['allowed_actions']
    assert action(client,root,item,'approve_scope').status_code==409


def test_splitting_does_not_create_budget(client,database):
    owner,root,milestone,allocation=environment(client,database)
    raw=scope(owner['user']['id']);second=deepcopy(raw['deliverables'][0]);raw['deliverables'].append(second)
    result=create(client,root,owner,milestone,allocation,raw)
    assert result.status_code==409 and result.json()['error']['code']=='package_budget_exceeded'
    for d in raw['deliverables']:d['budget_atoms']=50_000;d['attribution']['entries'][0]['atoms']=50_000
    result=create(client,root,owner,milestone,allocation,raw);assert result.status_code==201,result.text
    assert result.json()['deliverable_atoms']==100_000


def test_filters_empty_states_and_history_access(client,database):
    _,root,_,_,item=setup_package(client,database)
    collection=root+'/work-packages'
    assert client.get(collection+'?q=disconnected').json()['total']==1
    assert client.get(collection+'?state=completed').json()['items']==[]
    assert client.get(collection+'?category=art').json()['items']==[]
    assert client.get(collection+'?state=bogus').status_code==422
    assert client.get(collection+f"/{item['id']}/revisions/99").status_code==404
    assert client.get(collection+f"/{item['id']}/submissions/{uuid4()}").status_code==404
    assert client.get(collection+'/options').json()['allocations']==[]


def test_request_changes_requires_new_scope_revision(client,database):
    _,root,_,_,item=setup_package(client,database)
    item=advance(client,root,item,'approve_scope','start','submit','request_changes')
    assert item['state']=='changes_requested' and item['approved_revision'] is None
    assert action(client,root,item,'submit').status_code==409


def test_history_and_bindings_reject_ordinary_database_mutation(client,database):
    _,root,_,_,item=setup_package(client,database)
    item=advance(client,root,item,'approve_scope','start','submit')
    for table in ['work_package_revisions','work_package_participants','work_package_events','work_submissions','work_packages']:
        with pytest.raises(DatabaseError),database.engine.begin() as connection:
            connection.execute(text(f'DELETE FROM {table}'))
    with pytest.raises(DatabaseError),database.engine.begin() as connection:
        connection.execute(text("UPDATE work_packages SET policy_id='00000000000000000000000000000000'"))
    with pytest.raises(DatabaseError),database.engine.begin() as connection:
        connection.execute(text("UPDATE work_package_revisions SET reason='Mutate old reason'"))


def test_no_completion_issuance_or_direct_status_endpoint(client,database):
    _,root,_,_,item=setup_package(client,database)
    for name in ['complete','issue_credit','approve_award']:
        assert action(client,root,item,name).status_code==422
    assert mutation(client,root+f"/work-packages/{item['id']}",{'state':'completed'},method='patch').status_code==405
    assert action(client,root,item,'approve_scope',reviewed=False).status_code==422
