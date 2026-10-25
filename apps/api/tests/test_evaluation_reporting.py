import copy
import json
from pathlib import Path
import pytest
from app.ai.assessments.prompt import generation_material
from app.evaluation.corpus import CorpusError, load_corpus
from app.evaluation.report import mock_predictions, score, validate_predictions, markdown

ROOT=Path(__file__).resolve().parents[3]


@pytest.fixture
def example():
    cases,meta=load_corpus(ROOT/'evals')
    # Whole first family preserves sensitivity pair semantics.
    cases=cases[:7]
    return cases,meta,mock_predictions(cases)


def test_actual_mock_results_do_not_claim_quality_or_pilot(example):
    cases,meta,rows=example; report=score(cases,meta,rows)
    assert report['valid_output_coverage']['rate']==1
    assert report['agreement_with_allowed_synthetic_labels']['rate']==pytest.approx(1/3)
    assert report['provisional_regression_pass'] is False
    assert report['real_model_quality_evaluated'] is False
    assert report['human_pilot_periods_completed']==0
    assert report['release_authorized'] is False
    assert report['latency_ms']['median'] is None
    assert report['token_usage']['input_tokens']['unknown']==7
    assert report['cost_micro_usd']['known_total']=='0'
    assert all(v['changed_pair_rate']['rate']==0 for v in report['sensitivity'].values())


def test_mock_receives_no_reference_or_expected_labels(example,monkeypatch):
    from app.providers.mock import MockProvider
    original=MockProvider.generate; seen=[]
    def capture(self, credential, request):
        value=json.loads(request.prompt)
        assert set(value)=={'untrusted_evidence_packet'}
        assert 'reference' not in value['untrusted_evidence_packet']
        assert 'allowed_statuses' not in request.prompt
        assert 'synthetic_author_expectation' not in request.prompt
        assert credential==''
        seen.append(1);return original(self,credential,request)
    monkeypatch.setattr(MockProvider,'generate',capture)
    assert len(mock_predictions(example[0]))==7 and len(seen)==7


def test_output_schema_cannot_issue_credit(example):
    cases,meta,rows=example
    data=json.loads(rows[0]['content']);data['ownership_percentage']=100
    rows[0]['content']=json.dumps(data)
    result=score(cases,meta,rows)
    assert result['cases'][0]['outcome']=='invalid'
    assert result['valid_output_coverage']['numerator']==6
    assert result['release_authorized'] is False
    assert 'ownership_percentage' not in json.dumps(result)


@pytest.mark.parametrize('change',[
    lambda r:r.update(case_id='unknown'),lambda r:r.update(packet_fingerprint='wrong'),
    lambda r:r.update(prompt_fingerprint='wrong'),lambda r:r.update(profile_fingerprint='wrong'),
    lambda r:r.update(provider='https://untrusted.test'),lambda r:r.update(requested_model='../escape'),
    lambda r:r.update(origin='verified_provider'),lambda r:r.update(finish=[]),
    lambda r:r.update(cost_micro_usd=-1),lambda r:r.update(cost_micro_usd='1.5'),
    lambda r:r.update(cost_micro_usd='00'),lambda r:r.update(latency_ms=True),
    lambda r:r.update(input_tokens=-5),lambda r:r.update(content='x'*65537),
    lambda r:r.update(secret='never accepted'),lambda r:r.update(returned_model='https://secret.test'),
])
def test_reject_invalid_prediction_envelope(example,change):
    cases,_,rows=example;change(rows[0])
    with pytest.raises(CorpusError):validate_predictions(rows,cases)


def test_duplicate_row_rejected(example):
    cases,_,rows=example;rows[1]=copy.deepcopy(rows[0])
    with pytest.raises(CorpusError,match='duplicate'):validate_predictions(rows,cases)


def test_mixed_requested_evaluator_cannot_hide_in_aggregate(example):
    cases,_,rows=example
    rows[0].update(origin='offline_operator_supplied',provider='example',requested_model='model-a')
    with pytest.raises(CorpusError,match='mixed_evaluators'):validate_predictions(rows,cases)


