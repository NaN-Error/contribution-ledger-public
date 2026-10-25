from uuid import UUID
from fastapi import APIRouter, Query
from sqlalchemy import select
from app.auth.dependencies import Db, Authenticated
from app.projects.authorization import project_access
from app.contributions.budgets.models import Milestone
from app.contributions.budgets.schemas import MilestoneCreate, AmendmentCreate, AmendmentDecision
from app.contributions.budgets.service import (get_milestone, milestone_view, milestone_detail,
    create_milestone, prepare_preview, propose_amendment, decide_amendment, amendment_view, MAX_MILESTONES)

router = APIRouter(prefix='/api/v1/workspaces/{workspace_id}/projects/{project_id}/milestones', tags=['milestone budgets'])


@router.get('')
def milestones(workspace_id: UUID, project_id: UUID, db: Db, identity: Authenticated):
    project, _ = project_access(db, workspace_id, project_id, identity.user.id, lock=True)
    rows = db.scalars(select(Milestone).where(Milestone.workspace_id == workspace_id, Milestone.project_id == project_id)
        .order_by(Milestone.created_at.desc(), Milestone.id).limit(MAX_MILESTONES))
    return {'items': [milestone_view(db, row) for row in rows]}


@router.post('', status_code=201)
def milestone_create(workspace_id: UUID, project_id: UUID, body: MilestoneCreate, db: Db, identity: Authenticated):
    project, _ = project_access(db, workspace_id, project_id, identity.user.id, manage=True, lock=True)
    row = create_milestone(db, project, identity.user, body)
    result = milestone_detail(db, project, row, identity.user.id)
    db.commit()
    return result


@router.get('/{milestone_id}')
def milestone_get(workspace_id: UUID, project_id: UUID, milestone_id: UUID, db: Db, identity: Authenticated,
                  history_offset: int = Query(0, ge=0, le=500)):
    project, _ = project_access(db, workspace_id, project_id, identity.user.id, lock=True)
    return milestone_detail(db, project, get_milestone(db, project, milestone_id), identity.user.id, history_offset=history_offset)


@router.post('/{milestone_id}/preview')
def milestone_preview(workspace_id: UUID, project_id: UUID, milestone_id: UUID, body: AmendmentCreate, db: Db, identity: Authenticated):
    project, _ = project_access(db, workspace_id, project_id, identity.user.id, manage=True, lock=True)
    # No writes; the lock makes the snapshot coherent with concurrent decisions.
    row = get_milestone(db, project, milestone_id, lock=True)
    return prepare_preview(db, project, row, body)


@router.post('/{milestone_id}/amendments', status_code=201)
def amendment_create(workspace_id: UUID, project_id: UUID, milestone_id: UUID, body: AmendmentCreate, db: Db, identity: Authenticated):
    project, _ = project_access(db, workspace_id, project_id, identity.user.id, manage=True, lock=True)
    row = get_milestone(db, project, milestone_id, lock=True)
    proposal = propose_amendment(db, project, identity.user, row, body)
    result = amendment_view(db, row, proposal)
    db.commit()
    return result


@router.post('/{milestone_id}/amendments/{amendment_id}/decision')
def amendment_decide(workspace_id: UUID, project_id: UUID, milestone_id: UUID, amendment_id: UUID,
                     body: AmendmentDecision, db: Db, identity: Authenticated):
    # Fixed lock order matches membership edits: workspace -> milestone.
    project, _ = project_access(db, workspace_id, project_id, identity.user.id, manage=True, lock=True)
    row = get_milestone(db, project, milestone_id, lock=True)
    decide_amendment(db, project, identity.user, row, amendment_id, body)
    result = milestone_detail(db, project, row, identity.user.id)
    db.commit()
    return result
