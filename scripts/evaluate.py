"""Offline evaluator commands. No database, network, credential or paid request.

Examples (from repository root, with project Python dependencies installed):
  python scripts/evaluate.py mock --output .local/evaluation/mock-calibration
  python scripts/evaluate.py score --predictions .local/predictions.jsonl --output .local/evaluation/model-a
Holdout access additionally requires --allow-holdout and --reason; logs record
that access. Never claim the shipped synthetic author labels are human reviews.
"""
from __future__ import annotations
import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'apps/api'))
from app.evaluation.corpus import CorpusError, load_corpus, canonical, fingerprint
from app.evaluation.report import mock_predictions, score, markdown
from app.providers.contracts import parse_json


def read_predictions(path: Path) -> list[dict]:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 16 * 1024 * 1024:
        raise CorpusError('invalid_prediction_file')
    rows = []
    with path.open(encoding='utf-8') as handle:
        for line in handle:
            if not line.strip():
                continue
            if len(line.encode('utf-8')) > 100000 or len(rows) >= 1000:
                raise CorpusError('prediction_file_limit')
            try:
                row = parse_json(line)
            except (ValueError, RecursionError):
                raise CorpusError('invalid_prediction_json') from None
            rows.append(row)
    return rows


def run(args: argparse.Namespace) -> dict:
    # New output directory prevents silently replacing an earlier run or leaking
    # prior private data. Actual operator outputs should remain under .local/.
    if args.output.exists():
        raise CorpusError('output_already_exists')
    cases, metadata = load_corpus(args.corpus, args.split,
        allow_holdout=args.allow_holdout, reason=args.reason)
    predictions = mock_predictions(cases) if args.command == 'mock' else read_predictions(args.predictions)
    report = score(cases, metadata, predictions)
    args.output.mkdir(parents=True, mode=0o700)
    try:
        os.chmod(args.output, 0o700)
    except OSError:
        pass  # Windows ACLs remain an operator responsibility; do not claim POSIX modes apply.
    (args.output / 'report.json').write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    (args.output / 'report.md').write_text(markdown(report), encoding='utf-8')
    # Store only hashes/counts in run logs; never copy imported raw output text.
    receipt = {'command': args.command, 'split': args.split, 'holdout_access_reason': metadata['holdout_reason'],
        'corpus_fingerprint': metadata['manifest_fingerprint'], 'predictions_fingerprint': fingerprint(predictions),
        'report_fingerprint': report['report_fingerprint'], 'case_count': len(cases),
        'human_pilot_completed': False, 'network_requests': 0, 'real_model_validation': False}
    (args.output / 'receipt.json').write_bytes(canonical(receipt) + b'\n')
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['mock', 'score'])
    parser.add_argument('--corpus', type=Path, default=ROOT / 'evals')
    parser.add_argument('--split', choices=['calibration', 'holdout'], default='calibration')
    parser.add_argument('--allow-holdout', action='store_true')
    parser.add_argument('--reason', default='')
    parser.add_argument('--predictions', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--require-provisional-pass', action='store_true',
        help='Return exit 3 unless provisional checks pass. Never grants real-use authority.')
    args = parser.parse_args()
    if args.command == 'score' and args.predictions is None:
        parser.error('score requires --predictions')
    try:
        report = run(args)
    except (CorpusError, UnicodeError, OSError) as exc:
        print('Evaluation rejected: ' + (str(exc) if isinstance(exc, CorpusError) else type(exc).__name__), file=sys.stderr)
        return 2
    print(json.dumps({'cases': report['case_count'], 'families': report['independent_scenario_family_count'],
        'valid': report['valid_output_coverage'], 'synthetic_agreement': report['agreement_with_allowed_synthetic_labels'],
        'real_model_quality_evaluated': False, 'human_pilot_completed': False}, indent=2))
    return 3 if args.require_provisional_pass and not report['provisional_regression_pass'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
