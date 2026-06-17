# RABBIT_HOLE_EXIT — hard-middle only (2026-06-16)

Scope: MESSY INPUT → RIGHT MEMORY → RIGHT INTENT → RIGHT PREPARED ACTION → PARKED/READ-BACK RECEIPT.
Nothing else.

## 1. Is Claude blocked, halted, or running?
Actively running — this foreman session, working the single memory-handoff gate. Not blocked.

## 2. Is the engine running?
Yes — one instance on `127.0.0.1:8787`, restarted by me in SAFE mode for the gate test
(`DATA_DIR=/tmp/anticipy_g3`). No mic, no Next dev server unless I start it for the UI proof.

## 3. Live channels on or mock?
**Mock.** `.env.local`: `ANTICIPY_CHANNELS_MODE=mock`, `ANTICIPY_INBOUND_POLL_SECONDS=0`, no mic var.
No live SMS/call/mic path can run. `/status` shows `channels.mode=mock`.

## 4. Current git HEAD
`9316fe4` (branch `factory/build`, pushed to origin). Factory loop halted (`factory/.halt` present, no `.lock`).

## 5. Committed vs dirty
Clean working tree at the time of writing (the gate fix below will be the next dirty set → committed
only with a passing receipt).

## 6. Hard-middle failures still REAL (verified this session on the live engine path)
- **F-A (the gate): vague-reference handoff is broken.** 5-line scenario, line 4 "Can you put that desk
  thing in the cart?" → card kept the vague text "that desk thing" UNRESOLVED, url google.com. It did
  NOT resolve to "Jarvis standing desk". (It did not recall Mia pickup either this run — it resolved to
  *nothing*; the log's "kid pickup" mis-recall is the same root: no reliable referent resolution.)
- **F-B: context/preference line over-caught.** "The Jarvis standing desk is the one I liked. Don't buy
  it yet." became a browser ask. It is an inert preference/context statement, not a task.
- **F-C: the model context-resolution (cheap tier) is unreliable** for references; the engine has no
  deterministic referent disambiguation, so "that X thing" is left vague or mis-resolved.
- NOT failing now: both vents (coffee→woods, lottery→island) are SILENT (zero cards). Money/checkout
  is parked. Those hold.

## 7. Exact test that will prove the next fix
Deterministic unit `engine/scripts/test_memory_handoff.py` + the live 5-line scenario:
- "that desk thing" RESOLVES to "Jarvis standing desk" (card task names the desk, not the vague text,
  not Mia pickup).
- proof emits: memory candidates, CHOSEN referent, REJECTED referents, intent, action decision, receipt/blocker.
- parks before checkout/payment; coffee-woods → 0 cards; lottery → 0 cards.
- `safety_mega_eval` stays 0 breaches; suite stays GREEN.

## 8. What I refuse to work on (this pass)
Twilio / SMS / calls / mic / voice; loop metrics / suite bragging; product copy / styling / deploy
polish; broad research; workflows; spawning agent fleets; editing tests to accept wrong recall;
scoreboards / persona banks; the factory loop (kept halted).
