"""Keep release routing usable without collapsing honest verification states."""
import json
import pytest
from tests.test_candidate_tools import ROOT, tool


def backlog():
    return json.loads((ROOT / 'docs/backlog.json').read_text(encoding='utf-8'))


def test_current_backlog_declares_all_statuses_and_routes_to_release_verification():
    data = backlog()
    tool('verify_backlog').verify_backlog(data)
    assert data['current_phase'] == 'P17' and data['next_batch'] == 'P17C'
    assert data['phases'][14]['batches'][2]['status'] == 'observation_tools_prepared_human_pilot_not_started'


@pytest.mark.parametrize('change', [
    lambda data: data.update(next_batch='P15A'),
    lambda data: data['phases'][-1].update(status='undeclared'),
    lambda data: data['phases'][-1]['batches'][0].update(status='undeclared'),
    lambda data: data.update(batch_count=999),
    lambda data: data['phases'][-1]['batches'].append(data['phases'][-1]['batches'][0]),
    lambda data: data['phases'][0].update(depends_on=['P16']),
])
def test_inconsistent_backlog_is_rejected(change):
    data = backlog()
    change(data)
    with pytest.raises(AssertionError):
        tool('verify_backlog').verify_backlog(data)
