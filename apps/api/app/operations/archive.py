"""Versioned, bounded operator recovery bundles. Never an HTTP upload format.

ZIP_STORED plaintext is prepared only in the caller's private scratch directory.
It is wrapped in authenticated AES-256-GCM frames under an external recovery key.
The terminal empty frame detects truncation, reorder and append. File sizes and
hashes are then checked before files are copied into a new private directory.
This is application-specific encryption, not an independently audited standard.
"""
from __future__ import annotations
import hashlib
import json
import os
import re
import shutil
import stat
import struct
import tempfile
import zipfile
from pathlib import Path,PurePosixPath
from typing import BinaryIO
from uuid import UUID
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes
from app.security.secrets.encrypted import private_path,secure_read

MAGIC=b"CLB14\x00\x01"
CHUNK=1024*1024
MAX_TOTAL=20*1024**3
MAX_FILES=100000
MAX_MANIFEST=16*1024**2

class BundleError(ValueError):pass

def safe_name(value: str) -> str:
    if not isinstance(value,str) or not value or len(value)>512 or "\\" in value or ":" in value:
        raise BundleError("Unsafe bundle path")
    path=PurePosixPath(value)
    if path.is_absolute() or any(x in {"",".",".."} for x in value.split("/")):
        raise BundleError("Unsafe bundle path")
    if any(ord(x)<32 or ord(x)==127 for x in value):raise BundleError("Unsafe bundle path")
    return value

def keygen(path: Path):
    path=path.absolute();private_path(path);path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,"O_NOFOLLOW",0),0o600)
    with os.fdopen(fd,"wb") as f:f.write(os.urandom(32));f.flush();os.fsync(f.fileno())

def read_key(path: Path):
    value=secure_read(path.absolute(),32)
    if len(value)!=32:raise BundleError("A separate 32-byte recovery key is required")
    return value

def _cipher(key: bytes,salt: bytes):
    if len(key)!=32:raise BundleError("Invalid recovery key")
    return AESGCM(HKDF(algorithm=hashes.SHA256(),length=32,salt=salt,info=MAGIC).derive(key))

def _exact(source: BinaryIO,n: int) -> bytes:
    raw=source.read(n)
    if len(raw)!=n:raise BundleError("Truncated recovery bundle")
    return raw

def encrypt(source: BinaryIO,target: BinaryIO,key: bytes):
    salt=os.urandom(16);prefix=os.urandom(8);header=MAGIC+salt+prefix
    target.write(header);cipher=_cipher(key,salt);count=0;total=0
    while True:
        chunk=source.read(CHUNK);total+=len(chunk)
        if total>MAX_TOTAL or count>=2**32:raise BundleError("Bundle exceeds the recovery limit")
        index=struct.pack(">I",count);frame=cipher.encrypt(prefix+index,chunk,header+index)
        target.write(struct.pack(">I",len(frame)));target.write(frame);count+=1
        if not chunk:break

def decrypt(source: BinaryIO,target: BinaryIO,key: bytes):
    try:
        header=_exact(source,len(MAGIC)+24)
        if not header.startswith(MAGIC):raise BundleError("Unsupported recovery bundle")
        salt=header[len(MAGIC):len(MAGIC)+16];prefix=header[-8:];cipher=_cipher(key,salt)
        count=0;total=0
        while True:
            size=struct.unpack(">I",_exact(source,4))[0]
            if size<16 or size>CHUNK+16 or count>=2**32:raise BundleError("Invalid recovery frame")
            index=struct.pack(">I",count)
            raw=cipher.decrypt(prefix+index,_exact(source,size),header+index);count+=1
            if not raw:
                if source.read(1):raise BundleError("Trailing recovery data")
                return
            total+=len(raw)
            if total>MAX_TOTAL:raise BundleError("Bundle exceeds the recovery limit")
            target.write(raw)
    except BundleError:raise
    except Exception:raise BundleError("Recovery authentication failed") from None

def _regular(path: Path):
    private_path(path)
    info=path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1:raise BundleError("Only private regular files can be archived")
    return info

def _hash(path):
    digest=hashlib.sha256()
    with path.open("rb") as source:
        for raw in iter(lambda:source.read(CHUNK),b""):digest.update(raw)
    return digest.hexdigest()

