"""Pure deterministic allocation. Never reads a database or writes an obligation.

Amounts are integer cents, weights are integer atoms/basis points. Hamilton
(largest-remainder) rounding is applied first to pools, then within each pool.
Equal remainders use ascending immutable ASCII keys, never names or input order.
This method is not guaranteed to be monotone when the total/weights change.
"""
from typing import Any
import re

ENGINE_VERSION = 'largest-remainder-v1'
MAX_CENTS = 1_000_000_000_000
MAX_SAFE_INTEGER = 9_007_199_254_740_991
_KEY = re.compile(r'^[a-z0-9][a-z0-9_-]{0,79}$')


def integer(value: Any, name: str, maximum: int = MAX_SAFE_INTEGER) -> int:
    if type(value) is not int or not 0 <= value <= maximum:
        raise ValueError(f'{name} must be a nonnegative integer no greater than {maximum}.')
    return value


def key(value: Any) -> str:
    if not isinstance(value, str) or not _KEY.fullmatch(value):
        raise ValueError('Use stable lowercase ASCII identifiers, not display names, for rounding.')
    return value


def largest_remainder(total: int, weighted_keys: list[tuple[str, int]]) -> list[dict]:
    """Allocate exactly total, exposing exact quotients and remainder evidence.

    A zero denominator is an error even if total is zero; the caller must label
    empty pools explicitly. Zero weights are retained but never receive cents.
    """
    integer(total, 'total', MAX_CENTS)
    if not weighted_keys or len(weighted_keys) > 10000:
        raise ValueError('Supply between one and 10,000 recipients.')
    items = [(key(k), integer(weight, 'weight')) for k, weight in weighted_keys]
    if len({k for k, _ in items}) != len(items):
        raise ValueError('Duplicate recipient identifier.')
    denominator = integer(sum(weight for _, weight in items), 'total weight')
    if denominator == 0:
        raise ValueError('A zero denominator cannot define allocation shares.')
    rows = []
    for recipient_id, weight in sorted(items):
        floor, remainder = divmod(total * weight, denominator)
        rows.append({'key': recipient_id, 'weight': weight, 'denominator': denominator,
                     'floor_cents': floor, 'remainder_numerator': remainder,
                     'rounding_cent': 0, 'amount_cents': floor})
    left = total - sum(row['floor_cents'] for row in rows)
    ranked = sorted((row for row in rows if row['weight']),
                    key=lambda row: (-row['remainder_numerator'], row['key']))
    for row in ranked[:left]:
        row['rounding_cent'] = 1
        row['amount_cents'] += 1
    assert sum(row['amount_cents'] for row in rows) == total
    return rows


def distribute(amount_cents: int, pools: list[dict]) -> dict:
    """Calculate a non-payable scenario from already scoped recognized credit.

    Expected pool fields: key, weight_bps, recipients [{user_id, atoms}],
    blocked_by_dispute (strict bool). Person display names are not calculation
    inputs. A blocked pool keeps its own hypothetical cents unallocated; it is
    never renormalized into the other pools or handed to the project owner.
    """
    integer(amount_cents, 'amount_cents', MAX_CENTS)
    if not pools or len(pools) > 2:
        raise ValueError('Supply one or two explicit contribution pools.')
    if len({pool['key'] for pool in pools}) != len(pools):
        raise ValueError('Duplicate contribution pool.')
    for pool in pools:
        if pool['key'] not in {'release', 'ongoing'}:
            raise ValueError('Unknown contribution pool.')
        if not 1 <= integer(pool['weight_bps'], 'pool weight', 10000) <= 10000:
            raise ValueError('Pool weights must be positive.')
        if type(pool.get('blocked_by_dispute', False)) is not bool:
            raise ValueError('Dispute status must be boolean.')
        recipients = pool['recipients']
        if not isinstance(recipients, list) or len(recipients) > 10000:
            raise ValueError('Too many recipients.')
        ids = [key(row['user_id']) for row in recipients]
        if len(set(ids)) != len(ids):
            raise ValueError('Combine each contributor once within their pool.')
        for row in recipients:
            integer(row['atoms'], 'contributor atoms')
        integer(sum(row['atoms'] for row in recipients), 'pool denominator')
    if sum(pool['weight_bps'] for pool in pools) != 10000:
        raise ValueError('Pool weights must total exactly 10,000 basis points.')
    pool_rounding = {row['key']: row for row in largest_remainder(
        amount_cents, [(pool['key'], pool['weight_bps']) for pool in pools])}
    output = []
    totals: dict[str, int] = {}
    for pool in sorted(pools, key=lambda p: p['key']):
        split = pool_rounding[pool['key']]
        denominator = sum(row['atoms'] for row in pool['recipients'])
        blockers = []
        if pool.get('blocked_by_dispute', False):
            blockers.append('unresolved_dispute')
        if denominator == 0:
            blockers.append('empty_pool')
        allocations = []
        if not blockers:
            allocations = largest_remainder(split['amount_cents'],
                [(row['user_id'], row['atoms']) for row in pool['recipients']])
            for line in allocations:
                totals[line['key']] = totals.get(line['key'], 0) + line['amount_cents']
        output.append({'key': pool['key'], 'weight_bps': pool['weight_bps'],
                       'pool_rounding': split, 'denominator_atoms': denominator,
                       'amount_cents': split['amount_cents'], 'blockers': blockers,
                       'status': 'blocked' if blockers else 'calculated',
                       'unallocated_cents': split['amount_cents'] if blockers else 0,
                       'allocations': allocations})
    unallocated = sum(pool['unallocated_cents'] for pool in output)
    people = [{'user_id': uid, 'amount_cents': cents} for uid, cents in sorted(totals.items())]
    assert sum(person['amount_cents'] for person in people) + unallocated == amount_cents
    return {'engine_version': ENGINE_VERSION, 'currency': 'USD', 'hypothetical': True,
            'payable': False, 'amount_cents': amount_cents, 'pools': output,
            'people': people, 'allocated_cents': amount_cents - unallocated,
            'unallocated_cents': unallocated,
            'status': 'blocked' if any(pool['blockers'] for pool in output) else 'calculated'}
