from copy import deepcopy
from datetime import timedelta
from hashlib import sha256
from uuid import UUID, uuid4
from sqlalchemy import select, func, cast, String, true
from app.core.errors import ApiError
from app.projects.authorization import project_access, not_found
from app.auth.models import User
from app.policies.service import digest
from app.security.tokens import now, utc
from app.security.audit import audit
from app.integrations.github.models import GitHubImport, GitHubRepository, GitHubSourceVersion, GitHubObservation
from app.integrations.github.client import GitHubError
from app.integrations.github.normalization import canonical, text
from app.finance.calculation.engine import largest_remainder
from app.reporting.service import dashboard as recognized_dashboard
from .models import RepositoryAnalysis, AnalysisDraft, AnalysisDraftRevision
from .schemas import repository_name, KEY, MAX_ATOMS
from .capture import initial, request_for, absorb, MAX_REQUESTS, MAX_SOURCES, MAX_BYTES
from .analyzer import analyze, RUBRIC, contributor_summary
from . import connections


def access(db, wid, pid, actor, *, manage=False, lock=False):
    project, role = project_access(db, wid, pid, actor, manage=manage, lock=lock)
    if role not in {'admin','reviewer'}:
        raise ApiError(403,'analysis_source_access','Draft repository reports are available to project administrators and reviewers. Recognized contributions remain available in Contribution overview.')
    return project, role


def run_in_project(db, project, rid, *, lock=False):
    q = select(RepositoryAnalysis).where(RepositoryAnalysis.id == rid,
        RepositoryAnalysis.project_id == project.id, RepositoryAnalysis.workspace_id == project.workspace_id)
    if lock: q = q.with_for_update().execution_options(populate_existing=True)
    row = db.scalar(q)
    if not row: raise not_found()
    return row


def run_view(row, *, full=False):
    p = row.progress
    value = {'id':str(row.id), 'state':row.state, 'version':row.version, 'definition':row.definition,
        'created_at':row.created_at, 'finished_at':row.finished_at, 'error_code':row.error_code,
        'retry_after':row.retry_after, 'requests':p['requests'], 'completed_tasks':p['cursor'],
        'total_tasks':len(p['tasks']), 'source_count':len(p['sources']), 'omissions':p['omissions']}
    if full: value['report'] = row.report
    return value


def complete(row, progress):
    omissions = progress['omissions'] + ['Unobserved branches, binary assets and off-repository work may be missing.',
        'Repository context is the pinned default-branch snapshot at capture time, not a historical checkout.']
    row.report = analyze(progress['sources'], progress['repositories'], row.definition, omissions)
    row.state = 'completed'; row.finished_at = now(); row.error_code = None
    row.progress = progress; row.lease_token = None; row.lease_until = None; row.version += 1


