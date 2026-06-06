# LESSONS

Append here whenever a mistake repeats, then adjust the loop or docs so it is harder to repeat.

- 2026-06-06: Generated Codex build transcripts under `logs/codex/build_*.jsonl` mutate while a lap is still running. Do not track them as kept proof. Keep stable replay proof in `logs/trace/<lap>.jsonl`; ignore generated live transcripts.
- 2026-06-06: The amended judge required MP3 holdouts but the realday harness rejected audio while normal builder diffs were forbidden from touching the harness. Treat generic input-adapter fixes as control-plane plumbing, log them as not judged, and never count them as milestone proof until a later fresh judge lap passes.
- 2026-06-06: A verdict inventory list of holdout filenames was treated as if every listed file had been burned, leaving the judge with no selectable fresh day. Amendment 2 supersedes that burn model: failed or blocked judge runs do not burn held-out days. A held-out file rotates out only when it contributes to a milestone PASS.
- 2026-06-06: The system repeatedly typed the whole task into a browser search box and treated search/read/context proof as progress. This is not thinking. Fix the planner and routing boundary: explicit information lookup may search, but action tasks must decompose into API hands, the real browser agent, or ask/needs-human. Do not paper this over with more browser regexes.
- 2026-06-06: Stale eval proof from older laps leaked into fresh held-out planning. Treat previous-lap ids, old proof titles, and old sent-mail subjects as contamination. Current-lap planning must create fresh parameters from the current real need or abstain.
- 2026-06-06: Raw run artifacts were committed before Amendment 2: `logs/last_realday.json`, `logs/trace/*.jsonl`, and raw verdict JSON/JSONL can contain transcripts or held-out-derived evidence. Keep them local-only, ignore them, untrack them with `git rm --cached`, and amend or scrub branch history before judging.
