# Context Handoff — read this FIRST after compaction or session start

**You are reading this because:** the previous session was compacted, or you are picking up fresh. Everything you need to continue is in this file or files it links to. Trust files, not memory.

---

## In 30 seconds, what is Anticipy?

> Anticipy listens to your day, anticipates what you need, and silently does it for you. From construction worker to CEO, anyone downloads it from anticipy.ai/app and within 120 seconds it knows them, their people, and their tools. It works inside their real Chrome via extension and chrome.debugger (never raw APIs), costs under $200 a year, and follows through on every task across days and weeks without losing the thread. It feels like Donna from Suits, a real human at your side who just gets it done.

3-word loop: **Listen. Anticipate. Act.**

## Where am I (the repo, the branch, the engine)

- **Repo:** `/Users/omarebrahim/Developer/Anticipy-DEV-FINAL` (the ONE canonical repo, V7 is dead)
- **Branch:** `deploy/preorder-to-main` (or `main`, both at HEAD `fac316d5` as of 2026-05-30)
- **GitHub:** `https://github.com/omize10/Anticipy.git`
- **Pre-merge rollback tags:** `pre-merge-devfinal-2026-05-30`, `pre-merge-v7-2026-05-30`
- **Engine sidecar (live as of 2026-05-30 15:00 PDT):** pid 7354, port **49671** (NOT 8731 — stale lock at start of session; bug noted for cleanup in P1-2). To find current port: `cat ~/.anticipy/engine.port`.
- **Tauri shell:** pid 30446
- **Chrome:** owner has extension loaded (per his confirmation, handshake unverified end-to-end yet)
- **DMG live URL:** https://www.anticipy.ai/dl/Anticipy_1.0.0_aarch64.dmg (SHA `483741a2`, ~2.34 GB)

## Order of reading (DO THIS)

1. **This file** (you are here)
2. **[NORTH_STAR.md](NORTH_STAR.md)** — the 4-sentence vision + non-negotiables (1 page)
3. **[PROGRESS_LOG.md](PROGRESS_LOG.md)** — what's DONE/PARTIAL/QUEUED with cited verification proofs
4. **[VERIFICATION_PROTOCOL.md](VERIFICATION_PROTOCOL.md)** — the rules that prevent lying-to-yourself about DONE
5. **[ARCHITECTURE.md](ARCHITECTURE.md)** — the engineering bible (read in full before any code change)
6. **[RALPH_LOOP.md](RALPH_LOOP.md)** — the persistence + retry + recovery spec
7. **[RESEARCH/](RESEARCH/)** — 5 research files (Chrome APIs, Resend, agent loops, A2P, LLM cost). Read whichever is relevant to current work.
8. **[MASTER_HANDOFF.md](MASTER_HANDOFF.md)** — earlier comprehensive snapshot (still useful for historical context)

## Owner directives (memory anchors — never violate)

Read the full index: `~/.claude/projects/-Users-omarebrahim-Developer-Anticipy-DEV-FINAL/memory/MEMORY.md`

Top 12 rules to keep forefront:
1. **No em-dashes** anywhere user-visible. Periods, commas, parens only.
2. **No 100M% claims.** Never say "done" or "shipped" while red gates exist.
3. **No fabrication.** Real artifacts only. Run the command, paste the output.
4. **No service APIs.** Browser via extension + chrome.debugger only. Exception: OpenRouter (LLM), Twilio (SMS/voice), Resend (email), Perplexity Sonar (trivia lookup).
5. **SMS pre-confirm** before any irreversible action. Default to draft on no reply within window.
6. **No real send testing.** Drafts only. SMS only to +16047245161 (owner) or omarkebrahim+anticipy-*@gmail.com.
7. **Trivia is a gimmick.** 30-second closer at the END of a demo. Silent execute + Donna effect are the headline.
8. **No parallel agents on same files.** Serialize, or coordinate. Race conflicts wasted hours of demo prep.
9. **Full autonomy on owner's Mac.** Don't ask permission to kill processes, install apps, modify /Applications, etc.
10. **Apple-feel polish.** Every surface. Plain human English. Real voice TTS. Smooth animations.
11. **Cost ceiling $200/user/year.** $0.002/task average. Prompt caching mandatory.
12. **Persistent follow-through.** Anticipy owns tasks across restarts/days/weeks. Like Donna.

