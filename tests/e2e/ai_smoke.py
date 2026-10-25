"""Actual synthetic-only browser flow; no paid calls and no intercepted API responses.

Called from the opt-in disposable accounts_smoke test. The test process advances
one real database-owned job at a time with the synthetic provider, not a hosted AI.
This does not verify the separately privileged deployed worker process.
"""
from playwright.sync_api import expect
from app.core.config import get_settings
from app.db.session import Database
from app.ai.jobs import tick
from app.providers.factory import ProviderFactory
from app.security.secrets.encrypted import EncryptedCredentialStore


def exercise_ai(owner,viewer,base,workspace_id):
    settings=get_settings()
    if settings.ai_live_enabled or settings.ai_paid_probes_enabled:
        raise RuntimeError('Browser fixture requires live providers and paid probes to be disabled.')
    owner.get_by_role('button',name='AI settings',exact=True).click()
    expect(owner.get_by_role('heading',name='AI connections and evaluator settings',exact=True)).to_be_visible()
    owner.get_by_label('Connection label',exact=True).fill('Browser synthetic connection')
    owner.get_by_label('Permission / payer authorization reference',exact=True).fill('No-cost browser fixture authorization only')
    owner.get_by_label('Reason for connection',exact=True).fill('Create a synthetic test connection')
    owner.get_by_label('Authorize project administrators',exact=False).check()
    owner.get_by_role('button',name='Create connection and queue discovery',exact=True).click()
    expect(owner.get_by_role('heading',name='Browser synthetic connection',exact=True)).to_be_visible()
    db=Database(settings)
    store=EncryptedCredentialStore(settings.ai_credential_root,settings.ai_master_key_file)
    try:
        assert tick(db,settings,ProviderFactory(settings),store)
        owner.get_by_role('button',name='Refresh status',exact=True).click()
        owner.get_by_role('button',name='Reload captured catalog',exact=True).click()
        owner.get_by_label('Captured model',exact=True).select_option(label='synthetic-json-v1')
        owner.get_by_text('Add a reviewed price version',exact=True).click()
        owner.get_by_label('Price review reason',exact=True).fill('The synthetic provider has no API charge')
        owner.get_by_role('button',name='Save reviewed price version',exact=True).click()
        expect(owner.get_by_text('Price version saved. Review a new quotation before a paid request.',exact=True)).to_be_visible()
        owner.get_by_role('button',name='Prepare compatibility-test quotation (no generation)',exact=True).click()
        expect(owner.get_by_role('heading',name='Review before requesting a probe',exact=True)).to_be_visible()
        owner.get_by_role('button',name='I approve this reservation and one synthetic probe',exact=True).click()
        expect(owner.get_by_text('Explicit probe queued. Inspect job history after the worker processes it.',exact=True)).to_be_visible()
        assert tick(db,settings,ProviderFactory(settings),store)
        owner.get_by_role('button',name='Reload captured catalog',exact=True).click()
        expect(owner.get_by_text('Create an evaluator-profile draft',exact=True)).to_be_visible()
        owner.get_by_text('Create an evaluator-profile draft',exact=True).click()
        owner.get_by_label('Profile title',exact=True).fill('Browser synthetic evaluator')
        owner.get_by_label('Project data-sharing policy reference and review',exact=True).fill('Synthetic-only reviewed policy; no real project evidence')
        owner.get_by_role('button',name='Save profile draft (not approved)',exact=True).click()
        expect(owner.get_by_text('Profile draft saved. Refresh the profiles list and inspect it before approval.',exact=True)).to_be_visible()
        owner.get_by_role('button',name='Refresh profiles',exact=True).click()
        owner.locator('summary').filter(has_text='Browser synthetic evaluator').click()
        owner.get_by_label('Reason for approving this exact profile',exact=True).fill('Reviewed synthetic model and unchanged data boundary')
        owner.get_by_label('I reviewed the provider, payer authorization',exact=False).check()
        owner.get_by_role('button',name='Approve this configuration prospectively',exact=True).click()
        expect(owner.locator('summary').filter(has_text='Browser synthetic evaluator')).to_contain_text('last approved configuration')
        projects=owner.context.request.get(base+f'/api/v1/workspaces/{workspace_id}/projects').json()['items']
        project=next(p for p in projects if p['name']=='Smoke game')
        root=base+f"/api/v1/workspaces/{workspace_id}/projects/{project['id']}/ai"
        assert viewer.context.request.get(root).json()['connections']==[]
        assert viewer.context.request.get(root+'/profiles').json()['items'][0]['approved']
    finally:db.dispose()
