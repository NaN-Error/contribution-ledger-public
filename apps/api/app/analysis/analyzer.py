"""Bounded, source-cited draft interpretation, never an automatic unit scorer.

Numeric GitHub identities are combined across repositories. Email/coauthor
claims remain separate until an explicit correction; a committer or merger is
not assumed to own an outcome. All repository text remains inert data.
"""
from collections import Counter
from hashlib import sha256
from types import SimpleNamespace
from app.contributions.reconstruction.grouping import groups, group_title
from app.integrations.github.normalization import canonical, text

ALGORITHM = 'repository-outcomes-v3'
RUBRIC = {
    'version': 'outcome-review-v1',
    'name': 'Team-proposed outcome units',
    'criteria': ['Describe the useful outcome and scope.', 'Cite evidence of completion and limitations.',
                 'Explain the proposed budget relative to other outcomes.',
                 'Identify contributors, non-code work and possible overlap.'],
    'notice': 'No units are inferred from commits, lines changed, activity volume or personal worth. '
              'Draft proposals require a reason and separate independent acceptance in the ledger.'}


def source_id(doc):
    return sha256(canonical(doc)).hexdigest()


def source_url(doc, parent_kind=None):
    base = 'https://github.com/' + doc['repository']['full_name']
    kind, key = doc['kind'], doc['remote_key']
    if kind == 'commit': return base + '/commit/' + key
    if kind == 'pull_request': return base + '/pull/' + key
    if kind == 'issue': return base + '/issues/' + key
    c = doc['content']
    parent = c.get('pull_number') or c.get('parent_issue_or_pull')
    if parent: return base + ('/issues/' if parent_kind=='issue' else '/pull/') + str(parent)
    if c.get('commit_sha'): return base + '/commit/' + c['commit_sha']
    return base


def synthesize(connected, paths):
    """Explain captured claims/status/scope with citations, without inventing impact.

    Source prose stays quoted inert data. Repository status and review metadata
    do not establish correctness, team acceptance, labor hours or unit value.
    """
    ordered = sorted(connected,key=lambda s:({'pull_request':0,'issue':1,'commit':2}.get(s.kind,3),s.remote_key))
    primary = next((s for s in ordered if s.kind in {'pull_request','issue','commit'}),ordered[0])
    c = primary.document['content']; description = text(' '.join((c.get('body') or c.get('message') or '').split()),600)
    objective = {'label':'Stated goal','text':f'Captured {primary.kind.replace("_"," ")} description: “{description}”' if description else 'No work description was present in this source.',
        'source_ids':[str(primary.id)]}
    states = []; state_sources = []
    for s in ordered:
        content = s.document['content']
        if s.kind=='pull_request':
            state = 'merged' if content.get('merged') is True or content.get('merged_at') else content.get('state') or 'status not recorded'
            states.append(f'Pull request #{s.remote_key}: {state}')
        elif s.kind=='issue':states.append(f'Issue #{s.remote_key}: {content.get("state") or "status not recorded"}')
        else:continue
        state_sources.append(str(s.id))
    status = {'label':'Repository status','text':('; '.join(states[:6]) if states else 'Commit/discussion evidence was captured; delivery status is not established.')+
        '. Repository closure or merging is separate from team acceptance.', 'source_ids':state_sources[:6] or [str(primary.id)]}
    file_sources = [str(s.id) for s in ordered if s.document['content'].get('files')]
    scope = {'label':'Captured file scope','text':f'{len(paths)} distinct captured paths: '+', '.join(text(p,120) for p in paths[:6])+(' …' if len(paths)>6 else '')+
        '. File paths describe observed scope, not effort or economic value.' if paths else 'No changed-file artifact was captured. Missing or binary patches are not evidence of zero work.',
        'source_ids':file_sources[:6]}
    findings = [objective,status,scope]
    reviews = [s for s in ordered if s.kind=='review']
    if reviews:
        states = Counter(s.document['content'].get('state') or 'state not recorded' for s in reviews)
        findings.append({'label':'Review evidence','text':'; '.join(f'{n} {state.replace("_"," ").lower()}' for state,n in sorted(states.items()))+
            '. Review records do not prove the implementation is correct or independently accepted by this team.', 'source_ids':[str(s.id) for s in reviews[:6]]})
    checks = [s for s in ordered if s.kind in {'check_run','commit_status'}]
    if checks:
        findings.append({'label':'Reported checks','text':'; '.join(text(s.document['content'].get('name') or s.document['content'].get('context') or 'Unnamed check',100)+': '+
            text(s.document['content'].get('conclusion') or s.document['content'].get('state') or s.document['content'].get('status') or 'unknown',50) for s in checks[:6])+
            '. Captured metadata only; logs were not fetched and checks were not run.', 'source_ids':[str(s.id) for s in checks[:6]]})
    return findings


