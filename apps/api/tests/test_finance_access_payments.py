from datetime import timedelta
from uuid import UUID,uuid4
from sqlalchemy import select
from app.auth.models import User
from app.projects.models import ProjectMembership
from app.security.tokens import now
from tests.auth_helpers import mutation,bootstrap
from tests.phase13_helpers import *


def test_financial_source_permissions_and_own_statement(client,database,settings,monkeypatch):
    e=finance_environment(client,database,settings,monkeypatch);p,d,entry,closed=complete(e)
    private=[f'/periods/{p["id"]}',f'/documents/{d["id"]}/download',f'/documents/{d["id"]}/preview',
        f'/closes/{closed["id"]}',f'/closes/{closed["id"]}/export?format=json',f'/closes/{closed["id"]}/payments']
    for name in ['contributor','reviewer','viewer']:
        actor=e['actors'][name]['client']
        for path in private:assert actor.get(e['finance']+path).status_code==403
        assert mutation(actor,e['finance']+'/periods',period_body(e)).status_code==403
        assert mutation(actor,e['finance']+'/entries/'+entry['id']+'/decisions',decision_body(entry,'void')).status_code==403
        assert actor.get(e['finance']+'/periods').status_code==200
        assert actor.get(e['finance']+'/closes/'+closed['id']+'/statement?recipient_id='+e['owner']['user']['id']).status_code==403
    own=client.get(e['finance']+'/closes/'+closed['id']+'/statement').json()
    assert 'entries' not in own and 'ledger_snapshot' not in own
    assert own['recipient']['distribution_cents']==100000
    with database.session() as db:
        member=db.scalar(select(ProjectMembership).where(ProjectMembership.user_id==UUID(e['actors']['viewer']['id'])))
        member.role='finance';member.version+=1;db.commit()
    finance=e['actors']['viewer']['client'];assert finance.get(e['finance']+'/periods/'+p['id']).status_code==200
    assert mutation(finance,e['finance']+'/periods',period_body(e)).status_code==403
    with database.session() as db:
        member=db.scalar(select(ProjectMembership).where(ProjectMembership.user_id==UUID(e['actors']['viewer']['id'])))
        member.status='suspended';member.version+=1;db.commit()
    assert finance.get(e['finance']+'/closes/'+closed['id']+'/export?format=json').status_code==404


def test_payment_idempotency_reference_uniqueness_void_and_overpayment(client,database,settings,monkeypatch):
    e=finance_environment(client,database,settings,monkeypatch);p,d,entry,closed=complete(e)
    path=e['finance']+'/closes/'+closed['id']+'/payments';body=payment_body(e,closed)
    first=checked(mutation(client,path,body),201);second=checked(mutation(client,path,body),201);assert first['id']==second['id']
    repeated={**body,'request_id':str(uuid4())};assert mutation(client,path,repeated).status_code==409
    too_much=payment_body(e,closed,cents=70000);assert mutation(client,path,too_much).status_code==409
    too_much['overpayment_acknowledged']=True;checked(mutation(client,path,too_much),201)
    totals=client.get(path).json()['balances'][0];assert totals['overpaid_cents']==10000 and totals['outstanding_cents']==0
    void_body={'request_id':str(uuid4()),'reviewed_payment_hash':first['record_hash'],'bookkeeping_correction_only':True,
        'reason':'Correct a mistaken duplicate declaration without reversing any transfer'}
    checked(mutation(client,e['finance']+'/payments/'+first['id']+'/void',void_body))
    assert client.get(path).json()['balances'][0]['outstanding_cents']==30000
    assert mutation(client,path,repeated).status_code==409
    assert client.get(e['finance']+'/closes/'+closed['id']).json()['record_hash']==closed['record_hash']


def test_payment_invalid_time_recipient_amount_and_stale_hash(client,database,settings,monkeypatch):
    e=finance_environment(client,database,settings,monkeypatch);p,d,entry,closed=complete(e);path=e['finance']+'/closes/'+closed['id']+'/payments'
    for change in [{'paid_at':(now()+timedelta(days=1)).isoformat()}, {'paid_at':'2020-01-01T00:00:00Z'},
        {'paid_at':'2020-01-01'}, {'recipient_id':str(uuid4())},{'amount_cents':True},{'amount_cents':0},
        {'reviewed_close_hash':'0'*64},{'externally_completed':False},{'synthetic_only':False}]:
        assert mutation(client,path,payment_body(e,closed,**change)).status_code in {404,409,422}
    assert not client.get(path).json()['items']


def test_release_correction_changes_only_future_closed_shares(client,database,settings,monkeypatch):
    from tests.phase6_helpers import open_dispute,resolver,correction,vote,finalize
    from app.finance.calculation.periods import month_bounds
    e=finance_environment(client,database,settings,monkeypatch);p,d,entry,first=complete(e,cents=10000)
    original=client.get(e['finance']+'/closes/'+first['id']+'/export?format=json').content
    case=resolver(e,open_dispute(e,e['award']));r=vote(e,correction(e,case),who='resolver');finalize(e,r,who='resolver')
    _,end=month_bounds(e['month'],'UTC');month=end.strftime('%Y-%m');advance_clock(e,month,monkeypatch)
    p2=period(e,month);d2=document(e,p2);decide(e,add_entry(e,p2,d2,cents=10000))
    assert 'release_correction_requires_approval' in preview(e,p2)['record']['blockers']
    approval=approve_proposal(e,propose(e,p2,'release_correction'))
    second=close(e,p2);amounts={p['user_id']:p['amount_cents'] for p in second['record']['result']['people']}
    assert amounts[e['owner']['user']['id']]==6000 and amounts[e['actors']['contributor']['id']]==4000
    assert second['record']['release']['record']['version']==2
    assert client.get(e['finance']+'/closes/'+first['id']+'/export?format=json').content==original
    own=e['actors']['contributor']['client'].get(e['finance']+'/closes/'+second['id']+'/statement')
    assert own.status_code==200 and own.json()['recipient']['distribution_cents']==4000
