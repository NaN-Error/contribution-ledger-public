import test from 'node:test';
import assert from 'node:assert/strict';
import { api, loadSession, rememberSession, RequestFailure } from '../.test-build/lib/api.js';
const session = { user:null, csrf_token:'a'.repeat(64), session_id:'one', expires_at:'2026-09-14T00:00:00Z', bootstrap_required:true, password_min_length:15 };
const json = (body, status=200) => new Response(JSON.stringify(body), {status, headers:{'Content-Type':'application/json','X-Request-ID':'test-request'}});

test('protected mutations forward CSRF in memory and use same-origin cookies', async t => {
  rememberSession(session); let received;
  t.mock.method(globalThis, 'fetch', async (path, options) => {received={path, options};return json({ok:true});});
  await api('/api/v1/workspaces', 'POST', {name:'Test workspace'});
  assert.equal(received.options.headers['X-CSRF-Token'], session.csrf_token);
  assert.equal(received.options.credentials, 'same-origin'); assert.equal(received.options.cache, 'no-store');
  assert.equal(received.options.body, '{"name":"Test workspace"}');
  assert.equal(received.options.headers.Authorization, undefined);
});
test('session startup deduplicates concurrent requests', async t => {
  let count=0; t.mock.method(globalThis, 'fetch', async () => {count++;return json(session);});
  const [one,two] = await Promise.all([loadSession(), loadSession()]); assert.equal(count,1);assert.deepEqual(one,two);
});
test('unsafe request failures never auto-retry', async t => {
  let count=0; t.mock.method(globalThis, 'fetch', async () => {count++;return json({error:{code:'csrf_failed',message:'Refresh your session.'}},403);});
  await assert.rejects(api('/api/v1/workspaces','POST',{}), error => error instanceof RequestFailure && error.status===403 && error.requestId==='test-request');
  assert.equal(count,1);
});
test('unreadable successful responses are not accepted', async t => {
  t.mock.method(globalThis,'fetch',async()=>new Response('<html>proxy failure</html>'));
  await assert.rejects(api('/api/v1/workspaces'),error=>error.code==='invalid_response');
});
test('session schema is checked before it is used', async t => {
  t.mock.method(globalThis,'fetch',async()=>json({user:null}));
  await assert.rejects(loadSession(),error=>error.code==='invalid_session');
});
test('external and non-API routes cannot receive credentials', async () => {
  for (const path of ['https://evil.test/api/v1/x','//evil.test/api/v1/x','/health/live']) await assert.rejects(api(path));
});
test('network failures and aborted requests remain distinguishable', async t => {
  t.mock.method(globalThis,'fetch',async()=>{throw new TypeError('Failed to fetch');});
  await assert.rejects(api('/api/v1/workspaces'),error=>error.code==='network_error');
  t.mock.method(globalThis,'fetch',async()=>{throw new DOMException('Cancelled','AbortError');});
  await assert.rejects(api('/api/v1/workspaces'),error=>error.name==='AbortError');
});


test('late session polling cannot overwrite a newer authenticated result', async t => {
  let finish; t.mock.method(globalThis, 'fetch', () => new Promise(resolve => {finish=resolve;}));
  const pending = loadSession();
  const authenticated = {...session, csrf_token:'b'.repeat(64), user:{id:'user', email:'new@example.test', display_name:'New owner'}};
  rememberSession(authenticated); finish(json(session));
  assert.deepEqual(await pending, authenticated);
});
