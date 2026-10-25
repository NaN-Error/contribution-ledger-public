"""Read the ledger under the existing tenant lock; never change contribution credit.

All current ledger, policy, membership and planning writers use the same
workspace lock. Routes MUST obtain project_access(lock=True) before capture.
Snapshot balances are reconstructed from signed events, not editable caches.
"""
from collections import defaultdict
from uuid import uuid4
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select, func
from app.core.errors import ApiError
from app.projects.authorization import not_found
from app.policies.models import PolicyVersion
from app.policies.schemas import PolicyRules
from app.policies.service import digest, get_policy, policy_view
from app.contributions.budgets.models import Milestone, BudgetAllocation
from app.ledger.models import CreditAward, ContributionEvent
from app.ledger.service import open_disputes
from app.security.audit import audit
from app.security.tokens import now, utc
from app.finance.calculation.engine import distribute, MAX_SAFE_INTEGER
from app.finance.calculation.periods import month_bounds, award_eligible
from .models import SimulationScenario
from .schemas import PreviewInput, SaveScenario

MAX_AWARDS = 2000
MAX_EVENTS = 20000
MAX_PLANNING = 10000
MAX_SCENARIOS = 1000
NOTICE = ('Hypothetical, non-payable scenario only. No units, obligations, finalized distributions, '
          'ownership or payments are created. Pending work and unissued reserve are not contributor credit.')


def bounded(db, query, maximum):
    rows = list(db.scalars(query.limit(maximum + 1)))
    if len(rows) > maximum:
        raise ApiError(422, 'simulation_scope_too_large', 'This local simulator scope exceeds its documented limit. No data was silently omitted.')
    return rows


def short_policy(db, project, policy, actor_id):
    view = policy_view(db, project, policy, actor_id)
    return {'id': str(policy.id), 'version': policy.version, 'title': policy.title,
            'state': view['state'], 'content_hash': policy.content_hash,
            'ready_for_pinned_work': view['ready_for_pinned_work'],
            'missing_acknowledgement_ids': sorted(str(i) for i in view['acknowledgements']['missing_user_ids']),
            'rules': policy.rules}


def options(db, project, actor_id, role):
    policies = bounded(db, select(PolicyVersion).where(PolicyVersion.workspace_id == project.workspace_id,
        PolicyVersion.project_id == project.id).order_by(PolicyVersion.version.desc()), 200)
    return {'policies': [short_policy(db, project, p, actor_id) for p in policies],
            'can_save': role != 'viewer', 'notice': NOTICE,
            'limits': {'awards_per_source_policy': MAX_AWARDS, 'events_per_source_policy': MAX_EVENTS,
                       'saved_scenarios_per_project': MAX_SCENARIOS}}


