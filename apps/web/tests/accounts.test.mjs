import test from 'node:test';
import assert from 'node:assert/strict';
import { entryFromHash, invitationUrl, isAuthSession, authenticatedAppHash } from '../.test-build/lib/accounts.js';
const token = 'a'.repeat(43);
const valid = { user: null, csrf_token: 'b'.repeat(64), session_id: 'id', expires_at: '2026-09-14T00:00:00Z', bootstrap_required: true, password_min_length: 15 };

test('sign-in preserves application drilldowns and consumes account-entry fragments',()=>{
  const profile='#analysis?project=11111111-1111-1111-1111-111111111111&person=github%3A123';
  assert.equal(authenticatedAppHash(profile),profile);
  assert.equal(authenticatedAppHash('#projects?section=reconstruction'),'#projects?section=reconstruction');
  assert.equal(authenticatedAppHash('#account'),'#account');
  for(const h of ['', '#invite/'+token,'#recover/'+token,'https://evil.test'])assert.equal(authenticatedAppHash(h),'#analysis');
});

test('invitation and recovery fragments accept only bounded local formats', () => {
  assert.deepEqual(entryFromHash('#invite/' + token), {mode: 'invite', token});
  assert.deepEqual(entryFromHash('#recover/' + token), {mode: 'recover', token});
  assert.deepEqual(entryFromHash('#invite'), {mode: 'invite', token: ''});
  for (const bad of ['', '#invite/short', '#invite/' + token + '?url=https://evil.test', '#login', '#invite/../../x']) assert.equal(entryFromHash(bad), null);
});
test('invitation URLs never place credentials in a query or another origin', () => {
  const url = new URL(invitationUrl('http://localhost:5173', '/?old=anything', '#invite/' + token));
  assert.equal(url.search, ''); assert.equal(url.hash, '#invite/' + token); assert.equal(url.origin, 'http://localhost:5173');
  assert.throws(() => invitationUrl('http://localhost:5173', 'https://evil.test/', '#invite/' + token));
  assert.throws(() => invitationUrl('http://localhost:5173', '/', '#recover/' + token));
});
test('session validation rejects malformed and secretless responses', () => {
  assert.ok(isAuthSession(valid));
  assert.ok(isAuthSession({...valid, user: {id:'x', email:'member@example.test', display_name:'Member'}}));
  for (const bad of [null, [], {}, {...valid, csrf_token:'invalid'}, {...valid, expires_at:'not-a-date'}, {...valid, user:{}}, {...valid, bootstrap_required:0}]) assert.equal(isAuthSession(bad), false);
});
test('password-only MFA challenge is a valid unauthenticated session', () => {
  assert.ok(isAuthSession({...valid,bootstrap_required:false,mfa_required:true,mfa_enrolled:true}));
});
test('MFA challenge cannot carry a logged-in user', () => {
  assert.equal(isAuthSession({...valid,mfa_required:true,user:{id:'x',email:'x@example.test',display_name:'X'}}),false);
});
test('MFA flags reject truthy strings and numbers', () => {
  for (const item of [{mfa_required:'true'},{mfa_required:1},{mfa_enrolled:'false'},{mfa_enrolled:0}]) assert.equal(isAuthSession({...valid,...item}),false);
});
test('fully verified session retains normal account information', () => {
  assert.ok(isAuthSession({...valid,mfa_required:false,mfa_enrolled:true,user:{id:'x',email:'x@example.test',display_name:'X'}}));
});
