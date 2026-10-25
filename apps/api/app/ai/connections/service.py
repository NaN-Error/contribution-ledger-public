"""Authorized configuration, immutable quotations and database-owned job creation."""
from datetime import timedelta
from uuid import UUID, uuid4
from sqlalchemy import select,func,text
from app.ai.models import AIConnection,AIModel,AIPrice,AIUsageBucket,AIJob,AIEvent
from app.core.errors import ApiError
from app.policies.service import digest
from app.projects.authorization import project_access,not_found
from app.security.audit import audit
from app.security.tokens import now,utc
from app.providers.contracts import PROBE_VERSION,ADAPTER_VERSION
from app.ai.usage.calculation import token_cost,PROBE_INPUT_ALLOWANCE,PROBE_OUTPUT_LIMIT
from app.security.secrets.store import SecretUnavailable

NOTICE='Provider settings and synthetic compatibility tests only. No project evidence is sent, no AI assessments or contribution decisions are performed, and no financial rights are created.'
BUDGET_NOTICE='Per-connection UTC-calendar-month estimates, not provider invoices or an account-wide spending guarantee. Reused keys, taxes, pricing tiers and external usage are outside this cap. Unknown usage keeps its reservation until reviewed reconciliation.'


def lock_workspace(db,workspace_id):
    # The restricted worker can take the common tenant lock via a narrow function
    # without UPDATE permission on workspaces or any economic table.
    if db.bind.dialect.name=='postgresql':
        db.execute(text('SELECT cl_ai_lock_workspace(:wid)'),{'wid':workspace_id})
    else:
        from app.projects.models import Workspace
        db.scalar(select(Workspace).where(Workspace.id==workspace_id).with_for_update())

def context(db,wid,pid,uid,manage=False,lock=False):
    if lock:lock_workspace(db,wid)
    return project_access(db,wid,pid,uid,manage=manage)

def scoped(db,model,project,id):
    row=db.scalar(select(model).where(model.id==id,model.workspace_id==project.workspace_id,model.project_id==project.id)
        .execution_options(populate_existing=True))
    if row is None:raise not_found()
    return row

def connection(db,project,uid,role,cid,owner=False):
    row=scoped(db,AIConnection,project,cid)
    if row.owner_id!=uid and (owner or not row.allow_project_use or role not in {'admin','reviewer'}):raise not_found()
    return row

def key_context(row):return f'{row.workspace_id}:{row.project_id}:{row.id}:{row.provider}'

def event(db,row,kind,document=None,job=None):
    db.add(AIEvent(workspace_id=row.workspace_id,project_id=row.project_id,connection_id=row.id,
        job_id=job.id if job else None,kind=kind,document=document or {}))

def configuration_check(settings,provider,paid=False):
    if provider=='mock':return
    if (not settings.ai_live_enabled or settings.ai_deployment_mode!='customer_controlled'
        or provider not in settings.ai_permitted_providers or (paid and not settings.ai_paid_probes_enabled)):
        raise ApiError(409,'ai_disabled','The operator has not enabled this provider and operation for this customer-controlled deployment.')

def active(row):
    if not row.enabled:raise ApiError(409,'ai_revoked','This connection has been revoked. Create a new connection rather than reactivating old approval.')

def owner_active(db,row):
    try:
        _,role=context(db,row.workspace_id,row.project_id,row.owner_id)
        if role=='viewer':return False
    except ApiError:return False
    return True

def model_for(db,row,mid,ready=False):
    model=db.scalar(select(AIModel).where(AIModel.id==mid,AIModel.connection_id==row.id,AIModel.project_id==row.project_id))
    if model is None:raise not_found()
    if ready:
        if not model.available or model.generation!=row.generation or not row.last_catalog_at or utc(row.last_catalog_at)<now()-timedelta(hours=48):
            raise ApiError(409,'ai_catalog_stale','Refresh the connection catalog before selecting this model.')
        if model.document.get('text_generation') is False or model.document.get('structured_output') is False:
            raise ApiError(409,'ai_model_incompatible','This model is explicitly incompatible with the text/JSON adapter.')
    return model

def bucket(db,row,month):
    b=db.scalar(select(AIUsageBucket).where(AIUsageBucket.connection_id==row.id,AIUsageBucket.month==month))
    if b is None:
        b=AIUsageBucket(workspace_id=row.workspace_id,project_id=row.project_id,connection_id=row.id,month=month,
                       held_microusd=0,estimated_microusd=0);db.add(b);db.flush()
    return b

