"""Context-bound AES-256-GCM credentials outside the application database.

A separately mounted 32-byte master key is required. Filesystem administrators can
still read process memory and backups; encryption is not hosted-BYOK permission.
"""
import os
import stat
from pathlib import Path
from uuid import UUID, uuid4
from typing import Protocol
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.exceptions import InvalidTag
from app.security.secrets.store import SecretUnavailable

class CredentialStore(Protocol):
    def write(self, value: str, context: str) -> str: ...
    def read(self, reference: str, context: str) -> str: ...
    def delete(self, reference: str) -> None: ...


def private_path(path: Path):
    for part in [path,*path.parents]:
        if part.is_symlink():raise SecretUnavailable()


def secure_read(path: Path, limit: int):
    private_path(path)
    try:
        fd=os.open(path,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0)|getattr(os,'O_BINARY',0))
        with os.fdopen(fd,'rb') as f:
            info=os.fstat(f.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size>limit or (os.name!='nt' and info.st_mode&0o077):
                raise SecretUnavailable()
            data=f.read(limit+1)
        if len(data)>limit:raise SecretUnavailable()
        return data
    except OSError:raise SecretUnavailable() from None


def valid_credential(value):
    if not isinstance(value,str) or not 8<=len(value)<=4096 or any(ord(c)<33 or ord(c)>126 for c in value):
        raise SecretUnavailable()
    return value


class EncryptedCredentialStore:
    def __init__(self,root: str,master_file: str):
        self.root=Path(root).absolute();self.master_file=Path(master_file).absolute()
    def _key(self):
        raw=secure_read(self.master_file,32)
        if len(raw)!=32:raise SecretUnavailable()
        return raw
    def _path(self,reference):
        try:
            if str(UUID(reference))!=reference:raise ValueError()
        except (ValueError,AttributeError,TypeError):raise SecretUnavailable() from None
        private_path(self.root)
        return self.root/(reference+'.enc')
    def write(self,value,context):
        value=valid_credential(value)
        private_path(self.root)
        if not self.root.is_dir():raise SecretUnavailable()
        if os.name!='nt' and self.root.stat().st_mode&0o077:raise SecretUnavailable()
        ref=str(uuid4());path=self._path(ref);nonce=os.urandom(12)
        blob=b'CLAI1'+nonce+AESGCM(self._key()).encrypt(nonce,value.encode('ascii'),('ledger-ai-v1:'+context+':'+ref).encode())
        try:
            fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o600)
            with os.fdopen(fd,'wb') as f:f.write(blob);f.flush();os.fsync(f.fileno())
            return ref
        except OSError:raise SecretUnavailable() from None
    def read(self,reference,context):
        blob=secure_read(self._path(reference),8192)
        if len(blob)<34 or blob[:5]!=b'CLAI1':raise SecretUnavailable()
        try:
            raw=AESGCM(self._key()).decrypt(blob[5:17],blob[17:],('ledger-ai-v1:'+context+':'+reference).encode())
            return valid_credential(raw.decode('ascii'))
        except (InvalidTag,ValueError,UnicodeError):raise SecretUnavailable() from None
    def delete(self,reference):
        try:self._path(reference).unlink(missing_ok=True)
        except OSError:raise SecretUnavailable() from None


def initialize(master_file: str,root: str):
    """Explicit operator operation. Never overwrite a master key or rotate silently."""
    key=Path(master_file).absolute();folder=Path(root).absolute()
    private_path(key);private_path(folder)
    key.parent.mkdir(parents=True,exist_ok=True,mode=0o700);folder.mkdir(parents=True,exist_ok=True,mode=0o700)
    if os.name!='nt':os.chmod(folder,0o700)
    if not key.exists():
        # Refuse a new key over existing ciphertext: this is recovery, not setup.
        if any(folder.iterdir()):raise SecretUnavailable()
        fd=os.open(key,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o600)
        with os.fdopen(fd,'wb') as f:f.write(os.urandom(32));f.flush();os.fsync(f.fileno())
    EncryptedCredentialStore(str(folder),str(key))._key()


class CredentialWrites:
    """Request-local write tracking for failures before the database commit attempt.

    A process death or ambiguous DB commit may leave encrypted orphan files. Never
    delete them automatically after a commit attempt: the record could be durable.
    """
    def __init__(self,store):self.store=store;self.references=[]
    def write(self,value,context):
        ref=self.store.write(value,context);self.references.append(ref);return ref
    def read(self,reference,context):return self.store.read(reference,context)
    def delete(self,reference):return self.store.delete(reference)
    def discard(self):
        complete=True
        for ref in self.references:
            try:self.store.delete(ref)
            except SecretUnavailable:complete=False
        self.references=[]
        return complete
