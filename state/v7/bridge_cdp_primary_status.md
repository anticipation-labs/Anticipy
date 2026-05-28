# Anticipy V7 bridge: CDP-first rewrite status

Date: 2026-05-27
Branch: main (V7 repo)

## What changed

The fallback bridge at `~/.anticipy/anticipy_bridge_fallback.py` was a 314-line
AppleScript-only loopback. It had two real problems:

1. AppleScript `make new tab` activates Chrome and pulls the new tab to the
   foreground. The car cannot navigate while the user is reading another
   tab without yanking focus.
2. AppleScript `execute t javascript` requires Chrome > View > Developer >
   Allow JavaScript from Apple Events, which is a developer-mode-only
   setting that we cannot ship to end users.

The rewrite (903 lines) makes CDP (Chrome DevTools Protocol on
`--remote-debugging-port=9222`) the primary code path and keeps the
AppleScript path as a last-resort fallback for when 9222 is dead.

## Source under version control

The canonical source is now in the repo at
`scripts/v7/anticipy_bridge_fallback_cdp.py`. The live bridge at
`/Users/omarebrahim/.anticipy/anticipy_bridge_fallback.py` is a copy of
that file. To resync after future edits:

```bash
cp /Users/omarebrahim/Developer/Anticipy-V7/scripts/v7/anticipy_bridge_fallback_cdp.py \
   /Users/omarebrahim/.anticipy/anticipy_bridge_fallback.py
kill $(pgrep -f anticipy_bridge_fallback)
( cd ~/.anticipy && nohup python3 ./anticipy_bridge_fallback.py \
  > /Users/omarebrahim/Developer/Anticipy-V7/state/v7/bridge_cdp_primary_logs/bridge_live.log 2>&1 & )
```

The supervisor at `tools/anticipy_supervisor.sh` already restarts the bridge
on liveness failure using the same command form, so no supervisor changes
are needed.

## How CDP-first works

On startup the bridge probes `http://localhost:9222/json/version`. If 9222
responds, every HTTP request that arrives on `:7777` is routed through CDP
(via the `websockets.sync.client` library, which omits the Origin header
that Chrome 148+ rejects under `--remote-allow-origins=http://localhost:*`).

| HTTP endpoint | CDP path |
| --- | --- |
| `GET /status` | returns `bridge_kind: cdp_primary`, `cdp_alive: true` |
| `POST /surface-proof` | `Runtime.evaluate` for URL/title/DOM + `Page.captureScreenshot` |
| `POST /surface-command navigate` | in-place via `Page.navigate` if a tab with the same host exists, else `Target.createTarget {background: true}` |
| `POST /surface-command eval_js` | `Runtime.evaluate` (no Apple Events permission) |
| `POST /surface-command click` | `Runtime.evaluate("document.querySelector(...).click()")` |
| `POST /surface-command type` | `Runtime.evaluate` with native `HTMLInputElement.value` setter + bubbled input/change events |
| `POST /surface-command read/extract` | `Runtime.evaluate` on `outerHTML` + `innerText` |

When 9222 is down at handler time, click/type/read return a clear error
(`"command requires CDP (port 9222) which is not responding"`) and
navigate/eval_js fall through to the AppleScript paths preserved from the
previous bridge.

## Verification

Test harness: `scripts/v7/test_bridge_cdp_primary.sh` (199 lines).

Four checks, all PASS on both dry-run (port 7779, candidate file) and live
(port 7777, installed file) bridges:

1. `status_cdp_primary`: `/status` reports `bridge_kind=cdp_primary` and `cdp_alive=true`
2. `navigate_background`: after `navigate https://example.com/?anticipy_cdp_test=<ts>`, the URL of the frontmost Chrome tab is NOT the navigated URL (no foreground steal)
3. `eval_js_title`: `eval_js("document.title")` returns `Example Domain` via `chrome_cdp_loopback_bridge` (no Apple Events permission needed)
4. `click_selector`: `click "a"` on the example.com tab returns `OK`

Latest live run: `state/v7/test_bridge_cdp_primary_20260527T151845Z/summary.json` (4 PASS, 0 FAIL).

## Live bridge status

Old PID 83787 killed. New PID 97482 running. Confirmed via:

```
curl -s http://127.0.0.1:7777/status
```

returns `bridge_kind: cdp_primary`, `acquired_via: chrome_cdp_loopback_bridge`,
`cdp_alive: true`, `websockets_available: true`.

## Regression risk

The biggest risk is in-place navigation reusing a tab the user is actively
viewing. The bridge prefers in-place when ANY existing page tab has the
same scheme+netloc as the target. If the user has the same host open
themselves (e.g. they navigated to gmail.com manually and the car also
tries to navigate to a different gmail.com URL), the bridge will replace
their tab's URL without their consent. In contrast, `Target.createTarget`
would always create a new background tab.

Mitigations to consider:
- Track which tabs Anticipy created (by `targetId`) and ONLY in-place
  navigate those tabs. Treat user-created tabs as read-only.
- Default `prefer_in_place=False` and let the caller opt in when it knows
  the tab is Anticipy-owned.

For now the bridge defaults to `prefer_in_place=True` to match the existing
test harnesses (which expect ONE saucedemo / juiceshop tab at a time, not a
new tab per step).
