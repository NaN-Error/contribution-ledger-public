"""Release shares freeze once. Corrections retain the same underlying award roster.

New work cannot dilute a release via a correction. New release economics require
another explicitly scoped project in this initial single-stream implementation.
"""
from collections import defaultdict
from uuid import UUID
from sqlalchemy import select
from app.ledger.models import CreditAward, ContributionEvent
from app.ledger.service import open_disputes
from app.contributions.reconstruction.models import ReconstructionBatch
from app.finance.periods.models import ReleaseShareSnapshot
from app.finance.periods import service as records
from app.policies.service import digest
from app.security.tokens import utc


def current(db, project, source_policy_id):
    row = db.scalar(records.query(ReleaseShareSnapshot, project).where(
        ReleaseShareSnapshot.source_policy_id == source_policy_id).order_by(ReleaseShareSnapshot.version.desc()).limit(1))
    return records.sealed(row) if row else None


def roster(db, project, source_policy_id, ids):
    selected = set(ids)
    awards = records.bounded(db, select(CreditAward).where(CreditAward.workspace_id == project.workspace_id,
        CreditAward.project_id == project.id, CreditAward.policy_id == source_policy_id,
        CreditAward.pool_key == 'release').order_by(CreditAward.id), 2000)
    awards = [a for a in awards if str(a.id) in selected]
    if len(awards) != len(selected): records.fail('release_awards_missing', 'The frozen release roster no longer matches preserved awards.')
    events = records.bounded(db, select(ContributionEvent).join(CreditAward, CreditAward.id == ContributionEvent.award_id)
        .where(CreditAward.workspace_id == project.workspace_id, CreditAward.project_id == project.id,
               CreditAward.policy_id == source_policy_id, CreditAward.pool_key == 'release',
               ContributionEvent.workspace_id == project.workspace_id, ContributionEvent.project_id == project.id)
        .order_by(ContributionEvent.created_at, ContributionEvent.id), 20000)
    events = [e for e in events if str(e.award_id) in selected]
    by_award = defaultdict(lambda: defaultdict(int)); names = {}; people = defaultdict(int)
    for event in events:
        by_award[event.award_id][(str(event.user_id), event.role)] += event.delta_atoms
        names[str(event.user_id)] = event.display_name
    for award in awards:
        amounts = by_award[award.id]
        if sum(amounts.values()) != award.budget_atoms or any(a < 0 for a in amounts.values()):
            records.fail('release_ledger_integrity', 'The preserved release award lines do not reconcile.')
        for (uid, _), atoms in amounts.items(): people[uid] += atoms
    event_rows = [{'id': str(e.id), 'award_id': str(e.award_id), 'user_id': str(e.user_id),
        'role': e.role, 'display_name': e.display_name, 'delta_atoms': e.delta_atoms,
        'kind': e.kind, 'created_at': utc(e.created_at).isoformat()} for e in events]
    return {'source_policy_id': str(source_policy_id), 'award_ids': sorted(selected),
        'awards': [{'id': str(a.id), 'budget_atoms': a.budget_atoms, 'accepted_at': utc(a.created_at).isoformat()}
                   for a in sorted(awards, key=lambda a: str(a.id))],
        'events': event_rows, 'recipients': [{'user_id': uid, 'atoms': atoms} for uid, atoms in sorted(people.items()) if atoms],
        'names': [{'user_id': uid, 'display_name': names.get(uid, 'Preserved contributor')} for uid in sorted(people) if people[uid]],
        'denominator_atoms': sum(people.values())}


def current_dispute_ids(db, project, policy_id, award_ids):
    return sorted(str(d.id) for d in open_disputes(db, project, policy_id=policy_id) if str(d.award_id) in set(award_ids))


def choice(db, project, period, simulation):
    frozen = current(db, project, period.source_policy_id)
    blockers = []
    if frozen:
        data = roster(db, project, period.source_policy_id, frozen.record['roster']['award_ids'])
        if digest(data) != frozen.record['roster_hash']:
            blockers.append('release_correction_requires_approval')
        chosen = frozen.record
    else:
        ids = [a['award_id'] for a in simulation['snapshot']['eligible_awards'] if a['pool_key'] == 'release']
        data = roster(db, project, period.source_policy_id, ids)
        if any(a['pool_key'] == 'release' and a['id'] not in set(ids) for a in simulation['snapshot']['ledger_source']['awards']):
            blockers.append('release_work_accepted_after_cutoff')
        if simulation['snapshot']['pending_by_pool'].get('release', 0):
            blockers.append('unfinished_release_work')
        unfinished = records.bounded(db, select(ReconstructionBatch).where(
            ReconstructionBatch.workspace_id == project.workspace_id, ReconstructionBatch.project_id == project.id,
            ReconstructionBatch.policy_id == period.source_policy_id, ReconstructionBatch.state != 'frozen'), 200)
        if unfinished: blockers.append('historical_opening_not_archived')
        chosen = {'schema_version': 1, 'source_policy_id': str(period.source_policy_id), 'version': 1,
            'predecessor_hash': None, 'initial_cutoff_exclusive': utc(period.end_at).isoformat(),
            'roster': data, 'roster_hash': digest(data), 'synthetic_only': True}
    if not chosen['roster']['denominator_atoms']: blockers.append('empty_release_pool')
    disputes = current_dispute_ids(db, project, period.source_policy_id, chosen['roster']['award_ids'])
    if disputes: blockers.append('disputed_release_credit')
    return {'snapshot_id': str(frozen.id) if frozen else None,
            'snapshot_hash': frozen.record_hash if frozen else digest(chosen),
            'record': chosen, 'blockers': blockers, 'open_dispute_ids': disputes,
            'proposed_initial_freeze': frozen is None}


def correction_preview(db, project, period):
    frozen = current(db, project, period.source_policy_id)
    if not frozen: records.fail('release_not_frozen', 'The initial release shares are created only by the first approved period close.')
    data = roster(db, project, period.source_policy_id, frozen.record['roster']['award_ids'])
    blockers = []
    if digest(data) == frozen.record['roster_hash']: blockers.append('no_release_attribution_change')
    if data['denominator_atoms'] != frozen.record['roster']['denominator_atoms']:
        blockers.append('release_budget_changed')
    disputes = current_dispute_ids(db, project, period.source_policy_id, data['award_ids'])
    if disputes: blockers.append('disputed_release_credit')
    return {'kind': 'release_correction', 'period_id': str(period.id), 'predecessor_id': str(frozen.id),
        'predecessor_hash': frozen.record_hash, 'before': frozen.record,
        'after': {'schema_version': 1, 'source_policy_id': str(period.source_policy_id),
            'version': frozen.version + 1, 'predecessor_hash': frozen.record_hash,
            'initial_cutoff_exclusive': frozen.record['initial_cutoff_exclusive'],
            'roster': data, 'roster_hash': digest(data), 'synthetic_only': True},
        'blockers': blockers, 'open_dispute_ids': disputes, 'synthetic_only': True,
        'notice': 'Corrected attribution applies to future closes only. Past closes and external payments remain unchanged.'}
