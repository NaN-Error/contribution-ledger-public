"""Exact cash waterfall. Reserve is unallocated cash, not contributor ownership."""
from app.finance.calculation.engine import MAX_CENTS

POSITIVE = {'receipt', 'adjustment_credit', 'reserve_release'}
NEGATIVE = {'deduction', 'adjustment_debit', 'reserve_hold'}


def cash_waterfall(entries: list[dict], opening_reserve: int = 0, opening_deficit: int = 0) -> dict:
    if type(opening_reserve) is not int or not 0 <= opening_reserve <= MAX_CENTS:
        raise ValueError('Invalid opening reserve.')
    if type(opening_deficit) is not int or not -MAX_CENTS <= opening_deficit <= 0:
        raise ValueError('Invalid carried deficit.')
    sums = {key: 0 for key in sorted(POSITIVE | NEGATIVE)}
    for item in entries:
        cents = item['amount_cents']; kind = item['kind']
        if kind not in sums or type(cents) is not int or not 1 <= cents <= MAX_CENTS:
            raise ValueError('Invalid financial entry.')
        sums[kind] += cents
        if sums[kind] > MAX_CENTS:
            raise ValueError('Aggregate cash entries exceed the supported exact range.')
    reserve = opening_reserve + sums['reserve_hold'] - sums['reserve_release']
    net = opening_deficit + sum(sums[k] for k in POSITIVE) - sum(sums[k] for k in NEGATIVE)
    blockers = []
    if reserve < 0: blockers.append('reserve_overdrawn')
    if reserve > MAX_CENTS or not -MAX_CENTS <= net <= MAX_CENTS:
        raise ValueError('Aggregate cash balances exceed the supported exact range.')
    # Do not create reserve while the waterfall still has an unfunded deficit.
    if sums['reserve_hold'] > sums['reserve_release'] and net < 0:
        blockers.append('unfunded_reserve_hold')
    return {'currency': 'USD', 'opening_reserve_cents': opening_reserve,
        'opening_deficit_cents': opening_deficit, 'entries_by_kind_cents': sums,
        'net_cents': net, 'distributable_cents': max(0, net),
        'closing_deficit_cents': min(0, net), 'closing_reserve_cents': reserve,
        'blockers': blockers}
