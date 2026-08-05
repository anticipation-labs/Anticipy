# ORCHESTRATOR HANDOFF — read all of it before touching anything

You are the new orchestrator of Anticipy. You run on Omar's Mac with full
access to this repo, his Chrome, Xcode, the Railway CLI, and a fleet of
Claude Code subagents you can spawn. You have no other context. This
document is your entire memory. The previous orchestrator (Devin) wrote it;
the addendum below it is from the orchestrator after him (2026-08-05).

---

## 0. ADDENDUM 2026-08-05 — the dinner fix (read before §6)

The demo Omar needs: he talks through a dinner plan with a friend
(Cactus Club, park location, 7 PM tomorrow, two people, said messily over
eight turns) and ONE held booking card, carrying all of it, lands on his
desk. On 2026-08-04 every line came back "Noted — nothing needed". Three
defects, all fixed, deployed to the Railway worker, live:

1. The ambient lane refused ALL consequential work from person-to-person
   speech. "May she SPEAK" and "may she WORK" are separate questions now:
   a plan agreed with another human becomes a prepared, HELD job
   (lane=desk) and she still says nothing. Dictation stays inert
   (AUTHORED_ADDRESSEES in orchestrator.py).
2. Word-overlap dedupe let a research job swallow the booking job
   ("research Cactus Club…" vs "book Cactus Club…"). Dedupe never crosses
   the consequence line now (tests/test_job_dedupe.py).
3. One dinner minted one card per turn. Consequential work now keeps ONE
   open plan per conversation (OPEN_PLAN_WINDOW=600s), merged words-first,
   model-second (_same_plan); a card only ever gets richer.

The proof: `proof/dinner_demo_proof.py` — replays the REAL transcript
through the live model, demands exactly one held booking with venue+time+
day, no duplicates, no syllable spoken over ambient speech. 16 consecutive
green runs locally (incl. 4/4 on the production model
google/gemini-2.5-flash), and the deployed production worker itself
produced exactly 1 held booking + 1 research job from the transcript's
opening lines. Run several in PARALLEL when gating — nondeterminism needs
streaks, not one green.

TRAP LEARNED THE HARD WAY (cost ~10 min of production deafness): the
worker's transcript poll (fetch_unprocessed) is the ONE query not
owner-scoped, and you cannot naively scope it — events carry `owner_ref`
(a PocketBase owners-record id like l5wygrhnb067lbs), NOT the
ANTICIPY_OWNER_ID uuid that jobs.owner uses. Two keyspaces. A `&& owner=`
filter 400s every poll and she goes DEAF while looking deployed (commit
7769e95, reverted in b032e2a). Consequences until fixed properly: (a) any
transcript row anyone writes into the shared DB is heard as Omar's own
speech — NEVER post test events to production; prove locally against a
fake PB instead, (b) the real fix needs the owners-table identity mapping
— it is queued as its own task.

Wave 2 (§6) remains parked, uncommitted, in ~/AnticipyFleet/agent4-8 —
their Claude session limit reset is 3:10pm Vancouver 2026-08-04 (already
passed; relaunch by hand if logs show no DONE). Agent7's diff changes
hear()'s signature — merge it AFTER re-basing onto the dinner fix, the
same region moved.

### Addendum, part two (later on 2026-08-05) — the second-family pass