def refund(db,row,job):
    if job.accounting_state!='held':return
    b=bucket(db,row,job.month)
    if b.held_microusd<job.reserved_microusd:raise ApiError(409,'ai_usage_integrity','Stored usage requires operator investigation.')
    b.held_microusd-=job.reserved_microusd;job.accounting_state='refunded';job.accounted_microusd=0

def cancel_queued(db,row):
    for j in db.scalars(select(AIJob).where(AIJob.connection_id==row.id,AIJob.status=='queued')).all():
        refund(db,row,j);j.status='cancelled';j.finished_at=now();j.last_error='authorization_changed'
        event(db,row,'job_cancelled',{'cause':'authorization_changed'},j)

def create(db,project,user,role,body,settings,store):
    if role=='viewer':raise ApiError(403,'permission_denied','Read-only members cannot create AI connections.')
    old=db.scalar(select(AIConnection).where(AIConnection.project_id==project.id,AIConnection.owner_id==user.id,AIConnection.request_id==body.request_id))
    if old:
        if old.provider!=body.provider or old.label!=body.label or old.permission_reference!=body.permission_reference or old.monthly_limit_microusd!=body.monthly_limit_microusd or old.allow_project_use!=body.allow_project_use:raise ApiError(409,'idempotency_conflict','The request identifier belongs to another configuration.')
        return old
    configuration_check(settings,body.provider)
    if db.scalar(select(func.count()).select_from(AIConnection).where(AIConnection.project_id==project.id))>=50:
        raise ApiError(409,'ai_connection_limit','This project has reached its connection-record limit.')
    row=AIConnection(id=uuid4(),workspace_id=project.workspace_id,project_id=project.id,owner_id=user.id,
        request_id=body.request_id,provider=body.provider,label=body.label,permission_reference=body.permission_reference,
        monthly_limit_microusd=body.monthly_limit_microusd,allow_project_use=body.allow_project_use,
        generation=1,version=1,enabled=True,next_refresh_at=now())
    job_quota(db,row)
    if body.provider=='mock':
        if body.api_key is not None:raise ApiError(422,'ai_key_unexpected','The synthetic provider must not receive a real API key.')
    else:
        if body.api_key is None:raise ApiError(422,'ai_key_required','A permitted backend-managed API credential is required.')
        try:row.credential_ref=store.write(body.api_key.get_secret_value(),key_context(row))
        except SecretUnavailable:raise ApiError(409,'ai_secret_unavailable','The protected credential store is unavailable or the credential format is invalid.') from None
    db.add(row);db.flush()
    audit(db,'ai_connection_created',actor_id=user.id,workspace_id=project.workspace_id,project_id=project.id,
          subject_id=row.id,reason=body.reason,details={'provider':row.provider})
    enqueue_catalog(db,row,uuid4(),user.id,settings)
    return row

def update(db,row,user,body,settings):
    active(row)
    if row.version!=body.expected_version:raise ApiError(409,'stale_version','Refresh this connection before changing its settings.')
    b=bucket(db,row,now().strftime('%Y-%m'))
    if body.monthly_limit_microusd<b.held_microusd+b.estimated_microusd:
        raise ApiError(409,'ai_budget_committed','The limit cannot be lowered below estimated and reserved usage.')
    changed=row.allow_project_use!=body.allow_project_use
    row.label=body.label;row.monthly_limit_microusd=body.monthly_limit_microusd;row.allow_project_use=body.allow_project_use;row.version+=1
    if changed:
        row.generation+=1;cancel_queued(db,row);row.next_refresh_at=now()
        enqueue_catalog(db,row,uuid4(),user.id,settings)
    event(db,row,'settings_changed',{'version':row.version,'generation':row.generation,'allow_project_use':row.allow_project_use,
        'monthly_limit_microusd':row.monthly_limit_microusd})
    audit(db,'ai_connection_changed',actor_id=user.id,workspace_id=row.workspace_id,project_id=row.project_id,subject_id=row.id,reason=body.reason)

def rotate(db,row,user,body,store,settings):
    active(row);configuration_check(settings,row.provider)
    if row.provider=='mock':raise ApiError(409,'ai_mock_key','Synthetic connections have no credentials to rotate.')
    if row.version!=body.expected_version:raise ApiError(409,'stale_version','Refresh the connection before rotating its credential.')
    try:ref=store.write(body.api_key.get_secret_value(),key_context(row))
    except SecretUnavailable:raise ApiError(409,'ai_secret_unavailable','Protected credential storage is unavailable or invalid.') from None
    old=row.credential_ref;row.credential_ref=ref;row.generation+=1;row.version+=1;cancel_queued(db,row)
    row.next_refresh_at=now();enqueue_catalog(db,row,uuid4(),user.id,settings)
    event(db,row,'credential_rotated',{'generation':row.generation})
    audit(db,'ai_credential_rotated',actor_id=user.id,workspace_id=row.workspace_id,project_id=row.project_id,subject_id=row.id,reason=body.reason)
    return old

