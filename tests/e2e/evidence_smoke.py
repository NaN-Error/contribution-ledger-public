"""Actual-browser evidence checks, only called from the guarded disposable account smoke.

Not executed merely by importing this file. Synthetic images are generated in
memory and sent through the real form/proxy. No private sources or paid calls.
"""
from io import BytesIO
from PIL import Image
from playwright.sync_api import Page,expect


def fill_metadata(page:Page,title:str):
    page.get_by_label('Evidence title',exact=True).fill(title)
    page.get_by_label('Relevance to the work',exact=True).fill('Documents a synthetic deliverable and its known limitations.')
    page.get_by_label('Claimed author or authors',exact=True).fill('Synthetic smoke contributor')
    page.get_by_label('Source and provenance',exact=True).fill('Created solely for disposable browser acceptance testing.')
    page.get_by_label('Claimed date of the work',exact=True).fill('2026-09-13')
    page.get_by_label('Reason for this evidence entry or revision',exact=True).fill('Attach this synthetic evidence to the current work package.')


def add_evidence_before_submit(owner:Page):
    owner.get_by_role('button',name='Add evidence',exact=True).click()
    fill_metadata(owner,'Synthetic design statement')
    owner.get_by_label('Contributor statement',exact=True).fill('<script>window.evidenceExecuted = true</script> is inert example text.')
    owner.get_by_role('button',name='Save evidence and capture snapshot',exact=True).click()
    expect(owner.get_by_role('heading',name='Synthetic design statement',exact=True)).to_be_visible()
    assert owner.evaluate('window.evidenceExecuted === undefined')
    owner.get_by_role('button',name='Add evidence',exact=True).click()
    owner.get_by_label('Evidence type',exact=True).select_option('file')
    fill_metadata(owner,'Synthetic character image')
    image=BytesIO();Image.new('RGB',(64,48),(60,100,140)).save(image,format='PNG')
    owner.get_by_label('Artifact file',exact=True).set_input_files({'name':'character.png','mimeType':'image/png','buffer':image.getvalue()})
    owner.get_by_role('button',name='Save evidence and capture snapshot',exact=True).click()
    card=owner.locator('section.panel').filter(has=owner.get_by_role('heading',name='Synthetic character image',exact=True))
    card.get_by_role('button',name='Open protected preview',exact=True).click()
    picture=card.get_by_role('img',name='Contributor-supplied evidence preview',exact=True)
    expect(picture).to_be_visible()
    expect(picture).to_have_js_property('complete',True)
    assert picture.evaluate('(image)=>image.naturalWidth')==64
    with owner.expect_download() as download:
        card.get_by_role('link',name='Download original',exact=True).click()
    assert download.value.suggested_filename=='character.png'
    owner.get_by_role('button',name='Add evidence',exact=True).click()
    owner.get_by_label('Evidence type',exact=True).select_option('unavailable')
    fill_metadata(owner,'Synthetic missing test report')
    owner.get_by_label('Reason for exclusion or unavailability',exact=True).fill('This intentionally missing report must remain an explicit review limitation.')
    owner.get_by_label('Who can inspect this evidence?',exact=True).select_option('restricted')
    owner.get_by_role('button',name='Save evidence and capture snapshot',exact=True).click()
    expect(owner.get_by_role('heading',name='Synthetic missing test report',exact=True)).to_be_visible()


def revise_submitted_evidence(owner:Page,root:str,change_state):
    package=owner.context.request.get(root+'/work-packages').json()['items'][0]
    path=root+f"/work-packages/{package['id']}"
    card=owner.locator('section.panel').filter(has=owner.get_by_role('heading',name='Synthetic design statement',exact=True))
    card.get_by_role('button',name='Add a revision',exact=True).click()
    owner.get_by_label('Contributor statement',exact=True).fill('A revised synthetic design statement that requires a fresh review.')
    owner.get_by_label('Reason for this evidence entry or revision',exact=True).fill('Clarify synthetic evidence without rewriting the earlier submission.')
    owner.get_by_role('button',name='Save new evidence revision',exact=True).click()
    expect(owner.get_by_text('Submission needs fresh evidence review',exact=True)).to_be_visible()
    current=owner.context.request.get(path).json()
    sid=current['recent_submissions'][0]['id'];old=owner.context.request.get(path+'/submissions/'+sid).json()
    change_state(owner,'refresh_submission','Resubmit with current evidence','Explicitly resubmit the revised evidence packet; no contribution is accepted.')
    expect(owner.get_by_role('button',name='Inspect submission',exact=True)).to_have_count(2)
    expect(owner.get_by_text('Submission matches the current packet',exact=True)).to_be_visible()
    assert owner.context.request.get(path+'/submissions/'+sid).json()==old
    assert owner.context.request.get(path).json()['issued_atoms']==0


def inspect_as_viewer(viewer:Page):
    expect(viewer.get_by_role('heading',name='Synthetic design statement',exact=True)).to_be_visible()
    expect(viewer.get_by_role('heading',name='Synthetic missing test report',exact=True)).to_have_count(0)
    expect(viewer.get_by_role('button',name='Add evidence',exact=True)).to_have_count(0)
    viewer.get_by_role('button',name='Inspect current packet',exact=True).click()
    expect(viewer.get_by_text('An archived entry is not visible with your current access.',exact=True)).to_be_visible()
    viewer.get_by_role('button',name='Close snapshot',exact=True).click()
    assert viewer.evaluate('document.documentElement.scrollWidth <= window.innerWidth'), 'Evidence mobile overflow'
