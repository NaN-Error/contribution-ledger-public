"""Pure planning arithmetic. Fractions are integer ratios, never personal entitlements."""
from copy import deepcopy
from app.core.errors import ApiError
from app.policies.schemas import MAX_ATOMS


def invalid(code: str, detail: str):
    return ApiError(409, code, detail)


def validate_snapshot(state: dict) -> None:
    totals = [state[k] for k in ('total_atoms', 'reserve_floor_atoms', 'allocated_atoms', 'issued_atoms')]
    if any(type(v) is not int or not 0 <= v <= MAX_ATOMS for v in totals):
        raise invalid('invalid_budget', 'Budget amounts must be bounded, nonnegative integer unit atoms.')
    total, reserve, allocated, issued = totals
    if allocated + reserve > total:
        raise invalid('budget_exceeded', 'Assigned budgets plus protected reserve would exceed the milestone total.')
    if issued > allocated:
        raise invalid('issued_budget_bound', 'The new budget would be below already-issued units.')
    if state['status'] == 'draft' and any(totals):
        raise invalid('invalid_budget_state', 'Unapproved milestones cannot hold an active budget.')
    rows = state['allocations']
    if len({r['id'] for r in rows}) != len(rows):
        raise invalid('invalid_projection', 'Duplicate allocation in the budget projection.')
    for r in rows:
        if any(type(r[k]) is not int or not 0 <= r[k] <= MAX_ATOMS for k in ('atoms', 'issued_atoms')):
            raise invalid('invalid_budget', 'Allocation amounts must use bounded integer atoms.')
        if r['issued_atoms'] > r['atoms'] or (r['status'] == 'cancelled' and (r['atoms'] or r['issued_atoms'])):
            raise invalid('issued_budget_bound', 'Allocated budgets cannot erase already-issued units.')
    if sum(r['atoms'] for r in rows) != allocated or sum(r['issued_atoms'] for r in rows) != issued:
        raise invalid('invalid_projection', 'Budget projections do not reconcile. Stop and investigate before changing this milestone.')


def totals_view(state: dict) -> dict:
    return {**{k: state[k] for k in ('total_atoms', 'reserve_floor_atoms', 'allocated_atoms', 'issued_atoms')},
        'unassigned_atoms': state['total_atoms'] - state['allocated_atoms'],
        'available_atoms': state['total_atoms'] - state['allocated_atoms'] - state['reserve_floor_atoms'],
        'unissued_atoms': state['total_atoms'] - state['issued_atoms']}


def preview_change(before: dict, change: dict, rules: dict) -> dict:
    """Preview a change with deterministic IDs. Its eventual database ID is in the proposal UUID."""
    validate_snapshot(before)
    after = deepcopy(before)
    kind = change['kind']
    if kind == 'initial_budget':
        if before['status'] != 'draft':
            raise invalid('already_budgeted', 'The initial budget is already active. Propose an amendment instead.')
        after.update(status='active', total_atoms=change['total_atoms'], reserve_floor_atoms=change['reserve_floor_atoms'])
    else:
        if before['status'] != 'active':
            raise invalid('initial_budget_required', 'Approve an initial budget before allocating or amending it.')
        if kind == 'set_budget':
            after.update(total_atoms=change['total_atoms'], reserve_floor_atoms=change['reserve_floor_atoms'])
        elif kind == 'allocate':
            if change['category'] not in rules['eligible_categories']:
                raise invalid('category_not_eligible', 'This category is not eligible under the pinned policy.')
            if change['pool_key'] not in {p['key'] for p in rules['pools']}:
                raise invalid('pool_not_eligible', 'The allocation must use a pool defined in the pinned policy.')
            after['allocations'].append({'id': 'proposed', 'title': change['title'], 'category': change['category'],
                'pool_key': change['pool_key'], 'atoms': change['atoms'], 'issued_atoms': 0,
                'status': 'active', 'version': 1})
        elif kind in {'resize_allocation', 'cancel_allocation'}:
            row = next((r for r in after['allocations'] if r['id'] == change['allocation_id']), None)
            if row is None:
                # Do not reveal whether an ID exists in another project/milestone.
                raise ApiError(404, 'not_found', 'This allocation is not available in the requested milestone.')
            if row['status'] != 'active':
                raise invalid('allocation_cancelled', 'A cancelled allocation cannot be changed or reinstated.')
            if kind == 'cancel_allocation':
                if row['issued_atoms']:
                    raise invalid('issued_allocation', 'An allocation with finalized credit cannot be cancelled.')
                row.update(atoms=0, status='cancelled')
            else:
                if change['atoms'] < row['issued_atoms']:
                    raise invalid('issued_budget_bound', 'An allocation cannot be reduced below its issued units.')
                row['atoms'] = change['atoms']
            row['version'] += 1
        else:
            raise invalid('unsupported_change', 'This type of budget amendment is not supported.')
    after['allocated_atoms'] = sum(r['atoms'] for r in after['allocations'])
    after['issued_atoms'] = sum(r['issued_atoms'] for r in after['allocations'])
    after['version'] += 1
    after['allocations'].sort(key=lambda r: r['id'])
    validate_snapshot(after)
    if after['total_atoms'] < before['issued_atoms']:
        raise invalid('issued_budget_bound', 'A milestone total cannot fall below its issued units.')
    previous = {r['id']: r for r in before['allocations']}
    shares = []
    for row in after['allocations']:
        old = previous.get(row['id'])
        shares.append({'allocation_id': row['id'], 'title': row['title'], 'pool_key': row['pool_key'],
            'before': {'numerator_atoms': old['atoms'] if old else 0, 'denominator_atoms': before['total_atoms']},
            'after': {'numerator_atoms': row['atoms'], 'denominator_atoms': after['total_atoms']}})
    return {'before': before, 'after': after, 'before_totals': totals_view(before), 'after_totals': totals_view(after),
        'planned_budget_shares': shares,
        'personal_share_notice': 'These ratios describe planned allocation budgets within this milestone, not any person\'s earned share. Unissued reserve belongs to nobody.',
        'credit_effect': 'No contribution units are issued by this budget change.'}
