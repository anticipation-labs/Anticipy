# Anticipy Architecture — the bulletproof spec

**Purpose:** the engineering bible. Every implementation decision lives here. Cross-references research files.

**First-read order:** [NORTH_STAR](NORTH_STAR.md) → this file → [PROGRESS_LOG](PROGRESS_LOG.md) → [VERIFICATION_PROTOCOL](VERIFICATION_PROTOCOL.md) → [RALPH_LOOP](RALPH_LOOP.md).

---

## 1. The "one app" architecture

What user sees:
1. **Anticipy.app** in `/Applications`. Menubar icon. Popover. Single icon.
2. **Chrome** with an "Anticipy" tab group (color-coded, collapsible).

Two visible things. Chrome is unavoidable (Chrome security model). Everything else collapses into the .app bundle.

Inside Anticipy.app (user never sees these, but they exist):
- **Tauri shell** (Rust + macOS native UI) — tray icon, popover WebView, deep-link handler, app lifecycle
- **Python engine sidecar** (spawned by Tauri as child) — ASR, planner, executor, Ralph loop, memory, cost gate. Bound to a port in `~/.anticipy/engine.port` (lock-file enforced).
- **Native messaging agent** (Python stub at `~/.anticipy/anticipy-agent`) — spawned BY CHROME on `chrome.runtime.connectNative`. Lives until extension disconnects. Bridges engine ↔ extension.
- **Chrome extension** (loaded via Chrome Web Store in shipping, dev-loaded for owner). Drives Chrome tab group + chrome.debugger.

**The bridge process on port 7777 is dead.** Per `RESEARCH/chrome-apis.md`, SW is kept alive by `connectNative` port; we don't need a separate bridge.

## 2. Inputs (3 paths, no overlap)

| Input | Endpoint | Use |
|---|---|---|
| Live mic | `POST /api/listen/start { device_index }` | Ambient capture, all-day |
| MP3 upload | `POST /api/listen/upload` | One-shot recorded day analysis |
| Text inject | `POST /api/listen/inject { text }` | Claude's test interface (no mouth) |

Inputs flow into the **router** which classifies to one of: `LIFE_LOG` (just remember), `TRIVIA` (answer in earbud), `ACTION` (run through Ralph loop).

## 3. Unified timeline (everything synced)

**One store, all channels:**
```
~/.anticipy/v7/timeline.jsonl   (append-only, rotated weekly, max 100 MB)
```

Schema per row:
```json
{
  "ts": 1780174000.123,
  "goal_id": "g-abc123",
  "kind": "email_sent|sms_sent|voice_call|web_action|note|user_reply",
  "channel": "resend|twilio_sms|twilio_voice|chrome|popover",
  "status": "pending|done|failed|wait_user",
  "summary": "Drafted email to Sarah Lin about Friday demo",
  "payload": { ... }
}
```

App popover shows this as a single feed. Filter by status / kind / goal. A reply that came in by SMS shows up in the same goal's thread alongside the email sent earlier. **One brain, many channels, one view.**

## 4. Generic action executor (kills hardcoded recipes)

**Today's mess:** `engine/app/action_engine/gmail_compose.py`, `calendar_create.py`, etc. — site-specific scripted flows.

**New:** ONE function:
```
do(goal, context) -> result
```

Pipeline:
1. **Planner** (cheap LLM — DeepSeek V4 Flash) extracts intent: `{action, recipient, thing, surface_hint}`
2. **Surface picker** routes: web (chrome.debugger) / sms-out (Twilio relay) / voice-out (Twilio) / email-out (Resend) / search (Sonar) / memory (read dossier)
3. For web: **executor** opens whatever site is needed in the Anticipy tab group, drives DOM generically via DOM selectors + vision fallback when ambiguous
4. **Verifier** checks (deterministic first, vision only on cache miss / canvas)
5. On failure: **Ralph loop** classifies + recovers (see [RALPH_LOOP](RALPH_LOOP.md))

**Hardcoded recipes die.** No `if site == gmail then click_id("compose")`. The planner picks the site, the executor reads the DOM, the LLM decides what to click.

## 5. Chrome extension architecture (per `RESEARCH/chrome-apis.md`)

**Critical findings to respect:**

