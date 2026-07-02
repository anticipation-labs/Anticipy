# Phase 1 — Front-End UI · Test Report

**Date:** 2026-06-28
**Build:** `devin/full-frontend-ui` @ `cedfa26`
**Engine:** real, `uvicorn` on `http://127.0.0.1:8787` (`/health` → 200)
**Method:** walked every page live in Chrome (computer-use), against the real engine. Full annotated video recorded.

## Result summary

| # | Page | Status | Evidence |
|---|------|--------|----------|
| 1 | Welcome | PASS | Branded hero, live demo card, CTA into flow |
| 2 | Sign (Supabase) | PARTIAL | Real Supabase call fires; returns honest "Email signups are disabled". Live completion = 1 provider toggle away |
| 3–10 | Onboarding (basics + hidden machine steps) | PASS | Auto-advance through hidden steps, SOON pill on live-scrape |
| 4 | Onboarding "About you" form | PASS | POST `/owner/onboard` succeeded |
| 11 | Great (fact mirror) | PASS | Mirrored every saved fact back |
| 12 | Done (hand-off) | PASS | Clarification saved, CTA to product |
| 13 | Upload / MP3 | PASS | Transcript → POST `/owner/ingest` → caught real tasks, filtered venting; MP3 transcribe = SOON |
| 14 | Tasks board | PARTIAL | Real cards render w/ provenance + autonomy dial. Accept action fails honestly (confirm→act endpoint = Phase 5) |
| 15 | Settings | PASS | Autonomy → `full_send` persisted to engine; Gmail permission live; memory + text-mirror = SOON |

**Two honest gaps (not faked):**
1. **Live Supabase auth** — the project has the Email provider OFF. The page is genuinely wired to the live project (real call returns the real server error). No management/personal-access token (`sbp_`) is on disk, so I can't flip it from here — needs the dashboard toggle or an `sbp_` token.
2. **Card Accept** — the confirm→act path returns an honest "couldn't lock that in" rather than a fake success. Wiring the action endpoint (confirm → browser acts → proof) is Phase 5.

## Evidence

### 1. Welcome (page 1)
![Welcome](/home/ubuntu/screenshots/ss_2ba47b2a.png)

### 2. Sign — real Supabase, honest provider-disabled error (page 2)
![Sign](/home/ubuntu/screenshots/ss_7b0467b6.png)

### 4. Onboarding "About you" form, filled (page 4)
![Onboarding form](/home/ubuntu/screenshots/ss_9ecc20fc.png)

### 11. Great — facts mirrored back from engine (page 11)
![Great](/home/ubuntu/screenshots/ss_5b90eede.png)

### 12. Done — hand-off (page 12)
![Done](/home/ubuntu/screenshots/ss_6ef14a6c.png)

### 13. Upload — transcript ingested, 2 real cards, venting filtered (page 13)
![Upload result](/home/ubuntu/screenshots/ss_8be72393.png)

### 14. Tasks board — real cards w/ provenance + autonomy dial (page 14)
![Tasks](/home/ubuntu/screenshots/ss_f14c67ec.png)

### 15. Settings — autonomy Full-Send + permissions (page 15)
![Settings](/home/ubuntu/screenshots/ss_53d073a6.png)

### 15b. Coming-soon strategy — SOON pills + blocking toast
![Coming soon](/home/ubuntu/screenshots/ss_596da7d2.png)

## Engine verification (not just UI)
- `GET /health` → 200
- `POST /owner/onboard` → profile saved (mirrored on "Great" page)
- `POST /owner/ingest` → `{cards: [...], ignored_line_count}` — real task/vent separation
- `GET /owner/autonomy_mode` → `{"mode":"full_send",...}` after toggle (persisted)
