import test from 'node:test';
import assert from 'node:assert/strict';
import {parseMoney,formatCents,moneyInput,poolWeight,validateMonth,monthInTimezone,scenarioHash,parseScenarioHash,assertNonPayable,maxCents} from '../.test-build/lib/simulator.js';
const A='00000000-0000-0000-0000-000000000001',B='00000000-0000-0000-0000-000000000002',C='00000000-0000-0000-0000-000000000003';
for(const [input,cents] of [['0',0],['0.01',1],['10.2',1020],['10000.00',1000000],[' 12.34 ',1234],['10000000000.00',maxCents]])
  test(`parse exact hypothetical USD ${input}`,()=>assert.equal(parseMoney(input),cents));
for(const input of ['-1','NaN','Infinity','1e2','1,000','$1','0.001','1.','+1','','10000000000.01','100000000000','1 00','1,50'])
  test(`reject ambiguous money input ${JSON.stringify(input)}`,()=>assert.throws(()=>parseMoney(input)));
for(const [cents,text] of [[0,'$0.00'],[1,'$0.01'],[99,'$0.99'],[1000000,'$10,000.00'],[maxCents,'$10,000,000,000.00']])
  test(`format ${cents} cents exactly`,()=>{assert.equal(formatCents(cents),text);assert.equal(parseMoney(moneyInput(cents)),cents);});
for(const value of [-1,true,'100',1.2,NaN,Infinity,Number.MAX_SAFE_INTEGER,maxCents+1])
  test(`reject invalid cents display ${String(value)}`,()=>assert.throws(()=>formatCents(value)));
test('basis-point pool weights are exact display values',()=>{assert.equal(poolWeight(7000),'70.00%');assert.equal(poolWeight(3000),'30.00%');assert.throws(()=>poolWeight(10001));});
for(const month of ['2026-09','2000-01','9998-12'])test(`valid accounting month ${month}`,()=>assert.equal(validateMonth(month),month));
for(const month of ['2026-9','2026-13','9999-01','1999-12','2026-01-01',''])test(`invalid accounting month ${month}`,()=>assert.throws(()=>validateMonth(month)));
test('month selection uses policy timezone at UTC month boundary',()=>{const date=new Date('2026-10-01T02:00:00Z');assert.equal(monthInTimezone('UTC',date),'2026-10');assert.equal(monthInTimezone('America/Puerto_Rico',date),'2026-09');});
test('scoped scenario links round-trip without tokens',()=>{const hash=scenarioHash(A,B,C);assert.deepEqual(parseScenarioHash(hash),{workspaceId:A,projectId:B,scenarioId:C});assert.ok(!hash.includes('?'));});
for(const hash of ['#scenario/x/y/z',`#scenario/${A}/${B}/${C}/extra`,`#scenario/${A}/${B}/${C}?token=secret`,'https://evil.test','#projects'])
  test(`reject malformed scenario link ${hash}`,()=>assert.equal(parseScenarioHash(hash),null));
test('link builder rejects traversal and external paths',()=>assert.throws(()=>scenarioHash(A,B,'../other')));
test('refuses payable or misclassified results',()=>{for(const r of [{kind:'distribution',payable:false,result:{payable:false,hypothetical:true}},{kind:'hypothetical_simulation',payable:true,result:{payable:false,hypothetical:true}},{kind:'hypothetical_simulation',payable:false,result:{payable:true,hypothetical:true}},{kind:'hypothetical_simulation',payable:false,result:{payable:false,hypothetical:false}}])assert.throws(()=>assertNonPayable(r));});
test('hypothetical result keeps its original record',()=>{const r={kind:'hypothetical_simulation',payable:false,result:{payable:false,hypothetical:true}};assert.equal(assertNonPayable(r),r);});
