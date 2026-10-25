from hashlib import sha256
from typing import Literal
from uuid import UUID
from urllib.parse import quote
from fastapi import APIRouter, Query, Request, Response
from sqlalchemy import select
from app.auth.dependencies import Db, Authenticated
from app.projects.authorization import project_access
from app.finance.simulator.service import options as policy_options
from app.evidence.service import ObjectWrites
from app.finance.close import service as closes, payments, releases
from app.finance.exports.serialization import distribution_csv, audit_record, bundle, json_bytes
from . import service as records
from .models import (FinancePeriod, FinanceDocument, FinanceEntry, FinanceProposal,
    DistributionClose, ExternalPayment, ReleaseShareSnapshot)
from .schemas import (CreatePeriod, UploadDocument, AddEntry, ImportReceipts, DecideEntry,
    Propose, ApproveProposal, RecordPayment, VoidPayment)

router = APIRouter(prefix='/api/v1/workspaces/{workspace_id}/projects/{project_id}/finance', tags=['synthetic financial records'])


def context(db, identity, workspace_id, project_id, *, source=False, admin=False):
    project, role = project_access(db, workspace_id, project_id, identity.user.id, lock=True)
    if source or admin: records.permission(role, administer=admin)
    return project, role


def binary(data, filename, media_type='application/octet-stream'):
    return Response(data, media_type=media_type, headers={'Cache-Control': 'no-store, private',
        'Content-Disposition': f"attachment; filename=ledger-export; filename*=UTF-8''{quote(filename, safe='')}",
        'X-Content-Type-Options': 'nosniff', 'Content-Security-Policy': "default-src 'none'; sandbox; frame-ancestors 'none'",
        'Referrer-Policy': 'no-referrer', 'Vary': 'Cookie', 'X-Content-SHA256': sha256(data).hexdigest()})


@router.get('/options')
def options(workspace_id: UUID, project_id: UUID, db: Db, identity: Authenticated):
    project, role = context(db, identity, workspace_id, project_id)
    result = {'can_manage_finance': role in {'admin','finance'}, 'can_approve': role == 'admin',
        'viewer_id': str(identity.user.id), 'notice': records.NOTICE, 'synthetic_only': True,
        'limits': {'entries_per_period': records.MAX_ENTRIES, 'documents_per_period': records.MAX_DOCUMENTS,
                   'periods_per_project': records.MAX_PERIODS, 'exports_bytes': 8*1024*1024}}
    if role in {'admin','finance'}:
        result['policies'] = policy_options(db, project, identity.user.id, role)['policies']
    else: result['policies'] = []
    return result


@router.get('/periods')
def periods(workspace_id: UUID, project_id: UUID, db: Db, identity: Authenticated):
    project, _ = context(db, identity, workspace_id, project_id)
    rows = records.bounded(db, records.query(FinancePeriod, project).order_by(FinancePeriod.month.desc()), records.MAX_PERIODS)
    result = []
    for period in rows:
        records.sealed(period); close = records.closed(db, period)
        result.append({'id': str(period.id), 'month': period.month, 'timezone': period.timezone,
            'state': 'closed' if close else 'open', 'close_id': str(close.id) if close else None,
            'created_at': period.created_at})
    return {'items': result, 'notice': records.NOTICE}


@router.post('/periods', status_code=201)
def create_period(workspace_id: UUID, project_id: UUID, body: CreatePeriod, db: Db, identity: Authenticated):
    project, _ = context(db, identity, workspace_id, project_id, admin=True)
    row = records.create_period(db, project, identity.user, body)
    result = records.period_view(db, row); db.commit(); return result


@router.get('/periods/{period_id}')
def period(workspace_id: UUID, project_id: UUID, period_id: UUID, db: Db, identity: Authenticated):
    project, _ = context(db, identity, workspace_id, project_id, source=True)
    row = records.get(db, FinancePeriod, project, period_id)
    result = records.period_view(db, row)
    result['entries'] = [records.entry_view(db, e) for e in records.bounded(db,
        records.query(FinanceEntry, project).where(FinanceEntry.period_id == row.id)
            .order_by(FinanceEntry.created_at, FinanceEntry.id), records.MAX_ENTRIES)]
    result['documents'] = [records.view(d) for d in records.bounded(db,
        records.query(FinanceDocument, project).where(FinanceDocument.period_id == row.id)
            .order_by(FinanceDocument.created_at, FinanceDocument.id), records.MAX_DOCUMENTS)]
    result['proposals'] = [closes.proposal_view(db, p) for p in records.bounded(db,
        records.query(FinanceProposal, project).where(FinanceProposal.period_id == row.id)
            .order_by(FinanceProposal.created_at, FinanceProposal.id), records.MAX_PROPOSALS)]
    release = releases.current(db, project, row.source_policy_id)
    result['release_snapshot'] = records.view(release) if release else None
    return result


