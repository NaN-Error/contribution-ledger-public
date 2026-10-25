from copy import deepcopy
from uuid import UUID, uuid4
from sqlalchemy import select, func
from app.evidence.models import EvidenceItem, EvidenceRevision, EvidenceObject, EvidenceSnapshot
from app.contributions.work_packages.models import WorkSubmission
from tests.phase5_helpers import evidence_environment, metadata, command, add, revise, file_input, png_bytes
from tests.phase4_helpers import advance, action, edit
from tests.auth_helpers import mutation


def test_statement_records_claims_and_auto_snapshot_not_credit(client,database):
    _,_,path,package=evidence_environment(client,database)
    response=add(client,path); assert response.status_code==201,response.text
    evidence=response.json(); assert evidence['number']==1 and evidence['document']['text']
    summary=client.get(path+'/evidence').json()
    assert summary['total_entries']==1 and summary['current_snapshot_id'] and summary['review_state']=='not_submitted'
    packet=client.get(path+'/evidence/snapshots/'+summary['current_snapshot_id']).json()
    assert packet['document']['scope_hash']==package['revision']['content_hash'] and not packet['stale']
    assert client.get(path).json()['issued_atoms']==0
    with database.session() as db: assert db.scalar(select(func.count()).select_from(EvidenceObject))==0


def test_same_evidence_request_is_idempotent_and_conflicting_reuse_fails(client,database):
    _,_,path,package=evidence_environment(client,database)
    body=command(package)
    first=mutation(client,path+'/evidence',body);assert first.status_code==201,first.text
    replay=mutation(client,path+'/evidence',body);assert replay.status_code==201 and replay.json()['replayed']
    assert replay.json()['evidence_id']==first.json()['evidence_id']
    changed=mutation(client,path+'/evidence',{**body,'text':'Different source text with the same request identifier.'})
    assert changed.status_code==409 and changed.json()['error']['code']=='idempotency_conflict'
    with database.session() as db:
        assert db.scalar(select(func.count()).select_from(EvidenceRevision))==1
        assert db.scalar(select(func.count()).select_from(EvidenceSnapshot))==1


def test_stale_package_rejected_before_file_storage(client,database):
    _,_,path,package=evidence_environment(client,database)
    assert add(client,path).status_code==201
    response=mutation(client,path+'/evidence',command(package,'file'))
    assert response.status_code==409 and response.json()['error']['code']=='stale_package'
    with database.session() as db: assert db.scalar(select(func.count()).select_from(EvidenceObject))==0


def test_revision_preserves_old_text_and_snapshots(client,database):
    _,_,path,_=evidence_environment(client,database)
    first=add(client,path).json();before=client.get(path+'/evidence').json()['current_snapshot_id']
    updated=revise(client,path,first,text='A corrected explanation of the synthetic test outcome.')
    assert updated.status_code==200,updated.text
    assert updated.json()['number']==2
    original=client.get(path+f"/evidence/{first['evidence_id']}/revisions/1").json()
    assert original['document']['text']==first['document']['text'] and original['historical']
    assert client.get(path+'/evidence/snapshots/'+before).json()['stale']
    assert revise(client,path,first).status_code==409


def test_submission_packet_stales_on_evidence_change_and_refresh_preserves_both(client,database):
    _,root,path,package=evidence_environment(client,database)
    first=add(client,path).json()
    package=client.get(path).json();package=advance(client,root,package,'approve_scope','start','submit')
    sid=package['recent_submissions'][0]['id'];old=client.get(path+'/submissions/'+sid).json()
    assert old['snapshot']['evidence_snapshot_id'] and old['snapshot']['evidence_status']=='captured_unreviewed'
    assert client.get(path+'/evidence').json()['review_state']=='current'
    assert revise(client,path,first,text='The new report also records the previously omitted failure.').status_code==200
    assert client.get(path+'/evidence').json()['review_state']=='stale'
    assert action(client,root,package,'refresh_submission').status_code==409
    package=advance(client,root,client.get(path).json(),'refresh_submission')
    assert len(package['recent_submissions'])==2 and package['state']=='submitted'
    assert client.get(path+'/evidence').json()['review_state']=='current'
    assert client.get(path+'/submissions/'+sid).json()==old
    assert package['issued_atoms']==0


