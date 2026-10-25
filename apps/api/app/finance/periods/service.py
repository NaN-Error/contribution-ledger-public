"""Finance writes require the existing workspace lock and current role checks.

Nothing in this module calls a bank, provider, ledger award, or external URL.
Synthetic-only mode remains hard-gated until operational and agreement review.
"""
import csv
from pydantic import ValidationError
from io import BytesIO, StringIO
from uuid import UUID, uuid4, uuid5
from sqlalchemy import select, func
from fastapi.encoders import jsonable_encoder
from app.core.errors import ApiError
from app.projects.authorization import not_found
from app.policies.schemas import PolicyRules
from app.policies.service import digest, get_policy, require_ready_policy
from app.security.audit import audit
from app.security.tokens import utc
from app.finance.calculation.periods import month_bounds
from app.evidence.content import checked_file
from app.evidence.service import ObjectWrites
from app.evidence.schemas import MAX_UPLOAD_BYTES
from app.storage.contracts import ObjectReference, StorageError
from .models import (FinancePeriod, FinanceDocument, FinanceEntry, FinanceEntryDecision,
    FinanceProposal, FinanceApproval, DistributionClose, ExternalPayment, PaymentVoid, FinanceReceiptImport)
from .schemas import EntryInput, AddEntry

MAX_PERIODS = 240
MAX_ENTRIES = 200
MAX_DOCUMENTS = 60
MAX_PROPOSALS = 60
NOTICE = ('Synthetic development records only. An approved close, an export, and an external-payment '
          'declaration are separate records. This application does not authorize real compensation or move money.')


def fail(code, message, status=409):
    raise ApiError(status, code, message)


def permission(role, *, administer=False):
    if role not in ({'admin'} if administer else {'admin', 'finance'}):
        fail('permission_denied', 'Financial administration is required.' if administer else
             'Project administrator or finance access is required for financial source records.', 403)


def query(model, project):
    return select(model).where(model.workspace_id == project.workspace_id, model.project_id == project.id)


def get(db, model, project, row_id):
    row = db.scalar(query(model, project).where(model.id == row_id))
    if row is None: raise not_found()
    sealed(row)
    return row


def sealed(row):
    if row.record_hash != digest(row.record):
        fail('finance_integrity_error', 'A preserved financial record failed its fingerprint check.')
    return row


def view(row):
    sealed(row)
    return {'id': str(row.id), 'created_by': str(row.created_by), 'created_at': row.created_at,
            'record_hash': row.record_hash, 'record': row.record}


def bounded(db, statement, maximum):
    rows = list(db.scalars(statement.limit(maximum + 1)))
    if len(rows) > maximum: fail('finance_scope_limit', 'This scope exceeds its documented limit; nothing was silently omitted.', 422)
    return rows


def existing(db, model, project, actor, body):
    command_hash = digest({'actor_id': str(actor.id), 'body': body.model_dump(mode='json')})
    row = db.scalar(query(model, project).where(model.created_by == actor.id, model.request_id == body.request_id))
    if row:
        sealed(row)
        if row.request_hash != command_hash:
            fail('idempotency_conflict', 'This request identifier was already used for different financial contents.')
    return row, command_hash


def insert(db, model, project, actor, body, record, **fields):
    payload = jsonable_encoder(record)
    row = model(id=uuid4(), workspace_id=project.workspace_id, project_id=project.id,
        created_by=actor.id, request_id=body.request_id,
        request_hash=digest({'actor_id': str(actor.id), 'body': body.model_dump(mode='json')}),
        record=payload, record_hash=digest(payload), **fields)
    db.add(row); db.flush()
    audit(db, f'finance.{model.__tablename__}.created', actor_id=actor.id,
        workspace_id=project.workspace_id, project_id=project.id, subject_id=row.id,
        details={'record_hash': row.record_hash, 'synthetic_only': True})
    return row


def closed(db, period):
    return db.scalar(select(DistributionClose).where(DistributionClose.period_id == period.id))


def require_open(db, period):
    if closed(db, period):
        fail('finance_period_closed', 'This period is frozen. Enter a linked correction in a later period; do not rewrite history.')


