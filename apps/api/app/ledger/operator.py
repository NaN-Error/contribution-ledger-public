"""Audited operator-only verification/repair of projections, never ledger history."""
from uuid import UUID
from sqlalchemy import select
from app.auth.operator import check_reason
from app.projects.models import Workspace, Project
from app.projects.authorization import not_found
from app.contributions.budgets.models import Milestone
from app.contributions.work_packages.models import WorkPackage
from app.ledger.service import reconcile
from app.security.audit import audit


def inspect_credit(database, workspace_id: UUID, project_id: UUID, *, repair=False, confirm='', reason=''):
    database.settings.require_local_foundation()
    if repair:
        check_reason(reason)
        if confirm != f'REBUILD-PROJECTIONS:{project_id}':
            raise ValueError('Explicit project-specific rebuild confirmation is required.')
    with database.session() as db:
        workspace=db.scalar(select(Workspace).where(Workspace.id==workspace_id).with_for_update())
        project=db.scalar(select(Project).where(Project.id==project_id,Project.workspace_id==workspace_id))
        if workspace is None or project is None: raise not_found()
        # Use the same lock hierarchy as normal contribution mutations. The
        # tenant lock serializes all protected business writes for this pilot.
        list(db.scalars(select(Milestone).where(Milestone.project_id==project_id)
            .order_by(Milestone.id).with_for_update()))
        list(db.scalars(select(WorkPackage).where(WorkPackage.project_id==project_id)
            .order_by(WorkPackage.id).with_for_update()))
        before=reconcile(db,project)
        if repair:
            reconcile(db,project,repair=True)
            after=reconcile(db,project)
            audit(db,'operator.credit_projections_rebuilt',workspace_id=workspace_id,project_id=project_id,
                reason=reason,details={'differences':before['differences'],'award_count':after['award_count']})
            db.commit()
            return {'before':before,'after':after,'history_unchanged':True}
        return before
