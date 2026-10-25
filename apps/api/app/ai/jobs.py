"""Explicit AI job queue, isolated from the GitHub foreign-keyed outbox.

Catalog GETs may retry. A probe is durably marked dispatched before networking;
no automatic POST retry is ever performed, including after process death.
"""
from datetime import datetime,timedelta
from uuid import UUID,uuid4
from sqlalchemy import select
from app.ai.models import AIConnection,AIModel,AIJob,AIPrice
from app.ai.connections import service as c
from app.ai.usage.service import settle
from app.core.errors import ApiError
from app.policies.service import digest
from app.providers.contracts import (ProviderError,GenerationRequest,PROBE_PROMPT,PROBE_SCHEMA,PROBE_VERSION,
    ADAPTER_VERSION,ModelInfo,GenerationResult)
from app.security.secrets.store import SecretUnavailable
from app.security.tokens import now,utc

LEASE_SECONDS=1800


def _locked(db,job_id):
    j=db.get(AIJob,job_id)
    if j is None:return None,None
    c.lock_workspace(db,j.workspace_id)
    db.refresh(j)
    row=db.get(AIConnection,j.connection_id,populate_existing=True)
    return j,row


def current(db,row,j,settings):
    if not row.enabled or j.generation!=row.generation or not c.owner_active(db,row):return False
    try:
        c.context(db,row.workspace_id,row.project_id,j.requested_by)
        c.configuration_check(settings,row.provider,paid=j.kind in {'probe','assessment'})
    except ApiError:return False
    if j.kind=='assessment':
        from app.ai.assessments.service import job_current
        return job_current(db,row,j,settings)
    return True


def _cancel(db,row,j,cause):
    c.refund(db,row,j);j.status='cancelled';j.last_error=cause;j.finished_at=now();j.lease_token=None;j.lease_until=None
    c.event(db,row,'job_cancelled',{'cause':cause},j)


def maintain(database,settings,limit=50):
    """Bounded maintenance called only by the explicitly running AI worker."""
    at=now();count=0
    with database.session() as db:
        expired=list(db.scalars(select(AIJob.id).where(AIJob.status=='running',AIJob.lease_until<=at).limit(limit)))
    for jid in expired:
        with database.session() as db:
            j,row=_locked(db,jid)
            if j.status!='running' or not j.lease_until or utc(j.lease_until)>now():continue
            j.lease_token=None;j.lease_until=None
            if j.kind in {'probe','assessment'} and j.dispatched_at:
                j.status='ambiguous';j.accounting_state='uncertain';j.last_error='worker_lost_after_dispatch';j.finished_at=now()
                c.event(db,row,'assessment_ambiguous' if j.kind=='assessment' else 'probe_ambiguous',{'cause':'worker_lost_after_dispatch'},j)
            elif j.attempts>=3:
                j.status='failed';j.last_error='retry_exhausted';j.finished_at=now()
                c.event(db,row,'job_failed',{'cause':'retry_exhausted'},j)
            else:
                j.status='queued';j.not_before=now()+timedelta(seconds=60)
                c.event(db,row,'catalog_recovered',job=j)
            db.commit();count+=1
    with database.session() as db:
        due=list(db.scalars(select(AIConnection.id).where(AIConnection.enabled.is_(True),AIConnection.next_refresh_at<=at)
            .order_by(AIConnection.next_refresh_at,AIConnection.id).limit(limit)))
    for cid in due:
        with database.session() as db:
            row=db.get(AIConnection,cid);c.lock_workspace(db,row.workspace_id);db.refresh(row)
            if not row.enabled or utc(row.next_refresh_at)>now():continue
            if not c.owner_active(db,row):
                row.last_error='owner_access_removed';row.next_refresh_at=now()+timedelta(hours=24);db.commit();continue
            try:c.enqueue_catalog(db,row,uuid4(),row.owner_id,settings)
            except ApiError:
                row.last_error='configuration_or_quota';row.next_refresh_at=now()+timedelta(hours=24)
            else:row.next_refresh_at=now()+timedelta(hours=24)
            db.commit();count+=1
    return count


