"""Dedicated posting path. Callers hold workspace -> milestone -> package locks.

Ordinary routes cannot set a balance. Events are the accounting source; the
projection can be checked/rebuilt without invoking any evaluator. Adjustments
redistribute an existing award; they never create or erase its accepted budget.
"""
from collections import defaultdict
from uuid import UUID, uuid4
from sqlalchemy import select, func, delete
from app.core.errors import ApiError
from app.projects.authorization import not_found
from app.policies.service import digest, get_policy
from app.contributions.budgets.models import Milestone, BudgetAllocation
from app.contributions.work_packages.models import WorkPackage, WorkPackageRevision
from app.ledger.models import CreditAward, ContributionEvent, ContributionBalance
from app.reviews.models import CreditDispute, DisputeResolution, ReviewRound


def scope_fields(project, package):
    return dict(workspace_id=project.workspace_id,project_id=project.id,package_id=package.id)


def get_award(db, project, award_id):
    row=db.scalar(select(CreditAward).where(CreditAward.id==award_id,
        CreditAward.workspace_id==project.workspace_id,CreditAward.project_id==project.id))
    if row is None: raise not_found()
    return row


def event_balances(db, award):
    # Use the immutable ledger rather than trusting a mutable cached balance.
    rows=db.execute(select(ContributionEvent.user_id, ContributionEvent.role,
        func.sum(ContributionEvent.delta_atoms)).where(ContributionEvent.award_id==award.id)
        .group_by(ContributionEvent.user_id,ContributionEvent.role)).all()
    result={(str(uid),role):int(atoms) for uid,role,atoms in rows}
    if any(atoms<0 for atoms in result.values()) or sum(result.values())!=award.budget_atoms:
        raise ApiError(409,'ledger_integrity_error','Award events do not reconcile. Stop and inspect the preserved history.')
    return result


def balance_rows(db, award):
    balances=event_balances(db,award)
    labels={str(row.user_id):row.display_name for row in db.scalars(select(ContributionEvent)
        .where(ContributionEvent.award_id==award.id).order_by(ContributionEvent.created_at,ContributionEvent.id))}
    return [{'user_id':uid,'role':role,'atoms':atoms,'display_name':labels.get(uid,uid)}
        for (uid,role),atoms in sorted(balances.items()) if atoms]


def balance_hash(db, award):
    return digest({'award_id':str(award.id),'entries':balance_rows(db,award)})


def post_lines(db, project, package, award, review_id, entries, *, resolution_id=None):
    """Append lines and update per-award projections in the same transaction."""
    for line in entries:
        delta=line['atoms']
        if not delta: continue
        uid=UUID(line['user_id']); key=(award.id,uid,line['role'])
        existing=db.get(ContributionBalance,key)
        value=(existing.atoms if existing else 0)+delta
        if value<0 or value>award.budget_atoms:
            raise ApiError(409,'negative_entitlement','This correction would create an invalid per-award balance.')
        db.add(ContributionEvent(id=uuid4(),**scope_fields(project,package),award_id=award.id,
            review_id=review_id,resolution_id=resolution_id,user_id=uid,role=line['role'],
            display_name=line['display_name'],delta_atoms=delta,kind='adjustment' if resolution_id else 'award'))
        if existing: existing.atoms=value
        else: db.add(ContributionBalance(**scope_fields(project,package),award_id=award.id,
            user_id=uid,role=line['role'],atoms=value))
    db.flush()
    event_balances(db,award)


def issue_award(db, project, package, review, actor, body, command_hash):
    target=review.target
    allocation=db.get(BudgetAllocation,package.allocation_id)
    milestone=db.get(Milestone,package.milestone_id)
    amount=target['budget_atoms']
    # Defensive reconciliation before writing any effect, under the tenant lock.
    issued=int(db.scalar(select(func.coalesce(func.sum(CreditAward.budget_atoms),0))
        .where(CreditAward.allocation_id==allocation.id)))
    milestone_issued=int(db.scalar(select(func.coalesce(func.sum(CreditAward.budget_atoms),0))
        .where(CreditAward.milestone_id==milestone.id)))
    if issued!=allocation.issued_atoms or milestone_issued!=milestone.issued_atoms:
        raise ApiError(409,'projection_mismatch','Issued budget projections differ from preserved awards. Inspect and repair projections first.')
    if issued+amount>allocation.atoms or milestone_issued+amount>milestone.allocated_atoms:
        raise ApiError(409,'award_budget_exceeded','Acceptance exceeds the approved parent budget.')
    if sum(e['atoms'] for e in target['attributions'])!=amount:
        raise ApiError(409,'invalid_attribution','The preserved attribution does not equal the accepted budget.')
    award=CreditAward(id=uuid4(),**scope_fields(project,package),milestone_id=milestone.id,
        allocation_id=allocation.id,policy_id=review.policy_id,review_id=review.id,
        deliverable_id=review.deliverable_id,budget_atoms=amount,pool_key=target['pool_key'],
        original_attributions=target['attributions'],finalized_by=actor.id,
        request_id=body.request_id,request_hash=command_hash,reason=body.reason)
    db.add(award);db.flush()
    post_lines(db,project,package,award,review.id,target['attributions'])
    allocation.issued_atoms+=amount
    # allocation.version describes planning scope, not credit; changing it would
    # falsely stale all remaining deliverables against unchanged scope.
    milestone.issued_atoms+=amount;milestone.version+=1
    if allocation.issued_atoms==allocation.atoms: package.state='completed'
    db.flush()
    return award


