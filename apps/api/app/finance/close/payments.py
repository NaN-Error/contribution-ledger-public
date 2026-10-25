"""Human declarations of externally completed synthetic transfers, not a payment API."""
from uuid import UUID
from sqlalchemy import select
from app.finance.periods import service as records
from app.finance.periods.models import ExternalPayment, PaymentVoid
from app.security.tokens import now, utc
from .service import verify_close

MAX_PAYMENTS = 500


def collection(db, project, close):
    verify_close(close)
    rows = records.bounded(db, records.query(ExternalPayment, project).where(ExternalPayment.close_id == close.id)
        .order_by(ExternalPayment.created_at, ExternalPayment.id), MAX_PAYMENTS)
    voids = {v.payment_id: v for v in db.scalars(select(PaymentVoid).join(ExternalPayment, ExternalPayment.id == PaymentVoid.payment_id)
        .where(ExternalPayment.close_id == close.id, PaymentVoid.workspace_id == project.workspace_id,
               PaymentVoid.project_id == project.id))}
    paid = {}; items = []
    for row in rows:
        records.sealed(row)
        void = voids.get(row.id)
        if not void: paid[str(row.recipient_id)] = paid.get(str(row.recipient_id), 0) + row.amount_cents
        items.append({**records.view(row), 'void': records.view(void) if void else None,
                      'status': 'voided_record' if void else 'recorded_external_payment'})
    balances = []
    names = {p['user_id']: p['display_name'] for p in close.record['people']}
    for line in close.record['result']['people']:
        amount = paid.get(line['user_id'], 0); due = line['amount_cents']
        balances.append({'user_id': line['user_id'], 'display_name': names.get(line['user_id'], 'Preserved contributor'),
            'distribution_cents': due, 'recorded_paid_cents': amount,
            'outstanding_cents': max(0, due-amount), 'overpaid_cents': max(0, amount-due),
            'status': 'overpayment_recorded' if amount > due else 'fully_recorded' if amount == due else
                      'partially_recorded' if amount else 'not_recorded'})
    return {'close_id': str(close.id), 'items': items, 'balances': balances,
        'synthetic_only': True, 'notice': 'External declarations are not bank verification. Voiding a mistaken record does not refund or reverse a transfer.'}


def add(db, project, actor, close, body):
    old, _ = records.existing(db, ExternalPayment, project, actor, body)
    if old:
        if old.close_id != close.id: records.fail('idempotency_conflict', 'This payment belongs to another close.')
        return old
    verify_close(close)
    if body.reviewed_close_hash != close.record_hash:
        records.fail('stale_distribution', 'Review the exact frozen distribution before recording a transfer.')
    if utc(body.paid_at) > now(): records.fail('payment_in_future', 'An externally completed transfer cannot have a future completion time.', 422)
    if utc(body.paid_at) < utc(close.created_at):
        records.fail('payment_before_close', 'This tracker records transfers completed after the frozen close; earlier advances require separate accounting.', 422)
    current = collection(db, project, close)
    if len(current['items']) >= MAX_PAYMENTS: records.fail('payment_limit', 'This close has reached its 500-record limit.')
    target = next((b for b in current['balances'] if b['user_id'] == str(body.recipient_id)), None)
    if not target or target['distribution_cents'] == 0:
        records.fail('invalid_payment_recipient', 'Choose a recipient with a positive amount in this frozen distribution.', 422)
    if body.amount_cents > target['outstanding_cents'] and body.overpayment_acknowledged is not True:
        records.fail('overpayment_confirmation_required', 'The reported transfer exceeds the outstanding amount. Explicitly acknowledge the overpayment to record it.')
    from app.finance.calculation.engine import MAX_CENTS
    if target['recorded_paid_cents'] + body.amount_cents > MAX_CENTS:
        records.fail('payment_amount_limit', 'Cumulative reported payments exceed the supported exact range.', 422)
    key = records.source_key(body.provider, body.external_reference)
    if db.scalar(records.query(ExternalPayment, project).where(ExternalPayment.external_key == key)):
        records.fail('duplicate_payment_reference', 'This provider/transfer reference is already recorded in this project, including voided history.')
    return records.insert(db, ExternalPayment, project, actor, body,
        {'close_id': str(close.id), 'close_hash': close.record_hash, 'recipient_id': str(body.recipient_id),
         'amount_cents': body.amount_cents, 'provider': body.provider, 'external_reference': body.external_reference,
         'paid_at': body.paid_at.isoformat(), 'reason': body.reason, 'overpayment_acknowledged': body.overpayment_acknowledged,
         'verification': 'operator_declaration_not_bank_verification', 'synthetic_only': True},
        close_id=close.id, recipient_id=body.recipient_id, amount_cents=body.amount_cents, external_key=key)


def void(db, project, actor, payment, body):
    old, _ = records.existing(db, PaymentVoid, project, actor, body)
    if old:
        if old.payment_id != payment.id: records.fail('idempotency_conflict', 'This correction belongs to another payment.')
        return old
    if body.reviewed_payment_hash != payment.record_hash:
        records.fail('stale_payment_record', 'Review the exact payment record before voiding the declaration.')
    if db.scalar(records.query(PaymentVoid, project).where(PaymentVoid.payment_id == payment.id)):
        records.fail('payment_already_void', 'This declaration was already voided; its original reference remains reserved.')
    return records.insert(db, PaymentVoid, project, actor, body,
        {'payment_id': str(payment.id), 'payment_hash': payment.record_hash, 'reason': body.reason,
         'action': 'void_mistaken_declaration', 'money_reversed': False, 'synthetic_only': True}, payment_id=payment.id)


def statement(db, project, close, recipient_id):
    verify_close(close)
    line = next((p for p in close.record['result']['people'] if p['user_id'] == str(recipient_id)), None)
    if not line: raise records.not_found()
    current = collection(db, project, close)
    balance = next(b for b in current['balances'] if b['user_id'] == str(recipient_id))
    details = []
    for pool in close.record['result']['pools']:
        allocation = next((a for a in pool['allocations'] if a['key'] == str(recipient_id)), None)
        if allocation:
            details.append({'pool_key': pool['key'], 'weight_bps': pool['weight_bps'],
                'pool_cents': pool['amount_cents'], 'denominator_atoms': pool['denominator_atoms'],
                'recipient_calculation': allocation})
    return {'kind': 'synthetic_contributor_statement', 'synthetic_only': True,
        'close_id': str(close.id), 'close_hash': close.record_hash, 'closed_at': close.created_at,
        'month': close.record['period']['record']['month'], 'currency': 'USD',
        'recipient': balance, 'pool_explanations': details,
        'payments': [i for i in current['items'] if i['record']['recipient_id'] == str(recipient_id)],
        'notice': 'The distribution is frozen; reported payments are current declarations. This is not a tax form, a bank receipt or proof of legal entitlement.'}
