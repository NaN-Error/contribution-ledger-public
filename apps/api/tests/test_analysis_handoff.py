"""Dashboard evidence enters ordinary historical review; no automatic credit."""
from copy import deepcopy
from types import SimpleNamespace
from uuid import UUID, uuid4
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, func, text
from sqlalchemy.exc import DBAPIError
from app.main import create_app
from app.analysis.models import AnalysisHandoff, AnalysisSourceClaim, RepositoryAnalysis
from app.analysis.handoff import primary_link_guard
from app.core.errors import ApiError
from app.ledger.models import CreditAward
from tests.auth_helpers import mutation
from tests.phase3_helpers import active_milestone, allocate
from tests.phase4_helpers import scope
from tests.phase6_helpers import environment as prior_environment
from tests.phase5_helpers import revise
from tests.phase12_helpers import approve, accept_package
from tests.test_repository_analysis import PublicFixture, DATES, start, finish, dash, change, post


def environment(client, database, settings):
    e = prior_environment(client, database, settings)
    milestone = active_milestone(client, e['root'], e['policy'], total=1000000, reserve=100000)
    r = mutation(client, e['root']+'/reconstruction', {'request_id':str(uuid4()), 'milestone_id':milestone['id'],
        'title':'Reviewed repository work', **DATES, 'historical_scope':'Review the captured January work and manual extras under the current agreement.',
        'agreement_reference':'Synthetic reviewed team historical allocation agreement.', 'reason':'Define explicit scope before any historical credit review'})
    assert r.status_code == 201, r.text
    e['batch'] = r.json(); e['base'] = e['root']+'/reconstruction/'+e['batch']['id']; approve(e)
    e['analysis'] = {**e, 'root':e['root']+'/analysis'}
    e['fixture'] = PublicFixture(); client.app.state.public_repository_client = e['fixture']
    finish(e['analysis'], start(e['analysis']))
    return e


@pytest.fixture
def handoff_env(settings, database):
    with TestClient(create_app(settings, database), raise_server_exceptions=True) as client:
        e = environment(client, database, settings)
        try: yield e
        finally:
            for a in e['actors'].values(): a['client'].close()


def prepare(e, *, manual=False, performed_at='2026-01-20T12:34:56-04:00'):
    a = e['analysis']; d = dash(a)
    if manual:
        post(a, '/manual', change(a, title='Historical artwork', category='art',
            description='A finished fictional character design outside source control.',
            contributor_key='local:'+e['owner']['user']['id'], contributor_name='',
            evidence='Synthetic design board and independently reviewable participant statement.',
            performed_at=performed_at, proposed_atoms=100000,
            rationale='Explicit reviewed artwork scope of one hundred proposed units.'))
        d = dash(a); o = next(o for o in d['outcomes'] if o['origin'] == 'manual')
    else:
        o = d['outcomes'][0]
        post(a, '/proposals', change(a, report_id=d['report_id'], outcome_id=o['id'], proposed_atoms=100000,
            entries=[{'contributor_key':'github:1','atoms':100000}], rationale='The reviewed reconnect outcome proposes a hundred units under this scope.'))
        d = dash(a); o = next(x for x in d['outcomes'] if x['id'] == o['id'])
    milestone = e['client'].get(e['root']+'/milestones/'+e['batch']['milestone_id']).json()
    old = {r['id'] for r in milestone['allocations']}
    milestone = allocate(e['client'], e['root'], milestone, atoms=100000, title=o['title'][:120], category='art' if manual else 'qa')
    allocation = next(r for r in milestone['allocations'] if r['id'] not in old)
    params = {'report_id':d['report_id'], 'outcome_id':o['id'], 'batch_id':e['batch']['id']}
    r = e['client'].get(a['root']+'/handoff/preview', params=params); assert r.status_code == 200, r.text
    view = r.json(); assert view['blockers'] == [], view
    identities = [{'external_key':r['external_key'],
        'disposition':'participant' if r['external_key'] in {'github:1','local:'+e['owner']['user']['id']} else 'context_only',
        'user_id':e['owner']['user']['id'] if r['external_key'] in {'github:1','local:'+e['owner']['user']['id']} else None,
        'reason':'Explicit synthetic identity and role review; no name matching.'} for r in view['document']['identities']]
    planned = scope(e['owner']['user']['id'], 100000); planned['title'] = o['title'][:120]
    body = {'request_id':str(uuid4()), 'expected_version':d['draft_version'], **params,
        'expected_batch_version':view['document']['batch_version'], 'reviewed_hash':view['review_hash'],
        'project_sharing_confirmed':True, 'identities':identities, 'allocation_id':allocation['id'],
        'expected_allocation_version':allocation['version'], 'scope':planned,
        'reason':'Review and pin this precise outcome in the ordinary historical acceptance workflow.'}
    return body, view


def create(e, body, status=201):
    r = mutation(e['client'], e['analysis']['root']+'/handoff', body)
    assert r.status_code == status, r.text
    return r.json()


