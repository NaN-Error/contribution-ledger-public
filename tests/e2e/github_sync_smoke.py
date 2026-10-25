"""Actual browser disabled-integration shell; run by accounts_smoke.

No mocking of a passing enabled/live workflow, no external requests and no keys.
"""
from playwright.sync_api import expect

def exercise_sync_shell(owner,viewer,base,workspace_id):
    owner.get_by_role('link',name='Workspaces',exact=True).click();owner.reload()
    expect(owner.get_by_role('heading',name='Your workspaces',exact=True)).to_be_visible()
    owner.get_by_role('button',name='Smoke workspace Open projects',exact=False).click()
    owner.get_by_role('button',name='Smoke game',exact=False).first.click()
    owner.get_by_role('button',name='GitHub',exact=True).click()
    owner.get_by_role('button',name='Synchronization',exact=True).click()
    expect(owner.get_by_role('heading',name='Synchronization and recovery',exact=True)).to_be_visible()
    expect(owner.locator('body')).to_contain_text('Scheduler deployment: disabled')
    expect(owner.get_by_text('Connect and select a repository first.',exact=True)).to_be_visible()
    for label in ['Jobs and retries','Signed deliveries','Latest observations']:
        owner.get_by_role('button',name=label,exact=True).click()
        expect(owner.get_by_role('heading',name='Synchronization and recovery',exact=True)).to_be_visible()
    projects=owner.context.request.get(base+f'/api/v1/workspaces/{workspace_id}/projects').json()['items']
    project=next(p for p in projects if p['name']=='Smoke game')
    response=viewer.context.request.get(base+f"/api/v1/workspaces/{workspace_id}/projects/{project['id']}/github/sync")
    assert response.status==403,'A project viewer must not read raw integration data.'
