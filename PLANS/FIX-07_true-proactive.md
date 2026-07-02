# FIX-07 — TRUE PROACTIVITY: derive the unspoken, research the world, act, tell the owner
<!-- status: IN-PROGRESS | milestone: the marquee | created: 2026-07-02 | updated: 2026-07-02 -->

## Why (2–3 sentences, no jargon)
Before this fix, "proactive" was reactive-in-origin: the engine only reminded the owner of things
the owner literally said, at the time the owner said. The marquee behavior — noticing the kids need
pickup, checking the drive time, putting the hold on the calendar, and texting "I've got it, or you
this time?" — did not exist anywhere in the code. Now it does.

## Human check (how Omar verifies without a terminal)
Tell the app about your day (or just have real calendar/memory state), then ask me to run one
anticipation pass. You get a text about something you never asked for — with the reasoning and
what it already did — or honest silence if the day is quiet.

## Step 0 — Preconditions  [x]
**Baseline (2026-07-02):** suite 110/10 byte-identical · wiring CLEAN 37 debt · HEAD `c5b3a9e`.

## Step 1 — proactive/derive.py (the anticipation brain)  [x]
**What:** `WorldSnapshot` (now/tz/profile/open-loops/recent-cards/calendar) + `derive_needs()` —
ONE cheap-model JSON pass, then STRUCTURAL floors: action-kind whitelist (calendar_hold |
reminder | heads_up_text — money/send/purchase impossible by construction, any `_MONEY_SIGNAL`
match drops the need), confidence ≥ 0.6, max 2/tick, fail-closed [] on any error.
**WIRING PROOF (2026-07-02):** floors pinned in `test_derive_tick` (suite); stub model → `[]` proven.

## Step 2 — proactive/world_research.py (browser-only world research)  [x]
**What:** each research question → `Job(intent="browse_task")` on the SHARED Bus → the SAME
WebVoyagerAgent behind /agent/run (nav-wall, money guard, judge intact). No maps API, no per-site
code — the agent picks the site. `resolve_person()` = the REAL caller for the formerly-orphaned
anticipate.research_person. Honest per-question ok/answer/proof; failures never raise.
**WIRING PROOF (2026-07-02):** live acceptance below — research ran, honest `ok:false` misses with
proof URLs (mock browser), zero fabricated answers.

## Step 3 — ControlCore.derive_tick + /derive/tick + scheduler  [x]
**What:** snapshot → derive → fire-once ledger (`derived_needs.json`, per local-day + obligation-sig,
MARK BEFORE ACT) → dedupe vs open loops/recent cards (`_same_obligation`) → research → compose ONE
plain-English sentence → submit through the ONE FRONT DOOR (`owner_ingest` — same extractor, same
harm-line, same autonomy dial; no new decision engine) → acted/heads-up ⇒ ONE `notify_user` text
(budget-counted); asks never double-text. `_derive_scheduler` gated by `ANTICIPY_DERIVE_SECONDS`
(default 0 = OFF — zero behavior change until enabled).
**Proof command:** `ANTICIPY_MODEL_PROVIDER=stub ... engine/.venv/bin/python engine/scripts/test_derive_tick.py`
**WIRING PROOF (2026-07-02):** `PASS derive_tick: derive→research→front-door→notify proven;
fire-once holds; floors structural; stub honest` — added to run_suite.sh.

## Step 4 — LIVE-MODEL acceptance (the marquee, mock hands/channels)  [x]
**What I ran (fresh engine :8793, real model):** ingest the ambient line "Maya said can you grab
Leila from Lakeview Elementary at 3:15 today. Investor sync 1:30 to 2:30 at the office." then
`POST /derive/tick`.
**What happened (2026-07-02):**
- Reactive catch: "Pick up Leila from Lakeview Elementary at 3:15 PM today" → card + open loop.
- THE DERIVE: the model derived an UNSPOKEN need — "Prepare for potential client follow-up after
  investor sync" — with why + evidence citing the calendar. Nobody said it. It did NOT re-derive
  the Leila pickup (dedupe vs the open loop held, exactly as designed).
- Research ran browser-only and reported HONEST misses (`ok:false` + DuckDuckGo proof URLs, mock
  browser) — no fabricated facts.
- The need became a reminder card through owner_ingest and the owner was texted: glassbox shows
  `2 derived_notified`.
**WIRING PROOF:** outputs pasted above (2026-07-02).

## Step 5 — PROACTIVE→BROWSER, REAL (Omar's directive 2026-07-02: "don't stop until it works")  [x]
**What:** built the missing browser arm end-to-end. (a) Bridge venv `engine/.bu-venv` (py3.11 +
browser-use 0.13.1 + playwright — playwright was the missing import behind "CDP endpoint did not
come up"; Chrome-148 CFT only comes up when playwright spawns it). (b) browser_hand: READ-ONLY
research (research=True) PREFERS the throwaway runner; no-link browse_task falls back to it; the
strict no-guessed-site rule stays for ACTION tasks, search-start allowed only for research.
(c) derive prompt: research questions must be answerable NOW on public pages ("search the web for
the driving time … report the estimate you find").
**WIRING PROOFS (2026-07-02, all REAL browser):**
- Runner standalone: Wikipedia first sentence, success, 19.3s, screenshot.
- PRODUCT BUS browse_task: "662,248" (Vancouver population) + proof URL #Demographics.
- world_research through the bus (the exact derive path): `ok: True, answer: "11 minutes"` for the
  downtown→Kitsilano drive, proof URL attached.
- Composed derive_tick (live hands): derived the pickup travel-time need unprompted, ACTED (set the
  reminder), texted: "…pick up Leila from school… I set the reminder — I've got it, or you this
  time?" — the marquee sentence, real pipeline, honest couldn't-verify when a page fell short.
- Gates: suite 112/10 byte-identical · GATE-M fresh-engine 6/6 · PASS · ALL PASS · wiring CLEAN (debt 35).

## Remaining (queued)
- [ ] UI surface: show derived cards with their "why" + research on the board (FIX-05/06 UI pass).
- [ ] Research-arm robustness: the runner answers commute-class questions reliably; keep tuning
  question phrasing as real usage accumulates.
- [ ] Omar-live: enable `ANTICIPY_DERIVE_SECONDS=900` + his real Chrome (L1) + live SMS (L2).

## Final step — The gates + commit  [x]
**WIRING PROOF (2026-07-02):** `==== SUITE: 111 passed, 10 failed ====` — 110→111 = exactly the new
derive_tick pass; FAILED set byte-identical to baseline. Wiring gate: `WIRING: CLEAN (66 endpoints /
47 routes / 95 modules checked, 45 allowlisted incl. 39 TODO-debt)`.
