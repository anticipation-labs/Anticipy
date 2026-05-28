// One-shot executor task runner for the E2E test. Picks the task by
// ANTICIPY_E2E_TASK_ID env var, runs it via SkillExecutor, exits.
const path = require('path');
const dotenv = require('dotenv');
dotenv.config({ path: path.join(__dirname, '..', '..', '.env.local') });
const { createClient } = require('@supabase/supabase-js');
const { CDPClient } = require('../lib/cdp_client');
const { SkillExecutor } = require('../lib/skill_executor');
require('../skills');

async function main() {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.SUPABASE_SERVICE_ROLE_KEY;
  const taskId = process.env.ANTICIPY_E2E_TASK_ID;
  if (!url || !key || !taskId) { console.error('missing env'); process.exit(2); }
  const sb = createClient(url, key);
  const cdp = new CDPClient({ port: 9222 });
  await cdp.ready();

  const { data: rows } = await sb.from('anticipy_tasks_v2')
    .select('*').eq('task_id', taskId).limit(1);
  const task = rows && rows[0];
  if (!task) { console.error('no task'); process.exit(3); }

  const executor = new SkillExecutor({ cdp, supabase: sb });
  const result = await executor.run(task);
  console.log(JSON.stringify({ ok: true, status: result.status, verifier: result.verifier_output }));
  await cdp.closeAll();
}

main().catch((e) => { console.error('CRASH:', e); process.exit(1); });
