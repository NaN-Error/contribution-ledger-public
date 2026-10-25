"""Exact arithmetic regression fixtures plus bounded adversarial/property checks."""
import copy
import json
from pathlib import Path
import random
import pytest
from app.finance.calculation.engine import distribute, largest_remainder, MAX_CENTS, MAX_SAFE_INTEGER

CASE_PATH = next(base / 'tests/fixtures/simulator_cases.json' for base in Path(__file__).resolve().parents
                 if (base / 'tests/fixtures/simulator_cases.json').is_file())
CASES = json.loads(CASE_PATH.read_text())['fixtures']


@pytest.mark.parametrize('case', CASES, ids=lambda c: c['id'])
def test_documented_synthetic_case(case):
    result = distribute(**case['input'])
    assert {p['user_id']: p['amount_cents'] for p in result['people']} == case['expected_people_cents']
    assert result['unallocated_cents'] == case['expected_unallocated_cents']
    assert result['status'] == case['expected_status']
    assert result['payable'] is False
    assert result['allocated_cents'] + result['unallocated_cents'] == case['input']['amount_cents']


@pytest.mark.parametrize('value', [-1, True, 1.2, '100', None, MAX_CENTS + 1])
def test_rejects_invalid_money(value):
    with pytest.raises(ValueError):
        largest_remainder(value, [('a', 1)])


@pytest.mark.parametrize('weights', [[], [('a',0)], [('a',-1)], [('a',True)], [('a',1.5)],
    [('a',1),('a',2)], [('NAME',1)], [('someone name',1)], [('a',MAX_SAFE_INTEGER),('b',1)]])
def test_rejects_invalid_weights(weights):
    with pytest.raises(ValueError):
        largest_remainder(10, weights)


def test_random_allocation_conservation_quota_and_order_independence():
    generator = random.Random(701)
    for _ in range(1000):
        count = generator.randint(1,20)
        weights = [(f'id_{i:03}',generator.randint(0,100000)) for i in range(count)]
        if not sum(v for _,v in weights):weights[0]=(weights[0][0],1)
        total = generator.randint(0,MAX_CENTS)
        a = largest_remainder(total,weights)
        generator.shuffle(weights)
        assert a == largest_remainder(total,weights)
        assert sum(r['amount_cents'] for r in a) == total
        for r in a:
            assert r['amount_cents'] in {r['floor_cents'],r['floor_cents']+1}
            assert r['amount_cents'] == r['floor_cents']+r['rounding_cent']
            assert r['remainder_numerator'] == (total*r['weight']) % r['denominator']
            if r['weight']==0:assert r['amount_cents']==0


def test_pool_and_people_order_cannot_change_result_or_mutate_input():
    source = copy.deepcopy(CASES[0]['input'])
    untouched = copy.deepcopy(source)
    expected = distribute(**source)
    assert source == untouched
    source['pools'].reverse()
    for p in source['pools']:p['recipients'].reverse()
    assert distribute(**source)==expected


@pytest.mark.parametrize('mutation', ['duplicate_pool','bad_sum','zero_weight','unknown_pool','duplicate_person','negative_atoms','bad_dispute'])
def test_engine_rejects_invalid_pool_configuration(mutation):
    pools=copy.deepcopy(CASES[0]['input']['pools'])
    if mutation=='duplicate_pool':pools[1]['key']='release'
    elif mutation=='bad_sum':pools[0]['weight_bps']=7001
    elif mutation=='zero_weight':pools[0]['weight_bps']=0
    elif mutation=='unknown_pool':pools[0]['key']='owner'
    elif mutation=='duplicate_person':pools[0]['recipients'].append(pools[0]['recipients'][0])
    elif mutation=='negative_atoms':pools[0]['recipients'][0]['atoms']=-1
    elif mutation=='bad_dispute':pools[0]['blocked_by_dispute']='false'
    with pytest.raises(ValueError):distribute(100,pools)


def test_largest_remainder_is_not_falsely_assumed_monotone():
    weights=[('a',1500),('b',1500),('c',900),('d',500),('e',500),('f',200)]
    first={r['key']:r['amount_cents'] for r in largest_remainder(25,weights)}
    second={r['key']:r['amount_cents'] for r in largest_remainder(26,weights)}
    assert any(second[k]<first[k] for k in first)  # Documented limitation, not a floating-point bug.
