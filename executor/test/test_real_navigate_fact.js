// REAL production smoke for navigate_fact_lookup — drive Chrome on
// :9222 to en.wikipedia.org/wiki/Python_(programming_language) and
// extract the first paragraph. Assert the verifier CERTIFIES.
//
// This is a real Phase 6 production gate — no fixture worlds, no
// mocked DOM. The cascade output is the actual Wikipedia HTML.

const path = require('path');
const dotenv = require('dotenv');
const { createClient } = require('@supabase/supabase-js');
const crypto = require('crypto');

dotenv.config({ path: path.join(__dirname, '..', '..', '.env.local') });

const { CDPClient } = require('../lib/cdp_client');
const { SkillExecutor } = require('../lib/skill_executor');
const { registry, VERIFIED } = require('../lib/verifier');
require('../skills');  // auto-load (registers navigate_fact_lookup)

const cases = [];
function record(name, ok, detail = '') {
  cases.push({ name, ok, detail });
  console.log(`[${ok ? 'PASS' : 'FAIL'}] ${name}${detail ? '  — ' + detail : ''}`);
}

async function main() {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!url || !key) {
    record('env.supabase', false, 'missing keys');
    return summarize();
  }
  const supabase = createClient(url, key);
  const cdp = new CDPClient({ port: 9222 });

  let ok;
  try {
    const v = await cdp.ready();
    record('cdp.ready', true, `Browser=${v.Browser}`);
    ok = true;
  } catch (e) {
    record('cdp.ready', false, e.message);
    return summarize();
  }

  // Synthesize an Intent + Task targeting Wikipedia → extract first
  // paragraph. Insert into Supabase to satisfy the FK on tasks_v2.
  const userId = `realsmoke-${Date.now()}`;
  const intentId = crypto.randomUUID();
  const taskId = crypto.randomUUID();
  await supabase.from('anticipy_intents_v2').insert({
    intent_id: intentId,
    user_id: userId,
    utterance_window: { transcript_segments: [{ speaker: 'wearer', text: 'when was python created' }], start_ts: '', end_ts: '' },
    action_category: 'fact_lookup',
    proposed_skill_hint: 'navigate_fact_lookup',
    slots: { filled: {}, needs_memory: [], needs_inference: [], ambiguous: [] },
    detection_confidence: 0.95,
    hedge_filter_decision: 'COMMIT',
    hedge_filter_reason: 'real_smoke',
    proactivity_score: 0.95,
    source: 'typed',
  });
  const task = {
    task_id: taskId,
    intent_id: intentId,
    user_id: userId,
    skill_id: 'navigate_fact_lookup',
    parameters: {},
    recipe_steps: [
      { action: 'navigate', target_ref: null, value: 'https://en.wikipedia.org/wiki/Python_(programming_language)', timeout_ms: 20000 },
      { action: 'wait', target_ref: '.mw-parser-output p', timeout_ms: 8000 },
      // Wikipedia's first `<p>` is often empty (used for spacing); grab
      // the body wrapper which always has the lead text. Verifier's
      // ">= 5 chars" guard handles short results.
      { action: 'extract', target_ref: '.mw-parser-output', value: 'first_paragraph' },
    ],
    rehearsal_required: false,
    irreversible: false,
    aevoy_confirmation_required: false,
  };
  await supabase.from('anticipy_tasks_v2').insert(task);

  const executor = new SkillExecutor({ cdp, supabase });
  const result = await executor.run(task);
  record('executor.steps_completed_3', result.steps_completed === 3 && result.steps_failed === 0,
    `steps=${result.steps_completed}/${result.steps_completed + result.steps_failed} err=${result.lastError || 'none'}`);

  // Verifier should certify with the extracted text
  const world = { result };
  const verdict = registry.verify('navigate_fact_lookup', world);
  record('verifier.certified', verdict.verdict === VERIFIED,
    `verdict=${verdict.verdict} reason=${verdict.reason} extracted=${(verdict.extracted || '').slice(0, 80)}`);

  // Result row should land in anticipy_results_v2
  const { data: rows } = await supabase
    .from('anticipy_results_v2')
    .select('task_id,verifier_output,steps_completed')
    .eq('task_id', taskId)
    .limit(1);
  record('results_v2.row_inserted', Array.isArray(rows) && rows.length === 1,
    rows && rows[0] ? `verdict_in_db=${rows[0].verifier_output}` : 'row missing');

  await cdp.closeAll();
  return summarize();
}

function summarize() {
  const n = cases.length;
  const hits = cases.filter((c) => c.ok).length;
  console.log();
  console.log(`== SUMMARY: ${hits}/${n} ==`);
  for (const c of cases) if (!c.ok) console.log(`   FAIL  ${c.name}  ${c.detail}`);
  process.exit(hits === n ? 0 : 1);
}

main().catch((e) => { console.error('CRASH:', e); process.exit(2); });
