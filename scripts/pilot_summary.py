"""Summarize locally supplied shadow-pilot observations, without certifying them.

Input files may contain sensitive participant observations. Keep them outside
source control. No account, compensation, readiness flag or provider is changed.
An empty template remains unobserved, not a completed synthetic human pilot.
"""
from __future__ import annotations
import argparse
from datetime import datetime
import json
from pathlib import Path
from statistics import median


def summarize(value: dict) -> dict:
    if not isinstance(value, dict) or set(value) != {'schema_version','periods','observations'} or value['schema_version'] != 'shadow-observations-v1':
        raise ValueError('Invalid pilot input schema.')
    periods=value['periods']; rows=value['observations']
    if not isinstance(periods,list) or len(periods)>24 or not isinstance(rows,list) or len(rows)>10000:
        raise ValueError('Input limits exceeded.')
    known={}; ranges=[]
    for p in periods:
        if not isinstance(p,dict) or set(p)!={'id','start','end','compensation_unchanged','record_reference'}:
            raise ValueError('Invalid period.')
        if not isinstance(p['id'],str) or not 1<=len(p['id'])<=80 or p['id'] in known:
            raise ValueError('Invalid or duplicate period ID.')
        start=datetime.fromisoformat(p['start']);end=datetime.fromisoformat(p['end'])
        if start.tzinfo is None or end.tzinfo is None or end<=start:
            raise ValueError('Use distinct timezone-aware period boundaries.')
        if p['compensation_unchanged'] is not True:
            raise ValueError('This schema accepts shadow observations only.')
        if not isinstance(p['record_reference'],str) or not 8<=len(p['record_reference'])<=500:
            raise ValueError('A local supporting-record reference is required.')
        known[p['id']]=p;ranges.append((start,end))
    ranges.sort()
    if any(a[1]>b[0] for a,b in zip(ranges,ranges[1:])):
        raise ValueError('Shadow periods must not overlap.')
    seen=set();pairs=[];changed=[];reconstructed=[];participants=set()
    for row in rows:
        if not isinstance(row,dict) or set(row)!={'period_id','participant_alias','work_reference','manual_seconds','assisted_seconds','changed_ai_finding','reconstructed_distribution','record_reference'}:
            raise ValueError('Invalid observation.')
        if row['period_id'] not in known:
            raise ValueError('Unknown period.')
        for key in ('participant_alias','work_reference','record_reference'):
            if not isinstance(row[key],str) or not 1<=len(row[key])<=500:
                raise ValueError('Bounded observation references are required.')
        key=(row['period_id'],row['participant_alias'],row['work_reference'])
        if key in seen:raise ValueError('Duplicate paired observation.')
        seen.add(key);participants.add(row['participant_alias'])
        for key in ('manual_seconds','assisted_seconds'):
            if row[key] is not None and (type(row[key]) is not int or not 0<=row[key]<=86400):
                raise ValueError('Invalid or negative review duration.')
        for key in ('changed_ai_finding','reconstructed_distribution'):
            if row[key] is not None and type(row[key]) is not bool:
                raise ValueError('Unknown outcomes must be null, not guessed.')
        if row['manual_seconds'] is not None and row['assisted_seconds'] is not None:
            pairs.append(row['manual_seconds']-row['assisted_seconds'])
        if row['changed_ai_finding'] is not None:changed.append(row['changed_ai_finding'])
        if row['reconstructed_distribution'] is not None:reconstructed.append(row['reconstructed_distribution'])
    return {'schema_version':'shadow-summary-v1','operator_declared_periods':len(periods),
        'observation_count':len(rows),'distinct_declared_participant_aliases':len(participants),
        'paired_review_time_observations':len(pairs),'median_manual_minus_assisted_seconds':median(pairs) if pairs else None,
        'changed_ai_findings':{'count':sum(changed),'known_observations':len(changed),'unknown':len(rows)-len(changed)},
        'successful_reconstructions':{'count':sum(reconstructed),'known_observations':len(reconstructed),'unknown':len(rows)-len(reconstructed)},
        'human_pilot_verified':False,'deployment_authorized':False,
        'note':'Descriptive operator-supplied observations only. Accounts, independence, record authenticity, order effects and completeness require human review. Positive time difference is not a causal benefit estimate.'}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('input',type=Path)
    args=parser.parse_args()
    try:
        if args.input.is_symlink() or args.input.stat().st_size>8*1024*1024:raise ValueError('Invalid observation file.')
        def pairs(items):
            out={}
            for k,v in items:
                if k in out:raise ValueError('Duplicate JSON field.')
                out[k]=v
            return out
        def reject(_):raise ValueError('Nonfinite JSON.')
        data=json.loads(args.input.read_text(encoding='utf-8'),object_pairs_hook=pairs,parse_constant=reject)
        print(json.dumps(summarize(data),indent=2));return 0
    except (OSError,ValueError,TypeError,KeyError):
        print('Pilot summary rejected invalid or incomplete input. No verification status changed.');return 2


if __name__=='__main__':raise SystemExit(main())
