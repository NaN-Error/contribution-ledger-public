"""Exact arithmetic and strict input tests; no live billing or real records."""
from copy import deepcopy
from io import StringIO
from uuid import uuid4
import csv, random
import pytest
from pydantic import ValidationError
from app.core.errors import ApiError
from app.finance.periods.arithmetic import cash_waterfall
from app.finance.periods.schemas import AddEntry, ImportReceipts, RecordPayment, CreatePeriod
from app.finance.periods.service import parse_receipts, source_key
from app.finance.exports.serialization import text_cell, json_bytes
from tests.phase13_helpers import entry_body


def item(kind,amount):return {'kind':kind,'amount_cents':amount}


def test_cash_waterfall_preserves_negative_balance_and_reserve():
    first=cash_waterfall([item('receipt',1000),item('deduction',1600)])
    assert first['net_cents']==-600 and first['closing_deficit_cents']==-600 and first['distributable_cents']==0
    second=cash_waterfall([item('receipt',1000),item('reserve_hold',200)],0,-600)
    assert second['distributable_cents']==200 and second['closing_reserve_cents']==200
    third=cash_waterfall([item('reserve_release',100)],200,0)
    assert third['distributable_cents']==100 and third['closing_reserve_cents']==100


@pytest.mark.parametrize('kind',['receipt','deduction','reserve_hold','reserve_release','adjustment_credit','adjustment_debit'])
def test_all_cash_kinds_have_explicit_signs(kind):
    r=cash_waterfall([item(kind,100)],100,0)
    assert r['net_cents']==(100 if kind in {'receipt','reserve_release','adjustment_credit'} else -100)


@pytest.mark.parametrize('value',[True,False,-1,0,1.0,'1',10**12+1])
def test_cash_rejects_inexact_or_invalid_amount(value):
    with pytest.raises(ValueError):cash_waterfall([item('receipt',value)])


@pytest.mark.parametrize('reserve,deficit',[(True,0),(-1,0),(0,1),(0,False),(10**12+1,0),(0,-10**12-1)])
def test_opening_balances_are_bounded_exact(reserve,deficit):
    with pytest.raises(ValueError):cash_waterfall([],reserve,deficit)


def test_reserve_overdraw_and_unfunded_hold_are_blockers():
    assert 'reserve_overdrawn' in cash_waterfall([item('reserve_release',1)])['blockers']
    assert 'unfunded_reserve_hold' in cash_waterfall([item('reserve_hold',1)])['blockers']
    with pytest.raises(ValueError):cash_waterfall([item('receipt',10**12),item('receipt',1)])


def test_seeded_cash_conservation_and_order_independence():
    rng=random.Random(13013)
    for _ in range(500):
        revenue=rng.randrange(1,100000);expense=rng.randrange(1,100000);reserve=rng.randrange(10000)
        rows=[item('receipt',revenue),item('deduction',expense)]
        result=cash_waterfall(rows,reserve,-10)
        assert result==cash_waterfall(list(reversed(rows)),reserve,-10)
        assert result['distributable_cents']+result['closing_deficit_cents']==revenue-expense-10
        assert result['closing_reserve_cents']==reserve


@pytest.mark.parametrize('value',[True,0,-1,1.5,'100',10**12+1])
def test_entry_schema_strict_cents(value):
    with pytest.raises(ValidationError):AddEntry.model_validate(entry_body({'id':str(uuid4())},cents=value))


def test_net_basis_and_settlement_deduction_requirements():
    b=entry_body({'id':str(uuid4())});b['entry']['already_deducted']=[]
    with pytest.raises(ValidationError):AddEntry.model_validate(b)
    b['entry']['revenue_basis']='gross_receipts';AddEntry.model_validate(b)
    b['entry']['already_deducted']=['platform_fees']
    with pytest.raises(ValidationError):AddEntry.model_validate(b)
    b=entry_body({'id':str(uuid4())},kind='deduction',deduction_category='refunds',separate_charge_confirmed=True)
    with pytest.raises(ValidationError):AddEntry.model_validate(b)
    b['entry']['related_entry_id']=str(uuid4());AddEntry.model_validate(b)


def csv_command(value):
    return ImportReceipts(request_id=uuid4(),reason='Import the inspected synthetic receipt rows',document_id=uuid4(),
        source_name='Example account',statement_reference='Example statement',revenue_basis='net_storefront_settlements',
        already_deducted=['platform_fees'],csv_text=value)


@pytest.mark.parametrize('value',['=1+1','1.20','-1','+1','1e3','１','0','1000000000001'])
def test_csv_rejects_formulas_decimals_and_invalid_amounts(value):
    with pytest.raises(ApiError):parse_receipts(csv_command('line_reference,amount_cents,description\nrow1,'+value+',Synthetic revenue row\n'))


def test_csv_exact_header_quoted_content_and_no_partial_parsing():
    good='line_reference,amount_cents,description\nrow1,123,"Synthetic revenue, from testing"\n'
    assert parse_receipts(csv_command(good))[0].amount_cents==123
    for bad in ['',good.replace('amount_cents','amount'),good+'row2,999\n',good+'row3,0,Invalid row value\n']:
        with pytest.raises((ApiError,ValidationError)):parse_receipts(csv_command(bad))


@pytest.mark.parametrize('value',['=HYPERLINK("x")','+SUM(1,2)','-1+2','@cmd','\t=cmd','\r=cmd','＝1+2','Normal, "name"','\u202e=cmd'])
def test_csv_untrusted_text_has_visible_nonformula_prefix(value):
    safe=text_cell(value)
    assert safe.startswith('text: ') and not any(c in safe for c in '\t\r\n')
    buffer=StringIO();csv.writer(buffer,quoting=csv.QUOTE_ALL).writerow([safe])
    assert next(csv.reader(StringIO(buffer.getvalue())))[0]==safe


def test_normalized_source_references_keep_identity_without_amount():
    assert source_key(' Store A ','ＪＡＮ  2026','Line 1')==source_key('store a','jan 2026','line 1')
    assert source_key('store','statement','line1')!=source_key('store','statement','line2')


def test_export_json_is_canonical_and_rejects_nonfinite_numbers():
    assert json_bytes({'b':1,'a':2})==json_bytes({'a':2,'b':1})
    with pytest.raises(ValueError):json_bytes({'bad':float('nan')})
