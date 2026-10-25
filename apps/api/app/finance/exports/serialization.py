"""Deterministic export bytes, never a new obligation or payment side effect.

All user text in CSV is visibly prefixed with "text: " and controls are replaced.
JSON keeps original values. No universal spreadsheet escaping survives arbitrary
subsequent editing; consumers must preserve labels and not execute imported data.
"""
import csv
import json
import unicodedata
from hashlib import sha256
from io import StringIO, BytesIO
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED
from app.finance.close.service import verify_close

EXPORT_VERSION = 'finance-exports-v1'
MAX_EXPORT_BYTES = 8 * 1024 * 1024


def text_cell(value):
    text = ''.join(' ' if unicodedata.category(c) in {'Cc', 'Cf'} else c for c in str(value))
    return 'text: ' + text


def json_bytes(value):
    data = (json.dumps(value, sort_keys=True, ensure_ascii=False, indent=2, allow_nan=False, default=None) + '\n').encode('utf-8')
    if len(data) > MAX_EXPORT_BYTES: raise ValueError('The export exceeds the documented 8 MiB limit.')
    return data


def distribution_csv(close):
    verify_close(close)
    output = StringIO(newline=''); writer = csv.writer(output, quoting=csv.QUOTE_ALL, lineterminator='\r\n')
    writer.writerow(['mode', 'close_id', 'month', 'recipient_id', 'display_name', 'currency', 'amount_cents', 'amount_usd'])
    names = {p['user_id']: p['display_name'] for p in close.record['people']}
    for person in close.record['result']['people']:
        cents = person['amount_cents']
        writer.writerow(['synthetic_only', str(close.id), close.record['period']['record']['month'],
            person['user_id'], text_cell(names.get(person['user_id'], 'Preserved contributor')), 'USD', str(cents),
            f'{cents//100}.{cents%100:02d}'])
    return output.getvalue().encode('utf-8-sig')


def audit_record(close):
    verify_close(close)
    return {'export_version': EXPORT_VERSION, 'close_id': str(close.id), 'record_hash': close.record_hash,
        'closed_at': close.created_at.isoformat(), 'created_by': str(close.created_by),
        'proposal_id': str(close.proposal_id), 'release_snapshot_id': str(close.release_snapshot_id),
        'record': close.record, 'notice': 'Frozen synthetic distribution. Exporting never marks payment. Supporting original bytes and current payment declarations are not embedded.'}


def bundle(close):
    documents = {'distribution.json': json_bytes(audit_record(close)), 'distribution.csv': distribution_csv(close),
        'README.txt': ("Synthetic audit bundle, not a tax form or payment instruction.\n"
            "distribution.json preserves exact approved inputs, ledger evidence and calculator output.\n"
            "distribution.csv prefixes untrusted display text with 'text: '; JSON preserves exact names.\n"
            "Receipt attachment references/hashes are included; original bytes are not embedded.\n"
            "Payment declarations are separate and may change without changing this frozen export.\n"
            "A manifest detects accidental changes; it is not an external signature or tamper-proof certification.\n").encode()}
    documents['manifest.json'] = json_bytes({'version': EXPORT_VERSION, 'files': [
        {'path': key, 'bytes': len(value), 'sha256': sha256(value).hexdigest()} for key, value in sorted(documents.items())]})
    output = BytesIO()
    with ZipFile(output, 'w', compression=ZIP_DEFLATED) as archive:
        for name, data in sorted(documents.items()):
            item = ZipInfo(name, date_time=(1980,1,1,0,0,0)); item.compress_type = ZIP_DEFLATED
            item.external_attr = 0o100644 << 16
            archive.writestr(item, data)
    result = output.getvalue()
    if len(result) > MAX_EXPORT_BYTES: raise ValueError('The audit bundle exceeds the documented limit.')
    return result
