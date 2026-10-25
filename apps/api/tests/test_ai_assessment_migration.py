from uuid import UUID
from pathlib import Path
import io
import pytest
from sqlalchemy import text,inspect,select
from sqlalchemy.exc import IntegrityError,DatabaseError
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from app.db.migration import migration_config
from app.db.base import Base
from app.ai.assessments.models import AIReviewPacket
from tests.phase11_helpers import setup,packet,plan,complete


def test_current_metadata_matches_migrations(database):
    with database.engine.connect() as conn:
        assert compare_metadata(MigrationContext.configure(conn),Base.metadata)==[]


def test_populated_phase10_jobs_survive_upgrade_and_empty_p11_downgrade(client,database,settings):
    env=setup(client,database,settings)
    with database.engine.connect() as conn:
        before=conn.execute(text('SELECT id,kind,status,specification,result FROM ai_jobs ORDER BY id')).all()
        events=conn.scalar(text('SELECT count(*) FROM ai_operation_events'))
    cfg=migration_config()
    with database.engine.begin() as conn:
        cfg.attributes['connection']=conn;command.downgrade(cfg,'0010_ai_provider_foundation')
        assert 'ai_review_packets' not in inspect(conn).get_table_names()
        assert not conn.execute(text('PRAGMA foreign_key_check')).first()
    with database.engine.begin() as conn:
        cfg.attributes['connection']=conn;command.upgrade(cfg,'head');command.upgrade(cfg,'head')
        assert conn.execute(text('SELECT id,kind,status,specification,result FROM ai_jobs ORDER BY id')).all()==before
        assert conn.scalar(text('SELECT count(*) FROM ai_operation_events'))==events
        assert not conn.execute(text('PRAGMA foreign_key_check')).first()
    assert complete(env,plan(env,packet(env)))['status']=='valid'


def test_assessment_history_mutations_and_nonempty_downgrade_are_refused(client,database,settings):
    env=setup(client,database,settings);p=packet(env);complete(env,plan(env,p))
    for table in ('ai_review_packets','ai_review_plans','ai_review_grants','ai_review_results'):
        with pytest.raises(DatabaseError):
            with database.engine.begin() as conn:conn.execute(text(f'UPDATE {table} SET created_at=created_at'))
        with pytest.raises(DatabaseError):
            with database.engine.begin() as conn:conn.execute(text(f'DELETE FROM {table}'))
    cfg=migration_config()
    with pytest.raises(RuntimeError,match='history exists'):
        with database.engine.begin() as conn:
            cfg.attributes['connection']=conn;command.downgrade(cfg,'0010_ai_provider_foundation')
    assert env['client'].get(env['assessments']+'/packets/'+p['id']).status_code==200


def test_ai_job_plan_link_is_immutable_and_required(client,database,settings):
    from tests.phase11_helpers import grant,enqueue
    env=setup(client,database,settings);x=plan(env,packet(env));assert grant(env,x).status_code==201;j,_=enqueue(env,x)
    with pytest.raises(DatabaseError):
        with database.engine.begin() as conn:conn.execute(text('UPDATE ai_jobs SET assessment_plan_id=NULL WHERE id=:id'),{'id':UUID(j['id']).hex})


def test_offline_postgres_migration_contains_narrow_function_and_no_credit_update(monkeypatch):
    monkeypatch.setenv('CL_DB_PASSWORD','synthetic-offline-test')
    from app.core.config import get_settings
    get_settings.cache_clear();output=io.StringIO();cfg=migration_config();cfg.output_buffer=output
    command.upgrade(cfg,'0010_ai_provider_foundation:head',sql=True)
    ddl=output.getvalue()
    assert 'cl_ai_packet_current' in ddl and 'SECURITY DEFINER SET search_path = pg_catalog' in ddl
    assert 'REVOKE ALL ON FUNCTION cl_ai_packet_current(uuid) FROM PUBLIC' in ddl
    assert 'UPDATE credit_awards' not in ddl and 'UPDATE contribution_balances' not in ddl
    assert 'ALTER TABLE ai_jobs' in ddl
    get_settings.cache_clear()
