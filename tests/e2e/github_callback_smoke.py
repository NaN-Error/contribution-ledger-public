"""Real browser shell/callback smoke. No GitHub requests or real credentials.

Run after building and starting the normal local stack. This does not replace an
operator-approved live installation/import acceptance test.
"""
import os
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright,expect


def main():
    base=os.environ.get('CL_E2E_BASE_URL','http://127.0.0.1:5173')
    parsed=urlsplit(base)
    if parsed.hostname not in {'127.0.0.1','localhost'}:raise SystemExit('Only an explicit local test deployment is permitted.')
    with sync_playwright() as p:
        browser=p.chromium.launch();page=browser.new_page();outbound=[]
        def check(request):
            if urlsplit(request.url).hostname not in {'127.0.0.1','localhost'}:outbound.append(request.url)
        page.on('request',check)
        page.goto(base+'/github/callback?error=synthetic-declined-authorization')
        page.wait_for_url(base+'/#github-callback')
        assert 'synthetic-declined' not in page.url
        expect(page.locator('body')).not_to_contain_text('synthetic-declined-authorization')
        assert not outbound,'The callback smoke must not contact external services.'
        browser.close()
    print('Local browser callback shell passed; live GitHub authorization was not tested.')

if __name__=='__main__':main()
