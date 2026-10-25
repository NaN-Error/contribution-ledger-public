import base64
import io
import json
import os
from pathlib import Path
import shutil
import sqlite3
from uuid import UUID,uuid4
import pytest
from sqlalchemy import create_engine,text
from app.auth.mfa_crypto import FactorCipher
from app.auth.mfa_models import Authenticator
from app.db.session import Database
from app.operations.archive import create_bundle,unpack_bundle,validate_pair
from app.operations.verify import verify_retained,invalidate_recovered_access
from app.operations.security import initialize_auth_key
from app.security.tokens import now
from app.ai.models import AIConnection
from app.ai.connections.service import key_context
from app.security.secrets.encrypted import EncryptedCredentialStore,initialize
from tests.phase13_helpers import finance_environment,complete


def test_isolated_sqlite_restore_replays_real_application_close_and_secrets(client,database,settings,tmp_path,monkeypatch):
    e=finance_environment(client,database,settings,monkeypatch);p,doc,entry,closed=complete(e,cents=100003)
    settings.auth_master_key_file=str(tmp_path/'auth-master/master.key');initialize_auth_key(database)
    settings.ai_master_key_file=str(tmp_path/'ai-master/master.key');settings.ai_credential_root=str(tmp_path/'ai-credentials')
    initialize(settings.ai_master_key_file,settings.ai_credential_root)
    store=EncryptedCredentialStore(settings.ai_credential_root,settings.ai_master_key_file)
    uid=UUID(e['owner']['user']['id'])
    with database.session() as db:
        db.add(Authenticator(user_id=uid,encrypted_secret=FactorCipher(settings.auth_master_key_file).seal(uid,b'fictional-seed-bytes'),
            enabled=True,must_enroll=False,last_counter=-1,recovery_hashes=[],changed_at=now()))
        conn=AIConnection(id=uuid4(),workspace_id=UUID(e['owner']['workspace']['id']),project_id=UUID(e['owner']['project']['id']),owner_id=uid,
            request_id=uuid4(),provider='openai',label='Synthetic retained credential',permission_reference='Offline fixture only',next_refresh_at=now())
        conn.credential_ref=store.write('synthetic-api-key-never-sent',key_context(conn));db.add(conn);db.commit()
    before=verify_retained(database);assert before['counts']['distribution_closes']==1
    assert before['counts']['ai_credentials']==before['counts']['mfa_seeds']==1
    snapshot=tmp_path/'database.sqlite'
    raw=database.engine.raw_connection()
    try:
        with sqlite3.connect(snapshot) as target:raw.driver_connection.backup(target)
    finally:raw.close()
    data={'database.sqlite':snapshot}
    for path in Path(settings.object_storage_root).rglob('*'):
        if path.is_file():data['objects/'+path.relative_to(settings.object_storage_root).as_posix()]=path
    for path in Path(settings.ai_credential_root).glob('*.enc'):data['ai-credentials/'+path.name]=path
    recovery={'auth-master/master.key':Path(settings.auth_master_key_file),'ai-master/master.key':Path(settings.ai_master_key_file)}
    key=os.urandom(32);capture=str(uuid4());meta={'native_postgresql':False,'synthetic_only':True}
    create_bundle(data,tmp_path/'data.clb',key,capture_id=capture,kind='data',metadata=meta,scratch=tmp_path/'scratch')
    create_bundle(recovery,tmp_path/'recovery.clb',key,capture_id=capture,kind='recovery',metadata=meta,scratch=tmp_path/'scratch')
    a=unpack_bundle(tmp_path/'data.clb',tmp_path/'restored-data',key,scratch=tmp_path/'scratch')
    b=unpack_bundle(tmp_path/'recovery.clb',tmp_path/'restored-keys',key,scratch=tmp_path/'scratch');validate_pair(a,b)
    restored_settings=settings.model_copy(update={'environment':'test','object_storage_root':str(tmp_path/'restored-data/objects'),
        'ai_credential_root':str(tmp_path/'restored-data/ai-credentials'),'auth_master_key_file':str(tmp_path/'restored-keys/auth-master/master.key'),
        'ai_master_key_file':str(tmp_path/'restored-keys/ai-master/master.key')})
    engine=create_engine('sqlite:///'+str(tmp_path/'restored-data/database.sqlite'));restored=Database(restored_settings,engine)
    try:
        after=verify_retained(restored);assert after==before
        invalidate_recovered_access(restored,'INVALIDATE-RESTORED-ACCESS')
        with engine.connect() as c:assert c.execute(text('SELECT count(*) FROM browser_sessions WHERE revoked_at IS NULL')).scalar_one()==0
        assert verify_retained(restored)==before
        Path(restored_settings.ai_master_key_file).write_bytes(os.urandom(32))
        with pytest.raises(Exception):verify_retained(restored)
    finally:restored.dispose()


def test_missing_required_financial_blob_fails_recovery(client,database,settings,monkeypatch):
    e=finance_environment(client,database,settings,monkeypatch);p,doc,entry,closed=complete(e)
    assert verify_retained(database)['counts']['finance_documents']==1
    # Remove the exact document, not a retired evidence artifact.
    from app.finance.periods.models import FinanceDocument
    with database.session() as db:
        row=db.get(FinanceDocument,UUID(doc['id']));path=Path(settings.object_storage_root)/str(row.workspace_id)/str(row.object_id)
    path.unlink()
    with pytest.raises(Exception):verify_retained(database)
