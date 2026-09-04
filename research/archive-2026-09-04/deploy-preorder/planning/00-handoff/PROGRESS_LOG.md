# Anticipy Progress Log

**Single canonical tracker. Updated as work happens. One row per discrete unit.**

**The DONE column is the ONLY source of truth about what's done.** Per [VERIFICATION_PROTOCOL](VERIFICATION_PROTOCOL.md), every DONE row cites a real artifact + command. Otherwise PARTIAL.

Last full re-verification: 2026-05-30 15:30 PDT.

---

## Status legend

- **DONE** — verified end-to-end with cited artifact within last 10 min
- **PARTIAL** — code exists or partially works; specific gap named in Notes
- **BROKEN** — known failure; recovery plan in Notes
- **QUEUED** — planned, not started
- **BLOCKED** — waits on owner action or external service
- **DEAD** — abandoned, superseded

---

## Phase 0 — Stabilize the working machine (COMPLETE)

| ID | Item | Status | Verification proof |
|---|---|---|---|
| P0-1 | DEV-FINAL is canonical repo, V7 merged | DONE | `cd ~/Developer/Anticipy-DEV-FINAL && git log --oneline -1` = `fac316d5 build: gitignore desktop/target + *.dmg (prevent giant build artifacts)`. Merge commit `649fcbc6` includes 337 V7 commits. Pre-merge tag `pre-merge-devfinal-2026-05-30` saved for rollback. |
| P0-2 | Engine sidecar healthy + listening | DONE | `curl http://127.0.0.1:49671/health` at 15:30 PDT returned `{"ok":true,"pid":7354,"port":49671,"listening":true,"profile_error":""}`. Mic device: MacBook Air Microphone (index 2). |
| P0-3 | chrome-real-clone removed | DONE | `curl http://127.0.0.1:49671/api/state` shows `browser_surface:extension_native_bridge`, `chrome_user_data_dir:""`, `legacy_clone_cdp_enabled:False`. No chrome-real-clone process via `pgrep -fl chrome-real-clone` (empty). |
| P0-4 | OpenRouter key provisioned (key_ok TRUE) | DONE | `curl http://127.0.0.1:49671/api/state` returned `key_ok:True` at 15:30 PDT. OpenRouter direct probe: `curl -H "Authorization: Bearer $KEY" https://openrouter.ai/api/v1/auth/key` returned account valid, $25 used. |
| P0-5 | New DMG live on R2 at anticipy.ai/dl | PARTIAL | Ship-pipeline agent (a8e4) reported `Anticipy_1.0.0_aarch64.dmg` SHA `483741a2c8397c197d7e589c5628c7f30846829046fe2c57dd37d5485666878` size 2516712351 uploaded to R2 at 10:36 PDT. BUT live URL still serves OLD: `curl -sI https://www.anticipy.ai/dl/Anticipy_1.0.0_aarch64.dmg` content-length = 2515666283. **CDN cache stale OR upload didn't actually land.** Need to: (a) bypass CDN to check R2 origin directly, OR (b) wait for CDN TTL to expire and re-check. **Marked PARTIAL until CDN serves new SHA.** |
| P0-6 | History cleanup (DMG blob + Twilio SIDs stripped) | DONE | `git rev-list --objects HEAD | git cat-file --batch-check='%(objecttype) %(objectsize) %(rest)' | awk '$2 > 50000000'` returns empty. `git log --all -p | grep -cE "AC[0-9a-fA-F]{32}"` returns 0. Force-pushed via `git push --force-with-lease`. |
| P0-7 | main + deploy/preorder-to-main pushed to GitHub | DONE | `git push origin main --force-with-lease` succeeded. `git push origin deploy/preorder-to-main --force-with-lease=...:8eca561b` succeeded with "forced update". `git fetch origin && git log origin/main -1` shows `fac316d5`. |
| P0-8 | New /Applications/Anticipy.app installed | DONE | `ls -la /Applications/Anticipy.app/Contents/MacOS/` shows binary at May 30 10:35 (post-rebuild). Engine binary mtime matches. |
| P0-9 | Chrome extension loaded in owner's Chrome | PARTIAL | Owner reported he completed the 4-click load in chrome://extensions. Extension files at `~/.anticipy/extension/anticipy-v6/EXTENSION-LOAD-THIS-IN-CHROME/` confirmed present with manifest.json (manifest version 3, pinned ID `npnpagopediecennpleihemoochikggb`). **HANDSHAKE NOT YET VERIFIED.** `pgrep -fl anticipy-agent` was empty earlier — native messaging not spawned. **Phase 1 will verify the handshake end-to-end.** |
| P0-10 | Computer-use MCP granted on owner's Mac | DONE | `mcp__computer-use__list_granted_applications` shows 8 allowed apps (Google Chrome read tier, System Settings, Finder, Calendar, Mail, Notes, Terminal click tier, VS Code click tier). |
| P0-11 | Vercel deploy validates merged code | QUEUED | Pushed at 13:00 PDT. Need to check Vercel dashboard for build success. If green, P0-5 fully closes once CDN refreshes. |
| P0-12 | Planning docs written (NORTH_STAR + ARCHITECTURE + RALPH_LOOP + VERIFICATION_PROTOCOL + CONTEXT_HANDOFF + RESEARCH/) | DONE | `ls planning/00-handoff/*.md` shows 7 new docs at 15:30 PDT. `ls planning/00-handoff/RESEARCH/` shows 5 research files (agent-loops, chrome-apis, llm-cost-routing, resend-email, a2p-10dlc). All written by claude this session. |

