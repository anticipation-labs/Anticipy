# Anticipy — Project Guide

## Directive: scale by distribution, not by centralization (2026-05-20)

"Scale" for Anticipy means: any new user can download the Mac app from anticipy.ai/app and get the same working product Omar has — onboarding, RAG memory, hardware connection, polish. The local engine on each user's Mac IS the product. Privacy moat stays. The website at anticipy.ai is the scalable surface (download host, Supabase auth, model broker, public-facing pages). Do NOT centralize the engine to a cloud service: no Browserbase / Steel cloud browsers, no Groq Whisper / Deepgram server-side ASR, no Cloud Run / Fly.io engine hosts. The Codex handoff (`CLAUDE_CODE_HANDOFF.md`) describes the shipping architecture, not a transitional shape.

What to watch for in code:

- Local engine on `127.0.0.1:8731`, Chrome CDP on `:9222` against the user's own Chrome, `~/.anticipy/` data dir, `parakeet_mlx` ASR in the packaged app, `/Applications/Anticipy.app`, DMG distribution, `install.sh` — all CORRECT.
- Hardcoded Omar-specific paths in shipped code (e.g. `/Users/omarebrahim/.anticipy/chrome-real-clone`, `/tmp/anticipy-omar-flow-home.*`) are scale bugs to fix. Test recipients like `omarkebrahim+anticipy-*@gmail.com` belong only in proof artifacts, never in shipped product code.
- The website (`src/app/`) is the SCALABLE surface. Brand polish, /flash page, /onboarding/* pages, model broker (`/api/engine/model`), Supabase auth/session live here.

---

## Overview
Anticipy is an AI wearable product website (Next.js 14) with an integrated **Action Engine** — a browser-based AI agent that receives plain English instructions and completes real tasks on real websites autonomously.

## Architecture

### Website (Next.js 14 on Vercel)
- **Framework**: Next.js 14 App Router (`src/app/`)
- **Styling**: Tailwind CSS with custom dark/cream/gold theme
- **Database**: Supabase (project "handlit", ref: `ogbxpqkmsdrcuilafycn`)
- **Auth**: Supabase Auth for admin; custom JWT for engine users
- **Key pages**: `/` (marketing), `/waitlist`, `/admin`, `/engine`

### Action Engine (Python FastAPI)
- **Location**: `/engine/` directory at project root
- **Runtime**: Python 3.12 + Playwright Chromium
- **Communication**: WebSocket for real-time task streaming
- **Browser agent**: Browser Use framework (open source, github.com/browser-use/browser-use)
- **LLM**: Gemini 2.5 Flash (primary) → Groq Llama 4 Scout (fallback)
- **CAPTCHA**: NopeCHA extension (free) + playwright-recaptcha (free)
- **Anti-bot**: Patchright stealth + headful Chrome + human-like delays
- **Design**: Browser Use handles observation, element extraction, and action execution. Safety, streaming, and cookies managed by our wrapper.

## Environment Variables
```
# Supabase
NEXT_PUBLIC_SUPABASE_URL
NEXT_PUBLIC_SUPABASE_ANON_KEY
SUPABASE_SERVICE_ROLE_KEY

# LLM Providers
GOOGLE_API_KEY        # Gemini (primary)
GROQ_API_KEY          # Groq (fallback)
DEEPSEEK_API_KEY      # Currently no credits

# CAPTCHA
TWOCAPTCHA_API_KEY
CAPSOLVER_API_KEY

# Engine
NEXT_PUBLIC_ENGINE_URL  # Backend URL for frontend
PROFILE_ENCRYPTION_KEY  # Fernet key for cookie encryption
```

## Running Locally

### Website
```bash
npm run dev
```

### Engine Backend
```bash
cd engine
export DISPLAY=:99
Xvfb :99 -screen 0 1920x1080x24 &
export $(grep -v '^#' ../.env.local | xargs)
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### Access the Engine
1. Go to `/engine`
2. Enter access code: `123`
3. Create account or log in
4. Start chatting with the agent

### Test
```bash
cd engine
DISPLAY=:99 python test_real.py  # 10 real-world tests, target 9/10
```

## Engine Design Philosophy

1. **NO hardcoded website logic** — Browser Use reads pages generically via DOM + screenshots
2. **Single model sufficiency** — works with just Gemini OR just Groq
3. **Zero technical leakage** — user never sees JSON, API errors, model names
4. **Browser Use does the heavy lifting** — DOM extraction, element interaction, planning, loop detection
5. **Budget limits are code** — 40 steps, 300 seconds per task. Python enforced, not AI enforced.

## Database Tables

### Existing
- `anticipy_waitlist` — email signups
- `anticipy_admin_users` — admin access

### Engine
- `engine_users` — engine user accounts (username/password, bcrypt hashed)
- `browser_profiles` — saved cookies per user per site (Fernet encrypted)
- `engine_tasks` — task history with action logs

## Key Files
- `src/components/Footer.tsx` — has subtle "Engine" link
- `src/app/engine/page.tsx` — engine chat interface
- `engine/app/main.py` — FastAPI server, WebSocket handler, rate limiting
- `engine/app/agent.py` — Browser Use integration wrapper (core)
- `engine/app/models.py` — LLM wrapper with fallback chain (used for classification/planning)
- `engine/app/safety.py` — deterministic safety rules (blocked actions, confirmation)
- `engine/app/messages.py` — all user-facing message templates
- `engine/app/config.py` — env vars, budget limits
- `engine/app/auth.py` — bcrypt auth, JWT tokens, login rate limiting
- `engine/app/router.py` — task classification (chat/question/action)
- `engine/app/planner.py` — goal decomposition and URL extraction
- `engine/app/browser.py` — legacy browser manager (kept for reference)
- `engine/app/harness.py` — legacy observation compression (kept for reference)

## Known Limitations
- Canvas-heavy apps (Google Sheets, Figma) have limited interaction
- DataDome/Akamai on high-security sites may block datacenter IPs
- Some SPA form implementations may resist automated input
- Phase 2 will add user-device fallback for blocked sites

## Conventions
- Import alias: `@/` → `./src/`
- Components: PascalCase, named exports
- Client components: `"use client"` directive
- CSS: Tailwind utilities + CSS variables from globals.css
- Colors: dark (#0C0C0C), cream (#F5F0EB), gold (#C8A97E)

---

## Canonical local path (added 2026-05-13)

The local working copy lives at **`/Users/omarebrahim/Developer/Anticipy-DEV-FINAL`** — NOT `~/Desktop/Anticipy-DEV-FINAL`. Reason: `~/Desktop` is governed by macOS `fileproviderd` even when iCloud Drive's "Desktop & Documents Folders" toggle is off, and any path under it can re-enter the FPCK queue and become slow again. `~/Developer/` is plain local.

If a script or doc references the old `~/Desktop/Anticipy-DEV-FINAL` path, treat it as a soft alias for the new path.

---

## Terminal & git operational rules (added 2026-05-13)

Full diagnostic + root-cause analysis in `.anticipy/TERMINAL_DEBUG.md`. Read that before re-attempting any terminal/git debugging in this repo.

1. **NEVER `git commit -m "…"` inline if the message was copied from a chat tool.** Chat tools rewrite straight `"` → curly `"` `"` and `-` → em-dash. zsh's `"…"` parser only recognises ASCII 0x22 quotes, so an "opening" curly `"` is treated literally and the shell waits forever for a closing `"` (the `>` continuation prompt). Use `gcmsg "the message"` (defined in `~/.zshrc`) — it sed-normalises curly→ASCII and dashes→hyphens, then commits via `git commit -F`. Or pass `-F /tmp/msg.txt` directly.

2. **NEVER `kill -9` a running `git` mid-write.** It leaves `.git/index.lock` (or a 0-byte `.git/index`). Use `kill` (SIGTERM) first, wait 5 s, only then `-9`. After `-9`, run `cleanstale` (defined in `~/.zshrc`) — it removes any stale lock in CWD's repo.

3. **Run `cleanstale` between Claude Code sessions.** Kills leftover `mcp-server-*` and stale CLT git processes, removes any `.git/index.lock` in CWD.

4. **A new top-level dir with > 1 000 files MUST be in `.gitignore` before it's created.** Already covered: `node_modules`, `engine/.venv/`, `.venv/`, `.next/`, `.anticipy/models/`, `.anticipy/*.db`, `.anticipy/*.wav`, `.anticipy/*.npy`.

5. **VS Code git extension polls this repo with `git ls-files --recurse-submodules` constantly.** While the v-final-prototype build is hot, either close the workspace or set `"git.enabled": false` in `.vscode/settings.json` for this workspace.

6. **Desktop & Documents Folders iCloud sync must stay OFF.** System Settings → Apple ID → iCloud → Drive → "Sync this Mac" → "Desktop & Documents Folders" → off. When that toggle is on, macOS `fileproviderd` runs a continuous `FPCKTask` (File Provider Consistency Check) over every file in `~/Desktop`, which throttles every read to ~1 s/file. With 598 tracked files, `git status` walks for 10+ minutes. Verified at the kernel level via `sample <git-pid>` showing 100% of git's time in `cmd_status → refresh_index → ie_modified → index_fd → read_in_full → xread → read()`. Repo lives under `~/Developer/` precisely to keep it outside `fileproviderd`'s scope.

7. **If `git status` ever hangs > 10 s**: `sample <git-pid> 1`. If the stack shows `index_fd → read`, FPCK is throttling — confirm Desktop & Documents iCloud toggle is OFF, and confirm the working copy is at `~/Developer/Anticipy-DEV-FINAL`. If the stack shows `lstat` only, root cause is different — log it in `.anticipy/TERMINAL_DEBUG.md`.

8. **Local git perf config is already set** in `.git/config`: `core.untrackedCache=true`, `core.preloadIndex=true`, `core.fsmonitor=false`, `feature.manyFiles=true`, `gc.auto=256`. Re-apply after any fresh clone.