def test_missing_predictions_not_dropped_from_denominator(example):
    cases,meta,rows=example
    report=score(cases,meta,rows[:1])
    assert report['missing_predictions']==6
    assert report['prediction_coverage']['denominator']==7
    assert report['full_case_agreement']['denominator']==7
    assert report['criterion_coverage']['denominator']==21
    assert sum(x.get('unscored_pairs',0) for x in report['sensitivity'].values())==6


def test_zero_predictions_are_unknown_not_perfect(example):
    cases,meta,_=example; report=score(cases,meta,[])
    assert report['agreement_with_allowed_synthetic_labels']['rate'] is None
    assert report['invalid_output_rate']['rate'] is None
    assert report['provisional_regression_pass'] is False


@pytest.mark.parametrize('finish',['timeout','refused','truncated','model_unavailable','failure'])
def test_failed_generation_remains_visible(example,finish):
    cases,meta,rows=example; rows[0].update(finish=finish,content=None)
    report=score(cases,meta,rows)
    assert report['generation_failure_rate']['numerator']==1
    assert report['valid_output_coverage']['numerator']==6


def test_invalid_references_not_scored_as_truth(example):
    cases,meta,rows=example
    value=json.loads(rows[0]['content']);value['findings'][0].update(status='supported',evidence_refs=[{'source_id':'E99','start_line':1,'end_line':1}])
    rows[0]['content']=json.dumps(value)
    report=score(cases,meta,rows)
    assert report['invalid_output_rate']['numerator']==1
    assert report['criterion_coverage']['numerator']==18


def test_false_support_is_reported_against_synthetic_reference(example):
    cases,meta,rows=example
    value=json.loads(rows[0]['content']);value['findings'][1].update(status='supported',evidence_refs=[{'source_id':'E1','start_line':2,'end_line':2}])
    rows[0]['content']=json.dumps(value);report=score(cases,meta,rows)
    assert report['supported_predictions_not_allowed_by_reference']=={'numerator':1,'denominator':1,'rate':1.0}
    assert report['sensitivity']['source_order']['changed_pairs']==1


def test_retired_or_changed_returned_model_remains_visible(example):
    cases,meta,rows=example
    for row in rows:row.update(origin='offline_operator_supplied',provider='example',requested_model='alias')
    rows[0]['returned_model']='older-snapshot'
    report=score(cases,meta,rows)
    assert report['mixed_returned_models'] is True
    assert report['provisional_regression_checks']['stable_single_returned_model'] is False


def test_unknown_cost_not_zero_and_integer_cost_sum(example):
    cases,meta,rows=example
    for row in rows:row.update(origin='offline_operator_supplied',provider='example',cost_micro_usd=None)
    rows[0]['cost_micro_usd']='123456789012345678'
    rows[1]['cost_micro_usd']='1'
    report=score(cases,meta,rows)
    assert report['cost_micro_usd']['known_total']=='123456789012345679'
    assert report['cost_micro_usd']['unknown']==5


def test_report_omits_raw_private_model_prose(example):
    cases,meta,rows=example;value=json.loads(rows[0]['content'])
    value['summary']='PRIVATE_EXAMPLE_NOT_FOR_REPORT_CONTENT';rows[0]['content']=json.dumps(value)
    report=score(cases,meta,rows)
    assert 'PRIVATE_EXAMPLE' not in json.dumps(report)
    assert 'PRIVATE_EXAMPLE' not in markdown(report)


def test_ambiguous_references_do_not_enter_single_label_confusion():
    cases,meta=load_corpus(ROOT/'evals');cases=[c for c in cases if c['family']=='ai_assisted']
    report=score(cases,meta,mock_predictions(cases))
    assert report['ambiguous_reference_criteria_scored']==7
    assert sum(sum(r.values()) for r in report['confusion_single_label_only'].values())==14


def test_reports_are_deterministic_for_same_inputs(example):
    cases,meta,rows=example
    assert score(cases,meta,rows)==score(copy.deepcopy(cases),copy.deepcopy(meta),copy.deepcopy(rows))
