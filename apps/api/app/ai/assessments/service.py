"""Data approval, explicit payer dispatch, validated suggestions and human commentary.

There is intentionally no ledger-write or financial command in this module.
"""
from datetime import timedelta
import json
from uuid import UUID,uuid4
from sqlalchemy import select,func
from app.ai.assessments.models import AIReviewPacket,AIReviewPlan,AIReviewGrant,AIReviewRevocation,AIReviewResult,AIReviewFeedback
from app.ai.models import AIConnection,AIModel,AIPrice,AIJob,AIProfile
from app.ai.connections import service as c
from app.ai.profiles import service as profiles
from app.ai.packets import service as packets
from app.ai.packets.redaction import redact
from app.ai.assessments.prompt import generation_material,prompt_hash,PROMPT_VERSION,SCHEMA_VERSION,RUBRIC_VERSION
from app.ai.validation.output import validate_output,InvalidAssessment
from app.ai.usage.calculation import token_cost
from app.core.errors import ApiError
from app.policies.service import digest
from app.security.audit import audit
from app.security.tokens import now,utc
from app.providers.contracts import GenerationRequest,ADAPTER_VERSION

NOTICE='AI suggestions are not independent acceptance, contribution credit, proof of correctness or financial decisions. Inspect original evidence and separately complete the existing human review.'


def replay(db,model,project,actor,body):
    previous=db.scalar(select(model).where(model.project_id==project.id,model.created_by==actor.id,model.request_id==body.request_id))
    if previous and previous.request_hash!=digest(body.model_dump(mode='json')):
        raise ApiError(409,'idempotency_conflict','That request identifier belongs to a different operation.')
    return previous


def plan_visible(db,plan,user_id,role):
    packets.review_access(role)
    if plan.mode=='advisory':
        owner=db.scalar(select(AIConnection.owner_id).where(AIConnection.id==plan.connection_id))
        if user_id not in {plan.created_by,owner} and role!='admin':raise c.not_found()


def scoped_plan(db,project,user_id,role,plan_id):
    plan=c.scoped(db,AIReviewPlan,project,plan_id);plan_visible(db,plan,user_id,role);return plan


def create_plan(db,project,actor,role,body,settings):
    packets.review_access(role)
    old=replay(db,AIReviewPlan,project,actor,body)
    if old:return old
    packet=c.scoped(db,AIReviewPacket,project,body.packet_id);packets.verify(packet)
    if packet.content_hash!=body.reviewed_packet_hash or not packets.current(db,packet):
        raise ApiError(409,'ai_packet_stale','Inspect a current packet before proposing a run.')
    profile=c.scoped(db,AIProfile,project,packet.profile_id);packets.profile_contract(profile)
    row=c.connection(db,project,actor.id,role,profile.connection_id)
    m=c.model_for(db,row,UUID(profile.definition['model_id']),ready=True);profiles.ready(db,row,m)
    if profile.definition['credential_generation']!=row.generation or profile.definition['model_metadata_hash']!=m.fingerprint:
        raise ApiError(409,'ai_profile_stale','Review a successor profile after the connection/model changed.')
    _,payer_role=c.context(db,project.workspace_id,project.id,row.owner_id)
    packets.review_access(payer_role)
    current=profiles.active_profile(db,project)
    if body.mode=='official' and (not current or current.id!=profile.id):
        raise ApiError(409,'ai_official_profile','Official runs require the currently approved project profile. Alternatives must be marked advisory.')
    lineage=select(AIReviewPlan).join(AIReviewPacket,AIReviewPacket.id==AIReviewPlan.packet_id).where(AIReviewPlan.project_id==project.id,
        AIReviewPlan.package_id==packet.package_id,AIReviewPacket.deliverable_id==packet.deliverable_id,AIReviewPlan.mode==body.mode)
    # Official history is project-wide. A private advisory lineage is per requester,
    # so an unseen peer comparison cannot block another reviewer or leak its ID.
    if body.mode=='advisory':lineage=lineage.where(AIReviewPlan.created_by==actor.id)
    previous=db.scalar(lineage.order_by(AIReviewPlan.created_at.desc(),AIReviewPlan.id.desc()).limit(1))
    if (previous.id if previous else None)!=body.prior_plan_id:
        raise ApiError(409,'ai_rerun_review','A prior run plan exists or changed. Inspect its result and supply its ID with an explicit rerun reason.')
    if db.scalar(select(func.count()).select_from(AIReviewPlan).where(AIReviewPlan.project_id==project.id))>=5000:
        raise ApiError(409,'ai_run_limit','This pilot project reached its assessment-plan limit.')
    definition={'packet_hash':packet.content_hash,'prompt_hash':packet.prompt_hash,'profile_hash':profile.fingerprint,
        'provider':row.provider,'payer_id':str(row.owner_id),'connection_generation':row.generation,'mode':body.mode,
        'requested_model':m.remote_id,'max_output_tokens':profile.definition['settings']['max_output_tokens'],
        'data_policy_reference':profile.definition['data_policy_reference'],
        'audience':'project_reviewers_and_administrators' if body.mode=='official' else 'requester_payer_and_project_administrators',
        'notice':'Permission to inspect evidence, permission to disclose this packet, and permission to pay are separate. No model result can approve a contribution.'}
    plan=AIReviewPlan(id=uuid4(),workspace_id=project.workspace_id,project_id=project.id,package_id=packet.package_id,
        packet_id=packet.id,profile_id=profile.id,connection_id=row.id,created_by=actor.id,mode=body.mode,
        prior_plan_id=body.prior_plan_id,request_id=body.request_id,request_hash=digest(body.model_dump(mode='json')),
        definition=definition,content_hash=digest(definition),reason=body.reason)
    db.add(plan);db.flush()
    audit(db,'ai_assessment_planned',actor_id=actor.id,workspace_id=project.workspace_id,project_id=project.id,
        subject_id=plan.id,reason='An explicit assessment or rerun was planned; nothing was sent.',details={'mode':body.mode,'prior_plan_id':str(body.prior_plan_id) if body.prior_plan_id else None})
    return plan


