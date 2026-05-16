# Anticipy Action Engine V1 - HANDOFF (V4-10)

## One-paragraph summary

The Anticipy action engine takes a plain-English task and executes
it end-to-end against the user's real signed-in Chrome, in an
isolated background "Anticipy Agent" window, using DeepSeek V4 Flash
+ Kimi K2.6 (vision) via OpenRouter in a vision-woven snapshot ->
decide -> act -> verify Ralph loop. Completion is graded by a
separate vision auditor on the real screenshot (no fabricated
success possible). Tier 1 (general DOM web: search, read, click,
fill, multi-page, send) is at **36/36 = 100.0%** across 12 tasks x
3 runs, honest and not rounded, including Gmail compose-and-actually
-send and Slack reading real channel messages. Canvas apps (Tier 2:
Sheets/Docs/Slides cell-commit) remain a documented frontier limit:
Google's canvas resists synthetic input; navigation/extraction work,
multi-cell commit does not reliably. A Tauri Mac app ships the
engine behind a simple UI at anticipy.ai/download (unsigned).

## Phase tags (v4-0 -> v4-9)

- phase-v4-0-openrouter-confirmed   OpenRouter reachable, model routing documented
- phase-v4-1-cleanup                Fara/Ollama/Qwen3 removed
- phase-v4-2-client-ready           OpenRouter client (vision, fallback, cost ledger)
- phase-v4-3-verifier-ready         vision verifier (Kimi, conservative)
- phase-v4-4-runner-ready           DSv4 Ralph-loop runner
- phase-v4-5-wikipedia-passes       smoke gate (blank tab -> answer, vision-confirmed)
- phase-v4-6 (no tag)               compound/canvas gate: integrity fix + documented ceiling
- phase-v4-7-tier1-100              Tier 1 36/36 = 100% (gate)
- phase-v4-8-logging-live           Supabase trajectory logging (verified vs prod DB)
- phase-v4-9-mac-app-ships          Tauri .dmg published, /download 200

## Scoreboard

Full honest per-task results: `.anticipy/V4_SCOREBOARD.md`
(regenerate: `cd engine && python -m
tests.integration.test_v4_7_twenty_tasks --scoreboard-only`).
Tier 1 = 12/12 tasks at 3/3, aggregate 36/36 = 100.0%, both gate A
(>=11/12 at 3/3) and gate B (all 12 >=2/3, >=95% aggregate)
satisfied. Vision-auditor graded on real pixels; no silent passes.

## Cost analysis (real, measured, not projected)

Source: `~/.anticipy/openrouter_calls.jsonl` (2,277 calls) correlated
with the V4-7 run windows in `.anticipy/v4_7_results.jsonl`.

| metric | per successful task run |
|---|---|
| median | $0.0154 |
| mean   | $0.0211 |
| p90    | $0.0377 |
| p99    | $0.0897 |
| max    | $0.0897 |

Total OpenRouter spend across the ENTIRE V4 build (every phase, all
fix-loop iterations): **$4.74 all-time**.

Honest economic finding: median ~1.5 cents/task is ABOVE the
"<1 cent/task, $99/user/year for 10k tasks" target. Cause: the
decide step is vision-primary on Kimi K2.6 (the authorized V4-6
general fix - a text-only model is blind to canvas/complex pages).
At median that is ~$150/yr per 10k-task user; at p90 ~$380/yr. This
is the real number, stated truthfully, not rounded down. Lowering
it (cheaper vision model, or text-decide with vision only on
canvas) is a v2 economic decision, not a correctness one.

## Three demo tasks (run from the Anticipy Mac app)

1. "Open Hacker News and tell me the title of the current top story."
2. "Open Gmail, compose an email to anticipy-test@gmail.com with
   subject 'Hi from Anticipy' and body 'Test.', then send it."
3. "Open Google Maps, search for coffee shops, tell me the first
   result." (Spotify/YouTube/Amazon/Reddit/GitHub/Notion/Slack
   variants all pass 3/3 too.)

## Known limitations / failure modes

- Canvas cell-commit (Sheets/Docs/Slides) is a frontier limit:
  Google's canvas ignores synthetic input for value commit (~12
  experiments in V4-6). Navigation/extraction on those sites works;
  writing committed cell data does not reliably. Tier 2 target was
  90% with a 2-attempt cap and this is accepted, documented with
  evidence, not retried indefinitely.
- Bare password walls / account creation: the agent NEVER types
  passwords or creates accounts (safety). It uses existing sessions
  (account-chooser / Open / workspace subdomain). A site with no
  existing session and only a password form returns an honest
  NEEDS_PASSWORD, not a bypass.
- The Mac app is a UI shell that drives the LOCAL engine via
  subprocess (absolute paths per CLAUDE.md). It requires the engine
  checkout, its venv, `~/.anticipy/.env` (OPENROUTER_API_KEY), and
  Chrome on :9222. It is not a standalone self-contained installer.
- The .dmg is 3.2MB (Tauri uses the OS WebView, not bundled
  Chromium). The prompt's 50-500MB band assumed Electron. The dmg
  is a valid drag-to-Applications install, built via hdiutil
  because Tauri's create-dmg Finder/AppleScript styling fails
  without a GUI window-server session.
- Unsigned: first launch needs right-click -> Open (per the locked
  no-signing rule).
- Latency: ~25-60s for simple tasks, up to a few minutes for
  multi-step (Gmail compose+send ~160s). Vision calls dominate.
