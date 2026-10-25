import test from 'node:test';
import assert from 'node:assert/strict';
import {api,rememberSession} from '../.test-build/lib/api.js';
const A='00000000-0000-0000-0000-000000000001';
const root=`/api/v1/workspaces/${A}/projects/${A}/simulator`;
function session(){rememberSession({user:{id:A,email:'synthetic@example.test',display_name:'Synthetic'},csrf_token:'a'.repeat(64),bootstrap_required:false,session_id:'synthetic',expires_at:'2026-10-01T00:00:00Z',password_min_length:15});}
// Synthetic transport checks: no React rendering, no live account or money.
test('preview carries integer cents, explicit policy scope, session cookie and CSRF',async()=>{
  session();const prior=globalThis.fetch;
  globalThis.fetch=async(path,options)=>{assert.equal(path,root+'/preview');assert.equal(options.credentials,'same-origin');assert.equal(options.cache,'no-store');assert.equal(options.headers['X-CSRF-Token'],'a'.repeat(64));const b=JSON.parse(options.body);assert.equal(b.amount_cents,1000000);assert.equal(b.source_policy_id,A);assert.equal(b.calculation_policy_id,A);return new Response(JSON.stringify({payable:false,result:{amount_cents:1000000}}),{status:200,headers:{'Content-Type':'application/json'}});};
  try{const result=await api(root+'/preview','POST',{source_policy_id:A,calculation_policy_id:A,month:'2026-09',amount_cents:1000000});assert.equal(result.payable,false);}finally{globalThis.fetch=prior;}
});
test('stale scenario save is reported without retrying or writing a payment',async()=>{
  session();const prior=globalThis.fetch;let calls=0;
  globalThis.fetch=async()=>{calls++;return new Response(JSON.stringify({error:{code:'stale_simulation',message:'Recalculate and review first.'}}),{status:409});};
  try{await assert.rejects(()=>api(root+'/scenarios','POST',{reviewed_snapshot_hash:'a'.repeat(64)}),error=>error.code==='stale_simulation');assert.equal(calls,1);}finally{globalThis.fetch=prior;}
});
test('saved scenario read requires normal local session and no-cache request',async()=>{
  const prior=globalThis.fetch;globalThis.fetch=async(path,options)=>{assert.equal(path,root+'/scenarios/'+A);assert.equal(options.method,'GET');assert.equal(options.cache,'no-store');assert.equal(options.credentials,'same-origin');return new Response(JSON.stringify({id:A,payable:false}),{status:200});};
  try{assert.equal((await api(root+'/scenarios/'+A)).id,A);}finally{globalThis.fetch=prior;}
});
