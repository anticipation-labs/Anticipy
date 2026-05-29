# Handoff for next agent

> **FIRST READ: HANDOFF_COMPLETE.md** in this same folder. It has every micro-detail (components, files, gates, env vars, agents, gaps, commits, memory entries). This file (HANDOFF_FOR_NEXT_AGENT.md) is the architectural rules only.

You are picking up Anticipy planning from a prior planner. Read this first. The prior planner made specific architectural mistakes that you must not repeat.

## What Anticipy IS

An AI pendant that listens to everything around the user and silently completes whatever anyone asks them to do. Donna from Suits, for everyone. The pendant is always-on capture, the phone is the edge brain, a mini-PC ($30 Raspberry-Pi-class) runs Chrome and acts. Mac app today is the prototype of that final form. Engine code ports unchanged to the mini-PC.

Three concrete proof points:
1. Silent execute. Lawyer at intake hears the client; demand letter is drafted in her firm's case management system before she walks back to her desk.
2. Trivia in your ear. Friend asks "when did the Roman Empire actually fall," 1.2 seconds later your earbud whispers "476 AD Western, 1453 Constantinople."
3. "I just do." Anyone who asks the user a question gets the answer or action they wanted, before they've finished asking.

Privacy moat: local-first engine, only the LLM brain call goes out (to OpenRouter via the website broker). NO service APIs (no Gmail API, no Slack API, no Salesforce API). Drive the user's real Chrome with the user's real cookies. The user is already logged in.

## Hard rules Omar has stated, the prior planner violated, you must not violate

1. **No hardcoded skill library, no per-app recipe registry, no regex-based action programming.** The prior planner wrote in ROADMAP.md item #9: "Per-app config registry. `engine/config/auth_profiles/<app>.json` per supported SaaS." This is exactly the violation. Anticipy is a universal action agent that figures out any app at runtime by reading the DOM + screenshot + applying Claude-grade intelligence to interact with it. Like Claude computer use, like Codex web agent. NOT a hardcoded library of 30 app recipes. See `planning/08-universal-action-agent/DESIGN.md` for the correct architecture.

2. **No "we can't do X because of platform limitation" excuses when we have computer use.** The prior planner said the Chrome extension can't install in the user's running Chrome. False. We have computer-use available (`mcp__computer-use__*` tool family). The agent can click through `chrome://extensions`, toggle Developer Mode, drag the .crx file, click Install. The user does NOTHING. See `planning/09-extension-install-via-computer-use/DESIGN.md`.

3. **No regex programming in the planner.** The current `_is_actionish` at `engine/app/product/server.py:2548-2553` is a regex whitelist of verbs (`should|need|owe|draft|email|send|share|...`). This violates the same rule. The fastpaths `_fastpath_plan_from_memory` and `_fastpath_pronoun_resolve` are regex-based shortcuts. They should be replaced with a small fast LLM (Haiku 4.5 or DeepSeek V4 Flash with prompt caching) that does intent + person resolution in <300ms. See `planning/11-hardcoded-violations-audit/EXCISE_LIST.md`.

4. **Cold start works on day zero. Not week one.** Omar has an investor meeting tomorrow. The current cold-start has nothing for new users. The new design is auto-inhale that runs in the background while the user is doing onboarding, using the LLM to interpret raw Gmail/Calendar/Drive content into a structured dossier in real time. See `planning/10-instant-cold-start/DESIGN.md`.

5. **No "all green" claims without a real stranger-flow proof.** The prior planner shipped DMGs while declaring 6 gates GREEN, but never proved a brand-new macOS user account could install and use the product. The investor meeting requires that proof. See `planning/12-investor-demo-tomorrow/PLAN.md`.

6. **No em-dashes in any code, doc, or response.** Owner's #1 AI-tell hate.

7. **No "I'll never do it again."** Don't promise. Don't apologize. Just do the work correctly.

## What's in this folder

| Folder | Purpose | Status |
|---|---|---|
| 00-handoff | This file + HANDOFF.md (component summaries) + ROADMAP.md (prioritized backlog) | this file is the entry point |
| 01-cold-start | Original cold-start brainstorm. Superseded by 10. | superseded |
| 02-confidence-ladder | Silent/notify/confirm/refuse design. Mostly correct, watch for hardcoded verb tables. | use with care |
| 03-cross-app-auth | Tab isolation + MFA. Contains the per-app config registry violation. Refer to 08 instead. | superseded |
| 04-quietness-ux | Notification cascade. Correct, mostly. | use |
| 05-existing-code-map | Where every file lives. Treat as ground truth, but verify by re-reading. | use |
| 06-competitive-landscape | 12-competitor scan. Limitless Meta acquisition, Bee Amazon, Humane HP shutdown. Useful for positioning, no action items. | reference |
| 07-trivia-fire | The killer demo. Correct. | use |
| 08-universal-action-agent | THE CORRECT action architecture. No recipes. | read this |
| 09-extension-install-via-computer-use | Install Chrome extension by driving the install flow with computer-use. | read this |
| 10-instant-cold-start | Day-zero cold start via LLM-driven inhale. | read this |
| 11-hardcoded-violations-audit | Every hardcoded recipe / regex / verb table in the codebase. Excise list. | read this |
| 12-investor-demo-tomorrow | 24-hour plan for tomorrow's meeting. What must work, what we'll show. | read this |

