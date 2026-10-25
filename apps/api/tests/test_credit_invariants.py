from copy import deepcopy
from uuid import UUID,uuid4
import pytest
from sqlalchemy import select,func,text,delete
from sqlalchemy.exc import DBAPIError
from alembic import command
from app.db.migration import migration_config
from app.projects.models import Project,WorkspaceMembership
from app.ledger.models import CreditAward,ContributionEvent,ContributionBalance
from app.ledger.service import reconcile,require_clear_pool,event_balances
from app.reviews.models import ReviewRound
from app.core.errors import ApiError
from tests.phase6_helpers import (environment,assign,vote,finalize,award,final_body,open_dispute)
from tests.auth_helpers import mutation
from tests.phase5_helpers import add
from tests.phase4_helpers import advance


def test_accept_one_portion_then_complete_remaining_scope(client,database,settings):
    e=environment(client,database,settings,partial=True)
    a=assign(e,0);b=assign(e,1);a=vote(e,a);b=vote(e,b)
    finalize(e,a)
    package=client.get(e['path']).json();assert package['state']=='submitted' and package['issued_atoms']==60000
    totals=client.get(e['root']+'/contributions').json()
    assert totals['total_issued_atoms']==60000 and totals['pending_planned_atoms']==40000
    # An award advances the credit projection, not the unchanged planning target.
    assert e['actors']['reviewer']['client'].get(e['root']+'/reviews/'+b['id']).json()['state']=='ready_to_finalize'
    finalize(e,b)
    assert client.get(e['path']).json()['state']=='completed'
    assert client.get(e['root']+'/contributions').json()['total_issued_atoms']==100000


def test_partial_credit_allows_new_evidence_but_never_scope_rewrites(client,database,settings):
    e=environment(client,database,settings,partial=True);first=award(e,0)
    res=add(client,e['path'],text='Additional testing is now complete for the remaining portion.')
    assert res.status_code==201,res.text
    package=client.get(e['path']).json();assert not package['can_edit']
    response=mutation(client,e['path']+'/actions',{'action':'cancel','expected_version':package['version'],
        'reviewed_hash':package['review_hash'],'reviewed':True,'reason':'Cannot delete previously accepted contribution credit'})
    assert response.status_code==409,response.text
    advance(client,e['root'],client.get(e['path']).json(),'refresh_submission')
    assert award(e,1)['state']=='finalized'
    original=client.get(e['root']+'/contributions/awards/'+first['finalized_record_id']).json()
    assert original['budget_atoms']==60000 and len(original['events'])==1


def test_finalized_credit_survives_membership_suspension(client,database,settings):
    e=environment(client,database,settings);award(e)
    with database.session() as db:
        user=UUID(e['owner']['user']['id']);row=db.get(WorkspaceMembership,(UUID(e['owner']['workspace']['id']),user))
        row.status='suspended';db.commit()
    totals=e['actors']['reviewer']['client'].get(e['root']+'/contributions').json()
    assert totals['total_issued_atoms']==100000 and totals['groups'][0]['people'][0]['user_id']==str(user)


def test_contribution_views_are_project_scoped(client,database,settings):
    e=environment(client,database,settings);final=award(e);case=open_dispute(e,final)
    other=mutation(client,'/api/v1/workspaces',{'name':'Another isolated workspace'}).json()
    project=mutation(client,f"/api/v1/workspaces/{other['id']}/projects",{'name':'Isolated project','description':'Different data scope','timezone':'UTC','currency':'USD'}).json()
    root=f"/api/v1/workspaces/{other['id']}/projects/{project['id']}"
    for suffix in ['/reviews/'+final['id'],'/contributions/awards/'+final['finalized_record_id'],'/disputes/'+case['id']]:
        res=client.get(root+suffix);assert res.status_code==404,res.text
    assert client.get(root+'/contributions').json()['total_issued_atoms']==0
    assert client.get(root+'/reviews').json()['items']==[]


def test_project_readers_cannot_rebuild_or_set_balances(client,database,settings):
    e=environment(client,database,settings);award(e)
    viewer=e['actors']['viewer']['client']
    assert viewer.get(e['root']+'/contributions/integrity').status_code==403
    assert mutation(client,e['root']+'/contributions',{'atoms':900000}).status_code==405
    assert mutation(client,e['root']+'/contributions/integrity',{'repair':True}).status_code==405


