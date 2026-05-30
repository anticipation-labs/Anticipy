# Ralph Loop — Anticipy's persistence + retry + recovery spec

**Why this exists:** Anticipy must own every task across hours, days, weeks. Try, fail, learn, retry, escalate. Never silently give up. The "Ralph loop" is owner's name for this.

**Status:** spec only. Implementation lives in `engine/app/ralph/` (to be created in Phase 4).

**Research basis:** `RESEARCH/agent-loops.md` synthesizing browser-use, LangGraph, CrewAI, Open Interpreter, AutoGen, and Anthropic's "Building effective agents." Ralph is Anthropic's **evaluator-optimizer** pattern with browser-use's failure classifier.

---

## The loop, one diagram (top-down)

```
goal arrives
  -> plan (cheap LLM extracts steps)
    -> for each step:
        execute (extension drives Chrome tab in Anticipy group)
        verify (deterministic check first, vision judge if needed)
        if pass: continue
        if fail: classify failure -> recover -> bump retry counter
                 if retry < N: replan with failure as context
                 if retry >= N: escalate to user via SMS or schedule for later
                 if cost cap hit: pause + notify user
  -> all steps pass: judge with end-of-goal verifier
  -> persist final state, archive evidence, send receipt
```

## Failure classes (from `RESEARCH/agent-loops.md`)

Each failure gets a class label. The recovery strategy is dispatched per class.

| Class | Detection | Recovery strategy |
|---|---|---|
| `login_wall` | URL matches `/login`, `/signin`; selector for auth form found | SMS user with the tab URL: "Sign in to X to continue, here's the tab" |
| `captcha` | Element matches reCAPTCHA / hCaptcha / Cloudflare turnstile selectors | NopeCHA solver attempt (free tier). If fail: SMS user with screenshot |
| `network` | HTTP 5xx, 502, 504, timeout, DNS error | Exponential backoff: 1m, 5m, 30m, 3h, 24h. Re-attempt up to 5 times. |
| `rate_limit` | HTTP 429, "Too Many Requests", header `Retry-After` | Honor Retry-After if present, else 5m / 30m / 6h backoff |
| `element_missing` | Selector not found within timeout, DOM looks unfamiliar | Re-snapshot DOM, vision fallback (Gemini 2.5 Flash) ONLY here, re-plan with new map |
| `payment_required` | URL contains `/checkout`, `/billing`, `payment-required` text | Always SMS user, never autopay. Wait indefinitely. |
| `account_locked` | "account locked", "suspended", "2fa required" text | SMS user, do NOT retry. Wait for user reply. |
| `ambiguous_dom` | Multiple elements match selector + no disambiguator | Vision LLM picks best candidate, escalate to user if still unsure |
| `cost_cap` | Per-goal cost exceeded $0.05 budget | Pause goal, SMS user: "Spent $X on Y, OK to continue or stop?" |
| `model_error` | LLM returned malformed JSON, OOM, refused | Swap to fallback model (DeepSeek -> Gemini Flash), max 2 swaps per step |
| `unknown` | None of the above match | Snapshot everything (URL, DOM, screenshot, last action), SMS user with link |

## State persistence schema

NOT `memory.jsonl` (per bug-hunter B477 unbounded growth). SQLite, two tables:

```sql
CREATE TABLE goals (
  goal_id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  goal_text TEXT NOT NULL,
  origin TEXT,                    -- 'asr' | 'inject' | 'proactive' | 'mp3'
  status TEXT NOT NULL,           -- 'pending' | 'running' | 'wait_user' | 'wait_retry' | 'done' | 'failed' | 'cancelled'
  cost_usd REAL NOT NULL DEFAULT 0,
  cost_cap_usd REAL NOT NULL DEFAULT 0.05,
  consecutive_failures INT NOT NULL DEFAULT 0,
  next_attempt_at INTEGER,        -- unix ts; NULL if not scheduled
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL,
  surface TEXT,                   -- 'web' | 'sms_out' | 'voice_out' | 'search' | 'memory'
  channel_payload TEXT,           -- JSON: SMS body, email html, etc.
  final_artifact_path TEXT        -- screenshot / receipt id when done
);

CREATE TABLE goal_steps (
  step_id TEXT PRIMARY KEY,
  goal_id TEXT NOT NULL REFERENCES goals(goal_id),
  step_index INT NOT NULL,
  action TEXT NOT NULL,           -- 'navigate' | 'click' | 'type' | 'extract' | 'screenshot' | 'send_sms' | etc.
  action_payload TEXT,            -- JSON
  pre_state_hash TEXT,            -- normalized DOM + URL hash before action
  post_state_hash TEXT,           -- after action
  result TEXT,                    -- 'pass' | 'fail'
  failure_class TEXT,             -- one of the classes above
  failure_detail TEXT,
  retry_count INT NOT NULL DEFAULT 0,
  cost_usd REAL NOT NULL DEFAULT 0,
  duration_ms INT,
  started_at INTEGER NOT NULL,
  ended_at INTEGER
);

CREATE INDEX idx_goals_next_attempt ON goals(next_attempt_at) WHERE next_attempt_at IS NOT NULL;
CREATE INDEX idx_goals_status ON goals(status);
CREATE INDEX idx_goal_steps_goal ON goal_steps(goal_id, step_index);
```