def create_run(db, project, actor, body, settings):
    definition = body.model_dump(mode='json', exclude={'request_id','public_read_confirmed'}, exclude_none=True)
    fingerprint = digest(definition)
    previous = db.scalar(select(RepositoryAnalysis).where(RepositoryAnalysis.project_id==project.id, RepositoryAnalysis.request_id==body.request_id))
    if previous:
        if previous.request_hash != fingerprint or previous.created_by != actor:
            raise ApiError(409,'idempotency_conflict','This request ID belongs to a different analysis.')
        return previous
    if utc(body.end_before) > now(): raise ApiError(422,'analysis_future_range','The analysis end must be in the past or present.')
    if body.connection_id:
        connections.checked(db,project,actor,body.connection_id,settings,
            names=[repository_name(u) for u in body.repository_urls],lock=True)
    elif body.repository_urls and not settings.repository_public_reads_enabled:
        raise ApiError(409,'analysis_public_reads_disabled','The operator disabled public repository reads. Use completed authorized imports.')
    backoff = db.scalar(select(RepositoryAnalysis.id).where(RepositoryAnalysis.project_id==project.id, RepositoryAnalysis.retry_after > now()))
    if body.repository_urls and backoff: raise ApiError(429,'analysis_backoff','A repository request is cooling down. Wait for the recorded retry time.')
    if db.scalar(select(func.count()).select_from(RepositoryAnalysis).where(RepositoryAnalysis.project_id==project.id)) >= 200:
        raise ApiError(409,'analysis_history_limit','This project reached the 200-report pilot history limit.')
    if db.scalar(select(RepositoryAnalysis.id).where(RepositoryAnalysis.project_id==project.id, RepositoryAnalysis.state.in_(['queued','running']))):
        raise ApiError(409,'analysis_active','Finish or cancel the active analysis before starting another.')
    p = initial([repository_name(u) for u in body.repository_urls]); imported_repos = set()
    for iid in body.import_ids:
        job = db.scalar(select(GitHubImport).where(GitHubImport.id==iid, GitHubImport.project_id==project.id, GitHubImport.workspace_id==project.workspace_id))
        if job is None: raise not_found()
        if job.state not in {'completed','completed_incomplete'}:
            raise ApiError(409,'analysis_import_incomplete','Choose a completed import.')
        if utc(job.start_at) < utc(body.start_at) or utc(job.end_before) > utc(body.end_before):
            raise ApiError(422,'analysis_import_scope','The report dates must contain the selected import scope.')
        repo = db.get(GitHubRepository, job.repository_id)
        if repo.github_id in imported_repos or any(repository_name(u).casefold()==repo.full_name.casefold() for u in body.repository_urls):
            raise ApiError(422,'analysis_duplicate_repository','Choose one capture per repository in each report.')
        imported_repos.add(repo.github_id)
        sources = list(db.scalars(select(GitHubSourceVersion).join(GitHubObservation, GitHubObservation.source_id==GitHubSourceVersion.id)
            .where(GitHubObservation.import_id==job.id).distinct().order_by(GitHubSourceVersion.captured_at,GitHubSourceVersion.id).limit(MAX_SOURCES+1)))
        if len(sources) + len(p['sources']) > MAX_SOURCES:
            raise ApiError(409,'analysis_source_limit','Select smaller imports; a report retains at most 500 source versions.')
        p['sources'].extend(deepcopy(s.document) for s in sources)
        if sum(len(canonical(d)) for d in p['sources']) > MAX_BYTES:
            raise ApiError(409,'analysis_source_limit','Select a smaller import; a report retains at most 2 MiB of normalized source.')
        p['repositories'].append({'github_id':repo.github_id,'full_name':repo.full_name,'private':repo.private,
            'default_branch':repo.default_branch,'anchor_sha':job.anchor_sha,'import_id':str(job.id),
            'description':'Authorized captured import; repository context was not fetched.', 'tree_paths':[], 'context':[]})
        p['omissions'].extend(f'{repo.full_name}:{o}' for o in job.omissions[:100])
    row = RepositoryAnalysis(id=uuid4(), workspace_id=project.workspace_id, project_id=project.id,
        created_by=actor, request_id=body.request_id, request_hash=fingerprint, definition=definition,
        state='queued', version=1, progress=p, created_at=now())
    db.add(row)
    if not p['tasks']: complete(row,p)
    audit(db,'analysis.created',actor_id=actor,workspace_id=project.workspace_id,project_id=project.id,
        subject_id=row.id,reason='Requested bounded draft repository analysis; no credit issued.')
    db.flush(); return row


