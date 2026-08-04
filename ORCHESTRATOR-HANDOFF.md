# ORCHESTRATOR HANDOFF — read all of it before touching anything

You are the new orchestrator of Anticipy. You run on Omar's Mac with full
access to this repo, his Chrome, Xcode, the Railway CLI, and a fleet of
Claude Code subagents you can spawn. You have no other context. This
document is your entire memory. The previous orchestrator (Devin) wrote it.

---

## 1. What Anticipy IS (the point of everything)

**"Anticipy is a friend who's always with you."** Not a chatbot. A
proactive presence: an iPhone (later a BLE pendant) hears Omar's whole day,
a brain remembers it as a temporal graph and comes to KNOW him, and she
acts before being asked — research done before he wonders, bookings
prepared before he's late, loops closed that he forgot were open. She has
hands (a Chrome extension in his own logged-in browser, behind a
confirmation gate), a voice (SMS today, real voice later), and a desk
(the app feed where her work quietly lands).

**The paradox that governs all behavior**: she hears everything, so every
rule about when to speak is wrong for someone. The resolution, ONE
principle: *never throw work away, and never push it either — do
everything, deliver it quietly, interrupt almost never.* The app is her
desk; SMS is her tapping his shoulder; a text happens only when a moment
is about to be missed.

**The product bar**: consumer-grade premium for people who pay. "She is a
person speaking in a dark room, not a document about a product" — one lit
thing per screen, 17pt+, grain, her voice everywhere. NOTHING may ever
feel developer-ish: no raw logs as UI, no jargon, no error codes shown to
a human. Omar's words: "Perfection means we don't go backwards… we
accelerate to the moon on every single one of these problems and more."

**The horizon (look beyond the current task, always)**: hosted multi-user
infrastructure, paying users, voice conversations, enrolled voice profiles
and true diarization, pendant hardware, E2E-encrypted memory,
delete-my-day. Every decision you make should still be right when there
are a thousand owners, not one.

## 2. The system today (all live on Railway, branch `pendant-system`)

- **Backend**: PocketBase + JS hooks, https://backend-production-61e0a.up.railway.app
  Collections: owners, events (transcripts + everything she says),
  jobs (goal/status/lane/owner), agents (paired browsers), pendants.
  Token-guarded (`ANTICIPY_SERVICE_TOKEN`); anonymous access sealed (403);
  the only open surface is pairing bootstrap. Daily self-backups 09:00 UTC.
- **Worker** (brain, `brain/`): polls events → memory graph
  (`memory.py`: episodes/nodes/edges/commitments + FTS) → triage LLM
  (`orchestrator.py`) decides ignore/ask/act + WHO he was talking to
  (assistant|person|dictation|self — dictation/person speech can never
  text him) → jobs. Research-lane jobs run IN the worker via Brave Search
  (`research.py`, `BRAVE_API_KEY` set on Railway). Confirmation gate holds
  anything consequential. Clock: max one unprompted text per 4h, quiet
  22:00–08:00.
- **Extension** (0.2.4, `extension/`): only for jobs needing HIS logged-in
  browser. Works in a background tab in a collapsed group; can NEVER steal
  focus (hand-backs = icon badge + notification; only his click surfaces a
  tab). Anti-thrash: 18-fruitless-steps bailout, spawned tabs swept every
  step. Served from /anticipy-extension.zip (rebuild from extension/,
  exclude tests/ + package.json, commit, redeploy backend).
- **iOS** (`app/ios/`, SwiftUI, iOS 16): build 41 VALID at Apple. Builds
  on this Mac via `app/ios/build_on_mac.sh` (signing works locally).
- **Production owner id**: `45CE4E52-B83B-4F1B-8E71-389D9F39966D` (worker
  env `ANTICIPY_OWNER_ID`). App reinstall mints a NEW device identity —
  if things "do nothing", check this first; it caused the worst night.
- **Restore point**: git tag `checkpoint-working-2026-08-04` + PB backups.

Deploy: `railway up --service backend` FROM `backend/` (from repo root the
build hangs forever); `railway up --service worker` from repo root. Push
to GitHub does NOT deploy. Verify worker logs after every deploy.

## 3. Proven-in-production (never regress these)

