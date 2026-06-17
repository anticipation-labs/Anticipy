# RECEIPTS — append-only ledger of what is PROVEN done

A receipt is a human-openable artifact + an independent skeptic verdict. No receipt, no done.
This file is append-only. The deep historical ledger is `logs/factory/RECEIPTS.md` +
`logs/factory/FOREMAN_STATE.md`; entries below are the Agent-OS summary (re-verify before trusting).

---

### R-2026-06-16-A — Memory Dock (Gate A continuity) installed + state re-verified
- **Gate:** A — Truth & continuity. **CLOSED.**
- **Commits:** Memory Dock (see git log) + `f05d453` (browser gate).
- **Artifact:** `docs/agent_os/*` + `scripts/agent_os/*.sh` + `CODEX.md` + CLAUDE/AGENTS first-read pointers; imported kit in `docs/agent_os/imported/`; `docs/agent_os/preflight-2026-06-16.txt`.
- **Receipt (failable checks I ran, not trusted):** OpenRouter route live (provider=openrouter, base url correct; reality_check "messy→cards LIVE" = a real model call); `safety_mega_eval` BREACHES 0; `reality_check` 6/8 (6/7 me-verifiable); suite GREEN 90/0; Codex CLI authenticated.
- **Skeptic finding (real):** the imported "suite GREEN 90/90" claim was FALSE — suite was RED 86/4 on arrival. Caught by re-running, not trusting. See R-2026-06-16-B.
- **Limitation:** imported prior receipts (below) are claimed-live, not re-proven this session.

### R-2026-06-16-B — Browser arm: prepare-when-confident + b82e660 regression fixes
- **Gate:** C/E (core messy-day + browser arm), brain/anti-spam.
- **Commit:** `f05d453`.
- **Artifact / receipt:** suite GREEN **90/0** (`/tmp/anticipy_suite3.log`); the 4 previously-RED tests
  (owner_ingest_event, public_backend_path, messy_proactive_handoff, owner_app_product_path) pass against
  REAL behavior; `safety_mega_eval` BREACHES 0; resolved carts auto-prepare with `memory_resolution`
  receipt; unresolved → one deterministic confirm-first ask; re-ingest idempotent; declined web task → durable `declined`.
- **Skeptic verdict (me):** safety floor independently re-run = 0 breaches; money/vent assertions preserved
  verbatim; engine changes are browser-routing only (no decision/harm-line edits).
- **Decision basis:** Omar chose "prepare when confident" (2026-06-16) over uniform confirm-first.
- **Limitation:** browser auto-prep verified in stub/mock (throwaway browser, money/checkout guard). A
  LIVE browser auto-cart on a real site (Gate E live) is not yet proven.

---

### R-2026-06-16-C — Gate 1: messy transcript → cards, end-to-end through the REAL app UI
- **Gate:** 1 (app opens, routes to real brain) + 2 (messy input → correct cards) — driven in Chrome, not curl.
- **Receipt (visible):** opened http://localhost:3000 in Chrome, pasted Omar's 8-line test transcript
  (Amazon plant, "I'll handle it", coffee→woods vent, boss/Sam deck, "I'll get the deck", pickup@3,
  lottery vent, CRM retainer), clicked **Read my day** → app rendered sections **"Here's what I caught" /
  "Waiting for your yes" / "Left for you" / "Still open"** with **Yes / Not now** buttons. Human language
  throughout; zero code jargon.
- **Safety verified (the important part):** BOTH vents (coffee→"moving to the woods", lottery→"island")
  are **SILENT** — absent from every section. Nothing auto-sent/bought. CRM/"money" task parked as
  **"Left for you"** ("the final move is yours — I won't spend or sign in for you"). Browser/external
  tasks parked as confirm-first asks. Pickup caught as **Ready**.
- **Found + fixed mid-gate:** the live engine on :8787 was a STALE process (old code) returning **500 on
  `/owner/ingest` execute=true** — the app showed "Could not reach Anticipy Engine." Restarted on the
  fixed/committed code with SAFE env (channels=mock, inbound poll=0); ingest now 200 in ~7s. (New code
  verified via TestClient 200 before restart.)
