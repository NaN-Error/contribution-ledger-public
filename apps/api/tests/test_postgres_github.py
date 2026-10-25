"""Native phase-8 concurrency and history checks. Skip without a disposable PostgreSQL database."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import UUID
import pytest
from sqlalchemy import select,func,text
from sqlalchemy.exc import DBAPIError
from alembic import command
from tests.test_postgres_accounts import pg_accounts,browser
from tests.test_postgres_planning import race_requests
from tests.phase8_helpers import environment,queue,run,import_body
from app.integrations.github.importer import claim
from app.integrations.github.models import GitHubImport,GitHubSourceVersion
from app.jobs.models import OutboxMessage
from app.db.migration import migration_config
pytestmark=pytest.mark.postgres

def test_native_same_import_is_one_transactional_job_and_outbox(pg_accounts):
    settings,db=pg_accounts;client=browser(settings,db)
    try:
        _,root,_,overview,_,_=environment(client,db,settings)
        body=import_body(overview['repositories'][0]['id']);path=root+'/github/imports'
        assert sorted(race_requests(settings,db,client,[(path,body),(path,body)]))==[201,201]
        with db.session() as session:
            assert session.scalar(select(func.count()).select_from(GitHubImport))==1
            assert session.scalar(select(func.count()).select_from(OutboxMessage))==1
    finally:client.close()

def test_native_competing_runs_cannot_share_active_repository(pg_accounts):
    settings,db=pg_accounts;client=browser(settings,db)
    try:
        _,root,_,overview,_,_=environment(client,db,settings);repo=overview['repositories'][0]['id'];path=root+'/github/imports'
        assert sorted(race_requests(settings,db,client,[(path,import_body(repo)),(path,import_body(repo))]))==[201,409]
    finally:client.close()

def test_native_workers_claim_one_lease(pg_accounts):
    settings,db=pg_accounts;client=browser(settings,db)
    try:
        _,root,_,overview,_,_=environment(client,db,settings);job,_=queue(client,root,overview);barrier=Barrier(2)
        def work():barrier.wait();return claim(db,UUID(job['id']))
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:work(),range(2)))
        assert sum(result is not None for result in results)==1
    finally:client.close()

def test_native_source_history_is_immutable(pg_accounts):
    settings,db=pg_accounts;client=browser(settings,db)
    try:
        _,root,fake,overview,_,_=environment(client,db,settings);job,_=queue(client,root,overview);assert run(db,settings,fake,job['id'])[-1]=='completed'
        for sql in ["UPDATE github_source_versions SET kind='changed'",'DELETE FROM github_source_versions','TRUNCATE github_source_versions CASCADE']:
            with pytest.raises(DBAPIError),db.engine.begin() as connection:connection.execute(text(sql))
    finally:client.close()

def test_native_source_scope_fk_rejects_foreign_project(pg_accounts):
    settings,db=pg_accounts;client=browser(settings,db)
    try:
        _,root,fake,overview,_,_=environment(client,db,settings);job,_=queue(client,root,overview);run(db,settings,fake,job['id'])
        with pytest.raises(DBAPIError),db.engine.begin() as connection:
            connection.execute(text("""INSERT INTO github_source_versions
              (id,workspace_id,project_id,repository_id,kind,remote_key,content_hash,document,size_bytes,captured_at)
              SELECT gen_random_uuid(),workspace_id,gen_random_uuid(),repository_id,kind,remote_key,content_hash,document,size_bytes,captured_at
              FROM github_source_versions LIMIT 1"""))
    finally:client.close()

def test_native_repeated_migration_does_not_change_sources(pg_accounts):
    settings,db=pg_accounts;client=browser(settings,db)
    try:
        _,root,fake,overview,_,_=environment(client,db,settings);job,_=queue(client,root,overview);run(db,settings,fake,job['id'])
        with db.session() as session:before=list(session.execute(select(GitHubSourceVersion.id,GitHubSourceVersion.content_hash).order_by(GitHubSourceVersion.id)))
        with db.engine.begin() as connection:
            config=migration_config();config.attributes['connection']=connection;command.upgrade(config,'head')
        with db.session() as session:after=list(session.execute(select(GitHubSourceVersion.id,GitHubSourceVersion.content_hash).order_by(GitHubSourceVersion.id)))
        assert before==after
    finally:client.close()
