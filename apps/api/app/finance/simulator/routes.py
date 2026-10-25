from uuid import UUID
from fastapi import APIRouter, Query
from sqlalchemy import select
from app.auth.dependencies import Db, Authenticated
from app.projects.authorization import project_access
from . import service
from .models import SimulationScenario
from .schemas import PreviewInput, SaveScenario

router = APIRouter(prefix='/api/v1/workspaces/{workspace_id}/projects/{project_id}/simulator', tags=['hypothetical simulator'])


@router.get('/options')
def options(workspace_id: UUID, project_id: UUID, db: Db, identity: Authenticated):
    project, role = project_access(db, workspace_id, project_id, identity.user.id, lock=True)
    return service.options(db, project, identity.user.id, role)


@router.post('/preview')
def preview(workspace_id: UUID, project_id: UUID, body: PreviewInput, db: Db, identity: Authenticated):
    project, _ = project_access(db, workspace_id, project_id, identity.user.id, lock=True)
    # No INSERT/UPDATE of scenarios, awards, events, budgets or finances.
    return service.capture(db, project, identity.user.id, body)


@router.post('/scenarios', status_code=201)
def save(workspace_id: UUID, project_id: UUID, body: SaveScenario, db: Db, identity: Authenticated):
    project, role = project_access(db, workspace_id, project_id, identity.user.id, lock=True)
    row = service.save_scenario(db, project, identity.user, role, body)
    result = service.scenario_view(row)
    db.commit()
    return result


@router.get('/scenarios')
def scenarios(workspace_id: UUID, project_id: UUID, db: Db, identity: Authenticated,
              offset: int = Query(0, ge=0, le=1000), limit: int = Query(20, ge=1, le=50)):
    project, _ = project_access(db, workspace_id, project_id, identity.user.id, lock=True)
    rows = list(db.scalars(select(SimulationScenario).where(SimulationScenario.workspace_id == project.workspace_id,
        SimulationScenario.project_id == project.id).order_by(SimulationScenario.created_at.desc(),
        SimulationScenario.id).offset(offset).limit(limit + 1)))
    return {'items': [{'id': str(row.id), 'title': row.title, 'created_at': row.created_at,
                      'month': row.record['input']['month'], 'amount_cents': row.record['input']['amount_cents'],
                      'status': row.record['result']['status'], 'payable': False} for row in rows[:limit]],
            'offset': offset, 'next_offset': offset + limit if len(rows) > limit else None}


@router.get('/scenarios/{scenario_id}')
def scenario(workspace_id: UUID, project_id: UUID, scenario_id: UUID, db: Db, identity: Authenticated):
    project, _ = project_access(db, workspace_id, project_id, identity.user.id, lock=True)
    return service.scenario_view(service.get_scenario(db, project, scenario_id))