def verify_plan(db,plan):
    packet=db.get(AIReviewPacket,plan.packet_id);profile=db.get(AIProfile,plan.profile_id)
    if not packet or not profile or packet.project_id!=plan.project_id or packet.workspace_id!=plan.workspace_id or packet.profile_id!=profile.id:
        raise ApiError(409,'ai_plan_integrity','The assessment plan does not reconcile.')
    packets.verify(packet);packets.profile_contract(profile)
    if (digest(plan.definition)!=plan.content_hash or plan.definition['packet_hash']!=packet.content_hash
        or plan.definition['prompt_hash']!=packet.prompt_hash or plan.definition['profile_hash']!=profile.fingerprint):
        raise ApiError(409,'ai_plan_integrity','The assessment plan fingerprint does not reconcile.')
    return packet,profile


def approve_data(db,project,actor,plan,body):
    _,role=c.context(db,project.workspace_id,project.id,actor.id,manage=True)
    packet,_=verify_plan(db,plan)
    if not packets.current(db,packet) or body.reviewed_plan_hash!=plan.content_hash:
        raise ApiError(409,'ai_plan_stale','Review a current outbound packet and its exact plan.')
    old=db.scalar(select(AIReviewGrant).where(AIReviewGrant.plan_id==plan.id))
    if old:
        if (old.reviewed_hash!=body.reviewed_plan_hash or old.permission_reference!=body.permission_reference
            or utc(old.valid_until)!=utc(body.valid_until) or old.approved_by!=actor.id):
            raise ApiError(409,'ai_grant_exists','A different immutable data approval already exists. Create an explicit new run plan.')
        return old
    if db.scalar(select(AIReviewRevocation.id).where(AIReviewRevocation.plan_id==plan.id)):
        raise ApiError(409,'ai_data_revoked','This plan was revoked and cannot be reactivated.')
    if not now()<utc(body.valid_until)<=now()+timedelta(hours=24):
        raise ApiError(422,'ai_grant_expiry','Approve a future expiry no more than 24 hours away.')
    grant=AIReviewGrant(workspace_id=project.workspace_id,project_id=project.id,plan_id=plan.id,
        approved_by=actor.id,reviewed_hash=body.reviewed_plan_hash,permission_reference=body.permission_reference,
        valid_until=body.valid_until,reason=body.reason)
    db.add(grant);db.flush()
    audit(db,'ai_packet_disclosure_approved',actor_id=actor.id,workspace_id=project.workspace_id,project_id=project.id,
        subject_id=plan.id,reason='Administrator declared permission to disclose this reviewed packet for one run.',details={'grant_id':str(grant.id)})
    return grant