def reallocate_award(db, project, package, award, review, resolution):
    before=event_balances(db,award)
    after={(e['user_id'],e['role']):e['atoms'] for e in review.target['attributions']}
    if any(v<0 for v in after.values()) or sum(after.values())!=award.budget_atoms:
        raise ApiError(409,'invalid_correction','Corrections must preserve the exact accepted budget and nonnegative entitlements.')
    projected={(str(r.user_id),r.role):r.atoms for r in db.scalars(select(ContributionBalance)
        .where(ContributionBalance.award_id==award.id))}
    if {k:v for k,v in projected.items() if v}!={k:v for k,v in before.items() if v}:
        raise ApiError(409,'projection_mismatch','Balance projections do not match the ledger. Inspect them before correcting attribution.')
    labels={e['user_id']:e['display_name'] for e in [*balance_rows(db,award),*review.target['attributions']]}
    deltas=[{'user_id':uid,'role':role,'atoms':after.get((uid,role),0)-before.get((uid,role),0),
             'display_name':labels[uid]} for uid,role in sorted(set(before)|set(after))]
    if sum(e['atoms'] for e in deltas)!=0: raise ApiError(409,'unbalanced_adjustment','Adjustment lines must net to zero.')
    post_lines(db,project,package,award,review.id,deltas,resolution_id=resolution.id)


def open_disputes(db, project, *, policy_id=None,pool_key=None,milestone_id=None):
    query=select(CreditDispute).join(CreditAward,CreditAward.id==CreditDispute.award_id).where(
        CreditDispute.workspace_id==project.workspace_id,CreditDispute.project_id==project.id,
        ~select(DisputeResolution.id).where(DisputeResolution.dispute_id==CreditDispute.id).exists())
    if policy_id: query=query.where(CreditAward.policy_id==policy_id)
    if pool_key: query=query.where(CreditAward.pool_key==pool_key)
    if milestone_id: query=query.where(CreditAward.milestone_id==milestone_id)
    return list(db.scalars(query.order_by(CreditDispute.created_at,CreditDispute.id)))


def require_clear_pool(db, project, policy_id, pool_key, *, milestone_id=None):
    """Mandatory future finance-close guard; phase 6 does not have a close route."""
    if open_disputes(db,project,policy_id=policy_id,pool_key=pool_key,milestone_id=milestone_id):
        raise ApiError(409,'unresolved_dispute','An unresolved credit dispute blocks this pool from closing.')


def award_view(db, project, award):
    review=db.get(ReviewRound,award.review_id)
    return {'id':award.id,'package_id':award.package_id,'deliverable_id':award.deliverable_id,
        'title':review.target['title'],'budget_atoms':award.budget_atoms,'pool_key':award.pool_key,
        'policy_id':award.policy_id,'policy_version':review.target['policy_version'],
        'milestone_id':award.milestone_id,'review_id':award.review_id,
        'submission_id':review.submission_id,'evidence_snapshot_id':review.evidence_snapshot_id,
        'original_attributions':award.original_attributions,'current_attributions':balance_rows(db,award),
        'current_balance_hash':balance_hash(db,award),'finalized_by':award.finalized_by,
        'reason':award.reason,'created_at':award.created_at}


