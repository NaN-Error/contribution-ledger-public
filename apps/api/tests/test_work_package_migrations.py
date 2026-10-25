from alembic import command
from sqlalchemy import inspect, text
import pytest
from app.db.migration import migration_config, expected_revision
from tests.phase4_helpers import environment, create


def test_phase4_upgrade_preserves_phase3_records_and_repeatable_head(client,database):
    owner,root,milestone,allocation=environment(client,database)
    cfg=migration_config()
    with database.engine.begin() as conn:
        cfg.attributes['connection']=conn
        command.downgrade(cfg,'0003_policies_budgets')
        assert not inspect(conn).has_table('work_packages')
        command.upgrade(cfg,'head');command.upgrade(cfg,'head')
        assert inspect(conn).has_table('work_submissions')
    assert client.get(root+'/milestones/'+milestone['id']).json()['allocated_atoms']==allocation['atoms']
    assert create(client,root,owner,milestone,allocation).status_code==201


def test_phase4_nonempty_downgrade_refused_before_history_changes(client,database):
    owner,root,milestone,allocation=environment(client,database)
    item=create(client,root,owner,milestone,allocation).json()
    cfg=migration_config()
    with pytest.raises(RuntimeError,match='Phase-4 records exist'),database.engine.begin() as conn:
        cfg.attributes['connection']=conn;command.downgrade(cfg,'0003_policies_budgets')
    assert client.get(root+f"/work-packages/{item['id']}/revisions/1").status_code==200
    with database.engine.connect() as conn:
        assert conn.execute(text('SELECT version_num FROM alembic_version')).scalar_one()==expected_revision()
