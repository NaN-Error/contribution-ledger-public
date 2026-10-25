from copy import deepcopy
from datetime import datetime
import pytest
from pydantic import ValidationError
from app.policies.schemas import PolicyRules, PolicyApprove, PolicyAcknowledge
from app.policies.templates import templates
from app.contributions.budgets.schemas import MilestoneCreate, AmendmentCreate


def example(): return deepcopy(templates('America/Puerto_Rico')[1]['rules'])


@pytest.mark.parametrize('key', [0, 1])
def test_templates_are_valid_examples_only(key):
    item = templates('America/Puerto_Rico')[key]
    assert item['example_only'] is True
    rules = PolicyRules.model_validate(item['rules'])
    assert sum(p.weight_bps for p in rules.pools) == 10000
    assert rules.unit_scale == 1000


@pytest.mark.parametrize('field,value', [
    ('currency', 'EUR'), ('timezone', 'Not/A_Timezone'), ('timezone', '../etc/passwd'),
    ('unit_scale', 100), ('schema_version', 2), ('eligible_categories', []),
    ('eligible_categories', ['code', 'code']), ('eligible_categories', ['number_of_commits']),
    ('unissued_units', 'give_to_owner'), ('departure_rule', '   '), ('attribution_rule', 'count LOC')])
def test_invalid_policy_fields_rejected(field, value):
    item = example(); item[field] = value
    with pytest.raises(ValidationError): PolicyRules.model_validate(item)


@pytest.mark.parametrize('weights', [[7000, 2000], [10000, 1], [-1, 10001], [0, 10000], ['7000', 3000], [7000.0, 3000], [True, 9999]])
def test_pool_weights_are_exact_strict_and_sum_to_100_percent(weights):
    item = example()
    for pool, amount in zip(item['pools'], weights): pool['weight_bps'] = amount
    with pytest.raises(ValidationError): PolicyRules.model_validate(item)


def test_duplicate_pool_and_wrong_eligibility_rejected():
    item = example(); item['pools'][1]['key'] = 'release'
    with pytest.raises(ValidationError): PolicyRules.model_validate(item)
    item = example(); item['pools'][0]['eligibility'] = 'accepted_work_in_accounting_period'
    with pytest.raises(ValidationError): PolicyRules.model_validate(item)


@pytest.mark.parametrize('field,value', [('start_day', 2), ('boundary_time', '12:00:00'),
    ('boundary_resolution', 'guess_a_time'), ('cadence', 'some_months'), ('dispute_rule', 'ignore'),
    ('empty_pool_rule', 'pay_owner'), ('allowed_deductions', ['platform_fees']),
    ('allowed_deductions', ['hosting', 'hosting']), ('expense_approval', 'anyone')])
def test_ambiguous_or_unsafe_accounting_rules_rejected(field, value):
    item = example(); item['accounting'][field] = value
    with pytest.raises(ValidationError): PolicyRules.model_validate(item)


@pytest.mark.parametrize('effective', ['2026-10-01T12:00:00', 'not-a-date'])
def test_approval_time_must_be_offset_aware(effective):
    with pytest.raises(ValidationError): PolicyApprove.model_validate({'reviewed_content_hash': 'a'*64,
        'expected_latest_version': 1, 'examples_reviewed': True, 'reason': 'Reviewed synthetic rules', 'effective_at': effective})


def test_approval_normalizes_offset_and_needs_explicit_review():
    item = {'reviewed_content_hash': 'a'*64, 'expected_latest_version': 1,
        'examples_reviewed': True, 'reason': 'Reviewed synthetic rules', 'effective_at': '2030-01-01T12:00:00-04:00'}
    assert PolicyApprove.model_validate(item).effective_at.hour == 16
    item['examples_reviewed'] = False
    with pytest.raises(ValidationError): PolicyApprove.model_validate(item)


@pytest.mark.parametrize('amount', [-1, 1.5, 1000.0, '1000', True, 1_000_000_000_001])
def test_api_rejects_ambiguous_or_out_of_range_unit_amounts(amount):
    with pytest.raises(ValidationError): AmendmentCreate.model_validate({'expected_version': 1,
        'change': {'kind': 'allocate', 'title': 'Valid outcome', 'category': 'code', 'pool_key': 'release', 'atoms': amount},
        'reason': 'Synthetic testing for unit precision'})


def test_unknown_fields_cannot_turn_budget_into_award():
    with pytest.raises(ValidationError): AmendmentCreate.model_validate({'expected_version': 1,
        'change': {'kind': 'allocate', 'title': 'Useful work', 'category': 'code', 'pool_key': 'release',
                   'atoms': 1000, 'user_id': 'someone', 'issued_atoms': 1000}, 'reason': 'Invalid award attempt'})


@pytest.mark.parametrize('field,bad', [('schema_version', True), ('schema_version', 1.0), ('unit_scale', 1000.0)])
def test_fixed_integer_literals_cannot_coerce_numbers(field, bad):
    item = example(); item[field] = bad
    with pytest.raises(ValidationError): PolicyRules.model_validate(item)


@pytest.mark.parametrize('bad', [1, 'true', '1', False])
def test_review_confirmation_requires_an_actual_true_boolean(bad):
    with pytest.raises(ValidationError): PolicyAcknowledge.model_validate({'reviewed_content_hash': 'a'*64, 'reviewed': bad})


def test_start_day_cannot_coerce_boolean():
    item = example(); item['accounting']['start_day'] = True
    with pytest.raises(ValidationError): PolicyRules.model_validate(item)


@pytest.mark.parametrize('value', [2000000000, '2000000000', True, '2030-01-01 12:00:00Z'])
def test_effective_time_does_not_infer_a_format_or_epoch(value):
    with pytest.raises(ValidationError): PolicyApprove.model_validate({
        'reviewed_content_hash': 'a'*64, 'expected_latest_version': 1,
        'examples_reviewed': True, 'reason': 'Synthetic offset-aware review', 'effective_at': value})
