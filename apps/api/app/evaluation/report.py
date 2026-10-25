"""Score bounded offline predictions against explicitly synthetic expectations.

No API credential, URL, arbitrary code, database session, or payment interface is
accepted. Result reports contain identifiers/counts, never raw submitted prose.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from statistics import median
from typing import Any

from app.ai.assessments.prompt import generation_material, prompt_hash
from app.ai.validation.output import InvalidAssessment, validate_output
from app.providers.contracts import GenerationRequest
from app.providers.mock import MockProvider
from app.evaluation.corpus import CorpusError, canonical, fingerprint

REPORT_VERSION = 'offline-evaluation-report-v1'
LABELS = ('supported', 'contradicted', 'insufficient')
FINISHES = frozenset({'complete', 'timeout', 'refused', 'truncated', 'model_unavailable', 'failure'})


def fraction(numerator: int, denominator: int) -> dict:
    return {'numerator': numerator, 'denominator': denominator,
            'rate': numerator / denominator if denominator else None}


def _identifier(value: Any, max_length: int = 200) -> bool:
    return isinstance(value, str) and 1 <= len(value) <= max_length and bool(
        re.fullmatch(r'[A-Za-z0-9_.:/-]+', value)) and '://' not in value and '..' not in value


def validate_predictions(rows: list[dict], cases: list[dict]) -> None:
    if not isinstance(rows, list) or len(rows) > len(cases):
        raise CorpusError('invalid_prediction_count')
    index = {c['id']: c for c in cases}
    seen = set()
    run_identity = None
    for row in rows:
        if not isinstance(row, dict) or set(row) != {
            'case_id', 'packet_fingerprint', 'prompt_fingerprint', 'provider', 'requested_model',
            'returned_model', 'profile_fingerprint', 'origin', 'finish', 'content',
            'latency_ms', 'cost_micro_usd', 'input_tokens', 'output_tokens'
        }:
            raise CorpusError('invalid_prediction_fields')
        case_id = row['case_id']
        if not isinstance(case_id, str) or case_id not in index or case_id in seen:
            raise CorpusError('unknown_or_duplicate_prediction')
        seen.add(case_id)
        if row['packet_fingerprint'] != fingerprint(index[case_id]['packet']):
            raise CorpusError('wrong_prediction_packet')
        if row['prompt_fingerprint'] != prompt_hash(index[case_id]['packet']):
            raise CorpusError('wrong_prediction_prompt')
        if (not _identifier(row['provider']) or not _identifier(row['requested_model']) or
            (row['returned_model'] is not None and not _identifier(row['returned_model'])) or
            not isinstance(row['profile_fingerprint'], str) or
            not re.fullmatch(r'[a-f0-9]{64}', row['profile_fingerprint']) or
            not isinstance(row['origin'], str) or row['origin'] not in {'synthetic_mock', 'offline_operator_supplied'}):
            raise CorpusError('invalid_prediction_provenance')
        identity = (row['provider'], row['requested_model'], row['profile_fingerprint'], row['origin'])
        if run_identity is not None and run_identity != identity:
            raise CorpusError('mixed_evaluators_in_one_report')
        run_identity = identity
        if not isinstance(row['finish'], str) or row['finish'] not in FINISHES:
            raise CorpusError('invalid_finish')
        if row['content'] is not None and (not isinstance(row['content'], str) or
            len(row['content'].encode('utf-8')) > 65536):
            raise CorpusError('invalid_content_bound')
        for key in ('latency_ms', 'input_tokens', 'output_tokens'):
            value = row[key]
            if value is not None and (type(value) is not int or not 0 <= value <= 10**12):
                raise CorpusError('invalid_usage')
        cost = row['cost_micro_usd']
        if cost is not None and (not isinstance(cost, str) or not re.fullmatch(r'0|[1-9][0-9]{0,17}', cost)):
            raise CorpusError('invalid_cost')
        if row['origin'] == 'synthetic_mock' and (row['provider'] != 'mock' or
            row['requested_model'] != 'synthetic-json-v1' or cost != '0'):
            raise CorpusError('invalid_mock_provenance')


def mock_predictions(cases: list[dict]) -> list[dict]:
    """Invoke the actual no-network mock provider with ONLY the outgoing packet.

    References, tags and expected labels are never included in generation input.
    Mock byte-count estimates are not reported as real model token usage.
    """
    provider = MockProvider()
    profile = fingerprint({'provider': 'mock', 'model': 'synthetic-json-v1',
                           'purpose': 'offline-protocol-only', 'max_output_tokens': 8192})
    rows = []
    for case in cases:
        packet = case['packet']
        material = generation_material(packet)
        result = provider.generate('', GenerationRequest('synthetic-json-v1', material['prompt'],
            material['schema'], 8192, instructions=material['instructions']))
        rows.append({'case_id': case['id'], 'packet_fingerprint': fingerprint(packet),
            'prompt_fingerprint': prompt_hash(packet), 'provider': 'mock',
            'requested_model': 'synthetic-json-v1', 'returned_model': result.model,
            'profile_fingerprint': profile, 'origin': 'synthetic_mock', 'finish': result.finish,
            'content': result.content, 'latency_ms': None, 'cost_micro_usd': '0',
            'input_tokens': None, 'output_tokens': None})
    return rows


def score(cases: list[dict], metadata: dict, predictions: list[dict]) -> dict:
    validate_predictions(predictions, cases)
    by_id = {r['case_id']: r for r in predictions}
    confusion = {a: {b: 0 for b in LABELS} for a in LABELS}
    results = []
    totals: Counter = Counter()
    category_totals: dict[str, Counter] = {}
    returned_models: Counter = Counter()
    for case in cases:
        totals['criteria_expected'] += len(case['packet']['criteria'])
        totals['source_count'] += len(case['packet']['sources'])
        totals['omission_count'] += len(case['packet']['omissions'])
        totals['cases_with_omissions'] += bool(case['packet']['omissions'])
        row = by_id.get(case['id'])
        result = {'case_id': case['id'], 'family': case['family'], 'variant': case['variant'],
                  'category': case['category'], 'outcome': 'missing', 'statuses': {},
                  'agreed_criteria': 0, 'scored_criteria': 0, 'ambiguous_criteria': 0}
        if row is None:
            totals['missing'] += 1
        elif row['finish'] != 'complete':
            result['outcome'] = row['finish']
            totals['generation_failures'] += 1
        else:
            try:
                output = validate_output(row['content'], case['packet'])
            except InvalidAssessment as exc:
                result['outcome'] = 'invalid'
                result['failure_code'] = str(exc)
                totals['invalid'] += 1
            else:
                totals['valid'] += 1
                result['outcome'] = 'valid'
                result['statuses'] = {f['criterion_id']: f['status'] for f in output['findings']}
                for finding in output['findings']:
                    allowed = case['reference'][finding['criterion_id']]['allowed_statuses']
                    agreed = finding['status'] in allowed
                    result['agreed_criteria'] += int(agreed)
                    result['scored_criteria'] += 1
                    totals['agreed'] += agreed
                    totals['scored'] += 1
                    totals['predicted_supported'] += finding['status'] == 'supported'
                    totals['support_not_in_reference'] += finding['status'] == 'supported' and not agreed
                    if len(allowed) == 1:
                        confusion[allowed[0]][finding['status']] += 1
                    else:
                        result['ambiguous_criteria'] += 1
                        totals['ambiguous'] += 1
                totals['fully_agreed_cases'] += result['agreed_criteria'] == result['scored_criteria']
        if row is not None:
            if row['returned_model'] is not None:
                returned_models[row['returned_model']] += 1
            totals['missing_returned_model'] += row['returned_model'] is None
        group = category_totals.setdefault(case['category'], Counter())
        group['cases'] += 1
        group['valid'] += result['outcome'] == 'valid'
        group['agreed_criteria'] += result['agreed_criteria']
        group['scored_criteria'] += result['scored_criteria']
        results.append(result)
    precision_recall = {}
    for label in LABELS:
        tp = confusion[label][label]
        precision_recall[label] = {'precision_against_single_label_references': fraction(tp, sum(confusion[x][label] for x in LABELS)),
                                  'recall_against_single_label_references': fraction(tp, sum(confusion[label].values()))}
    bases = {r['family']: r for r in results if r['variant'] == 'baseline'}
    changes: dict[str, Counter] = {}
    for result in results:
        if result['variant'] == 'baseline':
            continue
        counts = changes.setdefault(result['variant'], Counter())
        counts['expected_pairs'] += 1
        base = bases[result['family']]
        if result['outcome'] != 'valid' or base['outcome'] != 'valid':
            counts['unscored_pairs'] += 1
            continue
        counts['scored_pairs'] += 1
        counts['changed_pairs'] += result['statuses'] != base['statuses']
        for key, status in base['statuses'].items():
            counts['scored_criteria'] += 1
            counts['changed_criteria'] += result['statuses'][key] != status
    latencies = [r['latency_ms'] for r in predictions if r['latency_ms'] is not None]
    costs = [int(r['cost_micro_usd']) for r in predictions if r['cost_micro_usd'] is not None]
    model_mixture = len(returned_models) > 1
    origin = predictions[0]['origin'] if predictions else 'none'
    report = {
        'report_version': REPORT_VERSION,
        'reference_origin': 'synthetic_author_expectation_not_human_review',
        'corpus': metadata, 'predictions_fingerprint': fingerprint(predictions),
        'run_identity': {k: predictions[0][k] for k in ('provider', 'requested_model', 'profile_fingerprint', 'origin')} if predictions else None,
        'case_count': len(cases), 'independent_scenario_family_count': len(bases),
        'prediction_coverage': fraction(len(predictions), len(cases)),
        'valid_output_coverage': fraction(totals['valid'], len(cases)),
        'invalid_output_rate': fraction(totals['invalid'], len(predictions)),
        'generation_failure_rate': fraction(totals['generation_failures'], len(predictions)),
        'missing_predictions': totals['missing'],
        'criterion_coverage': fraction(totals['scored'], totals['criteria_expected']),
        'agreement_with_allowed_synthetic_labels': fraction(totals['agreed'], totals['scored']),
        'full_case_agreement': fraction(totals['fully_agreed_cases'], len(cases)),
        'supported_predictions_not_allowed_by_reference': fraction(totals['support_not_in_reference'], totals['predicted_supported']),
        'ambiguous_reference_criteria_scored': totals['ambiguous'],
        'confusion_single_label_only': confusion, 'per_class': precision_recall,
        'category_counts': {k: dict(v) for k, v in sorted(category_totals.items())},
        'omissions': {'cases_with_omissions': fraction(totals['cases_with_omissions'], len(cases)),
                      'declared_omission_entries': totals['omission_count'],
                      'note': 'Packet disclosure coverage, not a model judgment or an estimate of unrecorded real work.'},
        'sensitivity': {k: {**dict(v), 'changed_pair_rate': fraction(v['changed_pairs'], v['scored_pairs'])} for k, v in sorted(changes.items())},
        'latency_ms': {'known': len(latencies), 'unknown': len(predictions) - len(latencies),
                       'median': median(latencies) if latencies else None,
                       'maximum': max(latencies) if latencies else None},
        'cost_micro_usd': {'known': len(costs), 'unknown': len(predictions) - len(costs),
                           'known_total': str(sum(costs)), 'currency': 'USD',
                           'note': 'Only supplied known costs; not a complete provider bill.'},
        'token_usage': {name: {'known': sum(r[name] is not None for r in predictions),
                              'known_total': sum(r[name] or 0 for r in predictions),
                              'unknown': sum(r[name] is None for r in predictions)}
                        for name in ('input_tokens', 'output_tokens')},
        'returned_models': dict(sorted(returned_models.items())),
        'missing_returned_model': totals['missing_returned_model'],
        'mixed_returned_models': model_mixture,
        'human_reviewer_changes': None,
        'human_pilot_periods_completed': 0,
        'real_model_quality_evaluated': False,
        'release_authorized': False,
        'limitations': [
            'Developer-authored synthetic references, including deliberately ambiguous examples; not independently reviewed ground truth.',
            'Variants within one family are correlated, not independent experiments; no statistical significance claim.',
            'Citation existence does not establish truth; fabricated or misleading interpretations still require human review.',
            'Imported provider/model/usage fields are operator assertions, not provider-attested records.',
            'No project data, credentials, database, contribution award, financial close or network call is used by this harness.',
            'Mock stability and structural validity do not demonstrate model accuracy or neutrality.' if origin == 'synthetic_mock' else
            'An offline score does not validate actual deployment permissions, billing, safety or reviewer usefulness.',
        ],
        'cases': results,
    }
    # Do not certify a live model from imported text. Threshold checks are only a
    # regression signal for a future independently reviewed benchmark.
    policy = metadata['thresholds']
    checks = {
        'complete_valid_coverage': totals['valid'] == len(cases),
        'minimum_synthetic_agreement': totals['scored'] > 0 and totals['agreed'] / totals['scored'] >= policy['minimum_synthetic_agreement'],
        'no_reference_contradicting_support': totals['support_not_in_reference'] == 0,
        'stable_single_returned_model': not model_mixture and totals['missing_returned_model'] == 0,
        'sensitivity_limit': all(v['scored_pairs'] == v['expected_pairs'] and
            v['changed_pairs'] / max(1, v['scored_pairs']) <= policy['maximum_changed_pair_rate'] for v in changes.values()),
    }
    report['provisional_regression_checks'] = checks
    report['provisional_regression_pass'] = all(checks.values()) and origin != 'synthetic_mock'
    report['report_fingerprint'] = fingerprint(report)
    return report


def markdown(report: dict) -> str:
    def percentage(item: dict) -> str:
        rate = item['rate']
        return 'Not measured (zero denominator)' if rate is None else f"{100 * rate:.1f}% ({item['numerator']}/{item['denominator']})"
    lines = [
        '# Offline evaluator report', '',
        '**Synthetic references only. This report does not authorize deployment or compensation.**', '',
        f"Split: {report['corpus']['split']}. Cases: {report['case_count']}; scenario families: {report['independent_scenario_family_count']}.", '',
        '| Measurement | Result |', '|---|---|',
    ]
    for title, key in [('Predictions supplied', 'prediction_coverage'), ('Valid output coverage', 'valid_output_coverage'),
        ('Criterion coverage', 'criterion_coverage'), ('Agreement with allowed synthetic labels', 'agreement_with_allowed_synthetic_labels'),
        ('Invalid output rate', 'invalid_output_rate'), ('Generation failure rate', 'generation_failure_rate'),
        ('Supported predictions not allowed by reference', 'supported_predictions_not_allowed_by_reference')]:
        lines.append(f'| {title} | {percentage(report[key])} |')
    lines.extend(['', '## Interpretation', '',
        'The mock provider always answers insufficient. Its stability measures protocol behavior, not useful evidence evaluation.',
        'No human reviewer changes, human pilot observations, or real model-quality measurements are present.', '',
        f"Known cost: {report['cost_micro_usd']['known_total']} micro-USD; {report['cost_micro_usd']['unknown']} rows have unknown cost.",
        'Unknown latency and token usage remain unknown, not zero.', '', '## Controlled perturbations', '',
        '| Variant | Changed pairs | Unscored pairs |', '|---|---|---|'])
    for name, values in report['sensitivity'].items():
        lines.append(f"| {name} | {percentage(values['changed_pair_rate'])} | {values.get('unscored_pairs', 0)} |")
    lines.extend(['', '## Limits', ''])
    lines.extend(p + '\n' for p in report['limitations'])
    lines.extend(['', f"Report fingerprint: `{report['report_fingerprint']}`", ''])
    return '\n'.join(lines)
