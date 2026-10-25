"""MFA enrollment and authentication. Pre-auth sessions cannot read project data."""
import base64
import hmac
import secrets
from datetime import timedelta
from urllib.parse import quote
from fastapi import APIRouter, Request, Response
from pydantic import Field, SecretStr
from sqlalchemy import select
from app.auth.dependencies import Browser, Db
from app.auth.models import User, BrowserSession
from app.auth.mfa_models import Authenticator
from app.auth.mfa_crypto import FactorCipher,match_counter
from app.auth.schemas import Input
from app.auth.service import create_session,revoke_all,session_response
from app.core.errors import ApiError
from app.security.passwords import verify_password
from app.security.audit import audit
from app.security.tokens import now,token_hash,utc
from app.security.throttling import reserve_attempts
from app.security.secrets.store import SecretUnavailable
router=APIRouter(prefix="/api/v1/auth/mfa",tags=["account security"])

class Password(Input):
    password: SecretStr = Field(min_length=1,max_length=128)
class Code(Input):
    code: SecretStr = Field(min_length=6,max_length=40)
class Disable(Password,Code):pass

def subject(db,identity,*,lock=False):
    uid=identity.user.id if identity.user else identity.session.pending_user_id
    if uid is None:raise ApiError(401,"authentication_required","Verify your password first.")
    query=select(User).where(User.id==uid)
    if lock:query=query.with_for_update().execution_options(populate_existing=True)
    user=db.scalar(query)
    session=db.scalar(select(BrowserSession).where(BrowserSession.id==identity.session.id).execution_options(populate_existing=True))
    if not user or not user.is_active or not session or session.revoked_at or utc(session.expires_at)<=now():
        raise ApiError(401,"authentication_required","Sign in again.")
    return user

def limited(db,request,identity):
    uid=identity.user.id if identity.user else identity.session.pending_user_id
    reserve_attempts(db,[("mfa-user:"+str(uid),10),("mfa-peer:"+(request.client.host if request.client else "unknown"),100)])

def cipher(request):return FactorCipher(request.app.state.settings.auth_master_key_file)
def failed(db,user):
    audit(db,"auth.mfa_failed",actor_id=user.id);db.commit()
    raise ApiError(401,"mfa_rejected","The code is invalid, expired, or already used.")
def factor_code(db,request,user,factor,code):
    if not factor or not factor.enabled:failed(db,user)
    counter=None
    try:counter=match_counter(cipher(request).open(user.id,factor.encrypted_secret),code,now().timestamp(),factor.last_counter)
    except SecretUnavailable:raise ApiError(503,"factor_unavailable","The operator must restore the protected authentication key.") from None
    if counter is not None:factor.last_counter=counter;return
    candidate=token_hash(code.replace("-","").lower(),"mfa-recovery:"+str(user.id))
    hashes=list(factor.recovery_hashes)
    for stored in hashes:
        if hmac.compare_digest(stored,candidate):
            hashes.remove(stored);factor.recovery_hashes=hashes
            audit(db,"auth.mfa_recovery_code_used",actor_id=user.id);return
    failed(db,user)

def finish(db,request,response,identity,user):
    session,raw=create_session(db,user,request.app.state.settings,identity.session,mfa_passed=True)
    db.commit()
    return session_response(db,response,request.app.state.settings,session,raw,user,set_cookie=True)

@router.get("/status")
def status(request:Request,db:Db,identity:Browser):
    user=subject(db,identity);factor=db.get(Authenticator,user.id)
    available=True
    try:cipher(request).key()
    except SecretUnavailable:available=False
    return {"enabled":bool(factor and factor.enabled),"required":request.app.state.settings.require_mfa or bool(factor and factor.must_enroll),
        "key_available":available,"recovery_codes_remaining":len(factor.recovery_hashes) if factor else 0,
        "pending_login":identity.session.pending_user_id is not None}

