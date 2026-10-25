import test from 'node:test';
import assert from 'node:assert/strict';
import { createServer, request } from 'node:http';
import { mkdtemp, writeFile, mkdir, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createWebServer } from '../server.mjs';

async function listen(server) {
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  return `http://127.0.0.1:${server.address().port}`;
}
async function close(server) {
  server.closeAllConnections();
  await new Promise(resolve => server.close(resolve));
}
async function fixture(context, apiTarget = 'http://127.0.0.1:1') {
  const distDir = await mkdtemp(join(tmpdir(), 'ledger-web-test-'));
  await writeFile(join(distDir, 'index.html'), '<!doctype html><title>Static server test fixture</title>');
  await writeFile(join(distDir, '.env'), 'SECRET');
  await mkdir(join(distDir, 'assets'));
  await writeFile(join(distDir, 'assets', 'test.js'), 'console.log("fixture")');
  const server = createWebServer({ distDir, apiTarget });
  const url = await listen(server);
  context.after(async () => { await close(server); await rm(distDir, { recursive: true, force: true }); });
  return { server, url };
}
function rawGet(url, path, headers = {}) {
  return new Promise((resolve, reject) => {
    const target = new URL(url);
    const req = request({ hostname: target.hostname, port: target.port, path, headers }, response => {
      let body = ''; response.on('data', chunk => body += chunk);
      response.on('end', () => resolve({ status: response.statusCode, body, headers: response.headers }));
    });
    req.on('error', reject); req.end();
  });
}

test('serves the built index with restrictive headers', async t => {
  const { url } = await fixture(t); const response = await fetch(url);
  assert.equal(response.status, 200); assert.match(response.headers.get('Content-Security-Policy'), /frame-ancestors 'none'/);
  assert.equal(response.headers.get('Cache-Control'), 'no-store');
});
test('static assets have MIME and cache controls', async t => {
  const { url } = await fixture(t); const response = await fetch(`${url}/assets/test.js`);
  assert.equal(response.status, 200); assert.match(response.headers.get('Content-Type'), /javascript/);
  assert.match(response.headers.get('Cache-Control'), /immutable/);
});
test('web health is independent of backend health', async t => {
  const { url } = await fixture(t); assert.equal((await fetch(`${url}/web-health`)).status, 200);
  assert.equal((await fetch(`${url}/api/v1/system/status`)).status, 502);
});
test('blocks hidden files, traversal and malformed URLs', async t => {
  const { url } = await fixture(t);
  for (const path of ['/.env', '/%2e%2e/.env', '/%ZZ', '/%00', '/assets/%5c..%5c.env', '//attacker.invalid/a']) {
    const response = await rawGet(url, path);
    assert.ok([400, 404].includes(response.status), `${path}: ${response.status}`);
    assert.equal(response.body.includes('SECRET'), false);
  }
});
test('rejects unsupported hosts and write methods', async t => {
  const { url } = await fixture(t);
  assert.equal((await rawGet(url, '/', { Host: 'attacker.invalid' })).status, 400);
  assert.equal((await fetch(`${url}/`, { method: 'POST' })).status, 405);
});
test('HEAD and missing resources are handled correctly', async t => {
  const { url } = await fixture(t); const response = await fetch(url, { method: 'HEAD' });
  assert.equal(response.status, 200); assert.equal(await response.text(), '');
  assert.equal((await fetch(`${url}/missing.js`)).status, 404);
});
test('proxy preserves backend status and request identity', async t => {
  const id = 'c6a6b586-2ed6-4c61-87bb-96a7a33bfbef';
  const upstream = createServer((req, res) => {
    assert.equal(req.url, '/api/v1/system/status');
    res.writeHead(503, { 'Content-Type': 'application/json', 'X-Request-ID': id });
    res.end(JSON.stringify({ status: 'degraded' }));
  });
  const apiTarget = await listen(upstream); t.after(() => close(upstream));
  const { url } = await fixture(t, apiTarget); const response = await fetch(`${url}/api/v1/system/status`);
  assert.equal(response.status, 503); assert.equal(response.headers.get('X-Request-ID'), id);
  assert.equal((await response.json()).status, 'degraded');
});
test('operator target rejects embedded credentials and non-HTTP schemes', () => {
  for (const apiTarget of ['file:///tmp/a', 'https://example.com', 'http://user:secret@localhost:8000', 'http://localhost/path']) {
    assert.throws(() => createWebServer({ apiTarget }));
  }
});


