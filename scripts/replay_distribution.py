"""Replay a frozen JSON export locally without a running server or external call.

Uses installed project Python dependencies. Validates calculation consistency,
not bank truth, authorization signatures, worker classification or entitlement.
"""
import argparse
import json
from pathlib import Path
import re
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'apps/api'))
MAX_BYTES = 8 * 1024 * 1024


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON field.')
        result[key] = value
    return result


def no_constant(value):
    raise ValueError('Nonfinite JSON values are not accepted.')


def replay(path: Path) -> dict:
    from app.finance.close.service import verify_close
    from app.finance.exports.serialization import EXPORT_VERSION
    with path.open('rb') as stream:
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError('The export exceeds the 8 MiB limit.')
    document = json.loads(raw.decode('utf-8'), object_pairs_hook=unique_object, parse_constant=no_constant)
    if not isinstance(document, dict) or document.get('export_version') != EXPORT_VERSION:
        raise ValueError('Expected a frozen distribution JSON export.')
    fingerprint = document.get('record_hash')
    if not isinstance(fingerprint, str) or not re.fullmatch('[a-f0-9]{64}', fingerprint):
        raise ValueError('Missing preserved fingerprint.')
    verify_close(SimpleNamespace(record=document['record'], record_hash=fingerprint))
    return document['record']['result']


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('export', type=Path, help='Local distribution.json exported by the application')
    args = parser.parse_args()
    try:
        result = replay(args.export)
    except Exception:
        # Do not echo potentially confidential source data or exception text.
        print('Verification failed. Check the export format, fingerprint, arithmetic, file access and installed project dependencies.', file=sys.stderr)
        return 2
    cents = result['amount_cents']
    print(f'Reproduced USD {cents // 100}.{cents % 100:02d}; recipient count: {len(result["people"])}.')
    print('Synthetic-only calculation. This does not verify bank receipts, external signatures or legal entitlement.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