DB lives at `~/.anticipy/v7/ralph.db` with WAL mode + checkpoint every 60s.

## Wake-up scheduling

Polling loop runs every 30s in the engine sidecar:
```
SELECT goal_id FROM goals
 WHERE status = 'wait_retry'
   AND next_attempt_at IS NOT NULL
   AND next_attempt_at <= unix_timestamp()
 ORDER BY next_attempt_at ASC
 LIMIT 10
```

Picks them up, sets status to 'running', resumes from last successful step.

NOT `asyncio.sleep` in-memory (loses state on restart). Always DB-backed.

## Verification layers

**Layer 1: Cheap deterministic (per step)**
- URL changed to expected pattern?
- Expected selector now visible?
- DOM hash differs from pre-action?
- Network request to expected endpoint completed with 200?

If layer 1 passes, no LLM call. ~$0 cost.

**Layer 2: Vision judge (end of goal only)**
- Take final screenshot
- Ask Gemini 2.5 Flash: "Did this complete the goal '$GOAL'? Be initially doubtful. Answer with verdict | impossible_task | reached_captcha | needs_more_steps."
- ~$0.0003 per call

Cost-vs-correctness tradeoff: layer 1 catches 90% of failures. Layer 2 is the safety net.

## Cost cap enforcement

Per-goal: $0.05 hard cap (25x the $0.002/task average).
Per-user-day: $0.30 hard cap.
Per-user-month: $6.00 hard cap (gives $72/year LLM budget, well under the $200 ceiling).

When cap is hit:
1. Pause the goal (status = 'wait_user', no retry scheduled)
2. SMS user: "Spent $X on $GOAL today. Reply CONTINUE or STOP."
3. On CONTINUE: bump cap to next tier, resume.
4. On STOP: cancel goal, archive.
5. On no reply 24h: default to STOP.

## User-in-the-loop pattern

When a step requires the user:
1. Save goal state (status = 'wait_user')
2. Send notification via appropriate channel (SMS for "sign in here", email for non-urgent, voice call for time-critical)
3. Include a one-tap action link (Anticipy app deep link `anticipy://goal/$GOAL_ID/continue`)
4. User taps -> Anticipy app opens, marks the gate satisfied (e.g., "I signed in"), resumes goal

If no reply in 3 hours (production) or 30 seconds (`ANTICIPY_TEST_FAST_TIMEOUTS=1`):
- Default action per goal type (draft instead of send, save instead of submit, etc.)
- Notify user that default was taken

## Retry counter logic (from browser-use)

- Per step: max 3 retries with same plan + fallback model on retry 3
- Per goal: max 5 consecutive step failures triggers replan
- After replan: 2 more attempt cycles before escalating to user
- Loop detection: hash of (action + pre_state_hash) — if we've seen this exact combo twice in a row, treat as failure_class = 'loop_detected' and replan immediately

## Anti-patterns we explicitly forbid (from research)

| Don't | Why |
|---|---|
| Single global retry counter | Conflates failure modes; can't differentiate "network" from "DOM changed" |
| `asyncio.sleep(3600)` in-memory waits | Loses state on engine restart |
| Hard-kill on first loop detection | One bad heuristic kills legitimate work |
| Sync human-in-loop (block main thread) | Stalls all other goals; use callback resume |
| Agent self-grading own output for safety | Drift toward "looks good to me" — use separate judge |

## What "DONE" looks like for a goal

A goal row in `goals` table reaches `status = 'done'` with:
- `final_artifact_path` not null (screenshot, receipt URL, draft message ID, etc.)
- A receipt sent on the appropriate channel (SMS or email per urgency)
- An entry in `timeline.jsonl` (unified view feeds the app)
- The original transcript chunk tagged with the goal_id (audit trail)

If any of these are missing, the goal is NOT done. It stays in 'running' or whatever last state.

## Implementation phases

| Phase | What lands |
|---|---|
| P4-1 | SQLite tables + state persistence |
| P4-2 | Failure classifier + class-specific recovery |
| P4-3 | Wake-up poller loop + retry scheduler |
| P4-4 | Two-layer verification (deterministic + vision judge) |
| P4-5 | Cost cap enforcement (per-goal + per-day + per-month) |
| P4-6 | User-in-the-loop + one-tap resume links |
| P4-7 | Loop detection (action+state hash) |
| P4-8 | End-to-end test: goal injected, 2 deliberate failures, recovery to success, receipt sent |

Gate for Phase 4 done: P4-8 passes a real integration test, with the test injecting "draft email to {test_recipient}" into the engine, failing twice (network error, ambiguous DOM), recovering to success, draft visible in Gmail, SMS receipt landed on test phone within 30s.
