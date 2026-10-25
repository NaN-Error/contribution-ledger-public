"""Opt-in real-browser hypothetical simulation on a prepared synthetic project.

Not executed automatically; never mark this as passed until a real browser ran.
Requires CL_E2E_ALLOW_SIMULATOR=1, a local disposable *_test deployment,
CL_E2E_EMAIL/PASSWORD, CL_E2E_WORKSPACE_ID, CL_E2E_PROJECT_ID,
CL_E2E_SOURCE_POLICY_ID, and a clearly synthetic project with accepted credit.
Existing policy, awards and source data are NOT modified. One non-payable
scenario is saved. No money or external-provider calls are involved.
"""
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID
from playwright.sync_api import sync_playwright,expect
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'apps/api'))
from app.core.config import get_settings


def main():
    if os.environ.get('CL_E2E_ALLOW_SIMULATOR')!='1':raise SystemExit('Explicit synthetic browser-test opt-in required.')
    settings=get_settings();settings.require_development_tools()
    if not settings.db_name.endswith('_test'):raise SystemExit('Only a disposable *_test database is permitted.')
    base=os.environ.get('CL_E2E_BASE_URL','http://127.0.0.1:5173');url=urlsplit(base)
    if url.hostname not in {'localhost','127.0.0.1'} or url.scheme!='http' or url.username or url.password:
        raise SystemExit('Use a credential-free local HTTP test origin.')
    wid=UUID(os.environ['CL_E2E_WORKSPACE_ID']);pid=UUID(os.environ['CL_E2E_PROJECT_ID']);policy=UUID(os.environ['CL_E2E_SOURCE_POLICY_ID'])
    root=base+f'/api/v1/workspaces/{wid}/projects/{pid}'
    with sync_playwright() as p:
        browser=p.chromium.launch();context=browser.new_context(viewport={'width':1280,'height':1000});page=context.new_page()
        page.goto(base);page.get_by_label('Email',exact=True).fill(os.environ['CL_E2E_EMAIL'])
        page.get_by_label('Password',exact=True).fill(os.environ['CL_E2E_PASSWORD'])
        page.locator('form').get_by_role('button',name='Sign in',exact=True).click()
        page.get_by_role('link',name='Workspaces',exact=True).click()
        expect(page.get_by_role('heading',name='Your workspaces',exact=True)).to_be_visible()
        workspace_response=context.request.get(base+f'/api/v1/workspaces/{wid}');assert workspace_response.ok
        project_response=context.request.get(root);assert project_response.ok
        workspace=workspace_response.json();project=project_response.json()
        assert any(word in project['name'].lower() for word in ['synthetic','smoke']), 'A clearly labeled synthetic project is required.'
        before=context.request.get(root+'/contributions').json()['total_issued_atoms']
        assert before>0,'Prepare accepted synthetic credit before this UI smoke.'
        page.locator('button.project-card').filter(has=page.get_by_text(workspace['name'],exact=True)).click()
        page.locator('button.project-card').filter(has=page.get_by_text(project['name'],exact=True)).click()
        page.get_by_role('button',name='Revenue simulator',exact=True).click()
        page.get_by_label('Source-credit policy',exact=True).select_option(str(policy))
        page.get_by_label('Calculation policy',exact=True).select_option(str(policy))
        page.get_by_label('Hypothetical distributable USD',exact=True).fill('10000.00')
        page.get_by_role('button',name='Calculate hypothetical distribution',exact=True).click()
        expect(page.get_by_role('heading',name='Simulation results',exact=True)).to_be_visible()
        expect(page.get_by_text('Hypothetical · not payable',exact=True)).to_be_visible()
        page.get_by_label('Saved example title',exact=True).fill('Synthetic browser what-if example')
        page.get_by_role('checkbox',name='This is hypothetical and creates no amount owed or payable.',exact=True).check()
        page.get_by_role('button',name='Save hypothetical example',exact=True).click()
        expect(page.get_by_role('heading',name='Synthetic browser what-if example',exact=True)).to_be_visible()
        page.get_by_role('link',name='Open project-protected link',exact=True).click()
        expect(page.get_by_role('heading',name='Saved hypothetical scenario',exact=True)).to_be_visible()
        assert context.request.get(root+'/contributions').json()['total_issued_atoms']==before
        link=page.url
        # A different, signed-out browser must not receive protected data.
        other=browser.new_context();stranger=other.new_page();stranger.goto(link)
        expect(stranger.locator('form').get_by_role('button',name='Sign in',exact=True)).to_be_visible()
        assert other.request.get(root+'/simulator/scenarios').status==401
        other.close();browser.close()
    print('Synthetic simulator browser flow passed: preview, saved example, scoped link, no credit mutation. No payments.')


if __name__=='__main__':main()
