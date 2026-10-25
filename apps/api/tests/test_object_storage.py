from dataclasses import replace
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from uuid import UUID, uuid4
import os
import json
import subprocess
import pytest
import boto3
from botocore.stub import Stubber, ANY
from botocore.response import StreamingBody
from app.storage.contracts import ObjectReference, ObjectMissing, ObjectCorrupt, StorageUnavailable, ObjectTooLarge, read_bounded
from app.storage.local import LocalObjectStorage
from app.storage.s3 import S3ObjectStorage
from app.evidence.service import ObjectWrites


def test_local_roundtrip_scope_mode_integrity_and_delete(tmp_path):
    store=LocalObjectStorage(tmp_path/'private');workspace=uuid4()
    reference=store.put(workspace,BytesIO(b'synthetic bytes'),100)
    filename=tmp_path/'private'/str(workspace)/str(reference.object_id)
    assert filename.read_bytes()==b'synthetic bytes'
    if os.name == 'nt':
        # Windows stat mode is not a DACL. Python 3.13 mkdir(0700) restricts
        # the directory to the current user and Administrators; files inherit it.
        env = {**os.environ, 'CL_TEST_OBJECT_PATH': str(filename)}
        script = "$a=[System.IO.File]::GetAccessControl($env:CL_TEST_OBJECT_PATH); @{owner=$a.GetOwner([System.Security.Principal.SecurityIdentifier]).Value; current=[System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value; allowed=@($a.Access | Where-Object AccessControlType -eq Allow | ForEach-Object {$_.IdentityReference.Translate([System.Security.Principal.SecurityIdentifier]).Value})} | ConvertTo-Json -Compress"
        acl = json.loads(subprocess.check_output(['powershell', '-NoProfile', '-NonInteractive', '-Command', script], env=env, text=True))
        assert acl['owner'] == acl['current']
        allowed = set(acl['allowed'])
        assert allowed <= {acl['current'], 'S-1-3-4', 'S-1-5-18', 'S-1-5-32-544'}
        assert allowed & {acl['current'], 'S-1-3-4'}  # user or OWNER RIGHTS
    else:
        assert filename.stat().st_mode&0o777==0o600
    store.check(reference)
    with store.open(reference) as stream: assert stream.read()==b'synthetic bytes'
    with pytest.raises(ObjectMissing):store.open(replace(reference,workspace_id=uuid4()))
    filename.write_bytes(b'corrupted bytes')
    with pytest.raises(ObjectCorrupt):store.open(reference)
    store.delete(reference);store.delete(reference)
    with pytest.raises(ObjectMissing):store.open(reference)


def test_local_exclusive_collision_does_not_delete_old_object(tmp_path,monkeypatch):
    store=LocalObjectStorage(tmp_path);workspace=uuid4();same=uuid4()
    monkeypatch.setattr('app.storage.local.uuid4',lambda:same)
    original=store.put(workspace,BytesIO(b'original'),100)
    with pytest.raises(StorageUnavailable):store.put(workspace,BytesIO(b'replacement'),100)
    assert store.open(original).read()==b'original'


def test_local_symlink_root_workspace_and_file_rejected(tmp_path):
    real=tmp_path/'real';real.mkdir();link=tmp_path/'link';link.symlink_to(real,target_is_directory=True)
    with pytest.raises(StorageUnavailable):LocalObjectStorage(link).put(uuid4(),BytesIO(b'x'),100)
    workspace=uuid4();(real/str(workspace)).symlink_to(tmp_path,target_is_directory=True)
    with pytest.raises(StorageUnavailable):LocalObjectStorage(real).put(workspace,BytesIO(b'x'),100)
    store=LocalObjectStorage(real);ref=store.put(uuid4(),BytesIO(b'data'),100)
    path=real/str(ref.workspace_id)/str(ref.object_id);path.unlink();path.symlink_to(tmp_path/'unknown')
    with pytest.raises(ObjectCorrupt):store.open(ref)
    with pytest.raises(StorageUnavailable):store.delete(ref)


def test_local_hardlink_is_not_read(tmp_path):
    store=LocalObjectStorage(tmp_path);ref=store.put(uuid4(),BytesIO(b'x'),100)
    path=tmp_path/str(ref.workspace_id)/str(ref.object_id)
    os.link(path,tmp_path/'linked')
    with pytest.raises(ObjectCorrupt):store.open(ref)


