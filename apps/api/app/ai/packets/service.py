"""Construct a closed, reviewed outbound packet from exact authorized local evidence.

This module runs in the API. The evaluator worker receives only sealed packets,
not a mounted artifact store, repository API, raw-evidence SELECT or any tools.
"""
from copy import deepcopy
import json
from uuid import UUID,uuid4
from sqlalchemy import select,func,text
from app.ai.assessments.models import AIReviewPacket
from app.ai.models import AIProfile
from app.ai.connections import service as c
from app.ai.assessments.prompt import prompt_hash,PROMPT_VERSION,SCHEMA_VERSION,RUBRIC_VERSION,INSTRUCTIONS
from app.ai.validation.output import response_schema
from app.ai.packets.redaction import redact,bounded_lines,excluded_path,DEFAULT_EXCLUDED_PATHS,REDACTION_VERSION
from app.contributions.work_packages.models import WorkPackage,WorkSubmission
from app.contributions.work_packages.service import get_package
from app.evidence.models import EvidenceSnapshot,EvidenceItem,EvidenceRevision,EvidenceRetirement
from app.evidence.service import require_visible,read_object
from app.reviews.service import award_target,latest_submission
from app.policies.service import digest
from app.security.audit import audit
from app.core.errors import ApiError

MAX_PACKET_BYTES=24000
MAX_SOURCES=24


def review_access(role):
    if role not in {'admin','reviewer'}:
        raise ApiError(403,'ai_review_access','Only project reviewers and administrators can inspect or prepare AI evidence assessments.')


def profile_contract(profile):
    d=profile.definition
    if (digest(d)!=profile.fingerprint or d.get('prompt_version')!=PROMPT_VERSION
        or d.get('schema_version')!=SCHEMA_VERSION or d.get('rubric_version')!=RUBRIC_VERSION
        or d.get('settings',{}).get('tools') is not False
        or d.get('settings',{}).get('automatic_fallback') is not False
        or d.get('redaction_version')!=REDACTION_VERSION
        or d.get('instructions_hash')!=digest(INSTRUCTIONS) or d.get('response_schema_hash')!=digest(response_schema())):
        raise ApiError(409,'ai_evidence_profile_required','Create and review a phase-11 evidence profile. Earlier protocol-only profiles are not evidence authorization.')


def stamp(db,package):
    submission=latest_submission(db,package)
    entries=[{'id':str(e.id),'revision':e.current_revision,'visibility':e.visibility}
        for e in db.scalars(select(EvidenceItem).where(EvidenceItem.workspace_id==package.workspace_id,
            EvidenceItem.project_id==package.project_id,EvidenceItem.package_id==package.id).order_by(EvidenceItem.id)).all()]
    return {'scope_revision':package.scope_revision,'submission_id':str(submission.id) if submission else None,
        'entries':entries,'retirements':db.scalar(select(func.count()).select_from(EvidenceRetirement).where(
            EvidenceRetirement.workspace_id==package.workspace_id,EvidenceRetirement.project_id==package.project_id,
            EvidenceRetirement.package_id==package.id))}


def current(db,packet):
    # A boolean-only definer function avoids giving the worker raw evidence,
    # policy-economics or credit-table read authority. SQLite is test-only.
    if db.bind.dialect.name=='postgresql':
        return bool(db.scalar(text('SELECT cl_ai_packet_current(:pid)'),{'pid':packet.id}))
    package=db.get(WorkPackage,packet.package_id)
    if not package or package.workspace_id!=packet.workspace_id or package.project_id!=packet.project_id or package.state!='submitted':return False
    from app.ledger.models import CreditAward
    if db.scalar(select(CreditAward.id).where(CreditAward.package_id==packet.package_id,CreditAward.deliverable_id==packet.deliverable_id)):return False
    return stamp(db,package)==packet.capture['stamp']


def verify(packet):
    if digest({'payload':packet.payload,'capture':packet.capture})!=packet.content_hash or prompt_hash(packet.payload)!=packet.prompt_hash:
        raise ApiError(409,'ai_packet_integrity','The preserved packet failed its fingerprint check. Stop and investigate.')


