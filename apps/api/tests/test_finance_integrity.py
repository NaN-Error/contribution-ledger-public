from copy import deepcopy
from datetime import timedelta
from types import SimpleNamespace
from uuid import UUID,uuid4
import json
from io import BytesIO
from zipfile import ZipFile
from hashlib import sha256
import pytest
from sqlalchemy import select,func,text
from sqlalchemy.exc import DBAPIError
from alembic import command
from app.db.migration import migration_config
from app.finance.close.service import verify_close
from app.finance.exports.serialization import bundle
from app.finance.periods.models import FinanceEntry,FinancePeriod,DistributionClose,FinanceReceiptImport
from app.policies.service import digest
from tests.auth_helpers import mutation
from tests.phase13_helpers import *


def test_csv_import_idempotency_atomicity_and_source_identity(client,database,settings,monkeypatch):
    e=finance_environment(client,database,settings,monkeypatch);p=period(e);d=document(e,p)
    path=e['finance']+'/periods/'+p['id']+'/import-receipts'
    body={'request_id':str(uuid4()),'reason':'Import a whole canonical synthetic statement transaction',
        'document_id':d['id'],'source_name':'Canonical storefront','statement_reference':'Test January',
        'revenue_basis':'net_storefront_settlements','already_deducted':['platform_fees'],
        'csv_text':'line_reference,amount_cents,description\nline1,100,First synthetic receipt\nline2,200,Second synthetic receipt\n'}
    first=checked(mutation(client,path,body),201);again=checked(mutation(client,path,body),201)
    assert [r['id'] for r in first['items']]==[r['id'] for r in again['items']]
    changed={**body,'csv_text':body['csv_text'].split('line2')[0]};assert mutation(client,path,changed).status_code==409
    changed={**body,'request_id':str(uuid4())};assert mutation(client,path,changed).status_code==409
    changed={**body,'request_id':str(uuid4()),'csv_text':'line_reference,amount_cents,description\nline3,300,New synthetic receipt\nline2,200,Existing receipt conflict\n'}
    assert mutation(client,path,changed).status_code==409
    with database.session() as db:
        assert db.scalar(select(func.count()).select_from(FinanceEntry))==2
        assert db.scalar(select(func.count()).select_from(FinanceReceiptImport))==1
    assert all(r['state']=='pending' for r in first['items'])


def test_net_receipt_prevents_double_deduction_and_wrong_basis(client,database,settings,monkeypatch):
    e=finance_environment(client,database,settings,monkeypatch);p=period(e);d=document(e,p)
    r=decide(e,add_entry(e,p,d,already_deducted=['platform_fees','refunds']))
    bad=entry_body(d,kind='deduction',deduction_category='refunds',related_entry_id=r['id'],separate_charge_confirmed=True)
    assert mutation(client,e['finance']+'/periods/'+p['id']+'/entries',bad).status_code==422
    bad=entry_body(d,revenue_basis='gross_receipts',already_deducted=[])
    assert mutation(client,e['finance']+'/periods/'+p['id']+'/entries',bad).status_code==422
    assert close(e,p)['record']['cash']['distributable_cents']==100000


def test_reserve_carryforward_and_linked_cash_correction_preserve_past(client,database,settings,monkeypatch):
    from app.finance.calculation.periods import month_bounds
    e=finance_environment(client,database,settings,monkeypatch);p=period(e);d=document(e,p)
    receipt=decide(e,add_entry(e,p,d,cents=1000));decide(e,add_entry(e,p,d,kind='reserve_hold',cents=300));first=close(e,p)
    assert first['record']['cash']['distributable_cents']==700
    _,end=month_bounds(e['month'],'UTC');month=end.strftime('%Y-%m');advance_clock(e,month,monkeypatch)
    p2=period(e,month);d2=document(e,p2);decide(e,add_entry(e,p2,d2,kind='reserve_release',cents=100))
    decide(e,add_entry(e,p2,d2,kind='adjustment_debit',cents=20,related_entry_id=receipt['id']))
    second=close(e,p2)
    assert second['record']['cash']['distributable_cents']==80
    assert second['record']['cash']['closing_reserve_cents']==200
    assert client.get(e['finance']+'/closes/'+first['id']).json()['record_hash']==first['record_hash']


def test_deficit_is_not_forgotten_at_zero_distribution(client,database,settings,monkeypatch):
    from app.finance.calculation.periods import month_bounds
    e=finance_environment(client,database,settings,monkeypatch);p=period(e);d=document(e,p)
    decide(e,add_entry(e,p,d,cents=100));decide(e,add_entry(e,p,d,kind='deduction',cents=300,deduction_category='hosting',separate_charge_confirmed=True))
    first=close(e,p);assert first['record']['cash']['closing_deficit_cents']==-200
    _,end=month_bounds(e['month'],'UTC');month=end.strftime('%Y-%m');advance_clock(e,month,monkeypatch)
    p2=period(e,month);d2=document(e,p2);decide(e,add_entry(e,p2,d2,cents=500));second=close(e,p2)
    assert second['record']['cash']['distributable_cents']==300
    assert second['record']['cash']['closing_deficit_cents']==0


def test_history_guards_replay_tamper_and_guarded_downgrade(client,database,settings,monkeypatch):
    e=finance_environment(client,database,settings,monkeypatch);p,d,entry,frozen=complete(e)
    for table in ['finance_periods','finance_documents','finance_entries','finance_entry_decisions','finance_proposals','finance_approvals','release_share_snapshots','distribution_closes']:
        for verb in ['DELETE FROM '+table,"UPDATE "+table+" SET record='{}'"]:
            with pytest.raises(DBAPIError),database.engine.begin() as conn:conn.execute(text(verb))
    row=SimpleNamespace(record=deepcopy(frozen['record']),record_hash=frozen['record_hash'])
    row.record['result']['people'][0]['amount_cents']+=1;row.record_hash=digest(row.record)
    from app.core.errors import ApiError
    with pytest.raises(ApiError):verify_close(row)
    config=migration_config()
    with pytest.raises(RuntimeError),database.engine.begin() as connection:
        config.attributes['connection']=connection;command.downgrade(config,'0012_historical_reconstruction')
    assert client.get(e['finance']+'/closes/'+frozen['id']).status_code==200
    data=client.get(e['finance']+'/closes/'+frozen['id']+'/export?format=zip').content
    with ZipFile(BytesIO(data)) as z:
        manifest=json.loads(z.read('manifest.json'))
        for item in manifest['files']:assert sha256(z.read(item['path'])).hexdigest()==item['sha256']
