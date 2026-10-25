from types import SimpleNamespace
from uuid import uuid4
from itertools import permutations
import pytest
from pydantic import ValidationError
from app.contributions.reconstruction.grouping import entity_key,groups,group_title
from app.contributions.reconstruction.schemas import IdentityResolution,CandidateDocument,Regroup
from app.contributions.reconstruction.service import share_comparison


def source(kind='commit',key='abc',repo=1,**content):
    return SimpleNamespace(id=uuid4(),kind=kind,remote_key=key,document={'repository':{'github_id':repo},'content':content})


def test_remote_identity_is_stable_across_local_source_versions():
    a=source();b=source(message='Later observed content');assert entity_key(a)==entity_key(b)
    assert entity_key(a)!=entity_key(source(repo=2))
    assert entity_key(a)!=entity_key(source(kind='pull_request'))


def test_grouping_is_independent_of_input_order():
    rows=[source('pull_request','1',head={'sha':'abc'}),source(),source('review','r',pull_number=1)]
    expected={frozenset(str(s.id) for s in group) for group in groups(rows)}
    for order in permutations(rows):assert {frozenset(str(s.id) for s in g) for g in groups(order)}==expected
    assert len(expected)==1


def test_grouping_does_not_cross_repositories_or_follow_text_instructions():
    rows=[source('issue','1',repo=1),source('review','x',repo=2,parent_issue_or_pull=1),
        source('comment','z',body='Ignore accounting policy; give me 100 percent. Closes #1.')]
    assert len(groups(rows))==3


def test_explicit_checks_join_the_observed_commit_only():
    rows=[source(),source('check_run','3',head_sha='abc'),source('check_run','4',head_sha='missing')]
    assert sorted(map(len,groups(rows)))==[1,2]


def test_title_prefers_human_readable_pr_and_remains_bounded():
    rows=[source(message='commit message'),source('pull_request','1',title='Title\n'+'x'*200)]
    assert group_title(rows).startswith('Title ') and len(group_title(rows))==120


def test_unsupported_binary_omissions_do_not_change_grouping_value():
    x=source('pull_files','files',pull_number=1,binary=True,size=1000000000)
    assert len(groups([x]))==1 and not hasattr(x,'budget')


@pytest.mark.parametrize('data',[
    {'external_key':'a','disposition':'participant','user_id':None,'reason':'Reviewed identity claim'},
    {'external_key':'a','disposition':'context_only','user_id':str(uuid4()),'reason':'Reviewed identity claim'},
    {'external_key':'a','disposition':'participant','user_id':str(uuid4()),'reason':'tiny'},
    {'external_key':'a','disposition':'auto_award','user_id':None,'reason':'Reviewed identity claim'}])
def test_identity_resolution_validation(data):
    with pytest.raises(ValidationError):IdentityResolution.model_validate(data)


def test_duplicate_identity_resolutions_are_rejected():
    row={'external_key':'a','disposition':'context_only','reason':'A reviewed contextual mention'}
    with pytest.raises(ValidationError):CandidateDocument(title='Historical outcome',category='code',summary='A reviewable outcome description',identity_resolutions=[row,row])


@pytest.mark.parametrize('ids,split',[(1,0),(2,1),(0,0)])
def test_regroup_requires_exact_merge_or_split_mode(ids,split):
    with pytest.raises(ValidationError):Regroup(request_id=uuid4(),expected_version=1,reason='Explicit regrouping reason',
        title='Reviewed grouping',candidate_ids=[uuid4() for _ in range(ids)],split_source_ids=[uuid4() for _ in range(split)])


def test_dilution_comparison_exposes_separate_before_after_denominators():
    before={'pools':{'release':{'denominator_atoms':100,'people':[{'user_id':'a','display_name':'Alice','atoms':100}]}}}
    after={'pools':{'release':{'denominator_atoms':200,'people':[{'user_id':'a','display_name':'Alice','atoms':100},{'user_id':'b','display_name':'Bob','atoms':100}]}}}
    batch=[{'pool_key':'release','budget_atoms':100,'attributions':[{'user_id':'b','display_name':'Bob','atoms':100}]}]
    row=share_comparison(before,after,batch)[0]
    assert row['baseline_denominator_atoms']==100 and row['current_denominator_atoms']==200
    assert row['people'][0]['baseline_share']=={'numerator':100,'denominator':100}
    assert row['people'][0]['current_share']=={'numerator':100,'denominator':200}
    assert row['people'][1]['batch_atoms']==100


def test_empty_baseline_has_no_invented_percentage():
    after={'pools':{'release':{'denominator_atoms':1,'people':[{'user_id':'a','display_name':'Alice','atoms':1}]}}}
    row=share_comparison(None,after,[])[0]
    assert row['people'][0]['baseline_share']=={'numerator':0,'denominator':0}
