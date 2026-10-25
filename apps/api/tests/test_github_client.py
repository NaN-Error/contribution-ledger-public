"""Offline contracts for GitHub HTTPS, App authentication, and source authorization."""
import io,json,os,time
from base64 import urlsafe_b64decode
from copy import deepcopy
from datetime import datetime,timezone
from pathlib import Path
from urllib.error import HTTPError,URLError
from urllib.parse import parse_qs,urlsplit
from types import SimpleNamespace
import pytest
from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.asymmetric import rsa,padding,ec
from app.integrations.github.client import (Transport,GitHubClient,GitHubError,READ_PERMISSIONS,
    MAX_RESPONSE_BYTES,NoRedirect,app_jwt,pkce,permissions_checked,repo_descriptor,retry_delay)
from app.security.secrets.store import SecretUnavailable,MountedSecretStore
from tests.phase8_helpers import REPO

@pytest.fixture(scope='module')
def key():return rsa.generate_private_key(public_exponent=65537,key_size=2048)

@pytest.fixture
def secrets(key):
    class Secrets:
        def read(self,name):
            if name=='github-client-secret':return b'synthetic-contract-secret-not-real'
            if name=='github-webhook-secret':return b'synthetic-webhook-signing-contract-secret-not-real'
            return key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption())
    return Secrets()

def configuration():return SimpleNamespace(github_enabled=True,github_client_id='Iv1.synthetic',github_app_id=123,github_callback_url='http://127.0.0.1:5173/github/callback')

class FixtureTransport:
    def __init__(self):
        self.calls=[];self.install={'id':501,'app_id':123,'account':{'login':'synthetic'},'permissions':dict(READ_PERMISSIONS),'suspended_at':None}
        self.repos=[deepcopy(REPO)];self.more=False
    def request(self,method,origin,path,**kw):
        self.calls.append((method,origin,path,deepcopy(kw)))
        if path=='/login/oauth/access_token':return {'access_token':'synthetic-token','refresh_token':'synthetic-refresh'},False
        if path=='/user':return {'id':7001,'login':'synthetic-author'},False
        if path=='/user/installations':return {'installations':[deepcopy(self.install)]},self.more
        if path=='/user/installations/501/repositories':return {'repositories':deepcopy(self.repos)},self.more
        if path=='/app/installations/501':return deepcopy(self.install),False
        if path=='/app/installations/501/access_tokens':return {'token':'synthetic-one-repo-token','permissions':dict(READ_PERMISSIONS)},False
        raise AssertionError('Unexpected endpoint')

def test_rs256_jwt_signature_and_claims(key,secrets):
    token=app_jwt('Iv1.synthetic',secrets.read('github-private-key.pem'),100000)
    header,payload,signature=token.split('.')
    decode=lambda x:urlsafe_b64decode(x+'='*((4-len(x)%4)%4))
    assert json.loads(decode(header))=={'alg':'RS256','typ':'JWT'}
    assert json.loads(decode(payload))=={'iat':99940,'exp':100480,'iss':'Iv1.synthetic'}
    key.public_key().verify(decode(signature),(header+'.'+payload).encode(),padding.PKCS1v15(),hashes.SHA256())

@pytest.mark.parametrize('data',[b'',b'not a private key',b'-----BEGIN PRIVATE KEY-----\nfixture\n-----END PRIVATE KEY-----'])
def test_invalid_keys_are_sanitized(data):
    with pytest.raises(SecretUnavailable) as error:app_jwt('fixture',data)
    assert repr(data) not in str(error.value)

def test_non_rsa_key_rejected():
    key=ec.generate_private_key(ec.SECP256R1())
    data=key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption())
    with pytest.raises(SecretUnavailable):app_jwt('fixture',data)

def test_pkce_bound_to_state_and_operator_secret():
    a=pkce(b'first', 'A'*43);assert a==pkce(b'first','A'*43)
    assert len(a[0])==43 and len(a[1])==43 and a[0]!=a[1]
    assert a!=pkce(b'first','B'*43) and a!=pkce(b'second','A'*43)

def test_authorization_url_contains_no_credential(secrets):
    client=GitHubClient(configuration(),secrets,FixtureTransport());url=client.authorize_url('A'*43)
    parsed=urlsplit(url);query=parse_qs(parsed.query)
    assert parsed.netloc=='github.com' and query['code_challenge_method']==['S256']
    assert 'secret' not in query and 'code_verifier' not in query and 'synthetic-contract-secret' not in url

