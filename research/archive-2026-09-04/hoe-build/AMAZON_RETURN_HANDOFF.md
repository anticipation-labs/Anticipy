# Amazon-Return Demo — Handoff (2026-06-26, ~6:45 PM)

## THE GOAL (one sentence)
One button labeled **Accept** on the local app that makes the software drive Omar's real
amazon.ca, find the **Aqara 4MP Camera Hub G5 Pro** order, open the return, tick the item,
set **Qty 2** + reason **"Performance or quality not adequate"** + a comment, and **STOP at the
Continue button** (never submit). The card must be **always on the board** on every refresh.
It does NOT need to be scaled, multi-user, or pretty. Just this one flow, reliably, from one button.

---

## WHERE EVERYTHING IS (exact paths on this Mac)

| Thing | Path |
|---|---|
| Engine code | `~/Anticipy/engine/anticipy_engine/` (branch `factory/build`) |
| Running engine | uvicorn PID ~12514, **http://127.0.0.1:8787**, log → **`/tmp/eng.log`** |
| The app page | **http://127.0.0.1:8787/app.html** (served from `~/Anticipy/web/`) |
| Browser hand (LOADED in Chrome) | **`~/Desktop/0-ANTICIPY-EXTENSION-LOAD-ME/`** (a renamed copy; the repo mirror is `~/Anticipy/extension/`) |
| Plan file | `~/.claude/plans/logical-frolicking-lobster.md` |
| Scratchpad (test outputs) | `/private/tmp/claude-501/.../scratchpad` and `/tmp/return_run*.json` |

**How the engine is currently launched** (live texting ON, owner locale .ca, demo card auto-seeded;
NOTE this is NOT `restart_engine.sh`, which keeps texting OFF):
```bash
cd ~/Anticipy/engine
lsof -ti tcp:8787 | xargs kill -9; pkill -9 -f uvicorn; sleep 2
eval "$(grep -E '^(ANTICIPY_MODEL_PROVIDER|OPENROUTER_API_KEY|ANTICIPY_OPENAI_BASE_URL|ANTICIPY_MODEL_CHEAP|ANTICIPY_MODEL_SMART|ANTHROPIC_API_KEY|GEMINI_API_KEY|GOOGLE_API_KEY|CEREBRAS_API_KEY|DEEPSEEK_API_KEY|TWILIO_ACCOUNT_SID|TWILIO_AUTH_TOKEN|TWILIO_FROM|OWNER_PHONE)=' ../.env.local | sed 's/^/export /')"
export ANTICIPY_CHANNELS_MODE=live ANTICIPY_OWNER_TLD=ca ANTICIPY_DEMO_AMAZON_RETURN=1
nohup .venv/bin/python -m uvicorn anticipy_engine.main:app --port 8787 --host 127.0.0.1 >/tmp/eng.log 2>&1 &
```
Twilio creds + OWNER_PHONE live in `~/Anticipy/.env.local`. **Never set `ARCADE_API_KEY`** (API arm = the
old calendar-spam path; we are browser-only).

**Test the flow from the terminal (the way to verify WITHOUT pressing the button — drives his Chrome):**
```bash
curl -s -X POST http://127.0.0.1:8787/agent/run -H 'Content-Type: application/json' \
  -d '{"task":"return the security camera on amazon","start_url":"https://www.amazon.ca/gp/css/order-history","max_steps":24}'
# read .history / .answer / .reached_return_page
```
**Simulate the Accept button:** `POST /resolve {"ask_id":"<card id>","approved":true}` (get the id from
`GET /owner/cards?limit=12`, the `action=="browser_action"` card — deterministic id `br_a9b9ffa338a2cf90f1`).

---

## STATE: what WORKS vs what's FLAKY (honest)

**Proven working (in clean isolated `/agent/run` runs):**
- Routing: any phrasing ("return the security camera on amazon", "get the amazon return…") → the browser
  hand at **amazon.ca/gp/css/order-history**, vents never leak. (committed `21ea94a`)
- The recipe `_try_amazon_return_recipe` reaches **"Choose items to return"**: orders → matches the Aqara
  order → clicks "Return or replace items" → **ticks the item checkbox (idx 61)** → sets **Qty 2**. (proven
  run `return_run8.json`)
- Perception fix (THE big unlock): the extension's `doObserve` cap was 140 elements / 2500 chars — Amazon's
  nav ate the whole budget so it never "saw" the orders. Raised to **600 / 12000** + below-fold window 4000.
- Accept path fires: `/resolve` → `{state:"running"}` and kicks the agent.

**Flaky / NOT solid (the remaining work):**
1. **Reproducibility:** same input sometimes ticks the box + reaches the page, sometimes the form/checkbox
   isn't seen by the observe (async render timing on the real stateful page). Needs a retry/verify loop that
   confirms the checkbox is actually checked (re-observe `state` contains `checked`) before moving on.
