from datetime import timedelta
from uuid import UUID
import pytest
from sqlalchemy import select, text, func
from sqlalchemy.exc import DBAPIError
from tests.auth_helpers import bootstrap, mutation, invite, accept, other_client
from tests.phase3_helpers import base, policy_body, draft, approve, acknowledge, ready_policy, milestone
from app.policies.models import PolicyVersion, PolicyApproval, PolicyAcknowledgement
from app.security.tokens import now


def test_draft_approval_ack_and_new_revision_are_distinct(client, database):
    owner = bootstrap(client, database); root = base(owner)
    item = draft(client, root)
    assert item['state'] == 'draft' and not item['usable_for_new_milestones']
    assert len(item['acknowledgements']['missing_user_ids']) == 1
    assert acknowledge(client, root, item).status_code == 409
    approved = approve(client, root, item); assert approved.status_code == 200
    assert approved.json()['state'] == 'awaiting_acknowledgements'
    accepted = acknowledge(client, root, item); assert accepted.status_code == 200
    assert accepted.json()['state'] == 'effective'
    assert accepted.json()['usable_for_new_milestones']
    assert acknowledge(client, root, item).status_code == 200
    with database.session() as db:
        assert db.scalar(select(func.count()).select_from(PolicyAcknowledgement)) == 1
    successor = draft(client, root, version=1)
    assert successor['version'] == 2 and successor['predecessor_id'] == item['id']
    assert not successor['my_acknowledgement']
    assert client.get(root + '/policies/' + item['id']).json()['usable_for_new_milestones']
    assert approve(client, root, successor).status_code == 200
    old = client.get(root + '/policies/' + item['id']).json()
    assert old['ready_for_pinned_work'] and not old['usable_for_new_milestones']
    current = client.get(root + '/policies/' + successor['id']).json()
    assert current['is_current_candidate'] and not current['usable_for_new_milestones']
    assert acknowledge(client, root, successor).json()['usable_for_new_milestones']


def test_hashes_latest_versions_and_duplicate_approval(client, database):
    root = base(bootstrap(client, database)); item = draft(client, root)
    wrong = approve(client, root, item, reviewed_content_hash='b'*64)
    assert wrong.status_code == 409
    assert mutation(client, root + '/policies', policy_body(client, root, version=0)).status_code == 409
    successor = draft(client, root, version=1)
    assert approve(client, root, item).status_code == 409
    assert approve(client, root, successor).status_code == 200
    assert approve(client, root, successor).status_code == 409
    bad_ack = mutation(client, root + f"/policies/{successor['id']}/acknowledge", {'reviewed_content_hash': item['content_hash'], 'reviewed': True})
    assert bad_ack.status_code == 409


def test_future_policy_never_activates_early_and_backdating_fails(client, database):
    root = base(bootstrap(client, database)); first = ready_policy(client, root)
    second = draft(client, root, version=1)
    assert approve(client, root, second, effective_at=(now()-timedelta(days=1)).isoformat()).status_code == 422
    assert approve(client, root, second, effective_at=(now()+timedelta(days=30)).isoformat()).status_code == 200
    acknowledged = acknowledge(client, root, second).json()
    assert acknowledged['state'] == 'scheduled' and not acknowledged['usable_for_new_milestones']
    assert client.get(root + '/policies/' + first['id']).json()['usable_for_new_milestones']
    third = draft(client, root, version=2)
    assert approve(client, root, third).status_code == 409


def test_every_required_participant_acknowledges_own_version(client, database, settings):
    owner = bootstrap(client, database); root = base(owner)
    invitation = invite(client, owner['workspace']['id'], project_id=owner['project']['id'])
    with other_client(settings, database) as member:
        user = accept(member, invitation['token'])
        item = draft(client, root); assert approve(client, root, item).status_code == 200
        mine = acknowledge(client, root, item).json()
        assert mine['acknowledgements']['missing_user_ids'] == [user['id']]
        assert not mine['usable_for_new_milestones']
        assert approve(member, root, item).status_code == 403
        assert mutation(member, root + '/policies', policy_body(member, root, version=1)).status_code == 403
        assert acknowledge(member, root, item).json()['usable_for_new_milestones']


def test_snapshot_prevents_suspending_an_unacknowledged_participant_to_bypass(client, database, settings):
    owner = bootstrap(client, database); root = base(owner)
    invitation = invite(client, owner['workspace']['id'], project_id=owner['project']['id'])
    with other_client(settings, database) as member:
        user = accept(member, invitation['token'])
    item = draft(client, root); assert approve(client, root, item).status_code == 200
    acknowledge(client, root, item)
    suspended = mutation(client, root + '/members/' + user['id'], {'expected_version': 1,
        'role': 'contributor', 'status': 'suspended', 'reason': 'Synthetic contributor departed'}, method='patch')
    assert suspended.status_code == 200
    result = client.get(root + '/policies/' + item['id']).json()
    assert user['id'] in result['acknowledgements']['missing_user_ids']
    participant = next(p for p in result['acknowledgements']['participants'] if p['user_id'] == user['id'])
    assert participant['required_at_creation'] and not participant['currently_required']
    revised = ready_policy(client, root, version=1)
    assert revised['usable_for_new_milestones']


