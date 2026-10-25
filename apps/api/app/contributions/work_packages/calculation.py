"""Exact planning allocations; these functions never issue credit."""
from uuid import uuid4
from app.core.errors import ApiError
from app.contributions.work_packages.schemas import ScopeInput


def distribute_percentages(budget: int, entries: list[dict]) -> tuple[list[dict], int]:
    """Largest remainder over people/roles AND a visible unassigned bucket.

    Integer arithmetic throughout. Stable ties: real person UUID + role, then
    the unassigned bucket. Input order cannot change the result. Incomplete
    percentage plans remain blockers even if the unassigned bucket rounds to 0.
    """
    weight = sum(e['basis_points'] for e in entries)
    if not isinstance(budget, int) or isinstance(budget, bool) or budget <= 0 or not 0 <= weight <= 10000:
        raise ValueError('Invalid percentage-allocation inputs.')
    buckets = [(f"{e['user_id']}:{e['role']}", e['basis_points']) for e in entries]
    if len({key for key, _ in buckets}) != len(buckets):
        raise ValueError('Duplicate attribution keys.')
    if any(type(w) is not int or w <= 0 for _, w in buckets):
        raise ValueError('Use positive integer basis points.')
    buckets.append(('~unassigned', 10000 - weight))
    floors = {key: budget * w // 10000 for key, w in buckets}
    remaining = budget - sum(floors.values())
    ranking = sorted(buckets, key=lambda row: (-(budget * row[1] % 10000), row[0]))
    for key, _ in ranking[:remaining]:
        floors[key] += 1
    result = [{**e, 'atoms': floors[f"{e['user_id']}:{e['role']}"]} for e in entries]
    return sorted(result, key=lambda e: (e['user_id'], e['role'])), floors['~unassigned']


def normalize_scope(scope: ScopeInput, budget_atoms: int, participants: dict[str, dict]) -> dict:
    """Persist source proposals alongside their resolved, exact atom amounts."""
    doc = scope.model_dump(mode='json')
    if sum(d['budget_atoms'] for d in doc['deliverables']) > budget_atoms:
        raise ApiError(409, 'package_budget_exceeded', 'Deliverable budgets exceed the approved work allocation.')
    required = {doc['coordinator_id'], *doc['intended_contributor_ids']}
    if not required <= set(participants):
        raise ApiError(422, 'participant_unavailable', 'Choose active non-viewer participants from this project.')
    doc['intended_contributor_ids'].sort()
    doc['participant_labels'] = {uid: participants[uid]['display_name'] for uid in sorted(required)}
    for d in doc['deliverables']:
        d['id'] = d['id'] or str(uuid4())
        plan = d['attribution']
        entries = plan['entries']
        if plan['mode'] == 'percent':
            resolved, unassigned = distribute_percentages(d['budget_atoms'], entries)
            complete = sum(e['basis_points'] for e in entries) == 10000
        else:
            resolved = sorted(entries, key=lambda e: (e['user_id'], e['role']))
            unassigned = d['budget_atoms'] - sum(e['atoms'] for e in resolved)
            complete = unassigned == 0
        d['attribution']['entries'] = sorted(entries, key=lambda e: (e['user_id'], e['role']))
        d['resolved_attributions'] = resolved
        d['unassigned_atoms'] = unassigned
        d['attribution_complete'] = complete
    doc['budget_atoms'] = budget_atoms
    doc['deliverable_atoms'] = sum(d['budget_atoms'] for d in doc['deliverables'])
    doc['unplanned_atoms'] = budget_atoms - doc['deliverable_atoms']
    return doc


def input_from_snapshot(doc: dict) -> ScopeInput:
    """Remove only server-derived fields before validating a new scope revision."""
    fields = ('title', 'outcome', 'acceptance_criteria', 'evidence_requirements',
              'coordinator_id', 'intended_contributor_ids')
    return ScopeInput.model_validate({**{key: doc[key] for key in fields}, 'deliverables': [
        {key: d[key] for key in ('id', 'title', 'outcome', 'acceptance_criteria', 'evidence_requirements',
                               'budget_atoms', 'attribution')} for d in doc['deliverables']]})


def scope_blockers(doc: dict, current_participant_ids: set[str]) -> list[str]:
    issues = []
    if not doc['deliverables']:
        issues.append('Add at least one independently acceptable deliverable.')
    if doc['unplanned_atoms']:
        issues.append('Budget every package atom into deliverables, or reduce the parent allocation while the package is a draft.')
    if any(not d['attribution_complete'] for d in doc['deliverables']):
        issues.append('Resolve every deliverable attribution to exactly its budget (100% for percentage plans).')
    required = {doc['coordinator_id'], *doc['intended_contributor_ids']}
    if not required <= current_participant_ids:
        issues.append('A coordinator or intended contributor no longer has active non-viewer access. Amend the scope.')
    return issues
