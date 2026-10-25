"""Preview -> preserved proposal -> explicit administrator decision -> frozen close.

Uses phase-7 deterministic arithmetic unchanged. Workspace locks are shared with
credit, dispute, policy and membership mutations. No AI provider is consulted.
"""
from uuid import UUID
from copy import deepcopy
from sqlalchemy import select
from fastapi.encoders import jsonable_encoder
from app.core.errors import ApiError
from app.finance.periods import service as records
from app.finance.periods.models import (FinancePeriod, FinanceDocument, FinanceEntry, FinanceProposal,
    FinanceApproval, DistributionClose, ReleaseShareSnapshot)
from app.finance.periods.arithmetic import cash_waterfall
from app.finance.periods.schemas import EntryInput
from app.finance.simulator.service import capture
from app.finance.simulator.schemas import PreviewInput
from app.finance.calculation.engine import distribute
from app.policies.schemas import PolicyRules
from app.policies.service import digest, get_policy, require_ready_policy
from app.security.tokens import now, utc
from . import releases


def approved_sources(entries):
    return [dict(item['record']['entry']) for item in entries if item['state'] == 'approve']


def preview_record(db, project, actor, period, storage):
    records.require_open(db, period)
    source = get_policy(db, project, period.source_policy_id)
    calculation = get_policy(db, project, period.calculation_policy_id)
    rules = PolicyRules.model_validate(calculation.rules)
    # Reuse a complete, bounded ledger reconstruction, not its editable projections.
    simulation = capture(db, project, actor.id, PreviewInput(source_policy_id=source.id,
        calculation_policy_id=calculation.id, month=period.month, amount_cents=0))
    blockers = []
    if utc(period.end_at) > now(): blockers.append('accounting_month_not_finished')
    if not simulation['snapshot']['source_policy']['ready_for_pinned_work']: blockers.append('source_policy_not_ready')
    if not simulation['snapshot']['calculation_policy']['ready_for_pinned_work']: blockers.append('calculation_policy_not_ready')
    entry_rows = records.bounded(db, records.query(FinanceEntry, project).where(FinanceEntry.period_id == period.id)
        .order_by(FinanceEntry.created_at, FinanceEntry.id), records.MAX_ENTRIES)
    entry_views = [records.entry_view(db, entry) for entry in entry_rows]
    documents = {}
    for entry, item in zip(entry_rows, entry_views):
        if item['state'] == 'pending': blockers.append('unreviewed_financial_entry')
        if item['state'] != 'approve': continue
        records.validate_entry(db, project, period, EntryInput.model_validate(entry.record['entry']))
        document = records.get(db, FinanceDocument, project, entry.document_id)
        if str(document.id) not in documents:
            try: records.document_bytes(document, storage)
            except ApiError:
                blockers.append('financial_document_unavailable')
        documents[str(document.id)] = records.view(document)
        if entry.kind == 'deduction' and entry.related_entry_id:
            related = records.get(db, FinanceEntry, project, entry.related_entry_id)
            decision = records.latest_decision(db, related)
            if not decision or decision.record['action'] != 'approve':
                blockers.append('deduction_receipt_not_approved')
    previous = None; reserve = 0; deficit = 0
    if period.previous_period_id:
        parent = records.get(db, FinancePeriod, project, period.previous_period_id)
        closed = records.closed(db, parent)
        if not closed: records.fail('finance_previous_unclosed', 'The preceding period has not been frozen.')
        verify_close(closed)
        previous = {'close_id': str(closed.id), 'record_hash': closed.record_hash,
            'closing_reserve_cents': closed.record['cash']['closing_reserve_cents'],
            'closing_deficit_cents': closed.record['cash']['closing_deficit_cents']}
        reserve, deficit = previous['closing_reserve_cents'], previous['closing_deficit_cents']
    try: cash = cash_waterfall(approved_sources(entry_views), reserve, deficit)
    except ValueError as error: records.fail('finance_amount_invalid', str(error), 422)
    blockers.extend(cash['blockers'])
    release = releases.choice(db, project, period, simulation); blockers.extend(release['blockers'])
    pool_inputs = deepcopy(simulation['calculation_input']['pools'])
    for pool in pool_inputs:
        if pool['key'] == 'release':
            pool['recipients'] = release['record']['roster']['recipients']
            pool['blocked_by_dispute'] = bool(release['open_dispute_ids'])
    output = distribute(cash['distributable_cents'], pool_inputs)
    for pool in output['pools']:
        blockers.extend(f"{pool['key']}:{reason}" for reason in pool['blockers'])
    names = {p['user_id']: p['display_name'] for p in simulation['snapshot']['people']}
    names.update({p['user_id']: p['display_name'] for p in release['record']['roster']['names']})
    return jsonable_encoder({'kind': 'synthetic_distribution_close', 'schema_version': 1,
        'synthetic_only': True, 'real_payment_authorized': False,
        'period': records.view(period), 'source_policy': simulation['snapshot']['source_policy'],
        'calculation_policy': simulation['snapshot']['calculation_policy'], 'previous_close': previous,
        'entries': entry_views, 'documents': [documents[k] for k in sorted(documents)],
        'cash': cash, 'release': release, 'ledger_snapshot': simulation['snapshot'],
        'calculation_input': {'amount_cents': cash['distributable_cents'], 'pools': pool_inputs},
        'result': output, 'people': [{'user_id': uid, 'display_name': name} for uid, name in sorted(names.items())],
        'blockers': sorted(set(blockers)), 'notice': records.NOTICE,
        'coverage_notice': 'Only the selected source-credit policy is included. Pending work and unissued reserve are not contributor ownership. Release shares are pinned; ongoing credit follows original acceptance in this month.'})


