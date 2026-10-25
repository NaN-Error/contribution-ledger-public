import io
import json
import os
import tarfile
from pathlib import Path
from uuid import uuid4
import pytest
from app.operations.archive import (BundleError,CHUNK,create_bundle,decrypt,encrypt,keygen,read_key,safe_name,unpack_bundle,validate_pair)
from app.operations.volume import export_volume,import_volume

@pytest.mark.parametrize('size',[0,1,CHUNK-1,CHUNK,CHUNK+1,2*CHUNK+5])
def test_authenticated_stream_roundtrip(size):
    data=os.urandom(size);key=os.urandom(32);sealed=io.BytesIO();encrypt(io.BytesIO(data),sealed,key)
    restored=io.BytesIO();decrypt(io.BytesIO(sealed.getvalue()),restored,key);assert restored.getvalue()==data

@pytest.mark.parametrize('kind',['wrong_key','flip','truncated','missing_terminal','appended','reordered'])
def test_encrypted_stream_rejects_tampering(kind):
    key=os.urandom(32);out=io.BytesIO();encrypt(io.BytesIO(b'a'*(CHUNK+100)),out,key);raw=out.getvalue()
    if kind=='wrong_key':key=os.urandom(32)
    elif kind=='flip':raw=raw[:100]+bytes([raw[100]^1])+raw[101:]
    elif kind=='truncated':raw=raw[:-1]
    elif kind=='missing_terminal':raw=raw[:-20]
    elif kind=='appended':raw+=b'junk'
    elif kind=='reordered':raw=raw[:31]+raw[-20:]+raw[31:-20]
    with pytest.raises(BundleError):decrypt(io.BytesIO(raw),io.BytesIO(),key)

@pytest.mark.parametrize('name',['../escape','/absolute','a/../b','a\\b','C:evil','a//b','./a','a/','a\x00b',''])
def test_unsafe_names(name):
    with pytest.raises(BundleError):safe_name(name)

def test_bundle_roundtrip_and_refuses_overwrite(tmp_path):
    f=tmp_path/'record';f.write_bytes(b'private financial document');key=os.urandom(32);sealed=tmp_path/'one.clb';dest=tmp_path/'recovered'
    manifest=create_bundle({'objects/record':f},sealed,key,capture_id=str(uuid4()),kind='data',metadata={'test':True},scratch=tmp_path/'scratch')
    assert b'private financial' not in sealed.read_bytes()
    restored=unpack_bundle(sealed,dest,key,scratch=tmp_path/'scratch');assert restored==manifest
    assert (dest/'objects/record').read_bytes()==f.read_bytes()
    with pytest.raises(BundleError):unpack_bundle(sealed,dest,key,scratch=tmp_path/'scratch')
    with pytest.raises(FileExistsError):create_bundle({'objects/record':f},sealed,key,capture_id=str(uuid4()),kind='data',metadata={},scratch=tmp_path/'scratch')

def test_key_is_separate_private_and_not_overwritten(tmp_path):
    key=tmp_path/'key';keygen(key);raw=read_key(key);assert len(raw)==32
    with pytest.raises(FileExistsError):keygen(key)
    assert read_key(key)==raw
    if os.name!='nt':assert key.stat().st_mode&0o077==0

def test_symlink_not_followed(tmp_path):
    source=tmp_path/'real';source.write_text('private');link=tmp_path/'link';link.symlink_to(source)
    with pytest.raises(Exception):create_bundle({'link':link},tmp_path/'bundle',os.urandom(32),capture_id=str(uuid4()),kind='data',metadata={},scratch=tmp_path/'scratch')

def test_pair_cannot_mix_captures():
    a={'kind':'data','capture_id':'a','metadata':{}}
    with pytest.raises(BundleError):validate_pair(a,{'kind':'recovery','capture_id':'b','metadata':{}})
    validate_pair(a,{'kind':'recovery','capture_id':'a','metadata':{}})

def test_private_volume_roundtrip(tmp_path):
    src=tmp_path/'source';src.mkdir();(src/'nested').mkdir();(src/'nested/blob').write_bytes(os.urandom(1500))
    archive=io.BytesIO();export_volume(src,archive);target=tmp_path/'target';target.mkdir()
    import_volume(target,io.BytesIO(archive.getvalue()));assert (target/'nested/blob').read_bytes()==(src/'nested/blob').read_bytes()
    with pytest.raises(BundleError):import_volume(target,io.BytesIO(archive.getvalue()))

@pytest.mark.parametrize('kind',['symlink','hardlink','traversal','duplicate','directory','device'])
def test_volume_refuses_unsafe_members(tmp_path,kind):
    data=io.BytesIO()
    with tarfile.open(fileobj=data,mode='w') as archive:
        item=tarfile.TarInfo('../escape' if kind=='traversal' else 'blob')
        if kind=='symlink':item.type=tarfile.SYMTYPE;item.linkname='/outside'
        if kind=='hardlink':item.type=tarfile.LNKTYPE;item.linkname='/outside'
        if kind=='directory':item.type=tarfile.DIRTYPE
        if kind=='device':item.type=tarfile.CHRTYPE
        archive.addfile(item,io.BytesIO())
        if kind=='duplicate':archive.addfile(item,io.BytesIO())
    target=tmp_path/'target';target.mkdir()
    with pytest.raises(BundleError):import_volume(target,io.BytesIO(data.getvalue()))
    assert not (tmp_path/'escape').exists()
