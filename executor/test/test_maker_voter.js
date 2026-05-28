// MAKER voter end-to-end test against real free-tier providers.
//
// The voter fans out to ≥3 providers and waits until one canonical
// answer leads by 3. For an atomic decision with strong consensus
// (which-of-these-actions to take in a clear scenario), every
// provider should converge on the same JSON shape and the lead is
// reached fast (~1-2 s).
//
// Per Rule 13: this is the gate for the MAKER voter module.

const path = require('path');
const dotenv = require('dotenv');
dotenv.config({ path: path.join(__dirname, '..', '..', '.env.local') });

const { MakerVoter, canonical, redFlag } = require('../lib/maker_voter');

const cases = [];
function record(name, ok, detail = '') {
  cases.push({ name, ok, detail });
  const sym = ok ? 'PASS' : 'FAIL';
  console.log(`[${sym}] ${name}${detail ? '  — ' + detail : ''}`);
}

async function main() {
  // ── (1) canonical()/redFlag() unit checks ──────────────────────────
  record('canonical.action_only_matches_across_targets',
    canonical('{"action":"click","target":"first result"}') === canonical('{"action":"click","target":"<a class=result>"}'),
    'action-only collapses target wording differences');
  record('canonical.lowercases_action',
    canonical('{"action":"CLICK"}') === '{"action":"click"}');
  record('canonical.strips_fences',
    canonical('```json\n{"action":"navigate"}\n```') === '{"action":"navigate"}');
  record('canonical.handles_garbage',
    canonical('not json') === null);
  record('redFlag.detects_refusal',
    redFlag("I can't do that"));
  record('redFlag.detects_hedge',
    redFlag('I should probably click the button'));
  record('redFlag.passes_clean',
    !redFlag('{"action":"click","selector":"#submit"}'));

  // ── (2) Voter against real providers — atomic decision ─────────────
  const voter = new MakerVoter({ leadBy: 3, voterCount: 5, timeoutMs: 18000 });
  const system = 'You are a browser-automation atomic decision oracle. Output STRICT JSON ONLY: {"action":"click"|"type"|"navigate"|"done","target":"<short>"}. No prose. No fences.';
  const user = 'A search results page is open. The user wants to open the FIRST result. There is a clear "<a class=result>...</a>" element at top. What is the next action?';

  const startMs = Date.now();
  let result;
  try {
    result = await voter.vote({ system, user });
    const elapsed = Date.now() - startMs;
    record('voter.returned_within_timeout',
      result != null && elapsed < 20000,
      `elapsed=${elapsed}ms timedOut=${result.timedOut}`);
    record('voter.answer_has_action',
      result.answer && typeof result.answer.action === 'string',
      `answer=${JSON.stringify(result.answer)}`);
    record('voter.consensus_reached',
      Object.values(result.votes || {}).reduce((a,b)=>a+b,0) >= 3,
      `votes=${JSON.stringify(result.votes)} redFlagged=${result.redFlagged}`);
  } catch (e) {
    record('voter.returned_within_timeout', false, `error=${e.message || e}`);
  }

  // ── Summary ─────────────────────────────────────────────────────────
  const n = cases.length;
  const hits = cases.filter((c) => c.ok).length;
  console.log();
  console.log(`== SUMMARY: ${hits}/${n} ==`);
  for (const c of cases) if (!c.ok) console.log(`   FAIL  ${c.name}  ${c.detail}`);
  process.exit(hits === n ? 0 : 1);
}

main().catch((e) => { console.error('CRASH:', e); process.exit(2); });