def advance(db, wid, pid, actor, rid, body, client, settings, repository_store=None, repository_transport=None):
    project, _ = access(db,wid,pid,actor,manage=True,lock=True)
    row = run_in_project(db,project,rid,lock=True)
    if row.version != body.expected_version: raise ApiError(409,'analysis_stale','The analysis changed. Refresh before continuing.')
    if row.state not in {'queued','running'}: raise ApiError(409,'analysis_terminal','This report is completed, failed or cancelled.')
    if row.lease_until and utc(row.lease_until) > now(): raise ApiError(409,'analysis_busy','One checkpoint is already being fetched.')
    project_access(db,wid,pid,row.created_by,manage=True)
    connection_id = row.definition.get('connection_id')
    connection_version = None
    if connection_id:
        try:
            connection = connections.checked(db,project,row.created_by,connection_id,settings,
                names=[repository_name(u) for u in row.definition['repository_urls']],lock=True)
            connection_version = connection.version
            client = connections.client_for(connection,repository_store,settings,repository_transport)
        except ApiError as error:
            row.state='failed';row.error_code=error.code;row.version+=1
            row.lease_token=None;row.lease_until=None;db.commit()
            return run_view(row,full=True)
    elif not settings.repository_public_reads_enabled:
        raise ApiError(409,'analysis_public_reads_disabled','Public reads are disabled.')
    p = deepcopy(row.progress)
    if p['cursor'] >= len(p['tasks']) or p['requests'] >= MAX_REQUESTS:
        if p['cursor'] < len(p['tasks']): p['omissions'].append('public_request_limit:remaining_tasks_not_fetched')
        complete(row,p); db.commit(); return run_view(row,full=True)
    task = p['tasks'][p['cursor']]; path, params = request_for(p,task,row.definition)
    fence = uuid4(); row.lease_token = fence; row.lease_until = now()+timedelta(seconds=90)
    row.state = 'running'; row.version += 1; db.commit()
    failure = None; raw = None; more = False
    try: raw,more = client.get(path,params)
    except GitHubError as error:
        if task['kind']=='anchor' and error.code=='github_empty_or_conflicting_repository':
            raw=[];more=False
            p['omissions'].append(task['repository']+':commit_history_unavailable_or_empty')
        else:failure = error
    # Workspace -> report lock, current caller AND original sharer checked after the network.
    project,_ = access(db,wid,pid,actor,manage=True,lock=True)
    row = run_in_project(db,project,rid,lock=True)
    project_access(db,wid,pid,row.created_by,manage=True)
    if row.lease_token != fence or row.state != 'running' or utc(row.lease_until) <= now():
        raise ApiError(409,'analysis_checkpoint_discarded','The checkpoint was cancelled, expired or replaced; no response was stored.')
    if connection_id:
        try:
            connection = connections.checked(db,project,row.created_by,connection_id,settings,lock=True)
            if connection.version != connection_version:
                raise ApiError(409,'analysis_connection_changed','The connection changed during capture.')
        except ApiError as error:
            row.lease_token=None;row.lease_until=None;row.version+=1;row.state='failed'
            row.error_code=error.code;db.commit()
            return run_view(row,full=True)
    elif not settings.repository_public_reads_enabled:
        raise ApiError(409,'analysis_public_reads_disabled','Public reads were disabled during the fetch.')
    p['requests'] += 1
    if failure is None:
        checkpoint = deepcopy(p)
        try:
            absorb(checkpoint,task,raw,more,row.definition)
            p = checkpoint
        except (GitHubError, ValueError, TypeError, KeyError, AttributeError) as error:
            failure = error if isinstance(error,GitHubError) else GitHubError('github_invalid_response')
    row.lease_token = None; row.lease_until = None; row.version += 1
    if failure:
        row.state = 'failed'; row.error_code = failure.code
        if failure.retry_seconds is not None: row.retry_after = now()+timedelta(seconds=max(60,failure.retry_seconds))
        p['failures'] = p.get('failures',0)+1
    else:
        p['cursor'] += 1
        if p['cursor'] >= len(p['tasks']): complete(row,p)
    row.progress = p; db.commit(); return run_view(row,full=True)


def action_run(db, project, row, body, action):
    if row.version != body.expected_version: raise ApiError(409,'analysis_stale','The analysis changed. Refresh before continuing.')
    if row.state in {'completed','cancelled'}: raise ApiError(409,'analysis_terminal','This report is already completed or cancelled.')
    if action == 'retry':
        if row.state != 'failed': raise ApiError(409,'analysis_not_failed','Only failed runs can be retried.')
        if row.retry_after and utc(row.retry_after)>now(): raise ApiError(429,'analysis_backoff','Wait for the recorded retry time.')
        if row.progress.get('failures',0) >= 5: raise ApiError(409,'analysis_retry_limit','Five failures reached; finish a partial report or cancel.')
        row.state = 'queued'; row.error_code = None; row.retry_after = None
    elif action == 'finish-partial':
        if row.lease_until and utc(row.lease_until)>now(): raise ApiError(409,'analysis_busy','Wait for the current fetch before completing a partial report.')
        p = deepcopy(row.progress)
        if not p['repositories']: raise ApiError(409,'analysis_no_sources','No repository identity was captured; retry or cancel.')
        p['omissions'].append('operator_finished_partial:remaining_tasks_not_fetched')
        if row.error_code: p['omissions'].append(row.error_code)
        complete(row,p)
    else:
        row.state = 'cancelled'; row.finished_at = now()
    row.lease_token = None; row.lease_until = None; row.version += 1
    return run_view(row,full=True)