def revoke(db,project,actor,role,plan,body):
    owner=db.scalar(select(AIConnection.owner_id).where(AIConnection.id==plan.connection_id))
    if role!='admin' and actor.id not in {plan.created_by,owner}:raise c.not_found()
    old=db.scalar(select(AIReviewRevocation).where(AIReviewRevocation.plan_id==plan.id))
    if old:return old
    rev=AIReviewRevocation(workspace_id=project.workspace_id,project_id=project.id,plan_id=plan.id,revoked_by=actor.id,reason=body.reason)
    db.add(rev);db.flush()
    j=db.scalar(select(AIJob).where(AIJob.assessment_plan_id==plan.id))
    if j and j.status=='queued':
        from app.ai.jobs import _cancel
        _cancel(db,db.get(AIConnection,plan.connection_id),j,'data_permission_revoked')
    audit(db,'ai_packet_disclosure_revoked',actor_id=actor.id,workspace_id=project.workspace_id,project_id=project.id,
        subject_id=plan.id,reason='Future disclosure withdrawn; already-sent requests and external copies cannot be recalled.')
    return rev


def allowed(db,plan,row,settings,*,require_paid_flag=True):
    """All authorities are rechecked by API and worker, including before/after send."""
    packet,profile=verify_plan(db,plan)
    if (row.id!=plan.connection_id or row.workspace_id!=plan.workspace_id or row.project_id!=plan.project_id
        or row.generation!=plan.definition['connection_generation'] or not row.enabled or not row.allow_project_use):
        raise ApiError(409,'ai_assessment_authorization','Connection authorization changed.')
    if row.provider!='mock':
        c.configuration_check(settings,row.provider,paid=require_paid_flag)
        if not settings.ai_evidence_enabled:raise ApiError(409,'ai_evidence_disabled','The operator must separately enable live evidence disclosure. Synthetic assessments remain available.')
    if not packets.current(db,packet):raise ApiError(409,'ai_packet_stale','Submitted scope, evidence, retirement or acceptance changed. Prepare a new packet.')
    grant=db.scalar(select(AIReviewGrant).where(AIReviewGrant.plan_id==plan.id))
    if (not grant or grant.reviewed_hash!=plan.content_hash or utc(grant.valid_until)<=now()
        or db.scalar(select(AIReviewRevocation.id).where(AIReviewRevocation.plan_id==plan.id))):
        raise ApiError(409,'ai_data_approval','A current explicit administrator data approval is required.')
    project,_=c.context(db,plan.workspace_id,plan.project_id,grant.approved_by,manage=True)
    for uid in {plan.created_by,row.owner_id}:
        _,role=c.context(db,plan.workspace_id,plan.project_id,uid);packets.review_access(role)
    m=c.model_for(db,row,UUID(profile.definition['model_id']),ready=True)
    profiles.ready(db,row,m)
    if m.fingerprint!=profile.definition['model_metadata_hash']:raise ApiError(409,'ai_profile_stale','Model capabilities changed.')
    if plan.mode=='official':
        current=profiles.active_profile(db,project)
        if not current or current.id!=profile.id:raise ApiError(409,'ai_official_profile','The official evaluator changed; review a new plan prospectively.')
    return packet,profile,grant,m


