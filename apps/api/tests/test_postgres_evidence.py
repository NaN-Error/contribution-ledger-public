"""Native PostgreSQL locking/upgrade checks. Skipped without an explicit disposable DB."""
from uuid import UUID
import pytest
from sqlalchemy import select,func,text
from sqlalchemy.exc import DBAPIError
from alembic import command as migrations
from app.db.migration import migration_config
from app.evidence.models import EvidenceRevision,EvidenceItem,EvidenceSnapshot,EvidenceObject
from tests.test_postgres_accounts import pg_accounts
from tests.test_postgres_work_packages import native_package
from tests.test_postgres_planning import race_requests
from tests.phase5_helpers import command,add

pytestmark=pytest.mark.postgres


def test_native_two_uploads_cannot_use_same_package_revision(pg_accounts):
    settings,db=pg_accounts;client,_,root,_,_,package=native_package(settings,db)
    try:
        path=root+f"/work-packages/{package['id']}/evidence"
        requests=[(path,command(package,'file')),(path,command(package,'file'))]
        assert sorted(race_requests(settings,db,client,requests))==[201,409]
        with db.session() as session:
            assert session.scalar(select(func.count()).select_from(EvidenceRevision))==1
            assert session.scalar(select(func.count()).select_from(EvidenceObject))==1
    finally:client.close()


def test_native_replayed_upload_creates_one_revision_and_blob(pg_accounts):
    settings,db=pg_accounts;client,_,root,_,_,package=native_package(settings,db)
    try:
        request=(root+f"/work-packages/{package['id']}/evidence",command(package,'file'))
        assert sorted(race_requests(settings,db,client,[request,request]))==[201,201]
        with db.session() as session:
            assert session.scalar(select(func.count()).select_from(EvidenceItem))==1
            assert session.scalar(select(func.count()).select_from(EvidenceSnapshot))==1
    finally:client.close()


def test_native_snapshot_capture_is_content_addressed_under_race(pg_accounts):
    settings,db=pg_accounts;client,_,root,_,_,package=native_package(settings,db)
    try:
        path=root+f"/work-packages/{package['id']}"
        request=(path+'/evidence/snapshots',{'expected_package_version':package['version'],
            'reviewed_hash':package['review_hash'],'reviewed':True,'reason':'Capture the same synthetic packet under concurrent requests'})
        assert sorted(race_requests(settings,db,client,[request,request]))==[201,201]
        with db.session() as session:assert session.scalar(select(func.count()).select_from(EvidenceSnapshot))==1
    finally:client.close()


def test_native_retire_race_does_not_rewrite_history(pg_accounts):
    settings,db=pg_accounts;client,_,root,_,_,package=native_package(settings,db)
    try:
        path=root+f"/work-packages/{package['id']}";record=add(client,path,'file').json()
        request=(path+f"/evidence/{record['evidence_id']}/revisions/1/retire",{'expected_package_version':2,
            'reviewed':True,'reason':'Retire one synthetic artifact without duplicate state transitions'})
        assert sorted(race_requests(settings,db,client,[request,request]))==[200,409]
        assert client.get(path+f"/evidence/{record['evidence_id']}/revisions/1/download").status_code==410
        assert client.get(path).json()['issued_atoms']==0
    finally:client.close()


def test_native_evidence_migration_history_guards(pg_accounts):
    settings,db=pg_accounts;client,_,root,_,_,package=native_package(settings,db)
    try:
        cfg=migration_config()
        with db.engine.begin() as conn:
            cfg.attributes['connection']=conn;migrations.downgrade(cfg,'0004_work_packages');migrations.upgrade(cfg,'head')
        path=root+f"/work-packages/{package['id']}";assert add(client,path,'file').status_code==201
        for sql in ['DELETE FROM evidence_items','DELETE FROM evidence_objects','DELETE FROM evidence_revisions',
                    'DELETE FROM evidence_snapshots',"UPDATE evidence_revisions SET reason='rewritten'"]:
            with pytest.raises(DBAPIError),db.engine.begin() as conn:conn.execute(text(sql))
        with pytest.raises(RuntimeError,match='Phase-5 records exist'),db.engine.begin() as conn:
            cfg.attributes['connection']=conn;migrations.downgrade(cfg,'0004_work_packages')
        assert client.get(path+'/evidence').json()['total_entries']==1
    finally:client.close()