def claim(database,settings,job_id=None):
    with database.session() as db:
        ids=[job_id] if job_id else list(db.scalars(select(AIJob.id).where(AIJob.status=='queued',AIJob.not_before<=now())
            .order_by(AIJob.created_at,AIJob.id).limit(50)))
    for jid in ids:
        with database.session() as db:
            j,row=_locked(db,jid)
            if j is None or j.status!='queued' or utc(j.not_before)>now():continue
            if not current(db,row,j,settings):_cancel(db,row,j,'authorization_changed');db.commit();continue
            # Serialize external requests for a connection. Repeated catalog requests coalesce.
            running=db.scalar(select(AIJob.id).where(AIJob.connection_id==row.id,AIJob.status=='running').limit(1))
            if running:continue
            if row.retry_not_before and utc(row.retry_not_before)>now():
                j.not_before=utc(row.retry_not_before);db.commit();continue
            if j.kind=='probe':
                s=j.specification;m=db.get(AIModel,UUID(s['model_id']))
                p=db.get(AIPrice,UUID(s['price_id']))
                if (j.requested_by!=row.owner_id or s['month']!=now().strftime('%Y-%m') or p is None
                    or utc(p.valid_until)<=now() or p.fingerprint!=s['price_hash'] or m is None
                    or not m.available or m.generation!=row.generation or m.fingerprint!=s['model_hash']
                    or s.get('adapter_version')!=ADAPTER_VERSION or s.get('prompt_version')!=PROBE_VERSION
                    or not row.last_catalog_at or utc(row.last_catalog_at)<now()-timedelta(hours=48)):
                    _cancel(db,row,j,'probe_configuration_stale');db.commit();continue
            j.status='running';j.attempts+=1;j.lease_token=uuid4();j.lease_until=now()+timedelta(seconds=LEASE_SECONDS)
            # Last-before-send commit is a deliberately conservative billable boundary.
            if j.kind in {'probe','assessment'}:j.dispatched_at=now()
            token=j.lease_token
            c.event(db,row,'job_dispatched',{'attempt':j.attempts},j)
            db.commit();return j.id,token
    return None


