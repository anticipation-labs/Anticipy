# LESSONS

Append here whenever a mistake repeats, then adjust the loop or docs so it is harder to repeat.

- 2026-06-06: Generated Codex build transcripts under `logs/codex/build_*.jsonl` mutate while a lap is still running. Do not track them as kept proof. Keep stable replay proof in `logs/trace/<lap>.jsonl`; ignore generated live transcripts.
- 2026-06-06: The amended judge required MP3 holdouts but the realday harness rejected audio while normal builder diffs were forbidden from touching the harness. Treat generic input-adapter fixes as control-plane plumbing, log them as not judged, and never count them as milestone proof until a later fresh judge lap passes.
- 2026-06-06: A verdict inventory list of holdout filenames was treated as if every listed file had been burned, leaving the judge with no selectable fresh day. Holdout rotation must distinguish inventory from actual use. Only a held-out file that was opened, transcribed, or used in a verdict is burned.
- 2026-06-06: The system repeatedly typed the whole task into a browser search box and treated search/read/context proof as progress. This is not thinking. Fix the planner and routing boundary: explicit information lookup may search, but action tasks must decompose into API hands, the real browser agent, or ask/needs-human. Do not paper this over with more browser regexes.
- 2026-06-06: Stale eval proof from older laps leaked into fresh held-out planning. Treat previous-lap ids, old proof titles, and old sent-mail subjects as contamination. Current-lap planning must create fresh parameters from the current real need or abstain.
