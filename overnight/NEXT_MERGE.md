# THE MERGE — corrected diagnosis (gate G12)

**My first framing was WRONG and I'm correcting it:** I said the engine should AUTO-execute browser
tasks. That would break the confirm-first safety model (acting without a YES). The engine is *designed*
confirm-first: ingest → texted/app ask → **YES** → `_run_browser_and_confirm` runs the browser → receipt.
That design is correct. Do NOT auto-execute browser actions.

**What actually works:** cart/shopping tasks register as approvable asks. Proof: ingest "put the water
table in the cart" → a pending ask appears (`/pending`, category `browser`) → `/resolve {ask_id, approved:true}`
fires the browser. The find_or_cart path calls `_browser_action_ask` (control_core.py ~1426), which registers
`proactive.pending[ask_id]` with `browser_task`/`browser_url`. The resolve handler (~3168-3182) runs it on YES.

**The real, narrow gap:** general LOOKUP/admin tasks shaped as `action="research_or_find_item"`
(owner_mode.py:555) are returned as a `do/browser` card that is **never registered as a browser ask** — so
they are a dead end: not auto-run (correct), but also not approvable (bug). Verified: ingest "look up the
Vancouver Art Gallery hours" → card `disposition=do, action=research_or_find_item`, NOT in `/pending`,
`/resolve` → "unknown ask".

**The fix (confirm-first, safe, mirrors the working cart path):** in control_core `_owner_ingest_inner`
(the do/browser branch ~2106-2118, or in `_spine_card` for research_or_find_item), route general
`research_or_find_item` cards through `self._browser_action_ask(line, source)` exactly like cart tasks —
so they register an approvable pending ask. Then ingest → approve (app button / SMS YES) → browser runs →
`browser_receipt` on the card. No new execution path; reuse the proven one.

**Verify (G12):** ingest a FRESH lookup task → assert it appears in `/pending` as an approvable ask →
`/resolve approved:true` → poll the card for `goal_state=running/done` + `browser_receipt`. Public task,
no login, fully autonomous to verify. (Operating the user's *logged-in* systems = same path at logged-in
doors; gated on login, not this.)

**Why I didn't hand-patch it live:** core ingest path on a running engine, and the first framing was wrong —
exactly why blind unattended hacking is the rabbit hole. Close it with the harness watching, revert-on-red.