def capture(db, project, actor_id, body: PreviewInput):
    captured_at = now()
    source = get_policy(db, project, body.source_policy_id)
    calculation = get_policy(db, project, body.calculation_policy_id)
    rules = PolicyRules.model_validate(calculation.rules)
    try:
        start, end = month_bounds(body.month, rules.timezone)
    except ValueError as error:
        raise ApiError(422, 'accounting_boundary_invalid', str(error)) from error
    source_info = short_policy(db, project, source, actor_id)
    calculation_info = source_info if source.id == calculation.id else short_policy(db, project, calculation, actor_id)
    awards = bounded(db, select(CreditAward).where(CreditAward.workspace_id == project.workspace_id,
        CreditAward.project_id == project.id, CreditAward.policy_id == source.id).order_by(CreditAward.id), MAX_AWARDS)
    events = bounded(db, select(ContributionEvent).join(CreditAward, CreditAward.id == ContributionEvent.award_id).where(
        CreditAward.workspace_id == project.workspace_id, CreditAward.project_id == project.id,
        CreditAward.policy_id == source.id, ContributionEvent.workspace_id == project.workspace_id,
        ContributionEvent.project_id == project.id).order_by(ContributionEvent.created_at, ContributionEvent.id), MAX_EVENTS)
    milestones = bounded(db, select(Milestone).where(Milestone.workspace_id == project.workspace_id,
        Milestone.project_id == project.id, Milestone.policy_id == source.id).order_by(Milestone.id), MAX_AWARDS)
    allocations = bounded(db, select(BudgetAllocation).join(Milestone, Milestone.id == BudgetAllocation.milestone_id).where(
        Milestone.workspace_id == project.workspace_id, Milestone.project_id == project.id,
        Milestone.policy_id == source.id).order_by(BudgetAllocation.id), MAX_PLANNING)
    disputes = open_disputes(db, project, policy_id=source.id)
    open_by_award = defaultdict(list)
    for dispute in disputes:
        open_by_award[dispute.award_id].append(str(dispute.id))
    by_award = defaultdict(list)
    for event in events:
        by_award[event.award_id].append(event)
    enabled_pools = {pool.key for pool in rules.pools}
    people_by_pool = {pool: defaultdict(int) for pool in enabled_pools}
    names = {}
    eligible_by_pool = {pool: [] for pool in enabled_pools}
    blockers_by_pool = {pool: [] for pool in enabled_pools}
    issued_by_allocation = defaultdict(int)
    issued_by_milestone = defaultdict(int)
    original_rows = []
    eligible_rows = []
    for award in awards:
        balances = defaultdict(int)
        for event in by_award[award.id]:
            balances[(str(event.user_id), event.role)] += event.delta_atoms
        if sum(balances.values()) != award.budget_atoms or any(value < 0 for value in balances.values()):
            raise ApiError(409, 'ledger_integrity_error', 'Preserved ledger lines do not reconcile with an accepted award. An operator must investigate; no scenario was calculated.')
        issued_by_allocation[award.allocation_id] += award.budget_atoms
        issued_by_milestone[award.milestone_id] += award.budget_atoms
        original_rows.append({'id': str(award.id), 'milestone_id': str(award.milestone_id),
            'allocation_id': str(award.allocation_id), 'package_id': str(award.package_id),
            'deliverable_id': str(award.deliverable_id), 'pool_key': award.pool_key,
            'budget_atoms': award.budget_atoms, 'created_at': utc(award.created_at).isoformat()})
        eligible = award.pool_key in enabled_pools and award_eligible(
            award.pool_key, utc(award.created_at), start, end, captured_at)
        if not eligible:
            continue
        eligible_by_pool[award.pool_key].append(str(award.id))
        blockers_by_pool[award.pool_key].extend(open_by_award[award.id])
        for (uid, _), atoms in balances.items():
            if atoms:
                people_by_pool[award.pool_key][uid] += atoms
        for event in by_award[award.id]:
            names[str(event.user_id)] = event.display_name
        eligible_rows.append({'award_id': str(award.id), 'package_id': str(award.package_id),
            'pool_key': award.pool_key, 'milestone_id': str(award.milestone_id),
            'accepted_at': utc(award.created_at).isoformat(), 'budget_atoms': award.budget_atoms,
            'current_attributions': [{'user_id': uid, 'role': role, 'atoms': atoms}
                                    for (uid, role), atoms in sorted(balances.items()) if atoms],
            'open_dispute_ids': sorted(open_by_award[award.id])})
    event_rows = [{'id': str(e.id), 'award_id': str(e.award_id), 'user_id': str(e.user_id),
        'role': e.role, 'display_name': e.display_name, 'delta_atoms': e.delta_atoms,
        'kind': e.kind, 'resolution_id': str(e.resolution_id) if e.resolution_id else None,
        'created_at': utc(e.created_at).isoformat()} for e in events]
    ledger_source = {'source_policy_id': str(source.id), 'awards': original_rows, 'events': event_rows}
    ledger_revision = digest(ledger_source)
    planning = []
    pending_by_pool = defaultdict(int)
    for milestone in milestones:
        members = [a for a in allocations if a.milestone_id == milestone.id and a.status == 'active']
        planned = sum(a.atoms for a in members)
        issued = issued_by_milestone[milestone.id]
        pending = planned - issued
        if pending < 0 or planned + milestone.reserve_floor_atoms > milestone.total_atoms:
            raise ApiError(409, 'planning_integrity_error', 'Planning and preserved awards do not reconcile. No scenario was calculated.')
        for allocation in members:
            unissued = allocation.atoms - issued_by_allocation[allocation.id]
            if unissued < 0:
                raise ApiError(409, 'planning_integrity_error', 'An accepted award exceeds its allocation.')
            pending_by_pool[allocation.pool_key] += unissued
        planning.append({'milestone_id': str(milestone.id), 'name': milestone.name, 'version': milestone.version,
            'total_atoms': milestone.total_atoms, 'planned_atoms': planned, 'issued_atoms': issued,
            'pending_planned_atoms': pending, 'protected_reserve_atoms': milestone.reserve_floor_atoms,
            'available_to_plan_atoms': milestone.total_atoms - planned - milestone.reserve_floor_atoms,
            'allocations': [{'id': str(a.id), 'version': a.version, 'pool_key': a.pool_key,
                'category': a.category, 'planned_atoms': a.atoms, 'issued_atoms': issued_by_allocation[a.id]}
                for a in members]})
    pool_inputs = [{'key': pool.key, 'weight_bps': pool.weight_bps,
        'blocked_by_dispute': bool(blockers_by_pool[pool.key]),
        'recipients': [{'user_id': uid, 'atoms': atoms} for uid, atoms in sorted(people_by_pool[pool.key].items())]}
        for pool in sorted(rules.pools, key=lambda p: p.key)]
    try:
        result = distribute(body.amount_cents, pool_inputs)
    except ValueError as error:
        raise ApiError(409, 'calculation_input_invalid', str(error)) from error
    if sum(m['pending_planned_atoms'] for m in planning) > MAX_SAFE_INTEGER:
        raise ApiError(422, 'simulation_scope_too_large', 'Aggregate planning exceeds the supported exact display range.')
    warnings = []
    if source.id != calculation.id:
        warnings.append('Alternative-policy scenario: existing credit remains under its source policy. Only the selected calculation policy pools, weights and timezone affect this example; other draft rules do not retroactively reapprove or remove awards.')
    if not calculation_info['ready_for_pinned_work']:
        warnings.append('The calculation policy is draft, scheduled or awaiting acknowledgements. This is an unapproved what-if example.')
    if not source_info['ready_for_pinned_work']:
        warnings.append('The source policy is not currently ready for new acceptance. Previously finalized credit remains preserved.')
    if end > captured_at:
        warnings.append('This month is incomplete or in the future. Only credit already accepted at capture time is included; future work is not predicted.')
    warnings.append('Current corrected attribution is used for original awards. Past-month simulations are not reconstructions of what was owed or known in that past month.')
    warnings.append('All matching milestones from one explicitly selected source policy are included. Other policy versions are not combined. Release percentages are not permanently frozen.')
    excluded = len(awards) - sum(len(ids) for ids in eligible_by_pool.values())
    if excluded:
        warnings.append(f'{excluded} source-policy award(s) are outside the selected pool/date scope and were not included.')
    source_other_count = db.scalar(select(func.count()).select_from(CreditAward).where(
        CreditAward.project_id == project.id, CreditAward.workspace_id == project.workspace_id,
        CreditAward.policy_id != source.id))
    if source_other_count:
        warnings.append(f'{source_other_count} award(s) under other policy versions are excluded; this is not an all-project percentage.')
    snapshot = {'source_policy': source_info, 'calculation_policy': calculation_info,
        'period': {'month': body.month, 'timezone': rules.timezone,
                   'start_inclusive': start.isoformat(), 'end_exclusive': end.isoformat()},
        'ledger_revision': ledger_revision, 'ledger_source': ledger_source,
        'eligible_awards': eligible_rows, 'source_award_count': len(awards), 'source_event_count': len(events),
        'excluded_source_award_count': excluded, 'excluded_other_policy_award_count': source_other_count,
        'planning': planning, 'pending_planned_atoms': sum(m['pending_planned_atoms'] for m in planning),
        'pending_by_pool': dict(sorted(pending_by_pool.items())),
        'pool_dispute_ids': {p: sorted(ids) for p, ids in sorted(blockers_by_pool.items())},
        'people': [{'user_id': uid, 'display_name': name} for uid, name in sorted(names.items())],
        'warnings': warnings}
    snapshot = jsonable_encoder(snapshot)
    input_data = body.model_dump(mode='json')
    calculation_input = {'amount_cents': body.amount_cents, 'pools': pool_inputs}
    return {'kind': 'hypothetical_simulation', 'payable': False, 'notice': NOTICE,
        'input': input_data, 'captured_at': captured_at.isoformat(), 'snapshot': snapshot,
        'snapshot_hash': digest({'input': input_data, 'snapshot': snapshot}),
        'calculation_input': calculation_input, 'result': result, 'result_hash': digest(result)}