@pytest.mark.skipif(not hasattr(os, 'mkfifo'), reason='Native POSIX FIFO creation is unavailable on this platform.')
def test_local_fifo_is_not_read(tmp_path):
    store=LocalObjectStorage(tmp_path);ref=store.put(uuid4(),BytesIO(b'x'),100)
    path=tmp_path/str(ref.workspace_id)/str(ref.object_id)
    path.unlink();os.mkfifo(path)
    with pytest.raises(ObjectCorrupt):store.open(ref)


@pytest.mark.parametrize('data,limit',[ (b'',1),(b'xx',1),(b'x',0),(b'x',6*1024*1024)])
def test_store_never_accepts_unbounded_or_empty_writes(data,limit):
    with pytest.raises((ObjectTooLarge,ValueError)):read_bounded(BytesIO(data),limit)


def test_known_failed_transaction_compensates_but_ambiguous_commit_preserves(tmp_path):
    store=LocalObjectStorage(tmp_path)
    with pytest.raises(ValueError):
        with ObjectWrites(store) as writes:
            first=writes.add(store.put(uuid4(),BytesIO(b'x'),100));raise ValueError('DB failure before commit')
    with pytest.raises(ObjectMissing):store.open(first)
    with pytest.raises(ValueError):
        with ObjectWrites(store) as writes:
            second=writes.add(store.put(uuid4(),BytesIO(b'x'),100));writes.success();raise ValueError('Commit response unavailable')
    assert store.open(second).read()==b'x'


@pytest.fixture
def s3():
    # Explicit synthetic keys disable credential discovery: no network or cloud account.
    client=boto3.client('s3',region_name='us-east-1',aws_access_key_id='synthetic',aws_secret_access_key='synthetic')
    with Stubber(client) as stub:
        yield S3ObjectStorage(client,'synthetic-evidence'),stub
        stub.assert_no_pending_responses()


def test_s3_contract_roundtrip_and_delete(s3):
    store,stub=s3;data=b'synthetic';digest=sha256(data).hexdigest();workspace=uuid4()
    stub.add_response('put_object',{}, {'Bucket':store.bucket,'Key':ANY,'Body':data,'ContentType':'application/octet-stream',
        'ContentLength':len(data),'IfNoneMatch':'*','Metadata':{'sha256':digest}})
    ref=store.put(workspace,BytesIO(data),100);params={'Bucket':store.bucket,'Key':f'evidence-v1/{workspace}/{ref.object_id}'}
    stub.add_response('head_object',{'ContentLength':len(data),'Metadata':{'sha256':digest}},params)
    store.check(ref)
    stream=BytesIO(data)
    stub.add_response('get_object',{'ContentLength':len(data),'Body':StreamingBody(stream,len(data))},params)
    assert store.open(ref).read()==data and stream.closed
    stub.add_response('delete_object',{},params);store.delete(ref)


@pytest.mark.parametrize('method,code,expected',[('head_object','NoSuchKey',ObjectMissing),('get_object','AccessDenied',StorageUnavailable),
    ('delete_object','AccessDenied',StorageUnavailable)])
def test_s3_errors_sanitized_and_missing_distinguished(s3,method,code,expected):
    store,stub=s3;ref=ObjectReference(uuid4(),uuid4(),'0'*64,1)
    stub.add_client_error(method,service_error_code=code,service_message='synthetic-secret internal-endpoint')
    with pytest.raises(expected) as error:getattr(store,{'head_object':'check','get_object':'open','delete_object':'delete'}[method])(ref)
    assert 'synthetic-secret' not in str(error.value)


def test_s3_checksum_and_size_mismatch_never_delivered(s3):
    store,stub=s3;ref=ObjectReference(uuid4(),uuid4(),sha256(b'good').hexdigest(),4)
    for data,size in [(b'bad!',4),(b'too long',8)]:
        stream=BytesIO(data);stub.add_response('get_object',{'ContentLength':size,'Body':StreamingBody(stream,len(data))})
        with pytest.raises(ObjectCorrupt):store.open(ref)
        assert stream.closed
    stub.add_response('head_object',{'ContentLength':4,'Metadata':{'sha256':'0'*64}})
    with pytest.raises(ObjectCorrupt):store.check(ref)


@pytest.mark.parametrize('bucket,prefix',[('BadBucket','evidence-v1'),('aa','safe'),('../unsafe','safe'),('valid-bucket','../unsafe')])
def test_s3_operator_names_are_bounded(bucket,prefix):
    with pytest.raises(ValueError):S3ObjectStorage(None,bucket,prefix)