def draft_document(db, project):
    row = db.get(AnalysisDraft,project.id)
    return row, deepcopy(row.document) if row else {'manual':[],'people':[],'aliases':{},'proposals':{},'amount_cents':0}


def change_draft(db, project, actor, body, transform):
    previous = db.scalar(select(AnalysisDraftRevision).where(AnalysisDraftRevision.project_id==project.id,AnalysisDraftRevision.request_id==body.request_id))
    fingerprint = digest(body.model_dump(mode='json'))
    if previous:
        if previous.request_hash != fingerprint or previous.created_by != actor:
            raise ApiError(409,'idempotency_conflict','This request ID belongs to another draft change.')
        return {'version':previous.version,'replayed':True}
    row, document = draft_document(db,project); version = row.version if row else 0
    if body.expected_version != version: raise ApiError(409,'analysis_draft_stale','The draft changed. Refresh and review the newer version.')
    if version >= 2000: raise ApiError(409,'analysis_draft_history_limit','This pilot supports 2,000 preserved draft revisions per project.')
    transform(document)
    if len(canonical(document)) > MAX_BYTES: raise ApiError(409,'analysis_draft_limit','The draft exceeds the 2 MiB pilot capacity.')
    if row is None:
        row = AnalysisDraft(project_id=project.id,workspace_id=project.workspace_id,version=1,document=document); db.add(row)
    else: row.version += 1; row.document = document
    db.add(AnalysisDraftRevision(project_id=project.id,workspace_id=project.workspace_id,version=row.version,
        created_by=actor,request_id=body.request_id,request_hash=fingerprint,reason=body.reason,document=document))
    audit(db,'analysis.draft_changed',actor_id=actor,workspace_id=project.workspace_id,project_id=project.id,
        reason=body.reason,details={'version':row.version,'draft_only':True})
    return {'version':row.version,'replayed':False}


def resolved(key, aliases):
    visited = set()
    while key in aliases:
        if key in visited: raise ApiError(409,'analysis_alias_cycle','Contributor aliases contain a cycle.')
        visited.add(key); key = aliases[key]
    return key


def available_people(db, project, document, report=None):
    people = {p['key']:p for p in document['people']}
    collections = [report.report['contributors']] if report else db.scalars(select(RepositoryAnalysis.report['contributors'])
        .where(RepositoryAnalysis.project_id==project.id,RepositoryAnalysis.state=='completed')
        .order_by(RepositoryAnalysis.created_at,RepositoryAnalysis.id))
    for collection in collections:
        for p in collection: people[p['key']] = p
    # Current members are explicit selectable identities; never match them by name/email.
    # Retained credit recipients remain available for historical draft attribution.
    from app.ledger.models import ContributionEvent
    for uid,name in db.execute(select(ContributionEvent.user_id,ContributionEvent.display_name).where(ContributionEvent.project_id==project.id).distinct()):
        key = 'local:' + str(uid); people[key] = {'key':key,'name':name,'username':None,'kind':'local','repositories':[],'roles':[]}
    from app.contributions.work_packages.service import active_people
    for uid,p in active_people(db,project).items():
        key = 'local:' + uid
        people[key] = {'key':key,'name':p['display_name'],'username':None,'kind':'local','repositories':[],'roles':[]}
    return people


def list_runs(db, project):
    # History lists do not materialize retained source packets or whole reports.
    columns = [RepositoryAnalysis.id,RepositoryAnalysis.state,RepositoryAnalysis.version,RepositoryAnalysis.definition,
        RepositoryAnalysis.created_at,RepositoryAnalysis.finished_at,RepositoryAnalysis.error_code,RepositoryAnalysis.retry_after,
        RepositoryAnalysis.progress['requests'].as_integer().label('requests'),
        RepositoryAnalysis.progress['cursor'].as_integer().label('completed_tasks'),
        func.json_array_length(RepositoryAnalysis.progress['tasks']).label('total_tasks'),
        func.json_array_length(RepositoryAnalysis.progress['sources']).label('source_count'),
        RepositoryAnalysis.progress['omissions'].label('omissions')]
    rows = db.execute(select(*columns).where(RepositoryAnalysis.project_id==project.id)
        .order_by(RepositoryAnalysis.created_at.desc(),RepositoryAnalysis.id.desc()).limit(200)).mappings()
    return [{**dict(r),'id':str(r['id'])} for r in rows]


