from uuid import UUID
from fastapi import APIRouter, Query, Request
from sqlalchemy import select, func
from app.auth.dependencies import Db, Authenticated
from app.core.errors import ApiError
from app.projects.authorization import project_access
from app.contributions.work_packages.service import get_package, lock_package, get_context, can_coordinate
from app.ledger.models import CreditAward
from app.ledger.service import get_award, contributions_view, award_view, reconcile
from app.ledger.models import ContributionEvent
from app.reviews.models import ReviewRound, CreditDispute, ParticipantNotification
from app.reviews.schemas import (ReviewCreate, DecisionCreate, Finalize, DisputeCreate,
    AssignResolver, NoteCreate, ResolutionCreate)
from app.reviews import service, disputes

router=APIRouter(prefix='/api/v1/workspaces/{workspace_id}/projects/{project_id}',tags=['human review and contribution ledger'])


@router.get('/reviews/options')
def options(workspace_id:UUID,project_id:UUID,package_id:UUID,request:Request,db:Db,identity:Authenticated):
    project,role=project_access(db,workspace_id,project_id,identity.user.id,lock=True)
    package=get_package(db,project,package_id);_,_,scope=get_context(db,project,package)
    items=[]
    for d in scope.document['deliverables']:
        award=db.scalar(select(CreditAward).where(CreditAward.package_id==package.id,CreditAward.deliverable_id==UUID(d['id'])))
        value={'deliverable_id':d['id'],'title':d['title'],'budget_atoms':d['budget_atoms'],'award_id':str(award.id) if award else None}
        try:
            target=service.award_target(db,project,package,UUID(d['id']),request.app.state.object_storage)
            value.update(target_hash=service.digest(target),minimum_reviewers=target['minimum_reviewers'],
                eligible_reviewers=service.reviewers_for(db,project,target['conflict_ids']),blocker=None)
        except ApiError as e:value.update(blocker=e.message,eligible_reviewers=[],minimum_reviewers=None,target_hash=None)
        items.append(value)
    return {'package_id':package.id,'package_version':package.version,'items':items,
        'can_assign':can_coordinate(package,scope.document,role,identity.user.id),
        'notice':'Select independent reviewers for each accepted portion. A review assignment and an approval vote do not issue credit.'}


@router.post('/reviews',status_code=201)
def create_review(workspace_id:UUID,project_id:UUID,body:ReviewCreate,request:Request,db:Db,identity:Authenticated):
    project,role=project_access(db,workspace_id,project_id,identity.user.id,lock=True)
    package=lock_package(db,project,body.package_id)
    review=service.create_review(db,project,package,identity.user,role,body,request.app.state.object_storage)
    result=service.review_view(db,project,package,review,identity.user.id,role,request.app.state.object_storage)
    db.commit();return result


@router.get('/reviews')
def review_list(workspace_id:UUID,project_id:UUID,request:Request,db:Db,identity:Authenticated,
    package_id:UUID|None=None,offset:int=Query(0,ge=0,le=100000),limit:int=Query(20,ge=1,le=50)):
    project,role=project_access(db,workspace_id,project_id,identity.user.id,lock=True)
    query=select(ReviewRound).where(ReviewRound.workspace_id==workspace_id,ReviewRound.project_id==project_id)
    if package_id:
        get_package(db,project,package_id);query=query.where(ReviewRound.package_id==package_id)
    rows=list(db.scalars(query.order_by(ReviewRound.created_at.desc(),ReviewRound.id).offset(offset).limit(limit+1)))
    items=[]
    for row in rows[:limit]:
        package=get_package(db,project,row.package_id)
        state,blocker=service.review_state(db,project,package,row,request.app.state.object_storage)
        items.append({'id':row.id,'package_id':row.package_id,'title':row.target['title'],
            'package_title':row.target['package_title'],'kind':row.kind,'number':row.number,
            'state':state,'blocker':blocker,'created_at':row.created_at})
    return {'items':items,'offset':offset,'next_offset':offset+limit if len(rows)>limit else None}


