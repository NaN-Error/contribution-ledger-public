"""Opt-in inspection of a PREPARED synthetic closed period. No account, credit or payment mutation.

Requires local disposable *_test deployment and CL_E2E_ALLOW_FINANCE=1;
CL_E2E_WORKSPACE_ID, CL_E2E_PROJECT_ID, CL_E2E_PERIOD_ID,
CL_E2E_FINANCE_EMAIL and CL_E2E_FINANCE_PASSWORD. No traces/screenshots saved.
"""
import os,sys
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID
from playwright.sync_api import sync_playwright,expect
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'apps/api'))
from app.core.config import get_settings


def main():
    if os.environ.get('CL_E2E_ALLOW_FINANCE')!='1':raise SystemExit('Explicit synthetic browser inspection opt-in required.')
    settings=get_settings();settings.require_development_tools()
    if not settings.db_name.endswith('_test'):raise SystemExit('Use a disposable *_test deployment.')
    base=os.environ.get('CL_E2E_BASE_URL','http://127.0.0.1:5173').rstrip('/')
    if urlsplit(base).hostname not in {'localhost','127.0.0.1'}:raise SystemExit('Use a local target.')
    wid=UUID(os.environ['CL_E2E_WORKSPACE_ID']);pid=UUID(os.environ['CL_E2E_PROJECT_ID']);period_id=UUID(os.environ['CL_E2E_PERIOD_ID'])
    root=f'{base}/api/v1/workspaces/{wid}/projects/{pid}'
    with sync_playwright() as pw:
        browser=pw.chromium.launch();context=browser.new_context(viewport={'width':1280,'height':1000});page=context.new_page()
        try:
            page.goto(base);page.get_by_label('Email',exact=True).fill(os.environ['CL_E2E_FINANCE_EMAIL'])
            page.get_by_label('Password',exact=True).fill(os.environ['CL_E2E_FINANCE_PASSWORD']);page.locator('form').get_by_role('button',name='Sign in',exact=True).click()
            page.get_by_role('link',name='Workspaces',exact=True).click()
            expect(page.get_by_role('heading',name='Your workspaces',exact=True)).to_be_visible()
            def get(path):
                r=context.request.get(path);assert r.status==200,'Prepared fixture must be authorized.';return r.json()
            workspace=get(base+f'/api/v1/workspaces/{wid}');project=get(root)
            assert any(v in project['name'].lower() for v in ('synthetic','smoke')),'Use a named synthetic project.'
            period=get(root+f'/finance/periods/{period_id}');assert period['state']=='closed' and period['record']['synthetic_only'] is True
            closed=get(root+'/finance/closes/'+period['close_id']);before=get(root+'/contributions')['total_issued_atoms']
            page.get_by_role('button',name=workspace['name']+' Open projects',exact=False).click()
            page.locator('button.project-card').filter(has=page.get_by_text(project['name'],exact=True)).click()
            page.get_by_role('button',name='Financial records',exact=True).click()
            expect(page.get_by_role('heading',name='Distributions and statements',exact=True)).to_be_visible()
            page.locator('button.project-card').filter(has=page.get_by_text(period['month'],exact=True)).click()
            page.get_by_role('button',name='Frozen distribution and payments',exact=True).click()
            expect(page.get_by_role('heading',name='Frozen synthetic distribution',exact=True)).to_be_visible()
            expect(page.get_by_role('heading',name='External-payment declarations',exact=True)).to_be_visible()
            export=root+'/finance/closes/'+closed['id']+'/export?format=json'
            a=context.request.get(export);b=context.request.get(export);assert a.status==b.status==200 and a.body()==b.body()
            page.set_viewport_size({'width':390,'height':844});expect(page.get_by_role('link',name='Download JSON',exact=True)).to_be_visible()
            assert get(root+'/contributions')['total_issued_atoms']==before
            assert get(root+'/finance/closes/'+closed['id'])['record_hash']==closed['record_hash']
            print('Prepared synthetic financial views rendered; repeated export preserved credit and closed amounts.')
        finally:context.close();browser.close()


if __name__=='__main__':main()