def period_view(db, period):
    result = view(period); close = closed(db, period)
    result.update(state='closed' if close else 'open', month=period.month,
                  close_id=str(close.id) if close else None, notice=NOTICE)
    return result


def create_period(db, project, actor, body):
    row, _ = existing(db, FinancePeriod, project, actor, body)
    if row: return row
    source = require_ready_policy(db, project, body.source_policy_id)
    calculation = require_ready_policy(db, project, body.calculation_policy_id)
    rules = PolicyRules.model_validate(calculation.rules)
    if source.rules['currency'] != rules.currency:
        fail('finance_currency_mismatch', 'Source and calculation policies must have the same currency.', 422)
    try: start, end = month_bounds(body.month, rules.timezone)
    except ValueError as error: fail('finance_boundary_invalid', str(error), 422)
    rows = bounded(db, query(FinancePeriod, project).order_by(FinancePeriod.month), MAX_PERIODS)
    previous = rows[-1] if rows else None
    if previous:
        prior_close = closed(db, previous)
        if not prior_close: fail('finance_previous_open', 'Close the existing open period before creating its successor.')
        if utc(previous.end_at) != start or previous.timezone != rules.timezone:
            fail('finance_period_gap', 'Create the immediately following calendar month with the same accounting timezone.')
        # One product/release stream per project in this pilot. A sequel is another project.
        if previous.source_policy_id != source.id:
            fail('finance_source_changed', 'This project finance stream retains its source-credit policy. Use another project for separate release economics.')
    record = {'schema_version': 1, 'synthetic_only': True, 'currency': 'USD',
        'month': body.month, 'timezone': rules.timezone, 'start_inclusive': start.isoformat(),
        'end_exclusive': end.isoformat(), 'source_policy_id': str(source.id),
        'calculation_policy_id': str(calculation.id), 'source_policy_hash': source.content_hash,
        'calculation_policy_hash': calculation.content_hash,
        'previous_period_id': str(previous.id) if previous else None,
        'agreement_reference': body.agreement_reference, 'deficit_rule': body.deficit_rule,
        'reason': body.reason, 'accounting_rules': rules.accounting.model_dump(mode='json')}
    return insert(db, FinancePeriod, project, actor, body, record, month=body.month,
        timezone=rules.timezone, source_policy_id=source.id, calculation_policy_id=calculation.id,
        previous_period_id=previous.id if previous else None, start_at=start, end_at=end)


def upload_document(db, project, actor, period, body, storage):
    # The route owns ObjectWrites so ambiguous commit never deletes a committed object.
    old, _ = existing(db, FinanceDocument, project, actor, body)
    if old:
        if old.period_id != period.id: fail('idempotency_conflict', 'The document request belongs to another period.')
        return old, None
    require_open(db, period)
    if len(bounded(db, query(FinanceDocument, project).where(FinanceDocument.period_id == period.id), MAX_DOCUMENTS)) >= MAX_DOCUMENTS:
        fail('finance_document_limit', 'This period has reached its supporting-document limit.')
    file = checked_file(body.file)
    reference = storage.put(project.workspace_id, BytesIO(file.data), MAX_UPLOAD_BYTES)
    record = {'period_id': str(period.id), 'title': body.title, 'provenance': body.provenance,
        'filename': file.filename, 'media_type': file.media_type, 'size_bytes': reference.size_bytes,
        'sha256': reference.sha256, 'reason': body.reason, 'scanner': 'not_malware_scanned',
        'visibility': 'administrator_and_finance_only', 'synthetic_only': True}
    try:
        row = insert(db, FinanceDocument, project, actor, body, record, period_id=period.id,
            object_id=reference.object_id, backend=storage.backend, sha256=reference.sha256, size_bytes=reference.size_bytes)
    except Exception:
        # Known pre-commit failure. Process death requires orphan inspection, not blind cleanup.
        try: storage.delete(reference)
        except StorageError: pass
        raise
    return row, reference


def document_reference(document):
    return ObjectReference(document.workspace_id, document.object_id, document.sha256, document.size_bytes)


