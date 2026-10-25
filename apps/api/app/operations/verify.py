"""Offline read-only recovery checks; optional explicit session invalidation.

This checks current referenced local objects, contribution projections, frozen
arithmetic and retained encrypted credentials. It never contacts a provider.
"""
import argparse
import json
from sqlalchemy import select,update,text
from app.core.config import get_settings
from app.db.session import Database
from app.db.migration import expected_revision
from app.db import models  # register all models
from app.projects.models import Project,Invitation
from app.auth.models import BrowserSession,RecoveryToken,InstallationState
from app.auth.mfa_models import Authenticator
from app.auth.mfa_crypto import FactorCipher
from app.ledger.service import reconcile
from app.finance.periods.models import DistributionClose,FinanceDocument
from app.finance.close.service import verify_close
from app.evidence.models import EvidenceObject,EvidenceRetirement
from app.storage.local import LocalObjectStorage
from app.storage.contracts import ObjectReference
from app.security.secrets.encrypted import EncryptedCredentialStore
from app.ai.models import AIConnection
from app.ai.connections.service import key_context
from app.security.tokens import now
from app.security.audit import audit


def verify_retained(database):
    settings=database.settings
    if settings.object_storage_backend!='local':raise ValueError("This coordinated restore verifier supports local object storage only")
    store=LocalObjectStorage(settings.object_storage_root)
    keys=EncryptedCredentialStore(settings.ai_credential_root,settings.ai_master_key_file)
    counts={"projects":0,"distribution_closes":0,"artifact_objects":0,"retired_objects":0,"finance_documents":0,"ai_credentials":0,"mfa_seeds":0}
    with database.session() as db:
        revision=db.execute(text('SELECT version_num FROM alembic_version')).scalar_one()
        if revision!=expected_revision():raise ValueError("Migrate the isolated restored database forward before verification")
        for project in db.scalars(select(Project)):
            if not reconcile(db,project)['consistent']:raise ValueError("Contribution projections differ from the preserved ledger")
            counts['projects']+=1
        for close in db.scalars(select(DistributionClose)):
            verify_close(close);counts['distribution_closes']+=1
        for obj in db.scalars(select(EvidenceObject)):
            if db.get(EvidenceRetirement,obj.id):counts['retired_objects']+=1;continue
            if obj.backend!='local':raise ValueError("A referenced object belongs to external storage")
            with store.open(ObjectReference(obj.workspace_id,obj.id,obj.sha256,obj.size_bytes)):pass
            counts['artifact_objects']+=1
        for doc in db.scalars(select(FinanceDocument)):
            if doc.backend!='local':raise ValueError("A financial document belongs to external storage")
            with store.open(ObjectReference(doc.workspace_id,doc.object_id,doc.sha256,doc.size_bytes)):pass
            counts['finance_documents']+=1
        for conn in db.scalars(select(AIConnection).where(AIConnection.enabled.is_(True),AIConnection.credential_ref.is_not(None))):
            keys.read(conn.credential_ref,key_context(conn));counts['ai_credentials']+=1
        for factor in db.scalars(select(Authenticator).where(Authenticator.encrypted_secret.is_not(None))):
            FactorCipher(settings.auth_master_key_file).open(factor.user_id,factor.encrypted_secret);counts['mfa_seeds']+=1
    return {"verified":True,"revision":revision,"counts":counts,"external_requests":0,
        "scope":"Internal consistency and retained bytes, not external receipt truth or deployment readiness"}


def invalidate_recovered_access(database,confirm):
    if confirm!='INVALIDATE-RESTORED-ACCESS':raise ValueError("Explicit recovery confirmation required")
    if database.settings.environment!='test':raise ValueError("Use the isolated test restoration environment")
    with database.session() as db:
        db.execute(update(BrowserSession).where(BrowserSession.revoked_at.is_(None)).values(revoked_at=now()))
        db.execute(update(RecoveryToken).where(RecoveryToken.consumed_at.is_(None)).values(consumed_at=now()))
        db.execute(update(Invitation).where(Invitation.status=='pending').values(status='revoked'))
        state=db.get(InstallationState,1)
        if state:state.bootstrap_token_hash=None;state.bootstrap_expires_at=None
        audit(db,'operator.restored_access_invalidated',reason='Isolated recovery; revoke copied sessions and pending invitations before deliberate cutover')
        db.commit()
    return {"access_invalidated":True,"workers_started":False}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--invalidate-access',action='store_true');p.add_argument('--confirm',default='');a=p.parse_args()
    database=None
    try:
        database=Database(get_settings());result=verify_retained(database)
        if a.invalidate_access:result.update(invalidate_recovered_access(database,a.confirm))
        print(json.dumps(result,sort_keys=True));return 0
    except Exception as exc:
        print(json.dumps({"verified":False,"error_type":type(exc).__name__,"message":"Recovery verification failed. Inspect protected operator records; no secret or source content is printed."}));return 2
    finally:
        if database:database.dispose()
if __name__=='__main__':raise SystemExit(main())
