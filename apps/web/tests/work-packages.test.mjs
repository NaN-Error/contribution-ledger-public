import test from 'node:test';
import assert from 'node:assert/strict';
import { newScope, newDeliverable, buildScope, scopeDraft, boundedWorkBody, workStates, workRoles, actionLabels } from '../.test-build/lib/workPackages.js';
const A='00000000-0000-0000-0000-000000000001';
const B='00000000-0000-0000-0000-000000000002';
const D='00000000-0000-0000-0000-000000000003';
function valid() {
  return { ...newScope(A, 'Reconnect players'), outcome:'Players reconnect to the same active match.', criteria:'A brief disconnection restores the same player session.', evidence:'Provide reproducible test results for reconnect cases.',
    deliverables:[{ ...newDeliverable(D),title:'Recover player session',outcome:'Reconnect after a temporary network interruption.',criteria:'The restored session matches the original state.',evidence:'Provide an integration test recording.',units:'100',mode:'units',entries:[{key:'a',user_id:A,role:'implementation',amount:'100'}]}] };
}
test('new drafts contain no invented credit or implicit completion',()=>{
  assert.equal(newScope(A).deliverables.length,0);
  assert.equal(newDeliverable(D).entries.length,0);
  assert.ok(workStates.includes('completed'));assert.ok(!('complete' in actionLabels));
  assert.ok(workRoles.includes('testing') && workRoles.includes('design'));
});
test('complete unit plan builds exact atom amounts and stable deliverable IDs',()=>{
  const result=buildScope(valid(),100_000);
  assert.equal(result.deliverables[0].budget_atoms,100_000);
  assert.deepEqual(result.deliverables[0].attribution,{mode:'units',entries:[{user_id:A,role:'implementation',atoms:100_000}]});
  assert.equal(result.deliverables[0].id,D);
  assert.ok(!('earned_atoms' in result));
});
test('partial attribution remains empty rather than assigning units to the owner',()=>{
  const draft=valid();draft.deliverables[0].entries=[];
  assert.equal(buildScope(draft,100_000).deliverables[0].attribution.entries.length,0);
});
test('percent entry converts exactly to basis points, not floating-point balances',()=>{
  const draft=valid();draft.intended.push(B);draft.deliverables[0].mode='percent';
  draft.deliverables[0].entries=[{key:'a',user_id:A,role:'implementation',amount:'70.25'},{key:'b',user_id:B,role:'testing',amount:'29.75'}];
  const result=buildScope(draft,100_000);
  assert.deepEqual(result.deliverables[0].attribution.entries.map(e=>e.basis_points),[7025,2975]);
});
for(const mode of ['units','percent']) for(const invalid of ['-1','1e2','1,000','0','1.0001']) {
  test(`${mode} rejects malformed or zero attribution amount ${invalid}`,()=>{
    const draft=valid();draft.deliverables[0].mode=mode;draft.deliverables[0].entries[0].amount=invalid;
    assert.throws(()=>buildScope(draft,100_000));
  });
}
test('child-budget sum cannot exceed parent even after splitting',()=>{
  const draft=valid();draft.deliverables.push({...structuredClone(draft.deliverables[0]),id:B});
  assert.throws(()=>buildScope(draft,100_000),/exceed/);
});
test('criteria have meaningful length, no duplicates and bounded count',()=>{
  for(const criteria of ['','tiny','Same useful criterion.\nSame useful criterion.',Array.from({length:21},(_,i)=>`Useful criterion ${i}`).join('\n')]) {
    const draft=valid();draft.criteria=criteria;assert.throws(()=>buildScope(draft,100_000),/criteria/);
  }
});
test('attribution must identify selected intended contributors and unique roles per person',()=>{
  const draft=valid();draft.deliverables[0].entries[0].user_id=B;
  assert.throws(()=>buildScope(draft,100_000),/intended/);
  draft.deliverables[0].entries[0].user_id=A;
  draft.deliverables[0].entries.push({...draft.deliverables[0].entries[0],key:'duplicate'});
  assert.throws(()=>buildScope(draft,100_000),/repeat/);
});
test('one person may plan two distinct roles within the same budget',()=>{
  const draft=valid();draft.deliverables[0].entries=[{key:'a',user_id:A,role:'implementation',amount:'80'},{key:'b',user_id:A,role:'testing',amount:'20'}];
  assert.equal(buildScope(draft,100_000).deliverables[0].attribution.entries.length,2);
});
test('empty coordinator or intended roster fails before submission',()=>{
  let draft=valid();draft.coordinator='';assert.throws(()=>buildScope(draft,100_000));
  draft=valid();draft.intended=[];assert.throws(()=>buildScope(draft,100_000));
});
test('safe snapshots convert back to an editable draft without derived server fields',()=>{
  const doc={...buildScope(valid(),100_000),participant_labels:{[A]:'Person A'},budget_atoms:100_000,deliverable_atoms:100_000,unplanned_atoms:0,
    milestone_id:A,allocation_id:B,policy_id:D,policy_version:1,policy_hash:'0'.repeat(64),category:'code',pool_key:'release'};
  const draft=scopeDraft(doc);const again=buildScope(draft,100_000);
  assert.equal(draft.deliverables[0].units,'100');assert.equal(draft.deliverables[0].id,D);
  assert.ok(!('participant_labels' in again));
});
test('percentage snapshot edits retain original requested shares, not rounded atoms',()=>{
  const input=buildScope(valid(),100_000);
  input.deliverables[0].attribution={mode:'percent',entries:[{user_id:A,role:'implementation',basis_points:7025}]};
  const draft=scopeDraft(input);
  assert.equal(draft.deliverables[0].entries[0].amount,'70.25');
  assert.equal(buildScope(draft,100_000).deliverables[0].attribution.entries[0].basis_points,7025);
});
test('UTF-8 request-size cap checks bytes rather than JS character count',()=>{
  assert.deepEqual(boundedWorkBody({scope:'synthetic'}),{scope:'synthetic'});
  assert.throws(()=>boundedWorkBody({scope:'x'.repeat(64000)}),/64 KB/);
  assert.throws(()=>boundedWorkBody({scope:'🎮'.repeat(17000)}),/64 KB/);
});
