"""Native PostgreSQL migration, append-only history and real multi-connection races.

These tests are skipped, never substituted with SQLite, without an explicitly
configured disposable *_test database. The imported fixture owns a fresh schema.
"""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import UUID
import pytest
from alembic import command
from sqlalchemy import select, func, text
from sqlalchemy.exc import DBAPIError
from tests.test_postgres_accounts import pg_accounts, browser
from tests.auth_helpers import bootstrap, mutation
from tests.phase3_helpers import base, ready_policy, draft, approve, active_milestone, proposal, allocate
from app.db.migration import migration_config, expected_revision
from app.contributions.budgets.models import Milestone, BudgetAllocation, BudgetDecision
from app.policies.models import PolicyVersion, PolicyAcknowledgement

pytestmark = pytest.mark.postgres


def race_requests(settings, db, owner_client, path_and_bodies):
    barrier = Barrier(len(path_and_bodies))
    def attempt(item):
        path, body = item
        client = browser(settings, db)
        client.cookies.update(owner_client.cookies)
        try:
            state = client.get('/api/v1/auth/session').json()
            barrier.wait(timeout=10)
            return client.post(path, json=body, headers={'Origin': 'http://testserver',
                'X-CSRF-Token': state['csrf_token']}).status_code
        finally:
            client.close()
    with ThreadPoolExecutor(max_workers=len(path_and_bodies)) as pool:
        return list(pool.map(attempt, path_and_bodies))


def test_native_upgrade_preserves_existing_phase2_accounts(pg_accounts):
    settings, db = pg_accounts
    config = migration_config()
    client = browser(settings, db)
    try:
        owner = bootstrap(client, db)
        # Populate accounts through the current API, then retain their phase-2
        # representation. Never run current ORM/session code against old columns.
        # Later-phase business tables are empty, so their guarded downgrade is safe.
        with db.engine.begin() as connection:
            config.attributes['connection'] = connection
            command.downgrade(config, '0002_accounts_access')
            assert connection.execute(text('SELECT count(*) FROM users')).scalar_one() == 1
            assert connection.execute(text('SELECT count(*) FROM projects')).scalar_one() == 1
            assert connection.execute(text('SELECT count(*) FROM browser_sessions WHERE user_id IS NOT NULL')).scalar_one() == 1
            command.upgrade(config, 'head')
            command.upgrade(config, 'head')
            assert connection.execute(text('SELECT version_num FROM alembic_version')).scalar_one() == expected_revision()
        assert client.get(base(owner)).json()['name'] == owner['project']['name']
        policy = ready_policy(client, base(owner))
        assert active_milestone(client, base(owner), policy)['total_atoms'] == 1_000_000
    finally:
        client.close()


def test_native_planning_history_and_database_bounds(pg_accounts):
    settings, db = pg_accounts
    client = browser(settings, db)
    try:
        owner = bootstrap(client, db); root = base(owner)
        policy = ready_policy(client, root)
        item = allocate(client, root, active_milestone(client, root, policy))
        for table in ['policy_versions', 'policy_participants', 'policy_approvals',
                      'policy_acknowledgements', 'budget_amendments', 'budget_decisions']:
            for statement in [f'UPDATE {table} SET project_id = project_id', f'DELETE FROM {table}']:
                with pytest.raises(DBAPIError), db.engine.begin() as connection:
                    connection.execute(text(statement))
        with pytest.raises(DBAPIError), db.engine.begin() as connection:
            connection.execute(text('UPDATE milestones SET allocated_atoms = total_atoms + 1'))
        with db.session() as session:
            assert session.get(Milestone, UUID(item['id'])).issued_atoms == 0
    finally:
        client.close()


def test_native_competing_allocations_cannot_overspend(pg_accounts):
    settings, db = pg_accounts
    client = browser(settings, db)
    try:
        owner = bootstrap(client, db); root = base(owner); policy = ready_policy(client, root)
        item = active_milestone(client, root, policy)
        change = {'kind': 'allocate', 'title': 'Concurrent planned work', 'category': 'art', 'pool_key': 'release', 'atoms': 800_000}
        first = proposal(client, root, item, change).json()
        second = proposal(client, root, item, {**change, 'title': 'Competing planned work'}).json()
        requests = [(root + f"/milestones/{item['id']}/amendments/{p['id']}/decision", {
            'decision': 'approve', 'expected_version': item['version'], 'reviewed_preview_hash': p['preview_hash'],
            'reason': 'Approve this exact reviewed planning proposal'}) for p in [first, second]]
        assert sorted(race_requests(settings, db, client, requests)) == [200, 409]
        with db.session() as session:
            saved = session.get(Milestone, UUID(item['id']))
            assert saved.allocated_atoms == 800_000 and saved.reserve_floor_atoms == 100_000
            assert saved.issued_atoms == 0 and saved.version == 3
            assert session.scalar(select(func.count()).select_from(BudgetAllocation)) == 1
    finally:
        client.close()


def test_native_repeated_decision_has_one_effect(pg_accounts):
    settings, db = pg_accounts
    client = browser(settings, db)
    try:
        owner = bootstrap(client, db); root = base(owner); policy = ready_policy(client, root)
        item = active_milestone(client, root, policy)
        proposed = proposal(client, root, item, {'kind': 'allocate', 'title': 'Once-only planned work',
            'category': 'qa', 'pool_key': 'release', 'atoms': 1000}).json()
        request = (root + f"/milestones/{item['id']}/amendments/{proposed['id']}/decision", {
            'decision': 'approve', 'expected_version': item['version'], 'reviewed_preview_hash': proposed['preview_hash'],
            'reason': 'Accept this planning proposal once'})
        assert sorted(race_requests(settings, db, client, [request, request])) == [200, 409]
        with db.session() as session:
            assert session.scalar(select(func.count()).select_from(BudgetAllocation)) == 1
            assert session.scalar(select(func.count()).select_from(BudgetDecision).where(
                BudgetDecision.amendment_id == UUID(proposed['id']))) == 1
    finally:
        client.close()


def test_native_policy_revisions_serialize_and_acks_do_not_duplicate(pg_accounts):
    settings, db = pg_accounts
    client = browser(settings, db)
    try:
        owner = bootstrap(client, db); root = base(owner)
        from tests.phase3_helpers import policy_body
        body = policy_body(client, root)
        assert sorted(race_requests(settings, db, client, [(root + '/policies', body), (root + '/policies', body)])) == [201, 409]
        policy = client.get(root + '/policies').json()['items'][0]
        assert approve(client, root, policy).status_code == 200
        request = (root + f"/policies/{policy['id']}/acknowledge", {'reviewed_content_hash': policy['content_hash'], 'reviewed': True})
        assert sorted(race_requests(settings, db, client, [request, request])) == [200, 200]
        with db.session() as session:
            assert session.scalar(select(func.count()).select_from(PolicyVersion)) == 1
            assert session.scalar(select(func.count()).select_from(PolicyAcknowledgement)) == 1
    finally:
        client.close()
