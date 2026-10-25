import { test } from 'node:test';
import assert from 'node:assert/strict';
import { parseAnalysisRoute,analysisHash,filterAnalysis,manualWorkDay,manualPerformedAt,repositoryActivityRange,analysisUtcDayRange,repositoryLinks } from '../.test-build/lib/analysis.js';
import { utcDayRange } from '../.test-build/lib/github.js';

test('Contributor and outcome deep links survive exact round trip',()=>{
  const r={workspace:'11111111-1111-1111-1111-111111111111',project:'22222222-2222-2222-2222-222222222222',report:'33333333-3333-3333-3333-333333333333',person:'github:123',outcome:'a'.repeat(64)};
  assert.deepEqual(parseAnalysisRoute(analysisHash(r)),r);
});
test('Malformed route identifiers are ignored',()=>{
  assert.deepEqual(parseAnalysisRoute('#analysis?project=../private&person=https://evil.test&outcome=bad'),{workspace:'',project:'',report:'',person:'',outcome:''});
});
test('A shared contributor link retains the publication independently of a raw report',()=>{
  const route={workspace:'11111111-1111-1111-1111-111111111111',project:'22222222-2222-2222-2222-222222222222',report:'',person:'github:1',outcome:'a'.repeat(64),publication:'33333333-3333-3333-3333-333333333333'};
  assert.deepEqual(parseAnalysisRoute(analysisHash(route)),route);
  assert.equal(parseAnalysisRoute('#analysis?publication=../raw-drafts').publication,undefined);
});
test('Repository and contributor display filters keep the project denominator',()=>{
  const d={proposed_denominator_atoms:10000,outcomes:[{id:'a',repositories:['team/game'],contributors:[{key:'github:1'}],proposal:null},{id:'b',repositories:['team/editor'],contributors:[{key:'github:2'}],proposal:null}],contributors:[{key:'github:1',outcome_ids:['a'],share:{numerator:2500,denominator:10000}},{key:'github:2',outcome_ids:['b'],share:{numerator:7500,denominator:10000}}]};
  const result=filterAnalysis(d,'team/game','github:1');
  assert.equal(result.denominator,10000);assert.equal(result.people[0].share.denominator,10000);assert.equal(result.outcomes.length,1);
});

test('Editing a manual entry preserves the exact instant across a UTC period boundary',()=>{
  const entry={performed_at:'2026-02-01T00:30:00+02:00'};
  assert.equal(manualWorkDay(entry.performed_at),'2026-01-31');
  assert.equal(manualPerformedAt('2026-01-31',entry),entry.performed_at);
  assert.equal(manualPerformedAt('2026-01-30',entry),'2026-01-30T12:00:00Z');
  assert.equal(manualPerformedAt('2026-01-20'),'2026-01-20T12:00:00Z');
});

test('Overview omits unused people while retaining manual choices and project denominators',()=>{
  const d={proposed_denominator_atoms:1000,outcomes:[{id:'a',repositories:[],contributors:[{key:'manual:1'}],proposal:null}],contributors:[{key:'manual:1',outcome_ids:['a']},{key:'local:2',outcome_ids:[]}]};
  assert.deepEqual(filterAnalysis(d,'','').people.map(p=>p.key),['manual:1']);
  assert.equal(d.contributors.length,2);
  assert.equal(filterAnalysis(d,'','').denominator,1000);
  assert.deepEqual(filterAnalysis(d,'','local:2').people.map(p=>p.key),['local:2']);
  assert.deepEqual(filterAnalysis(d,'team/game','').people,[]);
});

test('An inactive repository suggests a bounded year around its actual last commit',()=>{
  const now=Date.parse('2026-10-08T00:00:00Z');
  assert.deepEqual(repositoryActivityRange([{latest_commit_at:'2024-07-26T02:27:49Z'}],now),{start:'2023-07-27',end:'2024-07-27'});
  assert.equal(repositoryActivityRange([{}],now),null);
  assert.equal(repositoryActivityRange([{latest_commit_at:'invalid'},{latest_commit_at:'2099-01-01T00:00:00Z'}],now),null);
});

test('Activity suggestions keep a single shared UTC period and supported date bounds',()=>{
  assert.deepEqual(repositoryActivityRange([{latest_commit_at:'2024-07-26T02:27:49Z'},{latest_commit_at:'2025-03-01T00:30:00+02:00'}],Date.parse('2026-10-08T00:00:00Z')),{start:'2024-02-29',end:'2025-03-01'});
  assert.deepEqual(repositoryActivityRange([{latest_commit_at:'1970-01-01T00:00:00Z'}]),{start:'1970-01-01',end:'1970-01-02'});
});

test('Analysis end is excluded exactly, including a full 366-day activity shortcut',()=>{
  assert.deepEqual(utcDayRange('2023-07-27','2024-07-27'),{start_at:'2023-07-27T00:00:00Z',end_before:'2024-07-27T00:00:00Z'});
  assert.deepEqual(utcDayRange('2024-07-25','2024-07-27'),{start_at:'2024-07-25T00:00:00Z',end_before:'2024-07-27T00:00:00Z'});
  for(const dates of [['2023-07-26','2024-07-27'],['2024-07-27','2024-07-27'],['2024-02-31','2024-03-02'],['invalid','2024-07-27']])assert.throws(()=>utcDayRange(...dates));
});

test('A suggested window includes today only up to the exact request time',()=>{
  const now=Date.parse('2026-10-08T03:12:00Z');
  const suggested=repositoryActivityRange([{latest_commit_at:'2026-10-08T01:00:00Z'}],now);
  assert.equal(suggested.end,'2026-10-09');
  assert.equal(analysisUtcDayRange(suggested.start,suggested.end,now).end_before,'2026-10-08T03:12:00.000Z');
  assert.throws(()=>analysisUtcDayRange('2026-10-01','2026-10-10',now));
  assert.deepEqual(analysisUtcDayRange('2024-07-25','2024-07-27',now),utcDayRange('2024-07-25','2024-07-27'));
});

test('Repository link input gives clear bounded validation without echoing secrets',()=>{
  assert.deepEqual(repositoryLinks(' https://github.com/team/game.git/\nhttps://github.com/team/editor '),['https://github.com/team/game','https://github.com/team/editor']);
  for(const value of ['', 'https://github.com/team/game https://github.com/TEAM/GAME', 'http://github.com/team/game', 'https://github.com/team/game/issues', 'https://github.com/team/game?token=synthetic-sensitive-value', 'https://github.com/team/game#fragment', 'https://user:password@github.com/team/game', 'https://other.test/team/game']){
    assert.throws(()=>repositoryLinks(value),e=>!e.message.includes('synthetic-sensitive-value')&&!e.message.includes('password@'));
  }
  assert.throws(()=>repositoryLinks(Array.from({length:9},(_,i)=>'https://github.com/team/repo'+i).join(' ')));
});
