// Phase 5 executor smoke test — exercises the Mac executor's critical
// path WITHOUT spinning up Electron:
//
//   1. CDP attach to localhost:9222 — proves the LaunchAgent's Chrome
//      is reachable and we can drive it.
//   2. Typing helper sanity — Gaussian samples are non-negative finite.
//   3. Realtime subscriber subscribes to task.dispatched.{user_id}.
//   4. INSERT an Intent + Task pair into anticipy_intents_v2 +
//      anticipy_tasks_v2 — the subscriber MUST receive the Task within
//      a 5 s window.
//   5. SkillExecutor.run() runs a one-step `navigate` recipe in the
//      attached Chrome and writes the Result to anticipy_results_v2.
//
// Per Rule 13: Phase 5 is not "done" until this passes end-to-end.

const path = require('path');
const dotenv = require('dotenv');
const { createClient } = require('@supabase/supabase-js');
const { v4: uuidv4 } = require('crypto').webcrypto
  ? { v4: () => crypto.randomUUID() }
  : require('crypto');

// Load env from repo .env.local (the engine runtime path).
dotenv.config({ path: path.join(__dirname, '..', '..', '.env.local') });

const { CDPClient } = require('../lib/cdp_client');
const { gaussian, typingPlan } = require('../lib/typing');
const { RealtimeSubscriber } = require('../lib/realtime_subscriber');
const { SkillExecutor } = require('../lib/skill_executor');

const USER_ID = `smoketest-${Date.now()}`;
const cases = [];
function record(name, ok, detail = '') {
  cases.push({ name, ok, detail });
  const sym = ok ? 'PASS' : 'FAIL';
  console.log(`[${sym}] ${name}${detail ? '  — ' + detail : ''}`);
}

async function sleep(ms) { return new Promise((r) => setTimeout(r, ms)); }

async function main() {
  // ── (1) CDP reachable ───────────────────────────────────────────────
  const cdp = new CDPClient();
  let cdpOk = false;
  try {
    const v = await cdp.ready();
    cdpOk = !!v.Browser;
    record('cdp.attach.ready', cdpOk, `Browser=${v.Browser}`);
  } catch (e) {
    record('cdp.attach.ready', false, `error=${e.message || e}`);
  }

  // ── (2) Typing helper sanity ────────────────────────────────────────
  let typingOk = true;
  for (let i = 0; i < 50; i++) {
    const v = gaussian(180, 60);
    if (!isFinite(v) || v < 0) { typingOk = false; break; }
  }
  record('typing.gaussian.bounded', typingOk);
  let planLen = 0;
  for await (const _ of typingPlan('Hello world', { meanMs: 5, stdMs: 1 })) planLen++;
  record('typing.plan.length_matches_input', planLen === 'Hello world'.length, `planLen=${planLen}`);

  // ── (3) Realtime subscriber starts ──────────────────────────────────
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!url || !key) {
    record('env.supabase_keys_present', false, 'NEXT_PUBLIC_SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY missing');
    return summarize();
  }
  record('env.supabase_keys_present', true);
  const supabase = createClient(url, key);

  const received = [];
  const subscriber = new RealtimeSubscriber({
    supabaseUrl: url,
    supabaseServiceKey: key,
    userId: USER_ID,
  })
    .onTask((task) => received.push(task))
    .start();

  // Give the channel time to subscribe before INSERTing.
  await sleep(2500);

  // ── (4) INSERT Intent then Task; subscriber should receive ─────────
  const intentId = crypto.randomUUID();
  const taskId = crypto.randomUUID();

  await supabase.from('anticipy_intents_v2').insert({
    intent_id: intentId,
    user_id: USER_ID,
    utterance_window: { transcript_segments: [{ speaker: 'wearer', text: 'navigate to anticipy.ai' }], start_ts: '', end_ts: '' },
    action_category: 'navigate_to',
    proposed_skill_hint: null,
    slots: { filled: { url: 'https://www.anticipy.ai' }, needs_memory: [], needs_inference: [], ambiguous: [] },
    detection_confidence: 0.9,
    hedge_filter_decision: 'COMMIT',
    hedge_filter_reason: 'smoke',
    proactivity_score: 0.95,
    source: 'typed',
  });

  await supabase.from('anticipy_tasks_v2').insert({
    task_id: taskId,
    intent_id: intentId,
    user_id: USER_ID,
    skill_id: null,
    parameters: { url: 'https://www.anticipy.ai' },
    recipe_steps: [
      { action: 'navigate', target_ref: null, value: 'https://www.anticipy.ai', timeout_ms: 15000, postcondition: null },
    ],
    global_postcondition: null,
    rollback_spec: null,
    rehearsal_required: false,
    irreversible: false,
    aevoy_confirmation_required: false,
  });

  // Wait up to 5s for the Realtime push.
  const deadline = Date.now() + 6000;
  while (Date.now() < deadline && received.length === 0) await sleep(150);
  record(
    'realtime.task_received',
    received.length > 0 && received[0].task_id === taskId,
    `received=${received.length}`
  );

  // ── (5) SkillExecutor runs the recipe; Result lands in anticipy_results_v2 ──
  if (cdpOk) {
    const executor = new SkillExecutor({ cdp, supabase });
    const taskRow = received[0] || {
      task_id: taskId,
      user_id: USER_ID,
      recipe_steps: [
        { action: 'navigate', target_ref: null, value: 'https://www.anticipy.ai', timeout_ms: 15000, postcondition: null },
      ],
    };
    const result = await executor.run(taskRow);
    record(
      'executor.run.steps_completed',
      result.steps_completed === 1 && result.steps_failed === 0,
      `status=${result.status} verifier=${result.verifier_output} steps=${result.steps_completed}/${result.steps_completed + result.steps_failed} ${result.lastError ? 'err=' + result.lastError : ''}`
    );

    // Verify result row landed in Supabase
    const { data: rrows } = await supabase
      .from('anticipy_results_v2')
      .select('task_id,status,verifier_output,steps_completed')
      .eq('task_id', taskRow.task_id)
      .limit(1);
    record(
      'results_v2.row_inserted',
      Array.isArray(rrows) && rrows.length === 1 && rrows[0].verifier_output === 'CERTIFIED',
      `row=${JSON.stringify(rrows && rrows[0])}`
    );
  } else {
    record('executor.run.steps_completed', false, 'skipped (CDP not reachable)');
    record('results_v2.row_inserted', false, 'skipped');
  }

  await subscriber.stop();
  await cdp.closeAll();
  return summarize();
}

function summarize() {
  const n = cases.length;
  const hits = cases.filter((c) => c.ok).length;
  console.log();
  console.log(`== SUMMARY: ${hits}/${n} ==`);
  if (hits !== n) {
    for (const c of cases) {
      if (!c.ok) console.log(`   FAIL  ${c.name}  ${c.detail}`);
    }
  }
  process.exit(hits === n ? 0 : 1);
}

main().catch((e) => {
  console.error('SMOKE TEST CRASHED:', e);
  process.exit(2);
});
