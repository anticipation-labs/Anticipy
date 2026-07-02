> ⚠️ **SUPERSEDED — 2026-07-02.** Historical document. The living truth is **`CANON/00_START_HERE.md`**
> (+ `MISSION_LOCK.md` for live mission status). Do not follow this file's read-order, done-definition,
> or status claims. Indexed with context in `CANON/99_SUPERSEDED_INDEX.md`.

# CURRENT TRUTH — mutable; verified by live command/read-back each run (do NOT trust old docs)

_Last verified: 2026-06-17 PDT, foreman (Claude Opus 4.8). Gate 0 (Current Truth + Read-Back) re-run
from scratch with live commands. Every line below was checked this session, not copied forward._

## Repo / branch / commit (verified `git`)
- Working repo: `/Users/omarebrahim/Anticipy` → remote `omize10/Anticipy-executor-working`, branch
  `factory/build`, commit **`0ee3287`**.
- Dirty: only throwaway scratch (`hunt_*.py`, `hunt_out.json`) — untracked, not part of the product.
- `factory/.lock`: absent (foreman may commit). `factory/.halt`: present (nightly loop paused).

## Product surface (what Omar opens) — verified `curl` + `lsof`
- **Local web app:** `http://localhost:3000` — Next.js 15.5.19 server running (pid live on :3000).
- **App ↔ engine: CONNECTED (verified).** `curl localhost:3000/api/status` proxies through and returns
  the live engine state (`engine:ok`, `extension_connected:true`). The UI is wired to the real brain via
  `app/api/_engine.js` → `ANTICIPY_ENGINE_URL` (default `http://127.0.0.1:8787`).
- **Hosted/Vercel:** project linked (`.vercel/project.json` → `anticipy-executor-working`,
  `prj_BoANZrE5orccFSQr5O212Va7uvPY`). **No live hosted URL verified** — deploy is OWNER-gated.
- **Download app:** `macapp/` ("Anticipy Execute"); packaging/signed-download path NOT verified (OWNER:
  Apple signing).

## Engine — verified `curl localhost:8787/status`
- `engine: ok`, core `control_core`, on **:8787** (uvicorn running).
- history_count 9804, open_loop_count 139, pending_count 860 (durable demo/test data accumulated).
- readiness overall: **`local_mock`**.

## Brain / model route — verified live ("BRAIN ALIVE" smoke)
- provider **`openrouter`** (real base URL `https://openrouter.ai/api/v1/...` in `core/gateway.py`,
  NOT a Gemini misroute). cheap `google/gemini-2.5-flash-lite`, smart `google/gemini-2.5-flash`.
- Live smoke through the real gateway: replied **"BRAIN ALIVE"**, latency **0.69 s**. Funded
  (total_cost $0.259). The old "starved brain / 60 s free-tier 429s" condition is GONE.

## Live / mock / stub map (verified)
| Arm | State | Evidence |
|---|---|---|
| Model (brain) | **LIVE** | OpenRouter smoke 0.69 s "BRAIN ALIVE" |
| API hands | **LIVE** (`api_hands_mode: live`) | `/gateway` |
| Calendar | **LIVE / authorized** | `GoogleCalendar.CreateEvent` Arcade status=**completed** |
| Gmail | **NOT authorized** | `Gmail.WriteDraftEmail` Arcade status=**pending** (OWNER must enable Gmail toolkit / finish consent) |
| Browser arm | **ready** (extension `connected:true`) | `/ws/state`, `/status` browser=ready |
| Voice/Text (Twilio) | **configured, mode=mock** ("ready_to_enable", live OFF) | `/status` channels |
| Proof/read-back | independent read-back wired (`hands/api_hand.py` READ_BACK map; `prove_api_live.py`) | code |

## Proof discipline (Gate-0 requirement)
- API actions prove via an INDEPENDENT read-back by id (not the write's own echo). Calendar
  create→read-back→delete proven previously; re-prove in Gate 4 this run.
- No action is "done" from self-attestation.

## Genuinely OWNER-gated (cannot finish autonomously — do NOT fake)
1. Gmail draft live — enable the Gmail toolkit for the Arcade project (his Arcade login).
2. Two-way live voice / off-localhost — a public URL (deploy/cloudflared) + flip channels live.
3. Hosted deploy on a real URL (his hosting) · signed one-click Mac download (Apple creds).
4. The FIVE real owner days (lived time) — the finish line.

## Current gate
See `NEXT_GATE.md`. Gate 0 CLOSED (this file). On deck: **Gate 1 — product surface opens & talks to
engine, proven in Chrome with a screenshot**, then Gate 3 (messy day through the UI).

## Resume / re-verify commands
```bash
cd /Users/omarebrahim/Anticipy
git rev-parse --abbrev-ref HEAD && git rev-parse --short HEAD
curl -s localhost:8787/status | python3 -m json.tool | head -40
curl -s localhost:8787/gateway
curl -s localhost:3000/api/status | head -c 200   # proves app↔engine
```