def quote(db,project,actor,role,plan,settings):
    row=c.connection(db,project,actor.id,role,plan.connection_id,owner=True)
    packet,profile,grant,m=allowed(db,plan,row,settings)
    material=generation_material(packet.payload)
    # Conservative byte allowance + envelope margin; not a provider tokenization guarantee.
    allowance=sum(len(json.dumps(material[k],ensure_ascii=True).encode()) for k in ('instructions','prompt','schema'))+1024
    output=profile.definition['settings']['max_output_tokens']
    if (m.document.get('input_limit') is not None and allowance>m.document['input_limit']
        or m.document.get('output_limit') is not None and output>m.document['output_limit']):
        raise ApiError(409,'ai_model_limit','The selected model cannot fit this conservative input/output allowance. Select fewer sources or another explicitly reviewed profile.')
    price=db.scalar(select(AIPrice).where(AIPrice.connection_id==row.id,AIPrice.model_id==m.id)
        .order_by(AIPrice.created_at.desc(),AIPrice.id.desc()).limit(1))
    if not price or utc(price.valid_until)<=now():raise ApiError(409,'ai_price_unknown','Add a current payer-reviewed text price before generation.')
    cost=token_cost(allowance,output,price.input_rate,price.output_rate)
    if cost>10**9:raise ApiError(409,'ai_quote_limit','This request exceeds the pilot per-call reservation limit.')
    data={'plan_id':str(plan.id),'plan_hash':plan.content_hash,'packet_id':str(packet.id),'packet_hash':packet.content_hash,
        'prompt_hash':packet.prompt_hash,'profile_id':str(profile.id),'profile_hash':profile.fingerprint,
        'grant_id':str(grant.id),'grant_expires':utc(grant.valid_until).isoformat(),'mode':plan.mode,
        'connection_id':str(row.id),'generation':row.generation,'model_id':str(m.id),'remote_id':m.remote_id,
        'model_hash':m.fingerprint,'price_id':str(price.id),'price_hash':price.fingerprint,
        'input_rate':price.input_rate,'output_rate':price.output_rate,'price_valid_until':utc(price.valid_until).isoformat(),
        'month':now().strftime('%Y-%m'),'max_output_tokens':output,'input_token_allowance':allowance,
        'reservation_microusd':cost,'prompt_version':PROMPT_VERSION,'schema_version':SCHEMA_VERSION,
        'rubric_version':RUBRIC_VERSION,'adapter_version':ADAPTER_VERSION}
    return {'specification':data,'quote_hash':digest(data),'notice':c.BUDGET_NOTICE,
        'data_notice':'This sends the exact reviewed redacted packet, not only synthetic text. An API request cannot be recalled. A nonfinite/malformed/truncated/refused response cannot become a finding.'}


def enqueue(db,project,actor,role,plan,body,settings):
    row=c.connection(db,project,actor.id,role,plan.connection_id,owner=True)
    old=db.scalar(select(AIJob).where(AIJob.connection_id==row.id,AIJob.request_id==body.request_id))
    if old:
        if old.kind!='assessment' or old.assessment_plan_id!=plan.id or digest(old.specification)!=body.quote_hash or old.reserved_microusd!=body.confirmed_reservation_microusd:
            raise ApiError(409,'idempotency_conflict','That request identifier belongs to another operation.')
        return old
    if db.scalar(select(AIJob.id).where(AIJob.assessment_plan_id==plan.id)):
        raise ApiError(409,'ai_plan_used','This data approval is single-use. Inspect the result and propose an explicit rerun instead.')
    q=quote(db,project,actor,role,plan,settings);s=q['specification']
    if q['quote_hash']!=body.quote_hash or s['reservation_microusd']!=body.confirmed_reservation_microusd:
        raise ApiError(409,'ai_quote_stale','Review a fresh quotation and packet before approving a request.')
    if db.scalar(select(func.count()).select_from(AIJob).where(AIJob.connection_id==row.id,AIJob.accounting_state.in_(['held','uncertain'])))>=5:
        raise ApiError(409,'ai_unresolved_limit','Finish or reconcile pending generation before reserving another run.')
    b=c.bucket(db,row,s['month']);cost=s['reservation_microusd']
    if b.held_microusd+b.estimated_microusd+cost>row.monthly_limit_microusd:
        raise ApiError(409,'ai_budget_exhausted','Insufficient unreserved connection budget.')
    c.job_quota(db,row);b.held_microusd+=cost
    job=AIJob(id=uuid4(),workspace_id=project.workspace_id,project_id=project.id,connection_id=row.id,
        requested_by=actor.id,request_id=body.request_id,kind='assessment',assessment_plan_id=plan.id,status='queued',
        generation=row.generation,specification=s,month=s['month'],reserved_microusd=cost,accounting_state='held',
        attempts=0,not_before=max(now(),utc(row.retry_not_before)) if row.retry_not_before else now())
    db.add(job);db.flush();c.event(db,row,'assessment_reserved',{'plan_id':str(plan.id),'mode':plan.mode,'reserved_microusd':cost},job)
    return job


