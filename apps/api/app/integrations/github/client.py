"""Fixed-origin HTTPS, bounded JSON, read-only GitHub APIs and memory-only tokens.

No SDK auto-retries, redirects, arbitrary provider hosts, git clones or repository
execution. Access/authorization tokens are used only in this process. API error
bodies and exception strings are never surfaced or logged.
"""
from base64 import urlsafe_b64encode
from contextvars import ContextVar
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from hashlib import sha256
import hmac
import json
import re
import ssl
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, build_opener, HTTPRedirectHandler, HTTPSHandler, ProxyHandler
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from app.security.secrets.store import SecretUnavailable

AUTH_DEADLINE = ContextVar('github_authorization_deadline', default=None)

API_VERSION = '2026-03-10'
READ_PERMISSIONS = {'contents': 'read', 'issues': 'read', 'pull_requests': 'read', 'checks': 'read', 'metadata': 'read'}
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
REPO_PART = re.compile(r'^[A-Za-z0-9_.-]{1,100}$')
SHA = re.compile(r'^(?:[0-9a-f]{40}|[0-9a-f]{64})$')


class GitHubError(Exception):
    def __init__(self, code='github_unavailable', retry_seconds=None):
        super().__init__(code)
        self.code = code
        self.retry_seconds = retry_seconds


def b64(data):
    return urlsafe_b64encode(data).decode('ascii').rstrip('=')


def pkce(secret: bytes, state: str):
    # Derivation avoids storing a plaintext verifier in the application database.
    verifier = b64(hmac.new(secret, b'github-pkce-v1:' + state.encode('ascii'), sha256).digest())
    return verifier, b64(sha256(verifier.encode('ascii')).digest())


def app_jwt(client_id, private_key, instant=None):
    instant = int(time.time() if instant is None else instant)
    try:
        key = serialization.load_pem_private_key(private_key, password=None)
        if not isinstance(key, rsa.RSAPrivateKey) or key.key_size < 2048:
            raise SecretUnavailable()
        head = b64(b'{"alg":"RS256","typ":"JWT"}')
        payload = b64(json.dumps({'iat': instant - 60, 'exp': instant + 480, 'iss': client_id}, separators=(',', ':')).encode())
        signed = (head + '.' + payload).encode('ascii')
        return signed.decode() + '.' + b64(key.sign(signed, padding.PKCS1v15(), hashes.SHA256()))
    except (ValueError, TypeError):
        raise SecretUnavailable() from None


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def retry_delay(headers, instant=None):
    instant = time.time() if instant is None else instant
    waits = [60]
    value = headers.get('retry-after')
    if value:
        try: waits.append(max(0, int(value)))
        except ValueError:
            try: waits.append(max(0, int(parsedate_to_datetime(value).timestamp() - instant) + 1))
            except (ValueError, TypeError, OverflowError): pass
    if headers.get('x-ratelimit-remaining') == '0':
        try: waits.append(max(0, int(headers.get('x-ratelimit-reset', '0')) - int(instant) + 1))
        except ValueError: pass
    return max(waits)  # Never retry earlier than GitHub's indicated time.


