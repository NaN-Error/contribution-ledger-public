"""Read-only signed-out UI smoke for an already-started phase-2 deployment.
Creates anonymous session records, but no accounts/workspaces. Full account
creation is a separate, explicitly opted-in disposable-database test.
"""
import os
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright, expect

def main():
    base = os.environ.get('CL_E2E_BASE_URL', 'http://127.0.0.1:5173')
    if urlsplit(base).hostname not in {'127.0.0.1', 'localhost'}:
        raise SystemExit('This smoke test is restricted to a local deployment.')
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(viewport={'width':1440,'height':1000})
        page = context.new_page(); page.goto(base)
        expect(page.get_by_role('heading', name='Set up your first workspace').or_(page.get_by_role('heading', name='Sign in', exact=True))).to_be_visible(timeout=15000)
        page.get_by_role('link', name='Local setup', exact=True).click()
        expect(page.get_by_role('heading', name='Local setup', exact=True)).to_be_visible()
        expect(page.get_by_role('heading', name='Create the first owner', exact=True)).to_be_visible()
        page.get_by_role('link', name='Back to account access', exact=False).click()
        expect(page.get_by_role('button', name='Use invitation', exact=True)).to_be_visible()
        page.set_viewport_size({'width':390,'height':844})
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), 'Mobile layout overflow'
        page.get_by_role('button', name='Use invitation', exact=True).focus(); page.keyboard.press('Enter')
        expect(page.get_by_label('Invitation token', exact=True)).to_be_visible()
        page.get_by_role('button', name='Account recovery', exact=True).click()
        expect(page.get_by_label('Recovery token', exact=True)).to_be_visible()
        assert context.request.get(base+'/api/v1/workspaces').status == 401
        assert context.request.get(base+'/api/v1/system/status').status == 200
        browser.close()
    print('Signed-out UI smoke passed: account gate, local setup, invitation/recovery navigation, anonymous access denied, mobile width.')

if __name__ == '__main__': main()
