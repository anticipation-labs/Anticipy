# FIX-04 — The trust dial becomes real
<!-- status: DONE | milestone: — | created: 2026-07-02 | updated: 2026-07-02 -->

## Why (2–3 sentences, no jargon)
The Autonomy dropdown in Settings wrote to a local display file — the engine's REAL gate
(`/owner/autonomy_mode`, the thing that decides act-vs-ask) never heard about it. Flipping to
Limited did literally nothing. Now the dropdown reads and writes the real gate.

## Human check
Open Settings, flip Autonomy to Full-Send, reload the app — it still says Full-Send (read back
from the engine, not the local file).

## Step 1 — Proxy + two-way sync  [x]
**What:** new `app/api/owner/autonomy/route.js` (GET/POST → engine `/owner/autonomy_mode`);
SettingsScreen reads the real mode on mount and POSTs on change (Limited↔limited,
Regular↔regular, Full-Send↔full_send); local label kept for display. Burned the 2 TODO(FIX-04)
allowlist lines.
**WIRING PROOF (2026-07-02, through the app proxy with the owner cookie):**
GET → `{"mode":"limited",...}` (the real gate) · POST `{"mode":"full_send"}` → engine gate reads
`{"mode":"full_send",...}` · reset to regular verified. Wiring gate CLEAN after burn.

## Final step — gates  [x]
**WIRING PROOF (2026-07-02):** suite `111 passed, 10 failed` byte-identical (run below, shared
with FIX-06); `WIRING: CLEAN (66 endpoints / 48 routes / 95 modules, 43 allowlisted incl. 37 TODO-debt)`.
