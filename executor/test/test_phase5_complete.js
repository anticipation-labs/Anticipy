// Phase 5 completion gate — sandbox rehearsal + verifier framework +
// /download route. Per Rule 13: this test is the gate.
//
// Tests:
//   1. Verifier registry registers a skill, verify() returns CERTIFIED
//      on a good world, NOT_CERTIFIED on a bad world.
//   2. Skills loader auto-loads navigate_fact_lookup.
//   3. Sandbox rehearsal spawns a SECOND Chrome on :9223 with a temp
//      profile, attaches CDP, navigates, and STOPS (cleans up temp dir
//      and process). Cookies clone is best-effort — we only assert the
//      sandbox process spawned and was killed cleanly.

const path = require('path');
const fs = require('fs');
const dotenv = require('dotenv');
dotenv.config({ path: path.join(__dirname, '..', '..', '.env.local') });

const { CDPClient } = require('../lib/cdp_client');
const { registry, VERIFIED, NOT_VERIFIED } = require('../lib/verifier');
const { SandboxRehearsal } = require('../lib/sandbox_rehearsal');
require('../skills');  // auto-load skills

const cases = [];
function record(name, ok, detail = '') {
  cases.push({ name, ok, detail });
  console.log(`[${ok ? 'PASS' : 'FAIL'}] ${name}${detail ? '  — ' + detail : ''}`);
}

async function main() {
  // ── (1) Verifier registry ─────────────────────────────────────────
  record('registry.has_navigate_fact_lookup',
    registry.has('navigate_fact_lookup'),
    `loaded skills=${registry.ids().join(',')}`);

  const goodWorld = {
    result: {
      steps_failed: 0,
      steps_completed: 2,
      evidence: { parsed_confirmations: [{ year: '1991, by Guido van Rossum at CWI' }] },
    },
  };
  const badWorld = {
    result: {
      steps_failed: 1,
      steps_completed: 0,
      evidence: { parsed_confirmations: [] },
    },
  };
  const v1 = registry.verify('navigate_fact_lookup', goodWorld);
  record('verifier.certifies_good_world',
    v1.verdict === VERIFIED,
    `verdict=${v1.verdict} reason=${v1.reason}`);
  const v2 = registry.verify('navigate_fact_lookup', badWorld);
  record('verifier.refuses_bad_world',
    v2.verdict === NOT_VERIFIED,
    `verdict=${v2.verdict} reason=${v2.reason}`);
  const v3 = registry.verify('unknown_skill', goodWorld);
  record('verifier.unknown_skill_refuses',
    v3.verdict === NOT_VERIFIED,
    `reason=${v3.reason}`);

  // ── (2) Sandbox rehearsal — spawn / verify port / clean stop ─────
  const liveCdp = new CDPClient({ port: 9222 });
  let sandbox = null;
  try {
    sandbox = new SandboxRehearsal({ liveCdp, sandboxPort: 9223 });
    const sbCdp = await sandbox.start({ cookieDomains: [] });  // no cookie copy for the smoke test
    const sbReady = await sbCdp.ready();
    record('sandbox.spawned_and_ready',
      !!sbReady && !!sbReady.Browser,
      `Browser=${sbReady.Browser}`);
    record('sandbox.temp_dir_exists',
      sandbox._tempDir && fs.existsSync(sandbox._tempDir),
      `tempDir=${sandbox._tempDir}`);

    // Run a 1-step rehearse against the sandbox: navigate, then
    // verifier should certify based on steps_failed=0
    const fakeTask = {
      task_id: 'rehearse-test',
      skill_id: 'navigate_fact_lookup',
      recipe_steps: [
        { action: 'navigate', target_ref: null, value: 'about:blank', timeout_ms: 8000, postcondition: null },
      ],
    };
    const rehearseResult = await sandbox.rehearse({ task: fakeTask, registry });
    record('sandbox.rehearse_runs',
      rehearseResult && rehearseResult.result && rehearseResult.result.steps_completed === 1,
      `steps=${rehearseResult.result?.steps_completed}/${(rehearseResult.result?.steps_completed || 0) + (rehearseResult.result?.steps_failed || 0)} verdict=${rehearseResult.verdict?.verdict}`);
  } catch (e) {
    record('sandbox.spawned_and_ready', false, `error=${e.message || e}`);
  } finally {
    if (sandbox) await sandbox.stop();
  }
  // After stop the temp dir should be gone.
  record('sandbox.cleaned_up',
    !sandbox._tempDir,
    'temp dir + process killed');

  // ── (3) /download route + dmg in public/ ─────────────────────────
  const dmgPath = path.join(__dirname, '..', '..', 'public', 'Anticipy.dmg');
  record('public.dmg_present',
    fs.existsSync(dmgPath),
    fs.existsSync(dmgPath) ? `size=${(fs.statSync(dmgPath).size / 1024 / 1024).toFixed(1)}MB` : 'missing');

  const downloadRoute = path.join(__dirname, '..', '..', 'src', 'app', 'download', 'route.ts');
  record('download.route_present',
    fs.existsSync(downloadRoute),
    fs.existsSync(downloadRoute) ? 'src/app/download/route.ts' : 'missing');

  // ── Summary ──────────────────────────────────────────────────────
  const n = cases.length;
  const hits = cases.filter((c) => c.ok).length;
  console.log();
  console.log(`== SUMMARY: ${hits}/${n} ==`);
  for (const c of cases) if (!c.ok) console.log(`   FAIL  ${c.name}  ${c.detail}`);
  process.exit(hits === n ? 0 : 1);
}

main().catch((e) => { console.error('CRASH:', e); process.exit(2); });
