from uuid import uuid4
from sqlalchemy import select,func
from tests.auth_helpers import mutation
from tests.phase13_helpers import (finance_environment,period,document,add_entry,decide,preview,
    propose,approval_body,close,complete,payment_body,decision_body,period_body)
from app.finance.periods.models import DistributionClose,ReleaseShareSnapshot,ExternalPayment
from app.ledger.models import CreditAward


def test_full_financial_close_export_replay_and_partial_payment(client,database,settings,monkeypatch):
    env=finance_environment(client,database,settings,monkeypatch);p,doc,entry,frozen=complete(env)
    assert frozen['reproduced'] is True
    assert frozen['record']['cash']['distributable_cents']==100000
    assert frozen['record']['result']['people']==[{'user_id':env['owner']['user']['id'],'amount_cents':100000}]
    assert client.get(env['finance']+'/periods/'+p['id']).json()['state']=='closed'
    paths=[env['finance']+'/closes/'+frozen['id']+'/export?format='+f for f in ('csv','json','zip')]
    before=[client.get(path) for path in paths];assert all(r.status_code==200 for r in before)
    r=mutation(client,env['finance']+'/closes/'+frozen['id']+'/payments',payment_body(env,frozen))
    assert r.status_code==201,r.text
    assert [r.content for r in before]==[client.get(path).content for path in paths]
    statement=client.get(env['finance']+'/closes/'+frozen['id']+'/statement').json()
    assert statement['recipient']['outstanding_cents']==60000
    assert statement['recipient']['status']=='partially_recorded'
    with database.session() as db:
        for model in (CreditAward,DistributionClose,ReleaseShareSnapshot,ExternalPayment):
            assert db.scalar(select(func.count()).select_from(model))==1


def test_pending_entries_block_and_rejected_expenses_do_not_deduct(client,database,settings,monkeypatch):
    env=finance_environment(client,database,settings,monkeypatch);p=period(env);doc=document(env,p)
    receipt=add_entry(env,p,doc);assert 'unreviewed_financial_entry' in preview(env,p)['record']['blockers']
    decide(env,receipt)
    cost=add_entry(env,p,doc,kind='deduction',cents=20000,deduction_category='hosting',separate_charge_confirmed=True)
    assert 'unreviewed_financial_entry' in preview(env,p)['record']['blockers']
    decide(env,cost,'reject');assert close(env,p)['record']['cash']['distributable_cents']==100000


def test_void_before_close_keeps_history(client,database,settings,monkeypatch):
    env=finance_environment(client,database,settings,monkeypatch);p=period(env);doc=document(env,p)
    cost=decide(env,add_entry(env,p,doc,kind='deduction',cents=100,deduction_category='hosting',separate_charge_confirmed=True))
    cost=decide(env,cost,'void');assert len(cost['history'])==2
    decide(env,add_entry(env,p,doc,cents=200));assert close(env,p)['record']['cash']['net_cents']==200
    assert mutation(client,env['finance']+'/entries/'+cost['id']+'/decisions',decision_body(cost)).status_code==409


def test_stale_close_proposal_rejected_after_new_approved_entry(client,database,settings,monkeypatch):
    env=finance_environment(client,database,settings,monkeypatch);p=period(env);doc=document(env,p)
    decide(env,add_entry(env,p,doc));proposal=propose(env,p);decide(env,add_entry(env,p,doc,cents=1))
    r=mutation(client,env['finance']+'/proposals/'+proposal['id']+'/decisions',approval_body(proposal))
    assert r.status_code==409 and r.json()['error']['code']=='stale_finance_proposal'
    with database.session() as db:assert db.scalar(select(func.count()).select_from(DistributionClose))==0


def test_close_idempotency_and_closed_period_edits_fail(client,database,settings,monkeypatch):
    env=finance_environment(client,database,settings,monkeypatch);p=period(env);doc=document(env,p)
    entry=decide(env,add_entry(env,p,doc));proposal=propose(env,p);body=approval_body(proposal)
    path=env['finance']+'/proposals/'+proposal['id']+'/decisions'
    first=mutation(client,path,body);again=mutation(client,path,body)
    assert first.status_code==again.status_code==200
    assert first.json()['decision']['record']['close_id']==again.json()['decision']['record']['close_id']
    assert mutation(client,env['finance']+'/entries/'+entry['id']+'/decisions',decision_body(entry,'void')).status_code==409
    body['request_id']=str(uuid4());assert mutation(client,path,body).status_code==409


def test_open_dispute_blocks_freeze(client,database,settings,monkeypatch):
    from tests.phase6_helpers import open_dispute
    env=finance_environment(client,database,settings,monkeypatch);p=period(env);doc=document(env,p)
    decide(env,add_entry(env,p,doc));open_dispute(env,env['award'])
    assert 'disputed_release_credit' in preview(env,p)['record']['blockers']


def test_periods_are_sequential(client,database,settings,monkeypatch):
    from app.finance.calculation.periods import month_bounds
    env=finance_environment(client,database,settings,monkeypatch);p=period(env)
    _,end=month_bounds(env['month'],env['policy']['rules']['timezone']);next_month=end.strftime('%Y-%m')
    r=mutation(client,env['finance']+'/periods',period_body(env,next_month))
    assert r.status_code==409 and r.json()['error']['code']=='finance_previous_open'
    doc=document(env,p);decide(env,add_entry(env,p,doc));close(env,p)
    r=mutation(client,env['finance']+'/periods',period_body(env,'2040-01'))
    assert r.status_code==409 and r.json()['error']['code']=='finance_period_gap'
    assert period(env,next_month)['record']['previous_period_id']==p['id']


def test_unfinished_month_blocked_without_test_clock(client,database,settings,monkeypatch):
    from app.security.tokens import now
    env=finance_environment(client,database,settings,monkeypatch);monkeypatch.setattr('app.finance.close.service.now',now)
    p=period(env);doc=document(env,p);decide(env,add_entry(env,p,doc))
    assert 'accounting_month_not_finished' in preview(env,p)['record']['blockers']


def test_partial_release_work_blocks_initial_freeze(client,database,settings,monkeypatch):
    env=finance_environment(client,database,settings,monkeypatch,accepted=False);p=period(env);doc=document(env,p)
    decide(env,add_entry(env,p,doc));blockers=preview(env,p)['record']['blockers']
    assert 'unfinished_release_work' in blockers and 'empty_release_pool' in blockers
