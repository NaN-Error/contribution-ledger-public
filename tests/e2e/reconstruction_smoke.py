"""Opt-in rendered inspection of a prepared synthetic historical batch.

Does not create awards or call GitHub/AI. Use a local disposable *_test deployment,
CL_E2E_ALLOW_RECONSTRUCTION=1, CL_E2E_WORKSPACE_ID, CL_E2E_PROJECT_ID,
CL_E2E_BATCH_ID, CL_E2E_REVIEWER_EMAIL and CL_E2E_REVIEWER_PASSWORD.
The batch should have at least one reviewed candidate and a captured baseline.
No credentials, private screenshots, recordings or traces are saved.
"""
import os,sys
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID
from playwright.sync_api import sync_playwright,expect
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'apps/api'))
from app.core.config import get_settings


def main():
    if os.environ.get('CL_E2E_ALLOW_RECONSTRUCTION')!='1':raise SystemExit('Explicit local synthetic browser opt-in required.')
    settings=get_settings();settings.require_development_tools()
    if not settings.db_name.endswith('_test'):raise SystemExit('Use only a disposable *_test deployment.')
    base=os.environ.get('CL_E2E_BASE_URL','http://127.0.0.1:5173').rstrip('/')
    if urlsplit(base).hostname not in {'localhost','127.0.0.1'}:raise SystemExit('Use a local target.')
    wid=UUID(os.environ['CL_E2E_WORKSPACE_ID']);pid=UUID(os.environ['CL_E2E_PROJECT_ID']);bid=UUID(os.environ['CL_E2E_BATCH_ID'])
    root=f'{base}/api/v1/workspaces/{wid}/projects/{pid}'
    with sync_playwright() as pw:
        browser=pw.chromium.launch();context=browser.new_context(viewport={'width':1280,'height':1000});page=context.new_page()
        try:
            page.goto(base);page.get_by_label('Email',exact=True).fill(os.environ['CL_E2E_REVIEWER_EMAIL'])
            page.get_by_label('Password',exact=True).fill(os.environ['CL_E2E_REVIEWER_PASSWORD'])
            page.locator('form').get_by_role('button',name='Sign in',exact=True).click()
            page.get_by_role('link',name='Workspaces',exact=True).click()
            expect(page.get_by_role('heading',name='Your workspaces',exact=True)).to_be_visible()
            def get(url):
                response=context.request.get(url);assert response.status==200,'Fixture must be currently authorized.'
                return response.json()
            workspace=get(base+f'/api/v1/workspaces/{wid}');project=get(root);batch=get(root+f'/reconstruction/{bid}')
            assert any(x in project['name'].lower() for x in ('synthetic','smoke')),'Use a named synthetic project.'
            before=get(root+'/contributions')['total_issued_atoms']
            page.get_by_role('button',name=workspace['name']+' Open projects',exact=False).click()
            page.locator('button.project-card').filter(has=page.get_by_text(project['name'],exact=True)).click()
            page.get_by_role('button',name='Historical review',exact=True).click()
            page.locator('button.project-card').filter(has=page.get_by_text(batch['definition']['title'],exact=True)).click()
            expect(page.get_by_role('heading',name=batch['definition']['title'],exact=True)).to_be_visible()
            page.get_by_role('button',name='Opening balance',exact=True).click()
            expect(page.get_by_role('heading',name='Archived opening balance' if batch['state']=='frozen' else 'Review opening balance',exact=True)).to_be_visible()
            page.get_by_role('button',name='Contribution overview',exact=True).click()
            expect(page.get_by_role('heading',name='Contribution explanations',exact=True)).to_be_visible()
            page.get_by_label('Accepted category',exact=True).select_option('art')
            expect(page.get_by_text('Category and origin narrow the measured pool.',exact=False)).to_be_visible()
            page.set_viewport_size({'width':390,'height':844})
            expect(page.get_by_role('button',name='Refresh recognized contributions',exact=True)).to_be_visible()
            assert get(root+'/contributions')['total_issued_atoms']==before
            print('Historical review and contribution explanation views rendered; inspection changed no credit.')
        finally:context.close();browser.close()


if __name__=='__main__':main()
