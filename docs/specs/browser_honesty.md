# Browser agent honesty + wall handoff — file-level integration spec

**Docket:** ANTICIPY-BROWSER-HONESTY-2026-06-23
**Scope:** two defects in the live browser arm, fixed at the file/line level.

1. **False success.** The `/agent/act` arm reports `success` from the agent's own
   "I'm finished" flag — never from a judge. A finished-but-WRONG task returns
   `success: true`. We split **agent_finished** (the agent stopped) from
   **task_succeeded** (a judge verified the result), and a finished-but-failed task
   returns `needs_human`, never a false success.
2. **Wall resume loses state.** A login/captcha/Cloudflare wall already pauses, texts
   the owner, and mints a `resume_token` — but the token is never persisted, so
   `/agent/resume` throws away mid-plan state and restarts from scratch (the explicit
   TODO at `main.py:1566-1568`). We persist the paused plan under the token and restore
   it on resume.

**Hard invariant (do NOT weaken):** the agent NEVER auto-types credentials and NEVER
solves a captcha. The human clears the wall in their own tab; we stop observing while
they do (`agent/handoff.py:8-9`). Money/checkout stays the hard stop already enforced
at `webvoyager.py:2228-2241` and `browser_use_link.py:295-308`.

---

## Current behavior (cited, as-is)

### A. `/agent/act` — the browser-use action arm (the false-success path)
- **`engine/anticipy_engine/main.py:1504-1524`** — `agent_act()` calls
  `browser_use_link.browse_act(...)` and returns `"success": res.success`
  (the assignment is **`main.py:1516`**). There is **no judge call** on this arm and
  **no wall handling** — the handler returns whatever `browse_act` reports.
- **`engine/anticipy_engine/hands/browser_use_link.py:388-389`** — `success` is
  `runner_success and bool(result_text)`, where `runner_success = bool(payload.get("success"))`
  (**`browser_use_link.py:373`**).
- **`engine/anticipy_engine/hands/browser_use_runner.py:548-555`** — `runner_success`
  is `bool(is_done and out["result"])`, and `is_done = bool(history.is_done())`
  (**runner.py:552**). `history.is_done()` is **browser-use's own self-declared finish
  flag** — the agent saying "I called done", NOT a verification that the task was
  actually accomplished. **This is the bug:** "the agent stopped with some text" is
  being returned as `success: true`.

### B. `/agent/run` + `/agent/judge` — the WebVoyager arm (judge exists but is gated)
- **`main.py:1534-1549`** — `agent_run()` runs `WebVoyagerAgent.run()`, then judges
  **only** when `body.judge and not result.get("needs_human") and not
  result.get("stopped_for_safety")` (**`main.py:1547`**). So judging is opt-in and the
  raw `run()` result already carries no `success` key of its own — callers infer it.
- **`main.py:1586-1588`** — `agent_judge()` is a thin wrapper over `judge(...)`.
- **`engine/anticipy_engine/agent/webvoyager.py:2308-2322`** — `judge()` (`_judge_success`
  in spirit) asks the smart tier, at `temperature=0`, with the final screenshot, for
  `{"success":bool,"reason":str}` and returns `{"success": bool(j.get("success")),
  "reason": ...}`. This is the **only real verifier in the codebase**, and `/agent/act`
  never calls it.
- **`webvoyager.py:1504-1506`** — `_done()` returns the result dict; finish paths set
  `answer=""` with no `success` key (e.g. `exhausted=True` at **`webvoyager.py:2297`**,
  `stopped_for_safety=True` at **2232/2239**, `needs_human/paused` via `_handoff`).

### C. Wall handoff — pause + text works; resume does NOT restore state
- **`webvoyager.py:1597-1603`** — `_handoff()` builds the human message via
  `ask_message(...)`, texts the owner via `self._notify(...)`, then returns
  `_done(... needs_human=True, paused=True, wall_kind=..., ask=..., resume_token=new_id(),
  reason=...)`. The token is **minted and returned but never stored.**
- Wall detection is wired in `run()` at **`webvoyager.py:2145-2147`** (`BLOCK_MARKERS`
  → `classify_wall`) and across the commerce recipe (**1619-1622, 1696-1698, …, 2067-2069**),
  plus the stuck/subgoal-exhausted handoff at **2292-2294**. Classifier:
  `agent/handoff.py:31-38` (`captcha | login | block`).
