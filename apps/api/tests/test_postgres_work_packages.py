"""Native PostgreSQL races and migration/immutability checks; never use SQLite substitutes."""
from uuid import UUID
import pytest
from sqlalchemy import select, func, text
from sqlalchemy.exc import DBAPIError
from alembic import command
from tests.test_postgres_accounts import pg_accounts, browser
from tests.test_postgres_planning import race_requests
from tests.phase4_helpers import environment, scope, create, advance
from app.contributions.work_packages.models import WorkPackage, WorkSubmission
from app.contributions.budgets.models import Milestone
from app.db.migration import migration_config

pytestmark=pytest.mark.postgres


def native_package(settings,db):
    client=browser(settings,db)
    owner,root,milestone,allocation=environment(client,db)
    response=create(client,root,owner,milestone,allocation)
    assert response.status_code==201,response.text
    return client,owner,root,milestone,allocation,response.json()


def test_native_one_allocation_cannot_bind_twice(pg_accounts):
    settings,db=pg_accounts;client=browser(settings,db)
    try:
        owner,root,milestone,allocation=environment(client,db)
        body={'milestone_id':milestone['id'],'allocation_id':allocation['id'],'expected_allocation_version':allocation['version'],
              'scope':scope(owner['user']['id']),'reason':'Create the same synthetic binding once'}
        request=(root+'/work-packages',body)
        assert sorted(race_requests(settings,db,client,[request,request]))==[201,409]
        with db.session() as session:assert session.scalar(select(func.count()).select_from(WorkPackage))==1
    finally:client.close()


def test_native_concurrent_scope_edits_reject_stale_revision(pg_accounts):
    settings,db=pg_accounts;client,owner,root,_,_,item=native_package(settings,db)
    try:
        request=(root+f"/work-packages/{item['id']}/revisions",{'expected_version':item['version'],
            'reviewed_hash':item['review_hash'],'scope':scope(owner['user']['id']),'reason':'Record a synthetic concurrent scope amendment'})
        assert sorted(race_requests(settings,db,client,[request,request]))==[200,409]
        assert client.get(root+f"/work-packages/{item['id']}").json()['scope_revision']==2
    finally:client.close()


def test_native_repeated_submission_creates_one_snapshot(pg_accounts):
    settings,db=pg_accounts;client,_,root,_,_,item=native_package(settings,db)
    try:
        item=advance(client,root,item,'approve_scope','start')
        request=(root+f"/work-packages/{item['id']}/actions",{'action':'submit','expected_version':item['version'],
            'reviewed_hash':item['review_hash'],'reviewed':True,'reason':'Submit this exact scope revision once'})
        assert sorted(race_requests(settings,db,client,[request,request]))==[200,409]
        with db.session() as session:assert session.scalar(select(func.count()).select_from(WorkSubmission))==1
    finally:client.close()


def test_native_cancel_race_releases_budget_once(pg_accounts):
    settings,db=pg_accounts;client,_,root,milestone,_,item=native_package(settings,db)
    try:
        request=(root+f"/work-packages/{item['id']}/actions",{'action':'cancel','expected_version':item['version'],
            'reviewed_hash':item['review_hash'],'reviewed':True,'reason':'Cancel this exact unaccepted synthetic scope once'})
        assert sorted(race_requests(settings,db,client,[request,request]))==[200,409]
        with db.session() as session:
            m=session.get(Milestone,UUID(milestone['id']))
            assert m.allocated_atoms==0 and m.issued_atoms==0 and m.reserve_floor_atoms==100_000
    finally:client.close()


def test_native_work_history_guards_and_phase3_upgrade(pg_accounts):
    settings,db=pg_accounts;client=browser(settings,db)
    try:
        # Keep actual policy and budget data, remove only empty phase-4 tables.
        owner,root,milestone,allocation=environment(client,db)
        cfg=migration_config()
        with db.engine.begin() as conn:
            cfg.attributes['connection']=conn;command.downgrade(cfg,'0003_policies_budgets');command.upgrade(cfg,'head')
        response=create(client,root,owner,milestone,allocation);assert response.status_code==201,response.text
        item=advance(client,root,response.json(),'approve_scope','start','submit')
        for table in ['work_packages','work_package_revisions','work_package_participants','work_package_events','work_submissions']:
            with pytest.raises(DBAPIError),db.engine.begin() as conn:conn.execute(text(f'DELETE FROM {table}'))
        with pytest.raises(DBAPIError),db.engine.begin() as conn:conn.execute(text("UPDATE work_packages SET policy_id=gen_random_uuid()"))
        with pytest.raises(RuntimeError,match='Phase-5 records exist'),db.engine.begin() as conn:
            cfg.attributes['connection']=conn;command.downgrade(cfg,'0003_policies_budgets')
    finally:client.close()
