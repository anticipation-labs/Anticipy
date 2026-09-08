/** Actual SQLite writes: a stale consent cannot restore cancelled/changed work. */
import assert from 'node:assert/strict';
import { create, update, view, type RecordsRequest } from '../src/api/records.ts';
import { COLLECTIONS } from '../src/api/schema.ts';
import { openTestD1 } from './sqlite-d1.ts';

const t = openTestD1();
const req = (values: Partial<RecordsRequest> = {}): RecordsRequest => ({
  collection: COLLECTIONS.jobs, recordId: null, method: 'PATCH',
  url: new URL('https://api.anticipy.ai/api/collections/jobs/records'),
  body: null, principal: {kind: 'service'}, ...values,
});
const body = {goal: 'Send contract to Priya', status: 'awaiting_confirm', owner_ref: 'consenttestown01',
  owner: 'legacy', params: '{"source":"Send contract"}', device_id: 'test'};
async function task() {
  const made = await create({DB:t.db}, req({method:'POST', body}));
  assert.equal(made.status, 200);
  const row = await made.json() as {id:string};
  const response = await view({DB:t.db}, req({recordId:row.id, method:'GET'}));
  const etag = response.headers.get('ETag');
  assert.match(etag!, /^"[a-f0-9]{64}"$/);
  assert.equal(response.headers.get('Cache-Control'), 'private, no-store, no-transform');
  return {id:row.id, etag, stored: t.query<Record<string,unknown>>('SELECT * FROM jobs WHERE id = ?', row.id)[0]};
}
let checks = 0;
for (const mutation of [{status:'cancelled'}, {goal:'Send contract to Morgan'},
                       {params:'{"corrections":{"recipient":"Morgan"}}'}, {owner_ref:'anotherowner001'}]) {
  const j = await task();
  assert.equal((await update({DB:t.db}, req({recordId:j.id, body:mutation}))).status, 200);
  for (const storedRow of [undefined, j.stored]) {
    const attempt = await update({DB:t.db}, req({recordId:j.id, ifMatch:j.etag, storedRow,
      body:{status:'queued', params:'{"authorized":true}'}}));
    assert.equal(attempt.status, 412, 'stale approval must lose even after policy accepted the old row');
    const saved = t.query<Record<string,unknown>>('SELECT * FROM jobs WHERE id = ?', j.id)[0];
    for (const [key,value] of Object.entries(mutation)) assert.equal(saved[key],value);
    checks++;
  }
}
const fresh = await task();
assert.equal((await update({DB:t.db}, req({recordId:fresh.id, ifMatch:fresh.etag,
  body:{status:'queued', params:'{"authorized":true}'}}))).status,200);
assert.equal((await update({DB:t.db}, req({recordId:fresh.id, ifMatch:fresh.etag,
  storedRow:fresh.stored, body:{status:'queued'}}))).status,412, 'approval replay cannot win');
checks += 2;
for (const ifMatch of ['', '*', '"fake"']) {
  assert.equal((await update({DB:t.db}, req({recordId:fresh.id, ifMatch, body:{status:'queued'}}))).status,400);
  checks++;
}
const isolated = await task();
assert.equal((await update({DB:t.db}, req({recordId:isolated.id, ifMatch:isolated.etag,
  forcedScope:{column:'owner_ref',value:'someoneelse'}, body:{status:'queued'}}))).status,404);
checks++;
// Clock precision cannot stand in for question/authority identity. These
// writes deliberately keep `updated` identical to the pre-model record.
for (const [column,value] of [
  ['result','A different question'], ['workflow_version',2], ['effect_key','new-effect'],
  ['lease_token','new-lease'], ['lease_until','2030-01-01 00:00:00.000Z'],
  ['receipt','different-receipt'], ['effect_uncertain',1], ['consequence','consequential'],
] as const) {
  const j = await task();
  await t.db.prepare(`UPDATE jobs SET "${column}" = ? WHERE id = ?`).bind(value,j.id).run();
  const attempt = await update({DB:t.db}, req({recordId:j.id, ifMatch:j.etag, storedRow:j.stored,
    body:{status:'queued',params:'{"authorized":true}'}}));
  assert.equal(attempt.status,412,`same-time ${column} change must reject old authority`);
  assert.equal(t.query<Record<string,unknown>>('SELECT * FROM jobs WHERE id = ?',j.id)[0][column],value);
  checks++;
}
t.close();
console.log(`${checks} approval precondition checks passed`);
