# FIX-02 — The orphans: wire the digest, give anticipate.py a real caller
<!-- status: IN-PROGRESS | milestone: — | created: 2026-07-02 | updated: 2026-07-02 -->

## Why (2–3 sentences, no jargon)
Two real capabilities existed with no way to ever run: the daily digest queue filled forever but
nothing ever delivered it, and the person-research module (anticipate.py) was reachable only through
an endpoint no screen calls. This fix wires both into the living product.

## Human check (how Omar verifies without a terminal)
Ask me to "send my digest now" — you get one calm message bundling the day's non-urgent items, or an
honest "quiet day, nothing to send." Nothing new appears twice.

## Step 0 — Preconditions  [x]
**Baseline (2026-07-02, post FIX-01 Phase 2):** suite 110/10 byte-identical set · wiring CLEAN
(64 endpoints / 45 routes / 93 modules, 37 TODO-debt) · HEAD `51b96a4`.
**WIRING PROOF:** pasted above.

## Step 1 — Wire deliver_digest (endpoint + daily scheduler + app proxy)  [x]
**What I did:** `POST /digest/deliver` (calls the proven NF10 deliver_digest); a daily check in the
tick scheduler gated by `ANTICIPY_DIGEST_HOUR` (unset = OFF, zero suite impact; owner-timezone aware;
durable `digest_last.json` stamp, mark-before-send so a crash can't double-deliver);
`app/api/digest/route.js` proxy (UI button = FIX-14 debt line, recorded in the allowlist).
**Proof commands + outputs (2026-07-02):**
- quiet day via endpoint: `curl -X POST :8792/digest/deliver` → `{"sent":false,"count":0,"reason":"quiet day"}`
- deferred item + scheduler call (in-process, hour=0): stamp `{'date': '2026-07-02'}` written; mock
  channel received exactly ONE digest text; second same-day call → no-op (`fire-once holds: True`).
- queue mechanics remain pinned by the suite's `test_digest` (green).
**Rollback:** `git revert` this commit; env stays unset by default.
**WIRING PROOF:** pasted above (2026-07-02).

## Step 2 — anticipate.py gets its real caller  [ ]
**What happens:** `proactive/world_research.py` (FIX-07, in flight) calls `research_person` as its
person-resolution arm — the orphan becomes a live component of true proactivity. The `/anticipate/research`
endpoint + route keep their TODO(FIX-02) debt line until a UI "Who is this?" action lands (FIX-07/5.7).
**WIRING PROOF:** (pending — lands with FIX-07)

## Final step — The gates + commit  [~]
**WIRING PROOF:** (suite running)
