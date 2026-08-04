# HANDOFF — 2026-08-04, fleet era. Read this first, all of it.

Written by Devin for the next brain (Claude Code on Omar's Mac). Plain
words, two-year-old style, everything you need, nothing you don't.

## What this system is

Anticipy: a friend who's always with you. iPhone app hears Omar's day,
a brain (worker on Railway) decides what matters, a Chrome extension on
his Mac does browser tasks behind a confirmation gate, SMS is her tapping
his shoulder. Backend is PocketBase on Railway.

- Repo branch: `pendant-system`. ALL work happens here. Production deploys
  from it via `railway up` (NOT auto-deploy on push — you must run it).
- Backend: https://backend-production-61e0a.up.railway.app
  (`railway up --service backend`, run from `backend/` — repo root upload
  kills the builder).
- Worker: `railway up --service worker` from repo root.
- Known-good restore point if all goes to hell: git tag
  `checkpoint-working-2026-08-04` + PocketBase daily backups (09:00 UTC,
  keeps 7, restorable from the PB admin).
- Owner id in production: `45CE4E52-B83B-4F1B-8E71-389D9F39966D` (worker
  env `ANTICIPY_OWNER_ID`). If Omar reinstalls the app, the device gets a
  NEW id and jobs/browser split-brain — fix by updating that env var.

## What is DONE, deployed, and PROVEN in production (do not break these)

1. **Research arm (roadmap §6)** — read-only goals (`_READ_ONLY_RE`) run
   server-side in the worker: Brave Search + page fetch + LLM summary with
   citations. `BRAVE_API_KEY` is set on the Railway worker. Jobs carry
   `lane="research"`; the extension's claim filter excludes the lane AND a
   backend hook (`backend/pb_hooks/research_lane.pb.js`) rewrites old
   extensions' polls and 403s any browser claim on a research job. Live
   proof ran clean: `PYTHONPATH=. python3 proof/research_proof.py` with
   ANTICIPY_PB/TOKEN/OWNER_ID env — 5/5.
2. **Addressee classification (§7.1)** — triage classifies every line
   assistant|person|dictation|self (one LLM call, folded into triage,
   sticky 120s). Dictation/person speech goes ambient: remembered, quietly
   researched when read-only, NEVER an SMS or confirmation prompt.
   Deterministic pre-filter `looks_like_dictation` catches long fluent
   instruction-prose. Addressee stamped on event records.
3. **Never-foreground (§9)** — extension 0.2.4: nothing steals Chrome
   focus, ever. Hand-backs = badge + notification; only the owner's click
   surfaces a tab. Offline harness: `node extension/tests/run_all.mjs`
   (needs `extension/package.json` type:module — present).
   0.2.4 is live at /anticipy-extension.zip AND in `~/Anticipy/Extension`
   on the Mac. **Omar may still need to hit ↻ reload in chrome://extensions
   — verify it says 0.2.4.**
4. Everything from before: shared phone across accounts, truthful signup
   (iOS build 41 VALID at Apple), e2e account cleanup migration, daily DB
   backups, anti-thrash browser guards, identity split-brain fixed.

## How the work gets done: the fleet (YOU are now the manager)

Method that worked: isolated repo copies in `~/AnticipyFleet/agentN` on
the Mac, one written brief per agent (`design/briefs/NN-*.md`), launch
`claude -p "<assignment>" --dangerously-skip-permissions` from inside each
workspace, logs to `/tmp/fleet-agentN.log`. Agents must NOT push or touch
production. The manager (you) reviews every diff, runs the suites, merges
by hand, deploys, and runs a live production proof. NOTHING merges without
evidence. That gate is why nothing has regressed.

Test commands (the real ones):
- `cd repo && PYTHONPATH=$PWD python3 -m pytest tests -q` (36+ checks)
- `for t in proof/test_*.py; do PYTHONPATH=$PWD python3 $t; done` —
  skip `*live*`; 5 fail on ANY machine without a local PB/playwright/opuslib
  (test_backend, test_end_to_end, test_extension, test_full_chain,
  test_scenarios need a live LLM) — compare against a clean control clone,
  not against zero.
- `node extension/tests/run_all.mjs` (Node 22 on the Mac: nvm).
- Hook behavior: run a local PB (`backend/pocketbase serve --dir /tmp/x
  --hooksDir backend/pb_hooks --migrationsDir backend/pb_migrations`) and
  probe claim/poll paths with curl.

## WAVE 2 — IN FLIGHT RIGHT NOW (your first job: finish it)

Five agents were launched on briefs 04–08 and hit the Claude session limit
mid-work (resets 10:10am Vancouver 2026-08-04). Their PARTIAL, UNCOMMITTED
work sits in the working trees:
- `~/AnticipyFleet/agent4` — brief 04 three-lane delivery (brain/)
- `~/AnticipyFleet/agent5` — brief 05 memory consolidation + profile (brain/memory.py)
- `~/AnticipyFleet/agent6` — brief 06 heard-log redesign + app/SMS sync (app/ios/)
- `~/AnticipyFleet/agent7` — brief 07 segment-fed triage (brain/)
- `~/AnticipyFleet/agent8` — brief 08 day-zero interview + imports (iOS + brain)

A relauncher is scheduled on the Mac (`/tmp/fleet-relaunch.sh`, running as
a background loop) that restarts all five at 10:12am Vancouver telling each
to `git status`/`git diff` and CONTINUE, not start over. If it already ran,
`/tmp/fleet-relaunch.done` exists. If it didn't, run it by hand.

When they finish (they commit + print DONE in /tmp/fleet-agentN.log):
1. Review each diff against its brief. Reject scope creep.
2. Agents 4, 5, 7, 8 all touch brain/ — merge SEQUENTIALLY (apply one,
   run suites, commit, next). Expect conflicts in anticipy_core.py and
   worker.py; resolve by intent, keep both features.
3. Agent 6 + 8 touch iOS — build with `app/ios/build_on_mac.sh` after each.
4. Full suite + control comparison, then `railway up` both services, then
   a live proof per item (briefs list what to prove).
5. iOS: ship via the build script (signing works from the Mac's logged-in
   session), bump build number, upload; verify VALID at Apple.

## The full roadmap (design/PRODUCTION-ROADMAP.md — the standing checklist)

Done: §6, §7.1, §9. In flight: §3, §1, §4+§5, §2, §8.
Remaining after wave 2: §7.2 voice profile gate, §10 privacy hardening
(E2E encryption at rest, delete-my-day, on-device mode). One item at a
time, whole-system retest after each. Perfection = never backwards.

## Sharp edges (learned the hard way — respect them)

- `railway up` from repo ROOT for backend HANGS the builder; deploy backend
  from `backend/` only.
- PocketBase JS hooks: top-level consts break (isolated VM per request) —
  everything inside the handler. `app.createBackup` from JS panics — don't.
- proof/*.py are script-style (sys.exit at import) — never collect them
  with pytest; pytest.ini already scopes `testpaths = tests`.
- Extension is ES modules; `node --check` needs .mjs copies or the
  package.json marker.
- The service token guards the data API; the pairing bootstrap is the one
  open surface. Never commit tokens; never log the Brave key.
- Extension zip served from `backend/pb_public/anticipy-extension.zip` —
  rebuild it (exclude tests/ and package.json) when the extension changes,
  commit, redeploy backend.
- SMS routing follows the most recently active owner when a phone number
  is shared across accounts.
- Don't trust "all tests pass" claims — run them yourself; compare to the
  control clone.

## What Omar still owes the system (remind him gently)

1. chrome://extensions → ↻ reload Anticipy — must say 0.2.4.
2. TestFlight: be on build 41.
3. Change the Mac password he pasted into a chat once.

## The bar

He said: "Perfection means we don't go backwards. It means we accelerate
to the moon on every single one of these problems and more." Every merge
needs offline green + live production proof. The app must feel like a
person, not a product — one lit thing per screen, her voice, no
developer-feel, ever.
