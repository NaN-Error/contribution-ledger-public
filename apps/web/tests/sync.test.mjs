import test from 'node:test';
import assert from 'node:assert/strict';
import {boundedInteger,syncPayload,jobActionPayload,retryReady,displayInstant,summaryCounts} from '../.test-build/lib/sync.js';
for(const s of ['','-1','1.5','NaN','Infinity','1e2',' 60','9007199254740993']) {
  test(`strict sync integer rejects ${s||'empty'}`,()=>assert.throws(()=>boundedInteger(s,1,10080,'Interval')));
}
for(const [value,min,max] of [['60',60,10080],['10080',60,10080],['7',1,90]]) {
  test(`strict sync integer accepts ${value}`,()=>assert.equal(boundedInteger(value,min,max,'Value'),Number(value)));
}
const fields={interval:'360',lookback:'7',requests:'200',entities:'50'};
test('sync payload carries exact scope and explicit review',()=>assert.deepEqual(syncPayload(2,true,fields,'Reviewed fictional schedule',true),{
  expected_version:2,enabled:true,interval_minutes:360,lookback_days:7,request_limit:200,entity_limit:50,reason:'Reviewed fictional schedule',reviewed:true}));
test('sync payload requires review',()=>assert.throws(()=>syncPayload(0,true,fields,'Sufficient explanation',false)));
test('sync payload requires a reason',()=>assert.throws(()=>syncPayload(0,true,fields,'small',true)));
test('sync payload cannot invent a version',()=>assert.throws(()=>syncPayload(NaN,true,fields,'Sufficient explanation',true)));
test('pause is explicit false not omitted',()=>assert.equal(syncPayload(1,false,fields,'Pause for a fixture',true).enabled,false));
test('retry time accepts past instant only',()=>{assert.equal(retryReady('2026-09-14T00:00:00Z',Date.parse('2026-09-14T01:00:00Z')),true);assert.equal(retryReady('2026-09-14T02:00:00Z',Date.parse('2026-09-14T01:00:00Z')),false);});
test('unknown retry time fails closed',()=>assert.equal(retryReady('bad'),false));
test('absent instant is not a made up date',()=>assert.equal(displayInstant(null),'Not recorded'));
test('invalid instant is visible',()=>assert.equal(displayInstant('bad'),'Invalid recorded time'));
test('empty counts are explicit',()=>assert.equal(summaryCounts({}),'No recorded activity'));
test('state count rendering stable by key',()=>assert.equal(summaryCounts({running:2,completed_incomplete:1}),'completed incomplete: 1 · running: 2'));

test('job action uses the exact existing API schema without an unsupported flag',()=>assert.deepEqual(jobActionPayload(2,'  Cancel the fictional import  '),{expected_version:2,reason:'Cancel the fictional import'}));
for(const version of [0,-1,NaN,1.5,2147483648])test(`job command rejects invalid version ${version}`,()=>assert.throws(()=>jobActionPayload(version,'A sufficient reason')));
for(const reason of ['short','x'.repeat(501),'bad\x00command'])test(`job command rejects unsafe/bounded reason ${reason.length}`,()=>assert.throws(()=>jobActionPayload(1,reason)));