def verify_record(record):
    try:
        if record['kind'] != 'hypothetical_simulation' or record['payable'] is not False:
            raise ValueError('Invalid scenario kind.')
        if record['snapshot_hash'] != digest({'input': record['input'], 'snapshot': record['snapshot']}):
            raise ValueError('Snapshot fingerprint mismatch.')
        if record['snapshot']['ledger_revision'] != digest(record['snapshot']['ledger_source']):
            raise ValueError('Ledger fingerprint mismatch.')
        result = distribute(**record['calculation_input'])
        if result != record['result'] or record['result_hash'] != digest(result):
            raise ValueError('Calculation mismatch.')
    except (KeyError, TypeError, ValueError) as error:
        raise ApiError(409, 'simulation_integrity_error', 'The saved hypothetical scenario failed its integrity/reproduction check. No new calculation replaced it.') from error
    return True


def get_scenario(db, project, scenario_id):
    row = db.scalar(select(SimulationScenario).where(SimulationScenario.id == scenario_id,
        SimulationScenario.workspace_id == project.workspace_id, SimulationScenario.project_id == project.id))
    if row is None:
        raise not_found()
    return row


def scenario_view(row):
    if row.record_hash != digest(row.record):
        raise ApiError(409, 'simulation_integrity_error', 'The saved scenario record fingerprint does not match.')
    verify_record(row.record)
    return {'id': str(row.id), 'title': row.title, 'created_by': str(row.created_by),
        'created_at': row.created_at, 'record_hash': row.record_hash, 'record': row.record,
        'reproduced': True, 'notice': 'Saved hypothetical example. Its capture date is not current live state. To inspect changes, calculate a new preview.'}