def contributor_summary(key, outcomes):
    """Contributor-specific work titles, with role distinctions and outcome links."""
    labels = [('Manual contribution',{'manual contribution'}),('Authorship reported by GitHub',{'commit_author','pull_request_author'}),
        ('Review evidence',{'reviewer'}),('Issues and discussion',{'issue_author','comment_author'}),
        ('Integration activity',{'commit_committer','merger_not_assumed_author'}),
        ('Unverified commit attribution',{'git_author_claim','git_committer_claim','co_author_claim'})]
    grouped = {}
    for outcome in outcomes:
        roles = {role for p in outcome['contributors'] if p['key']==key for role in p['roles']}
        proposed = outcome.get('proposal') and any(e['contributor_key']==key for e in outcome['proposal']['entries'])
        if not roles and not proposed:continue
        label = next((label for label,allowed in labels if roles & allowed),'Proposed attribution')
        grouped.setdefault(label,[]).append({'label':label,'title':outcome['title'],'outcome_id':outcome['id']})
    if not grouped:return 'No contribution outcome is included for this identity in the selected report.',[]
    order = [label for label,_ in labels]+['Proposed attribution']
    groups_present = [grouped[label] for label in order if label in grouped]
    highlights = [entries[0] for entries in groups_present][:5]
    for entries in groups_present:
        for entry in entries[1:]:
            if len(highlights)<5:highlights.append(entry)
    summary = '. '.join(entries[0]['label']+': '+ '; '.join(text(e['title'],120) for e in entries[:2])+(' and other outcomes' if len(entries)>2 else '') for entries in groups_present[:2])
    return summary+'. Completion and attribution still require review.',highlights


