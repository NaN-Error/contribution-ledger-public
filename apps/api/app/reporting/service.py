"""Exact scoped activity/credit explanations. Activity is never a proxy for value."""
from collections import defaultdict
from sqlalchemy import select,func
from app.core.errors import ApiError
from app.security.tokens import now,utc
from app.policies.service import digest,get_policy
from app.ledger.models import CreditAward
from app.ledger.service import balance_rows,open_disputes
from app.contributions.budgets.models import BudgetAllocation,Milestone
from app.contributions.work_packages.models import WorkPackage,WorkPackageRevision
from app.contributions.reconstruction.models import ReconstructionCandidate,ReconstructionBatch
from app.integrations.github.models import GitHubSourceVersion
from app.contributions.reconstruction.grouping import entity_key
from app.reviews.models import ReviewRound


def dashboard(db,project,actor_id,role,*,policy_id=None,pool_key=None,category=None,origin=None,person_id=None):
    if policy_id:get_policy(db,project,policy_id)  # Explicit wrong-project filter is 404, not an empty pretend report.
    awards=list(db.scalars(select(CreditAward).where(CreditAward.project_id==project.id,
        CreditAward.workspace_id==project.workspace_id).order_by(CreditAward.id).limit(6001)))
    if len(awards)>6000:raise ApiError(409,'report_limit','The local pilot limits one project report to 6,000 accepted deliverables.')
    historic={c.package_id:c for c in db.scalars(select(ReconstructionCandidate).where(ReconstructionCandidate.project_id==project.id,
        ReconstructionCandidate.workspace_id==project.workspace_id,ReconstructionCandidate.package_id.is_not(None)))}
    disputes=open_disputes(db,project);disputed={d.award_id for d in disputes};groups={};filtered_ids=[]
    for a in awards:
        review=db.get(ReviewRound,a.review_id);kind='retrospective' if a.package_id in historic else 'prospective'
        cat=review.target.get('category')
        if not cat:
            package=db.get(WorkPackage,a.package_id)
            cat=db.get(WorkPackageRevision,(package.id,package.scope_revision)).document['category']
        if policy_id and a.policy_id!=policy_id or pool_key and a.pool_key!=pool_key or category and cat!=category or origin and kind!=origin:continue
        filtered_ids.append(str(a.id));key=(str(a.policy_id),a.pool_key)
        if key not in groups:
            policy=get_policy(db,project,a.policy_id)
            groups[key]={'policy_id':str(policy.id),'policy_version':policy.version,'pool_key':a.pool_key,
                'denominator_atoms':0,'people':{},'by_category':{},'by_origin':{},'disputed_atoms':0,
                'accepted_deliverable_count':0,'evidence_snapshot_count':0}
        group=groups[key];group['denominator_atoms']+=a.budget_atoms;group['accepted_deliverable_count']+=1
        group['by_category'][cat]=group['by_category'].get(cat,0)+a.budget_atoms
        group['by_origin'][kind]=group['by_origin'].get(kind,0)+a.budget_atoms
        if a.id in disputed:group['disputed_atoms']+=a.budget_atoms
        if review.evidence_snapshot_id:group['evidence_snapshot_count']+=1
        for e in balance_rows(db,a):
            p=group['people'].setdefault(e['user_id'],{'user_id':e['user_id'],'display_name':e['display_name'],'atoms':0,'roles':{},'award_ids':[]})
            p['atoms']+=e['atoms'];p['roles'][e['role']]=p['roles'].get(e['role'],0)+e['atoms']
            if str(a.id) not in p['award_ids']:p['award_ids'].append(str(a.id))
    for g in groups.values():
        people=sorted(g['people'].values(),key=lambda p:(p['display_name'].casefold(),p['user_id']))
        for p in people:p['share']={'numerator':p['atoms'],'denominator':g['denominator_atoms']}
        g['people']=[p for p in people if not person_id or p['user_id']==str(person_id)]
        g['person_filter_keeps_denominator']=True
    pending=[]
    for allocation,milestone in db.execute(select(BudgetAllocation,Milestone).join(Milestone,Milestone.id==BudgetAllocation.milestone_id)
        .where(BudgetAllocation.project_id==project.id,BudgetAllocation.workspace_id==project.workspace_id,BudgetAllocation.status=='active')):
        if allocation.atoms<=allocation.issued_atoms:continue
        batch=db.scalar(select(ReconstructionBatch.id).where(ReconstructionBatch.milestone_id==milestone.id))
        kind='retrospective' if batch else 'prospective'
        if policy_id and milestone.policy_id!=policy_id or pool_key and allocation.pool_key!=pool_key or category and allocation.category!=category or origin and kind!=origin:continue
        pending.append({'allocation_id':str(allocation.id),'policy_id':str(milestone.policy_id),'pool_key':allocation.pool_key,
            'category':allocation.category,'origin':kind,'pending_atoms':allocation.atoms-allocation.issued_atoms})
    filters={'policy_id':str(policy_id) if policy_id else None,'pool_key':pool_key,'category':category,'origin':origin,
        'person_id':str(person_id) if person_id else None}
    credits={'groups':list(groups.values()),'selected_award_ids':filtered_ids,'pending_planned_atoms':sum(x['pending_atoms'] for x in pending),
        'pending_allocations':pending,'filters':filters}
    activity=None
    if role in {'admin','reviewer'}:
        sources=list(db.scalars(select(GitHubSourceVersion).where(GitHubSourceVersion.project_id==project.id,
            GitHubSourceVersion.workspace_id==project.workspace_id).order_by(GitHubSourceVersion.id).limit(20001)))
        if len(sources)>20000:
            activity={'available':False,'reason':'The activity scan exceeds the 20,000-version local reporting bound; no partial counts are shown.'}
        else:
            seen=set();counts=defaultdict(int)
            for source in sources:
                key=entity_key(source)
                if key not in seen:counts[source.kind]+=1;seen.add(key)
            activity={'available':True,'scope':'Entire connected project history retained locally; independent of contribution filters.',
                'unique_observed_entities':dict(sorted(counts.items())),'retained_version_count':len(sources),
                'notice':'An entity may have several observed versions. These are activity counts, not effort, outcome count or economic value. Unknown or unimported work is not zero work.'}
    return {**credits,'snapshot_hash':digest(credits),'captured_at':now().isoformat(),'my_user_id':str(actor_id),'activity':activity,
        'denominator_label':'Finalized contribution atoms within each displayed policy and pool, restricted by the displayed category/origin filters. Selecting one person does not shrink the denominator.',
        'evidence_notice':'Snapshot counts indicate archived evidence references, not an AI sufficiency score or proof of correctness. Human decisions remain the basis of accepted credit.',
        'notice':'No cross-project ranking, inferred labor hours, objective meaningfulness score, permanent ownership or payable distribution is calculated.'}