def contributions_view(db, project, user_id):
    awards=list(db.scalars(select(CreditAward).where(CreditAward.project_id==project.id,
        CreditAward.workspace_id==project.workspace_id).order_by(CreditAward.created_at,CreditAward.id)))
    groups={}
    for award in awards:
        key=(str(award.policy_id),str(award.milestone_id),award.pool_key)
        if key not in groups:
            policy=get_policy(db,project,award.policy_id); milestone=db.get(Milestone,award.milestone_id)
            groups[key]={'policy_id':str(policy.id),'policy_version':policy.version,'milestone_id':str(milestone.id),
                'milestone_name':milestone.name,'pool_key':award.pool_key,'denominator_atoms':0,'people':{},'award_ids':[]}
        group=groups[key];group['denominator_atoms']+=award.budget_atoms;group['award_ids'].append(str(award.id))
        for e in balance_rows(db,award):
            person=group['people'].setdefault(e['user_id'],{'user_id':e['user_id'],'display_name':e['display_name'],'atoms':0,'roles':{}})
            person['atoms']+=e['atoms'];person['roles'][e['role']]=person['roles'].get(e['role'],0)+e['atoms']
    pending={}
    for allocation in db.scalars(select(BudgetAllocation).where(BudgetAllocation.project_id==project.id,
        BudgetAllocation.workspace_id==project.workspace_id,BudgetAllocation.status=='active')):
        milestone=db.get(Milestone,allocation.milestone_id)
        key=(str(milestone.policy_id),str(milestone.id),allocation.pool_key)
        pending[key]=pending.get(key,0)+allocation.atoms-allocation.issued_atoms
    open_cases=open_disputes(db,project)
    disputed_awards={str(d.award_id) for d in open_cases}
    for key,g in groups.items():
        g['people']=sorted(g['people'].values(),key=lambda p:(-p['atoms'],p['user_id']))
        for person in g['people']:
            person['share']={'numerator':person['atoms'],'denominator':g['denominator_atoms']}
        g['pending_planned_atoms']=pending.get(key,0)
        g['disputed_atoms']=sum(a.budget_atoms for a in awards if str(a.id) in g['award_ids'] and str(a.id) in disputed_awards)
        g['close_blocked']=g['disputed_atoms']>0
    return {'groups':list(groups.values()),'my_user_id':str(user_id),
        'total_issued_atoms':sum(a.budget_atoms for a in awards),'pending_planned_atoms':sum(pending.values()),
        'open_dispute_count':len(open_cases),'award_count':len(awards),
        'notice':'Shares are finalized eligible units within the named policy, milestone and pool. They are not objective worth, permanent release shares, ownership or payments. Future work may change the denominator.'}


def reconcile(db, project, *, repair=False):
    """Operator-only repair of derived caches. Never writes/deletes ledger events."""
    awards=list(db.scalars(select(CreditAward).where(CreditAward.project_id==project.id)))
    expected={};allocations=defaultdict(int);milestones=defaultdict(int)
    for award in awards:
        for (uid,role),atoms in event_balances(db,award).items():
            expected[(award.id,UUID(uid),role)]=atoms
        allocations[award.allocation_id]+=award.budget_atoms;milestones[award.milestone_id]+=award.budget_atoms
    actual={(r.award_id,r.user_id,r.role):r.atoms for r in db.scalars(select(ContributionBalance).where(ContributionBalance.project_id==project.id))}
    differences=[]
    if {k:v for k,v in actual.items() if v}!={k:v for k,v in expected.items() if v}: differences.append('contribution_balances')
    for a in db.scalars(select(BudgetAllocation).where(BudgetAllocation.project_id==project.id)):
        if a.issued_atoms!=allocations[a.id]: differences.append('allocation:'+str(a.id))
    for m in db.scalars(select(Milestone).where(Milestone.project_id==project.id)):
        if m.issued_atoms!=milestones[m.id]: differences.append('milestone:'+str(m.id))
    if repair:
        # The operator must have separately taken the same project/tenant locks.
        db.execute(delete(ContributionBalance).where(ContributionBalance.project_id==project.id))
        by_id={a.id:a for a in awards}
        for (aid,uid,role),atoms in expected.items():
            a=by_id[aid]
            db.add(ContributionBalance(workspace_id=project.workspace_id,project_id=project.id,
                package_id=a.package_id,award_id=aid,user_id=uid,role=role,atoms=atoms))
        for a in db.scalars(select(BudgetAllocation).where(BudgetAllocation.project_id==project.id)):
            if allocations[a.id]>a.atoms: raise ApiError(409,'ledger_budget_corrupt','Ledger awards exceed a parent budget; a projection repair cannot fix that.')
            a.issued_atoms=allocations[a.id]
        for m in db.scalars(select(Milestone).where(Milestone.project_id==project.id)):
            m.issued_atoms=milestones[m.id]
        db.flush()
    return {'consistent':not differences,'differences':differences,'award_count':len(awards),
        'ledger_atoms':sum(a.budget_atoms for a in awards),'repaired':repair and bool(differences)}


def can_extend_partial_evidence(db, package, allocation):
    """Allow new evidence for unfinished portions without modifying accepted scope."""
    if package.state!='submitted' or not 0<allocation.issued_atoms<allocation.atoms:
        return False
    awards=list(db.scalars(select(CreditAward).where(CreditAward.package_id==package.id)))
    if sum(a.budget_atoms for a in awards)!=allocation.issued_atoms:
        return False
    return all(db.get(ReviewRound,a.review_id).target.get('scope_revision')==package.scope_revision for a in awards)