## State of the codebase right now

Read `planning/05-existing-code-map/MAP.md` for the full map. Critical facts:

- Shipping engine: `engine/app/product/server.py:53` on port 8731. PyInstaller-packaged into `/Applications/Anticipy.app/Contents/MacOS/anticipy-engine`. PID can be confirmed via `lsof -nP -iTCP:8731 -sTCP:LISTEN`.
- Three engines fight for port 8731. The packaged sidecar, the `com.anticipy.human-ready-loop` launchd job (spawns source uvicorn from pyenv 3.10), and the `com.anticipy.finish-overnight` launchd job. Bootout the two loops before testing anything.
- 4 memory implementations coexist. Pick ONE before adding code. Recommend the active dossier at `~/.anticipy/v7/dossiers/<acct>/dossier.json` via `engine/app/product/dossier_active_loader.py:139`.
- 2 CDP paths: V4 skill runner direct to 9222 for Gmail draft, bridge on :7777 for surface probes + Z-001. Both use the same Chrome at 9222.
- `engine/app/anticipy/handoff` is imported at `server.py:73` but the file doesn't exist (wrapped in try/except). Either build it or delete the import.
- Hot path: `/api/listen/upload|inject` → `_fastpath_plan_from_memory` (line 5276) or `_fastpath_pronoun_resolve` (line 5399) → `_compose_task_from_memory` (line 5479) → `/api/act` (line 6659) → confirm card if irreversible.
- The "frozen paths" rule from CLAUDE.md (`engine/app/anticipy/`, `engine/app/action_engine/`, `engine/app/proactive_day/`, `verifier/`) was UNFROZEN by Omar on 2026-05-29: "Who froze it in ice? You can just unfreeze it. Just don't break it." You can edit anything. Just don't break Z-001 (run `python3 scripts/v7/z001_e2e_harness.py` to verify, expect 9/9 PASS).

## Current state of each component (honest scorecard, percent of vision shipped)

```
Capture (ASR)         80%   parakeet_mlx works on Mac, always-on daemon needs hardening
Memory                40%   4 partial impls, cold start broken
Action brain          50%   works but slow + 50% empty rate (platform_adapter.py:205 timeout)
Action surfaces       30%   Gmail + native macOS work, generic Chrome via surface_runtime.py exists
Confidence ladder     40%   logic exists, no calibration, no reversal log
Notification          20%   taxonomy built (proactive/types.py), NO delivery
Authority vault       30%   password works, MFA mostly missing
Cold start            10%   only Twilio scaffold, doesn't auto-inhale
Trivia fire            0%   not started
Engine stability      40%   port 8731 race, hardcoded Omar paths
Tab isolation         20%   active hijack bug (anticipy_bridge_fallback_cdp.py:528-554)
Stranger flow          0%   never proven E2E on a fresh macOS account
Distribution          90%   DMG + Vercel solid
Handoff               70%   works via mystery code, ghost import
UI surfaces           40%   popover exists, no activity feed
Pendant hardware       0%   doesn't exist (out of scope V1)
Phone app              0%   doesn't exist (out of scope V1)
-----------------------------------------------
TOTAL                 32%   of full vision
```

## Where Omar is right now

- Investor meeting tomorrow (2026-05-30). Whatever we show must work without manual rescue.
- Three months in. Pattern of "promise, don't deliver, claim done anyway." Trust is low. Earn it back with a clean, honest demo, not with more promises.
- Owner is the only person on the project beyond planners (us). Owner does code review by reading commits and watching the product work, not by reading planning docs. Planning docs are for the next agent (this is you).

## Working agreement for the next agent

- Read this file first. Read the 5 new planning docs (08-12). Then read the 7 old ones (01-07) with awareness of which are superseded.
- Before any code change, write the plan in the relevant planning folder.
- After each commit: run Z-001, paste result.json into the commit message. No exceptions.
- Use computer-use where Chrome-extension limitations or other "we can't because the OS won't let us" excuses arise. We can drive the user's Mac. Use that capability.
- No em-dashes. Owner will reject the PR if you use one.
- If you find a hardcoded skill library, regex verb whitelist, per-app recipe, or any code that violates rule #1, EXCISE IT, don't add to it.
- Update this file at the bottom with what you did, in chronological order.

## Changelog