def job_current(db,row,job,settings):
    try:
        plan=db.get(AIReviewPlan,job.assessment_plan_id)
        if not plan or job.requested_by!=row.owner_id:return False
        packet,profile,grant,m=allowed(db,plan,row,settings)
        s=job.specification;price=db.get(AIPrice,UUID(s['price_id']))
        return (job.generation==row.generation and s['plan_hash']==plan.content_hash and s['packet_hash']==packet.content_hash
            and s['prompt_hash']==packet.prompt_hash and s['profile_hash']==profile.fingerprint
            and s['model_hash']==m.fingerprint and s['month']==now().strftime('%Y-%m')
            and price is not None and price.fingerprint==s['price_hash'] and utc(price.valid_until)>now()
            and s['prompt_version']==PROMPT_VERSION and s['schema_version']==SCHEMA_VERSION and s['adapter_version']==ADAPTER_VERSION)
    except (ApiError,KeyError,ValueError,TypeError):return False


def generation_request(db,job):
    plan=db.get(AIReviewPlan,job.assessment_plan_id);packet,profile=verify_plan(db,plan)
    m=generation_material(packet.payload)
    return GenerationRequest(job.specification['remote_id'],m['prompt'],m['schema'],
        job.specification['max_output_tokens'],instructions=m['instructions'])


def finish(db,job,result,authorized):
    plan=db.get(AIReviewPlan,job.assessment_plan_id);packet=db.get(AIReviewPacket,plan.packet_id)
    document=None;status='authorization_changed'
    if authorized:
        status=result.finish
        if result.finish=='complete':
            try:
                document=validate_output(result.content,packet.payload)
                _,redactions=redact(json.dumps(document,ensure_ascii=False))
                if redactions:raise InvalidAssessment('sensitive_output')
                status='valid'
            except InvalidAssessment as exc:status=str(exc);document=None
    metadata={'provider':plan.definition['provider'],'requested_model':job.specification['remote_id'],
        'returned_model':result.model,'provider_request_id':result.request_id,'finish':result.finish,
        'input_tokens':result.input_tokens,'output_tokens':result.output_tokens,'usage_supported':result.usage_supported,
        'packet_hash':packet.content_hash,'prompt_hash':packet.prompt_hash,'profile_hash':plan.definition['profile_hash'],
        'prompt_version':PROMPT_VERSION,'schema_version':SCHEMA_VERSION,'rubric_version':RUBRIC_VERSION,
        'authorization_current_at_completion':authorized,'mode':plan.mode,'notice':NOTICE,
        'synthetic':plan.definition['provider']=='mock'}
    value=AIReviewResult(id=uuid4(),workspace_id=job.workspace_id,project_id=job.project_id,plan_id=plan.id,job_id=job.id,
        status=status,document=document,metadata_record=metadata,content_hash=digest({'status':status,'document':document,'metadata':metadata}))
    db.add(value);db.flush()
    # Generic job/event views contain no source excerpts, explanations or names.
    job.result={'assessment_id':str(value.id),'validation':status,'authorization_current_at_completion':authorized,
        'input_tokens':result.input_tokens,'output_tokens':result.output_tokens,'requested_model':job.specification['remote_id'],
        'returned_model':result.model,'provider_request_id':result.request_id,'finish':result.finish}
    return value


