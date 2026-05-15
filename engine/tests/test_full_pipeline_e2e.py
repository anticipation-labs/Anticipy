"""Full end-to-end pipeline test — utterance → Intent → Task → Result.

The definitive test that the typed contracts flow through all three
sides of the architecture:

  1. Pod A (Python)          — runs the cascade on a text utterance,
                                publishes the typed Intent to Supabase
                                anticipy_intents_v2.
  2. middle layer (Python)   — pulls the Intent, runs slot_resolver +
                                skill_router + policy + dispatcher,
                                writes a Task to anticipy_tasks_v2.
  3. executor (Node, spawned) — subscribes to task.dispatched.{user},
                                runs the recipe via CDP against the
                                attached Chrome :9222, writes a Result
                                to anticipy_results_v2.
  4. assertion (Python)      — polls anticipy_results_v2 for the Result
                                row matching the Task; asserts
                                verifier_output=CERTIFIED.

Per Rule 13: this is the canonical end-to-end gate.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(REPO_ROOT / ".env.local")

from supabase import create_client  # noqa: E402

from app.middle import (  # noqa: E402
    Dispatcher,
    PolicyEngine,
    SkillRouter,
    SlotResolver,
)
from app.proactive.demand_detection import DemandDetector  # noqa: E402
from app.proactive.hedge_filter import HedgeFilter  # noqa: E402
from app.proactive.intent_extraction import IntentExtractor  # noqa: E402
from app.proactive.pipeline import PodAPipeline  # noqa: E402

cases = []
def record(name, ok, detail=""):
    cases.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}{('  — ' + detail) if detail else ''}")


async def main() -> int:
    url = os.environ["NEXT_PUBLIC_SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    sb = create_client(url, key)

    user_id = f"e2e-{uuid.uuid4().hex[:10]}"
    utterance = "Look up when Python was first released."

    # ── 1. Pod A: cascade publishes Intent ────────────────────────
    pipeline = PodAPipeline(
        demand_detector=DemandDetector(),
        hedge_filter=HedgeFilter(backend="cascade", fewshot_count=8),
        intent_extractor=IntentExtractor(),
        supabase=sb,
    )
    result = await pipeline.from_text(utterance=utterance, user_id=user_id, source="typed")
    record("pod_a.cascade_committed",
        result.hedge is not None and result.hedge.decision == "COMMIT",
        f"decision={result.hedge.decision if result.hedge else None}")
    record("pod_a.intent_published",
        result.published,
        f"intent_id={result.intent.intent_id if result.intent else None}")

    if not result.published or not result.intent:
        return summarize()

    # Verify the row landed
    resp = sb.table("anticipy_intents_v2").select("intent_id").eq("intent_id", result.intent.intent_id).limit(1).execute()
    record("pod_a.intent_row_in_db",
        len(resp.data or []) == 1,
        f"row={resp.data}")

    # ── 2. Middle layer: dispatcher writes Task ────────────────────
    slots = SlotResolver().resolve(result.intent)
    route = SkillRouter().route(result.intent)
    decision = PolicyEngine().decide(result.intent, slots, route)
    dispatch_result = Dispatcher().dispatch(result.intent, slots, route, decision)
    record("middle.task_dispatched",
        dispatch_result.dispatched and dispatch_result.task_id is not None,
        f"task_id={dispatch_result.task_id} reason={dispatch_result.reason}")

    if not dispatch_result.dispatched:
        return summarize()

    # ── 3. Spawn the executor as a Node subprocess ─────────────────
    # The executor's main.js boots Electron; for the headless test we
    # spawn a one-shot script that subscribes, picks up the Task, runs
    # it, writes Result, and exits.
    executor_script = REPO_ROOT / "executor" / "test" / "run_one_task.js"
    # If the one-shot doesn't exist yet, create it inline
    if not executor_script.exists():
        executor_script.write_text(_one_shot_runner_source())

    env = os.environ.copy()
    env["ANTICIPY_USER_ID"] = user_id
    env["ANTICIPY_E2E_TASK_ID"] = dispatch_result.task_id
    proc = subprocess.Popen(
        ["node", str(executor_script)],
        cwd=str(REPO_ROOT / "executor"),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    # Wait for the executor to write the Result, with a 60s deadline
    deadline = time.monotonic() + 60
    final_row = None
    while time.monotonic() < deadline:
        rs = (
            sb.table("anticipy_results_v2")
            .select("task_id,verifier_output,steps_completed,status")
            .eq("task_id", dispatch_result.task_id)
            .limit(1)
            .execute()
        )
        if rs.data:
            final_row = rs.data[0]
            break
        await asyncio.sleep(2)

    # Reap the subprocess
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=2)

    record("executor.result_row_written",
        final_row is not None,
        f"row={final_row}")
    record("executor.verifier_certified",
        final_row is not None and final_row.get("verifier_output") == "CERTIFIED",
        f"verifier_output={final_row.get('verifier_output') if final_row else None}")

    return summarize()


def summarize() -> int:
    n = len(cases)
    hits = sum(1 for _, ok, _ in cases if ok)
    print()
    print(f"== SUMMARY: {hits}/{n} ==")
    for name, ok, detail in cases:
        if not ok:
            print(f"   FAIL  {name}  {detail}")
    return 0 if hits == n else 1


def _one_shot_runner_source() -> str:
    return """// One-shot executor task runner for the E2E test. Picks the task by
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
"""


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
