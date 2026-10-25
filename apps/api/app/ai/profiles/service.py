"""Immutable, explicitly approved evaluator configuration; not evidence evaluation."""
from datetime import timedelta
from uuid import UUID
from sqlalchemy import select,func
from app.ai.models import AIConnection,AIModel,AIProfile,AIProfileApproval,AIJob
from app.ai.connections import service as c
from app.core.errors import ApiError
from app.policies.service import digest
from app.security.tokens import now,utc
from app.security.audit import audit
from app.providers.contracts import ADAPTER_VERSION


def active_profile(db,project):
    return db.scalar(select(AIProfile).join(AIProfileApproval,AIProfileApproval.profile_id==AIProfile.id)
        .where(AIProfile.project_id==project.id).order_by(AIProfile.version.desc()).limit(1))

def ready(db,row,m):
    c.active(row)
    if not row.allow_project_use or not c.owner_active(db,row):raise ApiError(409,'ai_payer_not_authorized','The connection owner must currently authorize project use.')
    if row.last_error in {'authentication','permission','model_unavailable','disabled'}:
        raise ApiError(409,'ai_access_unavailable','Resolve the latest catalog authorization failure before approving a profile.')
    if m.probe_state!='passed' or not m.probe_at or utc(m.probe_at)<now()-timedelta(days=7):
        raise ApiError(409,'ai_probe_required','A current successful synthetic JSON probe is required. This is not a quality evaluation.')
    job=db.get(AIJob,m.probe_job_id)
    if (job is None or job.connection_id!=row.id or job.project_id!=row.project_id or job.workspace_id!=row.workspace_id
        or job.status!='succeeded' or not job.result or job.result.get('probe_passed') is not True
        or job.result.get('authorization_current_at_completion') is not True
        or job.specification.get('model_id')!=str(m.id) or job.generation!=row.generation
        or job.specification.get('model_hash')!=m.fingerprint):
        raise ApiError(409,'ai_probe_stale','The provider/model configuration changed since its probe.')

def create(db,project,user,body,settings):
    row=c.scoped(db,AIConnection,project,body.connection_id);m=c.model_for(db,row,body.model_id,ready=True)
    c.configuration_check(settings,row.provider);ready(db,row,m)
    version=(db.scalar(select(func.max(AIProfile.version)).where(AIProfile.project_id==project.id)) or 0)+1
    if version>1000:raise ApiError(409,'ai_profile_limit','The project has reached its profile-version limit.')
    definition={'title':body.title,'provider':row.provider,'connection_id':str(row.id),'credential_generation':row.generation,
        'model_id':str(m.id),'requested_model':m.remote_id,'model_metadata_hash':m.fingerprint,
        'compatibility_probe_id':str(m.probe_job_id),'adapter_version':ADAPTER_VERSION,
        'prompt_version':'evidence-review-v1-pending-phase11','rubric_version':'project-policy-bound-pending-phase11',
        'schema_version':'evidence-assessment-v1-pending-phase11','settings':{'max_output_tokens':256,'tools':False,'automatic_fallback':False},
        'data_policy_reference':body.data_policy_reference,'reason':body.reason,
        'notice':'Foundation profile only. No evidence may be dispatched until phase-11 packet, policy, privacy and per-call spending checks are implemented.'}
    if body.purpose=='evidence':
        from app.ai.assessments.prompt import PROMPT_VERSION,RUBRIC_VERSION,INSTRUCTIONS
        from app.ai.validation.output import SCHEMA_VERSION,response_schema
        from app.ai.packets.redaction import REDACTION_VERSION
        definition.update({'prompt_version':PROMPT_VERSION,'rubric_version':RUBRIC_VERSION,
            'schema_version':SCHEMA_VERSION,'redaction_version':REDACTION_VERSION,
            'instructions_hash':digest(INSTRUCTIONS),'response_schema_hash':digest(response_schema()),
            'settings':{'max_output_tokens':body.max_output_tokens,'tools':False,'automatic_fallback':False},
            'notice':'Evidence-review configuration only. Each outbound packet requires current data-disclosure and payer approvals. Suggestions cannot issue contribution credit.'})
    profile=AIProfile(workspace_id=project.workspace_id,project_id=project.id,connection_id=row.id,created_by=user.id,
        version=version,definition=definition,fingerprint=digest(definition))
    db.add(profile);db.flush()
    audit(db,'ai_profile_drafted',actor_id=user.id,workspace_id=project.workspace_id,project_id=project.id,subject_id=profile.id,reason=body.reason)
    return profile

def approval(db,project,user,profile,body,settings):
    old=db.scalar(select(AIProfileApproval).where(AIProfileApproval.profile_id==profile.id))
    if old:
        if old.reviewed_hash!=body.reviewed_hash:raise ApiError(409,'ai_profile_mismatch','The reviewed profile does not match.')
        return old
    previous=active_profile(db,project)
    if (previous.id if previous else None)!=body.expected_active_profile_id or (previous and previous.version>=profile.version):
        raise ApiError(409,'ai_profile_stale','The active evaluator changed. Review a new successor instead of activating older versions.')
    if body.reviewed_hash!=profile.fingerprint or digest(profile.definition)!=profile.fingerprint:
        raise ApiError(409,'ai_profile_mismatch','The reviewed profile fingerprint does not match.')
    row=c.scoped(db,AIConnection,project,profile.connection_id);m=c.model_for(db,row,UUID(profile.definition['model_id']),ready=True)
    c.configuration_check(settings,row.provider);ready(db,row,m)
    if row.generation!=profile.definition['credential_generation'] or m.fingerprint!=profile.definition['model_metadata_hash']:
        raise ApiError(409,'ai_profile_changed','The connection or model changed. Create and review a successor profile.')
    a=AIProfileApproval(workspace_id=project.workspace_id,project_id=project.id,profile_id=profile.id,
        approved_by=user.id,reason=body.reason,reviewed_hash=body.reviewed_hash);db.add(a)
    audit(db,'ai_profile_approved',actor_id=user.id,workspace_id=project.workspace_id,project_id=project.id,subject_id=profile.id,reason=body.reason)
    return a

def view(db,p):
    a=db.scalar(select(AIProfileApproval).where(AIProfileApproval.profile_id==p.id))
    return {'id':p.id,'version':p.version,'definition':p.definition,'fingerprint':p.fingerprint,'created_at':p.created_at,
        'approved':a is not None,'approved_at':a.created_at if a else None}
