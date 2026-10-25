"""Rendered repository-first workflow against an isolated native schema and mock API.

Opt-in CL_E2E_ALLOW_ANALYSIS_FIXTURES=1, local *_test DB, development tools,
built web app and installed Chromium required. Preserves all other schemas and
data. Stops only its own temporary servers. No live GitHub/model calls.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'apps/api'))


def main():
    from alembic import command
    from fastapi.testclient import TestClient
    from playwright.sync_api import sync_playwright, expect
    from sqlalchemy import create_engine,text
    import uvicorn
    from app.core.config import get_settings
    from app.db.session import Database
    from app.db.migration import migration_config
    from app.main import create_app
    from tests.auth_helpers import bootstrap, PASSWORD
    from tests.test_repository_analysis import PublicFixture, OlderThreadFixture
    settings=get_settings();settings.require_development_tools()
    if os.environ.get('CL_E2E_ALLOW_ANALYSIS_FIXTURES')!='1' or settings.db_host not in {'127.0.0.1','localhost'} or not settings.db_name.endswith('_test'):
        raise ValueError('Explicit opt-in and a disposable loopback PostgreSQL *_test database required.')
    if settings.github_enabled or settings.ai_live_enabled or settings.ai_evidence_enabled:
        raise ValueError('Keep live integrations disabled for synthetic browser acceptance.')
    node=shutil.which('node')
    if not node or not (ROOT/'apps/web/dist/index.html').is_file():raise ValueError('Build the frontend first.')
    schema='analysis_browser_'+uuid4().hex;output=ROOT/'.local'/'repository-analysis'/schema;output.mkdir(parents=True,exist_ok=False)
    api_port,web_port=18003,15176;base=f'http://127.0.0.1:{web_port}'
    settings=settings.model_copy(update={'allowed_hosts':['127.0.0.1','testserver'], 'allowed_origins':['http://testserver',base],
        'object_storage_root':str(output/'objects'),'auth_master_key_file':str(output/'auth/master.key')})
    control=create_engine(settings.database_url(),hide_parameters=True)
    with control.begin() as c:c.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine=create_engine(settings.database_url(),hide_parameters=True,connect_args={'options':f'-c search_path={schema} -c statement_timeout=10000'})
    database=Database(settings,engine);config=migration_config()
    with engine.begin() as c:config.attributes['connection']=c;command.upgrade(config,'head')
    fixture=PublicFixture();app=create_app(settings,database,public_repository_client=fixture)
    client=TestClient(app,raise_server_exceptions=True);owner=bootstrap(client,database)
    server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=api_port,access_log=False,proxy_headers=False,log_level='warning'))
    thread=threading.Thread(target=server.run,daemon=True);web=None;web_log=(output/'web.log').open('w',encoding='utf-8')
    report={'synthetic_only':True,'live_requests':0,'checks':{},'schema':schema}
    try:
        thread.start();deadline=time.monotonic()+30
        while not server.started:
            if not thread.is_alive() or time.monotonic()>deadline:raise RuntimeError('Isolated API failed to start.')
            time.sleep(.1)
        env={**os.environ,'CL_API_TARGET':f'http://127.0.0.1:{api_port}','CL_WEB_INTERNAL_PORT':str(web_port),'CL_BIND_HOST':'127.0.0.1'}
        web=subprocess.Popen([node,'server.mjs'],cwd=ROOT/'apps/web',env=env,stdout=web_log,stderr=web_log)
        import httpx
        deadline=time.monotonic()+30
        while True:
            try:
                if httpx.get(base+'/health/ready').status_code==200:break
            except httpx.HTTPError:pass
            if web.poll() is not None or time.monotonic()>deadline:raise RuntimeError('Isolated web did not become ready.')
            time.sleep(.1)
        with sync_playwright() as pw:
            browser=pw.chromium.launch();context=browser.new_context(viewport={'width':1440,'height':1100})
            cookies=[{'name':c.name,'value':c.value,'url':base} for c in client.cookies.jar];context.add_cookies(cookies)
            page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            page.goto(base+'/#analysis');expect(page.get_by_role('heading',name='Repository dashboard',exact=True)).to_be_visible()
            page.get_by_label('GitHub repository links',exact=True).fill('https://github.com/team/game\nhttps://github.com/team/editor')
            page.get_by_label('Analysis start (UTC)',exact=True).fill('2026-01-01');page.get_by_label('Analysis end, excluded (UTC)',exact=True).fill('2026-02-01')
            page.get_by_label('Read these public repositories or reuse selected authorized evidence within this project.',exact=True).check()
            page.get_by_role('button',name='Analyze repositories',exact=True).click()
            expect(page.get_by_role('button',name='alice',exact=False).first).to_be_visible(timeout=120000)
            expect(page.get_by_role('heading',name='Contribution outcomes',exact=True)).to_be_visible()
            report['checks']['paste_two_repository_urls_and_capture']='passed'
            expect(page.get_by_role('heading',name='Report has capture limitations',exact=True)).to_be_visible()
            limits=page.get_by_role('button',name='Inspect capture limitations',exact=True);limits.focus();limits.press('Enter')
            expect(page.locator('.analysis-report-context[open] > summary')).to_be_focused()
            alice=page.locator('.analysis-person').filter(has=page.get_by_text('@alice',exact=True));alice.focus();alice.press('Enter')
            expect(page.get_by_role('heading',name='alice · @alice',exact=True)).to_be_visible()
            page.locator('.analysis-outcome').first.focus();page.locator('.analysis-outcome').first.press('Enter')
            expect(page.get_by_role('heading',name='Stated goal',exact=True)).to_be_visible()
            page.go_back();expect(page.get_by_role('heading',name='Contribution outcomes',exact=True)).to_have_count(0)
            expect(page.get_by_role('heading',name='Contributions by alice',exact=True)).to_be_visible()
            page.go_forward();expect(page.get_by_role('heading',name='Stated goal',exact=True)).to_be_visible()
            report['checks']['keyboard_drilldown_browser_history_and_visible_capture_limits']='passed'
            page.get_by_text('Propose units and attribution',exact=True).click()
            expect(page.get_by_role('heading',name='Stated goal',exact=True)).to_be_visible()
            page.locator('.analysis-findings').get_by_role('button',name='Read pull request evidence',exact=True).first.click()
            expect(page.locator('.analysis-source[open]').get_by_text('Reconnect sessions without losing progress.',exact=True)).to_be_visible()
            report['checks']['source_cited_goal_status_scope_and_review_findings']='passed'
            page.get_by_label('Outcome proposed units',exact=True).fill('3');page.get_by_label('Proposal rationale',exact=True).fill('Three draft outcome units, with one unit unassigned until attribution is resolved.')
            for key,name in [('github:1','alice'),('github:2','ben')]:
                page.get_by_label('Add a contributor to attribution',exact=True).select_option(key);page.get_by_role('button',name='Add contributor',exact=True).click();page.get_by_label('Units for '+name,exact=True).fill('1')
            page.get_by_role('button',name='Save unit proposal',exact=True).click()
            expect(page.get_by_text('3 proposed units',exact=False).first).to_be_visible()
            page.get_by_label('Hypothetical distributable amount (USD)',exact=True).fill('1000.03');page.get_by_role('button',name='Update scenario',exact=True).click()
            expect(page.locator('.analysis-stats')).to_contain_text('$1,000.03')
            page.get_by_text('Add an extra contribution',exact=True).click()
            page.get_by_label('Contributor name',exact=True).fill('Cyra');page.get_by_label('Contribution title',exact=True).fill('Character concept artwork');page.get_by_label('Contribution category',exact=True).select_option('art')
            page.get_by_label('Work date (UTC)',exact=True).fill('2026-01-20');page.get_by_label('Work description',exact=True).fill('Character concepts created outside the repository.')
            page.get_by_label('Supporting evidence or link description',exact=True).fill('Synthetic artwork board and participant statement.')
            page.get_by_label('Proposed units',exact=True).fill('1');page.get_by_label('Reason for the unit proposal',exact=True).fill('One separately scoped draft artwork outcome for team review.')
            page.get_by_role('button',name='Save extra contribution',exact=True).click();expect(page.locator('.analysis-stats')).to_contain_text('4')
            report['checks']['profiles_evidence_proposals_manual_art_exact_scenario']='passed'
            page.get_by_text('Manage extra contributions (1)',exact=True).click()
            page.get_by_role('button',name='Edit extra contribution',exact=True).click()
            editor=page.get_by_role('form',name='Correct extra contribution',exact=True)
            editor.get_by_label('Contribution title',exact=True).fill('Corrected character concept artwork')
            editor.get_by_label('Work description',exact=True).fill('Corrected character concept scope and retained original evidence.')
            editor.get_by_label('Reason for this correction',exact=True).fill('Correct the description without rewriting the originally recorded artwork claim.')
            editor.get_by_role('button',name='Save contribution correction',exact=True).click()
            expect(page.locator('.analysis-manual-entry')).to_contain_text('Corrected character concept artwork')
            page.get_by_text('Exclude entry from draft',exact=True).click()
            page.get_by_label('Reason for exclusion or restoration',exact=True).fill('Exclude this manual claim temporarily while its overlap is reviewed.')
            page.get_by_role('button',name='Exclude extra contribution',exact=True).click()
            expect(page.locator('.analysis-stats').filter(has_text='Proposed units')).to_contain_text('3')
            page.get_by_text('Restore entry to draft',exact=True).click()
            page.get_by_label('Reason for exclusion or restoration',exact=True).fill('Restore the retained artwork claim after the overlap review.')
            page.get_by_role('button',name='Restore extra contribution',exact=True).click()
            expect(page.locator('.analysis-stats').filter(has_text='Proposed units')).to_contain_text('4')
            page.get_by_role('button',name='View entry history',exact=True).click()
            expect(page.get_by_role('heading',name='Preserved entry history',exact=True)).to_be_visible()
            assert page.locator('.analysis-entry-history details').count()==4
            original=page.locator('.analysis-entry-history details').last;original.locator('summary').click()
            expect(original.get_by_text('Character concept artwork',exact=False).first).to_be_visible()
            expect(page.locator('form.analysis-scenario')).to_have_count(1)
            expect(page.locator('form[aria-label="Add extra contribution"]')).to_have_count(1)
            report['checks']['manual_correction_exclusion_restore_and_retained_history']='passed'
            page.get_by_role('button',name='All contributors',exact=False).click();page.get_by_label('Repository display filter',exact=True).select_option('team/game')
            expect(page.locator('.analysis-stats').filter(has_text='Proposed units')).to_contain_text('4')
            alice=page.locator('.analysis-person').filter(has=page.get_by_text('@alice',exact=True));expect(alice).to_contain_text('25.00%');alice.click()
            page.reload();expect(page.get_by_role('heading',name='alice · @alice',exact=True)).to_be_visible()
            profile_url=page.url;page.get_by_role('button',name='Sign out',exact=True).click()
            expect(page.get_by_role('heading',name='Sign in',exact=True)).to_be_visible()
            page.goto(profile_url)
            expect(page.get_by_role('heading',name='Sign in',exact=True)).to_be_visible()
            page.get_by_label('Email',exact=True).fill(owner['user']['email']);page.get_by_label('Password',exact=True).fill(PASSWORD)
            page.locator('form').get_by_role('button',name='Sign in',exact=True).click()
            expect(page.get_by_role('heading',name='alice · @alice',exact=True)).to_be_visible()
            assert page.url==profile_url
            report['checks']['display_filter_preserves_denominator_and_profile_reload']='passed'
            page.set_viewport_size({'width':390,'height':844});page.screenshot(path=str(output/'mobile-profile.png'),full_page=True)
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), 'Mobile horizontal overflow'
            page.set_viewport_size({'width':1440,'height':1100});page.get_by_role('button',name='All contributors',exact=False).click()
            page.get_by_text('Create another project',exact=True).click();page.get_by_label('New project name',exact=True).fill('Second analysis project');page.get_by_role('button',name='Create project',exact=True).click()
            expect(page.get_by_role('heading',name='Second analysis project',exact=True)).to_be_visible();expect(page.locator('.analysis-stats').filter(has_text='Proposed units')).to_contain_text('0')
            page.get_by_label('Project',exact=True).select_option(owner['project']['id']);expect(page.locator('.analysis-person').filter(has=page.get_by_text('Cyra',exact=True))).to_be_visible()
            expect(page.locator('.analysis-stats').filter(has_text='Proposed units')).to_contain_text('4');page.screenshot(path=str(output/'desktop-dashboard.png'),full_page=True)
            report['checks']['project_switch_isolation_saved_drafts_mobile_layout']='passed'
            # Exact sharing preview and a separate real browser member session.
            page.get_by_text('Share a contribution report',exact=True).click()
            page.get_by_role('button',name='Preview report for sharing',exact=True).click()
            page.get_by_text('Inspect the exact report snapshot',exact=True).click()
            preview=page.locator('.analysis-sharing-preview')
            expect(preview.locator('.analysis-stats')).to_contain_text('4')
            expect(preview.locator('.analysis-person').filter(has=page.get_by_text('@alice',exact=True))).to_contain_text('25.00%')
            page.get_by_text('Inspect the exact report snapshot',exact=True).click()
            page.get_by_label("I reviewed this exact snapshot and may share its identities, evidence excerpts, repository context and proposed values with this project's members.",exact=True).check()
            page.get_by_label('Reason for sharing this report',exact=True).fill('Share the reviewed synthetic report with current project members for discussion.')
            page.get_by_role('button',name='Share reviewed report',exact=True).click()
            link=page.get_by_role('link',name='Open shared snapshot',exact=True);expect(link).to_be_visible()
            shared_url=base+'/'+link.get_attribute('href')
            from tests.test_analysis_sharing import member
            from app.auth.models import User
            uid,peer=member({'owner':owner,'database':database,'settings':settings},'contributor')
            with database.session() as db:email=db.get(User,uid).email
            member_context=browser.new_context(viewport={'width':390,'height':844});member_page=member_context.new_page()
            member_page.goto(shared_url);expect(member_page.get_by_role('heading',name='Sign in',exact=True)).to_be_visible()
            member_page.get_by_label('Email',exact=True).fill(email);member_page.get_by_label('Password',exact=True).fill(PASSWORD)
            member_page.locator('form').get_by_role('button',name='Sign in',exact=True).click()
            expect(member_page.get_by_role('heading',name='Shared contribution reports',exact=True)).to_be_visible()
            expect(member_page.locator('.analysis-stats')).to_contain_text('$1,000.03')
            member_page.locator('.analysis-person').filter(has=member_page.get_by_text('@alice',exact=True)).click()
            expect(member_page.get_by_role('heading',name='alice · @alice',exact=True)).to_be_visible()
            assert 'publication=' in member_page.url and 'person=github' in member_page.url
            member_page.reload();expect(member_page.get_by_role('heading',name='alice · @alice',exact=True)).to_be_visible()
            member_page.locator('.analysis-highlights').get_by_role('button').first.click()
            expect(member_page.get_by_role('heading',name='Stated goal',exact=True)).to_be_visible()
            member_page.locator('.analysis-findings').get_by_role('button',name='Read pull request evidence',exact=True).first.click()
            expect(member_page.locator('.analysis-source[open]')).to_contain_text('Reconnect sessions without losing progress.')
            expect(member_page.get_by_role('button',name='Save unit proposal',exact=True)).to_have_count(0)
            expect(member_page.get_by_text('Manage extra contributions (1)',exact=True)).to_have_count(0)
            expect(member_page.get_by_label('GitHub repository links',exact=True)).to_have_count(0)
            assert member_context.request.get(base+f"/api/v1/workspaces/{owner['workspace']['id']}/projects/{owner['project']['id']}/analysis").status==403
            member_page.screenshot(path=str(output/'mobile-shared-evidence.png'),full_page=True)
            assert member_page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), member_page.evaluate("Array.from(document.querySelectorAll('main *')).filter(e=>e.getBoundingClientRect().right>window.innerWidth+1).map(e=>({tag:e.tagName,class:e.className,right:e.getBoundingClientRect().right})).slice(0,15)")
            # Later draft edits cannot change a pinned shared view.
            page.get_by_label('Hypothetical distributable amount (USD)',exact=True).fill('999.99')
            page.get_by_role('button',name='Update scenario',exact=True).click()
            expect(page.locator('.analysis-stats')).to_contain_text('$999.99')
            member_page.reload();expect(member_page.locator('.analysis-stats')).to_contain_text('$1,000.03')
            page.get_by_text('Share a contribution report',exact=True).click()
            page.get_by_text('Revoke access to this snapshot',exact=True).click()
            page.get_by_label('Reason for revoking report access',exact=True).fill('Withdraw this synthetic report from project-member access while keeping its history.')
            page.get_by_role('button',name='Revoke shared report',exact=True).click()
            expect(page.get_by_role('link',name='Open shared snapshot',exact=True)).to_have_count(0)
            member_page.reload();expect(member_page.get_by_role('heading',name='Shared contribution reports',exact=True)).to_have_count(0)
            expect(member_page.get_by_role('button',name='Retry',exact=False)).to_be_visible()
            member_page.get_by_role('button',name='Open available shared reports',exact=True).click()
            expect(member_page.get_by_role('heading',name='Shared contribution reports',exact=True)).to_be_visible()
            expect(member_page.get_by_text('No shared contribution outcomes yet',exact=True)).to_be_visible()
            member_context.close();peer.close()
            report['checks']['exact_shared_snapshot_member_drilldown_edit_isolation_and_revocation']='passed'
            # A fresh report must retain January review/discussion on an older
            # December parent, while its original author's identity stays out.
            older_fixture=OlderThreadFixture();app.state.public_repository_client=older_fixture
            page.locator('.analysis-input > summary').click()
            page.get_by_label('GitHub repository links',exact=True).fill('https://github.com/team/game')
            page.get_by_label('Analysis start (UTC)',exact=True).fill('2026-01-01')
            page.get_by_label('Analysis end, excluded (UTC)',exact=True).fill('2026-02-01')
            page.get_by_label('Read these public repositories or reuse selected authorized evidence within this project.',exact=True).check()
            page.get_by_role('button',name='Analyze repositories',exact=True).click()
            cara=page.locator('.analysis-person').filter(has=page.get_by_text('@cara',exact=True))
            expect(cara).to_be_visible(timeout=120000)
            expect(page.locator('.analysis-person').filter(has=page.get_by_text('@alice',exact=True))).to_have_count(0)
            expect(page.locator('.analysis-person').filter(has=page.get_by_text('@ben',exact=True))).to_contain_text('Review evidence')
            cara.click();page.locator('.analysis-outcome').first.click()
            parent=page.locator('.analysis-source').filter(has=page.locator('summary',has_text='pull request'))
            parent.locator('summary').click()
            expect(parent).to_contain_text('Parent context only.')
            expect(parent).to_contain_text('Created: 2025-12-16T00:00:00.000Z')
            comment=page.locator('.analysis-source').filter(has=page.locator('summary',has_text='comment'))
            comment.locator('summary').click()
            expect(comment).to_contain_text('Created: 2026-01-19T00:00:00.000Z')
            expect(comment).to_contain_text('Last updated: 2026-03-07T00:00:00.000Z')
            expect(comment).to_contain_text('current_representation_updated_after_selected_window')
            expect(page.locator('.analysis-stats')).to_contain_text('1') # Retained manual draft only.
            expect(page.locator('form.analysis-scenario')).to_have_count(1)
            page.set_viewport_size({'width':390,'height':844})
            parent.screenshot(path=str(output/'mobile-older-parent-context.png'))
            comment.screenshot(path=str(output/'mobile-comment-dates.png'))
            page.screenshot(path=str(output/'mobile-older-thread-dates.png'),full_page=True)
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
            report['checks']['older_parent_review_discussion_dates_without_old_authorship']='passed'
            report['older_parent_mock_requests']=len(older_fixture.calls)
            assert not errors,errors
            with database.engine.connect() as c:assert c.execute(text('SELECT count(*) FROM credit_awards')).scalar_one()==0
            report['checks']['no_credit_or_money_effect']='passed';context.close();browser.close()
        report['mock_api_requests']=len(fixture.calls);report['passed']=True
        (output/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
        print(json.dumps({'passed':True,'checks':report['checks'],'report':str(output/'report.json')}))
    finally:
        server.should_exit=True;thread.join(timeout=20)
        if web is not None and web.poll() is None:web.terminate();web.wait(timeout=20)
        web_log.close();client.close();database.dispose();control.dispose()


if __name__=='__main__':main()
