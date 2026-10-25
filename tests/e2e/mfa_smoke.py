"""Opt-in factor UI exercise for the disposable account smoke; never capture secrets."""
import base64
import time
from playwright.sync_api import expect
from app.auth.mfa_crypto import totp


def exercise_mfa(page,context,base,password):
    page.get_by_role('link',name='Account and sessions',exact=True).click()
    factor=page.locator('section.panel').filter(has=page.get_by_role('heading',name='Authenticator protection',exact=True))
    factor.get_by_label('Current password',exact=True).fill(password)
    factor.get_by_role('button',name='Begin enrollment',exact=True).click()
    key=factor.get_by_label('Private authenticator setup key',exact=True)
    expect(key).to_be_visible()
    value=key.input_value();secret=base64.b32decode(value+'='*((-len(value))%8))
    factor.get_by_label('Code from your authenticator',exact=True).fill(totp(secret,int(time.time())//30))
    factor.get_by_role('button',name='Confirm authenticator',exact=True).click()
    expect(page.get_by_role('heading',name='Save your recovery codes',exact=True)).to_be_visible()
    codes=page.get_by_label('Private single-use recovery codes',exact=True).inner_text().splitlines()
    assert len(codes)==10 and len(set(codes))==10
    page.get_by_role('checkbox',name='I have saved these codes privately.',exact=True).check()
    page.get_by_role('button',name='Continue',exact=True).click()
    page.get_by_role('button',name='Sign out',exact=True).click()
    page.get_by_label('Email',exact=True).fill('smoke-owner@example.test')
    page.get_by_label('Password',exact=True).fill(password)
    page.locator('form').get_by_role('button',name='Sign in',exact=True).click()
    expect(page.get_by_role('heading',name='Finish signing in',exact=True)).to_be_visible()
    assert context.request.get(base+'/api/v1/workspaces').status==401
    page.get_by_label('Authenticator or unused recovery code',exact=True).fill(codes[0])
    page.get_by_role('button',name='Verify and sign in',exact=True).click()
    expect(page.get_by_role('link',name='Account and sessions',exact=True)).to_be_visible()
    assert context.request.get(base+'/api/v1/workspaces').status==200
    # Do not log, screenshot, persist or attach the secrets to a browser report.
    print('Opt-in MFA browser drill completed: enrolled, code accepted, password-only project access denied, recovery login accepted.')
