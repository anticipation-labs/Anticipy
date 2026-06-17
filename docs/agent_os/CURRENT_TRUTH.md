# CURRENT TRUTH — mutable; update every run

_Last verified: 2026-06-16 evening PDT, by foreman (Claude Opus 4.8). Gate A CLOSED; browser arm gate landed._

> **This session's headline:** the imported "suite GREEN 90/90" was FALSE — suite was secretly RED
> 86/4 on arrival (4 stale browser tests + 2 real anti-spam bugs from the last refactor). Re-verified,
> fixed, and restored Omar's "prepare when confident" browser behavior. Suite now **GREEN 90/0**,
> `safety_mega_eval` **0 breaches** (independently re-run twice). Commit `f05d453`. Disk freed (cleared
> 6736 stale temp dirs; 334Mi→685Mi). Codex CLI confirmed authenticated.

## Repo map (verified by inspection this session)

| Role | Path | Remote | Branch | State |
|---|---|---|---|---|
| **PRODUCT (autonomous build surface)** | `/Users/omarebrahim/Anticipy` | `omize10/Anticipy-executor-working` | `factory/build` | clean. Full-stack: `app/` (Next.js front, :3000), `engine/` (Python brain, :8787), `macapp/`, `extension/`. This is where the autonomous loop builds. |
| ENGINE (same repo) | `/Users/omarebrahim/Anticipy/engine` | — | — | Python venv at `engine/.venv`. Suite `scripts/run_suite.sh`. |
| WEBSITE / Omar-owned product attempt | `/Users/omarebrahim/Developer/Anticipy-DEV-FINAL` | `omize10/Anticipy` (anticipy.ai source) | `rebuild/spine-clean` | **HANDS-OFF.** Has uncommitted owner work + `.vercel`/`.next`/`desktop/`/`extension_v4`. Do not commit/push/clobber. Wire download→app with Omar. |
| (mirror) | `/Users/omarebrahim/Desktop/Anticipy-executor-working` | symlink → `~/Anticipy` | — | same repo via symlink. |

`WHAT_DEPLOYS_TO_VERCEL` = DEV-FINAL (Omar-owned) — not verified live this session.
`WHAT_BUILDS_DOWNLOAD_APP` = `~/Anticipy/macapp` (an "Anticipy Execute" app is currently running per launchctl: `application.ai.anticipy.execute…`) — packaging/download path NOT yet verified.
`WHAT_STARTS_LOCAL_ENGINE` = `engine/.venv/bin/python -m uvicorn --app-dir engine anticipy_engine.main:app --port 8787`
`WHAT_STARTS_WEB_APP` = Next.js app in `app/` on :3000 (premium reskin landed).

## Toolchain

- Codex CLI: **installed**, `codex-cli 0.133.0` at `~/.local/bin/codex` (verified `CODEX_OK` previously per FOREMAN_STATE).
- node v22.22.0, npm 10.9.4, gh 2.83.2.
- Claude Code = foreman/integrator/skeptic (this agent).

## Concurrency / loop state

- `factory/.lock`: **absent** (no lap running → foreman MAY commit).
- `factory/.halt`: **present** (nightly factory loop intentionally paused since 2026-06-12).
- launchd `com.anticipy.factory`: loaded but halted (won't run a lap while `.halt` exists).

## Live services observed (read-only)

- Engine on `:8787`: **running**, `engine:ok`, `extension_connected:true`, `history_count:39`.
  - ⚠️ `channels.mode=live` (Twilio configured, owner contact configured, inbound live_ready). I did
    NOT start it. **Do not trigger any live text/call to Omar.** Watch-item: confirm with Omar before
    any send; consider restarting channels=mock + inbound poll=0 when unattended.
- "Anticipy Execute" macapp process running (launchctl).

## What is PROVEN (live, from `logs/factory/FOREMAN_STATE.md` + ledgers — re-verify before trusting)

- The **moat** (proactive extraction via funded model) live through `/api/owner/ingest`: a run-on line
  mixing a vent with real tasks catches the real tasks (incl. implied/third-party), silent on the vent,
  money blocked. Context-aware extraction of vague references committed (`e716014`).
- `safety_mega_eval` = **0 BREACHES** (cardinal-sin floor; independently re-run this session, twice).
- Suite **GREEN 90/0** (`scripts/run_suite.sh`), incl. `premium_copy` + `purchase_guard` + the 4
  browser tests fixed this session.
- **Browser arm = "prepare when confident"** (Omar's 2026-06-16 decision, commit `f05d453`): a cart/web
  task auto-prepares (throwaway browser, never buys) when memory/onboarding resolves item+store, with a
  `memory_resolution` receipt; otherwise a deterministic confirm-first texted round-trip.
- Real **Google Calendar** create + read-back + delete proven live (3 test artifacts cleaned).
- A **time-due reminder delivered** to Omar's phone (Twilio SID, status=delivered, exactly one).
- Server-side **onboarding** `/onboard/scan_api` reads real connected accounts (Google Calendar).
- **Premium reskin** landed (charcoal/cream/DM Serif), copy gate clean.
- **Browser-action round-trip** live (`b82e660` HEAD): web task → texted ask → YES → visible browser → result.

## What is NOT proven / open

- `reality_check.py` ceiling ~6/8 (6/7 me-verifiable). Me-verifiable gap historically: inbound-text
  round-trip (needs Omar to text the Anticipy # or a 2nd number — 1 number on account).
- Full-product "download → install → onboard → use" by a **stranger off a real URL** — NOT done.
- Browser arm uses an in-house WebVoyager-style agent, **not** the kit's recommended `browser-use`
  open-source arm — not yet evaluated/decided.
- Model route: not yet re-verified this session (see NEXT_GATE / RESEARCH_LEDGER).

## Genuinely Omar-gated (do NOT fake, do NOT do autonomously)

1. Live channels for 2:45 call / reminder / text (real Twilio to his phone — 31-text history).
2. Off-localhost deploy (exposes his accounts/data publicly — his call; tools installed: cloudflared).
3. The 5 real owner days (the Owner Test).
4. Any push to DEV-FINAL (Omar-owned, uncommitted work present).

## Next gate

See `NEXT_GATE.md`. Currently: **Gate A — Truth & continuity** (this Memory Dock + preflight + route
verify + commit), then the first unproven autonomously-buildable gate.

## Resume commands

```bash
cd /Users/omarebrahim/Anticipy
git status -sb && git log --oneline -5
ls factory/.lock 2>/dev/null && echo "LOCK PRESENT — do not commit" || echo "no lock"
bash scripts/agent_os/preflight.sh
curl -s http://127.0.0.1:8787/status | head -c 400   # read-only
```