@router.post('/periods/{period_id}/documents', status_code=201)
def document_add(workspace_id: UUID, project_id: UUID, period_id: UUID, body: UploadDocument,
                 request: Request, db: Db, identity: Authenticated):
    project, _ = context(db, identity, workspace_id, project_id, source=True)
    period = records.get(db, FinancePeriod, project, period_id)
    store = request.app.state.object_storage
    with ObjectWrites(store) as writes:
        row, reference = records.upload_document(db, project, identity.user, period, body, store)
        if reference: writes.add(reference)
        result = records.view(row); writes.success(); db.commit()
    return result


@router.get('/documents/{document_id}/download')
def download_document(workspace_id: UUID, project_id: UUID, document_id: UUID,
                      request: Request, db: Db, identity: Authenticated):
    project, _ = context(db, identity, workspace_id, project_id, source=True)
    document = records.get(db, FinanceDocument, project, document_id)
    return binary(records.document_bytes(document, request.app.state.object_storage), document.record['filename'])


@router.get('/documents/{document_id}/preview')
def document_preview(workspace_id: UUID, project_id: UUID, document_id: UUID,
                     request: Request, db: Db, identity: Authenticated):
    project, _ = context(db, identity, workspace_id, project_id, source=True)
    document = records.get(db, FinanceDocument, project, document_id)
    if document.record['media_type'].startswith('image/'):
        records.fail('finance_text_preview_unavailable', 'Raster statement originals are download-only in this phase.')
    text = records.document_bytes(document, request.app.state.object_storage).decode('utf-8-sig')
    return {'text': text[:20000], 'truncated': len(text) > 20000,
            'notice': 'Plain text only. No formulas, Markdown or HTML are executed.'}


@router.post('/periods/{period_id}/entries', status_code=201)
def entry_add(workspace_id: UUID, project_id: UUID, period_id: UUID, body: AddEntry, db: Db, identity: Authenticated):
    project, _ = context(db, identity, workspace_id, project_id, source=True)
    row = records.add_entry(db, project, identity.user, records.get(db, FinancePeriod, project, period_id), body)
    result = records.entry_view(db, row); db.commit(); return result


@router.post('/periods/{period_id}/import-receipts', status_code=201)
def receipt_import(workspace_id: UUID, project_id: UUID, period_id: UUID, body: ImportReceipts, db: Db, identity: Authenticated):
    project, _ = context(db, identity, workspace_id, project_id, source=True)
    rows = records.import_receipts(db, project, identity.user, records.get(db, FinancePeriod, project, period_id), body)
    result = {'items': [records.entry_view(db, row) for row in rows]}; db.commit(); return result


@router.post('/entries/{entry_id}/decisions')
def entry_decide(workspace_id: UUID, project_id: UUID, entry_id: UUID, body: DecideEntry,
                 request: Request, db: Db, identity: Authenticated):
    project, _ = context(db, identity, workspace_id, project_id, admin=True)
    entry = records.get(db, FinanceEntry, project, entry_id)
    records.decide_entry(db, project, identity.user, entry, body, request.app.state.object_storage)
    result = records.entry_view(db, entry); db.commit(); return result


@router.post('/periods/{period_id}/preview')
def preview(workspace_id: UUID, project_id: UUID, period_id: UUID, request: Request, db: Db,
            identity: Authenticated, kind: Literal['close','release_correction'] = 'close'):
    project, _ = context(db, identity, workspace_id, project_id, source=True)
    return closes.preview(db, project, identity.user, records.get(db, FinancePeriod, project, period_id),
                          request.app.state.object_storage, kind)


