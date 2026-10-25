import os
from pathlib import Path
import pytest
from app.security.secrets.encrypted import EncryptedCredentialStore,initialize
from app.security.secrets.store import SecretUnavailable

@pytest.fixture
def vault(tmp_path):
    root=tmp_path/'cipher';master=tmp_path/'master'/'key';initialize(str(master),str(root))
    return EncryptedCredentialStore(str(root),str(master))

def test_context_bound_roundtrip_and_encrypted_at_rest(vault):
    ref=vault.write('synthetic-api-credential','workspace:connection:provider')
    assert vault.read(ref,'workspace:connection:provider')=='synthetic-api-credential'
    assert b'synthetic-api-credential' not in (vault.root/(ref+'.enc')).read_bytes()
    with pytest.raises(SecretUnavailable):vault.read(ref,'other-workspace')
    assert len(vault.master_file.read_bytes())==32

def test_different_random_ciphertexts(vault):
    a=vault.write('same-synthetic-key','ctx');b=vault.write('same-synthetic-key','ctx')
    assert a!=b and (vault.root/(a+'.enc')).read_bytes()!=(vault.root/(b+'.enc')).read_bytes()

def test_tamper_detected(vault):
    ref=vault.write('synthetic-credential','ctx');p=vault.root/(ref+'.enc');s=bytearray(p.read_bytes());s[-1]^=1;p.write_bytes(s)
    with pytest.raises(SecretUnavailable):vault.read(ref,'ctx')

def test_initialize_is_idempotent_and_does_not_rotate(vault):
    before=vault.master_file.read_bytes();initialize(str(vault.master_file),str(vault.root));assert before==vault.master_file.read_bytes()

def test_missing_master_over_existing_ciphertext_refuses_replacement(vault):
    vault.write('synthetic-credential','ctx');vault.master_file.unlink()
    with pytest.raises(SecretUnavailable):initialize(str(vault.master_file),str(vault.root))

def test_delete_is_idempotent(vault):
    ref=vault.write('synthetic-credential','ctx');vault.delete(ref);vault.delete(ref)
    with pytest.raises(SecretUnavailable):vault.read(ref,'ctx')

@pytest.mark.parametrize('value',['','short','with spaces', 'line\nbreak123','\u00f1'*12,'a'*4097])
def test_invalid_credentials(vault,value):
    with pytest.raises(SecretUnavailable):vault.write(value,'ctx')

@pytest.mark.parametrize('ref',['../../escape','anything',None,'00000000-0000-0000-0000-000000000000/extra'])
def test_invalid_references(vault,ref):
    with pytest.raises(SecretUnavailable):vault.read(ref,'ctx')

@pytest.mark.skipif(os.name=='nt',reason='POSIX permissions')
def test_world_readable_master_refused(vault):
    vault.master_file.chmod(0o644)
    with pytest.raises(SecretUnavailable):vault.write('synthetic-credential','ctx')

def test_symlinked_cipher_refused(vault,tmp_path):
    ref=vault.write('synthetic-credential','ctx');p=vault.root/(ref+'.enc');target=tmp_path/'target';p.rename(target);p.symlink_to(target)
    with pytest.raises(SecretUnavailable):vault.read(ref,'ctx')