def revoke(db,row,user,body):
    if row.version!=body.expected_version:raise ApiError(409,'stale_version','Refresh the connection before revocation.')
    if not row.enabled:return
    row.enabled=False;row.allow_project_use=False;row.version+=1;row.generation+=1
    cancel_queued(db,row)
    event(db,row,'connection_revoked',{'generation':row.generation})
    audit(db,'ai_connection_revoked',actor_id=user.id,workspace_id=row.workspace_id,project_id=row.project_id,subject_id=row.id,reason=body.reason)

def job_quota(db,row):
    if db.scalar(select(func.count()).select_from(AIJob).where(AIJob.project_id==row.project_id))>=10000:
        raise ApiError(409,'ai_job_limit','The project has reached its AI job-record limit. Review retention with the operator.')

def enqueue_catalog(db,row,request_id,uid,settings):
    active(row);configuration_check(settings,row.provider)
    old=db.scalar(select(AIJob).where(AIJob.connection_id==row.id,AIJob.request_id==request_id))
    if old:
        if old.kind!='catalog':raise ApiError(409,'idempotency_conflict','That request identifier is already used.')
        return old
    pending=db.scalar(select(AIJob).where(AIJob.connection_id==row.id,AIJob.kind=='catalog',AIJob.generation==row.generation,
        AIJob.status.in_(['queued','running'])).limit(1))
    if pending:return pending
    job_quota(db,row)
    job=AIJob(id=uuid4(),workspace_id=row.workspace_id,project_id=row.project_id,connection_id=row.id,
        requested_by=uid,request_id=request_id,kind='catalog',status='queued',generation=row.generation,
        specification={'adapter_version':ADAPTER_VERSION},reserved_microusd=0,accounting_state='none',attempts=0,not_before=max(now(),utc(row.retry_not_before)) if row.retry_not_before else now())
    db.add(job);db.flush();event(db,row,'catalog_queued',job=job);row.next_refresh_at=now()+timedelta(hours=24)
    return job

def price_create(db,row,user,body):
    active(row);m=model_for(db,row,body.model_id,ready=True)
    expires=utc(body.valid_until)
    if expires<=now() or expires>now()+timedelta(days=31):raise ApiError(422,'ai_price_expiry','Price review must expire within 31 days.')
    if row.provider!='mock':
        from urllib.parse import urlsplit
        try:
            u=urlsplit(body.source_reference); port=u.port
        except ValueError:
            raise ApiError(422,'ai_price_source','A valid official provider HTTPS pricing reference is required.') from None
        allowed={'openai':{'openai.com','developers.openai.com','platform.openai.com'},
            'anthropic':{'anthropic.com','www.anthropic.com','platform.claude.com','claude.com'},
            'gemini':{'ai.google.dev','cloud.google.com'}}[row.provider]
        if u.scheme!='https' or u.hostname not in allowed or u.username or u.password or port not in {None,443}:
            raise ApiError(422,'ai_price_source','Use an official provider HTTPS pricing reference. It is recorded, not automatically fetched or verified.')
        if body.input_rate==0 or body.output_rate==0:raise ApiError(422,'ai_zero_live_price','Use conservative nonzero standard text rates for live probes, including nominally free access.')
    elif body.input_rate or body.output_rate:raise ApiError(422,'ai_mock_price','Synthetic calls have zero rates.')
    if db.scalar(select(func.count()).select_from(AIPrice).where(AIPrice.connection_id==row.id))>=5000:
        raise ApiError(409,'ai_price_limit','This connection has reached its price-record limit.')
    record={'model_id':str(m.id),'input_rate':body.input_rate,'output_rate':body.output_rate,'source_reference':body.source_reference,
        'valid_until':expires.isoformat(),'reason':body.reason}
    price=AIPrice(workspace_id=row.workspace_id,project_id=row.project_id,connection_id=row.id,model_id=m.id,
        created_by=user.id,input_rate=body.input_rate,output_rate=body.output_rate,source_reference=body.source_reference,
        valid_until=expires,reason=body.reason,fingerprint=digest(record))
    db.add(price);db.flush();event(db,row,'price_reviewed',{'price_id':str(price.id),'fingerprint':price.fingerprint})
    return price

