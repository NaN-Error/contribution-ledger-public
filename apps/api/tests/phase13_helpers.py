"""Fictional finance records; explicit clock overrides never backdate awards."""
from base64 import b64encode
from datetime import timedelta
from uuid import uuid4
from app.security.tokens import now
from app.finance.calculation.periods import month_bounds
from tests.auth_helpers import mutation
from tests.phase6_helpers import environment, award


def finance_environment(client, database, settings, monkeypatch, *, accepted=True):
    env = environment(client, database, settings)
    if accepted: env['award'] = award(env)
    env['month'] = now().strftime('%Y-%m')
    advance_clock(env, env['month'], monkeypatch)
    env['finance'] = env['root'] + '/finance'
    return env


def advance_clock(env, month, monkeypatch):
    _, end = month_bounds(month, env['policy']['rules']['timezone'])
    monkeypatch.setattr('app.finance.close.service.now', lambda: end + timedelta(seconds=1))
    monkeypatch.setattr('app.finance.simulator.service.now', lambda: end + timedelta(seconds=1))


def checked(response, status=200):
    assert response.status_code == status, response.text
    return response.json()


def period_body(env, month=None):
    return {'request_id': str(uuid4()), 'month': month or env['month'],
        'source_policy_id': env['policy']['id'], 'calculation_policy_id': env['policy']['id'],
        'agreement_reference': 'Synthetic reviewed finance agreement',
        'deficit_rule': 'carry_negative_balance_forward', 'synthetic_only': True,
        'period_rules_reviewed': True, 'reason': 'Create a fictional accounting period with explicit rules'}


def period(env, month=None):
    return checked(mutation(env['client'], env['finance']+'/periods', period_body(env, month)),201)


def upload_body(text='Fictional receipt. Amount and basis reviewed by a human.', filename='statement.txt'):
    return {'request_id': str(uuid4()), 'title': 'Synthetic statement', 'provenance': 'Fictional test document',
        'file': {'filename': filename, 'media_type': 'text/plain' if filename.endswith('.txt') else 'text/csv',
                 'content_base64': b64encode(text.encode()).decode()}, 'reason': 'Attach synthetic supporting financial evidence'}


def document(env, p, text=None):
    return checked(mutation(env['client'],env['finance']+'/periods/'+p['id']+'/documents',
        upload_body() if text is None else upload_body(text)),201)


def entry_body(doc, *, kind='receipt', cents=100000, **kwargs):
    item = {'document_id': doc['id'], 'kind': kind, 'amount_cents': cents,
        'source_name': 'Synthetic storefront account', 'statement_reference': 'Statement sample',
        'line_reference': str(uuid4()), 'description': 'A fictional documented financial entry',
        'revenue_basis': 'net_storefront_settlements' if kind == 'receipt' else None,
        'already_deducted': ['platform_fees'] if kind == 'receipt' else [], **kwargs}
    return {'request_id': str(uuid4()), 'reason': 'Record this documented fictional financial entry', 'entry': item}


def add_entry(env,p,doc,**kwargs):
    return checked(mutation(env['client'],env['finance']+'/periods/'+p['id']+'/entries',entry_body(doc,**kwargs)),201)


def decision_body(entry,action='approve'):
    return {'request_id':str(uuid4()),'reviewed_entry_hash':entry['record_hash'],
        'expected_decision_hash':entry['decision']['record_hash'] if entry['decision'] else None,
        'action':action,'document_reviewed':True,'reason':'Administrator reviewed this source document and entry'}


def decide(env,entry,action='approve'):
    return checked(mutation(env['client'],env['finance']+'/entries/'+entry['id']+'/decisions',decision_body(entry,action)))


def preview(env,p,kind='close'):
    return checked(mutation(env['client'],env['finance']+'/periods/'+p['id']+'/preview?kind='+kind))


def proposal_body(pv,kind='close'):
    return {'request_id':str(uuid4()),'kind':kind,'reviewed_preview_hash':pv['preview_hash'],
        'financial_records_reviewed':True,'contribution_scope_reviewed':True,'synthetic_only':True,
        'reason':'Propose the inspected synthetic distribution without real money movement'}


def propose(env,p,kind='close'):
    pv=preview(env,p,kind);assert not pv['record']['blockers'],pv['record']['blockers']
    return checked(mutation(env['client'],env['finance']+'/periods/'+p['id']+'/proposals',proposal_body(pv,kind)),201)


def approval_body(proposal,action='approve'):
    return {'request_id':str(uuid4()),'reviewed_proposal_hash':proposal['record_hash'],
        'action':action,'reviewed':True,'synthetic_only':True,
        'reason':'Explicit administrator decision on this preserved synthetic proposal'}


def approve_proposal(env,proposal):
    return checked(mutation(env['client'],env['finance']+'/proposals/'+proposal['id']+'/decisions',approval_body(proposal)))


def close(env,p):
    approval=approve_proposal(env,propose(env,p))
    return checked(env['client'].get(env['finance']+'/closes/'+approval['decision']['record']['close_id']))


def complete(env,cents=100000):
    p=period(env);doc=document(env,p);entry=decide(env,add_entry(env,p,doc,cents=cents))
    return p,doc,entry,close(env,p)


def payment_body(env,closed,cents=40000,**kwargs):
    return {'request_id':str(uuid4()),'recipient_id':env['owner']['user']['id'],'amount_cents':cents,
        'provider':'Fictional bank reference','external_reference':str(uuid4()),'paid_at':now().isoformat(),
        'reviewed_close_hash':closed['record_hash'],'externally_completed':True,'synthetic_only':True,
        'reason':'Record a fictional external transfer declaration, not a real payment',**kwargs}
