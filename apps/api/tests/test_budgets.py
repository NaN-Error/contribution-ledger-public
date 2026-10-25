from uuid import UUID, uuid4
import pytest
from sqlalchemy import select, func, text
from sqlalchemy.exc import DBAPIError
from tests.auth_helpers import bootstrap, mutation, invite, accept, other_client
from tests.phase3_helpers import (base, draft, approve, acknowledge, ready_policy, milestone,
    active_milestone, decision, proposal, allocate)
from app.contributions.budgets.models import Milestone, BudgetAllocation, BudgetAmendment, BudgetDecision
from app.projects.models import AuditEvent


def test_initial_budget_is_only_a_proposal_until_approved(client, database):
    root = base(bootstrap(client, database)); policy = ready_policy(client, root)
    item = milestone(client, root, policy)
    assert item['status'] == 'draft' and item['total_atoms'] == item['issued_atoms'] == 0
    assert item['amendments'][0]['preview']['after_totals']['total_atoms'] == 1_000_000
    approved = decision(client, root, item, item['amendments'][0])
    assert approved.status_code == 200, approved.text
    result = approved.json()
    assert result['version'] == 2 and result['status'] == 'active'
    assert result['total_atoms'] == 1_000_000 and result['reserve_floor_atoms'] == 100_000
    assert result['available_atoms'] == 900_000 and result['unassigned_atoms'] == 1_000_000
    assert result['issued_atoms'] == 0
    assert decision(client, root, result, item['amendments'][0]).status_code == 409
    with database.session() as db: assert db.scalar(select(func.count()).select_from(BudgetDecision)) == 1


def test_unapproved_unacknowledged_and_historical_rules_cannot_create_budget(client, database):
    root = base(bootstrap(client, database)); policy = draft(client, root)
    body = {'name': 'New milestone', 'policy_id': policy['id'], 'total_atoms': 1000,
            'reserve_floor_atoms': 0, 'reason': 'Synthetic initial budget'}
    assert mutation(client, root + '/milestones', body).status_code == 409
    assert approve(client, root, policy).status_code == 200
    assert mutation(client, root + '/milestones', body).status_code == 409
    acknowledge(client, root, policy)
    assert mutation(client, root + '/milestones', body).status_code == 201
    successor = ready_policy(client, root, version=1)
    assert successor['usable_for_new_milestones']
    assert mutation(client, root + '/milestones', body).status_code == 409


def test_overspending_and_reserve_crossing_rejected_without_any_awards(client, database):
    root = base(bootstrap(client, database)); policy = ready_policy(client, root)
    item = active_milestone(client, root, policy)
    item = allocate(client, root, item, 700_000)
    bad = proposal(client, root, item, {'kind': 'allocate', 'title': 'Too much work', 'category': 'code',
                                      'pool_key': 'release', 'atoms': 200_001})
    assert bad.status_code == 409 and bad.json()['error']['code'] == 'budget_exceeded'
    good = allocate(client, root, item, 200_000, title='QA work')
    assert good['available_atoms'] == 0 and good['allocated_atoms'] == 900_000
    assert good['unassigned_atoms'] == 100_000 and good['issued_atoms'] == 0
    assert len(good['allocations']) == 2
    assert all('user_id' not in row for row in good['allocations'])


