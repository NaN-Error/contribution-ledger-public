"""Initialize and recover authentication factors without silently replacing keys."""
import os
from pathlib import Path
from sqlalchemy import select
from app.auth.models import User
from app.auth.mfa_models import Authenticator
from app.auth.service import revoke_all
from app.auth.operator import check_reason
from app.security.audit import audit
from app.security.tokens import now
from app.security.secrets.encrypted import private_path, secure_read
from app.auth.mfa_crypto import FactorCipher

def initialize_auth_key(database):
    path=Path(database.settings.auth_master_key_file).absolute();private_path(path)
    if path.exists():FactorCipher(str(path)).key();return {"created":False}
    with database.session() as db:
        if db.scalar(select(Authenticator.user_id).where(Authenticator.encrypted_secret.is_not(None)).limit(1)):
            raise ValueError("Existing factors require restoring the original master; initialization cannot replace it.")
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,"O_NOFOLLOW",0),0o600)
    with os.fdopen(fd,"wb") as f:f.write(os.urandom(32));f.flush();os.fsync(f.fileno())
    return {"created":True}

def reset_factor(database,email,reason,confirm):
    check_reason(reason)
    if confirm!="RESET-MFA:"+email:raise ValueError("Account-specific confirmation is required.")
    with database.session() as db:
        user=db.scalar(select(User).where(User.email==email).with_for_update())
        if not user:raise ValueError("Unknown account")
        factor=db.get(Authenticator,user.id)
        if factor is None:
            factor=Authenticator(user_id=user.id,recovery_hashes=[],changed_at=now(),last_counter=-1);db.add(factor)
        factor.enabled=False;factor.must_enroll=True;factor.encrypted_secret=None
        factor.recovery_hashes=[];factor.last_counter=-1;factor.enrollment_expires_at=None;factor.changed_at=now()
        revoke_all(db,user.id)
        audit(db,"operator.mfa_reset",subject_id=user.id,reason=reason,details={"reenrollment_required":True})
        db.commit()
    return {"reset":True,"reenrollment_required":True,"sessions_revoked":True}
