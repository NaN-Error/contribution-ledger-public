from uuid import UUID,uuid4
import pytest
from sqlalchemy import select
from app.ledger.operator import inspect_credit
from app.ledger.models import ContributionBalance,ContributionEvent
from app.projects.models import AuditEvent
from app.core.errors import ApiError
from tests.phase6_helpers import environment,award


def test_operator_requires_exact_confirmation_and_preserves_events(client,database,settings):
    e=environment(client,database,settings);award(e)
    wid=UUID(e['owner']['workspace']['id']);pid=UUID(e['owner']['project']['id'])
    with pytest.raises(ValueError):inspect_credit(database,wid,pid,repair=True,confirm='yes',reason='A synthetic projection repair test.')
    with database.session() as db:
        before=list(db.scalars(select(ContributionEvent.id)));db.scalar(select(ContributionBalance)).atoms=19;db.commit()
    result=inspect_credit(database,wid,pid,repair=True,confirm=f'REBUILD-PROJECTIONS:{pid}',reason='Rebuild corrupted synthetic cache from preserved events.')
    assert not result['before']['consistent'] and result['after']['consistent'] and result['history_unchanged']
    with database.session() as db:
        assert list(db.scalars(select(ContributionEvent.id)))==before
        assert db.scalar(select(AuditEvent).where(AuditEvent.action=='operator.credit_projections_rebuilt'))


def test_operator_cannot_cross_workspace_reference(client,database,settings):
    e=environment(client,database,settings)
    with pytest.raises(ApiError):inspect_credit(database,uuid4(),UUID(e['owner']['project']['id']))
