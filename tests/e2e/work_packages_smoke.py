"""Phase-4 browser acceptance source, invoked only by the opted-in local smoke.

Reuses the fictional account/planning fixture, creates no real compensation,
and never resets the database. Requires an actually built frontend. This file
being present is not evidence that a browser test was executed.
"""
from playwright.sync_api import Page, expect
from planning_smoke import metric
from evidence_smoke import add_evidence_before_submit,revise_submitted_evidence,inspect_as_viewer


def change_state(page: Page, action: str, label: str, reason: str):
    panel=page.locator('section.panel').filter(has=page.get_by_role('heading',name='Review the scope before changing its state',exact=True))
    panel.get_by_label('Work-package action',exact=True).select_option(action)
    panel.get_by_label('Submission note' if action=='submit' else 'Reason for this action',exact=True).fill(reason)
    panel.get_by_role('checkbox').check()
    panel.get_by_role('button',name=label,exact=True).click()


def exercise_work_packages(owner: Page, viewer: Page, base: str, workspace_id: str):
    projects=owner.context.request.get(base+f'/api/v1/workspaces/{workspace_id}/projects').json()['items']
    pid=next(p['id'] for p in projects if p['name']=='Smoke game')
    root=base+f'/api/v1/workspaces/{workspace_id}/projects/{pid}'
    uid=owner.context.request.get(base+'/api/v1/auth/session').json()['user']['id']
    owner.get_by_role('button',name='Work packages',exact=True).click()
    owner.get_by_role('button',name='Create work package',exact=True).click()
    owner.get_by_label('Work-package title',exact=True).fill('Synthetic reconnection work')
    owner.get_by_label('Useful outcome',exact=True).fill('Restore a synthetic player session after a temporary disconnection.')
    owner.get_by_label('Package acceptance criteria — one per line',exact=True).fill('Reconnect without creating a duplicate session.\nRestore the saved state and document the behavior.')
    owner.get_by_label('Required evidence',exact=True).fill('A reproducible test report, source revision and reviewed integration guide.')
    for n,(title,units,role) in enumerate([('Reconnection behavior','420','implementation'),('Reconnection tests','175','testing'),('Integration guide','105','documentation')],start=1):
        owner.get_by_role('button',name='Add deliverable',exact=True).click()
        owner.get_by_label(f'Deliverable {n} title',exact=True).fill(title)
        owner.get_by_label(f'Deliverable {n} outcome',exact=True).fill('Produce the independently reviewable synthetic '+title.lower()+'.')
        owner.get_by_label(f'Deliverable {n} criteria — one per line',exact=True).fill('The documented synthetic acceptance case can be reproduced.')
        owner.get_by_label(f'Deliverable {n} evidence requirements',exact=True).fill('Provide a dated report and versioned source reference.')
        owner.get_by_label(f'Deliverable {n} budget in units',exact=True).fill(units)
        mode='percent' if n==2 else 'units'
        owner.get_by_label(f'Deliverable {n} attribution method',exact=True).select_option(mode)
        owner.locator('fieldset.work-deliverable').nth(n-1).get_by_role('button',name='Add proposed attribution',exact=True).click()
        owner.get_by_label(f'Deliverable {n}, attribution 1 contributor',exact=True).select_option(uid)
        owner.get_by_label(f'Deliverable {n}, attribution 1 role',exact=True).select_option(role)
        owner.get_by_label(f'Deliverable {n}, attribution 1 {"percent" if mode=="percent" else "units"}',exact=True).fill('100' if mode=='percent' else units)
    owner.get_by_label('Reason for this scope revision',exact=True).fill('Define the synthetic browser review scope and planned attribution.')
    owner.get_by_role('button',name='Save work-package draft',exact=True).click()
    expect(owner.get_by_role('heading',name='Synthetic reconnection work',exact=True)).to_be_visible()
    expect(metric(owner,'Package budget')).to_have_text('700')
    expect(metric(owner,'Issued credit')).to_have_text('0')
    change_state(owner,'approve_scope','Approve this scope for work','Review and approve only the fictional planning scope.')
    expect(owner.get_by_label('Work-package action',exact=True)).to_have_value('start')
    change_state(owner,'start','Start work','Start the approved synthetic work package.')
    expect(owner.get_by_label('Work-package action',exact=True)).to_have_value('submit')
    add_evidence_before_submit(owner)
    change_state(owner,'submit','Submit readiness declaration','Declare this synthetic scope ready; no evidence is accepted yet.')
    expect(owner.get_by_role('button',name='Inspect submission',exact=True)).to_have_count(1)
    revise_submitted_evidence(owner,root,change_state)
    collection=owner.context.request.get(root+'/work-packages').json()['items'];item=collection[0]
    assert item['state']=='submitted' and item['issued_atoms']==0
    viewer.get_by_role('button',name='Work packages',exact=True).click()
    expect(viewer.get_by_role('button',name='Create work package',exact=True)).to_have_count(0)
    viewer.get_by_role('button',name='Synthetic reconnection work',exact=False).click()
    expect(viewer.get_by_role('heading',name='Synthetic reconnection work',exact=True)).to_be_visible()
    expect(viewer.get_by_role('button',name='Amend scope',exact=True)).to_have_count(0)
    expect(viewer.get_by_label('Work-package action',exact=True)).to_have_count(0)
    assert viewer.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), 'Work-package mobile overflow'
    inspect_as_viewer(viewer)
    change_state(owner,'withdraw','Withdraw submission for amendment','Revise the fictional scope while preserving the original submission.')
    expect(owner.get_by_role('button',name='Amend scope',exact=True)).to_be_visible()
    owner.get_by_role('button',name='Amend scope',exact=True).click()
    owner.get_by_label('Useful outcome',exact=True).fill('Restore the synthetic session after the specifically documented network interruption.')
    owner.get_by_label('Reason for this scope revision',exact=True).fill('Clarify the synthetic outcome without changing its proposed budget.')
    owner.locator('section.scope-editor').get_by_role('checkbox').last.check()
    owner.get_by_role('button',name='Save scope amendment',exact=True).click()
    expect(owner.get_by_label('Work-package action',exact=True)).to_have_value('approve_scope')
    expect(owner.get_by_role('button',name='Inspect submission',exact=True)).to_have_count(2)
    owner.get_by_role('button',name='Inspect submission',exact=True).first.click()
    expect(owner.get_by_role('heading',name='Archived submission of scope 1',exact=True)).to_be_visible()
    owner.get_by_role('button',name='Close archive',exact=True).click()
    change_state(owner,'cancel','Cancel package and release its budget','Cancel unaccepted synthetic work and release only its planned capacity.')
    expect(owner.get_by_role('heading',name='No state change available',exact=True)).to_be_visible()
    expect(metric(owner,'Issued credit')).to_have_text('0')
    current=owner.context.request.get(root+f"/work-packages/{item['id']}").json()
    assert current['state']=='cancelled' and current['budget_atoms']==0 and current['scope_budget_atoms']==700_000
    assert len(current['recent_submissions'])==2
    milestone=owner.context.request.get(root+'/milestones').json()['items'][0]
    assert milestone['allocated_atoms']==0 and milestone['reserve_floor_atoms']==100_000 and milestone['issued_atoms']==0
    owner.get_by_role('button',name='Back to work packages',exact=True).click()
    owner.get_by_label('Search work packages',exact=True).fill('a_no_matching_work_package')
    expect(owner.get_by_role('heading',name='No matching work packages',exact=True)).to_be_visible()
