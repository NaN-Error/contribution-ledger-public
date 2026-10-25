"""Independent human review; no score, payment or automated acceptance.

Mutations execute under the shared workspace lock, then milestone/package lock.
Review assignments and votes are immutable. A new round explicitly supersedes
unfinished decisions; accepted credit remains linked to its original round.
"""
from copy import deepcopy
from uuid import UUID, uuid4
from sqlalchemy import select, func
from app.core.errors import ApiError
from app.projects.authorization import not_found
from app.projects.models import WorkspaceMembership
from app.policies.service import digest, get_policy, require_ready_policy, current_participants
from app.contributions.work_packages.models import WorkPackageRevision, WorkSubmission
from app.contributions.work_packages.service import get_context, can_coordinate, record_event, active_people
from app.evidence.models import EvidenceSnapshot
from app.evidence.service import snapshot_document
from app.ledger.models import CreditAward
from app.ledger.service import scope_fields, issue_award, reallocate_award, get_award
from app.reviews.models import (ReviewRound, ReviewAssignment, ReviewDecision, CreditDispute,
    DisputeAssignment, DisputeNote, DisputeResolution, ParticipantNotification)
from app.security.audit import audit


def command_hash(actor, body):
    return digest({'actor_id':str(actor.id),'body':body.model_dump(mode='json')})


def replay(db, model, project, request_id, request_hash):
    found=db.scalar(select(model).where(model.workspace_id==project.workspace_id,
        model.project_id==project.id,model.request_id==request_id))
    if found and found.request_hash!=request_hash:
        raise ApiError(409,'idempotency_conflict','That request ID was already used for a different command or actor.')
    return found


def notify(db, project, user_ids, kind, subject_id, message):
    for uid in sorted(set(user_ids),key=str):
        uid=UUID(str(uid))
        if db.get(WorkspaceMembership,(project.workspace_id,uid)) is not None:
            db.add(ParticipantNotification(id=uuid4(),workspace_id=project.workspace_id,project_id=project.id,
                recipient_id=uid,kind=kind,subject_id=subject_id,message=message))
    db.flush()


def get_review(db, project, review_id):
    row=db.scalar(select(ReviewRound).where(ReviewRound.id==review_id,
        ReviewRound.workspace_id==project.workspace_id,ReviewRound.project_id==project.id))
    if row is None: raise not_found()
    return row


def reviewers_for(db, project, conflicts):
    return [p for uid,p in active_people(db,project).items()
            if p['role'] in {'admin','reviewer'} and uid not in set(conflicts)]


def validate_reviewers(db, project, ids, minimum, conflicts):
    if len(ids)!=minimum or len(set(ids))!=len(ids):
        raise ApiError(422,'reviewer_quorum','Assign exactly the policy-required number of distinct independent reviewers.')
    available={p['user_id'] for p in reviewers_for(db,project,conflicts)}
    if not {str(uid) for uid in ids}<=available:
        raise ApiError(403,'reviewer_conflict','A selected reviewer is unavailable, lacks review access, or has a conflict. Administrators do not bypass independence.')


def latest_submission(db, package):
    return db.scalar(select(WorkSubmission).where(WorkSubmission.package_id==package.id)
        .order_by(WorkSubmission.package_version.desc()).limit(1))