@router.post('/periods/{period_id}/proposals', status_code=201)
def proposal_add(workspace_id: UUID, project_id: UUID, period_id: UUID, body: Propose,
                 request: Request, db: Db, identity: Authenticated):
    project, role = context(db, identity, workspace_id, project_id, source=True)
    if body.kind == 'release_correction': records.permission(role, administer=True)
    row = closes.propose(db, project, identity.user, records.get(db, FinancePeriod, project, period_id), body,
                         request.app.state.object_storage)
    result = closes.proposal_view(db, row); db.commit(); return result


@router.get('/proposals/{proposal_id}')
def proposal_get(workspace_id: UUID, project_id: UUID, proposal_id: UUID, db: Db, identity: Authenticated):
    project, _ = context(db, identity, workspace_id, project_id, source=True)
    return closes.proposal_view(db, records.get(db, FinanceProposal, project, proposal_id))


@router.post('/proposals/{proposal_id}/decisions')
def proposal_decide(workspace_id: UUID, project_id: UUID, proposal_id: UUID, body: ApproveProposal,
                    request: Request, db: Db, identity: Authenticated):
    project, _ = context(db, identity, workspace_id, project_id, admin=True)
    row = records.get(db, FinanceProposal, project, proposal_id)
    closes.approve(db, project, identity.user, row, body, request.app.state.object_storage)
    result = closes.proposal_view(db, row); db.commit(); return result


@router.get('/releases')
def release_history(workspace_id: UUID, project_id: UUID, db: Db, identity: Authenticated):
    project, _ = context(db, identity, workspace_id, project_id, source=True)
    rows = records.bounded(db, records.query(ReleaseShareSnapshot, project).order_by(ReleaseShareSnapshot.version), 240)
    return {'items': [records.view(r) for r in rows]}


@router.get('/closes/{close_id}')
def close_get(workspace_id: UUID, project_id: UUID, close_id: UUID, db: Db, identity: Authenticated):
    project, _ = context(db, identity, workspace_id, project_id, source=True)
    return closes.close_view(records.get(db, DistributionClose, project, close_id))


@router.get('/closes/{close_id}/export')
def export(workspace_id: UUID, project_id: UUID, close_id: UUID, db: Db, identity: Authenticated,
           format: Literal['csv','json','zip'] = 'json'):
    project, _ = context(db, identity, workspace_id, project_id, source=True)
    row = records.get(db, DistributionClose, project, close_id)
    try:
        data = distribution_csv(row) if format == 'csv' else bundle(row) if format == 'zip' else json_bytes(audit_record(row))
    except ValueError as error: records.fail('finance_export_limit', str(error), 422)
    return binary(data, f'synthetic-distribution-{close_id}.{format}',
                  {'csv': 'text/csv', 'json': 'application/json', 'zip': 'application/zip'}[format])


@router.get('/closes/{close_id}/payments')
def payments_get(workspace_id: UUID, project_id: UUID, close_id: UUID, db: Db, identity: Authenticated):
    project, _ = context(db, identity, workspace_id, project_id, source=True)
    return payments.collection(db, project, records.get(db, DistributionClose, project, close_id))


@router.post('/closes/{close_id}/payments', status_code=201)
def payment_add(workspace_id: UUID, project_id: UUID, close_id: UUID, body: RecordPayment, db: Db, identity: Authenticated):
    project, _ = context(db, identity, workspace_id, project_id, source=True)
    row = payments.add(db, project, identity.user, records.get(db, DistributionClose, project, close_id), body)
    result = records.view(row); db.commit(); return result


@router.post('/payments/{payment_id}/void')
def payment_void(workspace_id: UUID, project_id: UUID, payment_id: UUID, body: VoidPayment, db: Db, identity: Authenticated):
    project, _ = context(db, identity, workspace_id, project_id, admin=True)
    row = payments.void(db, project, identity.user, records.get(db, ExternalPayment, project, payment_id), body)
    result = records.view(row); db.commit(); return result


@router.get('/closes/{close_id}/statement')
def own_statement(workspace_id: UUID, project_id: UUID, close_id: UUID, db: Db, identity: Authenticated,
                  recipient_id: UUID | None = None):
    project, role = context(db, identity, workspace_id, project_id)
    recipient = recipient_id or identity.user.id
    if recipient != identity.user.id: records.permission(role)
    row = records.get(db, DistributionClose, project, close_id)
    return payments.statement(db, project, row, recipient)