def document_bytes(document, storage):
    sealed(document)
    if storage.backend != document.backend:
        fail('finance_document_unavailable', 'The configured store does not contain this document.')
    try:
        with storage.open(document_reference(document)) as stream:
            data = stream.read(document.size_bytes + 1)
    except StorageError:
        fail('finance_document_unavailable', 'The supporting document is missing, corrupt or inaccessible.')
    from hashlib import sha256
    if len(data) != document.size_bytes or sha256(data).hexdigest() != document.sha256:
        fail('finance_document_unavailable', 'The supporting document failed its stored checksum.')
    return data


def source_key(*parts):
    import unicodedata
    normalized = [' '.join(unicodedata.normalize('NFKC', part).casefold().split()) for part in parts]
    return digest({'external_identity': normalized})


def latest_decision(db, entry):
    row = db.scalar(select(FinanceEntryDecision).where(FinanceEntryDecision.entry_id == entry.id)
        .order_by(FinanceEntryDecision.sequence.desc()).limit(1))
    return sealed(row) if row else None


def entry_view(db, entry):
    result = view(entry); decision = latest_decision(db, entry)
    result['decision'] = view(decision) if decision else None
    result['state'] = decision.record['action'] if decision else 'pending'
    result['history'] = [view(x) for x in db.scalars(select(FinanceEntryDecision)
        .where(FinanceEntryDecision.entry_id == entry.id).order_by(FinanceEntryDecision.sequence))]
    return result


def validate_entry(db, project, period, entry):
    rules = PolicyRules.model_validate(get_policy(db, project, period.calculation_policy_id).rules)
    doc = get(db, FinanceDocument, project, entry.document_id)
    if doc.period_id != period.id: fail('finance_document_scope', 'Attach supporting documentation to this period first.', 422)
    if entry.kind == 'receipt' and entry.revenue_basis != rules.accounting.revenue_basis:
        fail('finance_receipt_basis', 'The receipt basis must match the approved calculation policy.', 422)
    if entry.kind == 'deduction' and entry.deduction_category not in rules.accounting.allowed_deductions:
        fail('finance_deduction_disallowed', 'This deduction category is not permitted by the selected policy.', 422)
    related = get(db, FinanceEntry, project, entry.related_entry_id) if entry.related_entry_id else None
    if entry.kind == 'deduction' and related:
        if related.kind != 'receipt': fail('finance_receipt_required', 'Link a deduction to its receipt, not another expense.', 422)
        if entry.deduction_category in related.record['entry']['already_deducted']:
            fail('finance_already_deducted', 'This category was already deducted in the linked net receipt.', 422)
        other_period = get(db, FinancePeriod, project, related.period_id)
        if utc(other_period.start_at) > utc(period.start_at): fail('finance_future_link', 'A deduction cannot refer to a future receipt.', 422)
    if entry.kind.startswith('adjustment_'):
        target_period = get(db, FinancePeriod, project, related.period_id)
        if not closed(db, target_period) or utc(target_period.end_at) > utc(period.start_at):
            fail('finance_correction_target', 'Corrections must link an earlier frozen period entry.', 422)
        if related.kind.startswith('reserve_'):
            fail('finance_correction_target', 'Correct reserve balances with explicit reserve movements, not cash corrections.', 422)
        decision = latest_decision(db, related)
        if not decision or decision.record['action'] != 'approve':
            fail('finance_correction_target', 'The earlier entry must have been approved when its period closed.', 422)
    return doc


def add_entry(db, project, actor, period, body):
    old, _ = existing(db, FinanceEntry, project, actor, body)
    if old:
        if old.period_id != period.id: fail('idempotency_conflict', 'The entry request belongs to another period.')
        return old
    require_open(db, period)
    entries = bounded(db, query(FinanceEntry, project).where(FinanceEntry.period_id == period.id), MAX_ENTRIES)
    if len(entries) >= MAX_ENTRIES: fail('finance_entry_limit', 'This period has reached its 200-entry limit.')
    e = body.entry; doc = validate_entry(db, project, period, e)
    key = source_key(e.source_name, e.statement_reference, e.line_reference)
    if db.scalar(query(FinanceEntry, project).where(FinanceEntry.source_key == key)):
        fail('duplicate_financial_source', 'This external statement line is already recorded in the project, including rejected/void history.')
    record = {'period_id': str(period.id), 'entry': e.model_dump(mode='json'),
        'document_hash': doc.record_hash, 'reason': body.reason, 'synthetic_only': True}
    return insert(db, FinanceEntry, project, actor, body, record, period_id=period.id,
        document_id=e.document_id, related_entry_id=e.related_entry_id, source_key=key,
        kind=e.kind, amount_cents=e.amount_cents)