1. **No `chrome.tabGroups.create`.** Use `chrome.tabs.group({ tabIds, createProperties: { windowId } })`. Then `chrome.tabGroups.update(groupId, { title: 'Anticipy', color: 'blue' })`. Colors restricted to 9 named values, no hex.

2. **Tab/group IDs do NOT survive Chrome restart.** Re-resolve by title `'Anticipy'` on `chrome.runtime.onStartup`. Never cache numeric ids in storage.

3. **"started debugging this browser" infobar is PERMANENT and non-suppressible.** Product UX must accept it. Document this prominently for users ("you'll see a small bar at the top, that's Anticipy doing its work, you can dismiss it but it'll come back when Anticipy runs again").

4. **`--load-extension` flag is silently ignored on second Chrome launch** (ProcessSingleton). Chrome 137+ requires Developer Mode toggle which can't be set programmatically. **Shipping path is Chrome Web Store, period.** Until Web Store review approves, dev users (Omar) manual-load unpacked.

5. **SW kept alive while `connectNative` port open** (Chrome 105+). Native messaging port stays open = SW alive = engine reachable. This is the right keepalive.

6. **One `connectNative` = one host process.** Don't spawn per-tab. Multiplex one port with request ids. Inbound 1 MB max, outbound 64 MiB. Stream screenshots via file path, not inline base64.

7. **chrome.debugger has no documented concurrent-tabs limit.** Use Chrome 125+ flat sessions (`Target.setAutoAttach { flatten:true }`) for cross-origin iframes (Gmail, LinkedIn, Drive all use OOPIFs and need this).

8. **Per-profile isolation is automatic.** If user has Work + Personal Chrome profiles, extension is loaded per-profile. Use `chrome.identity.getProfileUserInfo` to display, persist per-profile UUID in `chrome.storage.local` for routing on native-host side.

## 6. Ralph loop summary (full spec in [RALPH_LOOP](RALPH_LOOP.md))

- Per-goal SQLite state in `~/.anticipy/v7/ralph.db` (NOT jsonl per bug B477)
- Failure classifier with 11 named classes (login_wall, captcha, network, rate_limit, element_missing, payment_required, account_locked, ambiguous_dom, cost_cap, model_error, unknown)
- Class-specific recovery (backoff for network, SMS user for login_wall, NopeCHA for captcha, etc.)
- Two-layer verification: deterministic per-step (free), vision judge per-goal (~$0.0003)
- Cost caps: $0.05/goal, $0.30/user/day, $6/user/month
- Wake-up via SQL polling `next_attempt_at` every 30s (NOT in-memory sleep)
- User-in-loop via SMS/email + one-tap deep link `anticipy://goal/$ID/continue`

## 7. Onboarding pipeline (the 120s magic)

| Step | Time | What happens |
|---|---|---|
| 0 | t=0s | User opens Anticipy.app first time |
| 1 | t=2s | Permission wizard: Mic → Accessibility → Notifications (one dialog each, in order) |
| 2 | t=30s | "Install our Chrome extension" — popover deep-links chrome://extensions and shows the 4-click wizard (until Web Store approves) |
| 3 | t=60s | Extension loaded, native messaging handshake, engine sees `browser_surface=extension_native_bridge` and `extension_connected=true` |
| 4 | t=65s | "What's your name and where are you?" — 2 quick text inputs |
| 5 | t=70s | "Give me 2 minutes to learn about you" — coldstart inhale begins |
| 6 | t=70-180s | **Extension opens Anticipy tab group, scrapes**: LinkedIn (if signed in), Gmail (if signed in), Calendar, Drive, Contacts, Slack, Notion, anything else signed in. Builds dossier. |
| 7 | t=180s | "I know you work at X, your boss is Y, your big project is Z. Did I get it right?" — SMS to user with 3-question summary |
| 8 | t=ongoing | User replies with corrections. Dossier locks. |
| 9 | t=done | "I'm listening" — popover flips to active mode. User can now use it. |

If Chrome has nothing signed in (construction worker case): step 6 yields very little. Step 7 SMS becomes a longer conversation ("Tell me a bit about your day"). Dossier builds from speech instead of scraping. Same destination, different source.

## 8. Communication channels (matrix)