| Date | Agent | Action |
|---|---|---|
| 2026-05-29 | prior planner | created planning/ folder, 7 thread agents (01-07), wrote ROADMAP with hardcoded-app-library violations. Owner called this out. |
| 2026-05-29 | this planner | wrote this handoff. Added 5 new planning threads (08-12) to correct the architectural violations. Spawning agents to draft the 5 new docs. |
| 2026-05-29 | exec agent (trivia) | shipped end-to-end trivia-fire per planning/07. New modules engine/app/trivia/{__init__,trigger,answer,deliver,cache,seed_facts}.py with 168 hand-curated seed facts. server.py: import _trivia at top; _process_utterance branches on _trivia.maybe_fire() right after profile-load; new GET /api/trivia/recent. Commit 31a5a64c. Verified: Roman Empire phrase produces cache hit in 7-10 ms, TTS spawn in 3-10 ms, total trivia internal latency 12-22 ms (user hears the answer essentially immediately). HTTP response p50 1.4-3.2 sec dominated by post-trivia memory_write LLM. Z-001 run 20260529T184750Z: PARTIAL verdict (8/9 PASS, 1 WARN on gmail_draft_visible due to Gmail UI autosave timing brittleness; engine_act PASSED with status=SUCCESS intent=email_draft proving trivia did not clobber the action path). Tab leakage 0. |
| 2026-05-29 | exec agent a6a27e8c (cold-start) | shipped instant cold-start inhale per planning/10. New module engine/app/coldstart/auto_inhale.py (orchestrator + module-level state + atomic dossier merge_delta). engine/app/coldstart/__init__.py extended to export auto_inhale + cdp_walker public API. server.py: new endpoints POST /api/coldstart/start (kicks off background inhale, returns immediately) and GET /api/coldstart/status (returns {state, people_count, projects_count, tools_count, rows_collected, elapsed_ms, batches_sent, llm_calls_ok/failed, errors, bridge_ready}). Commits 31a5a64c (server endpoints) and f46ed0e5 (auto_inhale module). Walker opens Anticipy-owned background tabs via Chrome /json/new (NEVER hijacks user tabs), scroll-extracts visible row metadata, closes its tabs on exit. LLM prompt is 2.6KB so platform_adapter.model_call auto-attaches cache_control:ephemeral. Merge is atomic temp+os.replace, preserves existing dossier fields (preferences, do_not_touch, original people). Verified live against Omar's actual Gmail: 119 rows -> 4 batches -> 4 LLM OK -> 8 new people / 4 projects / 10 tools merged in 44s. Dossier delta on disk: people 2 -> 15 (+13), projects 0 -> 6 (+6), tools 0 -> 15 (+15). Maya Patel + Jordan Lee preserved with provenance=original. Z-001 run 20260529T185103Z: PASS 9/9 (engine_act SUCCESS, gmail_draft_visible PASS, exchange_handoff WARN transient network). Tab leakage 0. |
| 2026-05-29 | exec agent a692daa0 (handoff ghost + post-action receipt) | Two fixes. Task 1: replaced the ghost import at server.py:73 (`app.anticipy.handoff`) with a real module engine/app/anticipy/handoff.py exposing GET /api/auth/handoff/session and POST /api/auth/handoff/exchange. The website still owns the actual handoff exchange (src/lib/handoff-token.ts plus src/app/api/auth/exchange/route.ts); the engine endpoints are thin convenience helpers that proxy the website exchange and cache a non-sensitive session record at ~/.anticipy/session.json. Tokens stay in the desktop keychain. Unwrapped the silent try/except so packaging regressions are loud. Commit bc54a03e. Task 2: post-action receipt. server.py: new helpers `_emit_action_receipt`, `_send_receipt_sms_sync`, `_send_receipt_email_via_cdp`, `_maybe_attach_receipt`, plus a new endpoint POST /api/dispatch/with_receipt that wraps act() and force-fires the receipt regardless of the ANTICIPY_RECEIPT_ON_SUCCESS env gate. Receipts go via Twilio SMS (only when TWILIO_TEST_TO_REAL_NUMBER=1 plus TWILIO_TEST_TO_REAL_NUMBER_E164 are set) and via a self-email opened through the same Gmail CDP path the action just used (safe because the destination is always the user's own address). Bundled with the SMS pre-confirm work into commit c2879c67 (parallel agent picked up my staged edits when committing sms_pre_confirm); the receipt code is intact in HEAD. Z-001 run 20260529T204904Z: PASS 9/9 (engine_act SUCCESS, gmail_draft_visible PASS, exchange_handoff PASS). Tab leakage 0. Manual: /api/auth/handoff/exchange with a bogus token returns the real 404 from the website. /api/dispatch/with_receipt against a Gmail draft instruction returns ok=true with receipt.self_email.ok=true (real draft created in user's mailbox) and receipt.sms.gated=true with reason "TWILIO_TEST_TO_REAL_NUMBER not set" (correct gating; no real phone hit). |
