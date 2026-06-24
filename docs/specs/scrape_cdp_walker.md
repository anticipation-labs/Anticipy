# Integration spec — onboarding account-scrape via a CDP walker

**Goal.** Port DEV-FINAL's cold-start CDP walker into `~/Anticipy` so onboarding can inhale
visible row metadata (Gmail inbox/sent, Calendar agenda, Drive recents, generic mail
surfaces) from the user's *already-logged-in* Chrome — and wire it to **this repo's existing
`:9222` direct-CDP path**, NOT DEV-FINAL's separate `127.0.0.1:7777` bridge.

**One-line architecture decision.** `~/Anticipy`'s `native_bridge_link.py` already talks
direct CDP to Chrome on `:9222` (lists targets via `/json/list`, opens a websocket to a page
target's `webSocketDebuggerUrl`, drives `Runtime.evaluate` / `Input.dispatchMouseEvent`).
That is the *same* mechanism DEV-FINAL's walker uses for tab create + eval. So we keep the
walker's CDP layer and **delete its 7777 HTTP-bridge layer** — the walker reaches Chrome the
same way the rest of this engine already does.

---

## Source files (read + cited)

### A. `~/Developer/Anticipy-DEV-FINAL/engine/app/coldstart/cdp_walker.py` (the walker to port)
- Module docstring claims it talks to the `127.0.0.1:7777` bridge (lines 3–5) — **this framing
  is what we drop.** In practice its *page* operations already go straight to `:9222`.
- `BRIDGE_*` constants (lines 41–47) and `_http_json` / `_bridge_alive` / `_bridge_command`
  (lines 75–122) — **the 7777 layer. DROP entirely.**
- `CDP_*` constants (lines 49–54), `_cdp_list_pages` (125–136), `_cdp_close` (139–149),
  `_cdp_create_new_tab` (152–184, PUT-then-GET on `/json/new`), `_cdp_eval_on_target`
  (187–237, websocket `Runtime.evaluate`) — **the `:9222` layer. KEEP, re-point to this repo's
  env vars.**
- `WalkerRow` dataclass (57–69) — KEEP as-is (plain dict rows for the LLM extractor).
- Class `CDPWalker` (243–627): `MAX_ROWS_PER_SURFACE` (261); `bridge_ready` (268–270, **rewrite**
  to a `:9222` `/json/version` probe — see Adaptation 3); `close_all` (272–279);
  `_open_anticipy_tab` (282–294); `_wait_for_dom_ready` (296–315); `_scroll_and_collect`
  (317–369).
- **Functions to port (the four walks + the generic dispatcher):**
  - `walk_gmail` — lines **412–460** (inbox/sent; `_GMAIL_COLLECT_JS` at 376–410, generic
    `[role="row"]`/`tr.zA` heuristic, no Gmail-class hardcoding).
  - `walk_calendar` — lines **480–522** (`_CAL_COLLECT_JS` at 463–478).
  - `walk_drive` — lines **544–580** (`_DRIVE_COLLECT_JS` at 525–542).
  - `walk_source` — lines **584–627** (the generic dispatcher keyed off `source["id"]`:
    `calendar`→calendar, `drive`/`files`→drive, else→gmail row-walker). This is the entry
    point onboarding calls per enabled source.
- `__all__` (630–635).

### B. `~/Developer/Anticipy-DEV-FINAL/engine/app/action_engine/cdp_dispatcher.py` (the CDP primitives reference)
- `_list_targets` (97–101) and `_new_target` (103–106) — `httpx.get`/`httpx.put` against
  `/json/list` and `/json/new`. The walker uses `urllib` for the same thing; either works.
- **`connect_to_chrome`** — lines **109–149**: attach a websocket to a target on `:9222`
  (`webSocketDebuggerUrl`), enable `Page`/`Runtime`. **Port this** as the canonical
  "attach to an existing logged-in tab" helper the walker reuses (avoids re-implementing
  target selection).
- **`humanlike_*`** primitives (the politeness layer that makes scraping look human and avoids
  tripping bot heuristics on Google surfaces):
  - `humanlike_click` — lines **155–190** (Bezier move + Gaussian-timed press/release).
  - `humanlike_type` — lines **193–204** (per-char Gaussian delays).
  - `humanlike_key` — lines **207–213** (combo key down/reverse-up).
  - `humanlike_scroll` — lines **216–230** (chunked `mouseWheel`, 100–300px, Gaussian gaps).
    Use this to **replace the raw `scrollBy` eval inside `_scroll_and_collect` (cdp_walker.py
    361–367)** so the inhale scroll is humanlike too.
  - These depend on `humanlike.py` (`MotionPoint`, `bezier_path`, `gaussian_delay`,
    `typing_inter_char_delays`) — import at `cdp_dispatcher.py:37–42`, defined in
    `~/Developer/Anticipy-DEV-FINAL/engine/app/action_engine/humanlike.py` (class at 21,
    funcs at 27/80/93). **Port `humanlike.py` verbatim** alongside.
- `CDPSession` (53–94), `_next_id`/`send`/`close` — port if you reuse `connect_to_chrome`
  (it returns a `CDPSession`). `dispatch_fara_action` (283–340) and `RefusalSignal` (47–51)
  are **NOT needed** for scrape (Fara action-loop, out of scope).

---

## Target files (read + cited)

### C. `~/Anticipy/engine/anticipy_engine/core/native_bridge_link.py` (the existing `:9222` talker — the pattern to mirror)
This file is the proof that `~/Anticipy` already speaks direct CDP to `:9222`; the walker
must follow the SAME conventions, not invent new ones:
- CDP host/port read from env: `self.cdp_host = ANTICIPY_CDP_HOST` (default `localhost`),
  `self.cdp_port = ANTICIPY_CDP_PORT` (default `9222`) — lines **237–238**. **The walker MUST
  read these same two env vars** (DEV-FINAL already uses identical names at
  `cdp_walker.py:50–53`, so this is a clean match — confirm, don't fork).
- `_cdp_page_ws_url` — lines **436–455**: GET `http://{host}:{port}/json/list`, filter
  `type=="page"`, choose by stored `targetId` / `url_prefix` / last page, and normalize
  `127.0.0.1`→`localhost` in the WS URL. **Reuse this selection logic** when the walker needs
  to attach to an existing tab instead of opening a fresh one.
- `_cdp_up` — lines **859–867**: `/json/version` liveness probe with a 0.8s timeout. **This is
  the body for the walker's rewritten `bridge_ready()`** (Adaptation 3).
- `_trusted_cdp_click_async` (457–572) and `_direct_cdp_proof_async` (920–1071): the canonical
  in-repo `websockets.connect(...)` + `Runtime.evaluate` call pattern (id-correlated `call()`
  helper, `max_size`, `open_timeout`, `ping_interval=None`). DEV-FINAL's
  `_cdp_eval_on_target` (cdp_walker.py 187–237) is the synchronous twin of this — keep the
  walker's sync version (simpler for a threaded inhale), just confirm the `ws://localhost:{port}`
  URL is built from the env-derived port.
- `_ensure_cdp_chrome` (817–857) launches Chrome with `--remote-debugging-port`,
  `--user-data-dir=~/.anticipy/chrome-real-clone`, `--profile-directory=Default`. **The walker
  does NOT launch Chrome** — it assumes the engine (control_core / native bridge) already did,
  and just attaches. If `bridge_ready()` is False, return `[]` and surface a needs-human/"open
  Chrome" reason; never spawn a second Chrome.

### D. How `~/Anticipy` talks to CDP `:9222` today (the wiring the walker plugs into)
- `~/Anticipy/engine/anticipy_engine/core/control_core.py:636–637` instantiates
  `NativeBridgeLink()` (gated by `ANTICIPY_NATIVE_BRIDGE_FALLBACK`, default on) and stores it as
  `self.native_bridge_link`; passed to `BrowserHand(..., fallback_link=native_bridge)` (≈644).
- `BrowserHand._active_link` (`hands/browser_hand.py:141–145`) prefers the extension
  `BrowserLink`, else the native bridge. The walker sits **beside** this, used by onboarding —
  it is a read-only scraper, not an action hand, so it does not go through `send_browse`.
- Onboarding entry today: `~/Anticipy/engine/anticipy_engine/onboarding/connection_scan.py`
  maps a *DOM scan* dict (`{service, logged_in, identifier, url}`) into the mesh via
  `scan_to_onboarding` (lines 38–89). **The walker becomes the engine-side producer of richer
  per-surface rows** that this onboarding flow can consume (people/projects/tools extraction),
  complementing the connection scan.

---

## Port plan — files to create in `~/Anticipy`

```
engine/anticipy_engine/onboarding/
  cdp_walker.py     # ported CDPWalker + WalkerRow, 7777 layer removed, :9222 re-pointed
  humanlike.py      # verbatim from DEV-FINAL action_engine/humanlike.py
  cdp_primitives.py # connect_to_chrome + CDPSession + humanlike_* (subset of cdp_dispatcher.py)
  sources/          # optional: port DEV-FINAL coldstart/sources/ (gmail/calendar/drive) OR
                    # feed walk_source() dicts from ~/.anticipy/inhale_sources.json directly
```

Exact functions to port:
- From `cdp_walker.py`: `CDPWalker` (incl. `walk_gmail`, `walk_calendar`, `walk_drive`,
  `walk_source`, `_open_anticipy_tab`, `_wait_for_dom_ready`, `_scroll_and_collect`,
  `close_all`, rewritten `bridge_ready`), `WalkerRow`, the three `_*_COLLECT_JS` blobs, and the
  `_cdp_*` helpers (`_cdp_list_pages`, `_cdp_close`, `_cdp_create_new_tab`, `_cdp_eval_on_target`).
- From `cdp_dispatcher.py`: `connect_to_chrome`, `CDPSession`, `humanlike_click`,
  `humanlike_type`, `humanlike_key`, `humanlike_scroll` (+ `_list_targets`, `_new_target`).
- From `humanlike.py`: `MotionPoint`, `bezier_path`, `gaussian_delay`, `typing_inter_char_delays`.

## pip dependencies
- `httpx`, `numpy`, `websockets` — **all three already installed** in
  `~/Anticipy/engine/.venv` (httpx 0.28.1, numpy 2.4.6, websockets 16.0). No new installs.
  (DEV-FINAL's walker itself uses only stdlib `urllib`/`json`; `httpx`/`numpy` come in with the
  `humanlike_*` primitives and `cdp_dispatcher` helpers. Add them to `engine/requirements.txt`
  if not pinned there.)

## Precise adaptation points
1. **Delete the 7777 bridge layer** in the ported `cdp_walker.py`: remove `BRIDGE_HOST/PORT/
   URL/SECRET` (DEV-FINAL lines 41–47), `_http_json` (75–101), `_bridge_alive` (104–108),
   `_bridge_command` (111–122). Nothing in the walk paths calls them once `bridge_ready` is
   rewritten — only the dropped `bridge_ready→_bridge_alive` did.
2. **Re-point CDP env vars** to this repo's convention (which already matches): keep
   `ANTICIPY_CDP_HOST` (default `localhost`) and `ANTICIPY_CDP_PORT` (default `9222`) exactly as
   `native_bridge_link.py:237–238` reads them. Build the eval WS URL as
   `ws://{ANTICIPY_CDP_HOST}:{ANTICIPY_CDP_PORT}/devtools/page/{target_id}` and normalize
   `127.0.0.1`→`localhost` (mirror `native_bridge_link.py:455`).
3. **Rewrite `CDPWalker.bridge_ready()`** (DEV-FINAL 268–270) to probe
   `GET http://{host}:{port}/json/version` with a ~0.8s timeout — copy `_cdp_up`
   (`native_bridge_link.py:859–867`). No 7777 `/status` call.
4. **Humanlike scroll**: in `_scroll_and_collect`, replace the raw `scrollBy` eval
   (cdp_walker.py 361–367) with `humanlike_scroll` over an attached `CDPSession` so the inhale
   scroll uses Bezier/Gaussian timing like the rest of the engine.
5. **Tab attach vs create**: keep `_cdp_create_new_tab` for Anticipy-owned background tabs
   (the safe default — never hijacks the user's active tab, closes on exit via `close_all`).
   When onboarding wants to read a tab the user already has open, use the `connect_to_chrome` /
   `_cdp_page_ws_url` selection logic instead of opening a new tab.
6. **No Chrome launch from the walker**: if `bridge_ready()` is False, return `[]` + a
   "Chrome not reachable on :9222" reason. Lifecycle (launching the real-clone Chrome) stays
   owned by `native_bridge_link._ensure_cdp_chrome` / control_core.
7. **Sources config**: feed `walk_source()` dicts (`{id, url}`) from
   `~/.anticipy/inhale_sources.json` (DEV-FINAL convention) — no URL literals in code. Wire the
   resulting `WalkerRow`s into the onboarding profile builder
   (`onboarding/profile_builder.py`) / `connection_scan.scan_to_onboarding` path.
8. **Navigation wall reuse**: before opening any source URL, pass it through this repo's
   `core/navwall.nav_block_reason` (already imported by `native_bridge_link.py:27`) so the
   scraper honors the same SSRF/credential-domain wall as the action hand.

## What Omar must do himself (human-in-the-loop)
- **Be logged into his own accounts** (Gmail, Google Calendar, Google Drive, plus any other
  enabled source) in the controlled Chrome (`~/.anticipy/chrome-real-clone`, started with
  `--remote-debugging-port=9222`). The walker only reads what an already-authenticated session
  renders.
- **The walker NEVER auto-types credentials and NEVER solves captchas/2FA.** If a source URL
  lands on a login/consent/captcha wall, the walk returns no rows and the flow pauses and texts
  Omar to log in, then resumes (the existing wall-handoff design) — it does not type creds or
  click through auth.
- **Decide which sources to enable** in `~/.anticipy/inhale_sources.json` (the URLs it walks).
- **No bodies, no checkout, no send**: the walker reads visible row metadata only
  (sender/subject/snippet/date, event labels, file names); it performs no money or send actions.

---
SUMMARY (5 lines):
1. Port DEV-FINAL's `CDPWalker` (`walk_gmail`/`walk_calendar`/`walk_drive`/`walk_source`) plus the `humanlike_*` primitives and `connect_to_chrome` into `~/Anticipy/engine/anticipy_engine/onboarding/`.
2. Keep the walker's `:9222` direct-CDP layer; DELETE its `127.0.0.1:7777` HTTP-bridge layer — this repo's `native_bridge_link.py` already proves `:9222` direct CDP is the in-repo path.
3. Re-point to existing env vars `ANTICIPY_CDP_HOST`/`ANTICIPY_CDP_PORT` (already a match), rewrite `bridge_ready()` to copy `native_bridge_link._cdp_up`'s `/json/version` probe, and route URLs through `navwall.nav_block_reason`.
4. Deps `httpx`/`numpy`/`websockets` are ALL already in `engine/.venv` — no installs; just pin them in `engine/requirements.txt`.
5. Omar must stay logged into his accounts in the `:9222` Chrome; the walker never auto-types creds or solves captchas — it reads visible rows only and pauses-to-text on any auth wall.