def save_proposal(db, project, actor, body):
    run = run_in_project(db,project,body.report_id)
    if run.state != 'completed': raise ApiError(409,'analysis_report_incomplete','Complete the source report first.')
    outcome = next((o for o in run.report['outcomes'] if o['id']==body.outcome_id),None)
    if not outcome: raise not_found()
    def update(doc):
        people = available_people(db,project,doc)
        if any(e.contributor_key not in people for e in body.entries): raise ApiError(422,'analysis_unknown_contributor','Select an observed or manual contributor.')
        if len(doc['proposals']) >= 1000 and body.outcome_id not in doc['proposals']:
            raise ApiError(409,'analysis_proposal_limit','The draft reached 1,000 outcome proposals.')
        doc['proposals'][body.outcome_id] = {'evidence_hash':outcome['evidence_hash'], 'report_id':str(run.id),
            'proposed_atoms':body.proposed_atoms,'entries':[e.model_dump() for e in body.entries],
            'rationale':text(body.rationale,2000),'rubric_version':body.rubric_version,'proposed_by':str(actor)}
    return change_draft(db,project,actor,body,update)


def save_manual(db, project, actor, body):
    if utc(body.performed_at) > now() or body.performed_at.year < 1970:
        raise ApiError(422,'analysis_manual_date','Record a performed date in the past or present, from 1970 onward.')
    cid = str(body.contribution_id or uuid4())
    def update(doc):
        existing = next((r for r in doc['manual'] if r['id']==cid),None)
        if body.contribution_id and not existing: raise not_found()
        if len(doc['manual']) >= 500 and not existing: raise ApiError(409,'analysis_manual_limit','This project reached 500 manual entries.')
        people = available_people(db,project,doc)
        key = body.contributor_key
        if key and key not in people: raise ApiError(422,'analysis_unknown_contributor','Select an observed or manual contributor.')
        if not key:
            if len(body.contributor_name.strip()) < 2: raise ApiError(422,'analysis_name_required','Enter the manual contributor name.')
            prior = people.get(existing['contributor_key']) if existing else None
            key = prior['key'] if prior and prior['kind']=='manual' and prior['name']==text(body.contributor_name.strip(),120) else 'manual:' + str(uuid4())
            if key not in people: doc['people'].append({'key':key,'name':text(body.contributor_name.strip(),120), 'username':None,'kind':'manual','repositories':[],'roles':[]})
        if body.repository:
            names = {o['full_name'] for run in db.scalars(select(RepositoryAnalysis).where(RepositoryAnalysis.project_id==project.id,RepositoryAnalysis.state=='completed')) for o in run.report['repositories']}
            if body.repository not in names: raise ApiError(422,'analysis_repository_unknown','Select a repository retained in this project.')
        record = {**body.model_dump(mode='json',exclude={'request_id','expected_version','reason','contribution_id','contributor_name'}),
            'id':cid,'contributor_key':key,'title':text(body.title,200),'description':text(body.description,6000),
            'evidence':text(body.evidence,4000),'rationale':text(body.rationale,2000),'origin':'manual',
            'status':existing.get('status','proposed') if existing else 'proposed'}
        if key.startswith('local:') and key not in {p['key'] for p in doc['people']}:doc['people'].append(deepcopy(people[key]))
        doc['manual'] = [r for r in doc['manual'] if r['id']!=cid] + [record]
    return change_draft(db,project,actor,body,update)


def save_manual_disposition(db, project, actor, body):
    def update(doc):
        entry = next((m for m in doc['manual'] if m['id']==str(body.contribution_id)),None)
        if entry is None: raise not_found()
        entry['status'] = body.status
    return change_draft(db,project,actor,body,update)


