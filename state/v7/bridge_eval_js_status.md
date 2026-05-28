# Bridge eval_js Patch Status

Date: 2026-05-27
Patch: state/v7/patches/bridge_fallback_eval_js.patch
Target: /Users/omarebrahim/.anticipy/anticipy_bridge_fallback.py

## Patch applied

YES. Backup of pre-patch file at /tmp/anticipy_bridge_fallback.py.bak.

The patch file is documentation-wrapped (header + footer prose) so `patch -p1`
rejected it as malformed. The two hunks were applied by hand with the Edit
tool. Result: byte-identical to what the patch describes.

- New `_chrome_eval_js(code)` helper inserted between `_chrome_navigate` and
  `_screencapture`.
- New `if command == "eval_js":` branch inserted in `_handle` immediately
  before the existing `navigate` branch.
- `python3 -c "import ast; ast.parse(...)"` reports SYNTAX_OK.
- No `.rej` files.

## Bridge restarted

Old PID killed via `kill $(lsof -t -iTCP:7777 -sTCP:LISTEN)`. Port confirmed
free, then new bridge launched with `nohup python3 ./anticipy_bridge_fallback.py
> /tmp/bridge_fallback_eval.log 2>&1 &`. New PID 83787, listening on
127.0.0.1:7777. `/status` returns `acquired_via:
chrome_applescript_loopback_bridge`.

## eval_js smoke test

Request:
```
POST /surface-command  {"secret":"local-dev","command":"eval_js","code":"document.title"}
```

Response (ok:false, but the eval_js wiring is correct):
```
{"ok": false, "command": "eval_js", "data": {"result": ""},
 "acquired_via": "chrome_applescript_loopback_bridge",
 "error": "execution error: Google Chrome got an error: Executing JavaScript
  through AppleScript is turned off ... (12) (enable Chrome > View > Developer
  > Allow JavaScript from Apple Events)"}
```

Bridge dispatched osascript, Chrome rejected the script with error (12).
This is KNOWN-BLOCKER: the menu flip below is required.

## KNOWN-BLOCKER: Chrome menu setting

Status: OFF in Omar's current Chrome.

Omar instruction (one line): in Chrome, click View > Developer > Allow
JavaScript from Apple Events, then check it. No restart needed.

After flipping, re-run the smoke test and expect
`{"ok": true, "data": {"result": "<page title>"}, ...}`.

## Background-tab support

NOT SUPPORTED in the fallback bridge. `_chrome_navigate` calls
`tell application "Google Chrome" activate` and then sets
`active tab index of front window to (count of tabs of front window)`, so
even when the request body carries `"background": true`, the bridge ignores
the flag and steals focus.

Smoke result with `"background": true`:
```
{"ok": true, "command": "navigate", "data": {"navigatedTo":
 "https://www.example.com", "url": "https://www.example.com/",
 "title": "Example Domain"}, ...}
```
Chrome did come to the foreground. The bridge has no current code path for
background tabs. Adding it would require dropping the `activate` line and
using `make new tab ... at end of tabs` without setting `active tab index`,
optionally behind a new payload flag. Not in this patch's scope.
