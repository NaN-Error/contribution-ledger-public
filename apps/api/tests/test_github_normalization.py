from types import SimpleNamespace
import pytest
from app.integrations.github.normalization import text,normalize,number,sha,claim_identity,github_identity,canonical,summary
from app.integrations.github.client import GitHubError
from tests.phase8_helpers import pull,commit,REPO,SHA_A,GH_BOT

REPOSITORY=SimpleNamespace(github_id=9001,full_name='synthetic/game')

def test_untrusted_text_redaction_and_limits():
    omitted=[];result=text('ghp_'+'A'*40+'\x00'+'Z'*100,60,omitted)
    assert 'A'*40 not in result and '\x00' not in result and len(result)==60
    assert any('credential' in s for s in omitted) and any('truncated' in s for s in omitted)

def test_key_blocks_redacted():
    result=text('-----BEGIN RSA PRIVATE KEY-----\nfictional\n-----END RSA PRIVATE KEY-----')
    assert 'fictional' not in result and 'REDACTED' in result

def test_commit_roles_coauthor_and_local_email_not_matched():
    result=normalize('commit',commit(),REPOSITORY)
    roles={i['role'] for i in result['identities']}
    assert {'commit_author','commit_committer','git_author_claim','git_committer_claim','co_author_claim'}<=roles
    assert all('mapped_user_id' not in i for i in result['identities'])
    assert 'owner@example.test' in str(result['identities'])
    assert result['content']['signature_verified_by_github'] is False

def test_unknown_claims_are_explicit():
    a=claim_identity('Unmapped','','git_author_claim',SHA_A)
    b=claim_identity('Unmapped','','git_committer_claim',SHA_A)
    assert a['kind']=='unknown' and a['external_key']!=b['external_key']

def test_claim_casefold_and_multiple_emails():
    a=claim_identity('A','Owner@Example.test','author','fixture');b=claim_identity('B','owner@example.test','author','fixture')
    assert a['external_key']==b['external_key']
    assert a['external_key']!=claim_identity('A','other@example.test','author','fixture')['external_key']

def test_bot_identification():assert github_identity(GH_BOT,'comment_author')['kind']=='github_bot'

@pytest.mark.parametrize('filename',['.env','x/.env.production','keys/private.pem','id_ed25519','node_modules/file.js','vendor/lib.c','package-lock.json'])
def test_sensitive_and_generated_files_excluded(filename):
    result=normalize('pull_files',{'files':[{'filename':filename,'patch':'sensitive fixture'}]},REPOSITORY,remote_key='1:1')
    assert result['content']['files'][0]['patch'] is None and result['omissions']

def test_missing_patch_does_not_claim_zero_work():
    result=normalize('commit_files',{'files':[{'filename':'art/hero.png','sha':SHA_A}]},REPOSITORY,remote_key=SHA_A+':1')
    assert result['content']['files'][0]['patch_state']=='missing_binary_or_api_omitted_patch'

def test_file_patch_truncation_is_visible():
    result=normalize('pull_files',{'files':[{'filename':'large.py','patch':'a'*9000}]},REPOSITORY,remote_key='1:1')
    assert len(result['content']['files'][0]['patch'])==4096 and result['omissions']

def test_coauthor_limit_recorded():
    data=commit();data['commit']['message']='\n'.join(f'Co-authored-by: Person {i} <p{i}@example.test>' for i in range(25))
    result=normalize('commit',data,REPOSITORY)
    assert len([i for i in result['identities'] if i['role']=='co_author_claim'])==20
    assert 'coauthor_claim_limit' in result['omissions']

def test_remote_urls_are_not_stored_or_followed():
    data=pull();data['url']='http://127.0.0.1/admin';data['diff_url']='https://evil.test'
    result=normalize('pull_request',data,REPOSITORY)
    assert 'diff_url' not in str(result) and '127.0.0.1' not in str(result)

@pytest.mark.parametrize('value',[True,0,-1,'12',2**63])
def test_source_numbers_reject_ambiguous_values(value):
    with pytest.raises(GitHubError):number(value)

@pytest.mark.parametrize('value',['a'*39,'A'*40,'a'*41,'../main','main',None])
def test_shas_are_exact(value):
    with pytest.raises(GitHubError):sha(value)

def test_deterministic_canonical_bytes_and_excerpt():
    result=normalize('pull_request',pull(),REPOSITORY)
    assert canonical(result)==canonical(dict(reversed(list(result.items()))))
    assert 'Synthetic reconnection' in summary(result) and len(summary(result))<=12000

def test_check_metadata_is_not_correctness_proof():
    result=normalize('check_run',{'id':1,'head_sha':SHA_A,'conclusion':'success','output':{'text':'private log'}},REPOSITORY)
    assert 'not proof' in result['content']['notice'] and 'private log' not in str(result)
