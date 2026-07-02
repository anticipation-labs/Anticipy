# Anticipy — The One Map
*Head of Engineering consolidated briefing. This replaces the sprawl. Base for everything = `/Users/omarebrahim/Anticipy-devin` (branch `hoe/build`). It is the only lineage that is current, wired, deployed, AND carries the honesty tooling (`CANON/`, `factory/bin/check_wiring.py`, `overnight/done_gate.py`). Factory is its parent (harvest, don't fork). DEV-FINAL is archived (parts bin only). Desktop folders are dead.*

---

## 1. The map — per system

| System | BEST version to keep (path) | Salvage from the other versions | The exact last-10% → 100% |
|---|---|---|---|
| **Proactive (brain-decider)** | `…/Anticipy-devin/engine/anticipy_engine/proactive/` — `core/proactive.py` + `decision_pipeline.py` + `harm.py` + `triage.py` + `decider.py` + `derive.py` + `world_research.py`. ~20 brains already collapsed onto ONE spine tonight. | **DEV-FINAL:** DonnaPass "would a great assistant push back?" (`proactive/engine.py` L5); UrgencyScorer→NotificationChannel (silent/text/call); settling-buffer "still wanted?" re-validation; STORE_AS_LATENT + addressee resolution; `dispatcher.admit` LLM dedup; `proactive_day/` SimWorld as a **regression harness** for the derive loop. **Factory:** diff `extract.py`/old `decision_pipeline.py` for test cases, then delete. | **Reactive path is ~90% and live.** The loop (derive→research→act→check-in) is code-complete but only stub/suite-proven. Last 10% = **proof + closure, not engines:** (1) one **watched live run** where `derive_tick` reads live state, proposes a real unspoken need, `world_research` drives a real maps site for a REAL number, text arrives; (2) wire the **state-fill seam** (heard line → memory fact → WorldSnapshot); (3) close the **warm check-in** (tune `warrants_follow_up` so a derived need schedules its own "did that work out?"); (4) **one dedup + one budget** across derived & reactive paths; (5) **calibrate floors on a real day** (kills the dentist/trash-spam failure). |
| **Browser (web hands)** | `…/Anticipy-devin/engine/anticipy_engine/agent/webvoyager.py` — 1924-line SoM screenshot+DOM hybrid, wired to real logged-in Chrome via extension/CDP, read-back judge, money/nav hard-stops. | **browser-use 0.13.1** (installed + runnable in `engine/.bu-venv`, chromium-1223 present) as the perception/execution substrate. **DEV-FINAL:** `vision_router.py` (tier0-3 escalation gate), `vision_image_prep.py` (768px/258-tok tile — built but UNWIRED), `cdp_dispatcher.py`+`humanlike.py` (Bezier/isTrusted anti-bot + coord cache), `dsv4_skill_runner` before/after Kimi vision-verifier. **Keep devin:** `browser_hand.py` proof boundary, extension+native_bridge CDP moat. | ~43% cold. See §4 — **build the one designed-but-missing piece: voting ensemble on a screenshot-first default.** Flip screenshot to the default tier; build the voting `decide()`; gate it behind the ported `vision_router`; add per-action read-back verify; re-run `browser_bench.py` on the real WebVoyager 30 until it holds **43%→60%**. |
| **Memory / context** | `…/Anticipy-devin/engine/anticipy_engine/live_memory/` (+ `memory/store.py`) — 4 typed drawers, bi-temporal, salience, privacy, ONE `context_builder` read by decider+hands+voice+UI. **All 7 M1-M7 gates pass; per-user isolation live.** | **DEV-FINAL:** `anticipy/memory.py` `resolve_reference()` ("the boss"/"the usual place", ASK-on-miss) + model ADD/UPDATE/DELETE/NOOP reconcile; `product/dossier_active_loader.py` per-person `Person`/`preferences`/`do_not_touch`/`pronoun_map`; `anticipy/hedge.py` tone-aware extraction. **Factory:** nothing (behind). | Architecture ~85% & proven; **"learns you" is ~40%.** Last 10%: (1) **STYLE/VOICE learning** (nothing today learns how Omar writes — derive a style_profile from his sent history, inject into "speak"); (2) **never-re-ask ledger**; (3) **runtime reference resolution** (port `resolve_reference`); (4) light up the **5 stubbed live seams** (`capture.py:179`, `infer.py:58`, `maintain.py:114`, `inject.py:126`, `selfcheck.py:42`); (5) **per-person depth** (replace "person:X recurs Nx" with the Person structure). |
| **UI / frontend** | `…/Anticipy-devin/app` — `phase-zero/PhaseZeroApp.js` + `globals.css` + `app/api/*`. Every screen in one shell, 48 routes proxy the live engine, real Supabase auth. **KEEP THIS.** | **devin/web:** `styles.css` + `auth.css` design tokens (`--ink #171615` / `--paper #F5F1E8` / `--gold #B8924A` / DM Serif Display / film-grain) — port wholesale; `index.html` editorial landing. **DEV-FINAL:** `onboarding/chat` 15-25-turn conversational "scrape-you" intake; the "Seg" `ready\|needs_user\|gated\|live` honest-state pattern; the full marketing/commerce site if ever needed. | Plumbing ~80%, **feel ~45%.** Last 10% = reskin, not rebuild: (1) swap light-Fraunces theme → canonical charcoal/cream/gold/DM-Serif; (2) collapse board to **one pulsing circle + one word** (Listening/Thinking/Acting/Resting), push panels behind `?debug=1`; (3) add a **motion lib** (none in package.json today) for physics/one-at-a-time reveal; (4) build the real **60-second scrape-you onboarding** (port DEV-FINAL chat OR wire the deep scrape); (5) human-copy audit; (6) re-verify the ~44 flows against **live** Railway (only ever run vs the `:3100` mock). |
| **Inputs / voice** | `…/Anticipy-devin` — `capture/transcribe.py` + `capture/mac_mic.py` + `core/voice.py` + `channels/*` + the `app/mp3` + phase-zero upload button. **Runs offline today** (ffmpeg+Whisper+cached models). | **DEV-FINAL:** `product/tts.py` (real ElevenLabs/Polly/`say` TTS, if a check-in should be *heard*); `verifier/lib/audio.py` (BlackHole loopback test rig); `conversation_relay._ONBOARD_SYS` warm system prompt for text check-ins. | Audio input ~92% — basically done. Last 10%: (1) **surface the upload button** as the obvious front door; (2) optional **keyless browser-mic fallback** (record→POST `/owner/ingest-file` for local Whisper, so a demo needs zero keys); (3) **`humanize_ask()`** — wrap `ask_line()` through the model like `humanize_reminder` already does (~20-30 lines); (4) only append "Reply YES `<code>`" when **2+ asks pending**; single ask → "…just say yes or no." |
| **Plumbing + brain (spine)** | `…/Anticipy-devin` — `main.py` + `core/control_core.py` (the brain) + `overnight/done_gate.py`. Core spine **independently verified live**: money hard-stop holds under full-send, vents→0 cards, cards persist with read-back, confirm/resolve closes, M1 6/6 on the real model. | **DEV-FINAL grafts (all confirmed present):** `product/intent_extractor.py` (multi-intent — the DIRECT fix for recall-under-density) → into `control_core._owner_ingest_inner`; `coldstart/cdp_walker.py` + `action_engine/cdp_dispatcher.py` + `humanlike.py` (deep-scrape + real hands) onto `core/native_bridge_link.py`. **Factory:** Amazon-return recipe only if wanted. | done_gate legs 1-4 PASS, **leg 5 FAILS** (unfakeable: real stranger, real day). Work in impact order: (1) **brain recall under density** — graft multi-intent extractor (live repro: a haircut ask embedded in a 5-clause ramble is silently DROPPED); (2) **real hands** — `extension_connected:false`, no real-account action has ever run; (3) wire the **35 built-but-unwired seams**; (4) **Gmail-compose hand — NOT BUILT** (not "broken," absent); (5) premium frontend M7; (6) voice M6 (Twilio 401); (7) deploy/download M8 + trust bar M9. |

### Honesty ledger — where "done" was claimed but ISN'T (Omar's core grievance)
- **Suite is 109 passed / 10 FAILED — RED, not "green."** Every "107/112" or "113/0 green" claim is stale/unverified. Test counts are NOT proof of the loop.
- **"Brain is flawless / done"** — OVERSTATED. It passes short curated cases and **drops legitimate tasks on a realistically dense/rambly transcript.** True on the test set, false on a real messy day.
- **True proactivity "80-90% done"** — the anticipate→research→act→check-in loop **did not exist in any repo until 2026-07-02.** Honest number ~70%, stub/suite-only, **never live-proven** on a real machine.
- **"Best browser agent in the world / 100%"** — measured ~**43% cold**; hard benchmarks (Online-Mind2Web-hard, WebArena) **never run**; the 97.9% is warm replay on toy sandbox sites; **the voting ensemble Omar asked for has ZERO code.**
- **Memory "learns you"** — the plumbing is real and proven (~85%), but style-learning, never-re-ask, and reference-resolution are **~40%** — running on regex/token-counts behind `# TODO(live)`. CANON/04's named failure ("re-asks what it already learned") is **unmet.**
- **UI "full-frontend-ui / premium public welcome / stranger-ready"** — CANON/05 (authoritative): premium build **not built**, public welcome **not deployed**, onboarding is a **shallow snapshot**, flows verified only against a **mock**. Felt product ~45%.
- **"hear → act → text on a real day"** — has **never run for real.** Extension not connected, Twilio 401, `done_gate` leg 5 honestly FAILS.

---

## 2. The new sector — the walking skeleton

**Principle:** don't fork, don't rebuild. The sector is a thin **assembly layer** that (a) imports the ONE best module per system as-is, (b) holds the small set of ported grafts, (c) adds the two genuinely-new browser pieces, and (d) exposes **one orchestrator** that `overnight/done_gate.py` drives end-to-end. The existing `app/` UI stays and points at the sector's endpoints.

```
/Users/omarebrahim/Anticipy-devin/sector/
  README.md                 # "the one skeleton"; points at overnight/done_gate.py as the acceptance test
  skeleton.py               # THE orchestrator: hear → infer → decide → memory → act → check-in → learn
  wire.py                   # imports canonical modules by reference — NO copies, NO forks:
                            #   proactive.core.proactive, proactive.derive, proactive.world_research
                            #   proactive.decision_pipeline, proactive.harm
                            #   live_memory.context_builder, live_memory.capture, memory.store
                            #   capture.transcribe, capture.mac_mic, core/voice
                            #   hands.browser_hand, agent.webvoyager, core.native_bridge_link
  grafts/                   # ported best-of parts (small, self-contained, from the parts bin)
    multi_intent.py         # ← DEV-FINAL product/intent_extractor.py  (fix: recall-under-density)
    resolve_reference.py    # ← DEV-FINAL anticipy/memory.py          (never-re-ask / anchors)
    donna_pass.py           # ← DEV-FINAL proactive/engine.py L5      (assistant-quality pushback)
    urgency_channel.py      # ← DEV-FINAL UrgencyScorer→Channel        (quiet vs escalate)
    person_dossier.py       # ← DEV-FINAL dossier_active_loader.py    (per-person depth)
  browser/                  # the ONLY net-new brain code
    ensemble.py             # NEW: screenshot-first voting decide() (see §4)
    validator.py            # NEW: per-action before/after read-back verify
    vision_router.py        # ← DEV-FINAL (tier0-3 escalation gate)
    vision_image_prep.py    # ← DEV-FINAL (768px tile — wire it into the live send path)
    humanlike_cdp.py        # ← DEV-FINAL cdp_dispatcher + humanlike (anti-bot + coord cache)
  proof/
    thin_path_test.py       # the failable walking-skeleton test the sector must pass before anything else
    regression_simworld.py  # ← DEV-FINAL proactive_day/ SimWorld, as a deterministic loop harness
```

**The thin end-to-end path (the one thing that must run first — it is the whole product in a line):**

> **MP3 upload** (existing button) → `transcribe` → `owner_ingest` → **`multi_intent`** extract → `proactive.core` decide + `harm` line → **`live_memory` read/write** → **ONE real browser action** on Omar's logged-in Chrome via `browser_hand`→extension → **warm text check-in** ("Okay to send?") → **YES** → execute → "Done." → **memory learns** (style + fact).

Everything else is a widening of this line. `skeleton.py` IS what `done_gate.py` exercises; leg 5 is the acceptance.

**Deferred (Omar's explicit call — noted, not scoped):** security/safety. The existing `harm.py` money/irreversible hard-stops stay (they're load-bearing and already verified) — but **no new gates, no auth hardening, no per-seam permission work** until a single final security-wire pass at the very end. Do not let it block the skeleton.

---

## 3. The feel — psychology-driven UX spec

**Global laws (every screen):** one primary action (usually a Yes/Approve); Krug — cut half the words, then half again; zero jargon (no "Ingest," "port," JSON, model names); recognition over recall (restate what it heard, never make them remember); Fogg — assume near-zero motivation/attention, make the action **one tap**; sound human via the 3-beat rhythm **acknowledge → confirm → prompt next**; a little imperfection (over-polished reads as cold). Optimize onboarding for the **aha moment**, not completion.

| Screen | One primary action | The rule + the hook | Copy |
|---|---|---|---|
| **Welcome / landing** | "Try it" (one button) | Editorial calm (charcoal/cream/gold, DM Serif). Set expectations plainly — the #1 trust builder. | *"Vibe your life. I listen to your day and quietly handle the small stuff. I draft — you approve. I never send anything without you."* |
| **Onboarding (60s scrape-you)** | "Connect Google" → then nothing to do but watch | **Wispr's guaranteed first win.** Reading-your-week animation, then the **unasked-for recap** = the aha. Progressive disclosure: one escalating rep at a time. Instrument that aha fired **before** they leave. | *"Reading your week…"* → *"You talk to Dana most. Tuesdays are packed. Want me to keep an eye out?"* |
| **First magic moment (raw→polished)** | "Okay to send?" | The Wispr aha: show the **messy input beside the clean thing it made**, unedited. This is proof R2. | *"You mumbled 'gotta tell mom about Sunday.' Here's a text — 'Hi Mom, still on for Sunday dinner? Love you.' Okay to send?"* |
| **Board / listen** | The orb (tap to talk) | Collapse to **one pulsing circle + one word** of state. Whitespace, physics motion, one-at-a-time reveal. Panels behind `?debug=1`. | Just: **Listening. / Thinking. / Acting. / Resting.** |
| **Check-in (the text)** | One tap: **Yes** | **Draft → approve → execute, batched into ONE ask** (never piecemeal — approval spam is the #1 failure). Fire at the **emotional moment**, not the clock (this kills the old calendar-spam). Restate → show finished draft → one tap. | *"Heard the back door won't close. I found a handyman near you, free Thursday AM — want me to book it? Just say yes or no."* |
| **After success** | (none — auto-close) | Celebrate immediately and **quietly.** Close the loop, no gamified noise. | *"Done — booked for Thursday 9am. I'll remind you."* |
| **When unsure / wall** | "Log in for me?" / "Which one?" | **Fail gracefully, never dead-end.** The uncertainty gate (§4) IS the moment it asks. | *"Two dentists came up — the one on King St or on Bloor?"* |
| **Memory** | (read-only, "Forget this") | "What I've learned about you," plain-English. Surface the **investment loop** so it visibly becomes *yours*. | *"I keep replies to your sister short. You book dinners on Fridays, party of two."* |
| **Settings** | The proactivity dial | **Control is what converts proactive from annoying to trusted.** How chatty, when to stay quiet. | *"How much should I do on my own?"* — Quiet · Balanced · Take the wheel. |

---

## 4. The browser plan — breaking the 50% ceiling

**Don't rewrite, don't bet on a bigger model.** The ceiling is already broken by a **control layer**, not base models. Stand on **browser-use 0.13.1** (installed, runnable, 89.1% WebVoyager, already does DOM+Set-of-Marks+screenshot) as the perception/execution substrate, and wrap `webvoyager.py` with four thin layers:

1. **Perception — hybrid, screenshot-first.** DOM/accessibility tree + **Set-of-Marks** (numbered overlays; act by ID `click 5`, never raw pixels) as the action space. **Flip the default:** send the SoM screenshot (downscaled to one 768px/258-tok tile via the ported `vision_image_prep`) on the routine majority of steps — today `vision_pct` is only 9-27%. Vision on-demand for canvas/icon-only.
2. **Confidence-gated voting (CATTS — this is the missing piece, ZERO code today).** In `ensemble.py`: sample the next action from **2-3 cheap VLMs in parallel** (Gemini 2.5 Flash + Flash-Lite + 4o-mini + optional Fara/UI-TARS pixel-pointer), normalize to `{action,index,text}`, **majority-vote on (action-type, target-mark)**. Agreement → execute (cheap + accurate). Split → tiebreak with a 4th cheap-VLM verifier over the SoM crop; escalate to the **frontier model only on a true 3-way split** (+~5pp for ~half the tokens of blind voting — proven).
3. **Per-action Validator (`validator.py`).** After every action, screenshot + a cheap VLM confirms the intended state change (cart count up? field filled?). On mismatch, **fall through to the next-ranked ensemble candidate** instead of blindly re-clicking. This kills the compounding-error collapse (90%/step → ~57%) and closes the ~15pp benchmark-to-real gap.
4. **Task-level Reflexion.** An LLM judge scores task success; on failure, diagnose + re-attempt (pass@k). Largest single reported gain (~29% relative).

Gate all of it behind the ported **`vision_router`** (tier1 easy → single cheap pass; tier2 hard → run the ensemble; tier3 → frontier + handoff). **Product win:** the same uncertainty signal that would cause a wrong click is exactly when Anticipy **pauses and texts Omar** ("okay to send?" / "log in for me?") — the reliability mechanism and the ask-first UX become one system. Add `humanlike_cdp.py` (Bezier/isTrusted) so hard sites accept the input. Ship only when `browser_bench.py` on the real WebVoyager 30 holds **43%→60%** across repeated runs. Deferred (GPU-gated): UI-TARS/Molmo self-hosting, public leaderboard runs.

---

## 5. Order of attack — mapped to the done-gate

`done_gate.py` legs 1-4 already PASS; **leg 5 (real cold stranger, real accounts, real day) is the unfakeable finish.** One system at a time, each step a precondition for leg 5 so nothing is dropped between step 1 and step 9:

1. **Assemble the sector skeleton** (`sector/skeleton.py` + `wire.py`, no new features). Prove `proof/thin_path_test.py` runs the one line end-to-end on the mock. → *legs 1-2 hold as ONE path.*
2. **Brain recall under density** — graft `multi_intent.py` into `control_core._owner_ingest_inner`; re-run the 5-clause-ramble repro until nothing drops. → *leg 3 (catches real tasks).*
3. **Memory compounds** — never-re-ask ledger + `resolve_reference` + seed style-learning; light up the 5 live seams. Add the failable "never re-asks a known fact" gate. → *underpins trust for legs 3 & 5.*
4. **Warm inputs/voice** — surface the upload button as the front door; add `humanize_ask()`; soften the YES/NO suffix. → *leg 3 check-in copy is human.*
5. **Browser to 60%** — build `ensemble.py` + `validator.py` on browser-use, screenshot-first, gated by `vision_router`; hold 43%→60% on `browser_bench.py`. → *leg 4 reliability.*
6. **Real hands live** — Omar loads the extension in his logged-in Chrome; run the first real-account action (no more `extension_connected:false`). → *leg 4 on a real account.*
7. **Proactive loop live proof** — one watched run: `derive`→`world_research` drives a real site for a real number→warm check-in; calibrate `CONFIDENCE_FLOOR`/`MAX_NEEDS_PER_TICK` on a full real day so it does NOT spam. → *the marquee; direct leg-5 precondition.*
8. **UI reskin + onboarding** — canonical charcoal/DM-Serif tokens, one-moment-per-screen, motion lib, the 60-second scrape-you onboarding with an instrumented aha; re-verify flows against **live** Railway. → *stranger-ready front for leg 5.*
9. **Leg 5** — one real stranger, real accounts, one real ambient day (hear→infer→act→text), signed into `overnight/done_proof.json`. **done_gate leg 5 passes = done.** *(Then, and only then, the single deferred security-wire pass.)*