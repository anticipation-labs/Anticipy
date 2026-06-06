# LESSONS

Append here whenever a mistake repeats, then adjust the loop or docs so it is harder to repeat.

- 2026-06-06: Generated Codex build transcripts under `logs/codex/build_*.jsonl` mutate while a lap is still running. Do not track them as kept proof. Keep stable replay proof in `logs/trace/<lap>.jsonl`; ignore generated live transcripts.
