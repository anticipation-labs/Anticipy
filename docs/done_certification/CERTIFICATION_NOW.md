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

## Next certification gate
Build autonomy-mode classifier → build Tier-1 harness → run batch → drive critical failures to 0 →
scale toward 10,000 → assemble bundle.