def github_parts(db,project,package,entry,patterns):
    from app.integrations.github.models import GitHubSourceVersion,GitHubEvidenceLink
    origin=entry['document']['external_source']
    try:sid=UUID(origin['source_id'])
    except (KeyError,ValueError,TypeError):return [],['pinned_source_unavailable']
    link=db.scalar(select(GitHubEvidenceLink.id).where(GitHubEvidenceLink.workspace_id==project.workspace_id,
        GitHubEvidenceLink.project_id==project.id,GitHubEvidenceLink.package_id==package.id,
        GitHubEvidenceLink.evidence_id==UUID(entry['evidence_id']),GitHubEvidenceLink.source_id==sid))
    source=db.scalar(select(GitHubSourceVersion).where(GitHubSourceVersion.id==sid,
        GitHubSourceVersion.workspace_id==project.workspace_id,GitHubSourceVersion.project_id==project.id))
    if not link or not source or source.content_hash!=origin.get('source_hash'):
        return [],['pinned_source_unavailable']
    doc=source.document;content=doc['content'];parts=[];omissions=[]
    if doc.get('omissions'):omissions.append('upstream_import_omissions')
    if isinstance(content.get('files'),list):
        for i,f in enumerate(content['files']):
            if i>=12:omissions.append('file_selection_limit');break
            if excluded_path(f.get('filename'),patterns) or (f.get('previous_filename') and excluded_path(f['previous_filename'],patterns)):
                omissions.append('excluded_path');continue
            if not f.get('patch') or f.get('patch_state')!='bounded_patch':
                omissions.append('patch_unavailable');continue
            # No name, repository URL, author, activity counts or economic metrics.
            parts.append(('captured_diff',f['filename'],f['patch']))
    else:
        path=content.get('path')
        if path and excluded_path(path,patterns):return [],[*omissions,'excluded_path']
        allowed=('title','body','message','description','state','status','conclusion','head_sha','commit_id','sha')
        text_value='\n'.join(f'{key}: {content[key]}' for key in allowed if isinstance(content.get(key),str) and content[key])
        if text_value:parts.append(('captured_claim_or_check',doc['kind'],text_value))
    return parts,omissions