class Transport:
    def __init__(self):
        self.opener = build_opener(ProxyHandler({}), HTTPSHandler(context=ssl.create_default_context()), NoRedirect())

    def request(self, method, origin, path, *, token=None, params=None, body=None):
        if origin not in {'https://api.github.com', 'https://github.com'} or not path.startswith('/') or path.startswith('//') or any(c in path for c in '\\?#'):
            raise GitHubError('github_unsafe_endpoint')
        if origin == 'https://github.com' and (path != '/login/oauth/access_token' or method != 'POST'):
            raise GitHubError('github_unsafe_endpoint')
        if method != 'GET' and not (method == 'POST' and (path == '/login/oauth/access_token' or re.fullmatch(r'/app/installations/[1-9][0-9]*/access_tokens', path))):
            raise GitHubError('github_write_rejected')
        url = origin + path + ('?' + urlencode(params) if params else '')
        headers = {'Accept': 'application/vnd.github+json' if origin.endswith('api.github.com') else 'application/json',
                   'User-Agent': 'contribution-ledger/phase8', 'X-GitHub-Api-Version': API_VERSION,
                   'Accept-Encoding': 'identity'}
        if token: headers['Authorization'] = 'Bearer ' + token
        data = None
        if body is not None:
            data = json.dumps(body, separators=(',', ':')).encode()
            headers['Content-Type'] = 'application/json'
        deadline = AUTH_DEADLINE.get()
        remaining = deadline - time.monotonic() if deadline is not None else 12
        if remaining <= 0: raise GitHubError('github_authorization_timeout')
        try:
            response = self.opener.open(Request(url, data=data, headers=headers, method=method), timeout=min(12, remaining))
            with response:
                status = response.status
                received = {k.lower(): v for k, v in response.headers.items()}
                if received.get('content-encoding', 'identity') != 'identity':
                    raise GitHubError('github_response_encoding')
                raw = response.read(MAX_RESPONSE_BYTES + 1)
        except HTTPError as error:
            status = error.code
            received = {k.lower(): v for k, v in error.headers.items()}
            error.close()  # Do not reflect the remote error body.
            if status in {403, 429} and (status == 429 or 'retry-after' in received or received.get('x-ratelimit-remaining') == '0'):
                raise GitHubError('github_rate_limited', retry_delay(received)) from None
            if status == 403:
                # Could be a secondary limit without headers, or revoked permissions.
                raise GitHubError('github_forbidden', 60) from None
            if status in {401, 404}: raise GitHubError('github_access_denied') from None
            if 300 <= status < 400: raise GitHubError('github_redirect_rejected') from None
            if status >= 500: raise GitHubError('github_unavailable', 60) from None
            if status == 409: raise GitHubError('github_empty_or_conflicting_repository') from None
            raise GitHubError('github_request_rejected') from None
        except (URLError, TimeoutError, OSError):
            raise GitHubError('github_unavailable', 60) from None
        if len(raw) > MAX_RESPONSE_BYTES: raise GitHubError('github_response_too_large')
        try:
            document = json.loads(raw)
        except (ValueError, UnicodeError): raise GitHubError('github_invalid_response') from None
        if not isinstance(document, (dict, list)): raise GitHubError('github_invalid_response')
        # Never follow Link URLs: only inspect presence, then increment our own bounded page.
        has_next = 'rel="next"' in received.get('link', '')
        return document, has_next


def permissions_checked(document, app_id):
    if document.get('app_id') != app_id or document.get('suspended_at') is not None:
        raise GitHubError('github_installation_mismatch')
    permissions = document.get('permissions') or {}
    if any(permissions.get(k) != v for k, v in READ_PERMISSIONS.items()) or any(v not in {'read', 'none'} for v in permissions.values()):
        raise GitHubError('github_read_permissions_required')


def repo_descriptor(row):
    full_name = row.get('full_name', '')
    parts = full_name.split('/')
    if len(parts) != 2 or not all(REPO_PART.fullmatch(p) and p not in {'.', '..'} for p in parts):
        raise GitHubError('github_invalid_repository')
    rid = row.get('id')
    if type(rid) is not int or not 0 < rid <= 2**53-1: raise GitHubError('github_invalid_repository')
    return {'github_id': rid, 'full_name': full_name, 'private': bool(row.get('private', True)),
            'default_branch': str(row.get('default_branch') or '')[:200]}


