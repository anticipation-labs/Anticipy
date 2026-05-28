# decline_kill: no frozen-path patches required

Date: 2026-05-26
Author: agent (Opus 4.7)
Source directive: Omar 2026-05-26 "never decline" rule.

Summary: every competent-decline template lived in the unfrozen file
`engine/app/product/server.py` and was rewritten in place. The frozen
paths (`engine/app/anticipy/`, `engine/app/action_engine/`,
`engine/app/proactive_day/`) contain zero user-facing decline templates;
the only "refuse" branch in `engine/app/anticipy/proactive_engine.py` is
a sarcasm / retraction classifier, not a decline of a real intent.

See `state/v7/decline_inventory.json` and
`state/v7/decline_kill_summary.md` for the full inventory and risk
assessment. No `decline_kill_*.patch` files needed.