@router.get('/reviews/{review_id}')
def review_get(workspace_id:UUID,project_id:UUID,review_id:UUID,request:Request,db:Db,identity:Authenticated):
    project,role=project_access(db,workspace_id,project_id,identity.user.id,lock=True)
    review=service.get_review(db,project,review_id);package=get_package(db,project,review.package_id)
    return service.review_view(db,project,package,review,identity.user.id,role,request.app.state.object_storage)


@router.post('/reviews/{review_id}/decisions')
def decision(workspace_id:UUID,project_id:UUID,review_id:UUID,body:DecisionCreate,request:Request,db:Db,identity:Authenticated):
    project,role=project_access(db,workspace_id,project_id,identity.user.id,lock=True)
    review=service.get_review(db,project,review_id);package=lock_package(db,project,review.package_id)
    service.decide(db,project,package,review,identity.user,body,request.app.state.object_storage)
    result=service.review_view(db,project,package,review,identity.user.id,role,request.app.state.object_storage)
    db.commit();return result


@router.post('/reviews/{review_id}/finalize')
def finalize(workspace_id:UUID,project_id:UUID,review_id:UUID,body:Finalize,request:Request,db:Db,identity:Authenticated):
    project,role=project_access(db,workspace_id,project_id,identity.user.id,lock=True)
    review=service.get_review(db,project,review_id);package=lock_package(db,project,review.package_id)
    service.finalize_review(db,project,package,review,identity.user,body,request.app.state.object_storage)
    result=service.review_view(db,project,package,review,identity.user.id,role,request.app.state.object_storage)
    db.commit();return result


@router.get('/contributions')
def contributions(workspace_id:UUID,project_id:UUID,db:Db,identity:Authenticated):
    project,_=project_access(db,workspace_id,project_id,identity.user.id,lock=True)
    return contributions_view(db,project,identity.user.id)


@router.get('/contributions/integrity')
def integrity(workspace_id:UUID,project_id:UUID,db:Db,identity:Authenticated):
    project,_=project_access(db,workspace_id,project_id,identity.user.id,manage=True,lock=True)
    return reconcile(db,project)


@router.get('/contributions/awards')
def awards(workspace_id:UUID,project_id:UUID,db:Db,identity:Authenticated,offset:int=Query(0,ge=0,le=100000),limit:int=Query(20,ge=1,le=50)):
    project,_=project_access(db,workspace_id,project_id,identity.user.id,lock=True)
    rows=list(db.scalars(select(CreditAward).where(CreditAward.workspace_id==workspace_id,CreditAward.project_id==project_id)
        .order_by(CreditAward.created_at.desc(),CreditAward.id).offset(offset).limit(limit+1)))
    return {'items':[award_view(db,project,a) for a in rows[:limit]],'offset':offset,'next_offset':offset+limit if len(rows)>limit else None}


@router.get('/contributions/awards/{award_id}')
def award_get(workspace_id:UUID,project_id:UUID,award_id:UUID,db:Db,identity:Authenticated,
    offset:int=Query(0,ge=0,le=100000),limit:int=Query(50,ge=1,le=100)):
    project,_=project_access(db,workspace_id,project_id,identity.user.id,lock=True)
    award=get_award(db,project,award_id)
    rows=list(db.scalars(select(ContributionEvent).where(ContributionEvent.award_id==award.id)
        .order_by(ContributionEvent.created_at,ContributionEvent.id).offset(offset).limit(limit+1)))
    return {**award_view(db,project,award),'events':[{'id':e.id,'review_id':e.review_id,'resolution_id':e.resolution_id,
        'kind':e.kind,'user_id':e.user_id,'display_name':e.display_name,'role':e.role,'delta_atoms':e.delta_atoms,
        'created_at':e.created_at} for e in rows[:limit]],'offset':offset,'next_offset':offset+limit if len(rows)>limit else None}


@router.post('/disputes',status_code=201)
def dispute_create(workspace_id:UUID,project_id:UUID,body:DisputeCreate,db:Db,identity:Authenticated):
    project,role=project_access(db,workspace_id,project_id,identity.user.id,lock=True)
    award=get_award(db,project,body.award_id);package=lock_package(db,project,award.package_id)
    item=disputes.create_dispute(db,project,package,identity.user,role,body)
    result=disputes.dispute_view(db,project,item,identity.user.id,role);db.commit();return result


