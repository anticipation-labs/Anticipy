# THE MERGE — the one wire that makes the system act on its own (gate G12)

**Status:** RED (proven). The engine shapes a `do/browser` card from a messy day but never executes it.

**Exact gap:** `engine/anticipy_engine/core/control_core.py` → `_owner_ingest_inner`. A shaped
`disposition="do", route="browser"` card (e.g. action `research_or_find_item`) falls through to the
spine-decision path (~1429–1460): it sets `card.execution` to the verdict but does NOT fire the browser.

**The seam already exists and is proven:** `_run_browser_and_confirm(task, url, card_id)` (control_core.py:1187)
— the opt-out path already calls it correctly at 1130–1136 (async, texts before+after, lands a `browser_receipt`).

**The fix (single additive hook):** when a finalized card is `do` + `browser` + has a concrete `task_text`
+ `browser_hand.mode == MODE_LIVE`, fire `_run_browser_and_confirm(task, self._web_start_url(task), card_id)`
async and set `execution.goal_state="running"` — mirroring 1130–1136. Guard: never for vents (already
filtered), never for `blocked`/money cards, never double-fire (dedupe on card_id like the opt-out pending).

**Verify:** `python3 overnight/harness.py` — G12 turns PROVEN when `/owner/ingest "look up Vancouver weather"`
lands a `browser_receipt` on the card with no agent touching anything. The public weather task needs no login,
so G12 is fully verifiable autonomously. (Operating the user's *logged-in* systems is the same wire pointed at
logged-in doors — that's gated on login, not on this code.)

**Why not done unattended:** core ingest path; a misfire (acting on the wrong card class) is exactly the
cardinal-sin risk. Close it with the harness watching and revert-on-red.
