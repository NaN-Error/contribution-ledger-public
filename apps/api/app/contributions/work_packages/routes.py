from app.contributions.reconstruction.models import ReconstructionBatch
from uuid import UUID
from fastapi import APIRouter, Query, Request
from sqlalchemy import select
from app.auth.dependencies import Db, Authenticated
from app.core.errors import ApiError
from app.projects.authorization import project_access, not_found
from app.contributions.budgets.models import BudgetAllocation, Milestone
from app.contributions.work_packages.models import WorkPackage, WorkPackageRevision, WorkSubmission
from app.contributions.work_packages.schemas import PackageCreate, ScopeEdit, PackageAction, State
from app.contributions.work_packages.service import (active_people, get_package, lock_package,
    package_summary, package_detail, create_package, edit_scope, perform_action, revision_view, MAX_PACKAGES)

router = APIRouter(prefix='/api/v1/workspaces/{workspace_id}/projects/{project_id}/work-packages', tags=['work packages'])


@router.get('/options')
def options(workspace_id: UUID, project_id: UUID, db: Db, identity: Authenticated):
    project, role = project_access(db, workspace_id, project_id, identity.user.id, lock=True)
    linked = select(WorkPackage.allocation_id).where(WorkPackage.workspace_id == workspace_id, WorkPackage.project_id == project_id)
    rows = db.execute(select(BudgetAllocation, Milestone).join(Milestone, Milestone.id == BudgetAllocation.milestone_id)
        .where(BudgetAllocation.workspace_id == workspace_id, BudgetAllocation.project_id == project_id,
               BudgetAllocation.id.not_in(linked), BudgetAllocation.status == 'active',
               BudgetAllocation.atoms > 0, BudgetAllocation.issued_atoms == 0, Milestone.status == 'active',
               Milestone.id.not_in(select(ReconstructionBatch.milestone_id).where(ReconstructionBatch.project_id == project_id)))
        .order_by(Milestone.created_at, BudgetAllocation.created_at, BudgetAllocation.id).limit(1001)).all()
    # Do not imply completeness when a pilot exceeds this bounded selector.
    return {'my_user_id': identity.user.id, 'can_create': role in {'admin','contributor'}, 'can_assess': role in {'admin','reviewer'},
        'participants': sorted(active_people(db, project).values(), key=lambda p: (p['display_name'].casefold(), p['user_id'])),
        'allocations': [{'id': a.id, 'milestone_id': m.id, 'milestone_name': m.name, 'policy_id': m.policy_id,
                         'title': a.title, 'category': a.category, 'pool_key': a.pool_key,
                         'atoms': a.atoms, 'version': a.version} for a, m in rows[:1000]],
        'allocations_truncated': len(rows) > 1000,
        'notice': 'Historical allocations are managed through Reconstruction. Only unlinked, positive, approved prospective allocations are listed. Current policy acknowledgements are rechecked when creating a package.'}


@router.get('')
def packages(workspace_id: UUID, project_id: UUID, db: Db, identity: Authenticated,
             q: str = Query('', max_length=120), state: State | None = None,
             category: str = Query('', max_length=30), offset: int = Query(0, ge=0, le=MAX_PACKAGES),
             limit: int = Query(20, ge=1, le=50)):
    project, _ = project_access(db, workspace_id, project_id, identity.user.id, lock=True)
    rows = db.scalars(select(WorkPackage).where(WorkPackage.workspace_id == workspace_id,
        WorkPackage.project_id == project_id).order_by(WorkPackage.created_at.desc(), WorkPackage.id).limit(MAX_PACKAGES))
    # Bounded local-pilot collection, not an unbounded in-memory search.
    items = [package_summary(db, project, row) for row in rows]
    needle = q.strip().casefold()
    items = [i for i in items if (not state or i['state'] == state) and (not category or i['category'] == category)
             and (not needle or needle in i['title'].casefold() or needle in i['coordinator_name'].casefold())]
    return {'items': items[offset:offset + limit], 'total': len(items), 'offset': offset,
            'next_offset': offset + limit if len(items) > offset + limit else None}


@router.post('', status_code=201)
def package_create(workspace_id: UUID, project_id: UUID, body: PackageCreate, db: Db, identity: Authenticated):
    project, role = project_access(db, workspace_id, project_id, identity.user.id, lock=True)
    item = create_package(db, project, identity.user, role, body)
    result = package_detail(db, project, item, identity.user.id, role)
    db.commit()
    return result


@router.get('/{package_id}')
def package_get(workspace_id: UUID, project_id: UUID, package_id: UUID, db: Db, identity: Authenticated,
                history_offset: int = Query(0, ge=0, le=2000)):
    project, role = project_access(db, workspace_id, project_id, identity.user.id, lock=True)
    return package_detail(db, project, get_package(db, project, package_id), identity.user.id, role, history_offset=history_offset)


@router.post('/{package_id}/revisions')
def scope_edit(workspace_id: UUID, project_id: UUID, package_id: UUID, body: ScopeEdit, db: Db, identity: Authenticated):
    project, role = project_access(db, workspace_id, project_id, identity.user.id, lock=True)
    item = lock_package(db, project, package_id)
    edit_scope(db, project, identity.user, role, item, body)
    result = package_detail(db, project, item, identity.user.id, role)
    db.commit()
    return result


@router.post('/{package_id}/actions')
def action(workspace_id: UUID, project_id: UUID, package_id: UUID, request: Request, body: PackageAction, db: Db, identity: Authenticated):
    project, role = project_access(db, workspace_id, project_id, identity.user.id, lock=True)
    item = lock_package(db, project, package_id)
    perform_action(db, project, identity.user, role, item, body, object_storage=request.app.state.object_storage)
    result = package_detail(db, project, item, identity.user.id, role)
    db.commit()
    return result


@router.get('/{package_id}/revisions/{number}')
def revision_get(workspace_id: UUID, project_id: UUID, package_id: UUID, number: int, db: Db, identity: Authenticated):
    project, _ = project_access(db, workspace_id, project_id, identity.user.id, lock=True)
    item = get_package(db, project, package_id)
    row = db.get(WorkPackageRevision, (item.id, number))
    if row is None:
        raise not_found()
    return revision_view(row)


@router.get('/{package_id}/submissions/{submission_id}')
def submission_get(workspace_id: UUID, project_id: UUID, package_id: UUID, submission_id: UUID, db: Db, identity: Authenticated):
    project, _ = project_access(db, workspace_id, project_id, identity.user.id, lock=True)
    item = get_package(db, project, package_id)
    row = db.scalar(select(WorkSubmission).where(WorkSubmission.id == submission_id,
        WorkSubmission.workspace_id == workspace_id, WorkSubmission.project_id == project_id,
        WorkSubmission.package_id == item.id))
    if row is None:
        raise not_found()
    return {'id': row.id, 'scope_revision': row.scope_revision, 'package_version': row.package_version,
            'submitted_by': row.submitted_by, 'snapshot': row.snapshot, 'snapshot_hash': row.snapshot_hash,
            'created_at': row.created_at}
