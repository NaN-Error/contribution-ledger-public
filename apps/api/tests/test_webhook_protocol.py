from uuid import uuid4
import pytest
from app.core.errors import ApiError
from app.integrations.github.webhook_protocol import parse_signed,MAX_WEBHOOK_BYTES
from tests.phase9_helpers import signed,event,SECRET,operational

def parse(body,event_name='pull_request',extra=()):
    raw,headers=signed(operational(body,event_name) if isinstance(body,dict) else body,event_name)
    return parse_signed(raw,[(k.encode(),v.encode()) for k,v in headers.items()]+list(extra),SECRET,123)

def test_signed_event_keeps_ids_not_body_or_urls():
    result=parse(event())
    assert result.targets==({'kind':'pull','subject':'1'},)
    assert result.installation_id==501 and result.repository_ids==(9001,)
    assert 'UNTRUSTED' not in repr(result)

@pytest.mark.parametrize('change',['body','signature','secret','missing'])
def test_signature_cannot_be_forged(change):
    raw,headers=signed(event());secret=SECRET
    if change=='body':raw+=b' '
    elif change=='signature':headers['x-hub-signature-256']='sha256='+'0'*64
    elif change=='secret':secret=b'wrong-secret-of-at-least-32-bytes-long'
    else:del headers['x-hub-signature-256']
    with pytest.raises(ApiError) as e:parse_signed(raw,[(k.encode(),v.encode()) for k,v in headers.items()],secret,123)
    assert e.value.code=='github_signature_rejected'

@pytest.mark.parametrize('body',[
 b'{"installation":{"id":501},"installation":{"id":502}}',b'[]',b'null',b'{',b'{"x":NaN}',
 event(installation={'id':True}),event(repository={'id':0}),event(pull_request={'number':-1}),
 event(pull_request={'number':'1'}),event(action='edited with space'),event(installation={'id':2**53}),
 event(pull_request=None),event(repository=None)])
def test_invalid_signed_shapes_rejected(body):
    with pytest.raises(ApiError):parse(body)

@pytest.mark.parametrize('header',[b'x-hub-signature-256',b'X-GitHub-Delivery',b'content-length',b'content-type'])
def test_ambiguous_security_headers(header):
    extras=[(header,b'x')]
    if header==b'content-length':extras.append((header,b'2'))
    with pytest.raises(ApiError) as e:parse(event(),extra=extras)
    assert e.value.code=='github_ambiguous_webhook_headers'

@pytest.mark.parametrize('body',[b'',b'x',b'x'*(MAX_WEBHOOK_BYTES+1)],ids=['empty','too_short','oversized'])
def test_size_bounds(body):
    with pytest.raises(ApiError) as e:parse(body)
    assert e.value.status==413

@pytest.mark.parametrize('event_name,body,kind,subject',[
 ('issues',event(action='edited',issue={'number':22}),'issue','22'),
 ('issue_comment',event(action='created',issue={'number':22,'pull_request':{}}),'pull','22'),
 ('check_run',event(action='completed',check_run={'head_sha':'a'*40,'pull_requests':[]}),'checks','a'*40),
 ('push',{'installation':{'id':501},'repository':{'id':9001},'ref':'refs/heads/main'},'reconcile',''),
 ('repository',event(action='archived'),'reconcile','')])
def test_event_routing(event_name,body,kind,subject):
    assert parse(body,event_name).targets[0]=={'kind':kind,'subject':subject}

@pytest.mark.parametrize('action',['deleted','suspend','new_permissions_accepted'])
def test_installation_revocation(action):
    result=parse(event(action=action),'installation')
    assert result.revoke=='github_installation_'+action and not result.targets

@pytest.mark.parametrize('action',['created','unsuspend'])
def test_installation_grants_do_not_reenable(action):
    result=parse(event(action=action),'installation')
    assert result.revoke is None and result.targets==()

def test_removed_repository_ids_deduped():
    result=parse(event(action='removed',repositories_removed=[{'id':9001},{'id':9001}]),'installation_repositories')
    assert result.repository_ids==(9001,) and result.revoke

def test_unknown_event_acknowledge_without_fetch_targets():
    result=parse(event(action='created'),'discussion')
    assert not result.supported and not result.targets and result.revoke is None

def test_ping_is_app_specific():
    result=parse({'hook':{'type':'App','app_id':123}},'ping')
    assert result.installation_id==0 and not result.targets
    with pytest.raises(ApiError):parse({'hook':{'type':'App','app_id':456}},'ping')


def test_first_delivery_cannot_relabel_issue_as_installation_revocation():
    raw,headers=signed({'action':'deleted','installation':{'id':501},'repository':{'id':9001},'issue':{'number':1}},'installation')
    with pytest.raises(ApiError):parse_signed(raw,[(k.encode(),v.encode()) for k,v in headers.items()],SECRET,123)

def test_app_ping_without_optional_app_id():
    assert parse({'hook':{'type':'App'}},'ping').installation_id==0
