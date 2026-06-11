# Last Lap

Lap: 20260611T112537Z (build, TARGET v7 item 1 — e2e_completion_rate; ledger
F30 fixed, F27 fixed, F31 opened)

## What changed
- `engine/anticipy_engine/shared/slotbooking.py` (NEW) — the anaphoric
  slot-choice booking shape, shared by BOTH consumers (the F29 anti-drift
  pattern): book-verb + determiner-fronted slot anaphor headed by "one" with a
  concrete time token inside the slot + same-line closed-class appointment-noun
  anchor (appointment/checkup/check-up/cleaning/visit) + commerce/travel-noun
  deny. Every deny fails toward None ("the earlier one", "book the Thursday
  10am one" with no anchor, any flight/hotel/ticket line all stay asks).
- `engine/anticipy_engine/proactive/harm.py` — rule 5b: a matched slot-choice
  booking is a reversible reservation -> ACT. Hard rules still run first
  (money ALWAYS outranks: "...and pay the copay" stays an ask).
- `engine/anticipy_engine/core/gateway.py` — default_stub grounded-calendar
  branch on the GOAL line, before the keyword triggers: a time-anchored
  "block X to Y" (F27) or a slot-choice booking (F30) plans EXACTLY one
  create_event with args from the SPOKEN line (title from "for <purpose>" /
  possessive+appointment-noun, when = spoken window/slot verbatim). No canned
  Lunch-with-Sarah args ride a grounded shape; "on site" no longer plants a
  junk browse step. Stub/keyless tier only — the LIVE planner grounds ISO
  datetimes itself and ApiHand keeps refusing ungrounded live calendar writes.
  Self-reminder branch still wins (scoping pin).
- Pins: F30 accept/deny battery in `test_harmline.py` (6 new, incl. money-
  outranks and the unchanged "Book the 9am flight" deny); F27/F30 planner pins
  in `test_gateway.py` (grounded slot plan, grounded block plan with NO
  browse_task despite "on site", reminder-over-block). All non-bank sentences.

## Numbers I saw (builder-side, stub, dev bank)
- OFFICIAL owner lane (ANTICIPY_OWNER_INGEST=1): e2e_completion_rate
  0.6305 -> 0.6483 (+0.0178 — exactly the one intended completion, dana
  5/7 -> 6/7). catch 1.0/1.0, false 0, harm 0, interrupt 0.6875/1.5,
  recall_worst 1.0 EXACTLY unchanged. correct_action_rate 0.8296 -> 0.8475.
- Default lane: e2e equally 0.6483 (shared plumbing, disclosed); interrupt
  0.625/1.0 and all other aggregates at ratchet bests.
- Per-line decision diff pre->post, BOTH lanes, 493 lines x 16 persona-days:
  EXACTLY one flip (parent_dana d02 L7 ask->act), zero others.
- Goal diffs: dana checkup waiting -> done (create_event "Maya's checkup" /
  "Friday 9am", labeled mock GoogleCalendar proof); luis cabinet
  done-via-browse_task -> done-via-create_event ("cabinet delivery" /
  "Monday 8 to 9" — F27's ledgered regression check satisfied); jin d01 L21 /
  amara d01 L5 / marcus d01 L5 keep state and get grounded spoken-window args
  instead of canned ones (disclosed; the honest direction).
- Suite 43/43. Scorer selftest PASS. Zero spend, zero real-world artifacts.

## THE IMPORTANT DISCLOSURE (F31, foreman-owned)
+0.0178 is UNDER the 0.02 epsilon_noise: this lap is mechanically dead-but-kept
no matter how clean the work, and the previous lap's "pair them to clear
epsilon" arithmetic was wrong (the F27 item already counted complete — its fix
is correctness/honesty, not e2e). After this lap the e2e instrument is AT ITS
HONEST CEILING for builder laps:
- luis DeWalt / amara Hoka / rob IPEVO: NO store in any memory line — stub
  completion would require inventing a site (banned fake). Owner-path
  shopping-context capture or live planning territory.
- pri "buy ... add it to the cart": behind the F23 fail-safe money stance
  (foreman queue).
- The 16 expected-asks are structural (scorer counts completions only on
  expected acts).
Every possible remaining flip is +0.0178..+0.0208 vs epsilon 0.02. Honest laps
will now read dead until K=5 escalates. The right next move is a foreman
re-aim (TARGET v8): candidates are correct_action_rate (0.8475, real headroom:
kayla compound-item args, stub canned send/draft args), owner-path capture for
storeless cart items, the F23 stance decision, or the human-gated P3 live legs
(OWNER_PHONE still pending in PENDING_FOR_OMAR.md; gate_P3.sh still does not
exist — foreman item).
