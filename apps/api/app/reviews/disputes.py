"""Disputes preserve claims, resolver assignments and reviewed corrections."""
from uuid import UUID, uuid4
from sqlalchemy import select, func
from app.core.errors import ApiError
from app.projects.authorization import not_found
from app.policies.service import digest, get_policy, require_ready_policy
from app.contributions.work_packages.service import active_people, record_event
from app.ledger.service import (get_award, scope_fields, balance_rows, balance_hash,
    open_disputes, award_view)
from app.reviews.models import (CreditDispute, DisputeAssignment, DisputeNote,
    DisputeResolution, ReviewRound, ReviewAssignment)
from app.reviews.service import command_hash, replay, notify, reviewers_for, store_round
from app.security.audit import audit


def get_dispute(db,project,dispute_id):
    item=db.scalar(select(CreditDispute).where(CreditDispute.id==dispute_id,
        CreditDispute.workspace_id==project.workspace_id,CreditDispute.project_id==project.id))
    if item is None: raise not_found()
    return item


def resolution(db,item):
    return db.scalar(select(DisputeResolution).where(DisputeResolution.dispute_id==item.id))


def require_open(db,item):
    if resolution(db,item): raise ApiError(409,'dispute_closed','This dispute has a preserved resolution. File a new dispute for new concerns.')


def current_assignment(db,item):
    return db.scalar(select(DisputeAssignment).where(DisputeAssignment.dispute_id==item.id)
        .order_by(DisputeAssignment.number.desc()).limit(1))


def notes(db,item):
    return list(db.scalars(select(DisputeNote).where(DisputeNote.dispute_id==item.id)
        .order_by(DisputeNote.created_at,DisputeNote.id)))


def dispute_context(db,project,item):
    award=get_award(db,project,item.award_id); assignment=current_assignment(db,item)
    return {'dispute_id':str(item.id),'award_id':str(award.id),'opening_reason':item.reason,
        'balance_hash':balance_hash(db,award),
        'assignment_number':assignment.number if assignment else None,
        'resolver_id':str(assignment.resolver_id) if assignment else None,
        'notes':[{'id':str(n.id),'created_by':str(n.created_by),'text':n.text,'source_url':n.source_url} for n in notes(db,item)],
        'resolved_id':str(resolution(db,item).id) if resolution(db,item) else None}


def conflict_ids(db,project,item,attributions=()):
    award=get_award(db,project,item.award_id); original=db.get(ReviewRound,award.review_id)
    ids={*original.target['conflict_ids'],str(item.opened_by)}
    ids.update(e['user_id'] for e in [*award.original_attributions,*balance_rows(db,award),*attributions])
    # Original acceptance reviewers cannot resolve an appeal of their own decision.
    ids.update(str(uid) for uid in db.scalars(select(ReviewAssignment.reviewer_id)
        .where(ReviewAssignment.review_id==award.review_id)))
    # A later dispute must not be resolved by the people whose earlier
    # finalized correction/uphold is itself being challenged. Unfinished
    # proposals do not recuse their own quorum mid-review.
    prior_resolution_reviews = select(DisputeResolution.review_id).join(
        CreditDispute, CreditDispute.id == DisputeResolution.dispute_id
    ).where(CreditDispute.award_id == award.id)
    ids.update(str(uid) for uid in db.scalars(select(ReviewAssignment.reviewer_id)
        .where(ReviewAssignment.review_id.in_(prior_resolution_reviews))))
    return sorted(ids)


def create_dispute(db,project,package,actor,role,body):
    prior=replay(db,CreditDispute,project,body.request_id,command_hash(actor,body))
    if prior:return prior
    if role=='viewer':raise ApiError(403,'permission_denied','A project participant must file a credit dispute.')
    award=get_award(db,project,body.award_id)
    if award.package_id!=package.id:raise not_found()
    if any(d.award_id==award.id for d in open_disputes(db,project)):
        raise ApiError(409,'active_dispute_exists','This award already has an open dispute. Add a supplementary note there.')
    count=int(db.scalar(select(func.count()).select_from(CreditDispute).where(CreditDispute.project_id==project.id)))
    if count>=2000:raise ApiError(409,'dispute_limit','This pilot supports 2,000 disputes per project.')
    item=CreditDispute(id=uuid4(),**scope_fields(project,package),award_id=award.id,
        opened_by=actor.id,reason=body.reason,request_id=body.request_id,request_hash=command_hash(actor,body))
    db.add(item);db.flush()
    package.version+=1
    record_event(db,package,actor,'dispute_opened',body.reason,{'dispute_id':str(item.id),'award_id':str(award.id),'pool_close_blocked':True})
    ids={UUID(e['user_id']) for e in balance_rows(db,award)}
    ids.update(UUID(uid) for uid,p in active_people(db,project).items() if p['role'] in {'admin','reviewer'})
    notify(db,project,ids,'dispute_opened',item.id,'A contribution dispute is open. The affected pool is blocked from future closing.')
    return item