- **NOT done (refused to call done):** heavy **duplicate over-extraction** — the same task surfaced 2–3×
  (Amazon ×3, Sam ×2, pickup ×2). That is spam (Omar's #1 concern). See FAILURES F-012; it is the next gate.

### R-2026-06-16-D — Gate 2: duplicate-obligation collapse, proven through the REAL app
- **Gate:** 2 (one real-world obligation = one card; no duplicate spam) — driven in Chrome.
- **Stop fixed first:** the run had died on **ENOSPC** (Data volume 100% full, 1.2–1.9Gi free). Freed
  regenerable caches (ms-playwright/VSCode+Claude updaters/Xcode DerivedData/brew) → **8.3Gi free**
  (no personal files, no Trash, no source). Durable hog is Omar's Downloads(27G)/Developer(95G)/Trash(2.2G).
- **Fix:** engine-side `_consolidate_obligations` (semantic obligation signature). Commit `0320127`.
- **Receipt (visible, fresh DATA_DIR, real keystrokes):** localhost:3000 → 8-line transcript → exactly
  **4 cards**: Amazon plant (Waiting ×1), Sam deck (Waiting ×1), Pickup (Ready ×1), CRM retainer
  ("Left for you", money-parked ×1). "Still open" = 3 unique loops. **Both vents silent**; nothing
  sent/bought. Engine curl cross-check: observed_lines 5 → 4 cards, "I'll handle it"/"I'll get the deck"
  merged away.
- **Verification:** `test_owner_duplicate_collapse` PASS; suite **GREEN 91/0**; `safety_mega_eval` 0 breaches.
- **NOT done:** Sam card title is generic ("Clarify possible request"); CRM "Money's involved" reason is a
  mild misclassification (outcome is correct/safe); cross-ingest live re-submit dedup is exact-text only.

### R-2026-06-16-E — Gate Middle-1: intent-shaped memory handoff (real owner-ingest path)
- **Gate:** the hard middle — vague reference → ranked recall → right intent → prepared/parked action.
- **Code:** new `engine/anticipy_engine/proactive/intent_threads.py` (IntentThread layer: classify each
  line vent/preference/action/followup; resolve vague refs against RANKED prior threads, deterministic);
  wired into `control_core._owner_ingest_inner` (`_intent_resolve` before consolidation); `middle_trace`
  returned on `/owner/ingest` + glassbox `intent_middle_trace`. Commit `Gate Middle-1 …`.
- **Real trace** (7-line scenario via `/owner/ingest`, channels=mock, fresh DATA_DIR):
  - captured memories: pickup=action · Jarvis desk=**preference** · coffee=**vent** · "that desk thing"=action
    · lottery=**vent** · Sam deck=action · "remind me"=**followup**.
  - "that desk thing" → ranked candidates [Jarvis desk (names 'desk', 10.5), Mia pickup (0.5)] →
    **chosen: Jarvis standing desk · rejected: Mia pickup** → rewritten "put Jarvis standing desk in the cart".
  - "remind me before I send it" → **chosen: the Sam revised-deck thread** (both about sending) → merged.
  - **3 cards** (Mia pickup ask · Jarvis-desk browser confirm-first, parks before checkout · Sam deck ask);
    Jarvis preference = **no card**; coffee + lottery = **0 cards**. Nothing external fired.
- **Proof fields present:** captured_memories, ranked_candidates, chosen_referent, rejected_referents,
  formed intent (resolved task), action plan (card route/action), result (disposition/parked).
- **Verification:** `test_memory_handoff` PASS (deterministic); suite **GREEN 92/0**; `safety_mega_eval` 0 breaches.
- **Still open (honest):** cross-ingest live re-submit dedup is exact-text; card titles are plain
  (drop names); classification is deterministic-heuristic (moat model vent-guard is the safety backstop).

### R-2026-06-16-F — Release certification: autonomy modes + 10,000-run Tier-1 harness
- **Gate:** packet 02 (autonomy modes) + packet 07 (10,000 whole-product runs).
- **Code:** `proactive/autonomy.py` (6 modes per card + middle_trace.autonomy); `scripts/cert_harness.py`
  (personas×scenarios through real `owner_ingest`, hidden keys, adversarial vent distractors, independent
  judge, `DONE_CERTIFICATION_BUNDLE/`). Resolver hardened: lowercase referents + self-exclusion.
- **Receipt:** repeated 100-run openrouter batches = **0 critical** (vents silent under noise, money
  blocked, referents correct, no dup, proof present). Full 10,000-run in progress → bundle. Commits
  `07a830b`, `b0cd291`. Suite GREEN 92/0; `safety_mega_eval` 0 breaches.
- **Autonomous ceiling (honest):** Tier-1 (synthetic) is the bar reachable without Omar. Tiers 2–4
  (live API/voice, owner Mac, 5 real days) + packaged download/signing are OWNER-GATED →
  `ALL_OF_IT_IS_DONE_CERTIFIED` cannot truthfully be claimed yet (release criteria 10–17, 19).

### R-2026-06-17-G — Tier-1 10,000-run cert: 0 critical (11-type), definitive 14-type rerun in progress
- **Gate:** packet 07, Tier-1 (synthetic whole-product), criteria 15–16.
- **Receipt:** `cert_harness.py --personas 100 --scenarios 100` through the real `owner_ingest` pipeline,
  openrouter, 11 scenario types incl. wrong_account: **10,000 runs / 0 critical / 90 non-critical / 2610s**
  (`/tmp/cert_10k3.log` superseding; bundle was `DONE_CERTIFICATION_BUNDLE`). The prior run's lone critical
  (rare auto-acted-no-proof) was root-fixed by the no-self-attestation invariant → now 0 across 10k.
- **In progress:** the DEFINITIVE rerun adds follow_up + prompt_injection + retraction + per-rep person
  rotation (14 types) — the version that closes Tier-1.
- **Non-critical (90/10000 = 0.9%):** autonomy mode mismatches (over-cautious on `calendar`), tracked, safe.
- **Ceiling:** Tiers 2–4 (live API/voice, owner Mac, 5 real days) + packaged signing are OWNER-GATED.

## Imported prior receipts (from `logs/factory/*`, FOREMAN_STATE 2026-06-15/16) — RE-VERIFY before relying

These were reported proven-live by prior foreman sessions. They are imported for continuity, NOT
re-proven this session. Treat as "claimed live; re-check with a failable test before building on top."

- **Calendar API arm (Gate D, partial):** real `GoogleCalendar.CreateEvent` executed + read-back by ID
  + `DeleteEvent` (3 `[Anticipy test]` artifacts created and cleaned). Read-back is the proof, not the
  write response.
- **Reminder voice/text (Gate G, partial, supervised):** one time-due reminder delivered to Omar's
  phone — Twilio SID, status=delivered, exactly one (no flood).
- **Cardinal-sin floor (Gate C safety):** `safety_mega_eval` CORPUS 157, **BREACHES 0**, run through the
  real `/owner/ingest` split path with `execute_actions=True`. Wired into `scripts/run_suite.sh`.
- **Core messy-day slice (Gate C):** run-on vent+tasks paragraph through `/api/owner/ingest` → real tasks
  caught (incl. implied third-party), silent on the vent, money blocked. Suite green 89–90/90.
- **Onboarding scan (Gate F, partial):** `/onboard/scan_api` discovered Google Calendar connection;
  `onboard_discover` glassbox event emitted only on a real non-empty scan.
- **Premium shell (UX):** `factory/bin/check_premium_copy.py` 0 leaks; standing suite gate.
- **Browser money backstop:** `test_purchase_guard.py` — 27 money controls blocked, 24 cart/nav allowed.
- **Browser round-trip (Gate E, partial):** web task → texted ask → YES → visible browser → result text
  (commit `b82e660`).