def manual_history(db, project, contribution_id):
    """Extract one entry in SQL; never materialize other source/draft packets.

    Window comparison removes unrelated draft changes. Latest 50 entry changes
    are returned; the immutable revisions retain the complete history.
    """
    _,doc = draft_document(db,project)
    if not any(m['id']==str(contribution_id) for m in doc['manual']): raise not_found()
    r = AnalysisDraftRevision
    if db.get_bind().dialect.name == 'postgresql':
        from sqlalchemy.dialects.postgresql import JSONB
        entries = func.jsonb_array_elements(cast(r.document['manual'],JSONB)).table_valued('value').alias('entries')
        identity = cast(entries.c.value,JSONB)['id'].as_string()
    else:
        entries = func.json_each(r.document,'$.manual').table_valued('value').alias('entries')
        identity = func.json_extract(entries.c.value,'$.id')
    serialized = cast(entries.c.value,String)
    changes = select(r.version,r.created_at,r.created_by,r.reason,serialized.label('entry'),
        func.lag(serialized).over(order_by=r.version).label('previous')).select_from(r).join(entries,true())\
        .where(r.workspace_id==project.workspace_id,r.project_id==project.id,identity==str(contribution_id)).subquery()
    rows = list(db.execute(select(changes).where((changes.c.previous.is_(None)) | (changes.c.entry!=changes.c.previous))
        .order_by(changes.c.version.desc()).limit(51)).mappings())
    import json
    return {'contribution_id':str(contribution_id),'truncated':len(rows)>50,'revisions':[
        {'version':r['version'],'created_at':r['created_at'],'created_by':str(r['created_by']),
         'reason':r['reason'],'entry':json.loads(r['entry'])} for r in rows[:50]]}


def save_alias(db, project, actor, body):
    def update(doc):
        people = available_people(db,project,doc)
        if body.source_key not in people or body.target_key not in people: raise ApiError(422,'analysis_unknown_contributor','Both identities must be retained in this project.')
        if body.source_key == body.target_key: doc['aliases'].pop(body.source_key,None)
        else: doc['aliases'][body.source_key] = body.target_key
        if body.target_key.startswith('local:') and body.target_key not in {p['key'] for p in doc['people']}:
            doc['people'].append(deepcopy(people[body.target_key]))
        for key in doc['aliases']: resolved(key,doc['aliases'])
    return change_draft(db,project,actor,body,update)


