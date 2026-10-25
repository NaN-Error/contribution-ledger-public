"""Guard older milestone commands against bypassing an attached work package.

The workspace/milestone transaction locks must already be held. Imported lazily
by budget services so that every proposal AND every decision sees current links.
"""
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.errors import ApiError
from app.contributions.work_packages.models import WorkPackage, WorkPackageRevision


def linked_package(db: Session, allocation_id: UUID) -> WorkPackage | None:
    return db.scalar(select(WorkPackage).where(WorkPackage.allocation_id == allocation_id)
                     .with_for_update().execution_options(populate_existing=True))


def guard_change(db: Session, project, milestone, change: dict, *, cancelling_package_id: UUID | None = None):
    from app.contributions.reconstruction.models import ReconstructionBatch
    historical = db.scalar(select(ReconstructionBatch).where(ReconstructionBatch.milestone_id == milestone.id))
    if historical and historical.state == 'frozen':
        raise ApiError(409, 'opening_balance_frozen', 'This historical milestone is frozen. Create a new milestone for later work.')
    if change['kind'] not in {'resize_allocation', 'cancel_allocation'}:
        return None
    item = linked_package(db, UUID(str(change['allocation_id'])))
    if item is None:
        return None
    if item.workspace_id != project.workspace_id or item.project_id != project.id or item.milestone_id != milestone.id:
        raise ApiError(404, 'not_found', 'The allocation is not available in this project.')
    if change['kind'] == 'cancel_allocation':
        if cancelling_package_id != item.id:
            raise ApiError(409, 'linked_package', 'Cancel this allocation through its work package so its scope and history are preserved.')
    else:
        if item.state != 'draft' or item.approved_revision is not None:
            raise ApiError(409, 'package_amendment_required', 'Create a work-package scope amendment before resizing its approved allocation.')
        revision = db.get(WorkPackageRevision, (item.id, item.scope_revision))
        if change['atoms'] < revision.document['deliverable_atoms']:
            raise ApiError(409, 'deliverable_budget_bound', 'Amend the draft deliverables first; the new allocation is below their combined budgets.')
    return item


def after_resize(db: Session, project, actor, allocation_id: UUID, reason: str):
    item = linked_package(db, allocation_id)
    if item is None:
        return
    # Rebind the draft to the exact new parent budget; preserve old snapshots.
    from app.contributions.work_packages.service import get_context, append_revision, record_event
    from app.contributions.work_packages.calculation import input_from_snapshot
    milestone, allocation, revision = get_context(db, project, item)
    item.scope_revision += 1
    item.version += 1
    append_revision(db, project, actor, item, allocation, input_from_snapshot(revision.document), reason)
    record_event(db, item, actor, 'budget_rebound', reason,
                 {'allocation_version': allocation.version, 'budget_atoms': allocation.atoms})