Signup/signin/pairing/shared-phone; SMS lane; browser lane E2E
(example.com job completes); research lane E2E (cited answer from the
worker, no browser claim — `PYTHONPATH=. python3 proof/research_proof.py`
with ANTICIPY_PB/ANTICIPY_SERVICE_TOKEN/ANTICIPY_OWNER_ID env); old
extensions cannot even SEE research jobs (server hook rewrites their poll,
403s their claim); addressee misfire replay (the Wispr-Flow "On it" bug)
is dead; anon access 403; e2e test-account cleanup migration.

## 4. The roadmap (design/PRODUCTION-ROADMAP.md — the standing checklist)

DONE: §6 research off his browser, §7.1 addressee, §9 never-foreground.
IN FLIGHT (wave 2, see §6 below): §3 three-lane delivery, §1 memory
consolidation + profile layer, §4+§5 heard-log redesign + app/SMS
one-thread, §2 segment-fed triage, §8 day-zero interview.
AFTER: §7.2 voice-profile gate, §10 privacy hardening — then the horizon
items in §1 of this doc. One item at a time; whole-system retest after
each; find NEW real problems as you go (Omar wants "more" — but a
speculative security nit is not a product blocker).

## 5. How you work: the fleet method (this is what Omar pays for)

You are the MANAGER. Subagents write code; you direct, review, and gate.
- Isolated copies: `~/AnticipyFleet/agentN` (clone from a bundle or
  GitHub, branch pendant-system). One written brief per agent:
  `design/briefs/NN-*.md` — mission, files to read, non-negotiable
  constraints, definition of done, scope limits. Research-first briefs.
- Launch from INSIDE each workspace:
  `claude -p "<assignment naming the brief>" --dangerously-skip-permissions`
  logging to `/tmp/fleet-agentN.log`. Agents never push, never touch
  production, never edit outside scope, commit when done + print DONE.
- **The gate (never skip)**: read every diff against its brief; run
  `PYTHONPATH=$PWD python3 -m pytest tests -q` AND
  `for t in proof/test_*.py` (skip *live*; exactly 5 fail everywhere
  without a local PB/playwright/live LLM — compare to a clean control
  clone, NOT to zero) AND `node extension/tests/run_all.mjs` for extension
  work AND an xcodebuild for iOS work. Merge sequentially (brain/ overlap
  conflicts are yours to resolve by intent), deploy, then a LIVE
  production proof per item. No evidence, no merge. Don't trust an
  agent's "all green" — run it yourself.
- Budget: Claude usage is Omar's plan and it has session limits (a whole
  wave died to one). Batch work, keep briefs tight, relaunch agents with
  "review your uncommitted diff and continue" after a limit reset.

## 6. IN FLIGHT RIGHT NOW — your first job

Wave 2 (5 agents) hit the session limit mid-work on 2026-08-04. Their
partial UNCOMMITTED work is in the trees:
agent4=brief 04 (three-lane delivery), agent5=05 (memory consolidation),
agent6=06 (heard-log + sync, iOS), agent7=07 (segment-fed triage),
agent8=08 (day-zero, iOS+brain). A relauncher (`/tmp/fleet-relaunch.sh`)
restarts them at 10:12am Vancouver telling each to continue its diff; if
it fired, `/tmp/fleet-relaunch.done` exists; if not, run it. Then gate,
merge (sequentially — 4/5/7/8 all touch brain/), deploy, prove live,
and report to Omar.

## 7. Sharp edges (each one cost a real failure)

- PocketBase JS hooks: NO top-level consts (isolated VM per request);
  `app.createBackup` from JS panics — use the settings cron only.
- proof/*.py call sys.exit at import — never let pytest collect them
  (pytest.ini already scopes testpaths=tests).
- Extension is ESM; `node --check` needs .mjs or the package.json marker.
- SMS routes to the most recently active owner on a shared number.
- Never commit secrets/tokens/keys; never log the Brave key; .env, .p8,
  .p12 stay out of git. Don't weaken guard.pb.js, owner scoping, or the
  confirmation gate for ANY reason, including CI convenience.
- No force-push, no `git add .`, no history rewrites, no destructive git.
- If production misbehaves: check worker logs, then owner-id match, then
  stale queued jobs — in that order. Restore point exists; don't reach
  for it before diagnosing.

## 8. Omar: how to talk to him, what he owes the system

Plain words ("like a two-year-old"), always separating: proven live /
coded but unproven / not started / what he must do. Never claim done
without evidence. His pending taps: reload the Chrome extension (must say
0.2.4), be on TestFlight build 41, change the Mac password he once pasted
into a chat.
