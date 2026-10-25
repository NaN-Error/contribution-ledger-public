"""Phase-3 browser flow, called by the explicitly opted-in account smoke test.

Uses its existing synthetic accounts only. No standalone credentials, remote
requests, screenshots, or database reset are introduced here. This is supplied
acceptance-test source; successful execution must be recorded separately.
"""
from playwright.sync_api import Page, expect


def metric(page: Page, label: str):
    return page.locator('.budget-metric').filter(has=page.get_by_text(label, exact=True)).locator('strong')


def approve_newest(page: Page, reason: str):
    proposal = page.locator('details.proposal-record').first
    expect(proposal.locator('summary')).to_contain_text('pending')
    if not proposal.evaluate('(element) => element.open'):
        proposal.locator('summary').click()
    proposal.get_by_label('Decision', exact=True).select_option('approve')
    proposal.get_by_label('Reason for budget decision', exact=True).fill(reason)
    proposal.get_by_role('checkbox').check()
    proposal.get_by_role('button', name='Approve budget change', exact=True).click()
    expect(page.locator('details.proposal-record').first.locator('summary')).to_contain_text('approved')


def exercise_planning(owner: Page, viewer: Page, base: str, workspace_id: str):
    owner.get_by_role('link', name='Workspaces', exact=True).click()
    owner.reload()
    expect(owner.get_by_role('heading', name='Your workspaces', exact=True)).to_be_visible()
    owner.get_by_role('button', name='Smoke workspace Open projects', exact=False).click()
    owner.get_by_role('button', name='Smoke game No description', exact=False).click()
    owner.get_by_role('button', name='Policies', exact=True).click()
    owner.get_by_role('button', name='Review draft example', exact=True).click()
    owner.get_by_label('Policy title', exact=True).fill('Synthetic planning policy')
    owner.get_by_label('Agreement reference', exact=True).fill('Synthetic browser fixture only; not a real agreement')
    owner.get_by_label('Reason for this policy revision', exact=True).fill('Synthetic policy-version acceptance test')
    owner.get_by_role('button', name='Save new policy revision', exact=True).click()
    expect(owner.get_by_role('heading', name='Version 1: Synthetic planning policy', exact=True)).to_be_visible()
    approval = owner.locator('section.panel').filter(has=owner.get_by_role('heading', name='Approve this policy version', exact=True))
    approval.get_by_label('Reason for policy approval', exact=True).fill('Reviewed synthetic template and participant snapshot')
    approval.get_by_role('checkbox').check()
    approval.get_by_role('button', name='Approve policy version 1', exact=True).click()
    acknowledgement = owner.locator('section.panel').filter(has=owner.get_by_role('heading', name='Your acknowledgement', exact=True))
    acknowledgement.get_by_role('checkbox').check()
    acknowledgement.get_by_role('button', name='Acknowledge version 1', exact=True).click()
    expect(owner.get_by_text('Your acknowledgement of version 1 is recorded.', exact=True)).to_be_visible()
    owner.get_by_role('button', name='Milestones', exact=True).click()
    owner.get_by_label('Milestone name', exact=True).fill('Synthetic release milestone')
    owner.get_by_label('Initial total units', exact=True).fill('1000')
    owner.get_by_label('Initial protected reserve units', exact=True).fill('100')
    owner.get_by_label('Reason for initial budget', exact=True).fill('Synthetic release planning budget')
    owner.get_by_role('button', name='Create milestone proposal', exact=True).click()
    expect(metric(owner, 'Approved total')).to_have_text('0')
    approve_newest(owner, 'Reviewed synthetic initial budget without awarding credit')
    expect(metric(owner, 'Approved total')).to_have_text('1,000')
    expect(metric(owner, 'Available to plan')).to_have_text('900')
    editor = owner.locator('section.proposal-editor')
    editor.get_by_label('Planned outcome', exact=True).fill('Synthetic reconnection behavior')
    editor.get_by_label('Planned allocation units', exact=True).fill('700')
    editor.get_by_label('Reason for budget proposal', exact=True).fill('Synthetic outcome planning reservation')
    editor.get_by_role('button', name='Preview budget change', exact=True).click()
    expect(editor.get_by_role('heading', name='Review the proposed effect', exact=True)).to_be_visible()
    expect(metric(owner, 'Planned allocations')).to_have_text('0')
    editor.get_by_role('button', name='Save proposal for approval', exact=True).click()
    expect(owner.locator('details.proposal-record').first.locator('summary')).to_contain_text('pending')
    expect(metric(owner, 'Planned allocations')).to_have_text('0')
    approve_newest(owner, 'Reviewed allocation preview; no contribution credit issued')
    expect(metric(owner, 'Planned allocations')).to_have_text('700')
    expect(metric(owner, 'Available to plan')).to_have_text('200')
    editor = owner.locator('section.proposal-editor')
    editor.get_by_label('Planned outcome', exact=True).fill('Synthetic over-allocation attempt')
    editor.get_by_label('Planned allocation units', exact=True).fill('201')
    editor.get_by_label('Reason for budget proposal', exact=True).fill('Confirm protected reserve cannot be overspent')
    editor.get_by_role('button', name='Preview budget change', exact=True).click()
    expect(editor.get_by_role('alert')).to_contain_text('exceed')
    expect(metric(owner, 'Available to plan')).to_have_text('200')
    owner.get_by_role('button', name='Policies', exact=True).click()
    owner.get_by_role('button', name='Create successor version', exact=True).click()
    owner.get_by_label('Policy title', exact=True).fill('Synthetic successor draft')
    owner.get_by_label('Reason for this policy revision', exact=True).fill('Check acknowledgements are version-specific')
    owner.get_by_role('button', name='Save new policy revision', exact=True).click()
    expect(owner.get_by_role('heading', name='Version 2: Synthetic successor draft', exact=True)).to_be_visible()
    expect(owner.get_by_text('Your acknowledgement of version 2 is recorded.', exact=True)).to_have_count(0)
    expect(owner.get_by_role('heading', name='Approve this policy version', exact=True)).to_be_visible()

    viewer.get_by_role('button', name='Policies', exact=True).click()
    expect(viewer.get_by_role('heading', name='Version 2: Synthetic successor draft', exact=True)).to_be_visible()
    expect(viewer.get_by_role('button', name='Create successor version', exact=True)).to_have_count(0)
    expect(viewer.get_by_role('heading', name='Approve this policy version', exact=True)).to_have_count(0)
    viewer.get_by_role('button', name='Milestones', exact=True).click()
    viewer.get_by_role('button', name='Synthetic release milestone Approved total', exact=False).click()
    expect(metric(viewer, 'Approved total')).to_have_text('1,000')
    expect(metric(viewer, 'Protected reserve')).to_have_text('100')
    expect(viewer.locator('section.proposal-editor')).to_have_count(0)
    expect(viewer.get_by_role('button', name='Approve budget change', exact=True)).to_have_count(0)
    assert viewer.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), 'Planning mobile layout overflow'
    # A draft successor did not edit the previously approved version or issue units.
    projects = owner.context.request.get(base+f'/api/v1/workspaces/{workspace_id}/projects').json()['items']
    project_id = next(p['id'] for p in projects if p['name'] == 'Smoke game')
    root = base+f'/api/v1/workspaces/{workspace_id}/projects/{project_id}'
    policies = owner.context.request.get(root+'/policies').json()['items']
    assert len(policies) == 2 and policies[0]['my_acknowledgement'] is False
    assert policies[1]['my_acknowledgement'] is True
    milestones = owner.context.request.get(root+'/milestones').json()['items']
    assert len(milestones) == 1 and milestones[0]['issued_atoms'] == 0