def test_captured_outcome_pins_evidence_and_only_independent_review_issues_credit(handoff_env):
    e = handoff_env; body, view = prepare(e); result = create(e, body)
    path = e['root']+'/work-packages/'+result['package_id']; p = e['client'].get(path).json()
    assert p['state'] == 'draft' and p['origin'] == 'retrospective' and p['issued_atoms'] == 0
    evidence = e['client'].get(path+'/evidence').json()['items']
    assert len(evidence) == 1+len(view['document']['outcome']['sources'])
    source_path=path+'/evidence/'+evidence[0]['evidence_id']+'/revisions/1'
    assert e['client'].get(source_path+'/github-source').status_code==404
    pinned=e['client'].get(source_path+'/analysis-source');assert pinned.status_code==200,pinned.text
    assert pinned.json()['document']['outcome']==view['document']['outcome']
    assert e['actors']['viewer']['client'].get(source_path+'/analysis-source').status_code==200
    assert e['actors']['viewer']['client'].get(source_path+'/github-source').status_code==404
    with e['database'].session() as db:
        row = db.get(AnalysisHandoff, UUID(result['handoff_id']))
        original = deepcopy(row.document)
        assert row.document['outcome'] == view['document']['outcome']
        assert row.document['identity_resolutions'] == sorted(body['identities'], key=lambda r:r['external_key'])
        assert db.scalar(select(func.count()).select_from(CreditAward)) == 0
    a = e['analysis']; post(a, '/scenario', change(a, amount_cents=100003))
    with e['database'].session() as db: assert db.get(AnalysisHandoff, UUID(result['handoff_id'])).document == original
    changed, final = accept_package(e, p)
    assert final
    d = dash(a); assert d['recognized']['groups']
    people = [p for g in d['recognized']['groups'] for p in g['people']]
    assert sum(p['atoms'] for p in people) == 100000
    assert next(p for p in people if p['user_id'] == e['owner']['user']['id'])['atoms'] == 100000
    assert next(p for p in d['contributors'] if p['key']=='github:1')['approved_user_ids']==[e['owner']['user']['id']]
    assert next(p for p in d['contributors'] if p['key']=='github:2')['approved_user_ids']==[]
    assert d['scenario']['amount_cents'] == 100003 and not d['scenario']['payable']


def test_manual_date_evidence_and_history_are_frozen_after_draft_correction(handoff_env):
    e = handoff_env; body, view = prepare(e, manual=True); result = create(e, body)
    with e['database'].session() as db:
        original = deepcopy(db.get(AnalysisHandoff, UUID(result['handoff_id'])).document)
    m = view['document']['manual_entry']; a = e['analysis']
    post(a, '/manual', change(a, contribution_id=m['id'], title='Corrected historical artwork', category=m['category'],
        description=m['description'], contributor_key=m['contributor_key'], contributor_name='', evidence='Corrected fictional evidence statement.',
        performed_at=m['performed_at'], proposed_atoms=m['proposed_atoms'], rationale=m['rationale']))
    with e['database'].session() as db:
        row = db.get(AnalysisHandoff, UUID(result['handoff_id']))
        assert row.document == original and row.document['manual_entry']['performed_at'] == m['performed_at']
    v = e['client'].get(a['root']+'/handoff/preview', params={k:body[k] for k in ('report_id','outcome_id','batch_id')}).json()
    assert any('already' in b for b in v['blockers'])
    for sql in ['DELETE FROM analysis_handoffs', "UPDATE analysis_source_claims SET entity_key='rewrite'"]:
        with pytest.raises(DBAPIError), e['database'].engine.begin() as db: db.execute(text(sql))


def test_pinned_analysis_source_rechecks_current_evidence_visibility_and_membership(handoff_env):
    e = handoff_env; body, _ = prepare(e); result = create(e, body)
    path = e['root']+'/work-packages/'+result['package_id']
    record = e['client'].get(path+'/evidence').json()['items'][0]
    revision_path = path+'/evidence/'+record['evidence_id']+'/revisions/1'
    viewer = e['actors']['viewer']['client']
    assert viewer.get(revision_path+'/analysis-source').status_code == 200
    assert viewer.get(e['analysis']['root']).status_code == 403
    assert e['client'].get(revision_path.replace(e['owner']['project']['id'],str(uuid4()))+'/analysis-source').status_code == 404
    record = e['client'].get(revision_path).json()
    revised = revise(e['client'],path,record,metadata={**record['document']['metadata'],'visibility':'restricted'})
    assert revised.status_code == 200, revised.text
    assert viewer.get(revision_path+'/analysis-source').status_code == 404
    assert e['client'].get(revision_path+'/analysis-source').status_code == 200
    restored = revise(e['client'],path,revised.json(),metadata={**record['document']['metadata'],'visibility':'project'})
    assert restored.status_code == 200, restored.text
    assert viewer.get(revision_path+'/analysis-source').status_code == 200
    suspended = mutation(e['client'],e['root']+'/members/'+e['actors']['viewer']['id'],
        {'role':'viewer','status':'suspended','expected_version':1,'reason':'Suspend the fictional viewer before reopening preserved source evidence.'},method='patch')
    assert suspended.status_code == 200, suspended.text
    assert viewer.get(revision_path+'/analysis-source').status_code == 404