def preview(db, project, actor, period, storage, kind='close'):
    records.require_open(db, period)
    record = preview_record(db, project, actor, period, storage) if kind == 'close' else releases.correction_preview(db, project, period)
    return {'record': record, 'preview_hash': digest(record), 'captured_at': now(), 'notice': records.NOTICE}


def proposal_view(db, proposal):
    result = records.view(proposal)
    decision = db.scalar(select(FinanceApproval).where(FinanceApproval.proposal_id == proposal.id))
    result.update(kind=proposal.kind, period_id=str(proposal.period_id),
        decision=records.view(decision) if decision else None, state=decision.record['action'] if decision else 'pending')
    return result


def propose(db, project, actor, period, body, storage):
    old, _ = records.existing(db, FinanceProposal, project, actor, body)
    if old:
        if old.period_id != period.id: records.fail('idempotency_conflict', 'This proposal belongs to another period.')
        return old
    if len(records.bounded(db, records.query(FinanceProposal, project).where(
        FinanceProposal.period_id == period.id), records.MAX_PROPOSALS)) >= records.MAX_PROPOSALS:
        records.fail('finance_proposal_limit', 'The period proposal limit was reached.')
    current = preview(db, project, actor, period, storage, body.kind)
    if current['preview_hash'] != body.reviewed_preview_hash:
        records.fail('stale_finance_preview', 'Financial entries, policies, credit or disputes changed. Recalculate and review.')
    if current['record']['blockers']:
        records.fail('finance_close_blocked', 'Resolve the blockers shown by the reviewed preview before proposing it.')
    return records.insert(db, FinanceProposal, project, actor, body,
        {'preview': current['record'], 'preview_hash': current['preview_hash'], 'reason': body.reason,
         'review_confirmations': {'finance': True, 'scope': True}, 'synthetic_only': True},
        period_id=period.id, kind=body.kind)