def test_preview_is_read_only_and_persists_reviewed_dilution(client, database):
    root = base(bootstrap(client, database)); policy = ready_policy(client, root)
    item = allocate(client, root, active_milestone(client, root, policy), 200_000)
    with database.session() as db:
        count = db.scalar(select(func.count()).select_from(BudgetAmendment))
        audits = db.scalar(select(func.count()).select_from(AuditEvent))
    change = {'kind': 'set_budget', 'total_atoms': 2_000_000, 'reserve_floor_atoms': 200_000}
    body = {'expected_version': item['version'], 'change': change, 'reason': 'Preview increased capacity'}
    preview = mutation(client, root + f"/milestones/{item['id']}/preview", body)
    assert preview.status_code == 200, preview.text
    assert preview.json()['preview']['planned_budget_shares'][0]['after']['denominator_atoms'] == 2_000_000
    with database.session() as db:
        assert db.scalar(select(func.count()).select_from(BudgetAmendment)) == count
        assert db.scalar(select(func.count()).select_from(AuditEvent)) == audits
    proposed = proposal(client, root, item, change).json()
    assert proposed['preview_hash'] == preview.json()['preview_hash']
    assert decision(client, root, item, proposed, reviewed_hash='0'*64).status_code == 409
    accepted = decision(client, root, item, proposed); assert accepted.status_code == 200
    assert accepted.json()['total_atoms'] == 2_000_000
    assert accepted.json()['allocated_atoms'] == 200_000


def test_two_valid_proposals_cannot_both_spend_the_same_snapshot(client, database):
    root = base(bootstrap(client, database)); policy = ready_policy(client, root)
    item = active_milestone(client, root, policy)
    change = {'kind': 'allocate', 'title': 'Large planned work', 'category': 'art', 'pool_key': 'release', 'atoms': 800_000}
    a = proposal(client, root, item, change).json()
    b = proposal(client, root, item, {**change, 'title': 'Competing large work'}).json()
    accepted = decision(client, root, item, a); assert accepted.status_code == 200
    latest = accepted.json()
    assert decision(client, root, item, b).status_code == 409
    assert decision(client, root, latest, b).status_code == 409
    assert next(p for p in latest['amendments'] if p['id'] == b['id'])['state'] == 'stale'
    rejected = decision(client, root, latest, b, choice='reject')
    assert rejected.status_code == 200 and rejected.json()['allocated_atoms'] == 800_000


def test_resize_cancel_and_rejection_have_exact_effects(client, database):
    root = base(bootstrap(client, database)); policy = ready_policy(client, root)
    item = allocate(client, root, active_milestone(client, root, policy), 200_000)
    allocation_id = item['allocations'][0]['id']
    grow = proposal(client, root, item, {'kind': 'resize_allocation', 'allocation_id': allocation_id, 'atoms': 500_000}).json()
    rejected = decision(client, root, item, grow, choice='reject').json()
    assert rejected['version'] == item['version'] and rejected['allocated_atoms'] == 200_000
    grow = proposal(client, root, item, {'kind': 'resize_allocation', 'allocation_id': allocation_id, 'atoms': 500_000}).json()
    result = decision(client, root, item, grow); assert result.status_code == 200, result.text
    item = result.json(); assert item['allocated_atoms'] == 500_000
    cancel = proposal(client, root, item, {'kind': 'cancel_allocation', 'allocation_id': allocation_id}).json()
    result = decision(client, root, item, cancel); assert result.status_code == 200, result.text
    item = result.json()
    assert item['allocated_atoms'] == 0 and item['available_atoms'] == 900_000
    assert item['allocations'][0]['status'] == 'cancelled'
    assert proposal(client, root, item, {'kind': 'resize_allocation', 'allocation_id': allocation_id, 'atoms': 1}).status_code == 409


def test_issued_unit_guard_has_no_public_mutation_path(client, database):
    root = base(bootstrap(client, database)); policy = ready_policy(client, root)
    item = allocate(client, root, active_milestone(client, root, policy), 200_000)
    # Synthetic future-ledger state, installed through the test fixture only.
    with database.session() as db:
        db.get(Milestone, UUID(item['id'])).issued_atoms = 150_000
        db.get(BudgetAllocation, UUID(item['allocations'][0]['id'])).issued_atoms = 150_000
        db.commit()
    for change in [{'kind': 'set_budget', 'total_atoms': 100_000, 'reserve_floor_atoms': 0},
        {'kind': 'resize_allocation', 'allocation_id': item['allocations'][0]['id'], 'atoms': 149_999},
        {'kind': 'cancel_allocation', 'allocation_id': item['allocations'][0]['id']}]:
        assert proposal(client, root, item, change).status_code == 409
    assert client.patch(root + f"/milestones/{item['id']}", json={'issued_atoms': 9999}).status_code in [403, 405]


