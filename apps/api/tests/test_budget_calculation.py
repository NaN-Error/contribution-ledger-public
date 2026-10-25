from copy import deepcopy
from random import Random
import pytest
from app.core.errors import ApiError
from app.contributions.budgets.calculation import preview_change, validate_snapshot
from app.policies.templates import templates


def state(total=1_000_000, reserve=100_000):
    return {'milestone_id': 'synthetic', 'policy_id': 'synthetic', 'version': 1, 'status': 'active',
        'total_atoms': total, 'reserve_floor_atoms': reserve, 'allocated_atoms': 0, 'issued_atoms': 0, 'allocations': []}


def rules(): return templates('UTC')[0]['rules']


def add(atoms): return {'kind': 'allocate', 'title': 'Useful synthetic outcome', 'category': 'art', 'pool_key': 'release', 'atoms': atoms}


def test_exact_planning_ratios_and_reserved_capacity():
    before = state(); original = deepcopy(before)
    result = preview_change(before, add(900_000), rules())
    assert before == original
    assert result['after_totals']['available_atoms'] == 0
    assert result['after_totals']['unassigned_atoms'] == 100_000
    assert result['after_totals']['issued_atoms'] == 0
    assert result['planned_budget_shares'][0]['after'] == {'numerator_atoms': 900_000, 'denominator_atoms': 1_000_000}
    with pytest.raises(ApiError): preview_change(before, add(900_001), rules())


def test_increasing_total_previews_dilution_of_planned_budget_not_credit():
    allocated = preview_change(state(), add(200_000), rules())['after']
    result = preview_change(allocated, {'kind': 'set_budget', 'total_atoms': 2_000_000, 'reserve_floor_atoms': 100_000}, rules())
    share = result['planned_budget_shares'][0]
    assert share['before'] == {'numerator_atoms': 200_000, 'denominator_atoms': 1_000_000}
    assert share['after'] == {'numerator_atoms': 200_000, 'denominator_atoms': 2_000_000}
    assert result['after_totals']['issued_atoms'] == 0


def test_already_issued_units_cannot_be_deleted_or_overshadowed():
    before = preview_change(state(), add(200_000), rules())['after']
    before['allocations'][0]['issued_atoms'] = 150_000; before['issued_atoms'] = 150_000
    for change in [{'kind': 'set_budget', 'total_atoms': 100_000, 'reserve_floor_atoms': 0},
        {'kind': 'resize_allocation', 'allocation_id': 'proposed', 'atoms': 149_999},
        {'kind': 'cancel_allocation', 'allocation_id': 'proposed'}]:
        with pytest.raises(ApiError): preview_change(before, change, rules())
    result = preview_change(before, {'kind': 'resize_allocation', 'allocation_id': 'proposed', 'atoms': 150_000}, rules())
    assert result['after']['issued_atoms'] == 150_000


def test_missing_or_nonreconciling_projection_fails_closed():
    before = state(); before['allocated_atoms'] = 1
    with pytest.raises(ApiError): validate_snapshot(before)
    before = state(); before['issued_atoms'] = 1
    with pytest.raises(ApiError): validate_snapshot(before)


def test_cancelling_unissued_allocation_releases_only_planned_units():
    before = preview_change(state(), add(500_000), rules())['after']
    result = preview_change(before, {'kind': 'cancel_allocation', 'allocation_id': 'proposed'}, rules())
    assert result['after_totals']['allocated_atoms'] == 0
    assert result['after_totals']['available_atoms'] == 900_000
    assert result['after']['allocations'][0]['status'] == 'cancelled'


def test_randomized_integer_budget_bounds():
    # Deterministic generated cases, not a claim of proof or Hypothesis coverage.
    random = Random(307)
    for _ in range(300):
        total = random.randint(1, 10**12)
        reserve = random.randint(0, total)
        before = state(total, reserve)
        remaining = total - reserve
        if remaining:
            amount = random.randint(1, remaining)
            result = preview_change(before, add(amount), rules())
            assert result['after_totals']['available_atoms'] == remaining - amount
            assert result['after_totals']['allocated_atoms'] + result['after_totals']['unassigned_atoms'] == total
        with pytest.raises(ApiError): preview_change(before, add(remaining + 1), rules())
