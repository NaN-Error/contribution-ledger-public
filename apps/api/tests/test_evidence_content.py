from base64 import b64encode
from io import BytesIO
from dataclasses import replace
import pytest
from PIL import Image, PngImagePlugin
from pydantic import ValidationError
from app.core.errors import ApiError
from app.evidence.content import checked_file, filename_and_format
from app.evidence.schemas import FileInput, EvidenceCreate, MAX_UPLOAD_BYTES
from tests.phase5_helpers import file_input, png_bytes, command

@pytest.mark.parametrize('filename', ['../secret.txt', '..\\secret.txt', '.hidden.txt', 'C:report.txt',
    'report.txt.', 'CON.txt', 'nul.txt', 'LPT1.md', 'COM9.json', 'foo..txt', 'a%2ftest.txt',
    'a\n.txt', 'a\u202e.txt', 'photo.svg', 'archive.zip', 'macro.docm', 'report.pdf', 'audio.mp3'])
def test_unsafe_and_out_of_scope_names_rejected(filename):
    with pytest.raises(ApiError): filename_and_format(filename)

@pytest.mark.parametrize('name,media,data', [('report.txt','text/plain',b'\xff\xfe'),
    ('report.txt','text/plain',b'abc\x00def'), ('report.txt','text/plain',b' '),
    ('report.txt','text/html',b'<script>hello</script>'),
    ('image.png','image/png',b'<svg onload="alert(1)"/>'),
    ('image.jpg','image/jpeg',png_bytes()), ('image.png','image/png',png_bytes()[:24])])
def test_invalid_text_type_or_raster_rejected(name,media,data):
    with pytest.raises(ApiError): checked_file(FileInput(**file_input(data,name,media)))

@pytest.mark.parametrize('name,media', [('report.txt','text/plain'),('guide.md','text/markdown'),
    ('data.csv','text/csv'),('metadata.json','application/json')])
def test_text_is_opaque_utf8_not_parsed_or_executed(name,media):
    data=b'<script>not executed</script>\n=not-a-formula-evaluation'
    result=checked_file(FileInput(**file_input(data,name,media)))
    assert result.data==data and result.preview is None

def test_bounded_text_original_and_invalid_base64():
    for raw in [b'x'*(256*1024+1), b'']:
        with pytest.raises((ApiError,ValidationError)):
            checked_file(FileInput(**file_input(raw)))
    with pytest.raises(ApiError):
        checked_file(FileInput(filename='report.txt',media_type='text/plain',content_base64='not!base64'))

def test_preview_strips_metadata_and_reduces_size():
    info=PngImagePlugin.PngInfo();info.add_text('private-comment','synthetic metadata must not be previewed')
    target=BytesIO();Image.new('RGB',(1500,1200)).save(target,format='PNG',pnginfo=info)
    checked=checked_file(FileInput(**file_input(target.getvalue(),'image.png','image/png')))
    assert checked.data==target.getvalue()
    with Image.open(BytesIO(checked.preview)) as image:
        assert image.format=='PNG' and max(image.size)<=1024 and not image.info

def test_multiframe_and_oversized_pixel_images_rejected():
    for images, options in [([Image.new('RGB',(8,8)),Image.new('RGB',(8,8),'white')],
                             {'save_all':True,'append_images':[Image.new('RGB',(8,8),'white')]}),
                            ([Image.new('RGB',(3000,3000))],{})]:
        output=BytesIO(); images[0].save(output,format='PNG',**options)
        with pytest.raises(ApiError): checked_file(FileInput(**file_input(output.getvalue(),'art.png','image/png')))

@pytest.mark.parametrize('url', ['http://example.test/a','javascript:alert(1)','file:///tmp/a',
    'https://name:password@example.test/a','https://example.test:8080/a','https://example.test/a%0ab',
    'https://example.test/\\evil','https://example.test/has space'])
def test_external_sources_are_safe_https_labels_not_fetch_instructions(url):
    with pytest.raises(ValidationError): EvidenceCreate(**command({'version':1},'link',source_url=url))
