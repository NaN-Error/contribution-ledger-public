from tests.phase6_helpers import *


def test_complete_human_award_and_linked_correction(client,database,settings):
    env=environment(client,database,settings)
    review=assign(env)
    assert review['state']=='awaiting_decisions'
    review=vote(env,review)
    assert review['state']=='ready_to_finalize'
    assert client.get(env['root']+'/contributions').json()['total_issued_atoms']==0
    final=finalize(env,review)
    assert final['state']=='finalized'
    assert client.get(env['path']).json()['state']=='completed'
    contributions=client.get(env['root']+'/contributions').json()
    assert contributions['total_issued_atoms']==100000
    assert contributions['groups'][0]['people'][0]['atoms']==100000
    dispute=resolver(env,open_dispute(env,final))
    assert client.get(env['root']+'/contributions').json()['groups'][0]['close_blocked']
    proposal=correction(env,dispute)
    voted=vote(env,proposal,who='resolver')
    resolved=finalize(env,voted,who='resolver')
    assert resolved['state']=='finalized'
    view=client.get(env['root']+'/contributions/awards/'+final['finalized_record_id']).json()
    assert sorted(e['atoms'] for e in view['current_attributions'])==[40000,60000]
    assert view['original_attributions'][0]['atoms']==100000
    assert sum(e['delta_atoms'] for e in view['events'])==100000
    assert len(view['events'])==3
    assert client.get(env['root']+'/contributions/integrity').json()['consistent']
    assert not client.get(env['root']+'/contributions').json()['groups'][0]['close_blocked']