def execute(database,settings,factory,store,claimed):
    jid,lease=claimed
    with database.session() as db:
        j,row=_locked(db,jid)
        if j.status!='running' or j.lease_token!=lease:return False
        if not current(db,row,j,settings):
            # No external request has been sent by THIS process yet.
            _cancel(db,row,j,'authorization_changed');db.commit();return False
        provider=row.provider;kind=j.kind;spec=dict(j.specification);ref=row.credential_ref;binding=c.key_context(row)
        generation=None
        if kind=='assessment':
            from app.ai.assessments.service import generation_request
            generation=generation_request(db,j)
        db.commit()
    result=None;err=None;models=None
    try:
        adapter=factory.get(provider)
        key='' if provider=='mock' else store.read(ref,binding)
        if kind=='catalog':
            models=adapter.list_models(key)
            if not isinstance(models,list) or len(models)>2000 or any(not isinstance(m,ModelInfo) for m in models):
                raise ProviderError('catalog_incomplete')
            if len({m.id for m in models})!=len(models):raise ProviderError('catalog_incomplete')
        else:
            result=adapter.generate(key,generation or GenerationRequest(spec['remote_id'],PROBE_PROMPT,PROBE_SCHEMA,spec['max_output_tokens']))
            if not isinstance(result,GenerationResult) or result.finish not in {'complete','refused','truncated','unexpected'} or not isinstance(result.content,str):
                raise ProviderError('malformed',ambiguous=True)
    except SecretUnavailable:err=ProviderError('disabled')
    except ProviderError as e:err=e
    except Exception:
        # Unknown failures after a generation dispatch could have been billed.
        # Never include str(exception), response text, or credentials in logs/DB.
        err=ProviderError('malformed',ambiguous=kind in {'probe','assessment'})
    finally:
        key=None
    with database.session() as db:
        j,row=_locked(db,jid)
        if j.status!='running' or j.lease_token!=lease or not j.lease_until or utc(j.lease_until)<=now():
            # A lease-expiry recovery owns this result. Do not retry or mutate it.
            return False
        authorized=current(db,row,j,settings)
        j.lease_token=None;j.lease_until=None
        if err and err.code=='rate_limited':
            row.retry_not_before=now()+timedelta(seconds=err.retry_after)
        if kind=='catalog':
            if not err and models is not None:
                previous_ids=set(db.scalars(select(AIModel.remote_id).where(AIModel.connection_id==row.id)).all())
                if len(previous_ids | {info.id for info in models})>5000:err=ProviderError('catalog_incomplete')
            if not authorized:_cancel(db,row,j,'authorization_changed')
            elif err:
                j.last_error=err.code;row.last_error=err.code
                retry=err.code in {'timeout','transport','rate_limited','provider_failure'} and j.attempts<3
                j.status='queued' if retry else 'failed'
                j.not_before=now()+timedelta(seconds=err.retry_after)
                if not retry:j.finished_at=now()
                row.next_refresh_at=max(utc(row.next_refresh_at),j.not_before)
                c.event(db,row,'catalog_failed',{'code':err.code,'retry_scheduled':retry},j)
            else:
                old={m.remote_id:m for m in db.scalars(select(AIModel).where(AIModel.connection_id==row.id)).all()}
                captured=now();seen=set()
                for info in models:
                    document=info.document();fingerprint=digest(document);seen.add(info.id);m=old.get(info.id)
                    if m is None:
                        m=AIModel(id=uuid4(),workspace_id=row.workspace_id,project_id=row.project_id,connection_id=row.id,remote_id=info.id,
                            document=document,fingerprint=fingerprint,generation=row.generation,available=True,observed_at=captured,probe_state='unknown');db.add(m)
                    else:
                        if m.fingerprint!=fingerprint or m.generation!=row.generation or not m.available:
                            m.probe_state='unknown';m.probe_job_id=None;m.probe_at=None
                        m.document=document;m.fingerprint=fingerprint;m.generation=row.generation;m.available=True;m.observed_at=captured
                for remote,m in old.items():
                    if remote not in seen:
                        m.available=False;m.probe_state='unknown';m.probe_job_id=None;m.probe_at=None
                row.last_catalog_at=captured;row.last_error=None;row.next_refresh_at=captured+timedelta(hours=24)
                j.status='succeeded';j.finished_at=captured;j.last_error=None
                j.result={'model_count':len(models),'catalog_hash':digest(sorted([m.document() for m in models],key=lambda v:v['id']))}
                c.event(db,row,'catalog_captured',j.result,j)
        else:
            if err:
                j.last_error=err.code;j.status='ambiguous' if err.ambiguous else 'failed';j.finished_at=now()
                if err.ambiguous:j.accounting_state='uncertain'
                else:c.refund(db,row,j)
                if kind=='probe' and authorized and err.code in {'authentication','permission','model_unavailable','incompatible','disabled'}:
                    m=db.get(AIModel,UUID(spec['model_id']))
                    if m and m.generation==j.generation and m.fingerprint==spec['model_hash']:
                        m.probe_state='failed';m.probe_job_id=j.id;m.probe_at=now()
                c.event(db,row,'assessment_finished' if kind=='assessment' else 'probe_finished',{'error':err.code,'ambiguous':err.ambiguous},j)
            elif kind=='assessment':
                from app.ai.assessments.service import finish
                observation=finish(db,j,result,authorized)
                j.status='succeeded' if observation.status=='valid' else 'failed'
                j.last_error=None if observation.status=='valid' else observation.status
                j.finished_at=now()
                settle(db,row,j,input_tokens=result.input_tokens,output_tokens=result.output_tokens,usage_supported=result.usage_supported)
                c.event(db,row,'assessment_finished',j.result,j)
            else:
                passed=result.probe_passed()
                j.status='succeeded' if passed else 'failed';j.finished_at=now()
                j.last_error=None if passed else result.finish if result.finish!='complete' else 'invalid_json_result'
                j.result={'probe_passed':passed,'finish':result.finish,'requested_model':spec['remote_id'],
                    'returned_model':result.model,'provider_request_id':result.request_id,
                    'input_tokens':result.input_tokens,'output_tokens':result.output_tokens,
                    'authorization_current_at_completion':authorized}
                settle(db,row,j,input_tokens=result.input_tokens,output_tokens=result.output_tokens,usage_supported=result.usage_supported)
                m=db.get(AIModel,UUID(spec['model_id']))
                if authorized and m and m.generation==j.generation and m.fingerprint==spec['model_hash'] and m.available:
                    # Unknown billing is not silently dismissed; model probing and local
                    # accounting remain separate, with an unresolved reservation visible.
                    m.probe_state='passed' if passed else 'failed';m.probe_job_id=j.id;m.probe_at=now()
                c.event(db,row,'probe_finished',j.result,j)
            # Costs remain recorded after revocation; authorization cannot undo a sent request.
        db.commit();return True


def tick(database,settings,factory,store):
    maintain(database,settings)
    item=claim(database,settings)
    if item:execute(database,settings,factory,store,item)
    return item is not None
