# FIX-03 — "Go deeper" runs the REAL deep read
<!-- status: DONE (wire; live proof needs L1) | milestone: M5 | created: 2026-07-02 | updated: 2026-07-02 -->

## Why (2–3 sentences, no jargon)
The genuine 4-layer scroll+read loop existed in the engine with NO app route at all — the UI's
"Go deeper" button called only a shallow extension snapshot. This was the exact "plumbed
separately" disease: the deep scrape Omar kept asking about was built and unreachable.

## Human check
In onboarding, press "Go deeper" WITHOUT the special Chrome running: you get the honest truth
("no account was readable yet" / the quick-read fallback note) — never a fake success. With the
real Chrome (L1), the same button runs the full layered read and says what it read and where it
expanded.

## Step 1 — the proxy + the button  [x]
**What:** new `app/api/onboard/loop/route.js` (maxDuration 320 — the loop budgets 300s);
`AccountReadStage.runScan(deep)` tries `/api/onboard/loop` FIRST and falls back to the shallow
deep-scan with the honest reason when the loop can't run. Result message says what was read
("read N places across M passes") and where it expanded ("followed your world into notion.so").
Burned the `/onboard/loop` allowlist line; `owner-scrape` + `deep-read-hand` retagged TODO(FIX-10).
**WIRING PROOF (2026-07-02, through the app proxy with the owner cookie):** POST `/api/onboard/loop`
(gmail allowed, no CDP Chrome) → `{"ok":true,"layers":[{"layer":1,"scraped":[],"needs_login":[],
"gaps":["everything — no account was readable yet"],"confidence":0,...}]}` — the REAL loop, reached
from the app, honestly reporting nothing readable. Zero fakery.

## Remaining
- [ ] L1 live proof: Omar's logged-in Chrome with CDP — the full layered read + expansion + dossier
  on the memory screen, watched live.