def award_target(db, project, package, deliverable_id, storage):
    milestone,allocation,scope=get_context(db,project,package)
    if package.state!='submitted' or package.approved_revision!=scope.number:
        raise ApiError(409,'submitted_scope_required','Submit this exact approved scope and its evidence before independent acceptance.')
    submission=latest_submission(db,package)
    if not submission or not submission.snapshot.get('evidence_snapshot_id'):
        raise ApiError(409,'evidence_snapshot_required','This declaration predates evidence snapshots. Explicitly resubmit before review.')
    snap=db.scalar(select(EvidenceSnapshot).where(EvidenceSnapshot.id==UUID(submission.snapshot['evidence_snapshot_id']),
        EvidenceSnapshot.workspace_id==project.workspace_id,EvidenceSnapshot.project_id==project.id,EvidenceSnapshot.package_id==package.id))
    if snap is None or snap.content_hash!=submission.snapshot.get('evidence_snapshot_hash'):
        raise ApiError(409,'invalid_evidence_snapshot','The submitted evidence reference does not reconcile.')
    if (submission.scope_revision!=scope.number or submission.snapshot.get('scope_content_hash')!=scope.content_hash
        or digest(snapshot_document(db,package,storage))!=snap.content_hash):
        raise ApiError(409,'stale_evidence','Scope or evidence differs from the submitted packet. Refresh the submission and start a new review round.')
    if allocation.status!='active' or milestone.status!='active' or allocation.version!=scope.allocation_version or allocation.atoms!=scope.document['budget_atoms']:
        raise ApiError(409,'stale_budget','The submission is not bound to the current approved planning budget.')
    require_ready_policy(db,project,package.policy_id)
    policy=get_policy(db,project,package.policy_id)
    doc=scope.document
    deliverable=next((d for d in doc['deliverables'] if d['id']==str(deliverable_id)),None)
    if deliverable is None: raise not_found()
    if not deliverable['attribution_complete'] or doc['unplanned_atoms']:
        raise ApiError(409,'incomplete_attribution','Budget and attribution must be complete before review.')
    if db.scalar(select(CreditAward.id).where(CreditAward.package_id==package.id,CreditAward.deliverable_id==deliverable_id)):
        raise ApiError(409,'already_awarded','This deliverable already has finalized credit. Use a dispute for a reviewed correction.')
    entries=[{'user_id':e['user_id'],'role':e['role'],'atoms':e['atoms'],
        'display_name':doc['participant_labels'][e['user_id']]} for e in deliverable['resolved_attributions'] if e['atoms']>0]
    conflicts={e['user_id'] for d in doc['deliverables'] for e in d['resolved_attributions'] if e['atoms']>0}
    conflicts.add(str(submission.submitted_by))
    refs=[]
    for entry in snap.document['entries']:
        metadata=entry['document']['metadata']
        if metadata['inclusion']=='included' and entry['availability_at_capture'] in {'available','external_unverified'}:
            refs.append({'ref':f"evidence:{entry['evidence_id']}:{entry['revision']}",
                'evidence_id':entry['evidence_id'],'revision':entry['revision'],
                'title':metadata['title'],'availability':entry['availability_at_capture'],
                'deliverable_ids':metadata['deliverable_ids'],'visibility':metadata['visibility']})
    criteria=[{'id':f'package:{i}','text':text} for i,text in enumerate(doc['acceptance_criteria'])]
    criteria += [{'id':f'deliverable:{i}','text':text} for i,text in enumerate(deliverable['acceptance_criteria'])]
    criteria += [{'id':'evidence:package','text':doc['evidence_requirements']},
                 {'id':'evidence:deliverable','text':deliverable['evidence_requirements']}]
    return {'schema_version':1,'kind':'award','package_id':str(package.id),'title':deliverable['title'],
        'package_title':doc['title'],'deliverable_id':str(deliverable_id),'scope_revision':scope.number,
        'scope_hash':scope.content_hash,'submission_id':str(submission.id),'submission_hash':submission.snapshot_hash,
        'evidence_snapshot_id':str(snap.id),'evidence_snapshot_hash':snap.content_hash,
        'allocation_id':str(allocation.id),'allocation_version':allocation.version,'allocation_atoms':allocation.atoms,
        'policy_id':str(policy.id),'policy_version':policy.version,'policy_hash':policy.content_hash,
        'pool_key':allocation.pool_key,'budget_atoms':deliverable['budget_atoms'],'attributions':entries,
        'minimum_reviewers':policy.rules['review']['minimum_independent_reviewers'],
        'conflict_ids':sorted(conflicts),'criteria':criteria,'evidence_sources':refs,
        'notice':'Acceptance is for this budgeted deliverable only. Each finding needs an explanation. Source references identify evidence; the application does not prove the claim.'}


