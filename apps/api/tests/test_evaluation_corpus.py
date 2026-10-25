"""Synthetic corpus contracts; not independent human reference verification."""
import copy
import hashlib
import json
from pathlib import Path
import pytest
from app.evaluation.corpus import CorpusError, _case, fingerprint, load_corpus, read_json

ROOT = Path(__file__).resolve().parents[3]
EVALS = ROOT / 'evals'


def test_calibration_family_count_and_heldout_manifest():
    cases, meta = load_corpus(EVALS)
    assert len(cases) == 126
    assert len({c['family'] for c in cases}) == 18
    assert meta['split'] == 'calibration'
    manifest = read_json(EVALS / 'manifest.json')
    assert manifest['splits']['holdout']['case_count'] == 42
    assert not set(manifest['splits']['calibration']['families']) & set(manifest['splits']['holdout']['families'])


def test_calibration_does_not_read_holdout(monkeypatch):
    original = Path.read_text
    def guarded(self, *args, **kwargs):
        assert self.name != 'cases.json', 'Calibration opened held-out cases'
        return original(self, *args, **kwargs)
    monkeypatch.setattr(Path, 'read_text', guarded)
    assert len(load_corpus(EVALS)[0]) == 126


@pytest.mark.parametrize('flag,reason', [(False,''),(True,''),(False,'Explicit structural check only'),(True,'too short')])
def test_holdout_requires_explicit_access(flag, reason):
    with pytest.raises(CorpusError, match='holdout_requires'):
        load_corpus(EVALS, 'holdout', allow_holdout=flag, reason=reason)


def test_holdout_structure_explicitly_inspected_not_scored():
    cases, meta = load_corpus(EVALS, 'holdout', allow_holdout=True,
        reason='Structural fixture validation only; no model or label scoring')
    assert len(cases) == 42 and len({c['family'] for c in cases}) == 6
    assert meta['holdout_reason']


@pytest.mark.parametrize('variant', ['baseline','alias_swap','source_order','verbosity','formatting','split_sources','embedded_instruction'])
def test_variants_preserve_reference_and_ids(variant):
    cases, _ = load_corpus(EVALS)
    rows = [c for c in cases if c['variant'] == variant]
    assert len(rows) == 18
    for row in rows:
        base = next(c for c in cases if c['family'] == row['family'] and c['variant'] == 'baseline')
        assert row['reference'] == base['reference']
        assert {c['id'] for c in row['packet']['criteria']} == {'C1','C2','C3'}


@pytest.mark.parametrize('change', [
    lambda c: c.update(id='../escape'),
    lambda c: c.update(reference_origin='human_verified'),
    lambda c: c['packet'].update(award_credit=100),
    lambda c: c['packet']['criteria'].append(c['packet']['criteria'][0]),
    lambda c: c['packet']['sources'].append(c['packet']['sources'][0]),
    lambda c: c['packet']['contributors'].append(c['packet']['contributors'][0]),
    lambda c: c['reference']['C1'].update(allowed_statuses=[{}]),
    lambda c: c['reference']['C1'].update(allowed_statuses=[]),
    lambda c: c['packet']['sources'][0].update(lines=['x'*1001]),
    lambda c: c['packet'].update(outcome='x'),
])
def test_bad_case_schema(change):
    case = copy.deepcopy(load_corpus(EVALS)[0][0]); change(case)
    with pytest.raises(CorpusError): _case(case)


def copy_corpus(tmp_path):
    import shutil
    target = tmp_path / 'corpus'; target.mkdir()
    for relative in ['manifest.json','thresholds.json','fixtures/calibration.json','holdout/cases.json']:
        p = target / relative; p.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(EVALS / relative, p)
    return target


def test_modified_corpus_requires_versioned_integrity_update(tmp_path):
    target = copy_corpus(tmp_path)
    p = target/'fixtures/calibration.json'; p.write_text(p.read_text()+' ')
    with pytest.raises(CorpusError, match='hash_mismatch'): load_corpus(target)


def test_family_overlap_rejected(tmp_path):
    target = copy_corpus(tmp_path); p=target/'manifest.json'; value=read_json(p)
    value['splits']['holdout']['families'].append(value['splits']['calibration']['families'][0])
    p.write_text(json.dumps(value))
    with pytest.raises(CorpusError, match='family_leakage'): load_corpus(target)


def test_changed_thresholds_rejected(tmp_path):
    target=copy_corpus(tmp_path); p=target/'thresholds.json'; value=read_json(p)
    value['minimum_synthetic_agreement']=0.01; p.write_text(json.dumps(value))
    with pytest.raises(CorpusError, match='thresholds_changed'):load_corpus(target)


@pytest.mark.parametrize('raw',['{"x":1,"x":2}','{"x":NaN}','[','null garbage'])
def test_duplicate_nonfinite_or_malformed_json(tmp_path,raw):
    path=tmp_path/'case.json';path.write_text(raw)
    with pytest.raises(CorpusError):read_json(path)


def test_symlink_is_rejected(tmp_path):
    original=tmp_path/'original'; original.write_text('{}')
    link=tmp_path/'link';link.symlink_to(original)
    with pytest.raises(CorpusError):read_json(link)


def test_packet_fingerprint_ignores_dict_order_not_data():
    assert fingerprint({'a':1,'b':2})==fingerprint({'b':2,'a':1})
    assert fingerprint({'a':1})!=fingerprint({'a':2})


def test_criterion_ids_and_order_do_not_reveal_status_globally():
    cases,_=load_corpus(EVALS)
    baseline=[c for c in cases if c['variant']=='baseline']
    for criterion_id in ('C1','C2','C3'):
        statuses={c['reference'][criterion_id]['allowed_statuses'][0] for c in baseline}
        assert statuses=={'supported','contradicted','insufficient'}
    positions={c['reference'][c['packet']['criteria'][0]['id']]['allowed_statuses'][0] for c in baseline}
    assert positions=={'supported','contradicted','insufficient'}
