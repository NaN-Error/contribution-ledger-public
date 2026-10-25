from uuid import uuid4
from zoneinfo import ZoneInfo
from app.security.tokens import now
from tests.auth_helpers import mutation


def input_for(env, cents=1000000):
    return {'source_policy_id':env['policy']['id'],'calculation_policy_id':env['policy']['id'],
        'month':now().astimezone(ZoneInfo(env['policy']['rules']['timezone'])).strftime('%Y-%m'),
        'amount_cents':cents}


def preview(env, body=None, client=None):
    result=mutation(client or env['client'],env['root']+'/simulator/preview',body or input_for(env))
    assert result.status_code==200,result.text
    return result.json()


def save_body(record):
    return {'request_id':str(uuid4()),'title':'Synthetic non-payable example','input':record['input'],
        'reviewed_snapshot_hash':record['snapshot_hash'],'hypothetical_confirmed':True}


def save(env, record=None):
    result=mutation(env['client'],env['root']+'/simulator/scenarios',save_body(record or preview(env)))
    assert result.status_code==201,result.text
    return result.json()
