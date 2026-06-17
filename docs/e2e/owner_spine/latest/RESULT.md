# E2E owner spine — PASS (GUI journey, fresh data dir, commit pending)

- surface: http://localhost:3000 (Next dev) -> engine :8787 (openrouter brain, hands=mock, channels=mock, data_dir fresh)
- UI talks to engine; 9-line messy scenario typed in the real UI; "reversible ones" checked; "Read my day".

## Result (4 cards, verified in UI + via /owner/cards)
- Amazon "call Amazon about the plant" -> do / AUTO_DO_WITH_OPT_OUT / route=browser. UI lane "On it —
  you can stop me": "I'm on it with call Amazon ... — tell me to stop" + STOP button. NOT an approval.
- CRM "retainer note in the CRM" -> do / AUTO_DO / prepare_internal_note. UI "Prepare internal note
  (Ready): CRM/notes not connected — I've kept the note text ready". NOT money-blocked.
- Sam deck -> ONE card (CLARIFY_FIRST "Can you get Sam the revised deck by Friday?"); the "remind me
  before I send it" reminder merged into the same thread (dedup). No duplicate.
- "that desk thing" -> resolved to "pull up the Jarvis standing desk".
- both vents (coffee->woods, lottery->island) -> SILENT (0 cards). "I read 4 lines, let 0 throwaway".
- every card carries autonomy_mode (persisted on the record + shown on the board). proof[] present.

## Seams fixed this round (engine + UI)
1. Approval-machine -> AUTO_DO_WITH_OPT_OUT for reversible external-service chores (support_chore.py,
   control_core _support_chore_opt_out, UI "On it" lane + Stop + /owner/stop). 2. autonomy_mode persisted
   (_stamp_autonomy_on_record). 3. CRM money-misclass -> prepare_internal_note (note_task/harm carve-out).
   4. Sam-deck dedup (_same_obligation object-core containment + send/deliver generic).

## Safety preserved: safety_mega_eval BREACHES 0; deterministic decision/dedup tests green.
