from tests.phase11_helpers import setup,packet,plan,complete


def test_synthetic_assessment_round_trip(client,database,settings):
    env=setup(client,database,settings)
    p=packet(env)
    assert p['payload']['sources']
    r=complete(env,plan(env,p))
    assert r['status']=='valid',r
    assert all(f['status']=='insufficient' for f in r['document']['findings'])
    assert r['metadata']['synthetic'] is True
    assert client.get(env['path']).json()['state']=='submitted'
