"""Native row locking, immutable reports and populated additive upgrades."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4
import pytest
from alembic import command
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from fastapi.testclient import TestClient
from app.main import create_app
from app.db.migration import migration_config
from tests.test_postgres_accounts import pg_accounts
from tests.test_repository_analysis import PublicFixture, start, finish, post, change, dash, DATES
from tests.auth_helpers import bootstrap, mutation

pytestmark=pytest.mark.postgres


def handoff_environment(pg_accounts):
    from tests.test_analysis_handoff import environment as setup
    settings,db=pg_accounts
    client=TestClient(create_app(settings,db),raise_server_exceptions=True)
    return setup(client,db,settings)


def close_handoff_environment(e):
    for actor in e['actors'].values(): actor['client'].close()
    e['client'].close()


def test_native_dashboard_handoff_runs_ordinary_independent_credit_path(pg_accounts):
    from tests.test_analysis_handoff import test_captured_outcome_pins_evidence_and_only_independent_review_issues_credit as check
    e=handoff_environment(pg_accounts)
    try: check(e)
    finally: close_handoff_environment(e)


def test_native_handoff_claims_and_manual_date_history_are_immutable(pg_accounts):
    from tests.test_analysis_handoff import test_manual_date_evidence_and_history_are_frozen_after_draft_correction as check
    e=handoff_environment(pg_accounts)
    try: check(e)
    finally: close_handoff_environment(e)


def test_native_competing_handoffs_create_one_package_and_no_credit(pg_accounts):
    from tests.test_analysis_handoff import prepare
    e=handoff_environment(pg_accounts);body,_=prepare(e)
    barrier=Barrier(2);csrf=e['client'].get('/api/v1/auth/session').json()['csrf_token']
    def attempt(_):
        peer=TestClient(create_app(e['settings'],e['database']),raise_server_exceptions=True)
        peer.cookies.update(e['client'].cookies)
        try:
            barrier.wait(timeout=10)
            r=peer.post(e['analysis']['root']+'/handoff',json=body,headers={'Origin':'http://testserver','X-CSRF-Token':csrf})
            assert r.status_code==201,r.text
            return r.json()
        finally: peer.close()
    try:
        with ThreadPoolExecutor(max_workers=2) as pool: rows=list(pool.map(attempt,[0,1]))
        assert rows[0]['package_id']==rows[1]['package_id']
        assert sorted(r['replayed'] for r in rows)==[False,True]
        with e['database'].engine.connect() as c:
            assert c.execute(text('SELECT count(*) FROM analysis_handoffs')).scalar_one()==1
            assert c.execute(text('SELECT count(*) FROM credit_awards')).scalar_one()==0
    finally: close_handoff_environment(e)


def test_native_populated_0016_upgrade_retains_reports_and_refuses_handoff_downgrade(pg_accounts):
    from tests.test_analysis_handoff import prepare,create
    e=handoff_environment(pg_accounts);db=e['database'];config=migration_config()
    try:
        before=dash(e['analysis']);body,_=prepare(e)
        before=dash(e['analysis'])
        with db.engine.begin() as c:
            users=c.execute(text('SELECT count(*) FROM users')).scalar_one()
            config.attributes['connection']=c;command.downgrade(config,'0016_analysis_sharing')
            command.upgrade(config,'head');command.upgrade(config,'head')
            assert c.execute(text('SELECT count(*) FROM users')).scalar_one()==users
        after=dash(e['analysis'])
        # Ordinary recognized reports include a fresh generation timestamp.
        # Compare preserved source/draft data and actual recognized groups.
        assert {k:v for k,v in after.items() if k!='recognized'}=={k:v for k,v in before.items() if k!='recognized'}
        assert after['recognized']['groups']==before['recognized']['groups']
        create(e,body)
        for table in ('analysis_handoffs','analysis_source_claims'):
            for sql in (f'DELETE FROM {table}',f'TRUNCATE {table}'):
                with pytest.raises(DBAPIError),db.engine.begin() as c:c.execute(text(sql))
        with pytest.raises(DBAPIError),db.engine.begin() as c:
            c.execute(text("UPDATE analysis_handoffs SET document='{}'"))
        with pytest.raises(RuntimeError),db.engine.begin() as c:
            config.attributes['connection']=c;command.downgrade(config,'0016_analysis_sharing')
        assert len(e['client'].get(e['base']).json()['candidates'])==1
    finally: close_handoff_environment(e)


def environment(pg_accounts):
    settings,db=pg_accounts;fixture=PublicFixture();client=TestClient(create_app(settings,db,public_repository_client=fixture),raise_server_exceptions=True)
    owner=bootstrap(client,db);p=owner['project'];w=owner['workspace']
    return {'client':client,'database':db,'fixture':fixture,'root':f"/api/v1/workspaces/{w['id']}/projects/{p['id']}/analysis",'owner':owner,'settings':settings}


def test_native_upgrade_preserves_populated_0014_and_adds_guarded_reports(pg_accounts):
    e=environment(pg_accounts);db=e['database'];config=migration_config()
    try:
        # Empty new analysis tables alone can be removed; populated pre-existing accounts stay intact.
        with db.engine.begin() as c:
            config.attributes['connection']=c;command.downgrade(config,'0014_security_recovery')
            count=c.execute(text('SELECT count(*) FROM users')).scalar_one()
            assert count==1
            command.upgrade(config,'head');command.upgrade(config,'head')
            assert c.execute(text('SELECT count(*) FROM users')).scalar_one()==count
        r=finish(e,start(e));post(e,'/scenario',change(e,amount_cents=100003))
        for sql in ["UPDATE repository_analyses SET report='{}'",'TRUNCATE repository_analyses',
                    'DELETE FROM analysis_draft_revisions',"UPDATE analysis_draft_revisions SET document='{}'"]:
            with pytest.raises(DBAPIError),db.engine.begin() as c:c.execute(text(sql))
        assert e['client'].get(e['root']+'/runs/'+r['id']).json()['report']==r['report']
        with pytest.raises(RuntimeError),db.engine.begin() as c:
            config.attributes['connection']=c;command.downgrade(config,'0014_security_recovery')
        assert dash(e)['scenario']['amount_cents']==100003
    finally:e['client'].close()


def test_native_duplicate_run_and_draft_requests_have_one_effect(pg_accounts):
    e=environment(pg_accounts);body={'request_id':str(uuid4()),'repository_urls':['https://github.com/team/game'],**DATES,'public_read_confirmed':True}
    barrier=Barrier(2);csrf=e['client'].get('/api/v1/auth/session').json()['csrf_token']
    def attempt(_):
        peer=TestClient(create_app(e['settings'],e['database']),raise_server_exceptions=True);peer.cookies.update(e['client'].cookies)
        try:
            barrier.wait(timeout=10)
            r=peer.post(e['root']+'/runs',json=body,headers={'Origin':'http://testserver','X-CSRF-Token':csrf})
            assert r.status_code==201,r.text;return r.json()
        finally:peer.close()
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:rows=list(pool.map(attempt,[0,1]))
        assert rows[0]['id']==rows[1]['id'];finish(e,rows[0])
        b=change(e,amount_cents=99999);post(e,'/scenario',b);post(e,'/scenario',b)
        with e['database'].engine.connect() as c:
            assert c.execute(text('SELECT count(*) FROM repository_analyses')).scalar_one()==1
            assert c.execute(text('SELECT count(*) FROM analysis_draft_revisions')).scalar_one()==1
            assert c.execute(text('SELECT count(*) FROM credit_awards')).scalar_one()==0
    finally:e['client'].close()


def test_native_manual_history_and_exclusion_reconcile_saved_scenario(pg_accounts):
    from tests import test_repository_analysis as cases
    e=environment(pg_accounts)
    try:cases.test_manual_correction_exclusion_restore_and_history_preserve_exact_scenario(e)
    finally:e['client'].close()


def test_native_reviewed_sharing_history_and_populated_0015_upgrade(pg_accounts):
    from tests import test_analysis_sharing as cases
    e=environment(pg_accounts);db=e['database'];config=migration_config()
    try:
        row=finish(e,start(e));post(e,'/scenario',change(e,amount_cents=100003))
        with db.engine.begin() as c:
            config.attributes['connection']=c;command.downgrade(config,'0015_repository_analysis')
            original=c.execute(text('SELECT report::text FROM repository_analyses')).scalar_one()
            command.upgrade(config,'head');command.upgrade(config,'head')
            assert c.execute(text('SELECT report::text FROM repository_analyses')).scalar_one()==original
        cases.test_revocation_and_current_membership_preserve_history_and_scope(e)
        for table in ('analysis_publications','analysis_publication_revocations'):
            with pytest.raises(DBAPIError),db.engine.begin() as c:c.execute(text('TRUNCATE '+table))
        with pytest.raises(RuntimeError),db.engine.begin() as c:
            config.attributes['connection']=c;command.downgrade(config,'0015_repository_analysis')
        assert dash(e)['scenario']['amount_cents']==100003
    finally:e['client'].close()


def test_native_competing_share_requests_have_one_reviewed_snapshot(pg_accounts):
    from tests.test_analysis_sharing import sharing_command
    e=environment(pg_accounts);row=finish(e,start(e));body,_=sharing_command(e,row['id'])
    barrier=Barrier(2);csrf=e['client'].get('/api/v1/auth/session').json()['csrf_token']
    def attempt(_):
        peer=TestClient(create_app(e['settings'],e['database']),raise_server_exceptions=True);peer.cookies.update(e['client'].cookies)
        try:
            barrier.wait(timeout=10)
            r=peer.post(e['root']+'/sharing',json=body,headers={'Origin':'http://testserver','X-CSRF-Token':csrf})
            assert r.status_code==201,r.text;return r.json()
        finally:peer.close()
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(attempt,[0,1]))
        assert results[0]['publication_id']==results[1]['publication_id']
        assert sorted(r['replayed'] for r in results)==[False,True]
        with e['database'].engine.connect() as c:
            assert c.execute(text('SELECT count(*) FROM analysis_publications')).scalar_one()==1
            assert c.execute(text('SELECT count(*) FROM credit_awards')).scalar_one()==0
    finally:e['client'].close()