def quote(db,row,mid,settings):
    active(row);configuration_check(settings,row.provider,paid=True)
    m=model_for(db,row,mid,ready=True)
    price=db.scalar(select(AIPrice).where(AIPrice.connection_id==row.id,AIPrice.model_id==m.id).order_by(AIPrice.created_at.desc(),AIPrice.id.desc()).limit(1))
    if price is None or utc(price.valid_until)<=now():raise ApiError(409,'ai_price_unknown','Add a current payer-reviewed price before requesting a probe.')
    for key,minimum in [('input_limit',PROBE_INPUT_ALLOWANCE),('output_limit',PROBE_OUTPUT_LIMIT)]:
        if m.document.get(key) is not None and m.document[key]<minimum:raise ApiError(409,'ai_model_limit','The selected model does not support the probe token allowance.')
    micros=token_cost(PROBE_INPUT_ALLOWANCE,PROBE_OUTPUT_LIMIT,price.input_rate,price.output_rate)
    data={'connection_id':str(row.id),'generation':row.generation,'model_id':str(m.id),'remote_id':m.remote_id,
        'model_hash':m.fingerprint,'price_id':str(price.id),'price_hash':price.fingerprint,
        'input_rate':price.input_rate,'output_rate':price.output_rate,'price_valid_until':utc(price.valid_until).isoformat(),
        'month':now().strftime('%Y-%m'),'max_output_tokens':PROBE_OUTPUT_LIMIT,'input_token_allowance':PROBE_INPUT_ALLOWANCE,
        'reservation_microusd':micros,'prompt_version':PROBE_VERSION,'adapter_version':ADAPTER_VERSION}
    return {'specification':data,'quote_hash':digest(data),'notice':BUDGET_NOTICE,
        'synthetic_prompt':'Connection compatibility test using synthetic data only. Return exactly the JSON object {"ok": true}.'}

def enqueue_probe(db,row,user,mid,body,settings):
    old=db.scalar(select(AIJob).where(AIJob.connection_id==row.id,AIJob.request_id==body.request_id))
    if old:
        if old.kind!='probe' or old.specification.get('model_id')!=str(mid) or digest(old.specification)!=body.quote_hash:
            raise ApiError(409,'idempotency_conflict','That request identifier belongs to another probe.')
        return old
    q=quote(db,row,mid,settings);s=q['specification']
    if body.quote_hash!=q['quote_hash'] or body.confirmed_reservation_microusd!=s['reservation_microusd']:
        raise ApiError(409,'ai_quote_stale','Review a fresh cost quotation before requesting the probe.')
    if db.scalar(select(func.count()).select_from(AIJob).where(AIJob.connection_id==row.id,AIJob.kind.in_(['probe','assessment']),AIJob.accounting_state.in_(['held','uncertain'])))>=5:
        raise ApiError(409,'ai_unresolved_limit','Resolve or finish existing probe requests before adding more.')
    b=bucket(db,row,s['month']);cost=s['reservation_microusd']
    if b.held_microusd+b.estimated_microusd+cost>row.monthly_limit_microusd:
        raise ApiError(409,'ai_budget_exhausted','This connection has insufficient unreserved monthly budget.')
    job_quota(db,row);b.held_microusd+=cost
    j=AIJob(id=uuid4(),workspace_id=row.workspace_id,project_id=row.project_id,connection_id=row.id,requested_by=user.id,
        request_id=body.request_id,kind='probe',status='queued',generation=row.generation,specification=s,
        month=s['month'],reserved_microusd=cost,accounting_state='held',attempts=0,not_before=max(now(),utc(row.retry_not_before)) if row.retry_not_before else now())
    db.add(j);db.flush();event(db,row,'probe_reserved',{'reserved_microusd':cost,'quote_hash':q['quote_hash']},j)
    return j

def connection_view(row,uid):
    result={k:getattr(row,k) for k in ['id','owner_id','provider','label','permission_reference','enabled','version','generation',
        'allow_project_use','monthly_limit_microusd','next_refresh_at','last_catalog_at','last_error','retry_not_before','created_at']}
    result.update(can_manage=row.owner_id==uid,credential_state='not required' if row.provider=='mock' else 'stored; never returned')
    return result

def model_view(m):return {k:getattr(m,k) for k in ['id','remote_id','document','fingerprint','generation','available','observed_at','probe_state','probe_job_id','probe_at']}
def price_view(p):return {k:getattr(p,k) for k in ['id','model_id','input_rate','output_rate','source_reference','valid_until','fingerprint','reason','created_at']}
def job_view(j):return {k:getattr(j,k) for k in ['id','connection_id','requested_by','kind','status','generation','specification','month',
    'reserved_microusd','accounting_state','accounted_microusd','attempts','not_before','dispatched_at','finished_at','last_error','result','created_at']}
