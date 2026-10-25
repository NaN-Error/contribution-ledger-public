import test from 'node:test';
import assert from 'node:assert/strict';
import { guideSteps, stepsFor, phaseStatus } from '../.test-build/lib/onboarding.js';

test('manual path is usable without GitHub and historical reconstruction', () => {
  const steps = stepsFor('manual');
  assert.ok(steps.some(s => s.id === 'package'));
  assert.ok(!steps.some(s => ['import', 'history'].includes(s.id)));
  assert.ok(steps.some(s => s.id === 'evidence'));
  assert.ok(steps.some(s => s.id === 'finance'));
});
test('existing path includes manual missing work and ordinary review', () => {
  assert.ok(stepsFor('existing').some(s => s.id === 'history'));
  assert.ok(stepsFor('existing').some(s => s.id === 'review'));
});
test('filter is case insensitive and trims whitespace', () => {
  assert.deepEqual(stepsFor('manual', ' EVIDENCE '), stepsFor('manual', 'evidence'));
  assert.ok(stepsFor('manual', 'evidence').length > 0);
});
test('no match is an empty list, not a fallback completion', () => {
  assert.deepEqual(stepsFor('manual', 'unmatched-123456'), []);
});
test('steps have stable unique ids and actual doc references', () => {
  assert.equal(new Set(guideSteps.map(s => s.id)).size, guideSteps.length);
  assert.ok(guideSteps.every(s => s.boundary && s.expected && s.documentation.startsWith('docs/')));
});
test('human pilot and deployment remain visibly pending', () => {
  assert.match(phaseStatus(15), /human pilot pending/);
  assert.match(phaseStatus(16), /verification open/);
});
test('financial step does not claim payment execution', () => {
  assert.match(guideSteps.find(s => s.id === 'finance').boundary, /do not send/);
});