def test_scope_amendment_stales_packet(client,database):
    _,root,path,package=evidence_environment(client,database)
    add(client,path)
    before=client.get(path+'/evidence').json()['current_snapshot_id']
    assert edit(client,root,client.get(path).json()).status_code==200
    stale=client.get(path+'/evidence/snapshots/'+before).json()
    assert stale['stale'] and stale['scope_revision']==1


def test_link_is_stored_not_fetched_and_missing_entry_is_explicit(client,database,monkeypatch):
    _,_,path,_=evidence_environment(client,database)
    import urllib.request
    monkeypatch.setattr(urllib.request,'urlopen',lambda *_a,**_k: (_ for _ in ()).throw(AssertionError('No remote fetch is allowed')))
    link=add(client,path,'link');assert link.status_code==201 and link.json()['availability']=='external_unverified'
    missing=add(client,path,'unavailable');assert missing.status_code==201 and missing.json()['availability']=='declared_unavailable'
    sid=client.get(path+'/evidence').json()['current_snapshot_id']
    omissions=client.get(path+'/evidence/snapshots/'+sid).json()['document']['omissions']
    assert len(omissions)==1 and omissions[0]['status']=='declared_unavailable'


def test_foreign_deliverable_rejected(client,database):
    _,_,path,_=evidence_environment(client,database)
    result=add(client,path,metadata=metadata(deliverable_ids=[str(uuid4())]))
    assert result.status_code==422 and result.json()['error']['code']=='invalid_deliverable'


def test_file_roundtrip_and_plaintext_preview_escape_nothing_into_html(client,database):
    _,_,path,_=evidence_environment(client,database)
    content=b'<script>alert("not executed")</script>\n# Markdown is plain text.'
    result=add(client,path,'file',file=file_input(content,'report.md','text/markdown'))
    assert result.status_code==201,result.text
    entry=result.json();rev=path+f"/evidence/{entry['evidence_id']}/revisions/1"
    download=client.get(rev+'/download')
    assert download.content==content and download.headers['content-type']=='application/octet-stream'
    assert download.headers['content-disposition'].startswith('attachment;') and 'no-store' in download.headers['cache-control']
    preview=client.get(rev+'/preview');assert preview.json()['text']==content.decode()
    assert preview.headers['content-type'].startswith('application/json')
    assert client.get(rev+'/image').status_code==404


def test_image_preview_is_separate_reencoded_object(client,database):
    _,_,path,_=evidence_environment(client,database)
    data=png_bytes()
    result=add(client,path,'file',file=file_input(data,'character.png','image/png'))
    assert result.status_code==201,result.text
    entry=result.json(); assert entry['document']['file']['width']==16
    rev=path+f"/evidence/{entry['evidence_id']}/revisions/1"
    preview=client.get(rev+'/image');assert preview.status_code==200 and preview.headers['content-type']=='image/png'
    assert client.get(rev+'/download').content==data and preview.content!=data
    with database.session() as db: assert db.scalar(select(func.count()).select_from(EvidenceObject))==2


def test_replacing_file_keeps_original_download_and_changes_hash(client,database):
    _,_,path,_=evidence_environment(client,database)
    first=add(client,path,'file').json()
    update=revise(client,path,first,file=file_input(b'Updated report with new evidence.'))
    assert update.status_code==200,update.text
    assert update.json()['document']['file']['sha256']!=first['document']['file']['sha256']
    assert client.get(path+f"/evidence/{first['evidence_id']}/revisions/1/download").content==b'Synthetic test report. No private data.'


