"""Read-only onboarding checks called by the existing opted-in account UI smoke.

This file does not create accounts or connect providers. It requires an already
signed-in page in the disposable local browser test, not production credentials.
"""
from playwright.sync_api import expect


def exercise_onboarding(page):
    mutations = []
    def track(request):
        if '/api/v1/' in request.url and request.method not in {'GET', 'HEAD', 'OPTIONS'}:
            mutations.append(request.method)
    page.on('request', track)
    try:
        page.get_by_role('link', name='Getting started', exact=True).click()
        expect(page.get_by_role('heading', name='Getting started', exact=True)).to_be_visible()
        expect(page.get_by_role('heading', name='Budget a useful outcome', exact=True)).to_be_visible()
        expect(page.get_by_role('heading', name='Connect only authorized repository evidence', exact=True)).to_have_count(0)
        page.get_by_label('Find a setup step', exact=True).fill('no_such_setup_step')
        expect(page.get_by_role('heading', name='No matching setup steps', exact=True)).to_be_visible()
        page.get_by_role('button', name='Clear filter', exact=True).click()
        page.get_by_label('Choose your starting path', exact=True).select_option('existing')
        expect(page.get_by_role('heading', name='Connect only authorized repository evidence', exact=True)).to_be_visible()
        expect(page.get_by_role('heading', name='Review historical candidates and missing work', exact=True)).to_be_visible()
        page.set_viewport_size({'width':390, 'height':844})
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), 'Onboarding mobile overflow'
        page.get_by_label('Find a setup step', exact=True).focus()
        page.keyboard.type('evidence')
        expect(page.get_by_role('heading', name='Attach evidence and submit the exact version', exact=True)).to_be_visible()
        assert not mutations, 'Guide navigation unexpectedly wrote project state'
    finally:
        page.remove_listener('request', track)
        page.set_viewport_size({'width':1440, 'height':1100})
    page.get_by_role('link', name='Open workspaces', exact=True).click()
    expect(page.get_by_role('heading', name='Your workspaces', exact=True)).to_be_visible()
