"""Native locking, scoped relations and append-only controls; skip without PostgreSQL."""
from uuid import uuid4
import pytest
from sqlalchemy import text,select,func
from sqlalchemy.exc import DBAPIError
from tests.test_postgres_accounts import pg_accounts,browser
from tests.test_postgres_planning import race_requests
from tests.phase6_helpers import environment,assign,vote,final_body,award,open_dispute,resolver,correction,finalize
from app.ledger.models import CreditAward,ContributionEvent

pytestmark=pytest.mark.postgres


def test_native_duplicate_finalization_is_idempotent(pg_accounts):
    settings,db=pg_accounts;client=browser(settings,db)
    try:
        e=environment(client,db,settings);r=vote(e,assign(e));path=e['root']+'/reviews/'+r['id']+'/finalize';body=final_body(r)
        assert sorted(race_requests(settings,db,e['actors']['reviewer']['client'],[(path,body),(path,body)]))==[200,200]
        with db.session() as session:assert session.scalar(select(func.count()).select_from(CreditAward))==1
    finally:client.close()


def test_native_different_finalization_keys_still_award_once(pg_accounts):
    settings,db=pg_accounts;client=browser(settings,db)
    try:
        e=environment(client,db,settings);r=vote(e,assign(e));path=e['root']+'/reviews/'+r['id']+'/finalize'
        assert sorted(race_requests(settings,db,e['actors']['reviewer']['client'],[(path,final_body(r)),(path,final_body(r))]))==[200,409]
        assert client.get(e['root']+'/contributions').json()['total_issued_atoms']==100000
    finally:client.close()


def test_native_independent_deliverables_preserve_total_under_race(pg_accounts):
    settings,db=pg_accounts;client=browser(settings,db)
    try:
        e=environment(client,db,settings,partial=True);a=vote(e,assign(e,0));b=vote(e,assign(e,1))
        requests=[(e['root']+'/reviews/'+r['id']+'/finalize',final_body(r)) for r in [a,b]]
        assert sorted(race_requests(settings,db,e['actors']['reviewer']['client'],requests))==[200,200]
        assert client.get(e['root']+'/contributions/integrity').json()['consistent']
        assert client.get(e['path']).json()['issued_atoms']==100000
    finally:client.close()


def test_native_credit_history_rejects_update_delete_truncate(pg_accounts):
    settings,db=pg_accounts;client=browser(settings,db)
    try:
        e=environment(client,db,settings);award(e)
        for sql in ['UPDATE contribution_events SET delta_atoms=1','DELETE FROM credit_awards','TRUNCATE contribution_events CASCADE']:
            with pytest.raises(DBAPIError),db.engine.begin() as conn:conn.execute(text(sql))
        with db.engine.begin() as conn:
            # Every historical row references one exact existing assignment.
            with pytest.raises(DBAPIError):
                conn.execute(text("INSERT INTO review_decisions (id,workspace_id,project_id,package_id,review_id,reviewer_id,decision,findings,reviewed_target_hash,request_id,request_hash,reason,created_at) SELECT gen_random_uuid(),workspace_id,project_id,package_id,review_id,gen_random_uuid(),decision,findings,reviewed_target_hash,gen_random_uuid(),request_hash,reason,created_at FROM review_decisions LIMIT 1"))
    finally:client.close()


def test_native_resolution_race_posts_adjustment_once(pg_accounts):
    settings,db=pg_accounts;client=browser(settings,db)
    try:
        e=environment(client,db,settings);case=resolver(e,open_dispute(e,award(e)));r=vote(e,correction(e,case),who='resolver')
        path=e['root']+'/reviews/'+r['id']+'/finalize';body=final_body(r)
        assert race_requests(settings,db,e['actors']['resolver']['client'],[(path,body),(path,body)])==[200,200]
        with db.session() as session:
            assert session.scalar(select(func.count()).select_from(ContributionEvent))==3
        assert client.get(e['root']+'/contributions/integrity').json()['consistent']
    finally:client.close()
