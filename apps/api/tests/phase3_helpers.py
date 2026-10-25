from tests.auth_helpers import mutation


def base(owner):
    return f"/api/v1/workspaces/{owner['workspace']['id']}/projects/{owner['project']['id']}"


def policy_body(client, root, *, version=0, key=0):
    templates = client.get(root + '/policies/templates')
    assert templates.status_code == 200, templates.text
    return {'expected_latest_version': version, 'title': 'Synthetic contribution policy',
        'rules': templates.json()['items'][key]['rules'],
        'agreement_reference': 'Synthetic test agreement only — no real compensation',
        'reason': 'Define rules for this synthetic test'}


def draft(client, root, *, version=0, key=0):
    result = mutation(client, root + '/policies', policy_body(client, root, version=version, key=key))
    assert result.status_code == 201, result.text
    return result.json()


def approve(client, root, item, **kwargs):
    body = {'expected_latest_version': item['version'], 'reviewed_content_hash': item['content_hash'],
        'examples_reviewed': True, 'reason': 'Approve these reviewed synthetic rules', **kwargs}
    return mutation(client, root + f"/policies/{item['id']}/approve", body)


def acknowledge(client, root, item):
    return mutation(client, root + f"/policies/{item['id']}/acknowledge",
        {'reviewed_content_hash': item['content_hash'], 'reviewed': True})


def ready_policy(client, root, *, version=0, key=0):
    item = draft(client, root, version=version, key=key)
    result = approve(client, root, item); assert result.status_code == 200, result.text
    result = acknowledge(client, root, item); assert result.status_code == 200, result.text
    return result.json()


def milestone(client, root, policy, *, total=1_000_000, reserve=100_000):
    result = mutation(client, root + '/milestones', {'name': 'Synthetic release milestone',
        'policy_id': policy['id'], 'total_atoms': total, 'reserve_floor_atoms': reserve,
        'reason': 'Plan an initial synthetic unit budget'})
    assert result.status_code == 201, result.text
    return result.json()


def decision(client, root, item, proposal, *, choice='approve', expected=None, reviewed_hash=None):
    return mutation(client, root + f"/milestones/{item['id']}/amendments/{proposal['id']}/decision",
        {'decision': choice, 'expected_version': expected or item['version'],
         'reviewed_preview_hash': reviewed_hash or proposal['preview_hash'], 'reason': 'Human review of the exact budget preview'})


def active_milestone(client, root, policy, **kwargs):
    item = milestone(client, root, policy, **kwargs)
    result = decision(client, root, item, item['amendments'][0]); assert result.status_code == 200, result.text
    return result.json()


def proposal(client, root, item, change):
    return mutation(client, root + f"/milestones/{item['id']}/amendments", {
        'expected_version': item['version'], 'change': change, 'reason': 'Propose a documented synthetic budget change'})


def allocate(client, root, item, atoms=200_000, title='Implement reconnect behavior', pool='release', category='code'):
    proposed = proposal(client, root, item, {'kind': 'allocate', 'title': title, 'category': category,
        'pool_key': pool, 'atoms': atoms})
    assert proposed.status_code == 201, proposed.text
    result = decision(client, root, item, proposed.json()); assert result.status_code == 200, result.text
    return result.json()
