from alembic import command
from sqlalchemy import inspect,text
import pytest
from app.db.migration import migration_config,expected_revision
from tests.phase9_helpers import sync_environment,send
TABLES={'github_webhook_deliveries','github_webhook_targets','github_sync_configs','github_sync_runs','github_source_heads','job_heartbeats'}

def test_phase9_additive_tables_and_repeat(database):
    with database.engine.begin() as connection:
        config=migration_config();config.attributes['connection']=connection
        command.upgrade(config,'head')
        assert TABLES<=set(inspect(connection).get_table_names())
        assert connection.execute(text('SELECT version_num FROM alembic_version')).scalar()==expected_revision()

def test_phase9_empty_downgrade_upgrade(database):
    with database.engine.begin() as connection:
        config=migration_config();config.attributes['connection']=connection
        command.downgrade(config,'0008_github_history')
        assert not TABLES&set(inspect(connection).get_table_names())
        assert 'retry_not_before' not in {c['name'] for c in inspect(connection).get_columns('github_repositories')}
        command.upgrade(config,'head')
        assert TABLES<=set(inspect(connection).get_table_names())

def test_phase9_receipt_history_blocks_downgrade(client,database,settings,tmp_path):
    sync_environment(client,database,settings,tmp_path);assert send(client).status_code==202
    with pytest.raises(RuntimeError,match='refusing destructive downgrade'),database.engine.begin() as connection:
        config=migration_config();config.attributes['connection']=connection;command.downgrade(config,'0008_github_history')
    assert TABLES<=set(inspect(database.engine).get_table_names())