def create(db,project,actor,role,body,storage):
    review_access(role)
    request_hash=digest(body.model_dump(mode='json'))
    existing=db.scalar(select(AIReviewPacket).where(AIReviewPacket.project_id==project.id,
        AIReviewPacket.created_by==actor.id,AIReviewPacket.request_id==body.request_id))
    if existing:
        if existing.request_hash!=request_hash:raise ApiError(409,'idempotency_conflict','That packet request identifier belongs to a different selection.')
        verify(existing);return existing
    if db.scalar(select(func.count()).select_from(AIReviewPacket).where(AIReviewPacket.project_id==project.id))>=2000:
        raise ApiError(409,'ai_packet_limit','This pilot project has reached its packet-record limit.')
    profile=c.scoped(db,AIProfile,project,body.profile_id);profile_contract(profile)
    package=get_package(db,project,body.package_id)
    if package.version!=body.expected_package_version:raise ApiError(409,'stale_package','Refresh the package before selecting evidence.')
    target=award_target(db,project,package,body.deliverable_id,storage)
    snap=db.get(EvidenceSnapshot,UUID(target['evidence_snapshot_id']))
    scope=snap.document['scope']
    patterns=(*DEFAULT_EXCLUDED_PATHS,*profile.definition.get('excluded_paths',[]),*body.excluded_paths)
    entries=snap.document['entries'];selected=set(map(str,body.evidence_ids))
    known={e['evidence_id'] for e in entries}
    if not selected<=known:raise c.not_found()
    # Aliases are scoped to this package. Never send display names, local account
    # IDs, budgets, current shares, popularity measures, or inferred labor hours.
    users=sorted(scope['intended_contributor_ids'])
    aliases={uid:f'contributor_{i+1}' for i,uid in enumerate(users)}
    labels=[(name,aliases.get(uid,'contributor')) for uid,name in scope.get('participant_labels',{}).items()]
    counts={}
    def clean(v):
        val,found=redact(v,labels)
        for k,n in found.items():counts[k]=counts.get(k,0)+n
        return val
    criteria=[{'id':f'C{i+1}','text':clean(row['text'])} for i,row in enumerate(target['criteria'])]
    if len(criteria)>64:raise ApiError(409,'ai_criteria_limit','Split this work into independently reviewable deliverables before AI assessment.')
    payload={'packet_version':'bounded-evidence-v1','outcome':clean(scope['outcome']),
        'deliverable':clean(target['title']),'criteria':criteria,
        'contributors':[{'alias':alias} for alias in aliases.values()], 'sources':[], 'omissions':[],
        'notice':'Untrusted bounded evidence. Claims and reported tests are not independently verified. Packet line numbers refer to these redacted excerpts, not original file line numbers.'}
    provenance={}
    def omit(code,eid=None):
        # No excluded path, hidden title, secret or raw omission explanation is sent.
        payload['omissions'].append({'code':code})
    def add_source(kind,title,value,entry):
        lines,cut=bounded_lines(clean(value))
        if cut:omit('source_text_bounded')
        if not lines:omit('no_text_within_limits');return
        sid=f'E{len(payload["sources"])+1}'
        source={'id':sid,'kind':kind,'title':clean(title)[:160],'lines':lines}
        if len(payload['sources'])>=MAX_SOURCES:omit('source_count_limit');return
        candidate={**payload,'sources':[*payload['sources'],source]}
        if len(json.dumps(candidate,ensure_ascii=True,separators=(',',':')).encode())>MAX_PACKET_BYTES-3000:
            omit('packet_size_limit');return
        payload['sources'].append(source)
        provenance[sid]={'evidence_id':entry['evidence_id'],'revision':entry['revision'],
            'evidence_ref':f"evidence:{entry['evidence_id']}:{entry['revision']}",
            'revision_hash':entry['revision_hash'],'kind':kind,'title':source['title']}
    for entry in entries:
        doc=entry['document'];meta=doc['metadata'];eid=entry['evidence_id']
        item=db.get(EvidenceItem,UUID(eid));require_visible(item,actor.id,role,doc)
        if selected and eid not in selected:omit('not_selected');continue
        if meta['inclusion']!='included':omit('declared_'+meta['inclusion']);continue
        if meta['visibility']=='restricted' and not body.include_restricted:omit('restricted_excluded');continue
        if meta['deliverable_ids'] and str(body.deliverable_id) not in meta['deliverable_ids']:omit('other_deliverable');continue
        if doc.get('external_source'):
            parts,missing=github_parts(db,project,package,entry,patterns)
            for code in missing:omit(code)
            for kind,title,value in parts:add_source(kind,title,value,entry)
            continue
        if doc['kind']=='statement':add_source('contributor_claim',meta['title'],doc['text'],entry)
        elif doc['kind']=='link':
            omit('external_link_not_fetched')
            # Only an explicitly labeled local description may be analyzed; never the URL.
            add_source('description_only',meta['title'],meta['description'],entry)
        elif doc['kind']=='file':
            f=doc.get('file') or {}
            if excluded_path(f.get('filename'),patterns):omit('excluded_path');continue
            if f.get('processing')!='validated_utf8_plaintext':omit('nontext_artifact_not_inspected');continue
            rev=db.get(EvidenceRevision,(UUID(eid),entry['revision']))
            try:raw=read_object(db,package,rev,storage).decode('utf-8-sig')
            except (ApiError,UnicodeError):omit('artifact_unavailable');continue
            add_source('uploaded_text',f['filename'],raw,entry)
        else:omit('missing_evidence')
    # Compress repeated omission reasons; preserve counts, never silently drop them.
    codes={}
    for o in payload['omissions']:codes[o['code']]=codes.get(o['code'],0)+1
    if not payload['sources']:codes['no_readable_sources']=1
    payload['omissions']=[{'code':k,'count':v} for k,v in sorted(codes.items())]
    if len(json.dumps(payload,ensure_ascii=True,separators=(',',':')).encode())>MAX_PACKET_BYTES:
        raise ApiError(409,'ai_packet_size','The criteria alone exceed the bounded packet. Split the deliverable or shorten the scope.')
    capture={'stamp':stamp(db,package),'scope_hash':target['scope_hash'],'submission_hash':target['submission_hash'],
        'evidence_snapshot_id':target['evidence_snapshot_id'],'evidence_snapshot_hash':target['evidence_snapshot_hash'],
        'policy_id':target['policy_id'],'policy_hash':target['policy_hash'],'profile_hash':profile.fingerprint,
        'criteria_map':{f'C{i+1}':r['id'] for i,r in enumerate(target['criteria'])},'aliases':aliases,
        'sources':provenance,'redaction_counts':counts,'redaction_version':REDACTION_VERSION,
        'include_restricted':body.include_restricted,'excluded_paths':list(patterns),
        'selection':sorted(selected),'privacy_notice':'Pattern redaction is incomplete by design. Inspect the exact outbound payload before authorizing disclosure. Archived redacted text is a separate retained copy.'}
    packet=AIReviewPacket(id=uuid4(),workspace_id=project.workspace_id,project_id=project.id,package_id=package.id,
        scope_revision=package.scope_revision,submission_id=UUID(target['submission_id']),deliverable_id=body.deliverable_id,
        profile_id=profile.id,created_by=actor.id,request_id=body.request_id,request_hash=request_hash,payload=payload,
        capture=capture,content_hash=digest({'payload':payload,'capture':capture}),prompt_hash=prompt_hash(payload),reason=body.reason)
    db.add(packet);db.flush()
    audit(db,'ai_packet_prepared',actor_id=actor.id,workspace_id=project.workspace_id,project_id=project.id,subject_id=packet.id,
        reason='A bounded redacted packet was prepared; nothing was sent.',details={'hash':packet.content_hash})
    return packet


def view(db,packet,full=True):
    verify(packet)
    result={k:getattr(packet,k) for k in ('id','package_id','scope_revision','submission_id','deliverable_id','profile_id',
        'created_by','content_hash','prompt_hash','reason','created_at')}
    result.update(stale=not current(db,packet),source_count=len(packet.payload['sources']),omissions=packet.payload['omissions'])
    if full:result.update(payload=deepcopy(packet.payload),capture=deepcopy(packet.capture))
    return result