def test_projection_rebuild_recovers_exact_values_without_changing_history(client,database,settings):
    e=environment(client,database,settings);award(e)
    with database.session() as db:
        project=db.get(Project,UUID(e['owner']['project']['id']))
        before=list(db.scalars(select(ContributionEvent.id)))
        row=db.scalar(select(ContributionBalance));row.atoms=123;db.commit()
        assert not reconcile(db,project)['consistent']
        result=reconcile(db,project,repair=True);assert result['repaired'];db.commit()
        assert reconcile(db,project)['consistent']
        assert list(db.scalars(select(ContributionEvent.id)))==before
        assert db.scalar(select(ContributionBalance.atoms))==100000


def test_ordinary_sql_cannot_change_credit_history(client,database,settings):
    e=environment(client,database,settings);award(e)
    for table in ['review_rounds','review_assignments','review_decisions','credit_awards','contribution_events','participant_notifications']:
        with pytest.raises(DBAPIError),database.engine.begin() as conn:conn.execute(text(f'DELETE FROM {table}'))
    with pytest.raises(DBAPIError),database.engine.begin() as conn:conn.execute(text('UPDATE contribution_events SET delta_atoms=1'))
    assert client.get(e['root']+'/contributions').json()['total_issued_atoms']==100000


def test_nonempty_downgrade_refuses_to_destroy_credit(client,database,settings):
    e=environment(client,database,settings);award(e)
    cfg=migration_config()
    with pytest.raises(RuntimeError,match='Phase-6'),database.engine.begin() as conn:
        cfg.attributes['connection']=conn;command.downgrade(cfg,'0005_manual_evidence')
    assert client.get(e['root']+'/contributions').json()['total_issued_atoms']==100000


def test_empty_phase6_downgrade_and_reupgrade_preserve_previous_evidence(client,database,settings):
    e=environment(client,database,settings);snapshot=e['package']['recent_submissions'][0]['id']
    cfg=migration_config()
    with database.engine.begin() as conn:
        cfg.attributes['connection']=conn;command.downgrade(cfg,'0005_manual_evidence');command.upgrade(cfg,'head')
    assert client.get(e['path']).json()['recent_submissions'][0]['id']==snapshot
    assert award(e)['state']=='finalized'


def test_partial_finalization_failure_rolls_back_every_effect(client,database,settings,monkeypatch):
    e=environment(client,database,settings);r=vote(e,assign(e))
    import app.reviews.service as service
    def fail(*args,**kwargs):raise ApiError(409,'synthetic_failure','Synthetic transaction rollback after posting credit.')
    monkeypatch.setattr(service,'notify',fail)
    response=mutation(e['actors']['reviewer']['client'],e['root']+'/reviews/'+r['id']+'/finalize',final_body(r))
    assert response.status_code==409,response.text
    with database.session() as db:
        assert db.scalar(select(func.count()).select_from(CreditAward))==0
        assert db.scalar(select(func.count()).select_from(ContributionEvent))==0
    assert client.get(e['path']).json()['issued_atoms']==0


def test_pool_guard_is_specific_not_global(client,database,settings):
    e=environment(client,database,settings);final=award(e);case=open_dispute(e,final)
    with database.session() as db:
        project=db.get(Project,UUID(e['owner']['project']['id']))
        with pytest.raises(ApiError,match='unresolved'):
            require_clear_pool(db,project,UUID(case['award']['policy_id']),case['award']['pool_key'])
        require_clear_pool(db,project,UUID(case['award']['policy_id']),'ongoing')
        require_clear_pool(db,project,uuid4(),case['award']['pool_key'])


def test_notifications_are_recipient_scoped(client,database,settings):
    e=environment(client,database,settings);r=assign(e)
    mine=e['actors']['reviewer']['client'].get(e['root']+'/notifications').json()['items']
    assert any(n['kind']=='review_assigned' for n in mine)
    assert e['actors']['reviewer2']['client'].get(e['root']+'/notifications').json()['items']==[]


def test_paginated_awards_and_rounds_do_not_duplicate_items(client,database,settings):
    e=environment(client,database,settings,partial=True);award(e,0);award(e,1)
    first=client.get(e['root']+'/contributions/awards?limit=1').json()
    second=client.get(e['root']+'/contributions/awards?limit=1&offset=1').json()
    assert first['next_offset']==1 and second['next_offset'] is None
    assert first['items'][0]['id']!=second['items'][0]['id']
    assert client.get(e['root']+'/contributions/awards?limit=1000').status_code==422
