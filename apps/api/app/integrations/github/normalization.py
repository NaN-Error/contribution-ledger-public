"""Bounded, plain-text source representations and non-authoritative identity claims.

Only allowlisted metadata is stored. Secret redaction is best effort, not DLP or
malware scanning. Raw REST URL fields are discarded rather than automatically
followed. GitHub IDs are account identifiers, not proof of economic authorship.
"""
from hashlib import sha256
import json
import re
import unicodedata
from app.integrations.github.client import GitHubError, SHA

TOKEN = re.compile(r'(?:github_pat_[A-Za-z0-9_]{15,}|gh[pousr]_[A-Za-z0-9]{15,}|sk-(?:proj-)?[A-Za-z0-9_-]{20,})')
PRIVATE = re.compile(r'-----BEGIN [A-Z ]*PRIVATE KEY-----.*?(?:-----END [A-Z ]*PRIVATE KEY-----|\Z)', re.S)
COAUTHOR = re.compile(r'^Co-authored-by:\s*([^<>\r\n]{1,150})\s*<([^<>\s]{3,254})>\s*$', re.I | re.M)
EMAIL = re.compile(r'^[^<>\s@]+@[^<>\s@]+$')


def text(value, limit=6000, omissions=None, label='text'):
    value = '' if value is None else str(value)
    cleaned = ''.join(c if unicodedata.category(c) not in {'Cc','Cf'} or c in '\n\t' else '\ufffd' for c in value)
    redacted = TOKEN.sub('[REDACTED credential-like text]', PRIVATE.sub('[REDACTED private-key-like text]', cleaned))
    if omissions is not None and redacted != cleaned:
        omissions.append(label + ':credential_like_text_redacted')
    if len(redacted) > limit and omissions is not None:
        omissions.append(label + ':text_truncated')
    return redacted[:limit]


def number(value):
    if type(value) is not int or value <= 0 or value >= 2**63:
        raise GitHubError('github_invalid_source_identifier')
    return str(value)


def sha(value):
    if not isinstance(value, str) or not SHA.fullmatch(value):
        raise GitHubError('github_invalid_source_revision')
    return value


def github_identity(user, role):
    if not isinstance(user, dict) or type(user.get('id')) is not int or user['id'] <= 0:
        return None
    kind = 'github_bot' if user.get('type') == 'Bot' else 'github_user'
    return {'external_key': 'github:' + str(user['id']), 'kind': kind,
            'label': text(user.get('login') or 'Unnamed GitHub account', 254), 'role': role,
            'assertion': 'GitHub-reported account; not independent authorship verification'}


def claim_identity(name, email, role, context):
    email = str(email or '').strip().casefold()
    valid = len(email) <= 254 and EMAIL.fullmatch(email)
    key = 'email:' + sha256(email.encode()).hexdigest() if valid else 'unknown:' + sha256((context+':'+role).encode()).hexdigest()
    return {'external_key': key, 'kind': 'email_claim' if valid else 'unknown',
            'label': text((str(name or 'Unknown') + ' <' + email + '>') if valid else name or 'Unknown author', 254),
            'role': role, 'assertion': 'Unverified commit-text claim; never matched to a local account automatically'}


def safe_files(files, omissions):
    if not isinstance(files, list):
        raise GitHubError('github_invalid_response')
    result = []
    if len(files) > 100: omissions.append('file_page_truncated')
    for row in files[:100]:
        path = text(row.get('filename'), 1000, omissions, 'filename')
        low = path.lower()
        omitted = (low.split('/')[-1].startswith('.env') or low.endswith(('.pem', '.key', '.p12', '.pfx'))
                   or any(p in low.split('/') for p in ('node_modules', '.git', 'vendor', 'dist', 'build'))
                   or low.split('/')[-1] in {'id_rsa','id_ed25519','package-lock.json','yarn.lock','poetry.lock'})
        patch = row.get('patch')
        state = 'excluded_sensitive_or_generated_path' if omitted else 'missing_binary_or_api_omitted_patch' if patch is None else 'bounded_patch'
        if state != 'bounded_patch': omissions.append(path + ':' + state)
        result.append({'filename': path, 'previous_filename': text(row.get('previous_filename'), 1000),
                       'sha': text(row.get('sha'), 64), 'status': text(row.get('status'), 40),
                       'additions': row.get('additions') if type(row.get('additions')) is int else None,
                       'deletions': row.get('deletions') if type(row.get('deletions')) is int else None,
                       'patch_state': state, 'patch': None if state != 'bounded_patch' else text(patch, 4096, omissions, path)})
    return result


