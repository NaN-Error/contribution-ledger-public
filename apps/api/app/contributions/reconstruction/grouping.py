"""Deterministic relationship hints, not AI judgments or economic valuations.

Only captured structured relationships are considered. Repository text/URLs are
never interpreted as instructions, fetched, or used to allocate units.
"""
from hashlib import sha256


def entity_key(source):
    doc=source.document
    raw=f"github:{doc['repository']['github_id']}:{source.kind}:{source.remote_key}"
    return sha256(raw.encode()).hexdigest()


def groups(sources):
    ordered=sorted(sources,key=lambda s:(str(s.document['repository']['github_id']),s.kind,s.remote_key,str(s.id)))
    parent={str(s.id):str(s.id) for s in ordered}
    lookup={(s.document['repository']['github_id'],s.kind,s.remote_key):str(s.id) for s in ordered}
    def root(k):
        while parent[k]!=k:
            parent[k]=parent[parent[k]];k=parent[k]
        return k
    def connect(k,other):
        if other:parent[root(k)]=root(other)
    for s in ordered:
        repo=s.document['repository']['github_id'];c=s.document['content'];sid=str(s.id)
        pull=c.get('pull_number') or c.get('parent_issue_or_pull')
        if pull:
            connect(sid,lookup.get((repo,'pull_request',str(pull))) or lookup.get((repo,'issue',str(pull))))
        sha=c.get('commit_sha') or (c.get('head_sha') if s.kind in {'check_run','commit_status'} else None)
        if sha:connect(sid,lookup.get((repo,'commit',sha)))
        if s.kind=='pull_request':
            for sha in [c.get('merge_commit_sha'),(c.get('head') or {}).get('sha')]:
                if sha:connect(sid,lookup.get((repo,'commit',sha)))
    result={}
    for s in ordered:result.setdefault(root(str(s.id)),[]).append(s)
    return list(result.values())


def group_title(sources):
    priority={'pull_request':0,'issue':1,'commit':2}
    s=min(sources,key=lambda x:(priority.get(x.kind,3),x.remote_key))
    c=s.document['content']
    text=c.get('title') or (c.get('message') or '').split('\n')[0] or f'{s.kind} {s.remote_key}'
    return (str(text).replace('\n',' ')[:120].strip() or 'Imported work candidate')
