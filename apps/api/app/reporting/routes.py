from typing import Literal
from uuid import UUID
from fastapi import APIRouter
from app.auth.dependencies import Db,Authenticated
from app.projects.authorization import project_access
from app.policies.schemas import Category,PoolKey
from .service import dashboard

router=APIRouter(prefix='/api/v1/workspaces/{workspace_id}/projects/{project_id}/reports',tags=['contribution explanations'])


@router.get('/overview')
def overview(workspace_id:UUID,project_id:UUID,db:Db,identity:Authenticated,
             policy_id:UUID|None=None,pool_key:PoolKey|None=None,category:Category|None=None,
             origin:Literal['prospective','retrospective']|None=None,person_id:UUID|None=None):
    project,role=project_access(db,workspace_id,project_id,identity.user.id,lock=True)
    return dashboard(db,project,identity.user.id,role,policy_id=policy_id,pool_key=pool_key,
        category=category,origin=origin,person_id=person_id)
