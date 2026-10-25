"""Versioned corpus loading with integrity, family-separated holdout, and strict bounds.

Synthetic reference annotations are developer-authored expectations, not human
review outcomes. Integrity establishes local file consistency, not an external
signature or independent validation of those expectations.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from app.providers.contracts import parse_json

VERSION = 'synthetic-evidence-corpus-v1'
MAX_FILE_BYTES = 8 * 1024 * 1024
STATUSES = frozenset({'supported', 'contradicted', 'insufficient'})


class CorpusError(ValueError):
    """Non-sensitive failure codes only."""


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
                      allow_nan=False).encode('utf-8')


def fingerprint(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def read_json(path: Path, *, limit: int = MAX_FILE_BYTES) -> Any:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > limit:
        raise CorpusError('invalid_file')
    try:
        return parse_json(path.read_text(encoding='utf-8'))
    except (UnicodeError, ValueError, RecursionError):
        raise CorpusError('invalid_json') from None


def _case(case: dict) -> None:
    if not isinstance(case, dict) or set(case) != {
        'id', 'family', 'variant', 'category', 'packet', 'reference', 'reference_origin', 'tags'
    }:
        raise CorpusError('invalid_case')
    for key in ('id', 'family', 'variant', 'category'):
        value = case[key]
        if not isinstance(value, str) or not 1 <= len(value) <= 80 or any(
            not (c.isascii() and (c.isalnum() or c in '_-')) for c in value
        ):
            raise CorpusError('invalid_case_identifier')
    if case['reference_origin'] != 'synthetic_author_expectation_not_human_review':
        raise CorpusError('invalid_reference_origin')
    packet = case['packet']
    if not isinstance(packet, dict) or len(canonical(packet)) > 60000:
        raise CorpusError('invalid_packet')
    if set(packet) != {'outcome', 'criteria', 'sources', 'contributors', 'omissions'}:
        raise CorpusError('invalid_packet_fields')
    if not isinstance(packet['outcome'], str) or not 8 <= len(packet['outcome']) <= 2000:
        raise CorpusError('invalid_outcome')
    criteria = packet['criteria']
    if not isinstance(criteria, list) or not 1 <= len(criteria) <= 64:
        raise CorpusError('invalid_criteria')
    import re
    for c in criteria:
        if (not isinstance(c, dict) or set(c) != {'id', 'text'} or
            not isinstance(c['id'], str) or not re.fullmatch(r'C[1-9][0-9]{0,2}', c['id']) or
            not isinstance(c['text'], str) or not 8 <= len(c['text']) <= 2000):
            raise CorpusError('invalid_criteria')
    ids = [c['id'] for c in criteria]
    if len(ids) != len(set(ids)):
        raise CorpusError('duplicate_criterion')
    if not isinstance(packet['sources'], list) or len(packet['sources']) > 100:
        raise CorpusError('invalid_sources')
    for s in packet['sources']:
        if (not isinstance(s, dict) or set(s) != {'id', 'kind', 'lines'} or
            not isinstance(s['id'], str) or not re.fullmatch(r'E[1-9][0-9]{0,2}', s['id']) or
            not isinstance(s['kind'], str) or not 1 <= len(s['kind']) <= 80 or
            not isinstance(s['lines'], list) or not 1 <= len(s['lines']) <= 200 or
            any(not isinstance(line, str) or len(line) > 1000 for line in s['lines'])):
            raise CorpusError('invalid_sources')
    source_ids = [s['id'] for s in packet['sources']]
    if len(set(source_ids)) != len(source_ids):
        raise CorpusError('duplicate_source')
    if not isinstance(packet['contributors'], list) or len(packet['contributors']) > 100:
        raise CorpusError('invalid_contributors')
    aliases = []
    for person in packet['contributors']:
        if (not isinstance(person, dict) or set(person) != {'alias'} or
            not isinstance(person['alias'], str) or
            not re.fullmatch(r'contributor_[1-9][0-9]{0,2}', person['alias'])):
            raise CorpusError('invalid_contributors')
        aliases.append(person['alias'])
    if len(aliases) != len(set(aliases)):
        raise CorpusError('duplicate_contributor')
    for key in ('omissions',):
        if not isinstance(packet[key], list) or any(not isinstance(s, str) or len(s) > 1500 for s in packet[key]):
            raise CorpusError('invalid_omissions')
    if not isinstance(case['tags'], list) or any(not isinstance(s, str) or len(s) > 80 for s in case['tags']):
        raise CorpusError('invalid_tags')
    ref = case['reference']
    if not isinstance(ref, dict) or set(ref) != set(ids):
        raise CorpusError('reference_criteria_mismatch')
    for item in ref.values():
        if (not isinstance(item, dict) or set(item) != {'allowed_statuses', 'rationale'} or
            not isinstance(item['allowed_statuses'], list) or not item['allowed_statuses'] or
            any(not isinstance(s, str) or s not in STATUSES for s in item['allowed_statuses']) or
            len(item['allowed_statuses']) != len(set(item['allowed_statuses'])) or
            not isinstance(item['rationale'], str) or not 8 <= len(item['rationale']) <= 2000):
            raise CorpusError('invalid_reference')


def load_corpus(root: Path, split: str = 'calibration', *, allow_holdout: bool = False,
                reason: str = '') -> tuple[list[dict], dict]:
    if split not in {'calibration', 'holdout'}:
        raise CorpusError('invalid_split')
    if split == 'holdout' and (not allow_holdout or not 12 <= len(reason.strip()) <= 500):
        raise CorpusError('holdout_requires_explicit_reason')
    manifest = read_json(root / 'manifest.json', limit=65536)
    if not isinstance(manifest, dict) or manifest.get('version') != VERSION:
        raise CorpusError('invalid_manifest')
    entries = manifest.get('splits')
    if not isinstance(entries, dict) or set(entries) != {'calibration', 'holdout'}:
        raise CorpusError('invalid_manifest_splits')
    # Validate family separation using the manifest; do not read holdout cases
    # during ordinary calibration. A local operator can still read files directly.
    fams = []
    for name, relative in [('calibration', 'fixtures/calibration.json'), ('holdout', 'holdout/cases.json')]:
        entry = entries[name]
        if (not isinstance(entry, dict) or set(entry) != {'path', 'sha256', 'case_count', 'families'} or
            entry['path'] != relative or type(entry['case_count']) is not int or
            not 1 <= entry['case_count'] <= 1000 or not isinstance(entry['families'], list) or
            not entry['families'] or any(not isinstance(x, str) for x in entry['families']) or
            len(entry['families']) != len(set(entry['families']))):
            raise CorpusError('invalid_manifest_entry')
        fams.append(set(entry['families']))
    if fams[0] & fams[1]:
        raise CorpusError('family_leakage')
    entry = entries[split]
    path = root / entry['path']
    # Resolved location must remain below the corpus root, including parent links.
    if not path.resolve().is_relative_to(root.resolve()):
        raise CorpusError('invalid_file_path')
    data = read_json(path)
    if hashlib.sha256(path.read_bytes()).hexdigest() != entry['sha256']:
        raise CorpusError('corpus_hash_mismatch')
    if not isinstance(data, list) or len(data) != entry['case_count']:
        raise CorpusError('case_count_mismatch')
    for case in data:
        _case(case)
    if len({c['id'] for c in data}) != len(data):
        raise CorpusError('duplicate_case')
    if {c['family'] for c in data} != set(entry['families']):
        raise CorpusError('family_manifest_mismatch')
    groups: dict[str, list[dict]] = {}
    for case in data:
        groups.setdefault(case['family'], []).append(case)
    for family in groups.values():
        variants = [c['variant'] for c in family]
        if variants.count('baseline') != 1 or len(variants) != len(set(variants)):
            raise CorpusError('invalid_variant_group')
        baseline = next(c for c in family if c['variant'] == 'baseline')
        if any(c['reference'] != baseline['reference'] for c in family):
            raise CorpusError('variant_reference_changed')
    thresholds = read_json(root / 'thresholds.json', limit=65536)
    if (not isinstance(thresholds, dict) or
        type(thresholds.get('minimum_synthetic_agreement')) not in (float, int) or
        type(thresholds.get('maximum_changed_pair_rate')) not in (float, int) or
        not 0 <= thresholds['minimum_synthetic_agreement'] <= 1 or
        not 0 <= thresholds['maximum_changed_pair_rate'] <= 1 or
        thresholds.get('human_reviewed') is not False or
        thresholds.get('independent_model_validation') is not False):
        raise CorpusError('invalid_thresholds')
    if fingerprint(thresholds) != manifest.get('thresholds_fingerprint'):
        raise CorpusError('thresholds_changed')
    return data, {'version': VERSION, 'split': split, 'cases_sha256': entry['sha256'],
                  'manifest_fingerprint': fingerprint(manifest), 'thresholds_fingerprint': fingerprint(thresholds),
                  'thresholds': thresholds, 'holdout_reason': reason.strip() if split == 'holdout' else None}
