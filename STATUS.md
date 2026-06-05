# STATUS — overnight run (technical log; WAKEUP.md is the morning report)

Branch `overnight/real-progress` off green main `4e523c2`. Started overnight, person asleep.
This file = ground truth + every real artifact id, written as it happens. No claim here is trusted
unless a checker that reads reality confirmed it.

## GROUND TRUTH (tested live, not remembered)

**Engine-relevant keys present in `.env.local` (names only):**
`ARCADE_API_KEY`, `ARCADE_USER_ID`, `OPENROUTER_API_KEY`, `ANTICIPY_MODEL_PROVIDER`,
`ANTICIPY_MODEL_CHEAP`, `ANTICIPY_MODEL_SMART`, `ANTICIPY_HANDS_MODE`.

**Real action path:** Arcade (`arcadepy` 1.10.0) via `engine/anticipy_engine/hands/api_hand.py`.
Arcade user = `omarkebrahim@gmail.com`.

**Arcade authorization RIGHT NOW (tested via `client.tools.authorize`, no execute):**
| Tool | Status | Meaning |
|---|---|---|
| `GoogleCalendar.CreateEvent` | **completed** | ✅ can create real events |
| `GoogleCalendar.ListEvents` | **completed** | ✅ can read calendar (the judge's eyes) |
| `GoogleCalendar.DeleteEvent` | **completed** | ✅ can clean up test events |
| `Gmail.WriteDraftEmail` | **pending** | ❌ needs one human tap (scope `gmail.compose`) |
| `Gmail.ListDraftEmails` | **pending** | ❌ same scope, needs the tap |

> NOTE: this is the OPPOSITE of what memory implied. Wave-2 proved `Gmail.SendEmail` (scope
> `gmail.send`), but the DRAFT tools need `gmail.compose`, which is NOT yet granted. Meanwhile
> Calendar got authorized (the connect URL from the prior session was tapped). Tested, not assumed.

**Discovered real tool schemas (so we use real field names, not guesses):**
- `GoogleCalendar.CreateEvent(summary*, start_datetime*, end_datetime*, calendar_id, description,
  location, attendee_emails, ...)`  (* required)
- `GoogleCalendar.ListEvents(...)`, `GoogleCalendar.DeleteEvent(event_id*)`
- `Gmail.WriteDraftEmail(subject*, body*, recipient*, cc, bcc, content_type)`

## NIGHT PLAN (follows the authorization reality)
- **Track A = REAL CALENDAR plumbing** (authorized, un-fakeable). Fresh hold-request each lap →
  real event via Arcade → SEPARATE judge confirms it via `ListEvents` reading the real calendar →
  cleanup. Self-prove the judge with a planted fake first.
- **Gmail drafts = HANDED OFF** (one tap). Connect URL is in WAKEUP.md. The draft worker+judge are
  built and ready but UNVERIFIED until the tap.
- **Track B = judgment decider** (no accounts needed) — build + grade honestly + drive false-action→0.
- **Track C = honest unverified code** — marked NOT VERIFIED.

## TRACK A — REAL CALENDAR PLUMBING ✅ PROVEN (un-fakeable)

Architecture (LAW #3 separation): `overnight/track_a/generate_request.py` (fresh ask each lap) →
`worker.py` (cheap model parses the ask → real event via the engine's `ApiHand`→Arcade) →
`judge.py` (independently reads the real calendar via `ListEvents`, confirms by real event id).
Worker and judge import 0 of each other (verified). Judge **self-proved** each run: planted real →
PASS, planted fake id → FAIL ("caught the fake").

**Result: 12/12 fresh laps passed, all 12 DISTINCT requests** (not one task × 12). Each created a
REAL Google Calendar event, each independently confirmed present in the real calendar by the judge.
No attendees, no notifications — private holds, nothing reached a third party. 3 kept visible as
morning proof, 9 cleaned up.

**Real artifacts you can verify yourself (kept, labeled `[Anticipy test]`):**
- `gfjnrtgtsndpa86r8do543a4pc` — "focus time", 10am this Wednesday
- `itnnlirt7qhg8qan6bre9f5gs4` — "1:1 with Alex", 3pm this Saturday
- `cbb19pittvli1cc77iagmfoopg` — half-hour hold, day after tomorrow
(full per-lap log: `overnight/track_a/results.json`.)

**Real bug found + fixed (general, not a Track-A hack):** all laps first failed "no id in tool
output" — `ApiHand._proof_from` (`engine/anticipy_engine/hands/api_hand.py`) only read a top-level
`id`, but `GoogleCalendar.CreateEvent` nests it under `{event:{id}}` (and Gmail drafts under
`{draft:{id}}`). Fixed to look one level into wrapper dicts. Suite still 29/29; `Gmail.SendEmail`
(top-level id) unaffected. This bug had been silently masking real calendar creates as failures.

## REAL ARTIFACTS LOG (continued below as tracks run)

## TRACK B — THE JUDGMENT DECIDER (built + graded honestly; cardinal gate MET)

Architecture (LAW #3 + #4): `overnight/track_b/answer_key.jsonl` (60 lines: 19 ACT / 11 ASK /
30 SILENT, 19 held-out, 8 near-the-line) is human-rule ground truth the decider never sees.
`decider.py` (cheap model, principled prompt, NO key lines, biased to SILENT when unsure) →
`score_decider.py` (separate; self-proves it counts a planted false-action, then grades). Decider
imports 0 of the scorer/key.

**Numbers (one temp-0 run; PROVISIONAL until you red-pen the key):**
| | TRAIN (41) | HELD-OUT (19) | ALL (60) |
|---|---|---|---|
| caught real commitments (ACT/ASK recall) | 20/21 = 0.95 | 8/9 = 0.89 | 28/30 = 0.93 |
| stayed silent on noise (SILENT recall) | 20/20 = 1.00 | 10/10 = 1.00 | 30/30 = 1.00 |
| SILENT precision | 0.95 | 0.91 | 30/32 = 0.94 |
| **CARDINAL false-action (SILENT→ACT)** | **0** | **0** | **0** |
| over-ask on SILENT (annoying, not fatal) | 0 | 0 | 0 |

The only 2 disagreements are MISSES in the SAFE direction (real ACT → SILENT), both on debatable
"should/probably" near-line rows ("Did the dispute get filed? I should chase it"; "I'll probably
tidy the garage"). Zero cardinal violations.

**Honest caveats:** (1) I wrote BOTH the decider's prompt and the key from the same commitment rule,
so their agreement partly reflects my own consistency — your red pen is the real test. (2) I did NOT
iterate to catch the 2 misses: the cardinal gate is already 0, and chasing recall on tentative lines
risks trading against it (a false action ≫ a missed promise) and edges toward tuning-to-the-key.
(3) These are provisional; this does NOT mean "the proactive engine works" — it means the measurable
thing it gets judged on exists, and the false-action count is 0 on this key.