test('proxy forwards JSON, session cookies and CSRF but strips spoofed forwarding headers', async t => {
  const upstream = createServer((req, res) => {
    assert.equal(req.method, 'POST');
    assert.equal(req.headers.cookie, 'cl_session=synthetic-session');
    assert.equal(req.headers['x-csrf-token'], 'synthetic-csrf');
    assert.equal(req.headers.origin, 'http://127.0.0.1:5173');
    assert.equal(req.headers['x-forwarded-for'], undefined);
    assert.equal(req.headers.authorization, undefined);
    let body = ''; req.on('data', chunk => body += chunk);
    req.on('end', () => {
      assert.deepEqual(JSON.parse(body), { value: 'synthetic' });
      res.writeHead(200, { 'Content-Type': 'application/json', 'Set-Cookie': ['cl_session=rotated; HttpOnly; SameSite=Lax; Path=/'] });
      res.end(JSON.stringify({ ok: true }));
    });
  });
  const apiTarget = await listen(upstream); t.after(() => close(upstream));
  const { url } = await fixture(t, apiTarget);
  const response = await fetch(`${url}/api/v1/auth/login`, { method: 'POST',
    headers: { Cookie: 'cl_session=synthetic-session', 'X-CSRF-Token': 'synthetic-csrf',
      Origin: 'http://127.0.0.1:5173', 'Content-Type': 'application/json', 'X-Forwarded-For': 'fake-ip', Authorization: 'fake-token' },
    body: JSON.stringify({ value: 'synthetic' }) });
  assert.equal(response.status, 200);
  assert.match(response.headers.get('set-cookie'), /cl_session=rotated; HttpOnly/);
});

test('proxy rejects oversized writes without reaching the API', async t => {
  let reached = false;
  const upstream = createServer((_req, res) => { reached = true; res.end('{}'); });
  const apiTarget = await listen(upstream); t.after(() => close(upstream));
  const { url } = await fixture(t, apiTarget);
  const response = await fetch(`${url}/api/v1/auth/login`, { method: 'POST',
    headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ x: 'x'.repeat(70000) }) });
  assert.equal(response.status, 413); assert.equal(reached, false);
});

test('proxy supports PATCH and DELETE and preserves retry guidance', async t => {
  const upstream = createServer((req, res) => { req.resume(); req.on('end', () => {
    res.writeHead(429, { 'Content-Type': 'application/json', 'Retry-After': '900' });
    res.end(JSON.stringify({ error: { code: 'rate_limited' } }));
  }); });
  const apiTarget = await listen(upstream); t.after(() => close(upstream));
  const { url } = await fixture(t, apiTarget);
  for (const method of ['PATCH', 'DELETE']) {
    const response = await fetch(`${url}/api/v1/example`, { method, headers: { 'Content-Type': 'application/json' }, body: '{}' });
    assert.equal(response.status, 429); assert.equal(response.headers.get('retry-after'), '900');
  }
});

const evidenceRoot='/api/v1/workspaces/00000000-0000-0000-0000-000000000001/projects/00000000-0000-0000-0000-000000000002/work-packages/00000000-0000-0000-0000-000000000003/evidence';
test('proxy permits bounded large evidence JSON without relaxing other routes',async t=>{
  const upstream=createServer((req,res)=>{let size=0;req.on('data',c=>size+=c.length);req.on('end',()=>{res.writeHead(201,{'Content-Type':'application/json'});res.end(JSON.stringify({size}));});});
  const apiTarget=await listen(upstream);t.after(()=>close(upstream));const {url}=await fixture(t,apiTarget);
  const body=JSON.stringify({content_base64:'a'.repeat(150000)});
  const response=await fetch(url+evidenceRoot,{method:'POST',headers:{'Content-Type':'application/json'},body});
  assert.equal(response.status,201);assert.equal((await response.json()).size,body.length);
  assert.equal((await fetch(url+evidenceRoot+'/snapshots',{method:'POST',headers:{'Content-Type':'application/json'},body})).status,413);
});
test('proxy bounds evidence uploads and rejects compressed requests before upstream',async t=>{
  let reached=false;const upstream=createServer((req,res)=>{reached=true;req.resume();res.end('{}');});
  const apiTarget=await listen(upstream);t.after(()=>close(upstream));const {url}=await fixture(t,apiTarget);
  assert.equal((await fetch(url+evidenceRoot,{method:'POST',headers:{'Content-Type':'application/json'},body:'x'.repeat(3000000)})).status,413);
  assert.equal((await fetch(url+evidenceRoot,{method:'POST',headers:{'Content-Type':'application/json','Content-Encoding':'gzip'},body:'{}'})).status,415);
  assert.equal(reached,false);
});
test('proxy preserves protected artifact bytes, attachment disposition and sandbox policy',async t=>{
  const bytes=Buffer.from([0,1,254,255,13,10]);
  const upstream=createServer((req,res)=>{assert.equal(req.headers.cookie,'cl_session=synthetic');res.writeHead(200,{'Content-Type':'application/octet-stream',
    'Content-Disposition':"attachment; filename=artifact; filename*=UTF-8''report.txt"});res.end(bytes);});
  const apiTarget=await listen(upstream);t.after(()=>close(upstream));const {url}=await fixture(t,apiTarget);
  const response=await fetch(`${url}${evidenceRoot}/00000000-0000-0000-0000-000000000004/revisions/1/download`,{headers:{Cookie:'cl_session=synthetic'}});
  assert.deepEqual(Buffer.from(await response.arrayBuffer()),bytes);assert.match(response.headers.get('content-disposition'),/^attachment;/);
  assert.match(response.headers.get('content-security-policy'),/default-src 'none'; sandbox/);assert.equal(response.headers.get('cache-control'),'no-store');assert.equal(response.headers.get('vary'),'Cookie');
});

