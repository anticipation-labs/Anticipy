# Annie: memory, orchestration, voice — proof report

Date: 2026-07-20

## What was built

- `brain/memory.py` — temporal knowledge graph on SQLite (not a JSON file, not RAG):
  episodes → extracted entities (people/places/topics) and commitments as graph
  nodes, typed timestamped edges (`committed_to`, `involves`, `about`).
  Recall = 2-hop graph walk from the entities in the query, returned as a
  newest-first linear chain of facts with the original quote as provenance.
  Commitments carry an open/done/cancelled lifecycle — Annie's to-do list.
- `brain/annie.py` — Annie, the single responsible orchestrator + personality:
  hear → remember → decide (memory-augmented triage) → delegate (action arm =
  browser job queue; voice arm = Twilio) → track every open loop to done →
  first-person briefing ("How goes it today? … I'm handling …").
- `brain/voice_arm.py` — Twilio SMS + real voice calls (spoken TwiML).
- iOS: Annie briefing card on the home feed; onboarding introduces her by name.

## Evidence (labels honest)

| Piece | Status |
|---|---|
| Memory graph ingest/recall/loops | PASSED — `proof/test_memory.py` (4/4) |
| Annie orchestration offline | PASSED — `proof/test_annie.py` (4/4) |
| Live spine vs real PocketBase | PASSED — `proof/test_annie_live.py`: commitment → job held `awaiting_confirm` → in-app confirm PATCH released it → agent done → Annie closed the loop and resolved the memory commitment |
| Voice arm | LIVE-AUTHENTICATED — Twilio account "Anticipy" active, number +16196584447 owned; outbound text/call methods ready. Real text/call to the owner still needs their confirmed number |
| LLM-driven triage/extraction/briefing | IMPLEMENTED, not live-run this session (OpenRouter key not on the box — previous key was chat-exposed and must be rotated anyway) |
| iOS integration | WRITTEN, not compiled (needs Mac tunnel) |

## Run log

```
proof/test_memory.py   PASS x4
proof/test_annie.py    PASS x4
proof/test_annie_live.py
  PASS held for confirmation: job awaiting_confirm
  PASS in-app confirm released the job (awaiting_confirm -> queued)
  PASS loop closed and memory commitment resolved
  Briefing: "How goes it today? I'm Annie. I overheard 1 thing worth
  remembering. Nothing needs you right now — go live your day."
```
