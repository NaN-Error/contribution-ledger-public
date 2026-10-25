import test from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import {once} from 'node:events';
import {createGateway,validateUpstream,WEBHOOK_PATH,MAX_BYTES} from '../../../infra/webhook-gateway.mjs';
async function fixture(t,handler,options={}) {
  const upstream=http.createServer(handler);upstream.listen(0,'127.0.0.1');await once(upstream,'listening');
  const gateway=createGateway({upstream:`http://127.0.0.1:${upstream.address().port}`,...options});gateway.listen(0,'127.0.0.1');await once(gateway,'listening');
  t.after(async()=>{gateway.closeAllConnections();upstream.closeAllConnections();await Promise.all([new Promise(r=>gateway.close(r)),new Promise(r=>upstream.close(r))]);});
  return `http://127.0.0.1:${gateway.address().port}`;
}
const signed={'content-type':'application/json','x-hub-signature-256':'sha256='+'0'.repeat(64),'x-github-delivery':'a7a5ad0f-10c4-4aee-a158-cd7eac858f33','x-github-event':'push'};
for(const url of ['https://api:8000','http://example.com','http://api:8000/path','http://api:8000?query','http://x:y@api:8000'])test(`gateway rejects upstream ${url}`,()=>assert.throws(()=>validateUpstream(url)));
for(const path of ['/', '/api/v1/auth/session','/api/v1/github/webhook?x=1','/api/v1/github/webhook/','/%61pi/v1/github/webhook'])test(`gateway blocks other route ${path}`,async t=>{
  const origin=await fixture(t,()=>assert.fail('No unrelated route may reach API'));
  assert.equal((await fetch(origin+path,{method:'POST',headers:signed,body:'{}'})).status,404);
});
test('gateway blocks GET even on webhook path',async t=>{const origin=await fixture(t,()=>assert.fail());assert.equal((await fetch(origin+WEBHOOK_PATH)).status,404);});
test('gateway requires signature headers',async t=>{const origin=await fixture(t,()=>assert.fail());assert.equal((await fetch(origin+WEBHOOK_PATH,{method:'POST',headers:{'content-type':'application/json'},body:'{}'})).status,401);});
test('gateway preserves raw bytes and strips session/forwarding headers',async t=>{
  const raw='{ "message": "untouched utf8 é", "value": 1 }';let seen;
  const origin=await fixture(t,(req,res)=>{const chunks=[];req.on('data',c=>chunks.push(c));req.on('end',()=>{seen={raw:Buffer.concat(chunks).toString(),headers:req.headers,path:req.url};res.writeHead(202,{'content-type':'application/json','set-cookie':'malicious=1'});res.end('{"accepted":true}');});});
  const response=await fetch(origin+WEBHOOK_PATH,{method:'POST',headers:{...signed,cookie:'session=secret',authorization:'Bearer secret',origin:'http://evil.invalid','x-forwarded-for':'8.8.8.8'},body:raw});
  assert.equal(response.status,202);assert.equal(seen.raw,raw);assert.equal(seen.path,WEBHOOK_PATH);
  for(const header of ['cookie','authorization','origin','x-forwarded-for'])assert.equal(seen.headers[header],undefined);
  assert.equal(response.headers.get('set-cookie'),null);assert.equal(response.headers.get('cache-control'),'no-store');
});
test('gateway preserves backend signature rejection',async t=>{const origin=await fixture(t,(req,res)=>{req.resume();res.writeHead(401);res.end('{"error":{"code":"github_signature_rejected"}}');});assert.equal((await fetch(origin+WEBHOOK_PATH,{method:'POST',headers:signed,body:'{}'})).status,401);});
test('gateway rejects oversized request',async t=>{const origin=await fixture(t,()=>assert.fail());assert.equal((await fetch(origin+WEBHOOK_PATH,{method:'POST',headers:signed,body:'x'.repeat(MAX_BYTES+1)})).status,413);});
test('gateway rejects compressed body',async t=>{const origin=await fixture(t,()=>assert.fail());assert.equal((await fetch(origin+WEBHOOK_PATH,{method:'POST',headers:{...signed,'content-encoding':'gzip'},body:'{}'})).status,415);});
test('gateway bounds stalled upstream',async t=>{const origin=await fixture(t,req=>req.resume(),{timeout:50});assert.equal((await fetch(origin+WEBHOOK_PATH,{method:'POST',headers:signed,body:'{}'})).status,503);});
test('gateway bounds upstream response',async t=>{const origin=await fixture(t,(req,res)=>{req.resume();res.writeHead(200);res.end('x'.repeat(20000));});assert.equal((await fetch(origin+WEBHOOK_PATH,{method:'POST',headers:signed,body:'{}'})).status,502);});
