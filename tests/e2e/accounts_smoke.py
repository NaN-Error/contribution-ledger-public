"""Actual account UI test against a fresh, disposable, local native deployment.

Explicitly creates synthetic accounts and audit records; DOES NOT clean them
by deleting production data. Requires a *_test DB, development tools enabled,
CL_E2E_ALLOW_ACCOUNT_CREATION=1, and an unbootstrapped installation. Secrets
exist in process memory only and are never printed or saved as screenshots.
"""
import os
import secrets
import sys
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright, expect
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'apps/api'))
from app.core.config import get_settings
from app.db.session import Database
from app.auth.operator import setup_token
from planning_smoke import exercise_planning
from work_packages_smoke import exercise_work_packages
from github_sync_smoke import exercise_sync_shell
from ai_smoke import exercise_ai
from onboarding_smoke import exercise_onboarding


def main():
    if os.environ.get('CL_E2E_ALLOW_ACCOUNT_CREATION') != '1':
        raise SystemExit('Opt in only for a fresh disposable test deployment: CL_E2E_ALLOW_ACCOUNT_CREATION=1.')
    settings = get_settings(); settings.require_development_tools()
    if not settings.db_name.endswith('_test'):
        raise SystemExit('Account UI tests require a disposable database name ending in _test.')
    base = os.environ.get('CL_E2E_BASE_URL','http://127.0.0.1:5173')
    if urlsplit(base).hostname not in {'localhost','127.0.0.1'}:
        raise SystemExit('Only local browser targets are permitted.')
    db = Database(settings)
    try: token = setup_token(db)
    finally: db.dispose()
    password = secrets.token_urlsafe(24)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        owner_context = browser.new_context(viewport={'width':1440,'height':1100})
        owner = owner_context.new_page(); owner.goto(base)
        owner.get_by_label('Setup token', exact=True).fill(token)
        owner.get_by_label('Display name', exact=True).fill('Smoke owner')
        owner.get_by_label('Email', exact=True).fill('smoke-owner@example.test')
        owner.get_by_label('New password', exact=True).fill(password)
        owner.get_by_label('Confirm new password', exact=True).fill(password)
        owner.get_by_label('Workspace name', exact=True).fill('Smoke workspace')
        owner.get_by_label('First project name', exact=True).fill('Smoke game')
        owner.get_by_label('Project timezone', exact=True).fill('America/Puerto_Rico')
        owner.get_by_role('button', name='Create owner and workspace', exact=True).click()
        expect(owner.get_by_role('heading', name='Repository dashboard', exact=True)).to_be_visible()
        owner.get_by_role('link', name='Workspaces', exact=True).click()
        expect(owner.get_by_role('heading', name='Your workspaces', exact=True)).to_be_visible()
        exercise_onboarding(owner)
        # Create a second private workspace; membership in the first never grants access.
        owner.get_by_label('New workspace name', exact=True).fill('Private second workspace')
        owner.get_by_role('button', name='Create workspace', exact=True).click()
        expect(owner.get_by_role('heading', name='Private second workspace', exact=True)).to_be_visible()
        all_ws = owner_context.request.get(base+'/api/v1/workspaces').json()['items']
        first = next(w for w in all_ws if w['name']=='Smoke workspace')
        private = next(w for w in all_ws if w['name']=='Private second workspace')
        owner.get_by_role('button', name='All workspaces', exact=False).click()
        owner.get_by_role('button', name='Smoke workspace Open projects', exact=False).click()
        owner.get_by_role('button', name='Invitations', exact=True).click()
        owner.get_by_label('Invited email', exact=True).fill('smoke-viewer@example.test')
        owner.get_by_label('Initial project', exact=True).select_option(label='Smoke game')
        owner.get_by_label('Project role', exact=True).select_option('viewer')
        owner.get_by_label('Reason for inviting this collaborator', exact=True).fill('Synthetic browser acceptance case')
        owner.get_by_role('button', name='Create invitation', exact=True).click()
        link = owner.get_by_label('One-time invitation link', exact=True)
        expect(link).to_be_visible(); invite_url = link.input_value()
        viewer_context = browser.new_context(viewport={'width':390,'height':844})
        viewer = viewer_context.new_page(); viewer.goto(invite_url)
        viewer.get_by_role('button', name='Check invitation', exact=True).click()
        viewer.get_by_label('Display name', exact=True).fill('Smoke viewer')
        viewer.get_by_label('New password', exact=True).fill(password)
        viewer.get_by_label('Confirm new password', exact=True).fill(password)
        viewer.get_by_role('button', name='Accept invitation', exact=True).click()
        expect(viewer.get_by_role('heading', name='Repository dashboard', exact=True)).to_be_visible()
        viewer.get_by_role('link', name='Workspaces', exact=True).click()
        expect(viewer.get_by_role('heading', name='Your workspaces', exact=True)).to_be_visible()
        assert '#invite/' not in viewer.url
        assert viewer_context.request.get(base+f"/api/v1/workspaces/{private['id']}").status == 404
        assert viewer_context.request.get(base+f"/api/v1/workspaces/{first['id']}/members").status == 403
        viewer.get_by_role('button', name='Smoke workspace Open projects', exact=False).click()
        expect(viewer.get_by_role('button', name='Invitations', exact=True)).to_have_count(0)
        viewer.get_by_role('button', name='Smoke game No description', exact=False).click()
        viewer.get_by_role('button', name='Settings and access', exact=True).click()
        expect(viewer.get_by_role('heading', name='Project details', exact=True)).to_be_visible()
        expect(viewer.get_by_role('button', name='Save project settings', exact=True)).to_have_count(0)
        assert viewer.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), 'Mobile layout overflow'
        exercise_planning(owner, viewer, base, first['id'])
        exercise_work_packages(owner, viewer, base, first['id'])
        exercise_sync_shell(owner, viewer, base, first['id'])
        exercise_ai(owner, viewer, base, first['id'])
        # Signed-in real status UI, including failed fetch clearing old success.
        owner.get_by_role('link', name='System overview', exact=True).click()
        expect(owner.get_by_role('heading', name='Connected', exact=True)).to_be_visible(timeout=15000)
        owner.route('**/api/v1/system/status', lambda route: route.abort())
        owner.get_by_role('button', name='Refresh status', exact=True).click()
        expect(owner.get_by_role('heading', name='Not connected', exact=True)).to_be_visible()
        owner.unroute('**/api/v1/system/status')
        owner.get_by_role('button', name='Refresh status', exact=True).click()
        expect(owner.get_by_role('heading', name='Responding', exact=True)).to_be_visible()
        owner.get_by_role('link', name='Project roadmap', exact=True).click()
        owner.get_by_label('Filter the roadmap', exact=True).fill('no_matching_phase')
        expect(owner.get_by_role('heading', name='No matching phases', exact=True)).to_be_visible()
        # A workspace suspension revokes the browser session; a reload clears access.
        owner.get_by_role('link', name='Workspaces', exact=True).click()
        # Component state may retain the workspace; normalize via reload.
        owner.reload(); expect(owner.get_by_role('heading', name='Your workspaces', exact=True)).to_be_visible()
        owner.get_by_role('button', name='Smoke workspace Open projects', exact=False).click()
        owner.get_by_role('button', name='Team access', exact=True).click()
        row = owner.locator('details.member-row').filter(has=owner.get_by_text('Smoke viewer', exact=True))
        row.locator('summary').click(); row.get_by_label('Access', exact=True).select_option('suspended')
        row.get_by_label('Reason for this change', exact=True).fill('Synthetic browser suspension verification')
        row.get_by_role('button', name='Save access change', exact=True).click()
        expect(row.locator('summary')).to_contain_text('suspended')
        viewer.reload(); expect(viewer.get_by_role('heading', name='Sign in', exact=True)).to_be_visible()
        assert viewer_context.request.get(base+f"/api/v1/workspaces/{first['id']}/projects").status == 401
        if os.environ.get('CL_E2E_ALLOW_MFA_ENROLLMENT') == '1':
            from mfa_smoke import exercise_mfa
            exercise_mfa(owner,owner_context,base,password)
        browser.close()
    print('Account UI smoke passed: first-owner setup, private workspace isolation, viewer invitation, read-only project, policy revisions and acknowledgements, budget preview/approval/overspend, work-package deliverables/attribution/submission/amendment/cancellation, status outage/recovery, roadmap, suspension and session revocation.')

if __name__ == '__main__': main()
