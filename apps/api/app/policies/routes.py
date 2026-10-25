from uuid import UUID
from fastapi import APIRouter
from sqlalchemy import select
from app.auth.dependencies import Db, Authenticated
from app.projects.authorization import project_access
from app.policies.models import PolicyVersion
from app.policies.schemas import PolicyCreate, PolicyApprove, PolicyAcknowledge
from app.policies.service import (get_policy, policy_view, create_policy, approve_policy,
    acknowledge_policy, current_candidate, MAX_POLICY_VERSIONS)
from app.policies.templates import templates

router = APIRouter(prefix='/api/v1/workspaces/{workspace_id}/projects/{project_id}/policies', tags=['policies'])


@router.get('/templates')
def draft_templates(workspace_id: UUID, project_id: UUID, db: Db, identity: Authenticated):
    project, _ = project_access(db, workspace_id, project_id, identity.user.id, lock=True)
    return {'items': templates(project.timezone), 'notice': 'Draft examples, not recommendations or accepted economics.'}


@router.get('')
def policies(workspace_id: UUID, project_id: UUID, db: Db, identity: Authenticated):
    project, _ = project_access(db, workspace_id, project_id, identity.user.id, lock=True)
    rows = db.scalars(select(PolicyVersion).where(PolicyVersion.workspace_id == workspace_id,
        PolicyVersion.project_id == project_id).order_by(PolicyVersion.version.desc()).limit(MAX_POLICY_VERSIONS)).all()
    return {'items': [policy_view(db, project, row, identity.user.id) for row in rows],
        'latest_version': rows[0].version if rows else 0, 'current_candidate_id': current_candidate(db, project)}


@router.post('', status_code=201)
def policy_create(workspace_id: UUID, project_id: UUID, body: PolicyCreate, db: Db, identity: Authenticated):
    project, _ = project_access(db, workspace_id, project_id, identity.user.id, manage=True, lock=True)
    item = create_policy(db, project, identity.user, body)
    result = policy_view(db, project, item, identity.user.id)
    db.commit()
    return result


@router.get('/{policy_id}')
def policy_detail(workspace_id: UUID, project_id: UUID, policy_id: UUID, db: Db, identity: Authenticated):
    project, _ = project_access(db, workspace_id, project_id, identity.user.id, lock=True)
    return policy_view(db, project, get_policy(db, project, policy_id), identity.user.id)


@router.post('/{policy_id}/approve')
def policy_approve(workspace_id: UUID, project_id: UUID, policy_id: UUID, body: PolicyApprove, db: Db, identity: Authenticated):
    project, _ = project_access(db, workspace_id, project_id, identity.user.id, manage=True, lock=True)
    item = get_policy(db, project, policy_id)
    approve_policy(db, project, identity.user, item, body)
    result = policy_view(db, project, item, identity.user.id)
    db.commit()
    return result


@router.post('/{policy_id}/acknowledge')
def policy_acknowledge(workspace_id: UUID, project_id: UUID, policy_id: UUID, body: PolicyAcknowledge, db: Db, identity: Authenticated):
    project, _ = project_access(db, workspace_id, project_id, identity.user.id, lock=True)
    item = get_policy(db, project, policy_id)
    acknowledge_policy(db, project, identity.user, item, body)
    result = policy_view(db, project, item, identity.user.id)
    db.commit()
    return result
