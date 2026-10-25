import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { isSystemStatus, fetchStatus, formatDate, pageFromHash, ApiFailure } from '../.test-build/lib/status.js';
import { filterPhases } from '../.test-build/lib/roadmap.js';
const sample = JSON.parse(readFileSync(new URL('./status-fixture.json', import.meta.url), 'utf8'));

test('accepts the documented ready payload', () => assert.ok(isSystemStatus(sample)));
test('rejects absent and partial payloads', () => {
  for (const value of [null, [], {}, 'ok', { ...sample, database: null }]) assert.equal(isSystemStatus(value), false);
});
test('rejects invalid timestamps and inconsistent readiness', () => {
  assert.equal(isSystemStatus({ ...sample, checked_at: 'not-a-date' }), false);
  assert.equal(isSystemStatus({ ...sample, database: { status: 'unavailable', message: 'Down' } }), false);
});
test('a present marker needs an ID and timestamp', () => {
  assert.equal(isSystemStatus({ ...sample, persistence: { status: 'present', marker_id: null, created_at: null } }), false);
});
test('known routes are normalized and unknown routes are harmless', () => {
  assert.equal(pageFromHash('#setup'), 'setup'); assert.equal(pageFromHash('#/roadmap'), 'roadmap');
  assert.equal(pageFromHash('#javascript:alert(1)'), 'overview');
});
test('roadmap supports case-insensitive filtering and an empty state', () => {
  assert.equal(filterPhases('').length, 16); assert.ok(filterPhases('GITHUB').length > 0);
  assert.equal(filterPhases('no_such_phase_001').length, 0);
});
test('date formatter tolerates unavailable values', () => {
  assert.equal(formatDate(null), 'Not available'); assert.equal(formatDate('bad-date'), 'Not available');
  assert.notEqual(formatDate(sample.checked_at), 'Not available');
});
test('fetch returns real successful status', async () => {
  const result = await fetchStatus(new AbortController().signal, async (url, options) => {
    assert.equal(url, '/api/v1/system/status'); assert.equal(options.cache, 'no-store');
    return new Response(JSON.stringify(sample), { status: 200 });
  });
  assert.equal(result.status, 'ready');
});
test('503 with a valid degraded payload is displayed rather than discarded', async () => {
  const degraded = { ...sample, status: 'degraded', database: { status: 'unavailable', message: 'Down' }, migrations: { ...sample.migrations, status: 'unavailable' } };
  const result = await fetchStatus(new AbortController().signal, async () => new Response(JSON.stringify(degraded), { status: 503 }));
  assert.equal(result.status, 'degraded');
});
test('proxy failures do not turn into healthy status', async () => {
  await assert.rejects(fetchStatus(new AbortController().signal, async () => new Response('private backend error', { status: 502 })), ApiFailure);
});
test('malformed payloads cannot become status results', async () => {
  for (const body of ['not JSON', '{}']) await assert.rejects(fetchStatus(new AbortController().signal, async () => new Response(body, { status: 200 })), ApiFailure);
});
test('an inconsistent HTTP status is rejected', async () => {
  await assert.rejects(fetchStatus(new AbortController().signal, async () => new Response(JSON.stringify(sample), { status: 503 })), ApiFailure);
});
test('request IDs survive errors, but raw error bodies do not', async () => {
  const id = 'e51053a3-f0d6-4f04-945c-214bf4e365ac';
  await assert.rejects(fetchStatus(new AbortController().signal, async () => new Response('private secret', { status: 500, headers: { 'X-Request-ID': id } })), error => {
    assert.equal(error.requestId, id); assert.equal(error.message.includes('private secret'), false); return true;
  });
});

for (const [key, bad] of [['database', ['ok']], ['migrations', ['current']], ['persistence', ['empty']]]) {
  test(`rejects coercible non-string ${key} status`, () => {
    const value = structuredClone(sample);
    value[key].status = bad;
    assert.equal(isSystemStatus(value), false);
  });
}
