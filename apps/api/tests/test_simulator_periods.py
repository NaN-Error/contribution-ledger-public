from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import pytest
from app.finance.calculation.periods import month_bounds, boundary


def test_puerto_rico_month_uses_four_hour_utc_offset():
    start,end=month_bounds('2026-09','America/Puerto_Rico')
    assert start.isoformat()=='2026-09-01T04:00:00+00:00'
    assert end.isoformat()=='2026-10-01T04:00:00+00:00'


def test_dst_month_is_not_assumed_fixed_hours():
    start,end=month_bounds('2026-03','America/New_York')
    assert (end-start).total_seconds()==(31*24-1)*3600


def test_december_rollover_and_leap_year():
    assert month_bounds('2026-12','UTC')[1].isoformat()=='2027-01-01T00:00:00+00:00'
    a,b=month_bounds('2024-02','UTC');assert (b-a).days==29


@pytest.mark.parametrize('date', [datetime(2026,3,8,2,30),datetime(2026,11,1,1,30)])
def test_ambiguous_or_nonexistent_wall_time_rejected(date):
    with pytest.raises(ValueError,match='ambiguous or nonexistent'):boundary(date,ZoneInfo('America/New_York'))


@pytest.mark.parametrize('month', ['2026-9','2026-00','2026-13','1999-01','9999-01','2026-01-01','',None])
def test_invalid_month(month):
    with pytest.raises(ValueError):month_bounds(month,'UTC')


def test_bad_timezone_and_aware_boundary_rejected():
    with pytest.raises(ValueError):month_bounds('2026-09','../invalid')
    with pytest.raises(ValueError):boundary(datetime.now(timezone.utc),ZoneInfo('UTC'))


@pytest.mark.parametrize('pool,accepted,expected', [
    ('release','2026-08-31T23:59:59+00:00',True),
    ('ongoing','2026-08-31T23:59:59+00:00',False),
    ('ongoing','2026-09-01T00:00:00+00:00',True),
    ('release','2026-09-30T23:59:59+00:00',True),
    ('ongoing','2026-09-30T23:59:59+00:00',True),
    ('ongoing','2026-10-01T00:00:00+00:00',False),
    ('release','2026-10-01T00:00:00+00:00',False),
])
def test_original_acceptance_date_eligibility(pool,accepted,expected):
    from app.finance.calculation.periods import award_eligible
    start,end=month_bounds('2026-09','UTC')
    assert award_eligible(pool,datetime.fromisoformat(accepted),start,end,end)==expected


def test_unaccepted_future_credit_and_naive_instants_rejected():
    from app.finance.calculation.periods import award_eligible
    start,end=month_bounds('2026-09','UTC')
    assert not award_eligible('release',end.replace(day=1),start,end,start)
    with pytest.raises(ValueError):award_eligible('release',datetime(2026,9,1),start,end,end)
