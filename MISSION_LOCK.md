# MISSION_LOCK — the ONLY source of mission truth (read FIRST, every session)

> This file is authoritative. It supersedes every other goal doc, handoff, or agent prompt on
> conflict. It was locked on 2026-07-01 by Omar's explicit instruction. Do not soften it, do not
> re-scope it, do not let it drift. Newer dated entries in the STATUS TABLE win over older ones.

## THE OPERATING PROTOCOL (non-negotiable)
1. **Always work the LOWEST OPEN milestone.** Track B and M1 may run in parallel (Track B has zero
   engine dependency). Otherwise strictly dependency-ordered.
2. **Prove every milestone by running its PASS test on the LIVE engine** — never by claim. A milestone
   is not PASSED until its **PASS output is pasted into the STATUS TABLE** with a replayable proof
   command. "The code exists" / "a test passed once" is NOT passed.
3. **Record proof → commit → move to the next.** Autonomously. No stopping, no asking, until **M8's
   PASS is green** (a fresh user completes the hosted flow end-to-end).
4. **Detours** (Omar's side requests — demos, cleanups, one-off fixes): do them, log them in the
   DETOURS section, then **RETURN to the lowest open milestone.** A detour NEVER becomes the mission.
   The Amazon return (`AMAZON_RETURN_HANDOFF.md`, `~/.claude/plans/logical-frolicking-lobster.md`) is
   explicitly **NOT the mission** — at most a detour if Omar asks.
5. **Money / submit / irreversible = the ONLY hard stop.** Always confirm; never auto-spend, never
   auto-submit. This overrides every autonomy mode.
6. **Never fake done.** No milestone claim without its pasted PASS output. Honest handbacks over false
   success.

## Provenance & base (locked judgment calls, 2026-07-01)
- **Verbatim source of the plan below:** `~/.claude/plans/okay-you-re-sure-pure-ocean.md` ("Anticipy —
  From Here to Genuinely Finished"). Omar cited `logical-frolicking-lobster.md` by mistake — that slug
  is the Amazon-return perception plan, which is NOT the mission.
- **Working base:** `/Users/omarebrahim/Anticipy-devin`, branch `hoe/build` off
  `origin/devin/full-frontend-ui` (PR #4 → main is MERGEABLE/CLEAN). This is a **superset** of the
  plan's original base (`~/Anticipy` @ `factory/build`, 2026-06-23) — more is already built (memory
  M0–M7 spine, onboarding scrape modules, frontend MVP). The plan's `file:line` references are from the
  older base and are **guides**; the functions exist, at shifted line numbers — locate, don't trust the
  number. Omar's existing `~/Anticipy` checkout is left untouched.
- **Engine (live) run:** `engine/.venv/bin/python -m uvicorn --app-dir engine anticipy_engine.main:app --port 8787`
- **Suite:** `bash scripts/run_suite.sh` (stub-forced; RED 109/10 at baseline 2026-07-01 — see STATUS).

---

# THE PLAN (verbatim from okay-you-re-sure-pure-ocean.md)

## "Fully done" (Omar's words)
A hosted, premium website anyone can visit → "here's what Anticipy is" → onboarding = layered scrape ↔
phone-call loop → confirmation → main app (Listen/MP3/Paste + a swipeable card deck:
confirm/deny/allow/feedback, self-improving) → a proactive brain that's flawless + a browser agent
equally good → **talks like a human** (never `task #24a`, never formulaic) → **goes the extra mile** →
3 autonomy modes (Full-Send/Regular/Limited) with trust that builds over time → premium real-time voice
you can't tell is AI → money/irreversible always confirm. Horizontal (any profession). Backend impeccable.

## The honest architecture (non-negotiable)
The engine **must run on the user's Mac** (it drives their *real* logged-in Chrome + local accounts) — it
cannot be a pure cloud service. **Fully-done = a hosted premium welcome/onboarding site (Vercel) that
talks to a local engine the user downloads/runs.** Marketing + onboarding UI = hosted; brain/hands = local.

## The two grafts (DEV-FINAL → base)
1. **Structured intent-extractor** — `Developer/Anticipy-DEV-FINAL/engine/app/product/intent_extractor.py`
   (+`intent_extractor_endpoints.py`). Zero pip deps (stdlib + OpenRouter). `Intent` dataclass:
   `type, target_surface, target_person_refs, required_slots, missing_slots, risk_level, confidence,
   actionable_probability, is_third_party_want, is_hypothetical` + `is_actionable()`. Port with two
   changes: (a) return **`list[Intent]`** not one; (b) gemini-2.5-flash primary, others fallback only.
2. **Stealth CDP scrape/action** — `…/coldstart/cdp_walker.py` + `action_engine/cdp_dispatcher.py`
   (+`humanlike.py`). Drives real Chrome over CDP (`:9222`) with humanlike motion;
   `walk_gmail/calendar/drive/source`, `connect_to_chrome`, `humanlike_click/type/key/scroll`,
   `dispatch_fara_action`. Deps: `httpx, numpy, websockets`. Adapt the walker to the base's
   `core/native_bridge_link.py` (do not stand up DEV-FINAL's separate `:7777` bridge).

## TRACK B (parallel, starts immediately — zero engine dependency)
**Welcome site live ASAP.** A premium hosted "here's what Anticipy is" page (fresh build,
`frontend-design` skill, charcoal/cream/gold, "Vibe your life.", a looping micro-demo of a card being
confirmed) + an "engine offline → here's how to get it" state. Deploy to Vercel.
- **PASS:** a stranger visits the public URL and sees a premium, clear, fast welcome — nothing owner-mode ugly.

## TRACK A — the milestones (dependency-ordered)

### M1 — Brain correctness (graft + 4 fixes). *(foundation; everything depends on it)*
- **Multi-intent:** port the extractor as `list[Intent]`; wire into `control_core.py` `_owner_ingest_inner`
  / `_expand_tasks_with_model` so one line → N cards. Reuse `owner_mode._split_intent_clauses` as backstop.
- **Money-flag scoping:** change line-wide `money_src` to **per-clause**; gate only the specific clause at
  `_spine_card` money hard-stop. Canonical signal stays `proactive/harm.py:_MONEY_SIGNAL`.
- **Missing-slot → ask:** in `_spine_card` after context read + `owner_mode._card_for_line` browser branch,
  if a required entity (restaurant/product/recipient) is unresolved, route to `_browser_action_ask` not AUTO_DO.
- **Ignore-trace:** dropped vent/sarcasm → push to `ignored[]` with reason + increment `ignored_line_count`.
- **PASS:** the 6-line battery yields exactly — mom/plant=ask, Sarah/deck=prepare+follow-up, judgment=ask,
  traffic→{kids=do (NOT money), $4,200=blocked/confirm, vent=ignored+logged}, dinner=ask-for-slot,
  sarcasm=ignored(count≥1). **$4,200 never dropped.**

### M2 — Human-copy engine + go-the-extra-mile.
- **One copy seam.** Add a single render layer (`engine/anticipy_engine/copy/voice.py`) that takes the
  structured card and emits human copy via a cheap model in the Anticipy voice — **never task-IDs/UUIDs,
  never the same line twice.** Reuse the frontend `humanCopy()` vendor-scrub guard on the surface.
- **Extra-mile:** a `do`-card carries real work product (candidate restaurants, the drafted message), not
  `execution=null`; fold recalled memory into the card.
- **PASS:** blind-read 20 cards — zero IDs/"Confirm task:" templates; dinner card shows real candidates;
  the Maya card shows the after-lunch window.

### M3 — Three autonomy modes + trust ledger.
- Surface **Full-Send / Regular(default) / Limited** onto the ladder in `proactive/autonomy.py`. Add
  `trust_tier` to `OwnerTaskCard` + a per-task-type trust ledger (promote ≥5 clean reps, demote on
  rejection; irreversibles cap at CONFIRM). Pre-consent tokens for Full-Send (scoped/ceilinged/expiring).
- **Two invariants override every mode:** money/send-to-human/delete/binding = confirm; below confidence
  floor, every mode drops a level.
- **PASS:** a coffee task promotes ASK→NOTIFY after 5 clean reps then demotes 2 on a complaint; a $4,200
  spend stays CONFIRM in **every** mode including Full-Send.

### M4 — Browser agent honesty + wall handoff.
- Split `agent_finished` vs judge-verified `task_succeeded` via `/agent/judge` + `webvoyager._judge_success`.
  The false `success:true` (from `browse_act`) is a "never fake done" violation — fix it.
- Wall (Cloudflare/login/MFA/captcha) → **pause → text you → `/agent/resume`** (add mid-plan state restore).
  Never auto-type creds/solve captchas.
- `/agent/act` mode param: throwaway (limited) vs **real-Chrome CDP via cdp_walker (full-send)**; auto-escalate on wall.
- **PASS:** a walled task returns the real answer via real-Chrome **or** `needs_human`+texts you; **never** a false success.

### M5 — Stealth onboarding scrape (layered). *(uses M4 plumbing)*
- Wire `cdp_walker` (adapted to `native_bridge_link`) as the engine behind onboarding "layer 1/2 scrape":
  walk real logged-in Gmail/Calendar/Drive/etc., build the profile into the 4-drawer memory.
- **PASS:** a logged-in scrape of one real account returns structured rows into memory with **zero
  credential-typing** by the agent.

### M6 — Premium real-time voice.
- Wire **ElevenLabs Conversational AI via Twilio ConversationRelay** into `channels/conversation_relay.py`
  `ConversationRelayBrain` (+ `ANTICIPY_CR_WSS_URL` + a `/cr` websocket route); make onboarding phone-call steps real.
- **PASS:** a real call completes a setup exchange; 3/3 blind listeners can't tag it AI; sub-second turns.

### M7 — Frontend: full app, fresh build (welcome → onboarding → swipe cards). *(largest; after the brain)*
- **Fresh build from scratch** with the `frontend-design` skill — own premium design system (editorial,
  charcoal/cream/gold, DM Serif headlines + quiet sans). DEV-FINAL components are reference only.
- Reuse proven *patterns* only (logic not look): `humanCopy()` guard, OAuth-poll, `StepRecap` editable facts,
  Listen+transcript, card-section logic.
- Net-new: the **swipeable card deck** (confirm/deny/allow/feedback, spring physics, gold=confirm, never
  harsh red) wired to the live engine; onboarding as the scrape↔call loop with a progress bar that starts
  partly filled; the Listen/MP3/Paste main screen. Folds Track B's welcome into the full site.
- **PASS:** a stranger visits the public URL, completes onboarding (scrape→call→scrape→call→confirm), lands
  in the app, and swipes **real** cards that confirm/deny/allow/feedback against the live engine.

### M8 — Hosting + hardening. *(THE FINISH LINE for the autonomous grind)*
- Deploy the site (Vercel); engine stays local but packaged for clean download+run (`/download` flow);
  secrets handled; per-user local data; `/status` exposes memory mode + fix `/memory/drawers` 404.
- **PASS:** hosted site works from a phone on cellular; a fresh user downloads the engine, pairs the
  extension, and the loop runs end-to-end on their machine.

### M9 — The trust bar (continuous; partly beyond-frontier).
- Engineer around raw autonomy limits: deterministic macros for the top ~20 flows + self-verify judge +
  real-Chrome CDP + **human confirms the one irreversible button.**
- **PASS:** on 10 hard real tasks, macro flows ≥90% task-completion, every irreversible step human-confirmed,
  **zero** hallucinated successes.

## Verification (how each milestone is proven)
- Brain/memory/modes: POST real lines to the live engine `/owner/ingest`, GET `/owner/cards` + `/memory/*`,
  assert exact dispositions — re-runnable via `overnight/harness.py`.
- Browser: `/agent/act` + `/agent/judge` on real tasks; a walled task must return `needs_human`, never false success.
- Voice: a real Twilio call; blind-listener test.
- Frontend: a stranger completes the hosted flow against the live engine; swipe cards mutate real engine state.

---

# STATUS TABLE (the live scoreboard — PASSED needs pasted proof; else OPEN)

Proof commands assume MY engine live on :8790 (safe: channels/hands=mock, inbound=0, real gemini model,
isolated data dir). Launch: `ANTICIPY_CHANNELS_MODE=mock ANTICIPY_HANDS_MODE=mock ANTICIPY_INBOUND_POLL_SECONDS=0 ANTICIPY_DATA_DIR=$PWD/.anticipy-data-hoe PYTHONPATH=engine engine/.venv/bin/python -m uvicorn --app-dir engine anticipy_engine.main:app --port 8790`

| Milestone | Status | Proof command (replayable) | Proof / notes |
|---|---|---|---|
| Track B — welcome site | OPEN | stranger loads public Vercel URL; visual premium check | not built/deployed |
| **M1 — brain correctness** | **OPEN (5/6)** | `ANTICIPY_ENGINE_URL=http://127.0.0.1:8790 python3 overnight/m1_battery.py` | 2026-07-01: 5/6 — see BASELINE PROOFS. Only gap: case 5 (dinner, no restaurant) yields **0 cards** instead of ask-for-slot. Cases 1–4,6 pass incl. **$4,200 blocked + never dropped**. |
| **M2 — human copy** | **PASSED** | `ANTICIPY_ENGINE_URL=http://127.0.0.1:8790 python3 overnight/m2_copy_test.py` | 2026-07-01: PASS — 5/5 distinct human titles, 0 leaks. See BASELINE PROOFS. |
| **M3 — autonomy + trust** | **PASSED** | `ANTICIPY_ENGINE_URL=http://127.0.0.1:8790 python3 overnight/m3_integration_test.py` (fresh engine) | 2026-07-01: ALL PASS 9/9 incl. $4,200 blocked in full_send + trust promote after 5 reps. See BASELINE PROOFS. |
| M4 — browser honesty | OPEN | walled-task `/agent/act`+`/agent/judge`: needs_human, never false success | not baselined; false `success:true` fix unverified |
| M5 — onboarding scrape | OPEN | logged-in scrape of 1 real account → structured rows in memory, 0 cred-typing | not baselined; needs real logged-in Chrome + CDP. NOTE: deep-crawl code exists (`owner_scrape.py`) but UI path uses a shallow single-viewport extension snapshot (see handoff-clone memory). |
| M6 — real-time voice | OPEN | real Twilio call; 3/3 blind can't tag AI; sub-second turns | not baselined; ConversationRelay only half-scaffolded |
| M7 — frontend app | OPEN | stranger completes onboarding + swipes real cards vs live engine | not built (fresh premium build pending) |
| M8 — hosting/download | OPEN | hosted site on cellular + fresh-user download→pair→loop runs | not deployed |
| M9 — trust bar | OPEN | 10 hard tasks ≥90% macro completion, every irreversible confirmed, 0 fake success | not baselined |

Baseline 2026-07-01: M2 ✓, M3 ✓, M1 5/6 (grinding). M4–M9 + Track B OPEN. NOTE: the stub-forced
`run_suite.sh` is RED 109/10, but the REAL-model brain baselines (M1/M2/M3) show that is mostly
stub-model brittleness, not real regressions — separate them when they gate a milestone.

## BASELINE PROOFS (pasted output, 2026-07-01)

**M1 — `overnight/m1_battery.py` vs live :8790 (real gemini):**
```
[PASS] 1 mom/plant -> ask :: dispositions=['ask']
[PASS] 2 Sarah/deck -> ask :: dispositions=['ask']
[PASS] 3 judgment -> ask :: dispositions=['ask']
[PASS] 4 traffic+kids+$4,200 (kids!=money, $4,200 blocked, never dropped) :: kids_ok(not money)=True $4200_present=True $4200_blocked=True | Pick up kids at 2:45::ask/create_calendar_or_reminder | Pay the $4,200 invoice::blocked/prepare_purchase_path_without_payment
[FAIL] 5 dinner(no restaurant) -> ask-for-slot :: dispositions=[]
[PASS] 6 sarcasm -> ignored + logged :: cards=0 ignored_line_count=1
M1 BATTERY: 5/6 pass
```

**M2 — `overnight/m2_copy_test.py` vs live :8790:**
```
cards checked: 5 | distinct titles: 5/5 | leaks: 0
  TITLE: 'Checking on that plant return for you'
  TITLE: 'Looking over that Sarah deck for you'
  TITLE: 'Getting the satisfaction of judgment filed'
  TITLE: "Checking on the kids' pickup"
  TITLE: 'Holding off on the big bill'
M2 COPY: PASS
```

**M3 — `overnight/m3_integration_test.py` vs fresh :8790:**
```
[PASS] default mode = regular
[PASS] set full_send sticks
[PASS] $4,200 BLOCKED in full_send (invariant)
[PASS] send-to-human stays ask in full_send
[PASS] full_send AUTO-RUNS a reversible web task (do)
[PASS] regular web task -> ask (no trust yet)
[PASS] 5 web asks were resolvable (browser_action)
[PASS] trust PROMOTES web ask->do after 5 clean reps (regular)
[PASS] limited keeps web task as ask even with trust
M3 INTEGRATION: ALL PASS
```

---

# DETOURS (side requests — do, log, RETURN to lowest open milestone)

| Date | Request | Done? | Notes |
|---|---|---|---|
| 2026-07-01 | Set up canonical clone off devin branch; sanity-check stack | yes | clone at ~/Anticipy-devin (hoe/build); engine boots; suite RED 109/10 |
| 2026-07-01 | STOP Amazon return as mission; write this MISSION_LOCK | yes | this file; Amazon plan is not the mission |