Product rule changed by Omar (Devin's 35e9ffd): a held overheard plan now
texts ONCE for the go-ahead — silence was the old rule. dinner_demo_proof
enforces exactly-one-text (never zero, never two).

A 10-agent adversarial audit (all blockers CONFIRMED by independent
re-derivation) then drove these fixes, all deployed:
- NOT hardcoded: exhaustive sweep found zero Cactus-special product code
  and zero site recipes. The Cactus-vs-Earls gap was (a) a STALE shipped
  zip (0.2.4 sweeper) + (b) general defects only a second wording family
  could trip.
- proof/second_scenario_proof.py (Earls Brooklyn, Saturday 1pm, four
  people, terse) is the anti-overfitting gate. Both proofs must pass,
  several parallel runs each, on google/gemini-2.5-flash.
- One voice: already_raised is fuzzy + act/clock cross-class (the clock
  double-texted the dinner); failed sends are never recorded as said;
  ambient texts (kind ambient_act) obey quiet hours; act-branch repeat
  uses the queue snapshot.
- SMS amnesia: context bounds ~20 turns; thread rebuild reads
  kind=anticipy_text (what the worker actually stamps).
- goal_tokens(): shared tokenizer, numbers kept (a "2 people" card can be
  corrected to 4), light morphology (Earls/Earl's, book/booking).
- _VERBS matches VERB forms only — "reservation options" in a find-goal
  is not the verb reserve. 10-case classification check in the commit.
- _same_plan judges with the conversation visible, and hear() stashes
  self._last_convo for it.
- TEXTING_STYLE example leaked a literal "7:30" into live texts (a 1pm
  booking texted as 7pm) — neutral example + never-invent-details rule.
- Extension 0.2.6: neutralizeSpawners (target=_blank→_self + MAIN-world
  window.open hook, working tab only) and spawnedThisRun budget (5) that
  NEVER resets on navigation → clean needs_user instead of a 20-tab pile.
  Zip rebuilt AND ~/Anticipy/Extension refreshed (0.2.4 backup alongside).
  Omar still owes the ↻ reload — must say 0.2.6 now.

Rule change (2026-08-05, Omar): quiet work is no longer invisible.
Finished research — overheard or asked — texts ONE varied FYI in her
voice (worker deliver_fyi; overheard FYIs obey quiet hours) and lands on
the feed. Live in production the same night; first FYI observed in the
worker log minutes after deploy.

Later 2026-08-05, the "did nothing / lands nowhere" close-out (commit
d0a0f47): worker stamps the GOAL on heard lines (ignore+goal = quietly
working); iOS build 42 renders 'Looking into it — I'll text you what I
find' on those lines and a 'Found for you' section at the very top
(finished research as expandable FoundCards — the data was already
fetched every 3s and rendered nowhere). Two brain rules from the proof
streak: read-only prep always starts even with an unknown detail, and
self-talk questions are NEVER texted (one 'self'-classified run drew
three 'what night were you thinking?' texts — thinking aloud gets help,
not sleeve-tugging; direct asks still question at any hour). Build 42
uploaded to Apple (Delivery a8543e9c); ship pipeline that WORKS is in
the b32 history/HANDOFF.md — xcodegen + archive (profile 'Anticipy
AppStore SIWA', bundle ai.anticipy.app) + exportArchive + altool with
key JM8NMC2CQ4. build_on_mac.sh is only a simulator smoke script.

Speaker recognition remains half-shipped ON PURPOSE: brain+backend live,
iOS enrollment+tagging is the fleet's job —
NEXT WAVE, FIRST: design/briefs/09-local-speaker-recognition.md — Omar's
explicit order ("we want local everything… solve the speaker recognition
part"). The approach is already PROVEN on the Mac, zero cloud
(proof/local_diarization_poc.py): diarization 3.8x realtime CPU with
correct boundaries + re-identification, voice-profile gate 0.923 owner
vs 0.236 stranger. The brief is the build order; do not re-litigate the
stack, benchmark it on real recordings of Omar.

Still open for the fleet after that (audit fix-sketches in the run
journal): iframe/shadow-DOM visibility for embedded booking widgets
(SevenRooms — the real Earls capability gap), a "Looking into it,
quietly" feed chip + result cards in the app (needs an iOS build — Omar
has already asked for results "at the top of the app"), onCreated-
registry tab sweep, numbered-clarifier durability across redeploys,
segment parent-context carry, desk-only events leaking into the SMS
thread rebuild, owner_ref scoping of the transcript poll (task chip
pending).

---

## 0.5 ARCHITECTURE LAW — LOCAL-FIRST (Omar, 2026-08-05)

"Everything must be local-first architecture." Read design/LOCAL-FIRST.md
before any design decision. Understanding happens on the DEVICE; only
conclusions and outward actions travel. Raw audio NEVER leaves a device
(this killed the idea of moving phone transcription to Deepgram —
improve the LOCAL model instead). Voiceprints never leave, never sync,
never enter git. Cloud today: triage judgment + the memory graph — both
are named gaps with a staged path in that doc, not permanent choices.
The research arm reading the public web is fine forever; what must be
audited is raw transcript text riding along in job params.

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

Deploy: `railway up --service worker` from repo root. BACKEND: with
Railway CLI ≥5.30 (on the Mac since 2026-08-05), `railway up` from
`backend/` uploads the GIT ROOT, the builder can't find `Dockerfile`, and
the deploy FAILS (safely — the old deployment keeps serving). Deploy the
backend from a GIT-FREE COPY instead:
`cp -R backend /tmp/backend-deploy && cd /tmp/backend-deploy &&
railway link --project anticipy-production && railway service backend &&
railway up --service backend`. Expect ~8s of worker 502s while the data
volume switches instances — it self-recovers; confirm the 502 count in
worker logs stops growing. Push to GitHub does NOT deploy. Verify worker
logs and the served /anticipy-extension.zip version after every deploy.

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
