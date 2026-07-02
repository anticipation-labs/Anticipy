> ⚠️ **SUPERSEDED — 2026-07-02.** Historical document. The living truth is **`CANON/00_START_HERE.md`**
> (+ `MISSION_LOCK.md` for live mission status). Do not follow this file's read-order, done-definition,
> or status claims. Indexed with context in `CANON/99_SUPERSEDED_INDEX.md`.

# THE PLAN — THE WHOLE PRODUCT WORKS, END TO END, THROUGH THE FRONT END

> Omar, repeatedly: stop testing pieces. "Everything needs to work — the front end, the browser agent,
> the scrape." The unit of success is the WHOLE PRODUCT a person opens and uses — NOT a micro draft or a
> curl. The toilet to flush is the ENTIRE JOURNEY, walked through the real UI, with no seams.

## THE ONE TEST (the only thing that counts as done)
Open the front end cold → onboard (the scrape learns you from your real accounts) → it shows it knows you
→ give it a real day → it produces the right cards → the BROWSER AGENT actually does the doable ones in
your real systems → results come back INTO the front end → money/sends asked, vents silent — **all as ONE
seamless product, walked through the UI, no curl, no babysitting.** (§4.1 / §4.2.)

## WHERE WE ARE (honest)
- Components proven in ISOLATION: brain decides ✅, hands operate/read/research/draft ✅ (draft flushed
  via compose-URL), onboarding scrape → memory ✅, per-user ✅. 
- **NEVER proven: the whole product walked through the FRONT END as one experience.** The front end
  (web app) has not been driven end-to-end this whole time. That is THE gap.

## THE PILLARS THAT MUST ALL WORK TOGETHER (through the UI)
1. **FRONT END** (the web app the engine serves at :8787 / the deployed app) — loads, onboard flow,
   shows cards, lets you act, shows results. No jank, no dead ends.
2. **SCRAPE / ONBOARDING** — from the UI, it connects + learns you from your real accounts.
3. **BROWSER AGENT** — from a card in the UI, it actually operates the real system and the result lands
   back in the UI.

## THE METHOD (drive the real UI, fix the real seam)
WALK the journey in the actual front end (Chrome on the served app). At the FIRST step that breaks or
feels like a seam, fix THAT (product/integration level — not micro-plumbing; suite stays 109/0, REVERT
regressions). Re-walk from the top. A step "works" only when seen working IN the UI (read the screen
back, never a claim).

## GATE (done)
The full journey — open → onboard → day → cards → agent acts → result in UI — walked clean end-to-end,
**twice**, through the front end, suite 109/0. Then Omar's real days/cloud are the final §4 stamp.

## LOOP
Every 3 min: open the front end, walk to the lowest broken step, fix the seam, re-walk, commit, log the
screen-evidence in LEDGER. Never test a piece in isolation and call it done — only the whole journey counts.
