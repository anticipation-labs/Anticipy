# FIX-06 — "Waiting for your yes": the pending asks finally have a room
<!-- status: DONE | milestone: — | created: 2026-07-02 | updated: 2026-07-02 -->

## Why (2–3 sentences, no jargon)
The app could RESOLVE an ask but never LISTED them — paused asks were invisible until something
else happened to surface one. Now the board shows every ask waiting on you, each with one gold
"Yes, go ahead" and a quiet "Not this one".

## Human check
Type "email Sarah the budget tonight" into the app. A "Waiting for your yes" panel appears on the
board with that ask and its honest reason; tap "Not this one" and it disappears.

## Step 1 — loadPending + panel + resolve loop  [x]
**What:** `loadPending()` (fetch `/api/pending`) joined the board's data loaders; new
`PendingAsksPanel` renders on the board (humanTitle-scrubbed, styled); Approve/Deny → existing
`/api/resolve` → reload. Burned the TODO(FIX-06) allowlist line.
**WIRING PROOF (2026-07-02):** through the app proxy: ingest "email Sarah the updated budget
tonight" → `/api/pending` lists it (reason: "send to a real person; memory low-confidence on
recipient then fail-safe ask") → resolve → list shrinks. VISUAL: screenshot on :3100 board shows
the panel with gold confirm buttons on every ask.

## Honest discovery along the way
`/api/owner/stop` (the STOP control for in-flight cards) has an engine route (fixed earlier today)
but the BUTTON was never rendered anywhere — recorded as explicit debt `TODO(FIX-06b)` in the
allowlist rather than silently re-hidden.

## Final step — gates  [x]
**WIRING PROOF (2026-07-02):** suite `111 passed, 10 failed` byte-identical; wiring gate CLEAN,
debt 39→37 net.
