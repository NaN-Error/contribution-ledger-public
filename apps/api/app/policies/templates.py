"""Draft examples only. No template is active or agreed to by default."""
from app.policies.schemas import CATEGORIES, PolicyRules


def templates(timezone: str) -> list[dict]:
    rules = {
        'schema_version': 1, 'currency': 'USD', 'timezone': timezone, 'unit_scale': 1000,
        'eligible_categories': CATEGORIES,
        'review': {'minimum_independent_reviewers': 1, 'beneficiary_cannot_be_sole_approver': True,
                   'acceptance': 'budgeted_deliverables_only'},
        'governance': {'policy_approval': 'project_admin', 'budget_approval': 'project_admin',
                      'acknowledgement': 'snapshot_and_current_non_viewer_participants'},
        'pools': [{'key': 'release', 'weight_bps': 10000, 'eligibility': 'accepted_release_work'}],
        'accounting': {
            'cadence': 'calendar_month', 'start_day': 1, 'boundary_time': '00:00:00',
            'boundary_resolution': 'reject_ambiguous_or_nonexistent_local_time',
            'revenue_basis': 'net_storefront_settlements',
            'allowed_deductions': ['hosting', 'tools', 'approved_external_services'],
            'distributable_definition': 'Example only: documented net receipts less explicitly approved, not-already-deducted expenses and agreed reserves.',
            'expense_approval': 'documented_project_admin_approval',
            'reserve_rule': 'Example only: no cash reserve unless separately documented and approved before the period closes.',
            'capital_repayment_rule': 'Example only: no priority capital repayment without an explicit prospective agreement.',
            'empty_pool_rule': 'block_close', 'dispute_rule': 'block_affected_close'},
        'departure_rule': 'Example only: departure preserves previously finalized credit; any duration or buyout requires a separate agreement.',
        'attribution_rule': 'Example only: recognized units follow human acceptance of useful outcomes, including non-code evidence, not activity volume.',
        'unissued_units': 'unowned_until_accepted',
    }
    release = PolicyRules.model_validate(rules).model_dump(mode='json')
    mixed = PolicyRules.model_validate({**release, 'pools': [
        {'key': 'release', 'weight_bps': 7000, 'eligibility': 'accepted_release_work'},
        {'key': 'ongoing', 'weight_bps': 3000, 'eligibility': 'accepted_work_in_accounting_period'}]}).model_dump(mode='json')
    return [
        {'key': 'release_only', 'title': 'Release-only draft example', 'example_only': True, 'rules': release},
        {'key': 'release_and_ongoing', 'title': 'Release and ongoing draft example', 'example_only': True, 'rules': mixed},
    ]