def assign_resolver(db,project,package,item,actor,role,body):
    prior=replay(db,DisputeAssignment,project,body.request_id,command_hash(actor,body))
    if prior:
        if prior.dispute_id!=item.id: raise ApiError(409,'idempotency_conflict','That request belongs to another dispute.')
        return prior
    if role!='admin':raise ApiError(403,'permission_denied','An administrator assigns the independent resolver; the administrator cannot override conflicts.')
    require_open(db,item)
    if body.reviewed_context_hash!=digest(dispute_context(db,project,item)):
        raise ApiError(409,'stale_dispute','The dispute changed. Review its current context again.')
    candidates={p['user_id'] for p in reviewers_for(db,project,conflict_ids(db,project,item))}
    if str(body.resolver_id) not in candidates:
        raise ApiError(403,'resolver_conflict','The resolver must have current review access and no original-beneficiary, complainant, or original-reviewer conflict.')
    previous=current_assignment(db,item); number=previous.number+1 if previous else 1
    if number>100:raise ApiError(409,'resolver_assignment_limit','This pilot supports 100 resolver assignments per dispute.')
    row=DisputeAssignment(**scope_fields(project,package),dispute_id=item.id,number=number,
        resolver_id=body.resolver_id,assigned_by=actor.id,reason=body.reason,
        request_id=body.request_id,request_hash=command_hash(actor,body))
    db.add(row);db.flush()
    audit(db,'dispute.resolver_assigned',actor_id=actor.id,workspace_id=project.workspace_id,project_id=project.id,
        subject_id=item.id,reason=body.reason,details={'assignment_number':number,'resolver_id':str(body.resolver_id)})
    notify(db,project,[body.resolver_id],'resolver_assigned',item.id,'You were assigned as the independent resolver for a credit dispute.')
    return row


def add_note(db,project,package,item,actor,role,body):
    prior=replay(db,DisputeNote,project,body.request_id,command_hash(actor,body))
    if prior:
        if prior.dispute_id!=item.id: raise ApiError(409,'idempotency_conflict','That request belongs to another dispute.')
        return prior
    if role=='viewer':raise ApiError(403,'permission_denied','Read-only access cannot add dispute notes.')
    require_open(db,item)
    if int(db.scalar(select(func.count()).select_from(DisputeNote).where(DisputeNote.dispute_id==item.id)))>=200:
        raise ApiError(409,'dispute_note_limit','This pilot supports 200 notes per dispute.')
    row=DisputeNote(id=uuid4(),**scope_fields(project,package),dispute_id=item.id,created_by=actor.id,
        text=body.text,source_url=body.source_url,request_id=body.request_id,request_hash=command_hash(actor,body))
    db.add(row);db.flush()
    audit(db,'dispute.note_added',actor_id=actor.id,workspace_id=project.workspace_id,project_id=project.id,
        subject_id=item.id,reason='Supplementary claim added; unfinished resolution approvals become stale.',details={'note_id':str(row.id)})
    assignment=current_assignment(db,item)
    if assignment:notify(db,project,[assignment.resolver_id],'dispute_note',item.id,'New supplementary information may require a fresh resolution review.')
    return row


def normalize_correction(db,project,award,disposition,entries):
    before=balance_rows(db,award)
    if disposition=='uphold':
        if entries and entries!=before:
            raise ApiError(422,'uphold_has_no_reallocation','An upheld award keeps its current allocations.')
        return before
    if not entries or len({(e['user_id'],e['role']) for e in entries})!=len(entries):
        raise ApiError(422,'invalid_correction','Supply distinct contributor/role rows for the complete replacement allocation.')
    if sum(e['atoms'] for e in entries)!=award.budget_atoms or any(type(e['atoms']) is not int or e['atoms']<=0 for e in entries):
        raise ApiError(422,'correction_budget','Replacement allocations must total exactly the accepted award, with positive integer amounts.')
    people=active_people(db,project)
    historical={e['user_id']:e['display_name'] for e in [*award.original_attributions,*before]}
    if not {e['user_id'] for e in entries} <= (set(people)|set(historical)):
        raise ApiError(422,'recipient_unavailable','Choose a current project participant or a historical recipient of this award.')
    result=[{'user_id':e['user_id'],'role':e['role'],'atoms':e['atoms'],
        'display_name':historical.get(e['user_id']) or people[e['user_id']]['display_name']} for e in entries]
    result.sort(key=lambda e:(e['user_id'],e['role']))
    if {(e['user_id'],e['role']):e['atoms'] for e in result}=={(e['user_id'],e['role']):e['atoms'] for e in before}:
        raise ApiError(422,'unchanged_correction','There is no allocation change. Use an uphold proposal instead.')
    return result