def normalize(kind, raw, repository, *, remote_key=None, extra=None):
    if not isinstance(raw, dict): raise GitHubError('github_invalid_response')
    omissions, identities, content = [], [], {}
    key = remote_key
    if kind in {'pull_request', 'issue'}:
        key = key or number(raw.get('number'))
        content = {k: text(raw.get(k), n, omissions, k) for k, n in [('title',500),('body',10000),('state',40),('created_at',40),('updated_at',40),('closed_at',40)]}
        content['number'] = int(key)
        identity = github_identity(raw.get('user'), 'pull_request_author' if kind == 'pull_request' else 'issue_author')
        if identity: identities.append(identity)
        if kind == 'pull_request':
            for name in ('head', 'base'):
                obj = raw.get(name) or {}
                content[name] = {'sha': text(obj.get('sha'), 64), 'ref': text(obj.get('ref'), 200)}
            content.update(merged=raw.get('merged'), merged_at=text(raw.get('merged_at'),40),
                           merge_commit_sha=text(raw.get('merge_commit_sha'),64),
                           reported_commits=raw.get('commits'), reported_changed_files=raw.get('changed_files'))
            merger = github_identity(raw.get('merged_by'), 'merger_not_assumed_author')
            if merger: identities.append(merger)
    elif kind == 'commit':
        key = key or sha(raw.get('sha'))
        commit = raw.get('commit') or {}
        content = {'sha': key, 'message': text(commit.get('message'), 10000, omissions, 'message'),
                   'parents': [text(p.get('sha'),64) for p in raw.get('parents', [])[:20]],
                   'git_author_date': text((commit.get('author') or {}).get('date'),40),
                   'git_committer_date': text((commit.get('committer') or {}).get('date'),40),
                   'signature_verified_by_github': (commit.get('verification') or {}).get('verified') is True,
                   'signature_reason': text((commit.get('verification') or {}).get('reason'),80)}
        for role in ('author','committer'):
            mapped = github_identity(raw.get(role), 'commit_' + role)
            if mapped: identities.append(mapped)
            claimed = commit.get(role) or {}
            identities.append(claim_identity(claimed.get('name'), claimed.get('email'), 'git_' + role + '_claim', key))
        matches = list(COAUTHOR.finditer(str(commit.get('message') or '')))
        if len(matches) > 20: omissions.append('coauthor_claim_limit')
        for found in matches[:20]: identities.append(claim_identity(found[1].strip(), found[2], 'co_author_claim', key))
        # Commit files are separate artifacts; missing patch is never called zero work.
    elif kind in {'review','comment','review_comment'}:
        key = key or number(raw.get('id'))
        content = {k: text(raw.get(k), n, omissions, k) for k,n in [('body',10000),('state',60),('created_at',40),('updated_at',40),('submitted_at',40),('commit_id',64),('original_commit_id',64),('path',1000)]}
        identity = github_identity(raw.get('user'), 'reviewer' if kind == 'review' else 'comment_author')
        if identity: identities.append(identity)
    elif kind in {'pull_files','commit_files'}:
        content = {'files': safe_files(raw.get('files', []), omissions), **(extra or {})}
    elif kind in {'check_run', 'commit_status'}:
        key = key or number(raw.get('id'))
        content = {k: text(raw.get(k), n, omissions, k) for k,n in [('name',200),('context',200),('state',80),('status',80),('conclusion',80),('head_sha',64),('started_at',40),('completed_at',40),('created_at',40),('updated_at',40),('description',1000)]}
        content['notice'] = 'Reported check metadata, not proof that the implementation is correct. Logs and annotations are not fetched.'
    else:
        raise GitHubError('github_unsupported_source_kind')
    if not key: raise GitHubError('github_invalid_source_identifier')
    if extra and kind not in {'pull_files','commit_files'}: content.update(extra)
    doc = {'schema_version': 1, 'kind': kind, 'remote_key': key,
           'repository': {'github_id': repository.github_id, 'full_name': repository.full_name},
           'content': content, 'identities': identities, 'omissions': list(dict.fromkeys(omissions)),
           'notice': 'Captured REST evidence, not accepted work, economic value, a verified person, or executed repository code.'}
    return doc


def canonical(document):
    return json.dumps(document, sort_keys=True, ensure_ascii=True, separators=(',', ':')).encode('utf-8')


def summary(document):
    """Safe short excerpt for an evidence statement; the full pinned source is separate."""
    c = document['content']
    title = c.get('title') or c.get('name') or c.get('context') or document['remote_key']
    excerpt = c.get('body') or c.get('message') or c.get('description') or ''
    return text(f"GitHub {document['kind']}: {title}\n\n{excerpt}\n\nThis is imported source evidence, not an acceptance decision.", 10000)
