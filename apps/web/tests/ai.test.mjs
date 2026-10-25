import test from 'node:test';
import assert from 'node:assert/strict';
import {parseMicroUSD,formatMicroUSD,selectableModel,modelStatus,probeRequest} from '../.test-build/lib/ai.js';
for (const [value,result] of [['0',0],['0.000001',1],['0.002560',2560],['1',1000000],['1000.000000',1000000000],['01.50',1500000]])
  test(`exact USD parser ${value}`,()=>assert.equal(parseMicroUSD(value),result));
for (const value of ['', ' 1', '1 ', '-1', '+1', 'NaN', 'Infinity', '1e3', '1,00', '.5','0.0000001','1000.000001','99999999','1.'])
  test(`reject invalid USD ${value}`,()=>assert.throws(()=>parseMicroUSD(value)));
for (const [value,result] of [[0,'$0.000000'],[1,'$0.000001'],[2560,'$0.002560'],[1500000,'$1.500000'],[null,'Unknown'],[-1,'Invalid amount'],[0.1,'Invalid amount']])
  test(`USD formatting ${value}`,()=>assert.equal(formatMicroUSD(value),result));
const connection={id:'fixture',generation:1,enabled:true};
const model={id:'model',remote_id:'synthetic-model',generation:1,available:true,probe_state:'unknown',document:{text_generation:null,structured_output:null}};
test('unknown capability allows only explicit compatibility discovery',()=>{assert.ok(selectableModel(model,connection));assert.match(modelStatus(model,connection),/not verified/);});
for (const [change,over] of [[{available:false},{}],[{generation:2},{}],[{}, {enabled:false}],[{document:{text_generation:false}},{}],[{document:{structured_output:false}},{}]])
  test('exclude unavailable/incompatible model '+JSON.stringify([change,over]),()=>assert.equal(selectableModel({...model,...change},{...connection,...over}),false));
test('passing probe does not claim quality',()=>assert.match(modelStatus({...model,probe_state:'passed'},connection),/quality not evaluated/));
const quote={quote_hash:'a'.repeat(64),specification:{reservation_microusd:2560}};
const id='11111111-1111-4111-8111-111111111111';
test('one reviewed probe request contains no prompt, credential or evidence',()=>{
 const value=probeRequest(quote,id);assert.deepEqual(value,{request_id:id,quote_hash:'a'.repeat(64),confirmed_reservation_microusd:2560,payer_approved:true});
 assert.deepEqual(probeRequest(quote,id),value);
});
for (const value of ['', '-'.repeat(36),'x'.repeat(36),'11111111111141118111111111111111'])
  test('probe request rejects invalid UUID '+value,()=>assert.throws(()=>probeRequest(quote,value)));
test('probe request rejects stale malformed fingerprint',()=>assert.throws(()=>probeRequest({...quote,quote_hash:'bad'},id)));
