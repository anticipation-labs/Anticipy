# Autonomy Run Log — Phase 1 (Browser Agent → 100%)

Started: 2026-05-11
Method: fire one corporate-real task → trajectory → diagnose → server-side fix → push → next task.

| Iter | Task | Fired | Outcome | Steps | Wall-clock | Diagnosis | Fix committed |
|------|------|-------|---------|-------|-----------|-----------|---------------|

| 1 | wiki_python_year | 03:03:47 | fail | 7 | 21.9s | extractor looped on selectors; never emitted done with parsed answer | extractor prompt: 'after non-empty extract, NEXT action MUST be done with answer parsed from result.text' |
| 2 | wiki_python_year | 03:06:08 | fail | 7 | 21.4s | extractor re-extracted on same selectors because state didn't include previous extract text; agent had no memory of what it just pulled | plumb last_extract_text into next executor's state context |
| 3 | wiki_python_year | 03:09:59 | fail | 7 | 21.2s | critic punished every extract because before/after DOM didn't change; last_extract_text fix likely missed Railway redeploy window | bypass critic for extract: non-empty text=progress, empty=no_progress (deterministic) |
| 4 | wiki_python_year | 03:12:59 | NO_ROW | 0 | 240s | orchestrator hit MAX_PIVOTS early-exit which RETURNED without writing trajectory; same bug existed on every abort path (reflector_abort, critic_unsafe, max_pivots) | _exit_with_record helper writes trajectory before each early-exit return |
| 5 | wiki_python_year | 03:27:18 | fail | 7 | 16s | type+submit didn't wait for navigation; extract ran on stale DOM, returned empty text 5 times | auto-wait 2.5s after type+submit, 1.5s after navigate, 1.0s after click in orchestrator |
| 6 | wiki_python_year | 03:31:10 | fail | 7 | 15.2s | settle wait applied but extract still empty; navigation may not be fully complete OR pickTab returning wrong tab; same selector loop | nav wait 4s + type+submit 5s + extract retry-on-empty + body fallback |
