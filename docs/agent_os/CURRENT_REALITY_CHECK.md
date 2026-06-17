# CURRENT REALITY CHECK — what is actually real (2026-06-16)

Answers verified by inspection/curl this session, not assumed. Companion to `CURRENT_TRUTH.md`.

| # | Question | Answer (verified) |
|---|---|---|
| 1 | **What app does Omar open/test?** | The Next.js web app at **http://localhost:3000** (premium reskin: charcoal/cream/DM Serif). Running now (HTTP 200). Also a packaged macapp "Anticipy Execute" runs (launchctl) but its build/download path is unverified. |
| 2 | **Which repo builds that app?** | `~/Anticipy` (`omize10/Anticipy-executor-working`, branch `factory/build`). `app/` = Next.js front; `next dev` serves :3000. |
| 3 | **Which engine does it call?** | The Python engine at **http://127.0.0.1:8787** (`engine/anticipy_engine`, uvicorn). Wiring: `app/api/_engine.js` → `ENGINE_URL` default `http://127.0.0.1:8787`. Running now (HTTP 200). |
| 4 | **Transcript input route** | UI capture box → `POST /api/owner/ingest` → engine `/owner/ingest` (`execute_actions` defaults true on the real path). |
| 5 | **Listening/mic input** | Same brain via `/api/owner/ingest`; MP3/file via `POST /api/owner/upload`. (Live mic device = future; transcript/MP3 are the doors today.) |
| 6 | **Execute actions route** | `/api/owner/ingest` with `execute_actions=true`; approvals via `/api/resolve`. |
| 7 | **Receipts route** | `GET /api/owner/cards` (durable cards + proof) and `GET /api/pending` (parked asks). |
| 8 | **Public site / deploy** | `~/Developer/Anticipy-DEV-FINAL` (`omize10/Anticipy` → anticipy.ai). **Omar-owned, separate, hands-off** (uncommitted work). The localhost app is NOT yet deployed off-localhost. |
| 9 | **Local app/download currently real** | macapp "Anticipy Execute" process runs; `app/api/download` route exists. Packaging→download→open path NOT yet end-to-end verified (Gate 8). |
| 10 | **Mock vs stub vs partial vs live** | **LIVE:** brain/model (OpenRouter, `gemini-2.5-flash[-lite]`), API arm (real Google Calendar create+read-back+delete proven), engine on :8787 (`channels=live`, Twilio configured). **MEMORY-GROUNDED + verified in stub/mock:** browser arm auto-cart (throwaway browser, money-guarded). **NOT live-proven:** real-site browser auto-cart; inbound-text round-trip; off-localhost; the 5 owner days. **Tests:** stub/mock tier, suite GREEN 90/0. |

## Auth state
- Localhost :3000 is **open** (no `ANTICIPY_APP_OWNER_TOKEN` set → `/api/status` 200, no unlock needed).
  A public deploy WOULD require the owner token (default-deny), so off-localhost exposes accounts → Omar's call.

## Self-attestation audit (receipt floor)
- **Clean.** `engine/.../hands/api_hand.py`: "the write echo is never proof" — issues a SECOND independent
  read of the artifact; if the read does not re-observe it → NOT done. Browser arm cross-checks
  (`browser_use_link.py`). Cards carry `memory_read_back` / `browser_receipt` / `engine_execution` proofs.
- No action arm treats the actor's own response as proof. Calendar create proven by independent read-back.

## OpenRouter
- `provider=openrouter`, base url `https://openrouter.ai/api/v1/chat/completions`, models
  `gemini-2.5-flash-lite` (cheap) / `gemini-2.5-flash` (smart). Live model call confirmed (reality_check
  "messy speech → cards LIVE" is a real OpenRouter round-trip). Not assumed from config.

## Loops
- `factory/.halt` present (nightly factory loop paused), no `factory/.lock`. No anticipy crontab. A stray
  second uvicorn on :8797 (harmless leftover; main is :8787).