def decide_entry(db, project, actor, entry, body, storage):
    old, _ = existing(db, FinanceEntryDecision, project, actor, body)
    if old:
        if old.entry_id != entry.id: fail('idempotency_conflict', 'The decision belongs to another entry.')
        return old
    period = get(db, FinancePeriod, project, entry.period_id); require_open(db, period)
    latest = latest_decision(db, entry)
    if body.reviewed_entry_hash != entry.record_hash or body.expected_decision_hash != (latest.record_hash if latest else None):
        fail('stale_finance_entry', 'The entry or its decision changed. Review the current record.')
    if latest and not (latest.record['action'] == 'approve' and body.action == 'void'):
        fail('finance_decision_terminal', 'Rejected/void entries remain in history; create a corrected entry with a new source-line identifier.')
    if not latest and body.action == 'void': fail('finance_decision_invalid', 'Only an approved open-period entry can be voided.')
    if body.action == 'approve':
        require_ready_policy(db, project, period.calculation_policy_id)
        validate_entry(db, project, period, EntryInput.model_validate(entry.record['entry']))
        document_bytes(get(db, FinanceDocument, project, entry.document_id), storage)
    seq = latest.sequence + 1 if latest else 1
    return insert(db, FinanceEntryDecision, project, actor, body,
        {'entry_id': str(entry.id), 'entry_hash': entry.record_hash, 'action': body.action,
         'previous_hash': latest.record_hash if latest else None, 'reason': body.reason,
         'document_reviewed': True, 'synthetic_only': True}, entry_id=entry.id, sequence=seq)


def parse_receipts(body):
    # UTF-8 text already supplied, strict canonical schema; no Excel formulas evaluated.
    try:
        reader = csv.DictReader(StringIO(body.csv_text), strict=True)
        if reader.fieldnames != ['line_reference', 'amount_cents', 'description']:
            fail('finance_csv_header', 'Use exactly: line_reference,amount_cents,description.', 422)
        result = []
        for row in reader:
            if len(result) >= MAX_ENTRIES or None in row or any(v is None for v in row.values()):
                fail('finance_csv_shape', 'CSV has too many rows or inconsistent columns.', 422)
            raw = row['amount_cents']
            if not raw.isascii() or not raw.isdigit() or len(raw) > 13:
                fail('finance_csv_amount', 'CSV amounts must be positive integer cents, not formulas or decimals.', 422)
            result.append(EntryInput(document_id=body.document_id, kind='receipt',
                amount_cents=int(raw), source_name=body.source_name, statement_reference=body.statement_reference,
                line_reference=row['line_reference'], description=row['description'],
                revenue_basis=body.revenue_basis, already_deducted=body.already_deducted))
        if not result: fail('finance_csv_empty', 'Supply at least one receipt row.', 422)
        return result
    except ValidationError:
        fail('finance_csv_invalid', 'A CSV row failed the documented field/amount/basis validation.', 422)
    except csv.Error:
        fail('finance_csv_invalid', 'The CSV quoting is invalid.', 422)


def import_receipts(db, project, actor, period, body):
    # Whole request is one DB transaction; failures roll back all inserted lines.
    # Row UUIDs include the canonical import hash, so changed payload replay conflicts
    # on source keys rather than quietly changing an earlier imported line.
    old, _ = existing(db, FinanceReceiptImport, project, actor, body)
    if old:
        if old.period_id != period.id: fail('idempotency_conflict', 'This import belongs to another period.')
        return [get(db, FinanceEntry, project, UUID(uid)) for uid in old.record['entry_ids']]
    rows = parse_receipts(body)
    result = []
    for index, entry in enumerate(rows):
        command = AddEntry(request_id=uuid5(body.request_id, str(index)), reason=body.reason, entry=entry)
        result.append(add_entry(db, project, actor, period, command))
    insert(db, FinanceReceiptImport, project, actor, body,
        {'period_id': str(period.id), 'entry_ids': [str(row.id) for row in result], 'synthetic_only': True}, period_id=period.id)
    return result