@router.get('/disputes')
def dispute_list(workspace_id:UUID,project_id:UUID,db:Db,identity:Authenticated,offset:int=Query(0,ge=0,le=2000),limit:int=Query(20,ge=1,le=50)):
    project,_=project_access(db,workspace_id,project_id,identity.user.id,lock=True)
    rows=list(db.scalars(select(CreditDispute).where(CreditDispute.workspace_id==workspace_id,CreditDispute.project_id==project_id)
        .order_by(CreditDispute.created_at.desc(),CreditDispute.id).offset(offset).limit(limit+1)))
    return {'items':[{'id':d.id,'award_id':d.award_id,'package_id':d.package_id,'reason':d.reason,
        'state':'resolved' if disputes.resolution(db,d) else 'open','created_at':d.created_at} for d in rows[:limit]],
        'offset':offset,'next_offset':offset+limit if len(rows)>limit else None}


@router.get('/disputes/{dispute_id}')
def dispute_get(workspace_id:UUID,project_id:UUID,dispute_id:UUID,db:Db,identity:Authenticated):
    project,role=project_access(db,workspace_id,project_id,identity.user.id,lock=True)
    return disputes.dispute_view(db,project,disputes.get_dispute(db,project,dispute_id),identity.user.id,role)


@router.post('/disputes/{dispute_id}/assignments')
def resolver_assign(workspace_id:UUID,project_id:UUID,dispute_id:UUID,body:AssignResolver,db:Db,identity:Authenticated):
    project,role=project_access(db,workspace_id,project_id,identity.user.id,lock=True)
    item=disputes.get_dispute(db,project,dispute_id);package=lock_package(db,project,item.package_id)
    disputes.assign_resolver(db,project,package,item,identity.user,role,body)
    result=disputes.dispute_view(db,project,item,identity.user.id,role);db.commit();return result


@router.post('/disputes/{dispute_id}/notes',status_code=201)
def note_add(workspace_id:UUID,project_id:UUID,dispute_id:UUID,body:NoteCreate,db:Db,identity:Authenticated):
    project,role=project_access(db,workspace_id,project_id,identity.user.id,lock=True)
    item=disputes.get_dispute(db,project,dispute_id);package=lock_package(db,project,item.package_id)
    disputes.add_note(db,project,package,item,identity.user,role,body)
    result=disputes.dispute_view(db,project,item,identity.user.id,role);db.commit();return result


@router.post('/disputes/{dispute_id}/proposals',status_code=201)
def resolution_propose(workspace_id:UUID,project_id:UUID,dispute_id:UUID,body:ResolutionCreate,request:Request,db:Db,identity:Authenticated):
    project,role=project_access(db,workspace_id,project_id,identity.user.id,lock=True)
    item=disputes.get_dispute(db,project,dispute_id);package=lock_package(db,project,item.package_id)
    review=disputes.propose_resolution(db,project,package,item,identity.user,body)
    result=service.review_view(db,project,package,review,identity.user.id,role,request.app.state.object_storage)
    db.commit();return result


@router.get('/notifications')
def notifications(workspace_id:UUID,project_id:UUID,db:Db,identity:Authenticated,
    offset:int=Query(0,ge=0,le=100000),limit:int=Query(20,ge=1,le=50)):
    project,_=project_access(db,workspace_id,project_id,identity.user.id,lock=True)
    rows=list(db.scalars(select(ParticipantNotification).where(ParticipantNotification.workspace_id==workspace_id,
        ParticipantNotification.project_id==project_id,ParticipantNotification.recipient_id==identity.user.id)
        .order_by(ParticipantNotification.created_at.desc(),ParticipantNotification.id).offset(offset).limit(limit+1)))
    return {'items':[{'id':n.id,'kind':n.kind,'subject_id':n.subject_id,'message':n.message,'created_at':n.created_at} for n in rows[:limit]],
        'offset':offset,'next_offset':offset+limit if len(rows)>limit else None,'notice':'In-app records only. No email or external notification was sent.'}