def test_category_and_pool_checked_against_pinned_policy(client, database):
    root = base(bootstrap(client, database)); policy = ready_policy(client, root)
    item = active_milestone(client, root, policy)
    wrong_pool = proposal(client, root, item, {'kind': 'allocate', 'title': 'Not eligible here', 'category': 'code', 'pool_key': 'ongoing', 'atoms': 1000})
    assert wrong_pool.status_code == 409


def test_history_cannot_be_rewritten_and_scope_constraints_enforced(client, database):
    root = base(bootstrap(client, database)); policy = ready_policy(client, root)
    item = active_milestone(client, root, policy)
    for table in ['budget_amendments', 'budget_decisions']:
        for statement in ['DELETE FROM ' + table, 'UPDATE ' + table + ' SET project_id = project_id']:
            with pytest.raises(DBAPIError), database.engine.begin() as connection: connection.execute(text(statement))
    with pytest.raises(DBAPIError), database.engine.begin() as connection:
        connection.execute(text('UPDATE milestones SET total_atoms = -1'))
    with pytest.raises(DBAPIError), database.engine.begin() as connection:
        connection.execute(text('UPDATE milestones SET allocated_atoms = total_atoms + 1'))
    with pytest.raises(DBAPIError), database.engine.begin() as connection:
        connection.execute(text('UPDATE milestones SET policy_id = :id'), {'id': uuid4().hex})
    assert client.get(root + f"/milestones/{item['id']}").json()['total_atoms'] == 1_000_000


def test_policy_versions_never_reassign_existing_milestones(client, database):
    root = base(bootstrap(client, database)); policy = ready_policy(client, root)
    item = active_milestone(client, root, policy)
    new = ready_policy(client, root, version=1, key=1)
    latest = allocate(client, root, item)
    assert latest['policy_id'] == policy['id']
    assert latest['policy']['rules']['pools'] == policy['rules']['pools']
    assert latest['policy_id'] != new['id']


def test_foreign_allocation_milestone_and_proposal_ids_fail(client, database):
    owner = bootstrap(client, database); root = base(owner); policy = ready_policy(client, root)
    first = allocate(client, root, active_milestone(client, root, policy))
    second = active_milestone(client, root, policy)
    foreign_allocation = first['allocations'][0]['id']
    assert proposal(client, root, second, {'kind': 'resize_allocation', 'allocation_id': foreign_allocation, 'atoms': 1}).status_code == 404
    foreign_proposal = first['amendments'][0]
    assert decision(client, root, second, foreign_proposal).status_code == 404
    other = mutation(client, f"/api/v1/workspaces/{owner['workspace']['id']}/projects", {'name': 'Second game'}).json()
    other_root = f"/api/v1/workspaces/{owner['workspace']['id']}/projects/{other['id']}"
    assert client.get(other_root + f"/milestones/{first['id']}").status_code == 404
    assert proposal(client, other_root, first, {'kind': 'set_budget', 'total_atoms': 999, 'reserve_floor_atoms': 0}).status_code == 404


def test_readonly_role_can_inspect_but_cannot_change_budgets(client, database, settings):
    owner = bootstrap(client, database); root = base(owner)
    invitation = invite(client, owner['workspace']['id'], project_id=owner['project']['id'], role='viewer')
    with other_client(settings, database) as viewer:
        accept(viewer, invitation['token']); policy = ready_policy(client, root)
        item = milestone(client, root, policy)
        assert viewer.get(root + f"/milestones/{item['id']}").status_code == 200
        assert viewer.get(root + '/milestones').status_code == 200
        assert decision(viewer, root, item, item['amendments'][0]).status_code == 403
        assert proposal(viewer, root, item, {'kind': 'initial_budget', 'total_atoms': 1, 'reserve_floor_atoms': 0}).status_code == 403
        body = {'name': 'Unauthorized budget', 'policy_id': policy['id'], 'total_atoms': 1000,
            'reserve_floor_atoms': 0, 'reason': 'Viewer cannot do this'}
        assert mutation(viewer, root + '/milestones', body).status_code == 403