def test_user_admin_intersection_and_memory_only_tokens(secrets):
    transport=FixtureTransport();transport.repos.append(dict(REPO,id=9002,full_name='synthetic/not-admin',permissions={'admin':False}))
    client=GitHubClient(configuration(),secrets,transport)
    proof=client.verify_authorization('synthetic-code','A'*43,501)
    assert [r['github_id'] for r in proof['repositories']]==[9001]
    serialized=json.dumps(proof);assert 'synthetic-token' not in serialized and 'synthetic-refresh' not in serialized
    exchange=transport.calls[0][3]['body'];assert 'code_verifier' in exchange and 'client_secret' in exchange
    assert not any('access_token' in k or 'refresh_token' in k for k in client.__dict__)

def test_user_without_installation_rejected(secrets):
    with pytest.raises(GitHubError,match='github_installation_not_authorized'):
        GitHubClient(configuration(),secrets,FixtureTransport()).verify_authorization('synthetic-code','A'*43,999)

def test_read_access_is_not_repository_sharing_authority(secrets):
    transport=FixtureTransport();transport.repos[0]['permissions']={'pull':True,'admin':False}
    with pytest.raises(GitHubError,match='github_repository_admin_required'):
        GitHubClient(configuration(),secrets,transport).verify_authorization('synthetic-code','A'*43,501)

def test_catalog_pages_have_a_bound(secrets):
    transport=FixtureTransport();transport.more=True;client=GitHubClient(configuration(),secrets,transport)
    with pytest.raises(GitHubError,match='github_authorization_catalog_limit'):list(client._pages('/user/installations','fixture','installations',maximum=2))
    assert len(transport.calls)==2

def test_installation_token_is_one_repo_read_only(secrets):
    transport=FixtureTransport();client=GitHubClient(configuration(),secrets,transport)
    assert client.repository_token(501,9001)=='synthetic-one-repo-token'
    body=transport.calls[-1][3]['body'];assert body=={'repository_ids':[9001],'permissions':READ_PERMISSIONS}

@pytest.mark.parametrize('change',[{'app_id':999},{'suspended_at':'2026-01-01T00:00:00Z'},{'permissions':{}},{'permissions':dict(READ_PERMISSIONS,contents='write')},{'permissions':dict(READ_PERMISSIONS,administration='write')}])
def test_permissions_fail_closed(change):
    record=dict(FixtureTransport().install,**change)
    with pytest.raises(GitHubError):permissions_checked(record,123)

@pytest.mark.parametrize('row',[dict(REPO,id=True),dict(REPO,id=0),dict(REPO,id=2**53),dict(REPO,full_name='../evil'),dict(REPO,full_name='owner/repo/extra'),dict(REPO,full_name='owner/r?query'),dict(REPO,full_name='owner/r%2f..')])
def test_invalid_repository_identity_rejected(row):
    with pytest.raises(GitHubError):repo_descriptor(row)

@pytest.mark.parametrize('method,origin,path',[
 ('GET','http://api.github.com','/user'),('GET','https://evil.test','/user'),('GET','https://api.github.com','//evil.test'),
 ('GET','https://api.github.com','/user?token=bad'),('GET','https://api.github.com','/user#x'),
 ('POST','https://api.github.com','/repos/owner/repo/issues'),('DELETE','https://api.github.com','/repos/owner/repo'),
 ('GET','https://github.com','/login/oauth/authorize')])
def test_transport_rejects_writes_arbitrary_hosts_and_queries(method,origin,path):
    with pytest.raises(GitHubError):Transport().request(method,origin,path)

def response(body=b'{}',headers=None):
    class Response(io.BytesIO):
        status=200
    obj=Response(body);obj.headers=headers or {};return obj

def transport_with_response(obj):
    tr=Transport()
    class Opener:
        def open(self,*args,**kwargs):return obj
    tr.opener=Opener();return tr

def test_transport_plain_json_and_no_link_following():
    tr=transport_with_response(response(b'[]',{'link':'<https://evil.test>; rel="next"'}))
    assert tr.request('GET','https://api.github.com','/user')==([],True)

@pytest.mark.parametrize('body',[b'not json',b'42',b'null',b'"a string"'])
def test_invalid_json_body_rejected(body):
    with pytest.raises(GitHubError):transport_with_response(response(body)).request('GET','https://api.github.com','/user')

def test_response_size_and_encoding_limits():
    with pytest.raises(GitHubError,match='github_response_too_large'):transport_with_response(response(b' '* (MAX_RESPONSE_BYTES+1))).request('GET','https://api.github.com','/user')
    with pytest.raises(GitHubError,match='github_response_encoding'):transport_with_response(response(b'{}',{'content-encoding':'gzip'})).request('GET','https://api.github.com','/user')