2. **"Always there":** the card is auto-seeded at startup and `resolve`/`_land_browser_result_on_card` were
   patched to keep it a reusable "waiting" ask — but it still ends up `state:"failed"` after a run, so it
   drops off the board. The keep-alive guard isn't holding (likely the record's `args.task_text` check, or a
   different code path marks it failed before `_land`). THIS is the main bug to finish for "always there".
3. **My restarts collided with Omar's Accept presses** → his presses hit "unknown/already-resolved" and
   failed. Any verification must be done in an UNINTERRUPTED window (no live presses during a restart).

---

## THE CHANGES MADE THIS SESSION (all uncommitted except 21ea94a / 790e86e / 3c04a14 / 3991c19)

**`engine/anticipy_engine/agent/webvoyager.py`**
- `_try_amazon_return_recipe(task, start_url)` — the whole recipe, registered in `run()` BEFORE
  `_try_commerce_recipe`. Funnel regexes (`RETURN_*_RE`, `RETURN_AD_RE`), `_return_item_text`,
  `_return_unsafe_click` (money/credential/buy hard-stops the recipe re-implements since it bypasses the
  run()-loop guards). Checkbox detected by **`type=="checkbox"`** (its role is "input", not "checkbox").
  Currently "reach + best-effort fill + SUCCEED on /returns/".
- `select` action helper expectation: the extension now supports `{"action":"select","index","value"}`.

**`~/Desktop/0-ANTICIPY-EXTENSION-LOAD-ME/background.js`** (+ mirror `~/Anticipy/extension/background.js`)
- `doObserve`: element cap 140→**600**, text 2500→**12000**, below-fold window 1200→**4000**.
- `doAct`: new **`select`** action (sets a `<select>` by visible option text + dispatches change).
- ⚠️ Reload required in `chrome://extensions` after any edit here.

**`engine/anticipy_engine/core/control_core.py`**
- `_RETURN_TASK` regex + site-action chokepoint also fires on it; `_web_start_url` → orders page in owner
  locale. Chokepoint + `_browser_action_ask` now use **`original_text`** (the user's real words), not the
  moat's rephrase — fixes the nondeterministic "falls back to api arm" bug.
- `_browser_action_ask`: title "Do Amazon return" for amazon returns (note: a title-beautifier elsewhere
  still overrides it to a rephrase — cosmetic, unsolved).
- `resolve`: demo amazon card kept reusable (don't pop pending / don't resolve record) under
  `ANTICIPY_DEMO_AMAZON_RETURN`; texts "handling your Amazon return right now" on Accept.
- `_land_browser_result_on_card`: demo keep-alive (reset to "waiting") — **NOT holding; finish this**.

**`engine/anticipy_engine/main.py`**
- `lifespan`: auto-seed the Amazon-return card on startup (env-gated) so it's on the board every start.

**`web/app.js` / `app.html` / `app.css`**: prominent mic button, **Accept / Deny** labels (was Confirm/Not now).

---

## NEXT STEPS TO FINISH (in order)
1. **Make the checkbox tick verified, not best-effort:** after clicking idx-61, re-observe and confirm the
   box's `state` now contains `checked` (or the Qty/reason fields appeared); retry up to 3× with a 2.5s
   settle; only then proceed. (Partly in place — harden it.)
2. **Make "always there" actually hold:** ensure the demo card record never ends `failed/done` — either fix
   the `_land_browser_result_on_card` keep-alive (verify `args.task_text` matches) OR re-seed the card
   immediately after every run completes. Verify: `GET /owner/cards` shows it `waiting` before AND after a run.
3. **Verify reproducibly in ONE uninterrupted window:** run the Accept path (`/resolve`) 3× back-to-back
   yourself; confirm each time it ticks the box + reaches the Continue page. Omar does not touch the page
   during this.
4. Only after 1–3 are green: hand to Omar to press Accept on `app.html` and film it.

---

## CONTEXT-MANAGEMENT SYSTEM (how I track state across this long session)
- **No DB/state file of my own** — I re-derive truth by reading files + hitting the live engine
  (`/owner/cards`, `/ws/state`, `/agent/run`), never trusting memory of them.
- **Background tasks**: long runs (agent runs, restarts) go to background; results land in
  `/private/tmp/claude-501/.../tasks/<id>.output` and `/tmp/return_run*.json`.
- **Persistent memory** (survives across sessions): `~/.claude/projects/-Users-omarebrahim/memory/`
  (`MEMORY.md` index + one fact per file). The browser-only + done-bar facts are there.
- **Plan file**: `~/.claude/plans/logical-frolicking-lobster.md` (the perception-fix plan).
- **This handoff** + the repo's `logs/factory/` + `CLAUDE.md` are the durable project record.
- When the chat window fills, it's auto-summarized; the summary + this file make the next agent current.
