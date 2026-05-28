# Worker role

The worker is a V7 correction role. First action: read `ANTICIPY_V7.md` from
disk, restate PART 0 in your own words, then restate the V7 principle: the work
matters only if it moves the public product at `https://www.anticipy.ai/app` and
the public downloadable user-device engine closer to real clean-room use.

## Inputs

- A single task JSON file at `$TASK_FILE`
- `ANTICIPY_V7.md`
- `contracts/PRODUCT_TARGET.md`, when it is in scope or needed to interpret the
  assigned product-spine step
- The files listed in the task scope

## Rules

- Work only inside your assigned worktree.
- Touch only files in task scope.
- Respect out-of-scope exactly.
- Run the task success test until it exits 0 or write a specific blocked file.
- Commit your worktree branch when the success test exits 0.
- Do not mutate the task file or success test.
- Do not add fixed verifier fixtures.
- Keep the assigned work tied to the single product spine: installed public
  product path, unified input boundary, surface runtime/action execution, memory
  resolution, proactive observation, then breadth/clean-room.
- Treat verifier and evaluator work as a guardrail, not a substitute for product
  work. If your task is proof/verifier-only, keep it scoped to the named
  product-spine step and do not expand harnesses, fixtures, or bureaucracy beyond
  what is needed to reject fake progress for that step.
- Optimize for the V7 principle, not alpha, prototype, local success, Gmail-only
  success, or any other soft completion story.
- Use user-device-engine language when touching the installed public engine,
  packaging, native host, app bridge, or device-facing runtime.
- Do not claim completion with soft language such as "done", "complete",
  "finished", "production-ready", "alpha works", "prototype works", "local
  success", or "Gmail success". Report only exact proof, remaining gaps, and
  blockers.
- Do not manufacture receipts or rely on stale source tests: no old screenshots,
  stale logs, cached browser state, fixed fixture pages, source-only proof,
  synthetic install/download proof, chrome-real-clone shortcuts, or private
  service/API bypasses.
- When the task touches user surfaces, installed behavior, capture, ASR,
  inference, or deployment, prefer real public installed app proof and
  installed-app parity from the real public product path:
  `https://www.anticipy.ai/app`, the public download/install path, and an
  installed Anticipy app talking to the user-device engine. If clean-room public
  proof is impossible in the worker worktree, write the specific blocked file.
- Preserve all four V7 input modes when relevant: Mac mic, Bluetooth mic via
  CoreAudio, MP3 upload, and Pendant via CoreBluetooth must feed the same
  post-ASR inference schema/data/eval loop.
- Do not add verifier backdoors through service keys, IMAP, Slack API, Google
  Calendar API, Notion API, app passwords, or bot tokens.
- Do not run `bash scripts/ship.sh` from the worker worktree. Workers prove the
  user-device-engine or bundled-code behavior locally and commit their branch.
  If the task changes bundled code or the user-device engine, record that
  ship/deploy parity requires post-merge `bash scripts/ship.sh`; no local proof
  replaces that ship step.
- Runtime code may not add banned models from D10.
- Frozen paths require verifier-first proof.

Exit when the success test passes and the branch is committed, or when a
specific blocked file is written.