@pytest.mark.parametrize('status,headers,code',[(429,{'Retry-After':'120'},'github_rate_limited'),(403,{},'github_forbidden'),(401,{},'github_access_denied'),(404,{},'github_access_denied'),(302,{},'github_redirect_rejected'),(500,{},'github_unavailable'),(409,{},'github_empty_or_conflicting_repository'),(422,{},'github_request_rejected')])
def test_transport_errors_sanitized(status,headers,code):
    tr=Transport()
    class Opener:
        def open(self,*args,**kwargs):raise HTTPError('https://api.github.com/private',status,'SECRET remote detail',headers,io.BytesIO(b'SECRET'))
    tr.opener=Opener()
    with pytest.raises(GitHubError) as error:tr.request('GET','https://api.github.com','/user')
    assert error.value.code==code and 'SECRET' not in str(error.value)

@pytest.mark.parametrize('headers,expected',[({},60),({'retry-after':'120'},120),({'retry-after':'1'},60),({'retry-after':'garbage'},60),({'x-ratelimit-remaining':'0','x-ratelimit-reset':'1120'},121),({'retry-after':'Thu, 01 Jan 1970 00:20:00 GMT'},201)])
def test_retry_delay_honors_server_bound(headers,expected):assert retry_delay(headers,1000)==expected

def test_no_redirect_handler():assert NoRedirect().redirect_request(None,None,None,None,None,None) is None

def test_mounted_secret_is_bounded_and_named(tmp_path):
    file=tmp_path/'github-client-secret';file.write_bytes(b'  synthetic secret  ');file.chmod(0o400)
    store=MountedSecretStore(str(tmp_path));assert store.read('github-client-secret')==b'synthetic secret'
    for bad in ['../github-client-secret','arbitrary.txt','/etc/passwd']:
        with pytest.raises(SecretUnavailable):store.read(bad)

@pytest.mark.parametrize('kind',['empty','oversize','directory','symlink','world_writable'])
def test_unsafe_secret_files_rejected(tmp_path,kind):
    file=tmp_path/'github-client-secret'
    if kind=='directory':file.mkdir()
    elif kind=='symlink':(tmp_path/'target').write_text('fixture');file.symlink_to(tmp_path/'target')
    else:file.write_bytes(b'' if kind=='empty' else b'a'*16385 if kind=='oversize' else b'fixture');file.chmod(0o666 if kind=='world_writable' else 0o600)
    with pytest.raises(SecretUnavailable):MountedSecretStore(str(tmp_path)).read('github-client-secret')


def test_authorization_deadline_is_context_local(secrets):
    from app.integrations.github.client import AUTH_DEADLINE
    assert AUTH_DEADLINE.get() is None
    GitHubClient(configuration(),secrets,FixtureTransport()).verify_authorization('synthetic-code','A'*43,501)
    assert AUTH_DEADLINE.get() is None
    token=AUTH_DEADLINE.set(time.monotonic()-1)
    try:
        with pytest.raises(GitHubError,match='github_authorization_timeout'):Transport().request('GET','https://api.github.com','/user')
    finally:AUTH_DEADLINE.reset(token)


def test_secret_provision_requires_confirmation_and_preserves_invalid_pair(tmp_path,secrets):
    from app.security.secrets.provision import stage,CONFIRM
    source=tmp_path/'source';target=tmp_path/'target';source.mkdir();target.mkdir()
    for name in MountedSecretStore.allowed_names:(source/name).write_bytes(secrets.read(name))
    with pytest.raises(SecretUnavailable):stage(source,target,confirmed='no')
    assert not list(target.iterdir())
    if os.name != 'posix':
        # The Docker-volume command must reject unsupported host execution
        # without leaving a partly staged credential behind.
        with pytest.raises(SecretUnavailable):stage(source,target,confirmed=CONFIRM)
        assert not list(target.iterdir())
        return
    stage(source,target,confirmed=CONFIRM,uid=os.getuid(),gid=os.getgid())
    assert MountedSecretStore(str(target)).read('github-client-secret')==secrets.read('github-client-secret')
    assert (target/'github-private-key.pem').stat().st_mode&0o777==0o400
    (source/'github-private-key.pem').write_bytes(b'invalid replacement')
    with pytest.raises(SecretUnavailable):stage(source,target,confirmed=CONFIRM,uid=os.getuid(),gid=os.getgid())
    assert (target/'github-private-key.pem').read_bytes()==secrets.read('github-private-key.pem').strip()