def round_number(db, package, deliverable_id):
    number=int(db.scalar(select(func.coalesce(func.max(ReviewRound.number),0))
        .where(ReviewRound.package_id==package.id,ReviewRound.deliverable_id==deliverable_id)))+1
    if number>1000: raise ApiError(409,'review_limit','This pilot supports 1,000 rounds per deliverable.')
    return number


def store_round(db, project, package, actor, body, target, *, dispute_id=None):
    minimum=target['minimum_reviewers']
    validate_reviewers(db,project,body.reviewer_ids,minimum,target['conflict_ids'])
    row=ReviewRound(id=uuid4(),**scope_fields(project,package),deliverable_id=UUID(target['deliverable_id']),
        policy_id=UUID(target['policy_id']),submission_id=UUID(target['submission_id']),
        evidence_snapshot_id=UUID(target['evidence_snapshot_id']),dispute_id=dispute_id,kind=target['kind'],
        number=round_number(db,package,UUID(target['deliverable_id'])),minimum_reviewers=minimum,
        target=target,target_hash=digest(target),request_id=body.request_id,request_hash=command_hash(actor,body),
        created_by=actor.id,reason=body.reason)
    db.add(row);db.flush()
    for uid in sorted(body.reviewer_ids,key=str):
        db.add(ReviewAssignment(**scope_fields(project,package),review_id=row.id,reviewer_id=uid))
    db.flush()
    package.version+=1
    record_event(db,package,actor,'review_assigned',body.reason,{'review_id':str(row.id),'kind':row.kind,'deliverable_id':str(row.deliverable_id)})
    notify(db,project,body.reviewer_ids,'review_assigned',row.id,'An independent human review was assigned to you.')
    return row


def create_review(db, project, package, actor, role, body, storage):
    previous=replay(db,ReviewRound,project,body.request_id,command_hash(actor,body))
    if previous: return previous
    _,_,scope=get_context(db,project,package)
    if not can_coordinate(package,scope.document,role,actor.id):
        raise ApiError(403,'permission_denied','The coordinator or a project administrator must assign the review.')
    if package.version!=body.expected_package_version:
        raise ApiError(409,'stale_package','The package changed. Refresh before assigning the review.')
    target=award_target(db,project,package,body.deliverable_id,storage)
    if digest(target)!=body.reviewed_target_hash:
        raise ApiError(409,'stale_review_target','The proposed review target changed. Review it again.')
    return store_round(db,project,package,actor,body,target)


def latest_round_id(db, review):
    query=select(ReviewRound.id).where(ReviewRound.package_id==review.package_id,
        ReviewRound.deliverable_id==review.deliverable_id,ReviewRound.kind=='award') if review.kind=='award' else select(ReviewRound.id).where(ReviewRound.dispute_id==review.dispute_id)
    return db.scalar(query.order_by(ReviewRound.number.desc()).limit(1))


def finalized(db, review):
    if review.kind=='award': return db.scalar(select(CreditAward).where(CreditAward.review_id==review.id))
    return db.scalar(select(DisputeResolution).where(DisputeResolution.review_id==review.id))


def check_current(db, project, package, review, storage):
    if finalized(db,review): raise ApiError(409,'already_finalized','This review has already been finalized.')
    if latest_round_id(db,review)!=review.id:
        raise ApiError(409,'superseded_review','A newer explicit review round supersedes these unfinished decisions.')
    if review.kind=='award': current=award_target(db,project,package,review.deliverable_id,storage)
    else:
        from app.reviews.disputes import resolution_target
        current=resolution_target(db,project,review.dispute_id,review.target['kind'],review.target['attributions'])
    if digest(current)!=review.target_hash:
        raise ApiError(409,'stale_review','The exact reviewed evidence, scope, attribution, policy or dispute context changed. Start a fresh round.')
    assigned=list(db.scalars(select(ReviewAssignment.reviewer_id).where(ReviewAssignment.review_id==review.id)))
    validate_reviewers(db,project,assigned,review.minimum_reviewers,review.target['conflict_ids'])
    return assigned


def choices(db, review):
    return list(db.scalars(select(ReviewDecision).where(ReviewDecision.review_id==review.id)
        .order_by(ReviewDecision.reviewer_id)))