## Phase 1 — Extension <-> engine handshake (NEXT)

**Gate:** owner injects "navigate to gmail.com" via popover or `/api/listen/inject`, extension opens gmail.com in newly-created "Anticipy" tab group (blue), engine receives screenshot from extension, screenshot saved to disk, URL contains "mail.google.com".

**Verification command (to be implemented):**
```
bash scripts/test/phase1-handshake.sh
```

| ID | Item | Status | Notes |
|---|---|---|---|
| P1-1 | Native messaging agent process spawns on extension load | QUEUED | Per `RESEARCH/chrome-apis.md` SW kept alive by connectNative port. Need to verify `anticipy-agent` process appears in `pgrep` when extension is active. |
| P1-2 | Engine reclaims port 8731 when stale lock detected | QUEUED | Bug captured today: when pid dies but lock file remains, engine silently auto-picks new random port (saw 49671). Clients hit dead port. Fix: lock file stores pid, reclaim if pid is dead. |
| P1-3 | Extension creates "Anticipy" tab group on first action | QUEUED | Per `RESEARCH/chrome-apis.md` use `chrome.tabs.group({tabIds, createProperties: {windowId}})` then `chrome.tabGroups.update(groupId, {title:'Anticipy', color:'blue'})`. Re-resolve by title on every startup (IDs don't survive restart). |
| P1-4 | Extension reports screenshot back to engine via native messaging | QUEUED | Per `RESEARCH/chrome-apis.md` stream via file path NOT inline base64 (64 MiB outbound limit). |
| P1-5 | Phase 1 GATE passes | BLOCKED-on-1-thru-4 | E2E test command + cited output. |

## Phase 2 — Unified timeline + popover

| ID | Item | Status | Notes |
|---|---|---|---|
| P2-1 | `~/.anticipy/v7/timeline.jsonl` append-only schema written | QUEUED | Per ARCHITECTURE.md §3. |
| P2-2 | Engine writes to timeline on every action | QUEUED | Replace scattered logs. |
| P2-3 | Popover renders timeline feed | QUEUED | Filter by kind / status / goal. |
| P2-4 | Phase 2 GATE | BLOCKED | "popover shows last 5 entries with kind+status+summary, filterable" |

## Phase 3 — Generic action executor + tab group hygiene

| ID | Item | Status | Notes |
|---|---|---|---|
| P3-1 | Rip out hardcoded recipes (`gmail_compose.py`, `calendar_create.py`, etc.) | QUEUED | Grep first, replace with generic `do(goal)` pipeline. |
| P3-2 | Tab group auto-create on first web action | QUEUED | Per P1-3. |
| P3-3 | Tab cleanup after task done (close success, leave failure for review) | QUEUED | Per owner directive. |
| P3-4 | Phase 3 GATE | BLOCKED | "spoken 'draft email to {test} about Friday' produces real Gmail draft in Anticipy tab group within 30s, no hardcoded recipe used" |

## Phase 4 — Ralph loop

See [RALPH_LOOP.md](RALPH_LOOP.md) for full spec.

| ID | Item | Status | Notes |
|---|---|---|---|
| P4-1 | SQLite tables `goals` + `goal_steps` created | QUEUED | Schema in RALPH_LOOP.md. NOT jsonl per bug B477. |
| P4-2 | Failure classifier (11 classes) | QUEUED | Per RALPH_LOOP.md §"Failure classes". |
| P4-3 | Wake-up poller (30s SQL polling on `next_attempt_at`) | QUEUED | Per RALPH_LOOP.md §"Wake-up scheduling". |
| P4-4 | Two-layer verification (deterministic + vision judge) | QUEUED | Per RALPH_LOOP.md §"Verification layers". |
| P4-5 | Cost cap enforcement ($0.05/goal, $0.30/day, $6/month) | QUEUED | Per RALPH_LOOP.md §"Cost cap enforcement". |
| P4-6 | User-in-loop via one-tap deep link | QUEUED | `anticipy://goal/$ID/continue` |
| P4-7 | Loop detection (action+state hash) | QUEUED | Per RALPH_LOOP.md §"Retry counter logic". |
| P4-8 | Phase 4 GATE | BLOCKED | "inject test goal with 2 deliberate failures, recover to success, SMS receipt within 30s" |

## Phase 5 — 120s onboarding pipeline

| ID | Item | Status | Notes |
|---|---|---|---|
| P5-1 | Permission wizard (Mic, Accessibility, Notifications) in popover | QUEUED | One macOS dialog per permission, ordered. |
| P5-2 | Coldstart inhale runs in <90s via extension scrape | PARTIAL | Code exists in `engine/app/coldstart/auto_inhale.py` + `cdp_walker.py`. Integration walker found it dies in 0.5ms on fresh install because bridge wasn't up. Now P0-3 wires extension surface; need to retest. |
| P5-3 | Sources detected automatically (LinkedIn, Gmail, Calendar, Drive, Slack, Notion if signed in) | QUEUED | Per ARCHITECTURE.md §7. |
| P5-4 | SMS clarification after scrape ("Did I get this right?") | QUEUED | Via existing Twilio broker. |
| P5-5 | Sector detected + hint package loaded | QUEUED | Per ARCHITECTURE.md §10. |
| P5-6 | Phase 5 GATE | BLOCKED | "wipe ~/.anticipy, open app, complete wizard, dossier populated from real sources in <=120s, SMS clarification within 60s" |

## Phase 6 — Resend email channel

See [RESEARCH/resend-email.md](RESEARCH/resend-email.md).

| ID | Item | Status | Notes |
|---|---|---|---|
| P6-1 | Add DNS records on `send.anticipy.ai` subdomain (DKIM, SPF, MX) | BLOCKED | Need owner to add via Porkbun dashboard. Records in `RESEARCH/resend-email.md`. |
| P6-2 | Resend API key + domain verification | BLOCKED | Owner to provide Resend account + API key. |
| P6-3 | Website route `/api/email/receipt` (broker pattern, mirrors Twilio relay) | QUEUED | Engine POSTs to this. Route enforces preconfirm + allowlist. |
| P6-4 | React Email templates in `src/emails/` | QUEUED | Receipt, pre-confirm, weekly summary. |
| P6-5 | Inbound reply webhook routes user reply back to engine | QUEUED | Per-goal reply addresses like `goal-abc123@reply.anticipy.ai`. |
| P6-6 | Phase 6 GATE | BLOCKED | "engine sends test receipt, email lands at owner inbox within 30s, reply routes back to timeline" |

## Phase 7 — Cost-efficient LLM routing

See [RESEARCH/llm-cost-routing.md](RESEARCH/llm-cost-routing.md).

| ID | Item | Status | Notes |
|---|---|---|---|
| P7-1 | Router module that picks model per task type | QUEUED | DeepSeek V4 Flash 85%, Gemini Flash 8% (vision), Sonar 5% (trivia), Gemini Pro 2% (escalation). |
| P7-2 | Prompt caching enabled across all LLM calls | QUEUED | Anthropic 5min TTL, OpenAI auto, DeepSeek caching. |
| P7-3 | Cost telemetry per goal + per user/day/month | DONE-CODE-PARTIAL | `engine/app/product/cost_telemetry.py` exists per audit. Enforcement code in `costctl/guard.py`. Verify it's actually wired to all LLM call sites. |
| P7-4 | Phase 7 GATE | BLOCKED | "20 test goals, observed model ratio matches plan, avg cost ≤$0.002/task" |

## Phase 8 — Sector profiles

| ID | Item | Status | Notes |
|---|---|---|---|
| P8-1 | YAML schema for sector hint packages | QUEUED | Per ARCHITECTURE.md §10. |
| P8-2 | Sector detector from scraped data | QUEUED | Procore = construction, etc. |
| P8-3 | 8 sector files: construction, sales, job_seeking, healthcare, startup_founder, stay_at_home_parent, pensioner, freelance | QUEUED | One YAML each. |
| P8-4 | Planner reads sector hints when active | QUEUED | Inject as system prompt prefix. |
| P8-5 | Phase 8 GATE | BLOCKED | "Procore detected, construction.yaml loaded, next 3 planner outputs include construction vocab" |

## Phase 9 — Fresh-install integration test

| ID | Item | Status | Notes |
|---|---|---|---|
| P9-1 | Test harness: wipe state + install + onboard + 3 sample goals | QUEUED | Real Mac state, real Chrome, real engine. |
| P9-2 | Sample goal 1: email draft | QUEUED | Per Phase 3 gate. |
| P9-3 | Sample goal 2: calendar invite | QUEUED | Generic executor handles. |
| P9-4 | Sample goal 3: web booking (haircut, restaurant, etc.) | QUEUED | Generic executor proves universality. |
| P9-5 | Phase 9 GATE | BLOCKED | "all 3 goals land successfully with receipts in timeline, fresh install" |

## Phase 10 — Investor video recording

| ID | Item | Status | Notes |
|---|---|---|---|
| P10-1 | Phase 9 GATE green | BLOCKED-on-P9 | Pre-requisite. |
| P10-2 | Demo script: 3 moments (silent execute, Donna, trivia) | DONE | In [NORTH_STAR.md](NORTH_STAR.md) §"3 demo moments". |
| P10-3 | Recording | BLOCKED | Owner records. |

## Open architectural questions (still need owner decisions)

1. Construction worker / pensioner cases need native macOS Messages / Phone? Or always Chrome (via icloud.com / web SMS)? Per owner: Chrome-only v1.
2. Two-way phone calls (Anticipy CALLS people) v1 or later? Per owner: phone calls both directions critical only, v1.
3. Voice cloning (user's voice as TTS) — never v1 per scope.
4. Email sender: Resend, send from `send.anticipy.ai` subdomain (NOT apex, would conflict with Porkbun forwarder).

## Currently dead / superseded

- Anticipy V7 repo (per owner 2026-05-30: merge into DEV-FINAL, kill V7 after Vercel deploy validates)
- `chrome-real-clone` profile (architecturally forbidden, removed today, never returns)
- `scripts/v7/anticipy_bridge_fallback_cdp.py` standalone bridge (dead code, not referenced from shipping path; kept for legacy load tests)
- Hardcoded action recipes (`engine/app/action_engine/gmail_compose.py` etc.) — to be ripped in Phase 3
- `engine/app/memory.py` (legacy memory store, unbounded jsonl growth bug B477) — to be replaced by memory_v2 + scoped_memory + dossier_active_loader

## Update protocol

- claude updates this file after every meaningful change (status flip, gate pass, blocker discovery)
- one row = one discrete unit
- "PARTIAL" rows MUST link to what's missing in Notes column
- Never mark DONE without end-to-end verification per [VERIFICATION_PROTOCOL.md](VERIFICATION_PROTOCOL.md)
- Re-verify the live state at the top of every session and update the timestamp
