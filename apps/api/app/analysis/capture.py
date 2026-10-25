"""Credential-free fixed-origin public reads; persisted one-request checkpoints.

Uses the existing no-redirect, no-proxy, size/time-bounded transport. Imported
code, links and API response URLs are never executed or followed. A tree supplies
context only; it does not establish historical authorship or completion.
"""
import base64
from datetime import datetime, timezone
from types import SimpleNamespace
from urllib.parse import quote
from app.integrations.github.client import Transport, GitHubError, repo_descriptor
from app.integrations.github.normalization import normalize, sha, text, canonical

MAX_REQUESTS = 64
MAX_SOURCES = 500
MAX_BYTES = 2 * 1024 * 1024
READABLE = {'readme.md','readme.txt','package.json','pyproject.toml','project.godot'}


class PublicRepositoryClient:
    def __init__(self, transport=None): self.transport = transport or Transport()

    def get(self, path, params=None):
        return self.transport.request('GET', 'https://api.github.com', path, params=params)


def initial(names):
    return {'tasks': [{'repository': n, 'kind': 'repository', 'page': 1} for n in names],
            'cursor': 0, 'requests': 0, 'sources': [], 'repositories': [], 'omissions': []}


def repo_for(progress, name):
    return next(r for r in progress['repositories'] if r['full_name'].casefold() == name.casefold())


def request_for(progress, task, definition):
    base = '/repos/' + task['repository']; kind = task['kind']
    page = {'per_page': 20, 'page': task.get('page', 1)}
    if kind == 'repository': return base, None
    if kind == 'anchor': return base + '/commits', {'per_page':1, 'sha':repo_for(progress, task['repository'])['default_branch']}
    repo = repo_for(progress, task['repository'])
    if kind == 'commits': return base + '/commits', {**page, 'sha':repo['anchor_sha'], 'since':definition['start_at'], 'until':definition['end_before']}
    if kind == 'pulls': return base + '/pulls', {**page,'state':'all','sort':'created','direction':'desc'}
    if kind == 'issues': return base + '/issues', {**page,'state':'all','sort':'created','direction':'desc','since':definition['start_at']}
    if kind == 'tree': return base + '/git/trees/' + repo['anchor_sha'], {'recursive':'1'}
    subject = task['subject']
    if kind == 'commit': return base + '/commits/' + subject, None
    if kind == 'pull_commits': return base + '/pulls/' + subject + '/commits', page
    if kind == 'reviews': return base + '/pulls/' + subject + '/reviews', page
    if kind == 'comments': return base + '/issues/' + subject + '/comments', page
    if kind == 'content': return base + '/contents/' + quote(subject, safe='/'), {'ref':repo['anchor_sha']}
    raise GitHubError('analysis_unknown_task')


def in_window(value, definition):
    try:
        date = datetime.fromisoformat(value.replace('Z','+00:00'))
        start = datetime.fromisoformat(definition['start_at']); end = datetime.fromisoformat(definition['end_before'])
        return date.tzinfo is not None and start <= date < end
    except (ValueError, TypeError, AttributeError): return False


def created_after_window(value, definition):
    try:
        date = datetime.fromisoformat(value.replace('Z','+00:00'))
        return date.tzinfo is not None and date >= datetime.fromisoformat(definition['end_before'])
    except (ValueError, TypeError, AttributeError): return False


