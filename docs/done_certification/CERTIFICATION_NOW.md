# CERTIFICATION_NOW — release-certification working state

_Started 2026-06-16 (autonomous). Packet: `docs/done_certification/PACKET.md`._

## Repo / runtime
- Repo: `~/Anticipy` (`omize10/Anticipy-executor-working`), branch `factory/build`, HEAD `6ea7fd3`+.
- App path: Next.js at `http://localhost:3000` (`npm run dev` in repo) → engine.
- Engine: `engine/.venv/bin/python -m uvicorn --app-dir engine anticipy_engine.main:app --port 8787`.
  Started SAFE: `ANTICIPY_CHANNELS_MODE=mock`, `ANTICIPY_INBOUND_POLL_SECONDS=0`.
- Unified ingest path (the one the app POSTs to + the harness drives): `POST /owner/ingest` (execute=true).

## Subsystem state (verified this/prior sessions)
- Memory/intent: intent-thread layer (`proactive/intent_threads.py`) — classify + ranked vague-ref
  resolution; "that desk thing"→Jarvis, "send it"→Sam deck PROVEN. middle_trace = the per-line proof.
- Dedup: `_consolidate_obligations` — one obligation = one card. PROVEN.
- Safety floor: `safety_mega_eval` 0 breaches (vent→no act, money hard stop). Suite GREEN 92/0.
- API arm: Calendar create+read-back+delete proven LIVE earlier. Gmail NOT connected.
- Browser arm: confirm-first round-trip + resolved auto-cart (throwaway browser, money-guarded).
- Voice/text: one reminder texted earlier; OFF now (mock). Inbound round-trip unproven.

## Certification gates (this run builds Tier 1; Tiers 2–4 owner-gated)
- **Autonomy modes (NEW, packet §02):** label every obligation AUTO_DO / AUTO_DO_WITH_OPT_OUT /
  PREPARE_THEN_STOP / CLARIFY_FIRST / REMEMBER_ONLY / IGNORE + classification proof. → building.
- **Tier 1 — 10,000 synthetic whole-product runs** through `/owner/ingest` with hidden keys + judges.
  → building (`engine/scripts/cert_harness.py`, bundle → `DONE_CERTIFICATION_BUNDLE/`).
- **Tier 2 (controlled live)** / **Tier 3 (owner Mac live)** / **Tier 4 (5 real days)** — OWNER-GATED.
- **Download/packaged app** — Mac signing = Apple creds (OWNER-GATED); unsigned dev fallback for local.

## Current blockers (owner / physical — Omar away)
- Live Gmail/Calendar unattended writes, live Twilio number, app signing/download, the 5 real days.
  These cannot be done autonomously; tracked for `HUMAN_CLICK_REQUIRED` at the autonomous ceiling.

## Progress (autonomous)
- **Autonomy modes (packet 02): DONE.** `proactive/autonomy.py` labels every card AUTO_DO /
  AUTO_DO_WITH_OPT_OUT / PREPARE_THEN_STOP / CLARIFY_FIRST / REMEMBER_ONLY / IGNORE; carried on each
  card + in `middle_trace.autonomy`.
- **Tier-1 harness (packet 07): BUILT + GREEN at batch scale.** `engine/scripts/cert_harness.py` —
  templated personas across 10 domains + hidden answer keys + adversarial vent distractor on every
  scenario, run through the REAL `ControlCore.owner_ingest` pipeline, independent judge. 100-run
  openrouter batches = **0 critical** (after fixing referent self-exclusion + lowercase-referent
  resolution). Full **10,000-run** in progress → `DONE_CERTIFICATION_BUNDLE/`.
- Suite GREEN 92/0; `safety_mega_eval` 0 breaches.

### 2026-06-17 — dedup hardening + Tier-1 blocked by model throttle (NOT logic)
- **Dedup F-012 hardened (commit `4d1aa2d`, pushed):** the lone critical in the healthy-brain
  2500-run diagnostic was duplicate spam — the moat rewords a confirmation ("yeah, I'll handle it")
  into a synonym of the original ("call Amazon about the monitor" → "handle the Amazon monitor
  issue"); sigs `{amazon,call,monitor}` vs `{amazon,issue,monitor}` differ only by an interchangeable
  comm verb / filler noun, so containment-merge missed them. `_same_obligation` now ALSO merges on
  equal identity-core (salient entity+object after stripping generic comm verbs/filler nouns).
  Verified: 0/30 live dup (was ~3/25), unit checks pass, suite GREEN 92/0, safety 0 breaches.
- **Tier-1 10k is CAPACITY-BLOCKED, not logic-blocked.** The post-fix definitive 14-type rerun ran
  at **0.3/s with ~12% critical** vs the healthy diagnostic's **5.9/s with 1 critical**. Root cause:
  the OpenRouter brain is throttled — a single standalone ingest measured **15–53s/call** (≈10–25×
  normal) and latency *climbed* through the run. Under throttle the moat returns degraded/empty
  judgments and DROPS real tasks → the criticals are all "obligation dropped" (a concurrency-1
  per-type probe confirmed: 12/14 ok, `mixed` + `calendar` dropped — no crashes/429 exceptions).
  This is the documented "starved brain" blocker; funding/unthrottling the model is owner-gated.
  **Plan:** back off (every call deepens the throttle), let it recover, relaunch the clean 10k when
  a single ingest is back under ~3s. The dedup fix means a healthy-brain 10k should be 0 critical.

## Verified (autonomous) — release criteria status
- **Inputs same-brain (criteria 5–7, packet 05): VERIFIED.** All three routes call `core.owner_ingest`:
  typed transcript (`main.py:722`), MP3/audio upload (transcribe → `owner_ingest`, `main.py:774`),
  always-on mic/listening (`_sink → owner_ingest(execute=True)`, `main.py:792`). Covered by suite
  `owner_upload_ingest` + `mac_mic`. No route bypasses memory/intent/action.
- **Autonomy modes (criterion 9): VERIFIED** (6 modes + full classification proof).
- **Memory/intent vague refs (criterion 8): VERIFIED** (intent-thread layer; R-2026-06-16-E).
- **Follow-up (criterion 14): VERIFIED** (plan_follow_up; external-dependency obligations).
- **No-self-attestation (proof floor): VERIFIED** (act-without-proof → downgrade).
- **10,000-run Tier-1 (criteria 15–16): IN PROGRESS** — definitive 12-type rerun pending.

## Autonomous ceiling — what genuinely needs Omar (HUMAN_CLICK_REQUIRED at the end)
Tier-1 (synthetic whole-product, 10,000 runs) is the autonomous bar. These CANNOT be done without Omar:
- **Tier 2 (controlled live):** live Gmail/Calendar writes + a live Twilio test number (the 31-text
  history forbids unattended sends). Needs auth taps + an approved number.
- **Tier 3 (owner Mac live):** runs on Omar's real accounts/Chrome/phone with approvals.
- **Tier 4 (five real days):** cannot be compressed — lived use.
- **Download/packaged app:** Mac signing/notarization = Apple Developer creds (or accept unsigned dev).
- Until these, `ALL_OF_IT_IS_DONE_CERTIFIED` cannot truthfully be said (release criteria 10–17, 19).
