"""No live credentials: optional signing-file compatibility and fail-closed rotation."""
import os
import pytest
from app.security.secrets.store import MountedSecretStore,SecretUnavailable
from app.security.secrets.provision import stage,CONFIRM
from tests.test_github_client import key,secrets


@pytest.mark.skipif(os.name != 'posix', reason='This provisioner targets a POSIX Docker secret volume.')
def test_earlier_two_file_provisioning_still_works(tmp_path,secrets):
    source=tmp_path/'source';target=tmp_path/'target';source.mkdir()
    for name in ['github-private-key.pem','github-client-secret']:(source/name).write_bytes(secrets.read(name))
    stage(source,target,confirmed=CONFIRM,uid=os.getuid(),gid=os.getgid())
    assert (target/'github-client-secret').read_bytes()==secrets.read('github-client-secret')
    assert not (target/'github-webhook-secret').exists()


@pytest.mark.skipif(os.name != 'posix', reason='This provisioner targets a POSIX Docker secret volume.')
def test_invalid_third_file_cannot_partially_rotate_existing_pair(tmp_path,secrets):
    source=tmp_path/'source';target=tmp_path/'target';source.mkdir()
    for name in MountedSecretStore.allowed_names:(source/name).write_bytes(secrets.read(name))
    stage(source,target,confirmed=CONFIRM,uid=os.getuid(),gid=os.getgid())
    before={p.name:p.read_bytes() for p in target.iterdir()}
    (source/'github-client-secret').write_bytes(b'synthetic-replacement-secret')
    (source/'github-webhook-secret').write_bytes(b'too-short')
    with pytest.raises(SecretUnavailable):stage(source,target,confirmed=CONFIRM,uid=os.getuid(),gid=os.getgid())
    assert before=={p.name:p.read_bytes() for p in target.iterdir()}


@pytest.mark.skipif(os.name != 'posix', reason='This provisioner targets a POSIX Docker secret volume.')
def test_omitting_optional_file_preserves_previous_signing_key(tmp_path,secrets):
    source=tmp_path/'source';target=tmp_path/'target';source.mkdir()
    for name in MountedSecretStore.allowed_names:(source/name).write_bytes(secrets.read(name))
    stage(source,target,confirmed=CONFIRM,uid=os.getuid(),gid=os.getgid())
    (source/'github-webhook-secret').unlink()
    stage(source,target,confirmed=CONFIRM,uid=os.getuid(),gid=os.getgid())
    assert MountedSecretStore(str(target)).read('github-webhook-secret')==secrets.read('github-webhook-secret')


def test_non_posix_provisioner_refuses_before_reading_or_writing(tmp_path,monkeypatch):
    from pathlib import Path
    source=tmp_path/'source';target=tmp_path/'target'
    source.mkdir();target.mkdir();retained=target/'retained';retained.write_bytes(b'synthetic-retained-value')
    def forbidden_read(*args,**kwargs):raise AssertionError('Unsupported staging must not read a credential.')
    with monkeypatch.context() as patch:
        patch.setattr(os,'name','nt')
        patch.setattr(Path,'read_bytes',forbidden_read)
        with pytest.raises(SecretUnavailable):stage(source,target,confirmed=CONFIRM)
    assert list(target.iterdir())==[retained] and retained.read_bytes()==b'synthetic-retained-value'
    assert list(source.iterdir())==[]