def save_scenario(db, project, actor, role, body: SaveScenario):
    if role == 'viewer':
        raise ApiError(403, 'permission_denied', 'Viewers can calculate and inspect examples but cannot save project scenarios.')
    command_hash = digest({'actor_id': str(actor.id), 'body': body.model_dump(mode='json')})
    existing = db.scalar(select(SimulationScenario).where(SimulationScenario.workspace_id == project.workspace_id,
        SimulationScenario.project_id == project.id, SimulationScenario.request_id == body.request_id))
    if existing:
        if existing.created_by != actor.id or existing.request_hash != command_hash:
            raise ApiError(409, 'idempotency_conflict', 'This save identifier belongs to a different request.')
        return existing
    count = db.scalar(select(func.count()).select_from(SimulationScenario).where(
        SimulationScenario.workspace_id == project.workspace_id, SimulationScenario.project_id == project.id))
    if count >= MAX_SCENARIOS:
        raise ApiError(409, 'scenario_limit', 'The local project scenario limit was reached. Unsaved previews remain available.')
    record = capture(db, project, actor.id, body.input)
    if record['snapshot_hash'] != body.reviewed_snapshot_hash:
        raise ApiError(409, 'stale_simulation', 'The policy, ledger, disputes or planning changed. Recalculate and review before saving.')
    verify_record(record)
    row = SimulationScenario(id=uuid4(), workspace_id=project.workspace_id, project_id=project.id,
        source_policy_id=body.input.source_policy_id, calculation_policy_id=body.input.calculation_policy_id,
        created_by=actor.id, title=body.title, request_id=body.request_id, request_hash=command_hash,
        snapshot_hash=record['snapshot_hash'], record_hash=digest(record), record=record)
    db.add(row)
    audit(db, 'simulation.saved', actor_id=actor.id, workspace_id=project.workspace_id, project_id=project.id,
          subject_id=row.id, details={'snapshot_hash': row.snapshot_hash, 'hypothetical': True, 'payable': False})
    db.flush()
    return row