def plan_view(db,project,actor_id,role,plan):
    plan_visible(db,plan,actor_id,role);packet,profile=verify_plan(db,plan)
    grant=db.scalar(select(AIReviewGrant).where(AIReviewGrant.plan_id==plan.id))
    rev=db.scalar(select(AIReviewRevocation).where(AIReviewRevocation.plan_id==plan.id))
    job=db.scalar(select(AIJob).where(AIJob.assessment_plan_id==plan.id))
    result=db.scalar(select(AIReviewResult).where(AIReviewResult.plan_id==plan.id))
    return {**{k:getattr(plan,k) for k in ('id','packet_id','profile_id','connection_id','package_id','created_by','mode','prior_plan_id','definition','content_hash','reason','created_at')},
        'packet_stale':not packets.current(db,packet),'can_approve_data':role=='admin',
        'deliverable_id':packet.deliverable_id,'can_revoke':role=='admin' or actor_id==plan.created_by or str(actor_id)==plan.definition['payer_id'],
        'can_pay':str(actor_id)==plan.definition['payer_id'],
        'grant':None if not grant else {k:getattr(grant,k) for k in ('id','approved_by','reviewed_hash','permission_reference','valid_until','reason','created_at')},
        'revoked':rev is not None,'job':c.job_view(job) if job else None,'result_id':result.id if result else None,'notice':NOTICE}


def result_view(db,project,actor_id,role,result):
    plan=c.scoped(db,AIReviewPlan,project,result.plan_id);plan_visible(db,plan,actor_id,role)
    packet,profile=verify_plan(db,plan)
    if digest({'status':result.status,'document':result.document,'metadata':result.metadata_record})!=result.content_hash:
        raise ApiError(409,'ai_result_integrity','The preserved assessment failed its fingerprint check.')
    return {**{k:getattr(result,k) for k in ('id','plan_id','job_id','status','document','content_hash','created_at')},
        'metadata':result.metadata_record,'packet':packets.view(db,packet),'mode':plan.mode,'notice':NOTICE}


def feedback(db,project,actor,role,result,body,storage):
    packets.review_access(role)
    old=replay(db,AIReviewFeedback,project,actor,body)
    if old:return old
    plan=scoped_plan(db,project,actor.id,role,result.plan_id);packet,profile=verify_plan(db,plan)
    if digest({'status':result.status,'document':result.document,'metadata':result.metadata_record})!=result.content_hash:
        raise ApiError(409,'ai_result_integrity','Inspect the preserved result integrity before recording feedback.')
    if result.status!='valid' or result.content_hash!=body.reviewed_result_hash or not packets.current(db,packet):
        raise ApiError(409,'ai_feedback_stale','Only a validated current assessment can receive new review feedback.')
    from app.reviews.service import get_review,check_current
    from app.reviews.models import ReviewAssignment
    from app.contributions.work_packages.service import get_package
    review=get_review(db,project,body.review_id);package=get_package(db,project,packet.package_id)
    if (review.kind!='award' or review.package_id!=packet.package_id or review.deliverable_id!=packet.deliverable_id
        or review.submission_id!=packet.submission_id or review.target['scope_hash']!=packet.capture['scope_hash']
        or review.target['evidence_snapshot_hash']!=packet.capture['evidence_snapshot_hash']):raise c.not_found()
    if not db.get(ReviewAssignment,(review.id,actor.id)) or str(actor.id) in review.target['conflict_ids']:
        raise ApiError(403,'ai_independent_reviewer','Only an assigned, currently authorized independent reviewer can record feedback for this review.')
    check_current(db,project,package,review,storage)
    if body.criterion_id not in {c['id'] for c in packet.payload['criteria']}:raise c.not_found()
    value=AIReviewFeedback(id=uuid4(),workspace_id=project.workspace_id,project_id=project.id,package_id=packet.package_id,
        result_id=result.id,review_id=review.id,created_by=actor.id,criterion_id=body.criterion_id,action=body.action,
        reason=body.reason,replacement_text=body.replacement_text,reviewed_result_hash=body.reviewed_result_hash,
        request_id=body.request_id,request_hash=digest(body.model_dump(mode='json')))
    db.add(value);db.flush()
    audit(db,'ai_assessment_feedback',actor_id=actor.id,workspace_id=project.workspace_id,project_id=project.id,
        subject_id=result.id,reason='An independent reviewer recorded an observation about an AI suggestion; no acceptance decision or award was created.',
        details={'action':body.action,'review_id':str(review.id),'criterion_id':body.criterion_id})
    return value
