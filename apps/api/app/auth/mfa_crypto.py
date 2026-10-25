"""RFC 6238 TOTP, with explicit replay state maintained by the service.

SHA-1/6 digits/30 seconds supports ordinary authenticator apps. TOTP is not
phishing resistant. AES-GCM protects seeds at rest under a separate operator key.
"""
import base64
import hashlib
import hmac
import os
import re
import struct
from uuid import UUID
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from app.security.secrets.encrypted import secure_read
from app.security.secrets.store import SecretUnavailable


def totp(secret: bytes, counter: int, digits: int = 6, digest=hashlib.sha1) -> str:
    if counter < 0 or digits not in (6,8):
        raise ValueError("Invalid OTP counter or digits")
    value=hmac.new(secret,struct.pack(">Q",counter),digest).digest()
    offset=value[-1]&15
    integer=int.from_bytes(value[offset:offset+4],"big")&0x7fffffff
    return str(integer % (10**digits)).zfill(digits)


def match_counter(secret: bytes, code: str, timestamp: float, last: int) -> int | None:
    if not re.fullmatch(r"[0-9]{6}",code):return None
    current=int(timestamp)//30
    for counter in (current,current-1,current+1):
        if counter>last and counter>=0 and hmac.compare_digest(totp(secret,counter),code):
            return counter
    return None


class FactorCipher:
    def __init__(self,path: str):self.path=path
    def key(self):
        from pathlib import Path
        raw=secure_read(Path(self.path).absolute(),32)
        if len(raw)!=32:raise SecretUnavailable()
        return raw
    def seal(self,user_id: UUID,secret: bytes):
        nonce=os.urandom(12)
        blob=nonce+AESGCM(self.key()).encrypt(nonce,secret,("ledger-mfa-v1:"+str(user_id)).encode())
        return base64.b64encode(blob).decode("ascii")
    def open(self,user_id: UUID,value: str):
        try:
            blob=base64.b64decode(value,validate=True)
            return AESGCM(self.key()).decrypt(blob[:12],blob[12:],("ledger-mfa-v1:"+str(user_id)).encode())
        except Exception:
            raise SecretUnavailable() from None
