import io
from alembic import command
from sqlalchemy import text,inspect,select,func
from sqlalchemy.exc import DBAPIError
import pytest
from app.db.migration import migration_config,expected_revision
from app.integrations.github.models import GitHubSourceVersion
from tests.phase8_helpers import environment,queue,run

TABLES={'github_auth_flows','github_connections','github_repositories','github_imports','github_fetch_tasks','github_source_versions','github_observations','github_identities','github_identity_decisions','github_evidence_links','job_outbox'}

def test_additive_tables_and_repeated_migration(database):
    with database.engine.begin() as connection:
        assert TABLES <= set(inspect(connection).get_table_names())
        config=migration_config();config.attributes['connection']=connection;command.upgrade(config,'head')
        assert connection.execute(text('SELECT version_num FROM alembic_version')).scalar()==expected_revision()

def test_empty_phase8_can_downgrade_and_upgrade(database):
    with database.engine.begin() as connection:
        config=migration_config();config.attributes['connection']=connection
        command.downgrade(config,'0007_hypothetical_simulator')
        assert not TABLES.intersection(inspect(connection).get_table_names())
        command.upgrade(config,'head')
        assert TABLES <= set(inspect(connection).get_table_names())

def test_nonempty_history_cannot_be_downgraded(client,database,settings):
    environment(client,database,settings)
    with pytest.raises(RuntimeError,match='refusing destructive downgrade'),database.engine.begin() as connection:
        config=migration_config();config.attributes['connection']=connection;command.downgrade(config,'0007_hypothetical_simulator')
    assert TABLES <= set(inspect(database.engine).get_table_names())

@pytest.mark.parametrize('statement',["UPDATE github_source_versions SET kind='changed'",'DELETE FROM github_source_versions','DELETE FROM github_observations'])
def test_source_history_rejects_ordinary_mutation(client,database,settings,statement):
    _,root,fake,overview,_,_=environment(client,database,settings);job,_=queue(client,root,overview);run(database,settings,fake,job['id'])
    with pytest.raises(DBAPIError),database.engine.begin() as connection:connection.execute(text(statement))
    with database.session() as db:assert db.scalar(select(func.count()).select_from(GitHubSourceVersion))>0

def test_postgres_offline_sql_contains_history_guards(settings,monkeypatch):
    monkeypatch.setattr('app.core.config.get_settings',lambda:settings)
    output=io.StringIO();config=migration_config();config.set_main_option('sqlalchemy.url','postgresql://fixture:fixture@127.0.0.1/fixture_test');config.output_buffer=output
    command.upgrade(config,'head',sql=True)
    sql=output.getvalue();assert 'CREATE TABLE github_source_versions' in sql and 'reject_github_history_mutation' in sql
    assert 'BEFORE TRUNCATE ON github_source_versions' in sql