def test_stale_and_repeated_handoff_commands_have_atomic_idempotent_effects(handoff_env):
    e = handoff_env; body, _ = prepare(e); a = e['analysis']
    post(a, '/scenario', change(a, amount_cents=19)); assert create(e, body, 409)['error']['code'] == 'analysis_handoff_stale'
    with e['database'].session() as db: assert db.scalar(select(func.count()).select_from(AnalysisHandoff)) == 0
    view = e['client'].get(a['root']+'/handoff/preview', params={k:body[k] for k in ('report_id','outcome_id','batch_id')}).json()
    body.update(expected_version=view['document']['draft_version'], reviewed_hash=view['review_hash'])
    result = create(e, body); replay = create(e, body)
    assert replay['replayed'] and result['package_id'] == replay['package_id']
    altered = deepcopy(body); altered['scope']['title'] = 'Different scope under the same request'
    assert create(e, altered, 409)['error']['code'] == 'idempotency_conflict'
    with e['database'].session() as db: assert db.scalar(select(func.count()).select_from(AnalysisHandoff)) == 1


def test_manual_handoff_evidence_day_matches_the_selected_utc_window(handoff_env):
    e=handoff_env;instant='2026-02-01T00:30:00+02:00'
    body,view=prepare(e,manual=True,performed_at=instant);result=create(e,body)
    path=e['root']+'/work-packages/'+result['package_id']+'/evidence'
    records=e['client'].get(path).json()['items']
    assert records and all(r['document']['metadata']['occurred_on']=='2026-01-31' for r in records)
    assert view['document']['manual_entry']['performed_at']==instant
    with e['database'].session() as db:
        assert db.get(AnalysisHandoff,UUID(result['handoff_id'])).document['manual_entry']['performed_at']==instant


def test_identity_and_exact_attribution_changes_cannot_bypass_review(handoff_env):
    e = handoff_env; body, _ = prepare(e)
    altered = deepcopy(body); altered['identities'] = []
    create(e, altered, 422)
    altered = deepcopy(body)
    next(r for r in altered['identities'] if r['external_key'] == 'github:1').update(disposition='context_only', user_id=None)
    assert create(e, altered, 409)['error']['code'] == 'analysis_handoff_attribution'
    altered = deepcopy(body); altered['scope']['deliverables'][0]['attribution']['entries'][0]['user_id'] = e['actors']['contributor']['id']
    altered['scope']['intended_contributor_ids'].append(e['actors']['contributor']['id'])
    assert create(e, altered, 409)['error']['code'] == 'analysis_handoff_attribution'
    with e['database'].session() as db: assert db.scalar(select(func.count()).select_from(AnalysisHandoff)) == 0


def test_handoff_requires_admin_current_project_scope_and_explicit_disclosure(handoff_env):
    e = handoff_env; body, _ = prepare(e); url = e['analysis']['root']+'/handoff'
    for actor in e['actors'].values():
        assert actor['client'].get(url+'/options').status_code == 403
        assert mutation(actor['client'], url, body).status_code == 403
    altered = {**body, 'project_sharing_confirmed':False}; create(e, altered, 422)
    altered = {**body, 'batch_id':str(uuid4())}; create(e, altered, 404)
    altered = {**body, 'allocation_id':e['package']['allocation_id']}; create(e, altered, 409)


def test_primary_source_claim_survives_recapture_and_blocks_shared_commit_in_another_repo(handoff_env):
    e = handoff_env; body, _ = prepare(e); result = create(e, body); a = e['analysis']
    e['fixture'].changed = True; finish(a, start(a, ['https://github.com/team/editor']))
    d = dash(a); o = d['outcomes'][0]
    v = e['client'].get(a['root']+'/handoff/preview', params={'report_id':d['report_id'], 'outcome_id':o['id'], 'batch_id':e['batch']['id']}).json()
    assert any('already' in b for b in v['blockers'])
    with e['database'].session() as db:
        run = db.get(RepositoryAnalysis, UUID(body['report_id']))
        doc = next(d for d in run.progress['sources'] if d['kind'] == 'commit')
        source = SimpleNamespace(document=doc, kind=doc['kind'], remote_key=doc['remote_key'])
        project = db.get(__import__('app.projects.models', fromlist=['Project']).Project, UUID(e['owner']['project']['id']))
        with pytest.raises(ApiError): primary_link_guard(db, project, source, uuid4())
        primary_link_guard(db, project, source, UUID(result['package_id']))
        assert db.scalar(select(func.count()).select_from(AnalysisSourceClaim)) >= 2