def approve(db, project, actor, proposal, body, storage):
    prior, _ = records.existing(db, FinanceApproval, project, actor, body)
    if prior:
        if prior.proposal_id != proposal.id: records.fail('idempotency_conflict', 'The approval belongs to another proposal.')
        return prior
    decision = db.scalar(select(FinanceApproval).where(FinanceApproval.proposal_id == proposal.id))
    if decision: records.fail('finance_proposal_decided', 'This proposal already has a preserved decision.')
    if body.reviewed_proposal_hash != proposal.record_hash:
        records.fail('stale_finance_proposal', 'Review the exact preserved proposal before deciding.')
    period = records.get(db, FinancePeriod, project, proposal.period_id)
    records.require_open(db, period)
    close_id = None; release_id = None
    if body.action == 'approve':
        require_ready_policy(db, project, period.source_policy_id)
        require_ready_policy(db, project, period.calculation_policy_id)
        latest = preview(db, project, actor, period, storage, proposal.kind)
        if latest['preview_hash'] != proposal.record['preview_hash'] or latest['record']['blockers']:
            records.fail('stale_finance_proposal', 'This proposal no longer describes current approved inputs. Recalculate and create a successor proposal.')
        document = proposal.record['preview']
        if proposal.kind == 'release_correction':
            frozen = releases.current(db, project, period.source_policy_id)
            release = records.insert(db, ReleaseShareSnapshot, project, actor, body, document['after'],
                source_policy_id=period.source_policy_id, predecessor_id=frozen.id, version=frozen.version + 1)
            release_id = str(release.id)
        else:
            release_info = document['release']
            if release_info['proposed_initial_freeze']:
                release = records.insert(db, ReleaseShareSnapshot, project, actor, body, release_info['record'],
                    source_policy_id=period.source_policy_id, predecessor_id=None, version=1)
            else:
                release = records.get(db, ReleaseShareSnapshot, project, UUID(release_info['snapshot_id']))
            row = records.insert(db, DistributionClose, project, actor, body, document,
                period_id=period.id, proposal_id=proposal.id, release_snapshot_id=release.id)
            verify_close(row)
            close_id, release_id = str(row.id), str(release.id)
    return records.insert(db, FinanceApproval, project, actor, body,
        {'proposal_id': str(proposal.id), 'proposal_hash': proposal.record_hash,
         'action': body.action, 'reason': body.reason, 'close_id': close_id,
         'release_snapshot_id': release_id, 'synthetic_only': True}, proposal_id=proposal.id)


def verify_close(row):
    records.sealed(row)
    record = row.record
    try:
        if record['kind'] != 'synthetic_distribution_close' or record['synthetic_only'] is not True or record['real_payment_authorized'] is not False:
            raise ValueError('Invalid closed-record mode.')
        for item in record['entries'] + record['documents']:
            if digest(item['record']) != item['record_hash']: raise ValueError('Source record fingerprint mismatch.')
        ledger = record['ledger_snapshot']
        if digest(ledger['ledger_source']) != ledger['ledger_revision']: raise ValueError('Ledger fingerprint mismatch.')
        release = record['release']['record']
        if digest(release) != record['release']['snapshot_hash'] or digest(release['roster']) != release['roster_hash']:
            raise ValueError('Release fingerprint mismatch.')
        previous = record['previous_close'] or {'closing_reserve_cents': 0, 'closing_deficit_cents': 0}
        cash = cash_waterfall(approved_sources(record['entries']), previous['closing_reserve_cents'], previous['closing_deficit_cents'])
        if cash != record['cash']: raise ValueError('Cash waterfall mismatch.')
        pools = []
        ongoing = {}
        for award in ledger['eligible_awards']:
            if award['pool_key'] == 'ongoing':
                for line in award['current_attributions']:
                    ongoing[line['user_id']] = ongoing.get(line['user_id'], 0) + line['atoms']
        for pool in record['calculation_policy']['rules']['pools']:
            recipients = release['roster']['recipients'] if pool['key'] == 'release' else [
                {'user_id': uid, 'atoms': atoms} for uid, atoms in sorted(ongoing.items())]
            pools.append({'key': pool['key'], 'weight_bps': pool['weight_bps'], 'recipients': recipients, 'blocked_by_dispute': False})
        pools.sort(key=lambda p: p['key'])
        expected_input = {'amount_cents': cash['distributable_cents'], 'pools': pools}
        if record['calculation_input'] != expected_input: raise ValueError('Scoped share inputs mismatch.')
        result = distribute(**expected_input)
        if result != record['result'] or record['blockers'] or cash['blockers'] or result['status'] != 'calculated':
            raise ValueError('Closed calculation mismatch or blocked state.')
        if sum(p['amount_cents'] for p in result['people']) != cash['distributable_cents']:
            raise ValueError('Amounts do not reconcile.')
    except (KeyError, ValueError, TypeError):
        records.fail('distribution_integrity_error', 'The preserved distribution failed its deterministic reproduction check. No replacement was calculated.')
    return True


def close_view(row):
    verify_close(row)
    return {**records.view(row), 'period_id': str(row.period_id), 'release_snapshot_id': str(row.release_snapshot_id),
            'reproduced': True, 'notice': records.NOTICE}
