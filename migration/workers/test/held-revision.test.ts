import assert from 'node:assert/strict';
import { heldRevision } from '../src/policy/held_revision.ts';
import { researchLane } from '../src/policy/research_lane.ts';
import { workflowGuard } from '../src/policy/workflow_guard.ts';
import type { Ctx } from '../src/policy/chain.ts';

function fixture() {
  const common = { goal: 'Complete the agreed task', owner_ref: 'owner-one',
    consequence: 'consequential', lineage_key: 'lineage', scope_digest: 'scope',
    effect_key: 'effect', attempts: 1 };
  const before = { ...common, plan_id: 'plan-one', version: 2, state: 'needs_user',
    facts: {}, required: [], approval: null, receipt: null, lease: null };
  const after = { ...before, version: 3, state: 'draft', required: ['What is still needed?'] };
  const row = { ...common, id: 'job-one', workflow_id: 'plan-one', workflow_version: 2,
    workflow_state: 'needs_user', status: 'needs_user', lane: 'research', approval: '',
    receipt: '', lease_token: '', effect_uncertain: 0,
    params: JSON.stringify({ _workflow: before, _effect: { touches: 'world' } }) };
  const body = { ...common, workflow_version: 3, workflow_state: 'draft',
    status: 'awaiting_confirm', lane: '', approval: '', receipt: '', lease_token: '',
    params: JSON.stringify({ _workflow: after, _effect: { touches: 'world' }, _hand: { hand: 'browser' } }) };
  const url = new URL('https://api.anticipy.ai/api/collections/jobs/records/job-one');
  const ctx = { request: new Request(url, { method: 'PATCH' }), url, path: url.pathname,
    method: 'PATCH', body, storedRow: row, principal: { kind: 'service' },
    worker: { fromWorker: true }, forcedScope: null, extraAst: null,
    db: { prepare() { return { bind() { return { first: async () => row }; } }; } },
  } as unknown as Ctx;
  return { row, body, ctx };
}

let checks = 0;
const good = fixture();
assert.equal(heldRevision(good.ctx, good.row, good.body), true);
assert.equal(await researchLane(good.ctx, {}), null);
const verdict = await workflowGuard(good.ctx, {});
assert.equal(verdict, null, verdict ? await verdict.text() : '');
checks += 3;

for (const change of [
  (x: ReturnType<typeof fixture>) => { x.row.status = 'running'; },
  (x: ReturnType<typeof fixture>) => { x.row.receipt = '{}'; },
  (x: ReturnType<typeof fixture>) => { x.row.lease_token = 'active'; },
  (x: ReturnType<typeof fixture>) => { x.row.effect_uncertain = 1; },
  (x: ReturnType<typeof fixture>) => { x.body.workflow_version = 2; },
  (x: ReturnType<typeof fixture>) => { x.body.status = 'queued'; },
  (x: ReturnType<typeof fixture>) => { x.body.approval = '{}'; },
  (x: ReturnType<typeof fixture>) => { x.row.owner_ref = 'other'; },
  (x: ReturnType<typeof fixture>) => { x.ctx.principal = { kind: 'anonymous' }; },
  (x: ReturnType<typeof fixture>) => { x.ctx.request.headers.set('X-Anticipy-Agent-ID', 'browser'); },
]) {
  const x = fixture(); change(x);
  assert.equal(heldRevision(x.ctx, x.row, x.body), false);
  assert.notEqual(await researchLane(x.ctx, {}), null);
  checks += 2;
}
for (const change of [
  (x: ReturnType<typeof fixture>) => { x.ctx.worker.fromWorker = false; },
  (x: ReturnType<typeof fixture>) => { x.ctx.principal = { kind: 'account', ownerId: 'owner-one', row: {} }; },
  (x: ReturnType<typeof fixture>) => { x.row.params = x.row.params.replace('"world"', '"read"'); },
  (x: ReturnType<typeof fixture>) => { x.body.params = x.body.params.replace('"browser"', '"research"'); },
]) {
  const x = fixture(); change(x);
  assert.notEqual(await researchLane(x.ctx, {}), null);
  checks++;
}
console.log(`held task revision: ${checks} checks passed`);