- **`main.py:1560-1577`** — `agent_resume()` logs the resume, then constructs a **fresh**
  `WebVoyagerAgent` and calls `agent.run(body.task, body.start_url)` from the now-unblocked
  page. The comment at **`main.py:1566-1568`** is explicit: *"Restoring the exact mid-plan
  state (same subgoal/history) is the TODO; for now we continue the task from the
  now-unblocked page."* `resume_token` is accepted (`main.py:1555`) and logged
  (`main.py:1569`) but **not used to look anything up** — there is no resume-state store
  anywhere in the engine (confirmed: the only references to `resume_token` are the mint at
  `webvoyager.py:1603` and the param/log at `main.py:1555,1569`).

---

## Change 1 — split `agent_finished` from `task_succeeded` (no false success)

### 1a. Rename the honest stop flag in the browse arm (semantic, not behavioral)
**`browser_use_runner.py:548-555`** — keep `is_done` exactly as computed, but emit it
under a name that does not lie. Add `out["agent_finished"] = bool(is_done and out["result"])`
and **stop** treating it as success on this side: set `out["success"] = None` (unknown —
"not yet judged") rather than mirroring `agent_finished`. Update the docstring at
**runner.py:11** and **`browser_use_link.py:15-16, 179`** to say `success` is now
*judge-verified*, and `agent_finished` is the agent's self-report.

**`browser_use_link.py:372-405`** — in the `BrowseReadResult` build:
- read `agent_finished = bool(payload.get("agent_finished"))` (fallback to the old
  `payload.get("success")` for back-compat) and carry it onto the result object
  (add an `agent_finished: bool` field to the dataclass at **`browser_use_link.py:175-208`**
  and to its `as_dict()`/`__init__`).
- set the dataclass `success` to `None` for ACT runs (`act=True`) — an action's truth is
  decided by the judge, not the agent. For READ runs leave the existing
  `runner_success and bool(result_text)` (reads are graded downstream via `needs_cross_check`,
  unchanged).

### 1b. Judge the `/agent/act` result before returning success
**`main.py:1504-1524`** — after `browse_act(...)` returns, call the existing judge:

```
agent_finished = bool(res.agent_finished)
verdict = await judge(gateway_agent, body.task,
                      {"answer": res.result, "final_url": res.url})
task_succeeded = bool(verdict.get("success")) and agent_finished and bool(res.result)
needs_human = (not task_succeeded) and (res.error is None) and agent_finished
```

Return shape (replace the current dict at `main.py:1515-1524`):
- `"agent_finished": agent_finished` — the agent stopped on its own.
- `"task_succeeded": task_succeeded` — **judge-verified**. This is the ONLY field a
  caller may treat as "the task is really done."
- `"success": task_succeeded` — keep the key for back-compat, but it now equals
  `task_succeeded` (never the raw self-report).
- `"needs_human": needs_human` — true when the agent finished (or stalled) but the judge
  did NOT verify success, and there is no hard `error`. A finished-but-FAILED task lands
  here, **never** in a `success: true`.
- `"judgment": verdict`, plus the existing `answer/steps/final_url/actions/allowed_domains/error/agent`.

Import `judge` from `.agent.webvoyager` (it is already importable; `agent_judge` at
`main.py:1586` uses it). Reuse `gateway_agent` (same gateway `/agent/run` judges with).
A hard infra `error` (bridge down, timeout — `browser_use_link.py:279-370`) stays
`success=False, needs_human=False` (a tool failure, not a human-clearable wall).

### 1c. Give the WebVoyager arm the same vocabulary
**`webvoyager.py:1504-1506`** — in `_done()`, when neither `paused`, `stopped_for_safety`,
nor a hard error is set and the finish is `exhausted`/`no parseable action`/`unactionable`
(the `answer=""` paths at **2137, 2216, 2297**), set `needs_human=True` on the returned
dict (the task ended without an answer → a human should look), and never let a caller read
those as success.

**`main.py:1534-1549`** — make judging the DEFAULT for answered runs, not opt-in: change
the gate at **`main.py:1547`** so that when the run produced an answer (not `needs_human`,
not `stopped_for_safety`), it is **always** judged, and stamp the result with
`task_succeeded = bool(result["judgment"]["success"])` and `agent_finished = True`. Apply
the identical stamping in `agent_resume()` at **`main.py:1572-1576`**.

### Invariant after Change 1
`task_succeeded` is true **only** when `judge()` returned `success:true`. Agent-finished,
exhausted, stuck, and unactionable outcomes that the judge does not bless return
`needs_human:true` (or a hard `error`) — there is **no path** from "the agent stopped" to
`success:true` without the judge.

---

## Change 2 — persist mid-plan state on a wall; restore it on `/agent/resume`