| Urgency | Channel | When |
|---|---|---|
| Critical, time-sensitive | Voice call (Twilio) | Agent hit a wall, needs login NOW, fraud alert |
| Critical, not time-sensitive | SMS | Pre-confirm before irreversible action, "spent $X today OK to continue" |
| High | SMS + email | Daily roundup, important booking confirmed |
| Medium | Email only | Receipts for completed actions, weekly summary |
| Low | Silent (timeline only) | Lifelog entries, ambient noise |

**Email goes through Resend** (per `RESEARCH/resend-email.md`):
- Send from `hello@send.anticipy.ai` (subdomain, doesn't conflict with Porkbun forwarder on apex)
- Replies via custom-per-goal addresses like `goal-abc123@reply.anticipy.ai` (inbound webhook)
- React Email templates in `src/emails/` (Node SDK + React)
- Broker pattern: engine POSTs to `https://www.anticipy.ai/api/email/receipt`, route enforces SMS-preconfirm allowlist + no-real-send-in-test
- Cost: ~$4.50/user/year at 5K receipts. Well under $200 ceiling.

**SMS goes through Twilio broker** (already wired):
- Production +16196584447 (Anticipy Aevoy account)
- Per `RESEARCH/a2p-10dlc.md`: A2P 10DLC required for US. Low-Volume Standard $5.50 one-time + $3/mo. Single Mixed campaign. 5-7 business days timeline.
- Multi-tenant via PIN routing (already wired per memory)

**Voice goes through Twilio voice:**
- Outbound (call user when critical): wired
- Inbound (Anticipy calls people for user, like booking a restaurant): future phase
- Per-user isolation: same number, PIN identifies caller

## 9. Cost-efficient LLM routing (per `RESEARCH/llm-cost-routing.md`)

**Decision tree:**

| Task | Model | $/call typical |
|---|---|---|
| Intent classify (text → ACTION/TRIVIA/LIFELOG) | DeepSeek V4 Flash (direct, not OpenRouter) | $0.0001 |
| Planner (extract recipient/action/thing) | DeepSeek V4 Flash | $0.0003 |
| Generic web action (DOM reasoning) | DeepSeek V4 Flash, vision fallback Gemini 2.5 Flash | $0.0001-$0.0008 |
| Vision DOM (only when DOM extractor returns <8 elements or canvas detected) | Gemini 2.5 Flash | $0.0005 |
| Trivia live lookup (cache miss only) | Perplexity Sonar (not Sonar Pro) | $0.0002 |
| Draft email/document body | DeepSeek V4 Flash | $0.0005 |
| Escalation (consecutive failures >= 3) | Gemini 2.5 Pro | $0.005 (rare) |
| ASR | Parakeet (local, on Mac) | $0 |
| TTS | ElevenLabs (cached by hash) | $0 if cached |

**Average $0.00188/task** = $56/user/year LLM cost. Leaves $144 for Twilio + Resend + R2 + Vercel + Supabase + TTS. Total well under $200.

**Prompt caching mandatory:** Anthropic 5min TTL (0.10x on hit), OpenAI auto prefix cache (0.50x), DeepSeek 50-120x cheaper on hit. System prompts cached. Re-prompted per goal.

**Tripwires:** daily LLM cost > $0.30 or monthly > $6.00 = kill switch + SMS user.

**Local-on-Mac (opt-in at onboarding):** 4-6 GB MLX bundle (Phi-4 or Qwen3 8B). Routes intent + extract + short-plan local, saves $10-$15/user/year if enabled. Mandatory MLX backend (2x faster than llama.cpp on Metal). Phase 7 work.

## 10. Sector profiles (hints, not hardcoded recipes)

Onboarding detects sector from scraped data:
- Procore tab + Buildertrend signed in → `construction`
- Salesforce + HubSpot → `sales`
- Indeed + LinkedIn job apps recent → `job_seeking`
- Multiple medical portals → `healthcare`

Each sector has a YAML hint package:
```yaml
construction.yaml:
  common_tools: [Procore, Buildertrend, Home Depot Pro, Google Maps]
  common_goals: [schedule subs, quote materials, invoice client, calendar callbacks]
  vocab_hints: [punch list, change order, job site, RFI]
  preferred_channels: [sms, voice]  # users likely on the move
```

The planner reads hints to pick the right tool/site faster. Generic LLM execution still does the work. If no sector matches, generic mode handles it. NEVER hardcoded "if construction then click button X" logic.

Sectors v1: construction, sales, job_seeking, healthcare, startup_founder, stay_at_home_parent, pensioner, freelance.

## 11. Failure mode catalog (predicted + defended)

See [RALPH_LOOP](RALPH_LOOP.md) §"Failure classes" for the full 11-class table.

Summary:
- Login walls → SMS user with tab URL
- CAPTCHA → NopeCHA auto-attempt, SMS user if fail
- Network errors → exponential backoff (1m, 5m, 30m, 3h, 24h)
- Rate limits → honor Retry-After header
- Payment required → always SMS user, never autopay
- Account locked → SMS user, never retry
- Element missing → vision fallback + replan
- Cost cap hit → pause + SMS user
- Engine crash → watchdog respawn (already wired via V7 merge) + state recovers from disk
- Power loss / Mac sleep → goal queue resumes on wake (DB-backed `next_attempt_at`)

## 12. Future-proofing (iOS + pendant)

Today: Mac only.

Tomorrow: iOS app + wireless pendant streaming audio to iOS → iOS streams to Mac engine.

Architecture today already supports this:
- Engine exposes an HTTP endpoint for audio ingest (`POST /api/listen/upload` for chunks)
- Add WebSocket endpoint (`/ws/listen/stream`) so iOS can stream live audio chunks
- Engine processes chunks identically whether they come from local mic or remote stream

Eventually: Raspberry Pi running the engine locally for users without a Mac. The engine is already Python+FastAPI, runs on any unix.

## 13. Agent execution rules (the "one agent per thing" rule)

**Right partition:**
- ONE agent = ONE discrete, verifiable outcome
- Example: "Wire chrome.tabs.group() into extension_v4 background.js and prove it creates 'Anticipy' colored blue when extension loads" = one agent
- NEVER: "Build the whole 120s onboarding" (too big)
- NEVER: "Fix all 60 P0 bugs" (too many concurrent file edits)
- NEVER: Two agents on overlapping files

**Serial execution:** agents queue, one finishes (and end-to-end verifies) before next starts. Parallel only for truly read-only research (like the 5 research agents above).

**Verification before "done":** every agent reports back with the artifact + the command to reproduce it. If the agent can't, the work is PARTIAL.

## 14. The 10 phases (each = one verifiable gate)

| Phase | Gate (the EXACT thing that proves done) | Verification command |
|---|---|---|
| 0 | DEV-FINAL is canonical, V7 merged, pushed | `git log --oneline -1 origin/main` shows merge commit + `git remote -v` shows only DEV-FINAL |
| 1 | Extension ↔ engine handshake on owner's Mac | Owner injects "navigate to gmail.com", extension opens gmail.com in Anticipy tab group, engine receives screenshot back, asserts URL contains "mail.google.com" |
| 2 | Unified timeline + popover shows everything | Popover shows last 5 entries from `~/.anticipy/v7/timeline.jsonl` with kind + status + summary, filterable by kind |
| 3 | Generic action executor + Anticipy tab group | Spoken "draft email to {test}@anticipy.ai about Friday demo" via inject API → real Gmail draft visible in Anticipy tab group within 30s, no hardcoded recipe used |
| 4 | Ralph loop end-to-end | Inject test goal that fails twice (network error then ambiguous DOM), Ralph recovers, completes, SMS receipt lands on +16047245161 within 30s |
| 5 | 120s onboarding pipeline | Wipe ~/.anticipy, open Anticipy.app, follow wizard, see dossier populate from Gmail + LinkedIn + Calendar in ≤120s, receive SMS clarification within 60s |
| 6 | Resend email channel | Engine sends test receipt via /api/email/receipt broker, email arrives at omarkebrahim@gmail.com from hello@send.anticipy.ai within 30s, reply routes back to engine timeline |
| 7 | Cost router live | Inject 20 test goals, observe ratio of model calls (DeepSeek 85%, Gemini Flash 8%, Sonar 5%, escalation 2%), avg cost ≤$0.002/task |
| 8 | Sector profiles | Engine loads construction.yaml when Procore detected during scrape, planner uses sector hints in next 3 actions |
| 9 | Fresh-install integration test | Wipe Mac state, download anticipy.ai/app DMG, install, complete onboarding, run 3 sample goals (email draft + calendar invite + web booking), all 3 land successfully with receipts |
| 10 | Investor video recording | After Phase 9 GREEN end-to-end, record 3 demo moments (silent execute, Donna effect, trivia) per [NORTH_STAR](NORTH_STAR.md) |

Each phase only starts when prior phase's GATE is GREEN, verified in PROGRESS_LOG with a real cited artifact.

## 15. Things explicitly OUT of scope for v1

- Native macOS app automation (Apple Mail, Messages, Phone.app)
- Two-way phone calls (agent CALLING people; receiving calls is in scope)
- Voice cloning (user's own voice as TTS)
- Multi-language (English only for v1)
- Windows / Linux desktop
- iOS app (architecture supports it, build comes later)
- Hardware pendant (architecture supports it, build comes later)
- Fine-tuned models (uses off-shelf cost-routed; fine-tune comes after 2k+ users per `RESEARCH/llm-cost-routing.md`)
- Browser other than Chrome (Edge works because Chromium, Safari does not)

## 16. Repositories + branches (canonical)

- **DEV-FINAL** (`~/Developer/Anticipy-DEV-FINAL`) is the ONLY repo going forward
- Branches: `main` (stable trunk) and `deploy/preorder-to-main` (Vercel-live)
- V7 (`~/Developer/Anticipy-V7`) is dead. Delete after Vercel deploy validates the merge.
- Remote: `https://github.com/omize10/Anticipy.git`
- Pre-merge rollback tags: `pre-merge-devfinal-2026-05-30`, `pre-merge-v7-2026-05-30`

## 17. Live infrastructure pointers (state on 2026-05-30)

- Engine sidecar pid 7354 port **49671** (auto-picked because 8731 lock was stale; bug noted for P1-2 cleanup)
- Tauri shell pid 30446
- Bridge pid 10261 (dead code, can be killed)
- Chrome on user's profile with extension loaded (per owner)
- DMG live at https://www.anticipy.ai/dl/Anticipy_1.0.0_aarch64.dmg (SHA 483741a2, ~2.34 GB)
- Twilio Aevoy account, +16196584447, A2P registration pending
- OpenRouter key valid, ~$25 used to date

## 18. Cross-references

- [NORTH_STAR](NORTH_STAR.md) — vision
- [PROGRESS_LOG](PROGRESS_LOG.md) — current state per phase
- [VERIFICATION_PROTOCOL](VERIFICATION_PROTOCOL.md) — DONE rules
- [RALPH_LOOP](RALPH_LOOP.md) — persistence + retry spec
- [CONTEXT_HANDOFF](CONTEXT_HANDOFF.md) — first-read after compaction
- [RESEARCH/chrome-apis.md](RESEARCH/chrome-apis.md) — Chrome Tab Groups + chrome.debugger + native messaging
- [RESEARCH/resend-email.md](RESEARCH/resend-email.md) — Resend DNS + API + cost
- [RESEARCH/agent-loops.md](RESEARCH/agent-loops.md) — browser-use + LangGraph + CrewAI + Open Interpreter + AutoGen + Anthropic patterns
- [RESEARCH/a2p-10dlc.md](RESEARCH/a2p-10dlc.md) — Twilio A2P registration step-by-step
- [RESEARCH/llm-cost-routing.md](RESEARCH/llm-cost-routing.md) — model routing for $0.002/task average

## 19. The owner directive log (memory anchors)

Anchored in `~/.claude/projects/-Users-omarebrahim-Developer-Anticipy-DEV-FINAL/memory/MEMORY.md`:
- No em-dashes
- No 100M% claims
- No fabrication
- No service APIs (browser only, except OpenRouter)
- SMS pre-confirm before irreversible
- No real send testing (drafts only, +16047245161 only for SMS)
- Trivia is a gimmick
- No parallel agents on same files
- Full autonomy on owner's Mac
- Apple-feel polish
- Cost ceiling $200/user/year

Read [MEMORY.md](../../../../.claude/projects/-Users-omarebrahim-Developer-Anticipy-DEV-FINAL/memory/MEMORY.md) for the full index.