@router.post("/enroll")
def enroll(body:Password,request:Request,db:Db,identity:Browser):
    limited(db,request,identity);user=subject(db,identity,lock=True)
    if not verify_password(user.password_hash,body.password.get_secret_value()):failed(db,user)
    factor=db.get(Authenticator,user.id)
    if factor and factor.enabled:raise ApiError(409,"factor_exists","Authenticate with the existing factor; do not overwrite it.")
    secret=secrets.token_bytes(20)
    try:sealed=cipher(request).seal(user.id,secret)
    except SecretUnavailable:raise ApiError(503,"factor_unavailable","Initialize or restore the protected authentication key first.") from None
    if factor is None:
        factor=Authenticator(user_id=user.id,enabled=False,must_enroll=False,last_counter=-1,recovery_hashes=[],changed_at=now());db.add(factor)
    factor.encrypted_secret=sealed;factor.enrollment_expires_at=now()+timedelta(minutes=10)
    factor.last_counter=-1;factor.changed_at=now()
    audit(db,"auth.mfa_enrollment_started",actor_id=user.id);db.commit()
    encoded=base64.b32encode(secret).decode().rstrip("=")
    label=quote("Contribution ledger:"+user.email,safe="")
    return {"secret":encoded,"uri":f"otpauth://totp/{label}?secret={encoded}&issuer=Contribution%20ledger&algorithm=SHA1&digits=6&period=30",
        "expires_at":factor.enrollment_expires_at,"warning":"Store this only in your authenticator. It is shown once, not logged."}

@router.post("/confirm")
def confirm(body:Code,request:Request,response:Response,db:Db,identity:Browser):
    limited(db,request,identity);user=subject(db,identity,lock=True);factor=db.get(Authenticator,user.id)
    if not factor or factor.enabled or not factor.enrollment_expires_at or utc(factor.enrollment_expires_at)<=now():
        raise ApiError(409,"enrollment_expired","Begin a new enrollment; no enabled factor was changed.")
    try:counter=match_counter(cipher(request).open(user.id,factor.encrypted_secret),body.code.get_secret_value(),now().timestamp(),-1)
    except SecretUnavailable:raise ApiError(503,"factor_unavailable","Restore the authentication key.") from None
    if counter is None:failed(db,user)
    codes=[secrets.token_hex(16) for _ in range(10)]
    factor.recovery_hashes=[token_hash(c,"mfa-recovery:"+str(user.id)) for c in codes]
    factor.enabled=True;factor.must_enroll=False;factor.last_counter=counter;factor.changed_at=now();factor.enrollment_expires_at=None
    revoke_all(db,user.id);audit(db,"auth.mfa_enabled",actor_id=user.id)
    return {"session":finish(db,request,response,identity,user),"recovery_codes":codes}

@router.post("/verify")
def verify(body:Code,request:Request,response:Response,db:Db,identity:Browser):
    if identity.session.pending_user_id is None:raise ApiError(409,"no_mfa_challenge","There is no pending password-verified login.")
    limited(db,request,identity);user=subject(db,identity,lock=True);factor=db.get(Authenticator,user.id)
    factor_code(db,request,user,factor,body.code.get_secret_value());audit(db,"auth.mfa_verified",actor_id=user.id)
    return finish(db,request,response,identity,user)

@router.post("/disable")
def disable(body:Disable,request:Request,response:Response,db:Db,identity:Browser):
    if identity.user is None:raise ApiError(401,"authentication_required","Finish signing in first.")
    if request.app.state.settings.require_mfa:raise ApiError(403,"mfa_required","This deployment requires MFA; disabling it is not permitted.")
    limited(db,request,identity);user=subject(db,identity,lock=True)
    if not verify_password(user.password_hash,body.password.get_secret_value()):failed(db,user)
    factor=db.get(Authenticator,user.id);factor_code(db,request,user,factor,body.code.get_secret_value())
    factor.enabled=False;factor.must_enroll=False;factor.encrypted_secret=None;factor.recovery_hashes=[];factor.changed_at=now()
    revoke_all(db,user.id);audit(db,"auth.mfa_disabled",actor_id=user.id)
    return finish(db,request,response,identity,user)