class GitHubClient:
    def __init__(self, settings, secrets, transport=None):
        self.settings, self.secrets = settings, secrets
        self.transport = transport or Transport()

    def ensure_configured(self):
        if not self.settings.github_enabled: raise GitHubError('github_not_configured')

    def app_token(self):
        self.ensure_configured()
        return app_jwt(self.settings.github_client_id, self.secrets.read('github-private-key.pem'))

    def authorize_url(self, state):
        self.ensure_configured()
        _, challenge = pkce(self.secrets.read('github-client-secret'), state)
        params = {'client_id': self.settings.github_client_id, 'redirect_uri': self.settings.github_callback_url,
                  'state': state, 'code_challenge': challenge, 'code_challenge_method': 'S256', 'allow_signup': 'false'}
        return 'https://github.com/login/oauth/authorize?' + urlencode(params)

    def _pages(self, path, token, key, maximum=10):
        for page in range(1, maximum + 1):
            data, more = self.transport.request('GET', 'https://api.github.com', path, token=token,
                                                params={'page': page, 'per_page': 100})
            values = data.get(key) if isinstance(data, dict) else None
            if not isinstance(values, list): raise GitHubError('github_invalid_response')
            yield from values
            if not more: return
        raise GitHubError('github_authorization_catalog_limit')

    def verify_authorization(self, code, state, installation_id):
        # A per-context budget avoids mutating the client shared by requests.
        token = AUTH_DEADLINE.set(time.monotonic() + 60)
        try:
            return self._verify_authorization(code, state, installation_id)
        finally:
            AUTH_DEADLINE.reset(token)

    def _verify_authorization(self, code, state, installation_id):
        self.ensure_configured()
        secret = self.secrets.read('github-client-secret')
        verifier, _ = pkce(secret, state)
        tokens, _ = self.transport.request('POST', 'https://github.com', '/login/oauth/access_token', body={
            'client_id': self.settings.github_client_id, 'client_secret': secret.decode('ascii'),
            'code': code, 'redirect_uri': self.settings.github_callback_url, 'code_verifier': verifier})
        token = tokens.get('access_token') if isinstance(tokens, dict) else None
        if not isinstance(token, str) or not token or tokens.get('error'): raise GitHubError('github_authorization_failed')
        # Tokens (including refresh tokens) are deliberately not persisted or returned.
        user, _ = self.transport.request('GET', 'https://api.github.com', '/user', token=token)
        if type(user.get('id')) is not int: raise GitHubError('github_invalid_response')
        installation = next((i for i in self._pages('/user/installations', token, 'installations') if i.get('id') == installation_id), None)
        if not installation: raise GitHubError('github_installation_not_authorized')
        permissions_checked(installation, self.settings.github_app_id)
        repositories = []
        for row in self._pages(f'/user/installations/{installation_id}/repositories', token, 'repositories'):
            # Stricter than GitHub read access: sharing private data with a local team
            # requires the authorizing GitHub account to administer the repository.
            if (row.get('permissions') or {}).get('admin') is True:
                repositories.append(repo_descriptor(row))
        if not repositories: raise GitHubError('github_repository_admin_required')
        actual, _ = self.transport.request('GET', 'https://api.github.com', f'/app/installations/{installation_id}', token=self.app_token())
        permissions_checked(actual, self.settings.github_app_id)
        return {'github_user_id': user['id'], 'github_login': str(user.get('login') or '')[:100],
                'installation_id': installation_id, 'account': str((actual.get('account') or {}).get('login') or '')[:100],
                'repositories': sorted(repositories, key=lambda r: r['github_id'])}

    def repository_token(self, installation_id, repository_id):
        token = self.app_token()
        installation, _ = self.transport.request('GET', 'https://api.github.com', f'/app/installations/{installation_id}', token=token)
        permissions_checked(installation, self.settings.github_app_id)
        result, _ = self.transport.request('POST', 'https://api.github.com', f'/app/installations/{installation_id}/access_tokens',
            token=token, body={'repository_ids': [repository_id], 'permissions': READ_PERMISSIONS})
        if not isinstance(result.get('token'), str) or not result['token']: raise GitHubError('github_invalid_response')
        if any(result.get('permissions', {}).get(k) != v for k, v in READ_PERMISSIONS.items()):
            raise GitHubError('github_read_permissions_required')
        return result['token']

    def check_repository_authority(self, token, repo, connection):
        # Recheck the actual sharing principal before AND after each checkpoint.
        # A reused login belonging to another numeric ID is not the same principal.
        if not REPO_PART.fullmatch(connection.github_login):
            raise GitHubError('github_authority_revoked')
        data, _ = self.get(token, '/repos/' + repo.full_name + '/collaborators/' + connection.github_login + '/permission')
        if (not isinstance(data,dict) or data.get('permission') != 'admin'
            or not isinstance(data.get('user'),dict)
            or type(data['user'].get('id')) is not int
            or data['user']['id'] != connection.github_user_id):
            raise GitHubError('github_authority_revoked')

    def get(self, token, path, params=None):
        return self.transport.request('GET', 'https://api.github.com', path, token=token, params=params)
