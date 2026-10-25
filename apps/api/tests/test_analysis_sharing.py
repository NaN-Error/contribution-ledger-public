"""Real commands and scoped reads of reviewed, immutable draft disclosures."""
from uuid import UUID, uuid4
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, func, text
from sqlalchemy.exc import DBAPIError
from app.main import create_app
from app.auth.models import User
from app.auth.service import create_session
from app.projects.models import WorkspaceMembership, ProjectMembership
from app.analysis.models import AnalysisPublication, AnalysisPublicationRevocation
from app.ledger.models import CreditAward
from app.policies.service import digest
from tests.auth_helpers import mutation
from tests.test_repository_analysis import analysis_env, start, finish, post, change, dash, manual


def member(e, role='contributor'):
    wid, pid = UUID(e['owner']['workspace']['id']), UUID(e['owner']['project']['id'])
    with e['database'].session() as db:
        user = User(id=uuid4(), email=uuid4().hex+'@example.test', display_name=role,
            password_hash=db.get(User, UUID(e['owner']['user']['id'])).password_hash)
        db.add(user); db.flush()
        db.add(WorkspaceMembership(workspace_id=wid, user_id=user.id, role='member', status='active', version=1)); db.flush()
        db.add(ProjectMembership(workspace_id=wid, project_id=pid, user_id=user.id, role=role, status='active', version=1)); db.flush()
        _, token = create_session(db,user,e['settings']); db.commit(); uid = user.id
    client = TestClient(create_app(e['settings'],e['database']),raise_server_exceptions=True)
    client.cookies.set(e['settings'].session_cookie_name,token)
    return uid, client


def sharing_command(e, rid):
    response = e['client'].get(e['root']+'/sharing/preview',params={'report_id':rid})
    assert response.status_code == 200,response.text
    view = response.json()
    return {'request_id':str(uuid4()), 'report_id':rid, 'expected_version':view['document']['draft_version'],
        'reviewed_hash':view['review_hash'], 'sharing_confirmed':True,
        'reason':'Reviewed exact synthetic identities, excerpts and proposals for current project members.'}, view


def test_shared_snapshot_excludes_private_management_and_later_edits(analysis_env):
    e = analysis_env; row = finish(e,start(e)); manual(e)
    hidden = dash(e)['manual_entries'][0]['id']
    post(e,'/manual/disposition',change(e,contribution_id=hidden,status='excluded'))
    post(e,'/scenario',change(e,amount_cents=100003))
    body, view = sharing_command(e,row['id'])
    doc = view['document']
    assert digest(doc) == view['review_hash'] and doc['manual_entries'] == [] and doc['aliases'] == {}
    assert 'Character concept artwork' not in str(doc) and 'Cyra' not in str(doc)
    assert 'recognized' not in doc and 'never disclose' not in str(doc)
    assert 'progress' not in doc and 'definitions' not in doc
    shared = post(e,'/sharing',body,201); assert post(e,'/sharing',body,201)['replayed']
    _, peer = member(e)
    try:
        assert peer.get(e['root']).status_code == 403
        response = peer.get(e['root']+'/shared',params={'publication_id':shared['publication_id']})
        assert response.status_code == 200,response.text
        d = response.json()['dashboard']; assert d['outcomes'] == doc['outcomes']
        assert d['scenario']['amount_cents'] == 100003 and d['recognized']['groups'] == []
        assert not response.json()['can_manage'] and not response.json()['runs'] and not response.json()['imports']
        post(e,'/scenario',change(e,amount_cents=99999))
        post(e,'/manual/disposition',change(e,contribution_id=hidden,status='proposed'))
        frozen = peer.get(e['root']+'/shared').json()['dashboard']
        assert frozen['scenario']['amount_cents'] == 100003 and frozen['outcomes'] == doc['outcomes']
        assert frozen['draft_version'] == doc['draft_version']
        with e['database'].session() as db:
            assert db.scalar(select(func.count()).select_from(AnalysisPublication)) == 1
            assert db.scalar(select(func.count()).select_from(CreditAward)) == 0
    finally: peer.close()


def test_share_requires_current_exact_review_confirmation_and_admin(analysis_env):
    e=analysis_env; row=finish(e,start(e)); body,view=sharing_command(e,row['id'])
    forged={**body,'reviewed_hash':'0'*64}
    assert mutation(e['client'],e['root']+'/sharing',forged).status_code==409
    assert mutation(e['client'],e['root']+'/sharing',{**body,'sharing_confirmed':False}).status_code==422
    post(e,'/scenario',change(e,amount_cents=7))
    assert mutation(e['client'],e['root']+'/sharing',body).status_code==409
    body,_=sharing_command(e,row['id']);pub=post(e,'/sharing',body,201)
    assert mutation(e['client'],e['root']+'/sharing',{**body,'reason':'A different reason for the reused request.'}).status_code==409
    for role in ('contributor','reviewer','viewer','finance'):
        _,peer=member(e,role)
        try:
            assert peer.get(e['root']+'/sharing/preview',params={'report_id':row['id']}).status_code==403
            assert mutation(peer,e['root']+'/sharing',body).status_code==403
            assert peer.get(e['root']+'/sharing/history').status_code==403
            assert peer.get(e['root']+'/shared').status_code==200
            assert mutation(peer,e['root']+'/sharing/'+pub['publication_id']+'/revoke',
                {'request_id':str(uuid4()),'reason':'A synthetic attempt without administrator authority.'}).status_code==403
        finally:peer.close()