## What was just done in the session that compacted

If this file is being read because the prior session was compacted, the most recent work was:

**Phase 0 cleanup (2026-05-30):**
- Merged V7 main (337 commits) into DEV-FINAL (commit `0a5fb008`, rewritten to `fac316d5` after history cleanup)
- Stripped 2.4GB DMG blob from V7's `c2c34914` via `git filter-repo`
- Redacted Twilio SIDs (`AC...`, `SK...`, `CA...`, `SM...`) across all 1249 commits
- Force-pushed `main` and `deploy/preorder-to-main` (Vercel redeploying)
- Tests: 20 passed, 1 skipped (in `engine/tests/`)
- All 17 critical Python modules import clean
- Pre-merge tags preserved

**Planning docs written (2026-05-30):**
- NORTH_STAR.md (this file's neighbor)
- VERIFICATION_PROTOCOL.md
- RALPH_LOOP.md
- ARCHITECTURE.md
- This file (CONTEXT_HANDOFF.md)
- 5 RESEARCH/ files

**Next phase to start:** Phase 1 per ARCHITECTURE.md §14 — Extension ↔ engine handshake on owner's Mac. Gate: owner injects "navigate to gmail.com", extension opens it in Anticipy tab group, engine receives screenshot, asserts URL contains "mail.google.com".

## Active background agents (if any are still running)

Check `/private/tmp/claude-501/-Users-omarebrahim-Developer-Anticipy-DEV-FINAL/f0491f60-df8c-4801-9ccb-8af58a257677/tasks/` for task output files.

If you see any background bash poll loops still alive (`pgrep -fl "anticipy-dmg-changed\|until \[" ...`), they may be zombies from the compacted session — safe to kill.

## Computer-use grants (so you can drive the Mac)

Already granted to current session: Google Chrome (read tier), System Settings, Finder, Calendar, Mail, Notes, Terminal (click tier), VS Code (click tier). Anticipy.app denied by MCP's installed-check (drive its popover via cliclick on tray coordinates).

Re-grant by calling `mcp__computer-use__request_access` with the app list.

For Chrome (which is tier "read"), use `mcp__claude-in-chrome__*` tools instead.

## Things explicitly NOT done yet (do not claim them)

- Phase 1 extension handshake (the next gate)
- Phase 2 unified timeline UI
- Phase 3 generic action executor (still has hardcoded recipes)
- Phase 4 Ralph loop implementation
- Phase 5 120s onboarding pipeline
- Phase 6 Resend email channel (research complete, code not written)
- Phase 7 cost-efficient routing (research complete, code not written)
- Phase 8 sector profiles
- Phase 9 fresh-install integration test
- Phase 10 investor video

## How to verify the current state (do this on session start)

```bash
# Repo + branch
cd /Users/omarebrahim/Developer/Anticipy-DEV-FINAL
git branch --show-current
git log --oneline -3

# Engine alive on whatever port it picked
PORT=$(cat ~/.anticipy/engine.port)
curl -s http://127.0.0.1:$PORT/health
curl -s http://127.0.0.1:$PORT/api/state | python3 -c "
import json,sys; d=json.load(sys.stdin)
print('key_ok:', d.get('key_ok'), '| listening:', d.get('listening'), '| browser_surface:', d.get('browser_surface'))
"

# DMG fresh on R2
curl -sI https://www.anticipy.ai/dl/Anticipy_1.0.0_aarch64.dmg | grep -i content-length
```

Expected outputs:
- branch: `deploy/preorder-to-main` or `main`
- HEAD: `fac316d5` or later
- engine: `{"ok":true, ...}`
- state: `key_ok: True`, `browser_surface: extension_native_bridge`
- DMG content-length: `2516712351` (the new SHA `483741a2`)

If any of these don't match, the state has drifted since this handoff was written. Investigate before continuing.

## The most important rule of all

**The DONE column in [PROGRESS_LOG.md](PROGRESS_LOG.md) is the only source of truth about what's done.** Not your memory. Not agent reports. Not what was said in chat. Just that table with cited proofs.

If you can't cite a verification artifact, the row is PARTIAL. Always.
