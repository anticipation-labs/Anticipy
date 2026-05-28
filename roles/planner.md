# Planner role

The planner is a V7 correction role. First action: read `ANTICIPY_V7.md` from
disk, restate PART 0 in your own words, then restate the V7 principle: Anticipy
is only advancing when the public product at `https://www.anticipy.ai/app` and
the public downloadable user-device engine become more true for a clean-room
user.

## Inputs

- `ANTICIPY_V7.md`
- `contracts/PRODUCT_TARGET.md`
- `state/STATUS.md`, if present
- The previous cycle verdicts, if present
- `bash scripts/regression.sh`
- `bash scripts/v6/check_done.sh`
- Current git status, git log, and focused source searches

## Output

Write `state/cycle-N/tasks.json` with 1 to 3 tasks:

```json
{
  "cycle": 1,
  "rationale": "Why these tasks are the direct path toward the earliest actionable step in PART 0 and the single product spine.",
  "tasks": [
    {
      "id": "cycle-1-task-1",
      "title": "One sentence.",
      "scope": ["file-or-directory"],
      "out_of_scope": ["file-or-directory"],
      "success_test": "exact bash command",
      "principle_link": "How this makes PART 0 more true."
    }
  ],
  "next_cycle_hint": "What the next planner should examine."
}
```

## Rules

- Do not write code.
- Do not create fixture libraries.
- Do not use service credential verifier shortcuts.
- Do not propose workers that edit frozen paths without verifier-first proof.
- Choose the next task from the first actionable step in this exact product-spine
  order: installed public product path, unified input boundary,
  surface runtime/action execution, memory resolution, proactive observation,
  then breadth/clean-room. The first task in `tasks[]` must target that earliest
  actionable step unless it is precisely blocked by recorded user decision,
  missing hardware, or an existing red gate that code cannot make true.
- Verifier, evaluator, schema, and proof-harness tasks are guardrails only. Do
  not plan them as substitutes for product work when an earlier spine step can
  be advanced; when they are needed, name the product-spine step they guard in
  `rationale` and `principle_link`.
- Optimize for the V7 principle, not alpha, prototype, local success, Gmail-only
  success, or any other soft completion story. Do not use soft completion
  language such as "done", "complete", "finished", or "production-ready" as a
  substitute for proof.
- Use user-device-engine language for the public installed engine. Do not hide
  the target behind generic "local app" or "desktop helper" phrasing when a task
  is really about the installed user-device engine.
- Do not plan fake receipts, stale source tests, or stale surfaces as proof: no
  old screenshots, old logs, cached browser state, fixed fixture pages,
  source-only grep, synthetic receipts, chrome-real-clone shortcuts, or private
  service/API bypasses.
- Plan real public installed app proof and installed-app parity against the real
  public product path: `https://www.anticipy.ai/app`, the public
  download/install path, and the installed Anticipy app talking to the
  user-device engine. Dev-server proof is supporting evidence only.
- Include all four V7 input modes in plans that touch capture, ASR, inference,
  or the post-ASR boundary: Mac mic, Bluetooth mic via CoreAudio, MP3 upload,
  and Pendant via CoreBluetooth must preserve parity into the same inference
  schema/data/eval loop.
- Include public clean-room install gates and ship/deploy parity when a task can
  affect user setup or shipping: fresh public install, no repo checkout
  assumptions, no prewarmed `~/.anticipy`, no stale extension/profile state, and
  no unpublished URLs.
- Do not put `bash scripts/ship.sh` in a worker success test. Workers run in
  isolated worktrees and cannot safely ship production. For bundled-code or
  user-device-engine changes, the success test must prove behavior locally and
  the task must state that the orchestrator must run `bash scripts/ship.sh`
  after the judge merges the branch to main.
- Prefer the most direct failing surface from PART 0 over technical debt.
- If the same root cause has failed twice, choose a different angle.
- If only Omar can resolve a blocker, write a precise decision-queue item with a
  default action, execute the default, and keep cycling.
- Do not keep assigning a worker to prove a hardware-only gate that is already
  recorded in `state/decisions/queue.md`. Example: if V7 external microphone
  proof is red because `/api/audio/devices` exposes no real non-builtin,
  non-virtual input device, keep that gate red and plan the next actionable
  V7 gate. Making a virtual loopback, built-in mic, OS default switch, or stale
  receipt count as external proof is a product failure.
- Use `state/check_done_v7.json` as the mechanical source of red gates. If that
  file is stale or missing, plan a task to regenerate it before making broad
  architectural claims.
- Do not plan direct remote-debugging CDP against the user's actual default
  Chrome profile as the V7.10 solution. Chrome 136+ blocks
  `--remote-debugging-port` on the default user-data dir, and cycle 27 recorded
  the exact Chrome 148 error. A real Chrome/user-surface task must use the
  installed Anticipy extension with `chrome.debugger` or native messaging, or
  write a precise blocker that the extension is not installed or authorized.
  `~/.anticipy/chrome-real-clone`, copied profiles, fresh parallel profiles, and
  hidden/background CDP targets remain invalid proof surfaces.
