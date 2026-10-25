"""Calendar-month boundaries with exact IANA local-time validation."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import re


def boundary(local: datetime, zone: ZoneInfo) -> datetime:
    if local.tzinfo is not None:
        raise ValueError('Boundary input must be a naive local wall time.')
    candidates = set()
    for fold in (0, 1):
        instant = local.replace(tzinfo=zone, fold=fold).astimezone(timezone.utc)
        if instant.astimezone(zone).replace(tzinfo=None) == local:
            candidates.add(instant)
    if len(candidates) != 1:
        raise ValueError('The local accounting boundary is ambiguous or nonexistent; select a reviewed policy with an unambiguous timezone.')
    return candidates.pop()


def month_bounds(month: str, timezone_name: str) -> tuple[datetime, datetime]:
    if not isinstance(month, str) or not re.fullmatch(r'\d{4}-(?:0[1-9]|1[0-2])', month):
        raise ValueError('Use a calendar month in YYYY-MM format.')
    year, number = map(int, month.split('-'))
    if not 2000 <= year <= 9998:
        raise ValueError('The supported accounting year is 2000 through 9998.')
    try:
        zone = ZoneInfo(timezone_name)
    except (ValueError, ZoneInfoNotFoundError) as error:
        raise ValueError('Use a supported IANA timezone.') from error
    start = datetime(year, number, 1)
    end = datetime(year + 1, 1, 1) if number == 12 else datetime(year, number + 1, 1)
    return boundary(start, zone), boundary(end, zone)


def award_eligible(pool_key: str, accepted_at: datetime, start: datetime, end: datetime, captured_at: datetime) -> bool:
    """No predicted future awards; ongoing eligibility never moves with a correction."""
    if pool_key not in {'release', 'ongoing'}:
        raise ValueError('Unknown award pool.')
    for instant in (accepted_at, start, end, captured_at):
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise ValueError('Eligibility requires timezone-aware instants.')
    return accepted_at < end and accepted_at <= captured_at and (pool_key == 'release' or accepted_at >= start)
