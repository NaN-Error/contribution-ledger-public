import test from 'node:test';
import assert from 'node:assert/strict';
import { desktopToken } from '../.test-build/lib/desktop.js';

test('desktop launch credentials accept only exact fragments without redirects or queries', () => {
  const token='A'.repeat(43);
  assert.equal(desktopToken('#desktop/'+token),token);
  for (const hash of ['#desktop/short','#desktop/'+token+'?next=https://evil.test',
    '#desktop/'+token+'/','#desktop/'+'A'.repeat(44),'#desktop/'+'%41'.repeat(43),'#analysis']) {
    assert.equal(desktopToken(hash),null);
  }
});
