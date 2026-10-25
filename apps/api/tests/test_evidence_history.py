from copy import deepcopy
from uuid import UUID,uuid4
from alembic import command
from sqlalchemy import select,text,inspect
from sqlalchemy.exc import DBAPIError
import pytest
from app.db.migration import migration_config
from app.evidence.models import EvidenceRevision,EvidenceSnapshot,EvidenceObject
from app.contributions.work_packages.models import WorkSubmission
from app.contributions.budgets.models import BudgetAllocation,Milestone
from app.storage.contracts import StorageUnavailable
from tests.auth_helpers import mutation
from tests.phase5_helpers import evidence_environment,add,revise,metadata


def test_evidence_history_triggers_and_nonempty_downgrade(client,database):
    _,_,path,_=evidence_environment(client,database)
    record=add(client,path,'file').json()
    mutation(client,path+f"/evidence/{record['evidence_id']}/revisions/1/retire",{
        'expected_package_version':2,'reviewed':True,'reason':'Retire this synthetic artifact with preserved history'})
    for table in ['evidence_items','evidence_objects','evidence_revisions','evidence_snapshots','evidence_retirements']:
        with pytest.raises(DBAPIError),database.engine.begin() as conn:conn.execute(text(f'DELETE FROM {table}'))
    for table,column in [('evidence_objects','sha256'),('evidence_revisions','reason'),('evidence_snapshots','reason'),('evidence_retirements','reason')]:
        with pytest.raises(DBAPIError),database.engine.begin() as conn:conn.execute(text(f"UPDATE {table} SET {column}='changed'"))
    with pytest.raises(DBAPIError),database.engine.begin() as conn:conn.execute(text("UPDATE evidence_items SET kind='statement'"))
    cfg=migration_config()
    with pytest.raises(RuntimeError,match='Phase-5 records exist'),database.engine.begin() as conn:
        cfg.attributes['connection']=conn;command.downgrade(cfg,'0004_work_packages')
    assert client.get(path+'/evidence').status_code==200


def test_phase4_legacy_submission_preserved_through_upgrade(client,database):
    owner,_,path,package=evidence_environment(client,database)
    cfg=migration_config()
    with database.engine.begin() as conn:
        cfg.attributes['connection']=conn;command.downgrade(cfg,'0004_work_packages')
        assert not inspect(conn).has_table('evidence_snapshots')
    legacy={'evidence_status':'not_implemented_phase_4','scope':deepcopy(package['revision']['document']),
            'notice':'This pre-evidence readiness declaration is not proof of acceptance.'}
    with database.session() as db:
        row=WorkSubmission(id=uuid4(),workspace_id=UUID(owner['workspace']['id']),project_id=UUID(owner['project']['id']),
            package_id=UUID(package['id']),scope_revision=1,package_version=1,snapshot=legacy,
            snapshot_hash='a'*64,submitted_by=UUID(owner['user']['id']))
        db.add(row);db.commit();sid=row.id
    with database.engine.begin() as conn:
        cfg.attributes['connection']=conn;command.upgrade(cfg,'head');command.upgrade(cfg,'head')
    with database.session() as db: assert db.get(WorkSubmission,sid).snapshot==legacy
    assert client.get(path+'/evidence').json()['review_state']=='legacy_without_evidence'


def test_retirement_failure_still_blocks_bytes_and_uses_current_envelope(client,database,monkeypatch):
    _,_,path,package=evidence_environment(client,database);record=add(client,path,'file').json()
    snap=client.get(path+'/evidence').json()['current_snapshot_id'];old=client.get(path+'/evidence/snapshots/'+snap).json()
    store=client.app.state.object_storage
    def fail(*args):raise StorageUnavailable('fixed safe error')
    monkeypatch.setattr(store,'delete',fail)
    response=mutation(client,path+f"/evidence/{record['evidence_id']}/revisions/1/retire",{
        'expected_package_version':2,'reviewed':True,'reason':'Retire synthetic artifact even during physical deletion failure'})
    assert response.status_code==200 and response.json()['deletion_pending_objects']==1
    assert client.get(path+f"/evidence/{record['evidence_id']}/revisions/1/download").status_code==410
    now=client.get(path+'/evidence/snapshots/'+snap).json()
    assert now['document']==old['document'] and now['content_hash']==old['content_hash']
    assert now['stale'] and now['current_artifact_states'][record['evidence_id']]=='retired'


def test_retirement_does_not_change_future_earned_projection(client,database):
    _,_,path,package=evidence_environment(client,database);record=add(client,path,'file').json()
    with database.session() as db:
        allocation=db.get(BudgetAllocation,UUID(package['allocation_id']))
        milestone=db.get(Milestone,allocation.milestone_id)
        allocation.issued_atoms=100;milestone.issued_atoms=100;db.commit()
    assert add(client,path).status_code==409
    response=mutation(client,path+f"/evidence/{record['evidence_id']}/revisions/1/retire",{
        'expected_package_version':2,'reviewed':True,'reason':'Retain accounting while retiring raw artifact bytes'})
    assert response.status_code==200,response.text
    assert client.get(path).json()['issued_atoms']==100


def test_replacement_metadata_is_scoped_and_old_object_cannot_be_injected(client,database):
    owner,_,path,package=evidence_environment(client,database);record=add(client,path,'file').json()
    result=revise(client,path,record,original_object_id=str(uuid4()))
    assert result.status_code==422
    with database.session() as db:
        row=EvidenceObject(id=uuid4(),workspace_id=UUID(owner['workspace']['id']),project_id=uuid4(),
            package_id=UUID(package['id']),backend='local',sha256='a'*64,size_bytes=10,created_by=UUID(owner['user']['id']))
        with pytest.raises(DBAPIError):db.add(row);db.commit()
