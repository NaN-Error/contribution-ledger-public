"""Opt-in real rendered assessment inspection against a prepared synthetic result.

Invoked by feature_acceptance.py. Does not make AI requests, write feedback or award
credit. Prepare a current mock assessment in a disposable local *_test deployment,
then set CL_E2E_ALLOW_ASSESSMENT=1, CL_E2E_WORKSPACE_ID, CL_E2E_PROJECT_ID,
CL_E2E_PACKAGE_ID, CL_E2E_RESULT_ID, CL_E2E_REVIEWER_EMAIL and
CL_E2E_REVIEWER_PASSWORD. The result must be among the newest 25 visible plans.
No credentials, packet screenshots, browser traces or model output are saved.
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
    if os.environ.get('CL_E2E_ALLOW_ASSESSMENT')!='1':raise SystemExit('Explicit synthetic assessment browser-test opt-in is required.')
    settings=get_settings();settings.require_development_tools()
    if not settings.db_name.endswith('_test'):raise SystemExit('Only a disposable *_test deployment is permitted.')
    if settings.ai_live_enabled or settings.ai_paid_probes_enabled or settings.ai_evidence_enabled:
        raise SystemExit('Keep all live/paid/evidence flags false for this synthetic browser fixture.')
    base=os.environ.get('CL_E2E_BASE_URL','http://127.0.0.1:5173').rstrip('/')
    if urlsplit(base).hostname not in {'localhost','127.0.0.1'}:raise SystemExit('Only a local browser target is permitted.')
    workspace=UUID(os.environ['CL_E2E_WORKSPACE_ID']);project=UUID(os.environ['CL_E2E_PROJECT_ID'])
    package=UUID(os.environ['CL_E2E_PACKAGE_ID']);result_id=UUID(os.environ['CL_E2E_RESULT_ID'])
    root=base+f'/api/v1/workspaces/{workspace}/projects/{project}'
    with sync_playwright() as pw:
        browser=pw.chromium.launch();context=browser.new_context(viewport={'width':1280,'height':1000});page=context.new_page()
        try:
            page.goto(base)
            page.get_by_label('Email',exact=True).fill(os.environ['CL_E2E_REVIEWER_EMAIL'])
            page.get_by_label('Password',exact=True).fill(os.environ['CL_E2E_REVIEWER_PASSWORD'])
            page.locator('form').get_by_role('button',name='Sign in',exact=True).click()
            page.get_by_role('link',name='Workspaces',exact=True).click()
            expect(page.get_by_role('heading',name='Your workspaces',exact=True)).to_be_visible()
            def get(path):
                response=context.request.get(path);assert response.status==200,'Prepared authorized fixture is not accessible.'
                return response.json()
            workspace_info=get(base+f'/api/v1/workspaces/{workspace}');project_info=get(root)
            assert any(x in project_info['name'].lower() for x in ('synthetic','smoke')),'Use a clearly named synthetic project.'
            package_info=get(root+f'/work-packages/{package}');result=get(root+f'/ai/assessments/results/{result_id}')
            assert result['status']=='valid' and result['metadata']['synthetic'] and result['document']
            assert result['packet']['package_id']==str(package)
            assert all(f['status']=='insufficient' for f in result['document']['findings'])
            plans=get(root+f'/ai/assessments/plans?package_id={package}')['items']
            index=next(i for i,p in enumerate(plans) if p['result_id']==str(result_id))
            before=get(root+'/contributions')['total_issued_atoms']
            page.get_by_role('button',name=workspace_info['name']+' Open projects',exact=False).click()
            page.locator('button.project-card').filter(has=page.get_by_text(project_info['name'],exact=True)).click()
            page.get_by_role('button',name='Work packages',exact=True).click()
            page.get_by_label('Search work packages',exact=True).fill(package_info['title'])
            page.locator('button.project-card').filter(has=page.get_by_text(package_info['title'],exact=True)).click()
            expect(page.get_by_role('heading',name='AI-assisted evidence review',exact=True)).to_be_visible()
            page.locator('.assessment-panel').first.get_by_role('button',name='Inspect plan and result',exact=True).nth(index).click()
            page.get_by_role('button',name='Inspect the preserved assessment',exact=True).click()
            expect(page.get_by_text('Synthetic demonstration, not a real AI evaluation.',exact=False)).to_be_visible()
            expect(page.get_by_text(result['content_hash'],exact=True)).to_be_visible()
            expect(page.get_by_role('heading',name='Outcome summary',exact=True)).to_be_visible()
            assert get(root+'/contributions')['total_issued_atoms']==before
            page.set_viewport_size({'width':390,'height':844})
            expect(page.get_by_role('button',name='Close assessment',exact=True)).to_be_visible()
            print('Prepared synthetic assessment rendered on desktop/mobile; inspection changed no contribution credit.')
        finally:context.close();browser.close()


if __name__=='__main__':main()