def test_joining_after_approval_requires_ack_and_before_approval_requires_revision(client, database, settings):
    owner = bootstrap(client, database); root = base(owner)
    first = ready_policy(client, root)
    next_draft = draft(client, root, version=1)
    invitation = invite(client, owner['workspace']['id'], project_id=owner['project']['id'])
    with other_client(settings, database) as member:
        user = accept(member, invitation['token'])
        assert approve(client, root, next_draft).status_code == 409
        old = client.get(root + '/policies/' + first['id']).json()
        assert old['acknowledgements']['missing_user_ids'] == [user['id']]
        assert not old['usable_for_new_milestones']
        assert acknowledge(member, root, first).json()['usable_for_new_milestones']


def test_viewer_is_not_automatically_an_economic_participant(client, database, settings):
    owner = bootstrap(client, database); root = base(owner)
    invitation = invite(client, owner['workspace']['id'], project_id=owner['project']['id'], role='viewer')
    with other_client(settings, database) as viewer:
        user = accept(viewer, invitation['token'])
        item = ready_policy(client, root)
        assert item['usable_for_new_milestones']
        assert user['id'] not in [p['user_id'] for p in item['acknowledgements']['participants']]
        assert viewer.get(root + '/policies/' + item['id']).status_code == 200
        assert acknowledge(viewer, root, item).status_code == 200
        assert len(acknowledge(viewer, root, item).json()['acknowledgements']['participants']) == 1


def test_project_changes_do_not_rewrite_a_pinned_policy(client, database):
    owner = bootstrap(client, database); root = base(owner); item = ready_policy(client, root)
    result = mutation(client, root, {'name': 'Changed project', 'description': '', 'timezone': 'America/Puerto_Rico',
        'currency': 'USD', 'expected_version': 1, 'reason': 'Change display settings prospectively'}, method='patch')
    assert result.status_code == 200
    assert client.get(root + '/policies/' + item['id']).json()['rules']['timezone'] == 'UTC'
    body = policy_body(client, root, version=1); body['rules']['timezone'] = 'UTC'
    assert mutation(client, root + '/policies', body).status_code == 422
    body['rules']['timezone'] = 'America/Puerto_Rico'
    assert mutation(client, root + '/policies', body).status_code == 201


def test_history_rejects_direct_update_and_delete(client, database):
    root = base(bootstrap(client, database)); item = ready_policy(client, root)
    for table in ['policy_versions', 'policy_participants', 'policy_approvals', 'policy_acknowledgements']:
        for command in ['DELETE FROM ' + table, 'UPDATE ' + table + ' SET project_id = project_id']:
            with pytest.raises(DBAPIError), database.engine.begin() as connection:
                connection.execute(text(command))
    assert client.get(root + '/policies/' + item['id']).json()['my_acknowledgement']


def test_gets_and_templates_do_not_create_records(client, database):
    root = base(bootstrap(client, database))
    for _ in range(2):
        assert client.get(root + '/policies/templates').status_code == 200
        assert client.get(root + '/policies').json()['items'] == []
    with database.session() as db:
        assert db.scalar(select(func.count()).select_from(PolicyVersion)) == 0


def test_foreign_project_and_workspace_ids_are_inaccessible(client, database):
    owner = bootstrap(client, database); root = base(owner); item = ready_policy(client, root)
    other_ws = mutation(client, '/api/v1/workspaces', {'name': 'Other private workspace'}).json()
    other_project = mutation(client, f"/api/v1/workspaces/{other_ws['id']}/projects", {'name': 'Other game'}).json()
    other_root = f"/api/v1/workspaces/{other_ws['id']}/projects/{other_project['id']}"
    assert client.get(other_root + '/policies/' + item['id']).status_code == 404
    assert approve(client, other_root, item).status_code == 404
    assert acknowledge(client, other_root, item).status_code == 404
    mixed = f"/api/v1/workspaces/{other_ws['id']}/projects/{owner['project']['id']}"
    assert client.get(mixed + '/policies/templates').status_code == 404
    assert client.get(mixed + '/policies').status_code == 404


def test_contributor_cannot_read_unassigned_project(client, database, settings):
    owner = bootstrap(client, database); root = base(owner); item = ready_policy(client, root)
    invitation = invite(client, owner['workspace']['id'])
    with other_client(settings, database) as member:
        accept(member, invitation['token'])
        for suffix in ['/policies', '/policies/templates', '/policies/' + item['id'], '/milestones']:
            assert member.get(root + suffix).status_code == 404
        assert acknowledge(member, root, item).status_code == 404


def test_unauthenticated_policy_reads_and_csrf_mutations_fail(client, database, settings):
    owner = bootstrap(client, database); root = base(owner)
    body = policy_body(client, root)
    result = client.post(root + '/policies', headers={'Origin': 'http://testserver'}, json=body)
    assert result.status_code == 403
    with other_client(settings, database) as anonymous:
        anonymous.get('/api/v1/auth/session')
        assert anonymous.get(root + '/policies').status_code == 401