def absorb(progress, task, raw, more, definition):
    name, kind = task['repository'], task['kind']
    omissions = progress['omissions']
    # One calculation per checkpoint, rather than reserializing every prior source
    # for each row in a page. Older persisted checkpoints need no migration.
    source_bytes = sum(len(canonical(d)) for d in progress['sources'])
    def omit(message):
        value = name + ':' + message
        if value not in omissions and len(omissions) < 300: omissions.append(value)
    def schedule(kind, **extra):
        value = {'repository':name, 'kind':kind, 'page':1, **extra}
        if value not in progress['tasks'] and len(progress['tasks']) < 500: progress['tasks'].append(value)
    if kind == 'repository':
        if not isinstance(raw, dict) or type(raw.get('private')) is not bool: raise GitHubError('github_invalid_response')
        if raw['private'] and not definition.get('connection_id'): raise GitHubError('analysis_public_repository_required')
        descriptor = repo_descriptor(raw)
        if descriptor['full_name'].casefold() != name.casefold(): raise GitHubError('analysis_repository_identity_changed')
        descriptor.update(description=text(raw.get('description'),1000), anchor_sha=None,
            latest_commit_at=None, tree_paths=[], context=[])
        progress['repositories'].append(descriptor); schedule('anchor')
        return
    repo = repo_for(progress, name); descriptor = SimpleNamespace(**repo)
    if kind == 'anchor':
        if not isinstance(raw,list): raise GitHubError('github_invalid_response')
        if not raw:
            repo['history_unavailable']=True
            omit('commit_history_unavailable_or_empty'); return
        repo['anchor_sha'] = sha(raw[0].get('sha'))
        # Context for choosing a useful period; never count out-of-window authorship.
        value = ((raw[0].get('commit') or {}).get('committer') or {}).get('date')
        try:
            date = datetime.fromisoformat(value.replace('Z', '+00:00'))
            if date.tzinfo is None or not 1970 <= date.year <= 2099: raise ValueError()
            repo['latest_commit_at'] = date.astimezone(timezone.utc).isoformat()
        except (ValueError, TypeError, AttributeError):
            omit('anchor_commit_date_unavailable')
        for k in ('commits','pulls','issues','tree'): schedule(k)
        return
    def store(source_kind, value, remote_key=None, extra=None, context_only=False):
        nonlocal source_bytes
        doc = normalize(source_kind, value, descriptor, remote_key=remote_key, extra=extra)
        if context_only:
            doc['context_only'] = True
            doc['omissions'].append('parent_metadata_is_context_not_in_window_authorship')
        updated = doc['content'].get('updated_at')
        if updated:
            try:
                if datetime.fromisoformat(updated.replace('Z','+00:00')) >= datetime.fromisoformat(definition['end_before']):
                    doc['omissions'].append('current_representation_updated_after_selected_window')
            except (ValueError,TypeError): pass
        if source_kind == 'commit':
            for previous in reversed(progress['sources']):
                if previous['repository']['github_id']==repo['github_id'] and previous['kind']=='commit' and previous['remote_key']==doc['remote_key']:
                    if 'pull_number' in previous['content']:
                        doc['content'].setdefault('pull_number',previous['content']['pull_number'])
                    break
        if len(progress['sources']) >= MAX_SOURCES:
            omit('source_limit'); return
        doc_bytes = len(canonical(doc))
        if source_bytes + doc_bytes > MAX_BYTES:
            omit('source_bytes_limit'); return
        progress['sources'].append(doc)
        source_bytes += doc_bytes
        for limitation in doc['omissions']: omit(source_kind + ':' + limitation)
    if kind == 'tree':
        if not isinstance(raw,dict) or not isinstance(raw.get('tree'),list): raise GitHubError('github_invalid_response')
        paths = [text(r.get('path'),500) for r in raw['tree'][:1000] if r.get('type') == 'blob' and r.get('mode') != '120000']
        repo['tree_paths'] = paths
        if raw.get('truncated') or len(raw['tree']) > 1000: omit('tree_paths_truncated')
        for path in paths:
            # Root allowlist, not arbitrary repository-controlled file selection.
            if '/' not in path and path.lower() in READABLE: schedule('content', subject=path)
        return
    if kind == 'content':
        if not isinstance(raw,dict) or raw.get('type') != 'file' or raw.get('encoding') != 'base64' or type(raw.get('size')) is not int or not 0 <= raw['size'] <= 16000:
            omit('context_file_unavailable_or_oversized'); return
        try:
            data = base64.b64decode(''.join(str(raw.get('content','')).split()), validate=True)
            if len(data) > 16000: raise ValueError()
            value = data.decode('utf-8')
        except (ValueError, UnicodeError):
            omit('context_file_not_utf8'); return
        notes = []
        repo['context'].append({'path':task['subject'], 'text':text(value,8000,notes,'context'),
            'sha':text(raw.get('sha'),64), 'anchor_sha':repo['anchor_sha']})
        for note in notes: omit(note)
        return
    if kind == 'commit':
        if not isinstance(raw,dict) or raw.get('sha') != task['subject']: raise GitHubError('github_invalid_response')
        store('commit',raw)
        store('commit_files', {'files':raw.get('files',[])}, remote_key=task['subject'], extra={'commit_sha':task['subject']})
        if more: omit('commit_files_not_fully_paginated')
        return
    if not isinstance(raw,list): raise GitHubError('github_invalid_response')
    if len(raw) > 20: omit(kind + ':response_row_limit')
    for row in raw[:20]:
        if not isinstance(row,dict): raise GitHubError('github_invalid_response')
        if kind in {'commits','pull_commits'}:
            if not in_window(((row.get('commit') or {}).get('committer') or {}).get('date'),definition): continue
            extra = {'pull_number':int(task['subject'])} if kind == 'pull_commits' else None
            store('commit', row, extra=extra); schedule('commit',subject=sha(row.get('sha')))
        elif kind in {'pulls','issues'}:
            if kind == 'issues' and 'pull_request' in row: continue
            context_only = not any(in_window(row.get(k), definition) for k in ('created_at','closed_at','merged_at'))
            if context_only and created_after_window(row.get('created_at'),definition): continue
            source_kind = 'pull_request' if kind == 'pulls' else 'issue'
            # Older parents can contain reviews/comments performed in this window,
            # even when their current updated_at is later. Their metadata provides
            # context; it does not credit the old author's work to this period.
            store(source_kind,row,context_only=context_only); subject = str(row.get('number'))
            schedule('comments', subject=subject)
            if kind == 'pulls':
                schedule('reviews',subject=subject); schedule('pull_commits',subject=subject)
        elif kind in {'reviews','comments'}:
            if not in_window(row.get('submitted_at') or row.get('created_at'),definition): continue
            store('review' if kind == 'reviews' else 'comment',row,extra={'parent_issue_or_pull':int(task['subject'])})
    if more:
        # Parent pages need explicit bounds; child metadata retains visible omissions.
        if kind in {'commits','pulls','issues'} and task.get('page',1) < 3:
            schedule(kind,page=task['page']+1)
        else: omit(kind + ':pagination_limit')