def approvals_hash(db, review):
    return digest({'review_id':str(review.id),'target_hash':review.target_hash,
        'assigned':sorted(str(uid) for uid in db.scalars(select(ReviewAssignment.reviewer_id).where(ReviewAssignment.review_id==review.id))),
        'decisions':[{'id':str(d.id),'reviewer_id':str(d.reviewer_id),'decision':d.decision,
            'request_hash':d.request_hash} for d in choices(db,review)]})


def decide(db,project,package,review,actor,body,storage):
    previous=replay(db,ReviewDecision,project,body.request_id,command_hash(actor,body))
    if previous:
        if previous.review_id!=review.id: raise ApiError(409,'idempotency_conflict','The request belongs to another review.')
        return previous
    assigned=check_current(db,project,package,review,storage)
    if actor.id not in assigned:
        raise ApiError(403,'permission_denied','Only an assigned independent reviewer may decide this round.')
    if body.reviewed_target_hash!=review.target_hash:
        raise ApiError(409,'review_hash_mismatch','Read the exact review target before deciding.')
    if db.scalar(select(ReviewDecision.id).where(ReviewDecision.review_id==review.id,ReviewDecision.reviewer_id==actor.id)):
        raise ApiError(409,'decision_preserved','Your decision is already preserved. Start a new round instead of overwriting it.')
    expected={c['id'] for c in review.target['criteria']}
    keys=[f.criterion_id for f in body.findings]
    if len(keys)!=len(set(keys)) or set(keys)!=expected:
        raise ApiError(422,'criteria_required','Provide exactly one finding for every displayed criterion and evidence requirement.')
    valid_refs={r['ref'] for r in review.target['evidence_sources']}
    for f in body.findings:
        if len(f.evidence_refs)!=len(set(f.evidence_refs)) or not set(f.evidence_refs)<=valid_refs:
            raise ApiError(422,'invalid_evidence_reference','Use distinct supporting references from this exact evidence packet or dispute notes.')
        if body.decision=='accept' and (f.result!='supported' or not f.evidence_refs):
            raise ApiError(422,'unsupported_acceptance','Acceptance requires supported findings and cited evidence for every criterion.')
    row=ReviewDecision(id=uuid4(),**scope_fields(project,package),review_id=review.id,reviewer_id=actor.id,
        decision=body.decision,findings=[f.model_dump(mode='json') for f in body.findings],
        reviewed_target_hash=body.reviewed_target_hash,request_id=body.request_id,
        request_hash=command_hash(actor,body),reason=body.reason)
    db.add(row);db.flush()
    audit(db,'review.decision',actor_id=actor.id,workspace_id=project.workspace_id,project_id=project.id,
        subject_id=row.id,reason=body.reason,details={'review_id':str(review.id),'decision':row.decision})
    notify(db,project,{review.created_by,*[UUID(e['user_id']) for e in review.target['attributions']]},
        'review_decision',review.id,'A human review decision is available. A vote alone does not issue credit.')
    return row


