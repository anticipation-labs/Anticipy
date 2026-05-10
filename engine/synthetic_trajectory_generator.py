"""
Synthetic trajectory generator for browser-agent fine-tuning.

The fine-tune corpus needs (state, correct-action, reasoning) tuples by the
thousands. Real-wearer trajectories are the gold standard but accumulate
slowly. This script generates synthetic high-quality trajectories now, by
having a strong teacher LLM (Kimi K2.6 — the reasoning variant on Moonshot
AI) walk through canonical tasks and emit the correct sequence of actions
for each.

Output JSONL is shaped like the production agent's `BrowserAgent.run()`
trajectory POST to /api/engine/trajectory: each step is
    {action, result, signalDiff, timestamp}
where action is one of the production action verbs and the final action is
always {"action": "done", "success": true|false, "message": "<answer>"}.
This means synthetic rows are interchangeable with the real
`engine_trajectories.steps` JSON column — same ingestion, same RAG.

Why Kimi K2.6 (reasoning) as teacher:
  - Agent-tuned (long-horizon coordination is its design intent).
  - Gemini Pro endpoint we used previously is dead (404) and we have no
    Gemini quota anyway.
  - Single Moonshot org/key already wired into the rest of the stack.

Cost model: K2.6 reasoning runs about 1500-3000 internal-reasoning tokens
plus ~500-1000 visible output tokens, on ~600 input tokens. At Moonshot
pricing ($0.60 in / $0.95 out per 1M) a typical trajectory is roughly
$0.003-0.005. 100 tasks ≈ $0.50, 1000 tasks ≈ $5. Under our $10 budget for
the full corpus.

Usage:
    set -a && source ../.env.local && set +a
    python synthetic_trajectory_generator.py \\
        --tasks-file synth_tasks.txt \\
        --out engine/logs/synth_trajectories.jsonl \\
        --per-task 3
    # OR a single ad-hoc task:
    python synthetic_trajectory_generator.py \\
        --task "Look up on Wikipedia what year Python was first released" \\
        --per-task 1 --out /tmp/one.jsonl

Default tasks: pulled at runtime from `test_extension_runner.SCENARIOS` so
we never duplicate the canonical list.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx


# ─────────────────────────────────────────────────────────────────────
# Kimi K2.6 (reasoning) teacher
# ─────────────────────────────────────────────────────────────────────

KIMI_URL = "https://api.cerebras.ai/v1/chat/completions"
KIMI_MODEL = "qwen-3-235b-a22b-instruct-2507"  # Cerebras Qwen3-235B free
# Cerebras free tier: 1M tokens/day, 30 RPM. $0 ongoing. No reasoning
# overhead (Qwen3-235B-instruct, not the thinking variant).
KIMI_INPUT_USD_PER_1M = 0.0
KIMI_OUTPUT_USD_PER_1M = 0.0
KIMI_MAX_TOKENS = 3000


SYNTH_SYSTEM_PROMPT = """\
You are generating an IDEAL browser-agent trajectory for fine-tuning a
production browser-automation agent. Given a USER TASK and a starting URL,
output ONLY a JSON trajectory in the exact format the production agent
emits — no prose, no markdown, no code fences.

ACTION SHAPES — use ONLY these (no inventing new fields, no new verbs):
  {"action":"navigate","url":"https://..."}
  {"action":"click","selector":"...","text":"...","aria":"..."}
  {"action":"type","selector":"...","text":"...","submit":true|false}
  {"action":"force_type","selector":"...","text":"..."}
  {"action":"canvas_type","text":"..."}
  {"action":"canvas_pointer","x":N,"y":N}
  {"action":"pierce_query","text":"..."}
  {"action":"keypress","key":"...","selector":"..."}
  {"action":"scroll","direction":"down|up","amount":N}
  {"action":"wait","seconds":N}
  {"action":"wait_for","url":"...","selector":"...","text":"...","timeout":N}
  {"action":"dismiss_modal"}
  {"action":"open_tab","url":"..."}
  {"action":"list_tabs"}
  {"action":"switch_tab","tabId":N}
  {"action":"close_tab","tabId":N}
  {"action":"extract","selector":"...","field":"..."}
  {"action":"getPageState"}
  {"action":"done","success":true|false,"message":"..."}

