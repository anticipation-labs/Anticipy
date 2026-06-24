# Anticipy

An always-listening assistant: it hears your messy day, infers the real tasks (a vent is **not** a task),
shows you swipeable cards, and acts for you by **driving your real, logged-in Chrome** (the "hands") plus
voice/SMS. **Money is the only hard stop** — it always asks. Browser-only by design (no per-service OAuth).

## 👉 Start here
**Read [`CURRENT_STATE.md`](./CURRENT_STATE.md) first.** It is the single, dated source of truth — what's
done, what's not, *why it keeps failing at the seams*, how to run it, and the history. The ~30 other `.md`
files (and this repo's old "executor-working" Next.js docs) are historical; **CURRENT_STATE supersedes them**
(newest dated wins). The definition of "done" is [`THE_BAR.md`](./THE_BAR.md).

## Layout
- `engine/` — the FastAPI brain + hands + voice + memory (`engine/anticipy_engine/`). Runs locally
  (`:8787`, WITH the hands) and in the cloud (Railway — brain only, no browser there).
- `web/` — the static site/app (Vercel): marketing, onboarding, the card Board.
- `extension/` — the Chrome extension (the hands). **Canonical loadable copy: `~/Desktop/Anticipy-Extension`.**
- `THE_BAR.md` — checkable definition of done. `CURRENT_STATE.md` — where we actually are.

## Run it (local owner, full power)
```bash
bash overnight/restart_engine.sh            # starts the engine on http://127.0.0.1:8787
# Chrome -> chrome://extensions -> Developer mode -> Load unpacked -> ~/Desktop/Anticipy-Extension
open http://127.0.0.1:8787/app.html         # the Board (owner mode skips sign-in; Cmd+Shift+R if it flashes)
```
Test suite: `bash scripts/run_suite.sh`. Live cloud: `https://anticipy-welcome.vercel.app`,
engine `https://engine-production-eb43.up.railway.app`.

## The one thing that wastes everyone's time
Repo/environment chaos — multiple engine trees and 10+ extension copies. **Before trusting any live test,
confirm which tree serves `:8787` and which extension Chrome loaded.** See CURRENT_STATE §5.
