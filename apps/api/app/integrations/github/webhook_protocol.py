"""Strict raw-body signature validation and bounded, content-free routing.

GitHub signs the body, not routing headers. Body hashes are independently deduped;
header changes on a replay cannot select new work. No URL in a payload is fetched.
"""
from dataclasses import dataclass
from hashlib import sha256
import hmac
import json
import re
from uuid import UUID
from app.core.errors import ApiError

MAX_WEBHOOK_BYTES = 1048576
WEBHOOK_PATH = '/api/v1/github/webhook'
EVENTS = {
    'ping': {''},
    'push': {''},
    'issues': {'opened','edited','deleted','closed','reopened','transferred','assigned','unassigned','labeled','unlabeled','milestoned','demilestoned','locked','unlocked','typed','untyped'},
    'issue_comment': {'created','edited','deleted'},
    'pull_request': {'opened','edited','closed','reopened','synchronize','ready_for_review','converted_to_draft','assigned','unassigned','labeled','unlabeled','review_requested','review_request_removed','locked','unlocked','auto_merge_enabled','auto_merge_disabled','enqueued','dequeued','milestoned','demilestoned'},
    'pull_request_review': {'submitted','edited','dismissed'},
    'pull_request_review_comment': {'created','edited','deleted'},
    'check_run': {'created','completed','rerequested','requested_action'},
    'check_suite': {'completed','requested','rerequested'},
    'installation': {'created','deleted','suspend','unsuspend','new_permissions_accepted'},
    'installation_repositories': {'added','removed'},
    'repository': {'archived','unarchived','created','deleted','edited','renamed','transferred','privatized','publicized'},
}


def invalid(code='github_invalid_webhook'):
    return ApiError(400, code, 'The signed webhook has an unsupported or invalid shape.')


def identifier(value):
    if type(value) is not int or not 0 < value <= 2**53-1:
        raise invalid()
    return value


def object_value(value):
    if not isinstance(value, dict): raise invalid()
    return value


def unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result: raise invalid('github_duplicate_json_key')
        result[key] = value
    return result


@dataclass(frozen=True)
class Envelope:
    delivery_key: str
    payload_hash: str
    body_bytes: int
    event: str
    action: str
    installation_id: int
    repository_ids: tuple[int, ...]
    targets: tuple[dict, ...]
    revoke: str | None
    supported: bool


def parse_signed(raw: bytes, headers: list[tuple[bytes, bytes]], secret: bytes, app_id: int) -> Envelope:
    if not 2 <= len(raw) <= MAX_WEBHOOK_BYTES:
        raise ApiError(413, 'github_webhook_size', 'The webhook exceeds the bounded intake size.')
    security = {b'x-hub-signature-256', b'x-github-delivery', b'x-github-event', b'content-type', b'content-length', b'content-encoding'}
    values = {}
    for key, value in headers:
        key = key.lower()
        if key in security and key in values: raise invalid('github_ambiguous_webhook_headers')
        values[key] = value
    signature = values.get(b'x-hub-signature-256', b'')
    expected = b'sha256=' + hmac.new(secret, raw, sha256).hexdigest().encode('ascii')
    if len(secret) < 32 or not hmac.compare_digest(signature, expected):
        raise ApiError(401, 'github_signature_rejected', 'Webhook signature validation failed.')
    try:
        delivery = values[b'x-github-delivery'].decode('ascii')
        if str(UUID(delivery)) != delivery.lower(): raise ValueError()
        event = values[b'x-github-event'].decode('ascii')
        if not re.fullmatch(r'[a-z_]{1,60}', event): raise ValueError()
        data = json.loads(raw.decode('utf-8'), object_pairs_hook=unique_keys,
                          parse_constant=lambda _: (_ for _ in ()).throw(invalid()))
    except (ValueError, UnicodeError, KeyError, RecursionError):
        raise invalid() from None
    data = object_value(data)
    action = data.get('action', '')
    if not isinstance(action, str) or not re.fullmatch(r'[a-z_]{0,60}', action): raise invalid()
    if event == 'ping':
        hook = object_value(data.get('hook'))
        if hook.get('type') != 'App': raise invalid()
        if 'app_id' in hook and identifier(hook['app_id']) != app_id: raise invalid()
        installation = 0
    else:
        installation_object=object_value(data.get('installation'))
        installation = identifier(installation_object.get('id'))
        if event in {'installation','installation_repositories'}:
            # Event headers are not HMAC-signed. An ordinary issue/PR event cannot
            # be relabelled as a global revocation even on its first delivery.
            if identifier(installation_object.get('app_id')) != app_id: raise invalid()
            if any(k in data for k in ('repository','issue','pull_request','comment','check_run','check_suite')): raise invalid()
        if event == 'repository' and any(k in data for k in ('issue','pull_request','comment','check_run','check_suite')):
            raise invalid()
    repos = ()
    if data.get('repository') is not None:
        repos = (identifier(object_value(data['repository']).get('id')),)
    supported = event in EVENTS and action in EVENTS[event]
    revoke = None
    targets = []
    if supported:
        if event == 'installation' and action in {'deleted','suspend','new_permissions_accepted'}:
            revoke = 'github_installation_' + action
        elif event == 'installation_repositories' and action == 'removed':
            removed = data.get('repositories_removed')
            if not isinstance(removed, list) or len(removed) > 1000: raise invalid()
            repos = tuple(sorted({identifier(object_value(r).get('id')) for r in removed}))
            revoke = 'github_repository_removed'
        elif event == 'repository' and action in {'deleted','transferred','renamed','privatized'}:
            if not repos: raise invalid()
            revoke = 'github_repository_' + action
        elif event.startswith('pull_request'):
            if not repos: raise invalid()
            targets = [{'kind':'pull','subject':str(identifier(object_value(data.get('pull_request')).get('number')))}]
        elif event in {'issues','issue_comment'}:
            if not repos: raise invalid()
            issue = object_value(data.get('issue'))
            targets = [{'kind':'pull' if 'pull_request' in issue else 'issue','subject':str(identifier(issue.get('number')))}]
        elif event in {'check_run','check_suite'}:
            if not repos: raise invalid()
            check = object_value(data.get(event))
            commit = check.get('head_sha')
            if not isinstance(commit,str) or not re.fullmatch(r'[0-9a-f]{40}|[0-9a-f]{64}',commit): raise invalid()
            targets = [{'kind':'checks','subject':commit}]
            pulls = check.get('pull_requests', [])
            if not isinstance(pulls,list) or len(pulls)>100: raise invalid()
            for pull in pulls[:20]:
                targets.append({'kind':'pull','subject':str(identifier(object_value(pull).get('number')))})
        elif event == 'push':
            if not repos or not isinstance(data.get('ref'),str): raise invalid()
            # Do not trust hundreds of inline commits; refresh API state and its anchor.
            targets = [{'kind':'reconcile','subject':''}]
        elif event == 'repository' and repos:
            targets = [{'kind':'reconcile','subject':''}]
    return Envelope(delivery.lower(),sha256(raw).hexdigest(),len(raw),event,action,
                    installation,repos,tuple(targets),revoke,supported)