TRAJECTORY RULES — what an IDEAL real run looks like:
  - Open with `getPageState` if the start URL is `about:blank` or unknown,
    so the model learns to inspect before acting. Otherwise jump straight
    to `navigate`.
  - Use direct-URL `navigate` (e.g. https://en.wikipedia.org/wiki/Foo)
    over search-then-click whenever the URL is known. Real production
    agents learn shortcuts from these synthetic traces.
  - Prefer `type` with `"submit": true` over a separate click on Submit.
  - Use `extract` (with a `field` name) when the answer is visibly on the
    page — the extracted value is what `done.message` should reference.
  - Don't pad with unnecessary `getPageState` or `wait` calls between
    deterministic steps. 3-7 actions is typical for a fact-finding task,
    7-12 for multi-source compare. Never exceed 25 actions.
  - The FINAL action MUST be `done`. Its `message` MUST contain the
    actual concrete answer the user asked for, in plain English, with
    the real value (not "I found the answer").
  - For login-wall or impossible tasks, the final action is
    {"action":"done","success":false,"message":"<why we declined>"}.
    That's a valid trajectory too — declining gracefully is a learned
    skill.
  - Selectors must be plausible, short, real-shape CSS — `#searchInput`,
    `input[name="q"]`, `h1`, `.mw-search-result-heading`. Never
    `:contains()` or other invented pseudoselectors.

OUTPUT — STRICT JSON, exactly this shape:
{
  "task_summary": "<echo the user's task>",
  "domain": "<primary hostname>",
  "start_url": "<starting url>",
  "steps": [
    {"action":"getPageState"},
    {"action":"navigate","url":"https://en.wikipedia.org/wiki/Python_(programming_language)"},
    {"action":"extract","selector":".infobox tr","field":"release_year"},
    {"action":"done","success":true,"message":"Python was released in 1991."}
  ],
  "outcome": "success",
  "outcome_message": "Python was released in 1991."
}

CRITICAL: `steps` is a flat array of ACTION OBJECTS only. Each element
of steps is ONE of the action shapes from the list above — nothing else.
No "result", no "signalDiff", no "timestamp" wrapper. Just the action.
JSON only — no code fences, no preamble."""


def estimate_cost_usd(usage: dict | None) -> float:
    """Compute $ for one Kimi call from usage block."""
    if not usage:
        return 0.0
    pin = usage.get("prompt_tokens") or 0
    pout = usage.get("completion_tokens") or 0
    return (
        (pin / 1_000_000.0) * KIMI_INPUT_USD_PER_1M
        + (pout / 1_000_000.0) * KIMI_OUTPUT_USD_PER_1M
    )


async def call_kimi_k26(
    client: httpx.AsyncClient,
    *,
    system: str,
    user: str,
    api_key: str,
) -> tuple[str, dict | None]:
    """One K2.6 reasoning call. Returns (visible_text, usage_dict).

    K2.6 is a reasoning model. The internal reasoning_content tokens are
    billed but we only see message.content. temperature=1.0 is required —
    K2.6 returns 400 otherwise."""
    body = {
        "model": KIMI_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.2,  # Cerebras Qwen3-235B works at any temp
        "max_tokens": KIMI_MAX_TOKENS,
        "response_format": {"type": "json_object"},
    }
    # K2.6 reasoning latency: 30-90s typical. Give it 180s ceiling.
    resp = await client.post(
        KIMI_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=body,
        timeout=180.0,
    )
    resp.raise_for_status()
    data = resp.json()
    choices = data.get("choices") or []
    if not choices:
        return "", data.get("usage")
    msg = choices[0].get("message") or {}
    return msg.get("content", "") or "", data.get("usage")


# ─────────────────────────────────────────────────────────────────────
# Validation
# ─────────────────────────────────────────────────────────────────────


KNOWN_ACTIONS = {
    "navigate", "click", "type", "force_type", "canvas_type",
    "canvas_pointer", "pierce_query", "keypress", "scroll", "wait",
    "wait_for", "waitForElement", "dismiss_modal", "open_tab",
    "list_tabs", "switch_tab", "close_tab", "extract", "getPageState",
    "done",
}


def validate_trajectory(traj: dict, *, expected_facts: list[str] | None = None) -> tuple[bool, str]:
    """Structural + semantic sanity check on a generated trajectory.

    Passes if:
      - `steps` is a non-empty list
      - every step has an `action` with a known `action` verb
      - the last action is `done`
      - if expected_facts is given, the done.message contains at least one
    Returns (ok, reason)."""
    if not isinstance(traj, dict):
        return False, "not an object"
    steps = traj.get("steps")
    if not isinstance(steps, list) or not steps:
        return False, "no steps"
    # New flat-shape: each step IS an action object {action:"verb", ...}.
    # Tolerant of legacy wrapper shape {"action":{action:"verb",...}, ...}.
    for i, s in enumerate(steps):
        if not isinstance(s, dict):
            return False, f"step {i}: not an object ({type(s).__name__})"
        if isinstance(s.get("action"), dict):
            verb = s["action"].get("action")
        else:
            verb = s.get("action")
        if verb not in KNOWN_ACTIONS:
            return False, f"step {i}: unknown action verb {verb!r}"
    last = steps[-1]
    last_action = last.get("action") if isinstance(last.get("action"), dict) else last
    last_verb = last_action.get("action") if isinstance(last_action, dict) else None
    if last_verb != "done":
        return False, f"last step is {last_verb!r}, not 'done'"
    msg = (last_action.get("message", "") if isinstance(last_action, dict) else "") or ""
    if not msg:
        return False, "done.message is empty"
    if expected_facts:
        msg_low = msg.lower()
        if not any(f.lower() in msg_low for f in expected_facts):
            return False, (
                f"done.message {msg[:80]!r} doesn't reference any expected "
                f"fact {expected_facts!r}"
            )
    return True, "ok"


# ─────────────────────────────────────────────────────────────────────
# Default tasks — pulled at runtime from test_extension_runner.SCENARIOS
# so the canonical list lives in exactly one place.
# ─────────────────────────────────────────────────────────────────────


def load_default_tasks() -> list[str]:
    """Import the SCENARIOS list from test_extension_runner and pull out
    just the task strings. Falls back to a hard-coded sample if the import
    fails (e.g. because the runner's heavy deps are missing in this env)."""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from test_extension_runner import SCENARIOS  # type: ignore
        tasks = [s["task"] for s in SCENARIOS if s.get("task")]
        if tasks:
            return tasks
    except Exception as e:
        print(f"warn: could not import SCENARIOS ({e}); using fallback list",
              file=sys.stderr)
    return [
        "Look up on Wikipedia the year Python the programming language was first released and tell me.",
        "Look up the capital of France on Wikipedia and tell me the name.",
    ]


# ─────────────────────────────────────────────────────────────────────
# Main generation pass
# ─────────────────────────────────────────────────────────────────────


async def generate_one(
    client: httpx.AsyncClient,
    *,
    task: str,
    start_url: str,
    api_key: str,
    variant: int,
) -> tuple[dict | None, dict | None, float]:
    """One K2.6 call → one trajectory. Returns (parsed_traj, usage, cost_usd)."""
    user_prompt = (
        f"USER TASK: {task}\n"
        f"STARTING URL: {start_url}\n"
        f"VARIANT: {variant} — if >0, take a different valid path "
        f"(different starting site, different selector strategy) but the "
        f"final answer must be the same correct one.\n\n"
        f"Output the JSON trajectory now."
    )

    try:
        text, usage = await call_kimi_k26(
            client,
            system=SYNTH_SYSTEM_PROMPT,
            user=user_prompt,
            api_key=api_key,
        )
    except httpx.HTTPStatusError as e:
        body = (e.response.text or "")[:300]
        print(f"  Kimi HTTP {e.response.status_code}: {body}", file=sys.stderr)
        return None, None, 0.0
    except Exception as e:
        print(f"  Kimi error: {e}", file=sys.stderr)
        return None, None, 0.0

    cost = estimate_cost_usd(usage)
    if not text:
        return None, usage, cost

    # Strip code fence if K2.6 wrapped the JSON despite instructions.
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.split("\n")
        # drop opening ``` and trailing ```
        stripped = "\n".join(lines[1:-1]) if len(lines) >= 3 else stripped

    try:
        traj = json.loads(stripped)
    except (ValueError, TypeError) as e:
        print(f"  JSON parse failed: {e}; first 200 chars: {stripped[:200]!r}",
              file=sys.stderr)
        return None, usage, cost

    return traj, usage, cost


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", help="One ad-hoc task (overrides --tasks-file and DEFAULTS)")
    ap.add_argument("--tasks-file", help="One task per line (overrides DEFAULTS)")
    ap.add_argument("--start-url", default="about:blank",
                    help="Starting URL the agent would see at step 0")
    ap.add_argument("--out", default="engine/logs/synth_trajectories.jsonl",
                    help="JSONL output path")
    ap.add_argument("--per-task", type=int, default=3,
                    help="Number of trajectory variants to generate per task")
    ap.add_argument("--limit-tasks", type=int, default=0,
                    help="If > 0, only process the first N tasks (for fast iteration)")
    args = ap.parse_args()

    api_key = os.environ.get("CEREBRAS_API_KEY") or os.environ.get("KIMI_API_KEY")
    if not api_key:
        print("ERROR: CEREBRAS_API_KEY not set. Source .env.local first.", file=sys.stderr)
        return 2

    tasks: list[str]
    if args.task:
        tasks = [args.task]
    elif args.tasks_file:
        tasks = [
            line.strip()
            for line in Path(args.tasks_file).read_text().splitlines()
            if line.strip()
        ]
    else:
        tasks = load_default_tasks()

    if args.limit_tasks > 0:
        tasks = tasks[: args.limit_tasks]

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    print(
        f"== generating {len(tasks)} task(s) x {args.per_task} variant(s) = "
        f"{len(tasks) * args.per_task} trajectories",
        flush=True,
    )
    print(f"== teacher: kimi-k2.6 (reasoning) at {KIMI_URL}", flush=True)
    print(f"== output: {out_path}", flush=True)

    success = 0
    fail = 0
    total_cost = 0.0
    total_in_tokens = 0
    total_out_tokens = 0
    t0 = time.time()
    async with httpx.AsyncClient() as client:
        with out_path.open("w") as f:
            for i, task in enumerate(tasks):
                print(f"\n[{i+1}/{len(tasks)}] {task[:80]}", flush=True)
                for variant in range(args.per_task):
                    traj, usage, cost = await generate_one(
                        client,
                        task=task,
                        start_url=args.start_url,
                        api_key=api_key,
                        variant=variant,
                    )
                    total_cost += cost
                    if usage:
                        total_in_tokens += usage.get("prompt_tokens") or 0
                        total_out_tokens += usage.get("completion_tokens") or 0
                    if traj is None:
                        print(f"   variant {variant}: FAILED (no parseable JSON)",
                              flush=True)
                        fail += 1
                        continue

                    # Stamp metadata before validation so failed rows are
                    # still inspectable.
                    traj["task"] = task
                    traj["variant"] = variant
                    traj["generated_by"] = KIMI_MODEL
                    traj["generated_at"] = time.strftime(
                        "%Y-%m-%dT%H:%M:%SZ", time.gmtime()
                    )
                    if usage:
                        traj["_kimi_usage"] = usage
                        traj["_kimi_cost_usd"] = round(cost, 6)

                    ok, why = validate_trajectory(traj)
                    traj["validated"] = ok
                    if not ok:
                        traj["validation_error"] = why
                        print(f"   variant {variant}: INVALID — {why}", flush=True)
                        fail += 1
                        # Still write it so we can inspect malformed runs.
                        f.write(json.dumps(traj) + "\n")
                        f.flush()
                        continue

                    f.write(json.dumps(traj) + "\n")
                    f.flush()
                    n_steps = len(traj.get("steps") or [])
                    last = (traj.get("steps") or [])[-1].get("action") or {}
                    final_msg = last.get("message", "")
                    print(
                        f"   variant {variant}: {n_steps} steps, "
                        f"answer={final_msg[:80]!r}, "
                        f"cost=${cost:.4f}",
                        flush=True,
                    )
                    success += 1

    elapsed = time.time() - t0
    print(
        f"\n== done. {success} valid, {fail} failed in {elapsed:.1f}s",
        flush=True,
    )
    print(
        f"== tokens: {total_in_tokens} in / {total_out_tokens} out  "
        f"== cost: ${total_cost:.4f}",
        flush=True,
    )
    print(
        f"== output: {out_path} "
        f"({out_path.stat().st_size if out_path.exists() else 0} bytes)",
        flush=True,
    )
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
