import test from 'node:test';
import assert from 'node:assert/strict';
import { parseUnits, parseWeight, formatUnits, unitInput, formatBps, formatRatio, explicitInstant, humanLabel, MAX_ATOMS } from '../.test-build/lib/planning.js';

test('decimal unit strings convert into exact integer atoms', () => {
  assert.equal(parseUnits('1.001'), 1001); assert.equal(parseUnits('0.001'), 1);
  assert.equal(parseUnits('1000'), 1_000_000); assert.equal(parseUnits(' 12.30 '), 12300);
  assert.equal(parseUnits('0'), 0); assert.equal(parseUnits('1000000000'), MAX_ATOMS);
});
for (const value of ['', '1,000', '-1', '1e3', '+2', '.5', '01', '1.', '1.0001', 'NaN', 'Infinity', '1000000000.001', '0x12', 'true']) {
  test(`rejects invalid unit input ${JSON.stringify(value)}`, () => assert.throws(() => parseUnits(value)));
}
test('formatting unit atoms preserves all three fractional digits without float multiplication', () => {
  assert.equal(formatUnits(1001), '1.001'); assert.equal(formatUnits(12340000), '12,340');
  assert.equal(formatUnits(1000000001), '1,000,000.001'); assert.equal(unitInput(12340), '12.34');
  for (const atoms of [0, 1, 999, 1000, 90001, 10**12]) assert.equal(parseUnits(unitInput(atoms)), atoms);
  for (const bad of [1.2, -1, NaN, Infinity, MAX_ATOMS + 1]) assert.throws(() => formatUnits(bad));
});
test('pool percentages use exact integer basis points', () => {
  assert.equal(parseWeight('70.25'), 7025); assert.equal(parseWeight('100'), 10000);
  assert.equal(formatBps(7025), '70.25%'); assert.equal(formatBps(1), '0.01%');
  for (const bad of ['70.001', '-1', '100.01', '50,00', '1e2']) assert.throws(() => parseWeight(bad));
});
test('scoped ratios distinguish zero denominator and round only for display', () => {
  assert.equal(formatRatio(1, 3), '33.33%'); assert.equal(formatRatio(1, 6), '16.67%');
  assert.equal(formatRatio(900000, 1000000), '90.00%'); assert.equal(formatRatio(0, 0), 'Not defined');
  assert.equal(formatRatio(MAX_ATOMS, MAX_ATOMS), '100.00%');
  assert.throws(() => formatRatio(2, 1)); assert.throws(() => formatRatio(1.1, 3));
});
test('effective times require explicit offsets; empty means immediate', () => {
  assert.equal(explicitInstant(''), null); assert.equal(explicitInstant('2030-01-01T12:00:00-04:00'), '2030-01-01T12:00:00-04:00');
  assert.equal(explicitInstant('2030-01-01T12:00:00Z'), '2030-01-01T12:00:00Z');
  for (const value of ['2030-01-01', '2030-01-01T12:00:00', 'tomorrow', '2030-01-01T12:00:00+99:00']) assert.throws(() => explicitInstant(value));
});
test('human-readable state labels remain plain text', () => assert.equal(humanLabel('awaiting_acknowledgements'), 'awaiting acknowledgements'));
