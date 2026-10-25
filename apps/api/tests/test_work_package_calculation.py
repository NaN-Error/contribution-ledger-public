from copy import deepcopy
from random import Random
from uuid import UUID
import pytest
from pydantic import ValidationError
from app.core.errors import ApiError
from app.contributions.work_packages.schemas import ScopeInput
from app.contributions.work_packages.calculation import distribute_percentages, normalize_scope, input_from_snapshot, scope_blockers
from tests.phase4_helpers import scope

A='00000000-0000-0000-0000-000000000001'
B='00000000-0000-0000-0000-000000000002'
PEOPLE={A:{'display_name':'Synthetic A'},B:{'display_name':'Synthetic B'}}


def test_percentage_largest_remainder_has_exact_stable_sum():
    entries=[{'user_id':A,'role':'testing','basis_points':5000},{'user_id':B,'role':'design','basis_points':5000}]
    rows, unused=distribute_percentages(1,entries)
    assert [r['atoms'] for r in rows]==[1,0] and unused==0
    assert distribute_percentages(1,entries[::-1])==(rows,unused)


def test_unassigned_bucket_is_not_an_owner_or_hidden_rounding_gain():
    rows, unused=distribute_percentages(1001,[{'user_id':A,'role':'testing','basis_points':5000}])
    assert rows[0]['atoms']==501 and unused==500
    assert distribute_percentages(999,[])==([],999)


def test_percentage_incomplete_even_when_unassigned_rounds_to_zero():
    raw=scope(A,1); raw['deliverables'][0]['attribution']={'mode':'percent','entries':[{'user_id':A,'role':'design','basis_points':9999}]}
    doc=normalize_scope(ScopeInput.model_validate(raw),1,PEOPLE)
    assert doc['deliverables'][0]['unassigned_atoms']==0
    assert not doc['deliverables'][0]['attribution_complete']
    assert any('100%' in s for s in scope_blockers(doc,set(PEOPLE)))


def test_seeded_percentage_properties_and_order_independence():
    rng=Random(417)
    for _ in range(500):
        budget=rng.randint(1,10**12); a=rng.randint(1,9999); b=rng.randint(1,10000-a)
        entries=[{'user_id':A,'role':'design','basis_points':a},{'user_id':B,'role':'testing','basis_points':b}]
        rows, unused=distribute_percentages(budget,entries)
        assert sum(r['atoms'] for r in rows)+unused==budget
        assert all(r['atoms']>=0 for r in rows) and unused>=0
        assert distribute_percentages(budget,list(reversed(entries)))==(rows,unused)


def test_snapshot_roundtrip_retains_ids_and_raw_allocation_mode():
    doc=normalize_scope(ScopeInput.model_validate(scope(A)),100_000,PEOPLE)
    assert normalize_scope(input_from_snapshot(doc),100_000,PEOPLE)==doc


def test_multiple_roles_for_one_person_are_not_duplicate_credit():
    raw=scope(A,100); raw['deliverables'][0]['attribution']['entries']=[
        {'user_id':A,'role':'testing','atoms':20},{'user_id':A,'role':'design','atoms':80}]
    doc=normalize_scope(ScopeInput.model_validate(raw),100,PEOPLE)
    assert not scope_blockers(doc,set(PEOPLE))
    assert sum(e['atoms'] for e in doc['deliverables'][0]['resolved_attributions'])==100


@pytest.mark.parametrize('field,value',[('budget_atoms',True),('budget_atoms',1.1),('budget_atoms','100'),('budget_atoms',0),('budget_atoms',-1),('budget_atoms',10**12+1)])
def test_deliverable_amounts_are_bounded_strict_integers(field,value):
    raw=scope(A);raw['deliverables'][0][field]=value
    with pytest.raises(ValidationError): ScopeInput.model_validate(raw)


@pytest.mark.parametrize('case',['duplicate_person','duplicate_criteria','duplicate_deliverable','over_units','over_percent','foreign_attribution','empty_criteria','control_text','unknown_field','boolean_percentage'])
def test_invalid_scope_shapes_are_rejected(case):
    raw=scope(A);d=raw['deliverables'][0]
    if case=='duplicate_person': raw['intended_contributor_ids'].append(A)
    if case=='duplicate_criteria': d['acceptance_criteria']*=2
    if case=='duplicate_deliverable':
        d['id']=A;raw['deliverables'].append(deepcopy(d))
    if case=='over_units': d['attribution']['entries'][0]['atoms']+=1
    if case=='over_percent': d['attribution']={'mode':'percent','entries':[{'user_id':A,'role':'design','basis_points':10001}]}
    if case=='foreign_attribution': d['attribution']['entries'][0]['user_id']=B
    if case=='empty_criteria': d['acceptance_criteria']=[]
    if case=='control_text': raw['outcome']='Text with\x00 forbidden control'
    if case=='unknown_field': raw['earned_atoms']=1000
    if case=='boolean_percentage': d['attribution']={'mode':'percent','entries':[{'user_id':A,'role':'design','basis_points':True}]}
    with pytest.raises(ValidationError): ScopeInput.model_validate(raw)


def test_unknown_and_departed_participants_are_distinct_from_zero_value():
    with pytest.raises(ApiError) as ex: normalize_scope(ScopeInput.model_validate(scope(B)),100_000,{A:PEOPLE[A]})
    assert ex.value.code=='participant_unavailable'
    doc=normalize_scope(ScopeInput.model_validate(scope(A)),100_000,PEOPLE)
    assert 'no longer' in ' '.join(scope_blockers(doc,set()))


def test_child_budgets_cannot_multiply_parent_and_partial_plan_stays_visible():
    raw=scope(A,101)
    with pytest.raises(ApiError) as ex: normalize_scope(ScopeInput.model_validate(raw),100,PEOPLE)
    assert ex.value.code=='package_budget_exceeded'
    doc=normalize_scope(ScopeInput.model_validate(scope(A,60)),100,PEOPLE)
    assert doc['unplanned_atoms']==40 and scope_blockers(doc,set(PEOPLE))