def finalize_review(db,project,package,review,actor,body,storage):
    # Same command can be safely replayed after a lost response, but not reused
    # on a different review/actor or with changed payload.
    prior=finalized(db,review); fingerprint=command_hash(actor,body)
    if prior:
        if prior.request_id==body.request_id and prior.request_hash==fingerprint: return prior
        raise ApiError(409,'already_finalized','This review already has a recorded finalization. No second credit is issued.')
    model=CreditAward if review.kind=='award' else DisputeResolution
    collision=replay(db,model,project,body.request_id,fingerprint)
    if collision: raise ApiError(409,'idempotency_conflict','That finalization request belongs to another review.')
    assigned=check_current(db,project,package,review,storage)
    if actor.id not in assigned:
        raise ApiError(403,'independent_finalizer_required','An assigned independent reviewer must finalize this decision set.')
    if body.reviewed_decisions_hash!=approvals_hash(db,review):
        raise ApiError(409,'stale_decisions','The decision set differs from the one you reviewed. Refresh before finalizing.')
    decisions=choices(db,review)
    if len(decisions)!=review.minimum_reviewers or any(d.decision!='accept' for d in decisions):
        raise ApiError(409,'approval_quorum_required','All assigned policy-required reviewers must accept. Unresolved findings are not silently overruled.')
    if review.kind=='award': result=issue_award(db,project,package,review,actor,body,fingerprint)
    else:
        from app.reviews.disputes import get_dispute, current_assignment
        dispute=get_dispute(db,project,review.dispute_id)
        assignment=current_assignment(db,dispute)
        if assignment is None or assignment.resolver_id!=actor.id:
            raise ApiError(403,'assigned_resolver_required','The current independent resolver must finalize the resolution.')
        result=DisputeResolution(id=uuid4(),**scope_fields(project,package),dispute_id=dispute.id,
            review_id=review.id,resolved_by=actor.id,disposition=review.kind,
            request_id=body.request_id,request_hash=fingerprint,reason=body.reason)
        db.add(result);db.flush()
        award=get_award(db,project,dispute.award_id)
        if review.kind=='reallocate': reallocate_award(db,project,package,award,review,result)
    package.version+=1
    record_event(db,package,actor,'credit_awarded' if review.kind=='award' else 'dispute_resolved',body.reason,
        {'review_id':str(review.id),'record_id':str(result.id),'deliverable_id':str(review.deliverable_id)})
    recipients={UUID(uid) for uid in review.target['conflict_ids']}
    recipients.update(assigned)
    notify(db,project,recipients,'credit_awarded' if review.kind=='award' else 'dispute_resolved',result.id,
        'A human-approved contribution record is finalized. Open the contribution history for its exact scope.')
    db.flush();return result


def review_state(db,project,package,review,storage):
    record=finalized(db,review)
    if record: return 'finalized',None
    try: check_current(db,project,package,review,storage)
    except ApiError as e: return 'stale',e.message
    decisions=choices(db,review)
    if any(d.decision!='accept' for d in decisions): return 'changes_requested','An independent reviewer requested evidence or rejected acceptance.'
    return ('ready_to_finalize',None) if len(decisions)==review.minimum_reviewers else ('awaiting_decisions',None)


def review_view(db,project,package,review,actor_id,role,storage):
    state,blocker=review_state(db,project,package,review,storage)
    assigned=list(db.scalars(select(ReviewAssignment.reviewer_id).where(ReviewAssignment.review_id==review.id)))
    decisions=choices(db,review)
    full=role in {'admin','reviewer'}
    target=deepcopy(review.target)
    if not full:
        # Do not leak restricted artifact titles/reference IDs through review metadata.
        from app.evidence.service import get_item, can_view
        from app.evidence.models import EvidenceRevision
        visible=[]
        for source in target['evidence_sources']:
            if source.get('evidence_id'):
                item=get_item(db,package,UUID(source['evidence_id']))
                revision=db.get(EvidenceRevision,(item.id,source['revision']))
                if not can_view(item,actor_id,role,revision.document):
                    visible.append({'restricted':True});continue
            visible.append(source)
        target['evidence_sources']=visible
    record=finalized(db,review)
    return {'id':review.id,'kind':review.kind,'number':review.number,'package_id':review.package_id,
        'deliverable_id':review.deliverable_id,'dispute_id':review.dispute_id,'target':target,
        'target_hash':review.target_hash,'state':state,'blocker':blocker,'created_by':review.created_by,
        'reason':review.reason,'created_at':review.created_at,'reviewer_ids':assigned,
        'minimum_reviewers':review.minimum_reviewers,'decisions_hash':approvals_hash(db,review),
        'decisions':[{'id':d.id,'reviewer_id':d.reviewer_id,'decision':d.decision,
            'findings':d.findings if full else [],'reason':d.reason if full else None,'created_at':d.created_at} for d in decisions],
        'can_read_assessments':role in {'admin','reviewer'},
        'can_decide':full and actor_id in assigned and state=='awaiting_decisions' and not any(d.reviewer_id==actor_id for d in decisions),
        'can_finalize':full and actor_id in assigned and state=='ready_to_finalize' and (review.kind=='award' or target['resolver_id']==str(actor_id)),
        'finalized_record_id':record.id if record else None}
