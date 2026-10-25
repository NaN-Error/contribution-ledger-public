"""Opt-in real-browser credit acceptance against an existing synthetic review.

Executed by feature_acceptance.py with isolated synthetic fixtures.
Use a disposable running local *_test database with development tools enabled.
Manually prepare one synthetic package, captured evidence and a review assigned
only to the configured independent reviewer (policy quorum 1, no votes yet).
Set CL_E2E_ALLOW_CREDIT=1, CL_E2E_WORKSPACE_ID, CL_E2E_PROJECT_ID,
CL_E2E_REVIEW_ID, CL_E2E_REVIEWER_EMAIL, CL_E2E_REVIEWER_PASSWORD locally;
CL_E2E_BASE_URL defaults to http://127.0.0.1:5173. Standard CL_DB_* settings
must describe that disposable deployment. No credentials are printed/saved.

Run from root: python tests/e2e/credit_smoke.py
This creates synthetic accepted units and a dispute; it never resets/deletes data.
It must not be directed at a real team or real compensation decisions.
"""
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID
from playwright.sync_api import sync_playwright, expect
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'apps/api'))
from app.core.config import get_settings


def main():
    if os.environ.get('CL_E2E_ALLOW_CREDIT')!='1':raise SystemExit('Explicit synthetic credit-smoke opt-in required.')
    settings=get_settings();settings.require_development_tools()
    if not settings.db_name.endswith('_test'):raise SystemExit('Only a disposable *_test deployment is permitted.')
    base=os.environ.get('CL_E2E_BASE_URL','http://127.0.0.1:5173')
    if urlsplit(base).hostname not in {'localhost','127.0.0.1'}:raise SystemExit('Only a local browser target is permitted.')
    workspace=UUID(os.environ['CL_E2E_WORKSPACE_ID']);project=UUID(os.environ['CL_E2E_PROJECT_ID']);rid=UUID(os.environ['CL_E2E_REVIEW_ID'])
    root=base+f'/api/v1/workspaces/{workspace}/projects/{project}'
    with sync_playwright() as pw:
        browser=pw.chromium.launch();context=browser.new_context(viewport={'width':1280,'height':1000})
        page=context.new_page();page.goto(base)
        page.get_by_label('Email',exact=True).fill(os.environ['CL_E2E_REVIEWER_EMAIL'])
        page.get_by_label('Password',exact=True).fill(os.environ['CL_E2E_REVIEWER_PASSWORD'])
        page.locator('form').get_by_role('button',name='Sign in',exact=True).click()
        page.get_by_role('link',name='Workspaces',exact=True).click()
        expect(page.get_by_role('heading',name='Your workspaces',exact=True)).to_be_visible()
        work=context.request.get(base+f'/api/v1/workspaces/{workspace}').json()
        project_info=context.request.get(root).json();review=context.request.get(root+f'/reviews/{rid}').json()
        assert any(marker in project_info['name'].lower() for marker in ('synthetic','smoke')), 'Use a clearly labeled synthetic project.'
        assert review['kind']=='award' and review['minimum_reviewers']==1 and review['can_decide'] and not review['decisions']
        assert review['state']=='awaiting_decisions'
        page.get_by_role('button',name=work['name']+' Open projects',exact=False).click()
        page.locator('button.project-card').filter(has=page.get_by_text(project_info['name'],exact=True)).click()
        page.get_by_role('button',name='Human reviews',exact=True).click()
        page.locator('.work-history').filter(has=page.get_by_text(review['target']['title'],exact=True)).first.get_by_role('button',name='Inspect review',exact=True).click()
        expect(page.get_by_text(review['target_hash'],exact=True)).to_be_visible()
        # A human preconfigures this synthetic packet; fixture acceptance is not
        # claimed to evaluate the truth of real source material.
        reference=next(s['ref'] for s in review['target']['evidence_sources'] if s.get('ref'))
        form=page.locator('section.panel').filter(has=page.get_by_role('heading',name='Your independent decision',exact=True))
        for n,_ in enumerate(review['target']['criteria'],1):
            form.get_by_label(f'Finding {n}',exact=True).select_option('supported')
            form.get_by_label(f'Supporting references for finding {n}',exact=True).select_option([reference])
            form.get_by_label(f'Explanation for finding {n}',exact=True).fill('The supplied synthetic fixture supports this acceptance-test criterion.')
        form.get_by_label('Review decision',exact=True).select_option('accept')
        form.get_by_label('Reason for your decision',exact=True).fill('Synthetic browser test of explicit independent review; not real compensation.')
        for check in form.get_by_role('checkbox').all():check.check()
        before=context.request.get(root+'/contributions').json()['total_issued_atoms']
        form.get_by_role('button',name='Record independent decision',exact=True).click()
        final=page.locator('section.panel').filter(has=page.get_by_role('heading',name='Finalize the reviewed decision set',exact=True))
        expect(final).to_be_visible();assert context.request.get(root+'/contributions').json()['total_issued_atoms']==before
        final.get_by_label('Finalization reason',exact=True).fill('Explicitly finalize this disposable synthetic credit fixture once.')
        final.get_by_role('checkbox').check();final.get_by_role('button',name='Finalize human-reviewed record',exact=True).click()
        expect(page.get_by_text('finalized',exact=True)).to_be_visible()
        after=context.request.get(root+'/contributions').json();assert after['total_issued_atoms']==before+review['target']['budget_atoms']
        page.get_by_role('button',name='Contributions',exact=True).click()
        expect(page.get_by_role('heading',name='Recognized contribution credit',exact=True)).to_be_visible()
        page.locator('.work-history').filter(has=page.get_by_text(review['target']['title'],exact=True)).first.get_by_role('button',name='Inspect credit history',exact=True).click()
        page.get_by_role('button',name='Raise an attribution concern',exact=True).click()
        page.get_by_label('Reason for disputing the award',exact=True).fill('Synthetic appeal records an issue without automatically changing credit.')
        page.get_by_role('button',name='Open credit dispute',exact=True).click()
        expect(page.get_by_text('Dispute recorded. Continue in the project Disputes section.',exact=True)).to_be_visible()
        page.get_by_role('button',name='Disputes',exact=True).click();expect(page.get_by_role('heading',name='Credit disputes',exact=True)).to_be_visible()
        assert context.request.get(root+'/contributions').json()['open_dispute_count']>=1
        assert context.request.get(root+'/contributions').json()['total_issued_atoms']==after['total_issued_atoms']
        browser.close()
    print('Synthetic browser credit flow passed: human decision, separate exact award, preserved credit and dispute creation. No payments sent.')

if __name__=='__main__':main()