def report_dashboard(db, project, actor, role, run=None):
    draft, doc = draft_document(db,project)
    report = run.report if run else {'contributors':[],'outcomes':[],'repositories':[],'omissions':[],'rubric':RUBRIC,'scope':None}
    all_people = available_people(db,project,doc)
    if len(all_people) >= 10000:
        raise ApiError(409,'analysis_people_limit','This project exceeds the 9,999-person exact reporting bound.')
    people = {}
    for key,p in all_people.items():
        target = resolved(key,doc['aliases']); label = all_people[target]
        entry = people.setdefault(target,{**label,'aliases':[],'proposed_atoms':0,'outcome_ids':[], 'repositories':set(), 'roles':set()})
        entry['aliases'].append({'key':key,'name':p['name'],'username':p.get('username')})
        entry['repositories'].update(p.get('repositories',[])); entry['roles'].update(p.get('roles',[]))
    outcomes = []; denominator = 0; assigned = 0; stale = 0
    for o in report['outcomes']:
        proposal = doc['proposals'].get(o['id']); valid = proposal and proposal['evidence_hash']==o['evidence_hash']
        if proposal and not valid: stale += 1
        derived = None
        if valid:
            weights = {}
            for e in proposal['entries']:
                key = resolved(e['contributor_key'],doc['aliases']); weights[key] = weights.get(key,0)+e['atoms']
            derived = {**proposal,'entries':[{'contributor_key':k,'atoms':v} for k,v in sorted(weights.items())]}
        record = {**o,'proposal':derived,'proposal_stale':bool(proposal and not valid)}
        record['contributors'] = [{**p,'key':resolved(p['key'],doc['aliases'])} for p in o['contributors']]
        outcomes.append(record)
    for m in doc['manual']:
        if m.get('status','proposed')=='excluded': continue
        if report['scope']:
            from datetime import datetime
            start = datetime.fromisoformat(report['scope']['start_at'].replace('Z','+00:00'))
            end = datetime.fromisoformat(report['scope']['end_before'].replace('Z','+00:00'))
            if not start <= datetime.fromisoformat(m['performed_at'].replace('Z','+00:00')) < end: continue
        oid = sha256(('manual:'+m['id']).encode()).hexdigest(); key = resolved(m['contributor_key'],doc['aliases'])
        outcomes.append({'id':oid,'title':m['title'],'category':m['category'],'origin':'manual','summary':m['description'],
            'manual_id':m['id'],'repositories':[m['repository']] if m['repository'] else [],'files':[],
            'contributors':[{'key':key,'roles':['manual contribution']}],
            'sources':[{'id':m['id'],'kind':'manual','repository':m['repository'],'url':None,'title':m['title'],'excerpt':m['evidence'],'omissions':[]}],
            'proposal':{'proposed_atoms':m['proposed_atoms'],'entries':[{'contributor_key':key,'atoms':m['proposed_atoms']}],
                'rationale':m['rationale'],'rubric_version':RUBRIC['version']},'proposal_stale':False,
            'limitations':['Manual evidence and attribution are claims awaiting independent review.']})
    for o in outcomes:
        for contribution in o['contributors']:
            p = people[contribution['key']]
            if o['id'] not in p['outcome_ids']: p['outcome_ids'].append(o['id'])
            p['repositories'].update(o['repositories']); p['roles'].update(contribution['roles'])
        proposal = o['proposal']
        if proposal:
            denominator += proposal['proposed_atoms']
            for e in proposal['entries']:
                key = resolved(e['contributor_key'],doc['aliases']); p = people[key]
                p['proposed_atoms'] += e['atoms']; assigned += e['atoms']
                if o['id'] not in p['outcome_ids']: p['outcome_ids'].append(o['id'])
    if denominator > MAX_ATOMS: raise ApiError(409,'analysis_unit_limit','Total proposed units exceed the supported exact pilot bound.')
    unassigned = denominator-assigned; amount = doc['amount_cents']; allocations = {}
    if denominator:
        weights = [('person_'+digest(k)[:32],p['proposed_atoms']) for k,p in people.items()] + [('unassigned',unassigned)]
        allocations = {r['key']:r['amount_cents'] for r in largest_remainder(amount,weights)}
    for key,p in people.items():
        p['repositories'] = sorted(p['repositories']); p['roles'] = sorted(p['roles'])
        p['share'] = {'numerator':p['proposed_atoms'],'denominator':denominator}
        p['estimated_cents'] = allocations.get('person_'+digest(key)[:32],0)
        p['summary'],p['highlights'] = contributor_summary(key,outcomes)
        p['github_usernames'] = sorted({a['username'] for a in p['aliases'] if a.get('username')})
    recognized = recognized_dashboard(db,project,actor,role)
    from .models import AnalysisHandoff
    transfers = {h.document['outcome']['id']:h for h in db.scalars(select(AnalysisHandoff)
        .where(AnalysisHandoff.workspace_id==project.workspace_id,AnalysisHandoff.project_id==project.id))}
    approved_ids = {key:{key[6:]} if key.startswith('local:') else set() for key in people}
    for outcome in outcomes:
        handoff = transfers.get(outcome['id'])
        outcome['handoff'] = {'id':str(handoff.id),'package_id':str(handoff.package_id),'created_at':utc(handoff.created_at).isoformat()} if handoff else None
        if handoff:
            for identity in handoff.document['identity_resolutions']:
                key = resolved(identity['external_key'],doc['aliases'])
                if identity['disposition']=='participant' and key in approved_ids:
                    approved_ids[key].add(identity['user_id'])
    for key,person in people.items(): person['approved_user_ids'] = sorted(approved_ids[key])
    return {'report_id':str(run.id) if run else None,'report':report,'draft_version':draft.version if draft else 0,
        'contributors':sorted(people.values(),key=lambda p:(p['name'].casefold(),p['key'])), 'outcomes':outcomes,
        'manual_entries':doc['manual'],'aliases':doc['aliases'],'rubric':RUBRIC,'stale_proposal_count':stale,
        'proposed_denominator_atoms':denominator,'unassigned_atoms':unassigned,
        'scenario':{'currency':'USD','amount_cents':amount,'allocated_cents':sum(p['estimated_cents'] for p in people.values()),
            'unallocated_cents':allocations.get('unassigned',amount if not denominator else 0),'synthetic_only':True,'payable':False},
        'recognized':recognized,
        'denominator_label':'All proposed outcome atoms in the selected report and dated manual entries, including unassigned atoms. Repository and person display filters keep this denominator.'}
