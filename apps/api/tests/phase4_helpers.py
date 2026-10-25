from copy import deepcopy
from tests.auth_helpers import bootstrap, mutation
from tests.phase3_helpers import base, ready_policy, active_milestone, allocate
from app.contributions.work_packages.calculation import input_from_snapshot


def environment(client, database, atoms=100_000):
    client._transport.raise_server_exceptions = True
    owner = bootstrap(client, database)
    root = base(owner)
    policy = ready_policy(client, root)
    milestone = active_milestone(client, root, policy)
    milestone = allocate(client, root, milestone, atoms=atoms)
    return owner, root, milestone, milestone['allocations'][0]


def scope(user_id, budget=100_000):
    return {'title': 'Recover a disconnected game session', 'outcome': 'Players can safely reconnect to their existing match.',
        'acceptance_criteria': ['Temporary disconnections do not lose the match state.'],
        'evidence_requirements': 'Provide a documented test report covering connection failures.',
        'coordinator_id': user_id, 'intended_contributor_ids': [user_id],
        'deliverables': [{'title': 'Reconnection behavior', 'outcome': 'Reconnect after a temporary network outage.',
            'acceptance_criteria': ['A reconnect restores the original player session.'],
            'evidence_requirements': 'Provide reproducible integration tests and their results.',
            'budget_atoms': budget, 'attribution': {'mode': 'units', 'entries': [
                {'user_id': user_id, 'role': 'implementation', 'atoms': budget}]}}]}


def create(client, root, owner, milestone, allocation, custom=None):
    body = {'milestone_id': milestone['id'], 'allocation_id': allocation['id'],
        'expected_allocation_version': allocation['version'], 'scope': custom or scope(owner['user']['id'], allocation['atoms']),
        'reason': 'Define an explicitly budgeted synthetic work package'}
    return mutation(client, root + '/work-packages', body)


def action(client, root, item, action_name, **extra):
    return mutation(client, root + f"/work-packages/{item['id']}/actions", {
        'action': action_name, 'expected_version': item['version'], 'reviewed_hash': item['review_hash'],
        'reviewed': True, 'reason': 'Review this synthetic work-package command', **extra})


def advance(client, root, item, *actions):
    for name in actions:
        response = action(client, root, item, name)
        assert response.status_code == 200, response.text
        item = response.json()
    return item


def edit(client, root, item, new_scope=None, **extra):
    body = {'expected_version': item['version'], 'reviewed_hash': item['review_hash'],
        'scope': new_scope or input_from_snapshot(item['revision']['document']).model_dump(mode='json'),
        'reason': 'Amend the reviewed scope without erasing its history', **extra}
    return mutation(client, root + f"/work-packages/{item['id']}/revisions", body)