def analyze(documents, repositories, definition, omissions):
    # Entity keys deduplicate repeated imports; newest captured representation wins.
    entities = {}
    for doc in documents:
        entities[(doc['repository']['github_id'], doc['kind'], doc['remote_key'])] = doc
    docs = list(entities.values())
    sources = [SimpleNamespace(id=source_id(d), kind=d['kind'], remote_key=d['remote_key'], document=d) for d in docs]
    people, outcomes = {}, []
    for source in sources:
        if source.document.get('context_only'): continue
        for identity in source.document['identities']:
            key = identity['external_key']
            p = people.setdefault(key, {'key': key, 'name': identity['label'], 'kind': identity['kind'],
                'username': identity['label'] if identity['kind'] in {'github_user','github_bot'} else None,
                'repositories': set(), 'roles': set()})
            p['repositories'].add(source.document['repository']['full_name']); p['roles'].add(identity['role'])
    for connected in groups(sources):
        primary = [s for s in connected if s.kind in {'pull_request','issue','commit','review','comment','review_comment'}]
        if not primary: continue
        if not any(not s.document.get('context_only') for s in primary): continue
        ids = sorted(str(s.id) for s in connected)
        # Stable across reruns/changed source representations; proposals bind a separate evidence fingerprint.
        entity_ids = sorted(f"{s.document['repository']['github_id']}:{s.kind}:{s.remote_key}" for s in connected)
        oid = sha256('|'.join(entity_ids).encode()).hexdigest()
        title = group_title(primary)
        paths = sorted({f['filename'] for s in connected for f in s.document['content'].get('files', [])})
        low = (title + ' ' + ' '.join(paths)).lower()
        category = ('testing' if any(x in low for x in ('test','spec/','qa ')) else
                    'documentation' if any(x in low for x in ('readme','docs/','documentation')) else
                    'art' if any(x in low for x in ('.png','.svg','.blend','texture','sprite')) else 'code')
        roles = {}
        for s in connected:
            if s.document.get('context_only'): continue
            for i in s.document['identities']:
                roles.setdefault(i['external_key'], set()).add(i['role'])
        parent_kinds = {(s.document['repository']['github_id'],s.remote_key):s.kind for s in connected if s.kind in {'pull_request','issue'}}
        refs = [{'id': str(s.id), 'kind': s.kind, 'repository': s.document['repository']['full_name'],
                 'url': source_url(s.document,parent_kinds.get((s.document['repository']['github_id'],str(s.document['content'].get('pull_number') or s.document['content'].get('parent_issue_or_pull'))))), 'title': group_title([s]),
                 'excerpt': text(s.document['content'].get('body') or s.document['content'].get('message') or '', 2000),
                 'content_hash': str(s.id), 'omissions': s.document['omissions'],
                 'context_only':bool(s.document.get('context_only')),
                 'recorded_times':{k:v for k,v in s.document['content'].items() if v and k in {
                     'created_at','updated_at','closed_at','merged_at','submitted_at','git_author_date','git_committer_date'}}} for s in connected]
        findings = synthesize(connected,paths)
        outcomes.append({'id': oid, 'evidence_hash': sha256('|'.join(ids).encode()).hexdigest(),
            'title': title, 'category': category, 'origin': 'github',
            'summary': findings[0]['text']+' '+findings[1]['text'], 'findings':findings,
            'repositories': sorted({s.document['repository']['full_name'] for s in connected}),
            'contributors': [{'key': k, 'roles': sorted(v)} for k,v in sorted(roles.items())],
            'files': paths[:100], 'sources': refs,
            'limitations': ['Completion, impact and attribution require human review.',
                'Structured relationships are grouping hints; separate changes may represent the same work.']})
        if any(s.document.get('context_only') for s in connected):
            outcomes[-1]['limitations'].append('Parent metadata provides context for related activity within the selected period; its older authorship is not counted as work in this report.')
    commit_repositories = {}
    for d in docs:
        if d['kind']=='commit': commit_repositories.setdefault(d['remote_key'],set()).add(d['repository']['full_name'])
    overlapping = {sha:repos for sha,repos in commit_repositories.items() if len(repos)>1}
    for outcome in outcomes:
        for s in outcome['sources']:
            if s['kind']=='commit':
                remote_key = next(d['remote_key'] for d in docs if source_id(d)==s['id'])
                if remote_key in overlapping:
                    outcome['limitations'].append('Possible shared commit across repositories: '+remote_key+'; review overlap before proposing separate units.')
    contributors = [{**p, 'repositories': sorted(p['repositories']), 'roles': sorted(p['roles'])} for p in people.values()]
    return {'algorithm': ALGORITHM, 'rubric': RUBRIC, 'scope': definition,
        'repositories': repositories, 'contributors': sorted(contributors, key=lambda p:(p['name'].casefold(),p['key'])),
        'outcomes': sorted(outcomes, key=lambda o:(o['title'].casefold(),o['id'])),
        'omissions': list(dict.fromkeys(omissions))[:300], 'source_count': len(sources),
        'notice': 'Draft source analysis. No repository code was executed, model called, units awarded or payment created.'}