### 2a. A serializable resume snapshot
Add a `ResumeState` dataclass (new module **`engine/anticipy_engine/agent/resume_store.py`**)
holding everything `run()` needs to continue mid-plan instead of restarting:
- `task: str`, `start_url: str` (original), `wall_url: str` (where we paused),
- `subgoals: list[dict]` and `i: int` — a direct serialization of `TaskState`
  (`webvoyager.py:1358-1378`; `TaskState.subgoals` and `TaskState.i` are already plain
  data),
- `history: list[str]`, `visited: dict`, `committed: Optional[str]`, `item_text`,
  `step: int`, `wall_kind`, `created_at`.

`TaskState` gains `to_dict()` / `from_dict()` (add at **`webvoyager.py:1358-1378`**) so the
plan round-trips without re-planning. `WebVoyagerAgent.run()` already keeps all the other
fields as locals (`history`, `visited`, `committed`, `item_text`, `step`) — capture them at
the handoff call sites.

### 2b. Store the snapshot at pause time
**`webvoyager.py:1597-1603`** — `_handoff()` currently can't see the loop locals. Change
its signature to accept an optional `snapshot: dict | None` and have `run()`'s in-loop
handoff (**`webvoyager.py:2143-2147` / `2292-2294`**) pass `state.to_dict()` plus
`history/visited/committed/item_text/step`. In `_handoff`, after minting
`token = new_id()` (replacing the inline `resume_token=new_id()` at **`webvoyager.py:1603`**),
write `resume_store.put(token, ResumeState(...))` **before** returning. Commerce-recipe
handoffs (no `TaskState` yet — **1619-1622** etc.) store a snapshot with `subgoals=[]` and
`recipe=True`; on resume they fall back to a fresh `run()` (current behavior) but keyed by a
real, looked-up token. Keep `_notify(...)` and the returned `paused/needs_human/ask/wall_kind`
exactly as-is.

`resume_store` is a small JSONL-backed store next to the glassbox
(`core.glassbox` base dir, `control_core.py:602`): `put(token, state)`, `get(token)`,
`pop(token)`, with a TTL (e.g. 24h) so abandoned walls expire. Tokens are opaque random ids
(`new_id`, `core/envelopes.py:16`) — they are NOT secrets and carry no credentials.

### 2c. Restore on resume
**`main.py:1560-1577`** — replace the TODO body:
- `state = resume_store.get(body.resume_token)`. If missing/expired → keep today's
  fallback (`agent.run(task, start_url)` from the unblocked page) and set
  `result["resumed_cold"]=True` so the caller knows state was not restored.
- If present → construct the agent and call a new
  `agent.resume(state, unblocked_url=body.start_url)` that:
  - rebuilds `TaskState.from_dict(state.subgoals, state.i)`,
  - re-seeds `history`, `visited`, `committed`, `item_text`, and the step counter,
  - re-observes the now-unblocked `start_url` and **re-enters the same `for step in
    range(self.max_steps)` loop** at `webvoyager.py:2143` mid-plan — it does **not**
    re-plan and does **not** re-touch the wall (the human already cleared it).
  - `resume_store.pop(token)` once resumed so a token is single-use.
- Keep the `core.glassbox.log("handoff", {"event":"resume", ...})` at **`main.py:1569`**.
- Stamp `task_succeeded`/`needs_human` via the same judged path as Change 1b
  (`main.py:1572-1576`), and `result["resumed"]=True`.

### Invariant after Change 2
A wall pauses → texts the owner → owner clears it in their own tab → `/agent/resume` with
the token restores the exact subgoal/history/visited/committed and continues from where it
paused. The agent never types the credential and never solves the captcha; it only re-reads
the page the human unblocked. SSRF guard `_assert_public_agent_url` (`main.py:1565`) stays in
force on the resumed URL.

---

## Test seams (mock-friendly, no live browser)
- **No-false-success:** a stub `browse_act` that returns `agent_finished=True, result="bought
  the wrong item"` with a judge stubbed to `success:false` → `/agent/act` returns
  `task_succeeded:false, needs_human:true, success:false`.
- **Judge-verified success:** same finish, judge stubbed `success:true` → `task_succeeded:true`.
- **Wall round-trip:** drive `run()` into a `BLOCK_MARKERS` page → assert `paused/needs_human`,
  a `resume_token`, a stored `ResumeState`, and one `_notify` call; then `/agent/resume`
  with that token restores `subgoals/i/history` and re-enters the loop (assert no re-`_plan`).
- **No-auto-auth:** assert the resume path issues no `type`/`form_input` against a
  password/captcha field — the agent only re-observes the unblocked URL.