def test_revocation_and_current_membership_preserve_history_and_scope(analysis_env):
    e=analysis_env;row=finish(e,start(e));body,_=sharing_command(e,row['id']);pub=post(e,'/sharing',body,201)
    uid,peer=member(e,'viewer')
    try:
        wrong=e['root'].replace(e['owner']['project']['id'],str(uuid4()))
        assert peer.get(wrong+'/shared',params={'publication_id':pub['publication_id']}).status_code==404
        assert peer.get(e['root']+'/shared',params={'publication_id':str(uuid4())}).status_code==404
        with e['database'].session() as db:
            db.get(ProjectMembership,(UUID(e['owner']['workspace']['id']),UUID(e['owner']['project']['id']),uid)).status='suspended';db.commit()
        assert peer.get(e['root']+'/shared').status_code==404
        with e['database'].session() as db:
            db.get(ProjectMembership,(UUID(e['owner']['workspace']['id']),UUID(e['owner']['project']['id']),uid)).status='active';db.commit()
        revoke={'request_id':str(uuid4()),'reason':'Withdraw this reviewed snapshot from project-member access.'}
        path='/sharing/'+pub['publication_id']+'/revoke'
        assert not post(e,path,revoke)['replayed'] and post(e,path,revoke)['replayed']
        assert peer.get(e['root']+'/shared',params={'publication_id':pub['publication_id']}).status_code==404
        assert peer.get(e['root']+'/shared').json()['shared']['items']==[]
        assert peer.get(e['root']+'/shared').json()['dashboard']['outcomes']==[]
        history=e['client'].get(e['root']+'/sharing/history').json()['items']
        assert history[0]['revoked_at'] and history[0]['revocation_reason']==revoke['reason']
        body,_=sharing_command(e,row['id']);fresh=post(e,'/sharing',body,201)
        assert peer.get(e['root']+'/shared').json()['shared']['publication_id']==fresh['publication_id']
        with e['database'].session() as db:
            assert db.scalar(select(func.count()).select_from(AnalysisPublication))==2
            assert db.scalar(select(func.count()).select_from(AnalysisPublicationRevocation))==1
        for sql in ["UPDATE analysis_publications SET document='{}'",'DELETE FROM analysis_publications',
            "UPDATE analysis_publication_revocations SET reason='erase'",'DELETE FROM analysis_publication_revocations']:
            with pytest.raises(DBAPIError),e['database'].engine.begin() as c:c.execute(text(sql))
    finally:peer.close()


def test_shared_denominator_retains_unassigned_and_included_manual_work(analysis_env):
    e=analysis_env;row=finish(e,start(e));d=dash(e);o=d['outcomes'][0]
    post(e,'/proposals',change(e,report_id=row['id'],outcome_id=o['id'],proposed_atoms=3000,
        entries=[{'contributor_key':'github:1','atoms':1000}],rationale='Three outcome units with two deliberately unassigned until review.'))
    manual(e);post(e,'/scenario',change(e,amount_cents=100003))
    body,view=sharing_command(e,row['id']);pub=post(e,'/sharing',body,201)
    _,peer=member(e)
    try:
        d=peer.get(e['root']+'/shared').json()['dashboard']
        assert d['proposed_denominator_atoms']==4000 and d['unassigned_atoms']==2000
        assert d['scenario']['allocated_cents']+d['scenario']['unallocated_cents']==100003
        assert all(p['share']['denominator']==4000 for p in d['contributors'])
        assert any(o['origin']=='manual' for o in d['outcomes']) and not d['manual_entries']
        assert all(p['outcome_ids'] for p in d['contributors'])
        assert d['outcomes']==view['document']['outcomes']
        assert pub['content_hash']==view['review_hash']
    finally:peer.close()


def test_preview_does_not_disclose_unselected_repository_or_excluded_alias(analysis_env):
    e=analysis_env;first=finish(e,start(e));finish(e,start(e,['https://github.com/team/editor']))
    manual(e);cid=dash(e)['manual_entries'][0]['id'];key=dash(e)['manual_entries'][0]['contributor_key']
    post(e,'/aliases',change(e,source_key=key,target_key='github:1'))
    post(e,'/manual/disposition',change(e,contribution_id=cid,status='excluded'))
    _,view=sharing_command(e,first['id']);d=view['document']
    assert 'team/editor' not in str(d) and 'Cyra' not in str(d)
    assert all(p['repositories']==['team/game'] for p in d['contributors'])
    assert all(a['key']!=key for p in d['contributors'] for a in p['aliases'])
    assert all(s['repository']=='team/game' for o in d['outcomes'] for s in o['sources'])
