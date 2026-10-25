import test from 'node:test';
import assert from 'node:assert/strict';
import { MAX_UPLOAD_BYTES, MAX_TEXT_BYTES, MAX_EVIDENCE_JSON_BYTES, fileMediaType, encodeFile, prepareFile,
  localDate, formatBytes, safeSourceURL, evidenceRevisionPath, boundedEvidenceBody, emptyMetadata, reviewStateLabel } from '../.test-build/lib/evidence.js';

const uuid='00000000-0000-0000-0000-000000000001';
const root=`/api/v1/workspaces/${uuid}/projects/${uuid}/work-packages/${uuid}/evidence`;
test('evidence file sizes distinguish text, binary and JSON encoding limits',()=>{
  assert.equal(MAX_UPLOAD_BYTES,2097152);assert.equal(MAX_TEXT_BYTES,262144);assert.equal(MAX_EVIDENCE_JSON_BYTES,2861740);
});
test('supported file labels match backend allowlist',()=>{
  assert.equal(fileMediaType('design.PNG'),'image/png');assert.equal(fileMediaType('Résumé.txt'),'text/plain');
  assert.equal(fileMediaType('data.json'),'application/json');assert.equal(fileMediaType('report.csv'),'text/csv');
});
for (const name of ['../secret.txt','..\\secret.txt','.hidden.md','CON.txt','COM1.csv','a%2F.txt','a\u202e.txt','art.svg','audio.mp3','report.pdf','a.txt.']) {
  test(`unsafe/out-of-scope file label rejected: ${JSON.stringify(name)}`,()=>assert.throws(()=>fileMediaType(name)));
}
test('byte encoding preserves exact data and does not trust reported browser type',()=>{
  const result=encodeFile('report.txt',new Uint8Array([65,66,10,67]));
  assert.deepEqual(result,{filename:'report.txt',media_type:'text/plain',content_base64:'QUIKQw=='});
  assert.throws(()=>encodeFile('report.txt',new Uint8Array(MAX_TEXT_BYTES+1)));
  assert.throws(()=>encodeFile('report.txt',new Uint8Array()));
});
test('File handling checks size before reading content',async()=>{
  let read=false;
  await assert.rejects(prepareFile({name:'image.png',size:MAX_UPLOAD_BYTES+1,arrayBuffer:()=>{read=true;return new ArrayBuffer(1);}}));
  assert.equal(read,false);
  const prepared=await prepareFile(new File(['synthetic'],'report.txt',{type:'application/octet-stream'}));
  assert.equal(prepared.media_type,'text/plain');
});
test('metadata uses local calendar date and explicitly unverified authorship fields',()=>{
  assert.equal(localDate(new Date(2026,8,13,0,1)),'2026-09-13');
  assert.equal(emptyMetadata().claimed_authors,'');assert.equal(emptyMetadata().inclusion,'included');
});
test('safe source labels reject executable schemes, embedded credentials and controls',()=>{
  for(const value of ['javascript:alert(1)','file:///tmp/a','http://example.test/a','https://a:b@example.test/a','https://example.test:8080/a','https://example.test/a%0ab']) assert.throws(()=>safeSourceURL(value));
  assert.equal(safeSourceURL('https://example.test/design'),'https://example.test/design');
});
test('artifact references never become external authenticated requests',()=>{
  assert.equal(evidenceRevisionPath(root,uuid,1),`${root}/${uuid}/revisions/1`);
  for(const [r,id,n] of [['https://evil.test',uuid,1],[root,'../secret',1],[root,uuid,51],[root,uuid,0]]) assert.throws(()=>evidenceRevisionPath(r,id,n));
});
test('size formatting and body budget do not accept invalid values',()=>{
  assert.equal(formatBytes(1024),'1.0 KiB');assert.equal(formatBytes(2097152),'2.00 MiB');assert.throws(()=>formatBytes(-1));
  const small={title:'A synthetic statement'};assert.equal(boundedEvidenceBody(small),small);
  assert.throws(()=>boundedEvidenceBody({text:'x'.repeat(MAX_EVIDENCE_JSON_BYTES)}));
});
test('legacy and stale submissions are not presented as accepted evidence',()=>{
  assert.match(reviewStateLabel('legacy_without_evidence'),/no evidence packet/);
  assert.match(reviewStateLabel('stale'),/fresh evidence review/);
});