def test_preapproval_membership_change_blocks_pending_budget(client, database, settings):
    owner = bootstrap(client, database); root = base(owner); policy = ready_policy(client, root)
    item = milestone(client, root, policy)
    invitation = invite(client, owner['workspace']['id'], project_id=owner['project']['id'])
    with other_client(settings, database) as member:
        accept(member, invitation['token'])
        assert decision(client, root, item, item['amendments'][0]).status_code == 409
        assert acknowledge(member, root, policy).status_code == 200
        assert decision(client, root, item, item['amendments'][0]).status_code == 200


def test_invalid_initial_budget_rolls_back_shell_and_audit(client, database):
    root = base(bootstrap(client, database)); policy = ready_policy(client, root)
    with database.session() as db: audits = db.scalar(select(func.count()).select_from(AuditEvent))
    result = mutation(client, root + '/milestones', {'name': 'Invalid budget', 'policy_id': policy['id'],
        'total_atoms': 1000, 'reserve_floor_atoms': 1001, 'reason': 'Synthetic invalid reserve'})
    assert result.status_code == 409
    assert client.get(root + '/milestones').json()['items'] == []
    with database.session() as db: assert db.scalar(select(func.count()).select_from(AuditEvent)) == audits


def test_proposal_history_has_explicit_stable_pages(client, database):
    root = base(bootstrap(client, database)); policy = ready_policy(client, root)
    item = active_milestone(client, root, policy)
    for n in range(23):
        result = proposal(client, root, item, {'kind': 'allocate', 'title': f'Historical proposal {n}',
            'category': 'code', 'pool_key': 'release', 'atoms': 1})
        assert result.status_code == 201
    first = client.get(root + f"/milestones/{item['id']}").json()
    assert len(first['amendments']) == 20 and first['next_history_offset'] == 20
    second = client.get(root + f"/milestones/{item['id']}?history_offset=20").json()
    assert len(second['amendments']) == 4 and second['next_history_offset'] is None
    assert {r['id'] for r in first['amendments']}.isdisjoint({r['id'] for r in second['amendments']})
    assert client.get(root + f"/milestones/{item['id']}?history_offset=-1").status_code == 422


def test_downgrade_refuses_to_erase_policy_history(client, database):
    from alembic import command
    from app.db.migration import migration_config, expected_revision
    root = base(bootstrap(client, database)); policy = draft(client, root)
    config = migration_config()
    with pytest.raises(RuntimeError, match='Refusing destructive downgrade'):
        with database.engine.begin() as connection:
            config.attributes['connection'] = connection
            command.downgrade(config, '0002_accounts_access')
    with database.engine.connect() as connection:
        assert connection.execute(text('SELECT version_num FROM alembic_version')).scalar() == expected_revision()
    assert client.get(root + '/policies/' + policy['id']).status_code == 200
    with pytest.raises(DBAPIError):
        with database.engine.begin() as connection:
            connection.execute(text("UPDATE policy_versions SET title='Do not erase history'"))


def test_empty_phase3_schema_can_downgrade_and_upgrade_without_erasing_accounts(client, database):
    from alembic import command
    from app.db.migration import migration_config, expected_revision
    root = base(bootstrap(client, database))
    config = migration_config()
    with database.engine.begin() as connection:
        config.attributes['connection'] = connection
        command.downgrade(config, '0002_accounts_access')
        command.upgrade(config, 'head')
        command.upgrade(config, 'head')
        assert connection.execute(text('SELECT version_num FROM alembic_version')).scalar() == expected_revision()
    assert client.get(root + '/policies').json()['items'] == []