test('GitHub callback serves the shell without reflecting secrets or caching', async t => {
  const {url}=await fixture(t);
  const response=await fetch(`${url}/github/callback?code=synthetic-private-code&state=synthetic-private-state`);
  assert.equal(response.status,200);assert.match(response.headers.get('cache-control'),/no-store/);
  assert.equal(response.headers.get('referrer-policy'),'no-referrer');
  const body=await response.text();assert.equal(body.includes('synthetic-private-code'),false);assert.equal(body.includes('synthetic-private-state'),false);
  assert.equal((await fetch(`${url}/github/unrecognized`)).status,404);
});

const financeRoot='/api/v1/workspaces/00000000-0000-0000-0000-000000000001/projects/00000000-0000-0000-0000-000000000002/finance';
const financePeriod='00000000-0000-0000-0000-000000000003';
test('proxy permits bounded finance documents without relaxing financial entry limits',async t=>{
 const upstream=createServer((req,res)=>{let size=0;req.on('data',c=>size+=c.length);req.on('end',()=>{res.writeHead(201,{'Content-Type':'application/json'});res.end(JSON.stringify({size}));});});
 const apiTarget=await listen(upstream);t.after(()=>close(upstream));const {url}=await fixture(t,apiTarget);const body=JSON.stringify({content_base64:'a'.repeat(150000)});
 const response=await fetch(`${url}${financeRoot}/periods/${financePeriod}/documents`,{method:'POST',headers:{'Content-Type':'application/json'},body});
 assert.equal(response.status,201);assert.equal((await response.json()).size,body.length);
 assert.equal((await fetch(`${url}${financeRoot}/periods/${financePeriod}/entries`,{method:'POST',headers:{'Content-Type':'application/json'},body})).status,413);
});
test('finance export preserves raw bytes, sha fingerprint, disposition and protected headers',async t=>{
 const bytes=Buffer.from([0,255,1,2,3]);const hash='a'.repeat(64);
 const upstream=createServer((req,res)=>{assert.equal(req.headers.cookie,'cl_session=synthetic');res.writeHead(200,{'Content-Type':'application/zip','Content-Disposition':'attachment; filename=audit.zip','X-Content-SHA256':hash});res.end(bytes);});
 const apiTarget=await listen(upstream);t.after(()=>close(upstream));const {url}=await fixture(t,apiTarget);
 const response=await fetch(`${url}${financeRoot}/closes/${financePeriod}/export?format=zip`,{headers:{Cookie:'cl_session=synthetic'}});
 assert.deepEqual(Buffer.from(await response.arrayBuffer()),bytes);assert.equal(response.headers.get('x-content-sha256'),hash);assert.equal(response.headers.get('cache-control'),'no-store');assert.equal(response.headers.get('vary'),'Cookie');assert.match(response.headers.get('content-security-policy'),/default-src 'none'; sandbox/);
});
test('oversized finance document is rejected without contacting the API',async t=>{
 let reached=false;const upstream=createServer((req,res)=>{reached=true;req.resume();res.end('{}');});const apiTarget=await listen(upstream);t.after(()=>close(upstream));const {url}=await fixture(t,apiTarget);
 const response=await fetch(`${url}${financeRoot}/periods/${financePeriod}/documents`,{method:'POST',headers:{'Content-Type':'application/json'},body:'a'.repeat(3000000)});
 assert.equal(response.status,413);assert.equal(reached,false);
});