def test_retirement_blocks_history_bytes_not_snapshot_or_units(client,database):
    _,_,path,_=evidence_environment(client,database)
    first=add(client,path,'file').json();summary=client.get(path+'/evidence').json();sid=summary['current_snapshot_id']
    packet=client.get(path+'/evidence/snapshots/'+sid).json()
    response=mutation(client,path+f"/evidence/{first['evidence_id']}/revisions/1/retire",{
        'expected_package_version':summary['package_version'],'reviewed':True,'reason':'Retire this synthetic source under the retention test'})
    assert response.status_code==200 and response.json()['deletion_pending_objects']==0
    assert client.get(path+f"/evidence/{first['evidence_id']}/revisions/1/download").status_code==410
    current=client.get(path+'/evidence').json();assert current['items'][0]['availability']=='retired'
    archived=client.get(path+'/evidence/snapshots/'+sid).json()
    assert archived['document']==packet['document'] and archived['stale']
    assert client.get(path).json()['issued_atoms']==0
    assert revise(client,path,first).status_code==409
    assert revise(client,path,first,file=file_input(b'New supplied artifact after retirement.')).status_code==200


def test_missing_and_corrupt_files_not_served(client,database):
    from app.evidence.service import ref
    _,_,path,_=evidence_environment(client,database)
    first=add(client,path,'file').json()
    with database.session() as db: obj=db.scalar(select(EvidenceObject))
    store=client.app.state.object_storage
    target=store._path(ref(obj));target.write_bytes(b'x'*obj.size_bytes)
    result=client.get(path+f"/evidence/{first['evidence_id']}/revisions/1/download")
    assert result.status_code==409 and result.json()['error']['code']=='artifact_integrity'
    target.unlink()
    assert client.get(path+'/evidence').json()['items'][0]['availability']=='missing'
    assert client.get(path+f"/evidence/{first['evidence_id']}/revisions/1/download").status_code==410


def test_cancelled_work_cannot_receive_evidence(client,database):
    _,root,path,package=evidence_environment(client,database)
    advance(client,root,package,'cancel')
    assert add(client,path).status_code==409


def test_quota_is_checked_before_writing_and_failed_writes_do_not_award(client,database,monkeypatch):
    from app.storage.contracts import StorageUnavailable
    _,_,path,_=evidence_environment(client,database)
    client.app.state.settings.evidence_workspace_quota_bytes=1
    result=add(client,path,'file');assert result.status_code==409 and result.json()['error']['code']=='artifact_quota'
    client.app.state.settings.evidence_workspace_quota_bytes=268435456
    def fail(*_):raise StorageUnavailable('Secret endpoint must not leak.')
    monkeypatch.setattr(client.app.state.object_storage,'put',fail)
    result=add(client,path,'file');assert result.status_code==503 and 'Secret endpoint' not in result.text
    assert client.get(path+'/evidence').json()['total_entries']==0


def test_snapshot_duplicate_capture_reuses_hash(client,database):
    _,_,path,package=evidence_environment(client,database)
    body={'expected_package_version':package['version'],'reviewed_hash':package['review_hash'],
        'reviewed':True,'reason':'Capture the supplied synthetic evidence references'}
    first=mutation(client,path+'/evidence/snapshots',body)
    second=mutation(client,path+'/evidence/snapshots',body)
    assert first.status_code==201 and first.json()['id']==second.json()['id']
    assert first.json()['document']['omissions'][0]['status']=='no_evidence'


def test_preview_text_truncates_but_download_remains_exact(client,database):
    _,_,path,_=evidence_environment(client,database)
    content=b'Safe text ' * 3000
    first=add(client,path,'file',file=file_input(content)).json()
    rev=path+f"/evidence/{first['evidence_id']}/revisions/1"
    preview=client.get(rev+'/preview').json()
    assert preview['truncated'] and len(preview['text'])==20000
    assert client.get(rev+'/download').content==content
