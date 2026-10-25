"""Rendered dashboard -> pinned historical package -> independent human credit.

Disposable native schema and fictional accounts only. No live source/provider
requests, repository execution, actual compensation or claimed human pilot.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
from uuid import UUID, uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'apps/api'))


def main():
    from alembic import command
    from fastapi.testclient import TestClient
    from playwright.sync_api import sync_playwright, expect
    from sqlalchemy import create_engine, text
    import httpx
    import uvicorn
    from app.core.config import get_settings
    from app.db.session import Database
    from app.db.migration import migration_config
    from app.main import create_app
    from app.auth.models import User
    from tests.test_analysis_handoff import environment, prepare
    from tests.phase6_helpers import assign
    from tests.auth_helpers import PASSWORD
    from tests.test_repository_analysis import dash
    settings = get_settings(); settings.require_development_tools()
    if os.environ.get('CL_E2E_ALLOW_ANALYSIS_FIXTURES') != '1' or settings.db_host not in {'localhost','127.0.0.1'} or not settings.db_name.endswith('_test'):
        raise ValueError('Explicit synthetic fixture opt-in and a disposable loopback *_test database are required.')
    if settings.github_enabled or settings.ai_live_enabled or settings.ai_evidence_enabled or settings.ai_paid_probes_enabled:
        raise ValueError('Live integrations must remain disabled.')
    node = shutil.which('node')
    if not node or not (ROOT/'apps/web/dist/index.html').is_file(): raise ValueError('Install Node and build the frontend first.')
    schema = 'analysis_handoff_browser_'+uuid4().hex
    output = ROOT/'.local'/'analysis-handoff'/schema; output.mkdir(parents=True, exist_ok=False)
    api_port, web_port = 18005, 15178; base = f'http://127.0.0.1:{web_port}'
    settings = settings.model_copy(update={'allowed_hosts':['127.0.0.1','testserver'], 'allowed_origins':['http://testserver',base],
        'object_storage_root':str(output/'objects'), 'auth_master_key_file':str(output/'auth/master.key')})
    control = create_engine(settings.database_url(), hide_parameters=True)
    with control.begin() as c: c.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(settings.database_url(), hide_parameters=True, connect_args={'options':f'-c search_path={schema} -c statement_timeout=10000'})
    database = Database(settings, engine); config = migration_config()
    with engine.begin() as c: config.attributes['connection']=c; command.upgrade(config,'head')
    app = create_app(settings, database); client = TestClient(app, raise_server_exceptions=True)
    e = environment(client, database, settings); body, preview = prepare(e)
    server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=api_port, access_log=False, proxy_headers=False, log_level='warning'))
    thread = threading.Thread(target=server.run, daemon=True); web = None
    web_log = (output/'web.log').open('w', encoding='utf-8')
    report = {'synthetic_only':True, 'live_requests':0, 'human_pilot_completed':False, 'schema':schema, 'checks':{}}
    try:
        thread.start(); deadline=time.monotonic()+30
        while not server.started:
            if not thread.is_alive() or time.monotonic()>deadline: raise RuntimeError('Isolated API did not start.')
            time.sleep(.1)
        web = subprocess.Popen([node,'server.mjs'], cwd=ROOT/'apps/web', env={**os.environ,
            'CL_API_TARGET':f'http://127.0.0.1:{api_port}', 'CL_WEB_INTERNAL_PORT':str(web_port), 'CL_BIND_HOST':'127.0.0.1'}, stdout=web_log, stderr=web_log)
        deadline=time.monotonic()+30
        while True:
            try:
                if httpx.get(base+'/health/ready').status_code==200: break
            except httpx.HTTPError: pass
            if web.poll() is not None or time.monotonic()>deadline: raise RuntimeError('Isolated web did not start.')
            time.sleep(.1)
        p = e['owner']['project']; w = e['owner']['workspace']
        with sync_playwright() as pw:
            browser = pw.chromium.launch(); context = browser.new_context(viewport={'width':1440,'height':1000})
            context.add_cookies([{'name':c.name,'value':c.value,'url':base} for c in client.cookies.jar])
            page=context.new_page(); errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto(base+f"/#analysis?workspace={w['id']}&project={p['id']}&report={body['report_id']}&outcome={body['outcome_id']}")
            page.get_by_role('button',name='Prepare this contribution for human review',exact=True).click()
            page.get_by_label('Approved historical scope',exact=True).select_option(e['batch']['id'])
            expect(page.get_by_role('heading',name='Review this contribution for a work package',exact=True)).to_be_visible()
            for i in preview['document']['identities']:
                page.get_by_label('Review identity: '+i['name'],exact=True).select_option(e['owner']['user']['id'] if i['external_key']=='github:1' else 'context')
            page.get_by_label('Reason for these identity dispositions',exact=True).fill('Explicit fictional username-to-participant mapping; all other observed roles are context.')
            page.get_by_label("I reviewed these precise findings, identities and evidence excerpts and permit sharing them with this project's participants.",exact=True).check()
            page.set_viewport_size({'width':390,'height':844});page.screenshot(path=str(output/'mobile-identity-review.png'),full_page=True)
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), 'Mobile review overflow'
            assert page.get_by_role('button',name='Continue to acceptance criteria and scope',exact=True).evaluate('(b)=>{const r=b.getBoundingClientRect(),p=b.parentElement.getBoundingClientRect();return r.left>=p.left-1&&r.right<=p.right+1;}'), 'Review button exceeds its mobile panel'
            page.get_by_role('heading',name='Review this contribution for a work package',exact=True).locator('..').screenshot(path=str(output/'mobile-review-panel.png'))
            page.set_viewport_size({'width':1440,'height':1000})
            page.get_by_role('button',name='Continue to acceptance criteria and scope',exact=True).click()
            expect(page.get_by_label('Deliverable 1 budget in units',exact=True)).to_have_value('100')
            page.get_by_label('Package acceptance criteria — one per line',exact=True).fill('Reconnect the interrupted session without losing preserved progress.')
            page.get_by_label('Deliverable 1 criteria — one per line',exact=True).fill('Reconnect the interrupted session and verify the retained progress evidence.')
            page.get_by_label('Reason for this scope revision',exact=True).fill('Prepare the exact fictional contribution and attribution for independent acceptance.')
            page.get_by_role('button',name='Save work-package draft',exact=True).click()
            expect(page.get_by_role('button',name='Refresh package',exact=True)).to_be_visible(timeout=30000)
            with database.engine.connect() as c:
                rows=c.execute(text('SELECT package_id, document FROM analysis_handoffs')).all();assert len(rows)==1
                package_id=str(rows[0].package_id);pinned=rows[0].document
                assert c.execute(text('SELECT count(*) FROM credit_awards')).scalar_one()==0
            assert pinned['outcome']==preview['document']['outcome']
            assert pinned['scope']['budget_atoms']==100000 and pinned['work_category']=='qa'
            page.get_by_text('Inspect pinned dashboard review',exact=True).first.click()
            expect(page.get_by_role('heading',name='Preserved dashboard review: Reconnect after interruption',exact=True)).to_be_visible()
            report['checks']['rendered_exact_identity_budget_evidence_handoff_without_credit']='passed'
            page.screenshot(path=str(output/'desktop-pinned-package.png'),full_page=True)
            for action in ('approve_scope','start','submit'):
                panel=page.locator('section.panel').filter(has=page.get_by_role('heading',name='Review the scope before changing its state',exact=True))
                panel.get_by_label('Work-package action',exact=True).select_option(action)
                panel.get_by_label('Submission note' if action=='submit' else 'Reason for this action',exact=True).fill('Fictional reviewed package action; this does not issue accepted units.')
                panel.get_by_role('checkbox').check();panel.get_by_role('button',name={'approve_scope':'Approve this scope for work','start':'Start work','submit':'Submit readiness declaration'}[action],exact=True).click()
                expect(page.get_by_text({'approve_scope':'budget approved','start':'in progress','submit':'submitted'}[action],exact=True)).to_be_visible()
            package=client.get(e['root']+'/work-packages/'+package_id).json();changed={**e,'package':package,'path':e['root']+'/work-packages/'+package_id}
            review=assign(changed)
            with database.session() as db: reviewer_email=db.get(User,UUID(e['actors']['reviewer']['id'])).email
            reviewer_context=browser.new_context(viewport={'width':1280,'height':1000});reviewer_page=reviewer_context.new_page()
            reviewer_page.goto(base);reviewer_page.get_by_label('Email',exact=True).fill(reviewer_email);reviewer_page.get_by_label('Password',exact=True).fill(PASSWORD)
            reviewer_page.locator('form').get_by_role('button',name='Sign in',exact=True).click()
            expect(reviewer_page.get_by_role('heading',name='Repository dashboard',exact=True)).to_be_visible()
            reviewer_page.get_by_role('link',name='Workspaces',exact=True).click()
            reviewer_page.get_by_role('button',name=w['name']+' Open projects',exact=False).click()
            reviewer_page.locator('button.project-card').filter(has=reviewer_page.get_by_text(p['name'],exact=True)).click()
            reviewer_page.get_by_role('button',name='Human reviews',exact=True).click()
            reviewer_page.locator('.work-history').filter(has=reviewer_page.get_by_text(review['target']['title'],exact=True)).first.get_by_role('button',name='Inspect review',exact=True).click()
            form=reviewer_page.locator('section.panel').filter(has=reviewer_page.get_by_role('heading',name='Your independent decision',exact=True))
            ref=next(s['ref'] for s in review['target']['evidence_sources'] if not s.get('restricted'))
            for n,_ in enumerate(review['target']['criteria'],1):
                form.get_by_label(f'Finding {n}',exact=True).select_option('supported');form.get_by_label(f'Supporting references for finding {n}',exact=True).select_option([ref])
                form.get_by_label(f'Explanation for finding {n}',exact=True).fill('Inspected the synthetic pinned outcome and provenance against this fictional criterion.')
            form.get_by_label('Review decision',exact=True).select_option('accept');form.get_by_label('Reason for your decision',exact=True).fill('Independent fictional reviewer acceptance of this precise evidence packet.')
            for check in form.get_by_role('checkbox').all():check.check()
            form.get_by_role('button',name='Record independent decision',exact=True).click()
            final=reviewer_page.locator('section.panel').filter(has=reviewer_page.get_by_role('heading',name='Finalize the reviewed decision set',exact=True))
            expect(final).to_be_visible()
            with database.engine.connect() as c:assert c.execute(text('SELECT count(*) FROM credit_awards')).scalar_one()==0
            final.get_by_label('Finalization reason',exact=True).fill('Explicitly finalize the independently reviewed synthetic dashboard package once.')
            final.get_by_role('checkbox').check();final.get_by_role('button',name='Finalize human-reviewed record',exact=True).click()
            expect(reviewer_page.get_by_text('finalized',exact=True)).to_be_visible()
            report['checks']['rendered_planning_submission_independent_decision_and_separate_credit']='passed'
            page.get_by_role('button',name='Back to work packages',exact=True).click()
            expect(page.get_by_role('button',name='Open the preserved review package',exact=True)).to_be_visible()
            page.goto(base+f"/#analysis?workspace={w['id']}&project={p['id']}&report={body['report_id']}")
            expect(page.get_by_role('heading',name='Current recognized contributions',exact=True)).to_be_visible()
            expect(page.get_by_text('100 approved units',exact=False)).to_be_visible()
            assert sum(p['atoms'] for g in dash(e['analysis'])['recognized']['groups'] for p in g['people'])==100000
            page.locator('.analysis-person').filter(has=page.get_by_text('@alice',exact=True)).click()
            expect(page.locator('.analysis-approved-profile')).to_contain_text('100 approved units')
            expect(page.locator('.analysis-approved-profile')).to_contain_text('100.00%')
            page.get_by_role('button',name='Reconnect after interruption',exact=False).first.click()
            page.get_by_role('button',name='Open the preserved review package',exact=True).click()
            expect(page.get_by_text('completed',exact=True)).to_be_visible()
            report['checks']['recognized_credit_comparison_and_existing_package_navigation']='passed'
            assert not errors, errors
            reviewer_context.close();context.close();browser.close()
        report['passed']=True;(output/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
        print(json.dumps({'passed':True,'checks':report['checks'],'report':str(output/'report.json')}))
    finally:
        server.should_exit=True;thread.join(timeout=20)
        if web is not None and web.poll() is None: web.terminate();web.wait(timeout=20)
        for actor in e['actors'].values():actor['client'].close()
        web_log.close();client.close();database.dispose();control.dispose()


if __name__=='__main__':main()
