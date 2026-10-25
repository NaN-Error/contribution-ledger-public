from base64 import b64encode
from io import BytesIO
from uuid import uuid4
from PIL import Image
from tests.auth_helpers import mutation
from tests.test_work_packages import setup_package


def evidence_environment(client, database):
    owner, root, milestone, allocation, package = setup_package(client, database)
    path = root + f"/work-packages/{package['id']}"
    return owner, root, path, package


def metadata(**overrides):
    return {'title': 'Synthetic reconnection test report', 'description': 'A reproducible report for this synthetic game.',
        'claimed_authors': 'Fictional test contributor', 'provenance': 'Created by the contributor for this fixture.',
        'occurred_on': '2026-09-13', 'category': 'qa', 'visibility': 'project',
        'inclusion': 'included', 'omission_reason': None, 'deliverable_ids': [], **overrides}


def file_input(data=b'Synthetic test report. No private data.', filename='report.txt', media_type='text/plain'):
    return {'filename': filename, 'media_type': media_type, 'content_base64': b64encode(data).decode('ascii')}


def png_bytes(size=(16, 12)):
    target = BytesIO()
    Image.new('RGB', size, (120, 160, 170)).save(target, format='PNG')
    return target.getvalue()


def command(package, kind='statement', **overrides):
    body = {'kind': kind, 'metadata': metadata(), 'expected_package_version': package['version'],
        'request_id': str(uuid4()), 'reason': 'Submit synthetic evidence for review'}
    if kind=='statement': body['text']='This is a contributor statement, not verified acceptance.'
    if kind=='file': body['file']=file_input()
    if kind=='link': body['source_url']='https://example.test/artifacts/design'
    if kind=='unavailable': body['metadata']=metadata(inclusion='unavailable', omission_reason='The original source report has not yet been supplied.')
    return {**body, **overrides}


def add(client, path, kind='statement', **overrides):
    package=client.get(path).json()
    return mutation(client, path+'/evidence', command(package,kind,**overrides))


def revise(client, path, record, **overrides):
    package=client.get(path).json()
    doc=record['document']
    body={'metadata':doc['metadata'], 'text':doc['text'], 'source_url':doc['source_url'],
        'expected_revision':record['number'],'expected_package_version':package['version'],
        'request_id':str(uuid4()),'reason':'Amend evidence while preserving the earlier revision', **overrides}
    return mutation(client,path+f"/evidence/{record['evidence_id']}/revisions",body)