def resolution_target(db,project,dispute_id,disposition,entries):
    item=get_dispute(db,project,dispute_id);require_open(db,item)
    award=get_award(db,project,item.award_id);original=db.get(ReviewRound,award.review_id)
    assignment=current_assignment(db,item)
    if assignment is None:raise ApiError(409,'resolver_required','Assign an independent resolver first.')
    # The original approved policy remains the authority; a successor never
    # silently changes the quorum needed to correct historical credit.
    require_ready_policy(db,project,award.policy_id)
    policy=get_policy(db,project,award.policy_id)
    entries=normalize_correction(db,project,award,disposition,entries)
    conflicts=conflict_ids(db,project,item,entries)
    eligible={p['user_id'] for p in reviewers_for(db,project,conflicts)}
    if str(assignment.resolver_id) not in eligible:
        raise ApiError(403,'resolver_conflict','The current resolver is no longer independent of this proposed outcome or lacks review access.')
    context=dispute_context(db,project,item)
    refs=[{'ref':'award:'+str(award.id),'title':'Original finalized award and immutable accounting history','visibility':'project'},
        {'ref':'dispute:'+str(item.id),'title':'Opening allegation (a claim, not automatically proven)','visibility':'project'}]
    refs.extend({'ref':'note:'+n['id'],'title':'Supplementary dispute note','visibility':'project'} for n in context['notes'])
    return {'schema_version':1,'kind':disposition,'package_id':str(award.package_id),
        'title':'Resolve: '+original.target['title'],'package_title':original.target['package_title'],
        'deliverable_id':str(award.deliverable_id),'policy_id':str(policy.id),'policy_version':policy.version,
        'policy_hash':policy.content_hash,'pool_key':award.pool_key,'budget_atoms':award.budget_atoms,
        'submission_id':str(original.submission_id),'evidence_snapshot_id':str(original.evidence_snapshot_id),
        'evidence_snapshot_hash':original.target['evidence_snapshot_hash'],'attributions':entries,
        'before_attributions':balance_rows(db,award),'context':context,'context_hash':digest(context),
        'award_id':str(award.id),'resolver_id':str(assignment.resolver_id),
        'minimum_reviewers':policy.rules['review']['minimum_independent_reviewers'],
        'conflict_ids':conflicts,'criteria':[{'id':'resolution','text':'The reviewed evidence and accounting history support this resolution and its exact allocation; the original accepted budget is preserved.'}],
        'evidence_sources':refs,'notice':'Supplementary notes and URLs are unverified claims. Reviewers must inspect the underlying evidence. This correction preserves the original award and does not rewrite payouts.'}


def propose_resolution(db,project,package,item,actor,body):
    prior=replay(db,ReviewRound,project,body.request_id,command_hash(actor,body))
    if prior:
        if prior.dispute_id!=item.id:raise ApiError(409,'idempotency_conflict','That request belongs to another review.')
        return prior
    if body.reviewed_context_hash!=digest(dispute_context(db,project,item)):
        raise ApiError(409,'stale_dispute','The dispute or its supplementary evidence changed. Refresh before proposing a resolution.')
    assignment=current_assignment(db,item)
    if assignment is None or assignment.resolver_id!=actor.id:
        raise ApiError(403,'assigned_resolver_required','Only the current independent resolver can propose a resolution.')
    if actor.id not in body.reviewer_ids:
        raise ApiError(422,'resolver_in_quorum','Include the current resolver in the independent review quorum.')
    target=resolution_target(db,project,item.id,body.disposition,[e.model_dump(mode='json') for e in body.attributions])
    return store_round(db,project,package,actor,body,target,dispute_id=item.id)


def dispute_view(db,project,item,actor_id,role):
    award=get_award(db,project,item.award_id);assignment=current_assignment(db,item);closed=resolution(db,item)
    ctx=dispute_context(db,project,item)
    history=list(db.scalars(select(DisputeAssignment).where(DisputeAssignment.dispute_id==item.id)
        .order_by(DisputeAssignment.number)))
    return {'id':item.id,'award':award_view(db,project,award),'opened_by':item.opened_by,
        'reason':item.reason,'created_at':item.created_at,'state':'resolved' if closed else 'open',
        'context_hash':digest(ctx),'notes':ctx['notes'],'resolver_id':assignment.resolver_id if assignment else None,
        'resolver_candidates':reviewers_for(db,project,conflict_ids(db,project,item)),
        'current_participants':sorted(active_people(db,project).values(),key=lambda p:p['display_name']),
        'minimum_reviewers':get_policy(db,project,award.policy_id).rules['review']['minimum_independent_reviewers'],
        'assignments':[{'number':a.number,'resolver_id':a.resolver_id,'assigned_by':a.assigned_by,
            'reason':a.reason,'created_at':a.created_at} for a in history],
        'resolution':None if not closed else {'id':closed.id,'review_id':closed.review_id,
            'disposition':closed.disposition,'resolved_by':closed.resolved_by,'reason':closed.reason,'created_at':closed.created_at},
        'review_ids':[str(r.id) for r in db.scalars(select(ReviewRound).where(ReviewRound.dispute_id==item.id)
            .order_by(ReviewRound.number.desc()))],
        'can_assign':role=='admin' and not closed,'can_note':role!='viewer' and not closed,
        'can_propose':bool(not closed and assignment and assignment.resolver_id==actor_id),
        'notice':'Dispute text and source links are project-visible. Do not paste restricted source contents or secrets. URLs are not fetched. An open case blocks the affected pool, not every project pool.'}