def create_bundle(files: dict[str,Path],output: Path,key: bytes,*,capture_id: str,kind: str,metadata:dict,scratch:Path) -> dict:
    if str(UUID(capture_id))!=capture_id or kind not in {"data","recovery"}:raise BundleError("Invalid bundle identity")
    if not files or len(files)>MAX_FILES:raise BundleError("Invalid bundle inventory")
    private_path(scratch);scratch.mkdir(parents=True,exist_ok=True,mode=0o700)
    manifest={"format":"ledger-recovery-v1","capture_id":capture_id,"kind":kind,"metadata":metadata,"files":{}}
    size=0
    for name,path in sorted(files.items()):
        safe_name(name)
        if name=="manifest.json":raise BundleError("Reserved bundle name")
        info=_regular(path);size+=info.st_size
        if size>MAX_TOTAL-64*1024**2:raise BundleError("Bundle exceeds the recovery limit")
        manifest["files"][name]={"size":info.st_size,"sha256":_hash(path)}
    encoded=json.dumps(manifest,sort_keys=True,separators=(",",":"),allow_nan=False).encode()
    if len(encoded)>MAX_MANIFEST:raise BundleError("Inventory exceeds recovery limit")
    with tempfile.TemporaryDirectory(prefix="ledger-seal-",dir=scratch) as temporary:
        plain=Path(temporary)/"bundle.zip"
        with zipfile.ZipFile(plain,"w",compression=zipfile.ZIP_STORED,allowZip64=True) as z:
            z.writestr("manifest.json",encoded)
            for name,path in sorted(files.items()):z.write(path,name)
        plain.chmod(0o600)
        output=output.absolute();private_path(output);output.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        created=False
        try:
            fd=os.open(output,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,"O_NOFOLLOW",0),0o600);created=True
            with os.fdopen(fd,"wb") as dst,plain.open("rb") as src:
                encrypt(src,dst,key);dst.flush();os.fsync(dst.fileno())
        except Exception:
            if created:output.unlink(missing_ok=True)
            raise
    return manifest

def unpack_bundle(source: Path,destination: Path,key:bytes,*,scratch:Path) -> dict:
    _regular(source);private_path(destination.absolute());private_path(scratch.absolute())
    if destination.exists():raise BundleError("Recovery extraction requires a new destination")
    scratch.mkdir(parents=True,exist_ok=True,mode=0o700)
    created=False
    with tempfile.TemporaryDirectory(prefix="ledger-unseal-",dir=scratch) as temporary:
        plain=Path(temporary)/"bundle.zip"
        with source.open("rb") as src,plain.open("xb") as dst:decrypt(src,dst,key)
        plain.chmod(0o600)
        with zipfile.ZipFile(plain) as z:
            entries=z.infolist()
            if len(entries)>MAX_FILES+1 or len({e.filename for e in entries})!=len(entries):raise BundleError("Duplicate or excessive inventory")
            for e in entries:
                safe_name(e.filename)
                if e.is_dir() or e.compress_type!=zipfile.ZIP_STORED or stat.S_ISLNK(e.external_attr>>16):raise BundleError("Unsupported archive member")
            names={e.filename for e in entries}
            if "manifest.json" not in names or z.getinfo("manifest.json").file_size>MAX_MANIFEST:raise BundleError("Missing inventory")
            def unique(pairs):
                obj={}
                for k,v in pairs:
                    if k in obj:raise BundleError("Duplicate inventory field")
                    obj[k]=v
                return obj
            manifest=json.loads(z.read("manifest.json"),object_pairs_hook=unique)
            if manifest.get("format")!="ledger-recovery-v1" or manifest.get("kind") not in {"data","recovery"}:raise BundleError("Unsupported inventory")
            if str(UUID(manifest["capture_id"]))!=manifest["capture_id"]:raise BundleError("Invalid capture")
            expected=manifest["files"]
            if names!=set(expected)|{"manifest.json"}:raise BundleError("Inventory differs from archived files")
            total=0
            for name,row in expected.items():
                safe_name(name);e=z.getinfo(name)
                if type(row.get("size")) is not int or row["size"]<0 or e.file_size!=row["size"] or not re.fullmatch(r"[a-f0-9]{64}",row.get("sha256","")):
                    raise BundleError("Invalid file inventory")
                total+=e.file_size
            if total>MAX_TOTAL:raise BundleError("Recovery exceeds limit")
            try:
                destination.mkdir(parents=True,mode=0o700);created=True
                for name,row in sorted(expected.items()):
                    target=destination/name;target.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
                    digest=hashlib.sha256();count=0
                    fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,"O_NOFOLLOW",0),0o600)
                    with os.fdopen(fd,"wb") as dst,z.open(name) as src:
                        for raw in iter(lambda:src.read(CHUNK),b""):
                            count+=len(raw)
                            if count>row["size"]:raise BundleError("Expanded member exceeds inventory")
                            digest.update(raw);dst.write(raw)
                    if count!=row["size"] or digest.hexdigest()!=row["sha256"]:raise BundleError("File fingerprint mismatch")
            except Exception:
                if created:shutil.rmtree(destination)
                raise
    return manifest

def validate_pair(data:dict,recovery:dict):
    if (data.get("kind")!="data" or recovery.get("kind")!="recovery" or data.get("capture_id")!=recovery.get("capture_id")
        or data.get("metadata")!=recovery.get("metadata")):
        raise BundleError("Data and recovery material are not from the same capture")
