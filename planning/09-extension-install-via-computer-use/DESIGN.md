# Extension install via computer-use

Owner: Omar. Drafted 2026-05-29. The prior planner deferred this work behind the false claim "we cannot inject a Chrome extension into the user's already-running Chrome." Wrong. Anticipy has computer-use via `mcp__computer-use__*`. The agent can drive the user's Mac end-to-end: open Chrome, type into the omnibar, click toggles, drag files, navigate Finder dialogs. The extension at `extension_v4/manifest.json` ships in the DMG. The missing piece is install automation, not Chrome capability.

## 1. Problem precisely stated

Anticipy drives the user's real Chrome on port 9222 via CDP. Without the extension, the bridge at `scripts/v7/anticipy_bridge_fallback_cdp.py:528-554` calls `_cdp_navigate(url, prefer_in_place=True)`, which finds any tab matching the URL's scheme+host and reuses it via `Page.navigate`. If the user has Gmail open in tab 3 and the agent goes to `mail.google.com/mail/u/0/#inbox`, the agent overwrites their open compose, scroll position, and read state. The tab hijack bug. User opens laptop, sees their Gmail draft changed under their hands, trust dies in a single frame.

The fix exists. `extension_v4/background.js:504-517` implements `ensureGroupWith(tabId)`: `chrome.tabs.group({ tabIds: [tabId] })` then `chrome.tabGroups.update(groupId, { title: "Anticipy", color: "blue" })`. Every Anticipy tab lands in a blue "Anticipy" group at the right of the strip; user tabs sit untouched at the left. The only missing input is loading the extension.

The prior excuse, "we can't inject," conflates two facts. We cannot programmatically write the extension ID into `~/Library/Application Support/Google/Chrome/Default/Preferences` (the `extensions.settings` block is HMAC-signed, Chrome wipes tampered entries on next start). True. But computer-use does what a human does: click through `chrome://extensions`, toggle Developer Mode, click "Load unpacked," select the folder. Chrome treats a synthetic `mcp__computer-use__left_click` identically to a human finger. The OS does not distinguish.

## 2. Computer-use install flow at first launch

Triggered by `engine/app/product/main.py` after the engine binds port 8731, before the popover opens:

1. Probe CDP on `:9222/json/version` and walk `chrome.management.getAll` via temporary CDP attach. If the pinned ID from `manifest.json:34` is present, skip install.
2. Set `~/.anticipy/v7/install/extension_pending=1`. Popover: "Anticipy is connecting to Chrome. ~10 seconds. Keep using your computer."
3. `mcp__computer-use__request_access` for `Google Chrome` at full tier (install needs click + type, above the default browser "read" tier). User approves once, persists.
4. `mcp__computer-use__open_application` Chrome, `key` `cmd+t`, `type` `chrome://extensions`, `key` `Return`.
5. `screenshot`, vision-locate Developer mode toggle (top right), `left_click`. Re-screenshot to confirm on-state; if flipped off, click again. Idempotent, two clicks worst case.
6. Re-screenshot, locate "Load unpacked," `left_click`.
7. Native file picker opens. `key` `cmd+shift+g`, `type` `/Applications/Anticipy.app/Contents/Resources/extension/`, `key` `Return`, `key` `Return` again to confirm Select.
8. Re-query CDP, confirm pinned ID present, clear the flag. Popover: "Anticipy is ready."

Total wall time on a warm M-series Mac: 8 to 15 seconds. User sees Chrome flash, the extensions tab open, toggle flip, file picker open and close. They do nothing.

## 3. Alternative install paths and why this one wins

| Path | Cost | Time-to-value | Verdict |
|---|---|---|---|
| Chrome Web Store unlisted | 1 to 3 weeks Google review, rejection risk for `<all_urls>` + `nativeMessaging` | ~5 s once approved | Start in parallel for v2 |
| Enterprise policy plist (`sudo defaults write com.google.Chrome ExtensionInstallForcelist`) | Admin password every install, fails on MDM-managed Macs with existing Forcelist | 30+ s plus prompt | Wrong for consumers |
| Native messaging only, no extension | Cannot call `chrome.tabs.group` / `chrome.tabGroups.update`, hijack bug unsolved | Zero, worse product | Off the table |
| Computer-use install flow | Zero Google review, zero admin prompt, one TCC approval | 8 to 15 s | Ship for v1 |

Web Store is correct for v2 (only path that survives Chrome's announced `--load-extension` + Developer Mode crackdown around Q4 2026), but waiting on Google review delays the investor demo by weeks. Computer-use ships today; the two coexist with Web-Store-first preference.

## 4. The exact computer-use commands

```python
# engine/app/product/extension_installer.py (new file)
await mcp.request_access(apps=["Google Chrome"], tier="full")
await mcp.open_application(name="Google Chrome")
await mcp.key(keys="cmd+t")
await mcp.type(text="chrome://extensions")
await mcp.key(keys="Return")

shot = await mcp.screenshot()
xy = locate_developer_toggle(shot)        # vision pass
if xy and not toggle_is_on(shot, xy):
    await mcp.left_click(x=xy[0], y=xy[1])

shot = await mcp.screenshot()
xy = locate_load_unpacked(shot)
await mcp.left_click(x=xy[0], y=xy[1])

await mcp.key(keys="cmd+shift+g")
await mcp.type(text="/Applications/Anticipy.app/Contents/Resources/extension/")
await mcp.key(keys="Return")
await mcp.key(keys="Return")              # confirm Select

if not await verify_extension_loaded_via_cdp():
    raise InstallFailed("extension did not register on CDP")
```

`locate_*` runs a small vision pass on the screenshot. Reuse the existing Kimi K2.6 vision broker in `engine/app/action_engine/`. Cost ~1 cent per install. `wait()` calls between steps elided for brevity; 200 to 800 ms each where dialogs open.

## 5. Permission and TCC dialogs

First `request_access` surfaces "Anticipy wants to control Google Chrome" (System Settings, Privacy and Security, Accessibility and Automation). The Tauri popover at `desktop/src/popover.html` already has the TCC explainer from commit `fcde9857`. Add a bullet: "We open `chrome://extensions` once to install our helper. You will see the toggle flip and a file picker. 10 seconds. We never touch this again unless Chrome turns the extension off on update." User clicks Allow once, grant persists.

If Deny: popover degrades to "Anticipy needs to control Chrome to install its helper. Open System Settings, Privacy and Security, Accessibility, check Anticipy, click Retry." The Retry button re-fires the install flow.

## 6. Reliability and failure handling

| Failure | Detection | Recovery |
|---|---|---|
| Chrome not installed | `open_application` returns "not found" | Popover offers Install Chrome link to `google.com/chrome`; engine polls every 30 s for `/Applications/Google Chrome.app`, then re-fires |
| Developer mode already on | Screenshot vision pass | Skip toggle, proceed to Load unpacked |
| User cancels file picker | 2 s timeout on post-Select CDP verification | Popover: "Cancelled. Click Retry." |
| Modal up ("Restore tabs?") | Initial screenshot | `key` `Escape` first, proceed |
| Enterprise policy blocks `chrome://extensions` | Page renders "Blocked by your administrator" | Hard-refuse (see Q4 below) |
| User clicks away mid-install | Each step screenshots Chrome frontmost | `open_application` to refront, resume at last verified step |
| Extension loads but `enabled=false` | `chrome.management.getAll` | Screenshot+click the enable toggle on the Anticipy row |

Each failure has a single visible recovery action in the popover. No silent retries.

## 7. Re-install on Chrome update

Chrome periodically disables unpacked extensions on major version updates ("Developer mode extensions are disabled" banner across `chrome://extensions`). Engine detects on every startup via the `chrome.management.getAll` probe; if Anticipy is missing or `enabled=false`, install re-fires. User sees a 10 s Chrome flash with popover note: "Chrome updated. Re-enabling Anticipy now."

Long term, Google's announced `--load-extension` phase-out (sliding, currently around Q4 2026) makes Web Store the eventual fallback. Ship both, prefer Web Store, computer-use as the install-now path and the post-Web-Store-rejection fallback.

## 8. Why this beats asking the user to install manually

Manual install: 6 ordered clicks across two surfaces, one toggle, one Finder navigation into `/Applications/Anticipy.app/Contents/Resources/extension/` (a folder most users have never opened), plus Chrome's developer-extension confirmation dialog. ~90 s flow with 30 to 50% drop-off based on comparable self-install extensions (Loom, Honey, Grammarly). The investor demo cannot survive that. Computer-use lifts success rate above 95% (TCC denial is the only failure, recoverable) and time-to-value below 15 s. User watches Anticipy do something visibly competent at first contact.

## 9. Runtime use of the tab group, wire protocol

After install, the bridge stops calling `_cdp_navigate(url, prefer_in_place=True)` blindly. New flow:

1. Bridge maintains `~/.anticipy/v7/runtime/owned_tabs.json` (set of Anticipy `targetId`s).
2. If a matching owned tab exists for the URL host, reuse via `Page.navigate`.
3. Otherwise send `{ type: "create_tab", url, taskId, cmdId }` to the extension over the existing native-messaging port at `com.anticipy.agent`. The extension's `createTab` handler at `extension_v4/background.js:412-423` creates the tab and groups it via `ensureGroupWith`. The new `targetId` flows back in `{ type: "result", cmdId, ok, tabId }`; bridge records it.
4. Bridge never reuses an ungrouped or user-grouped tab. Effective change: `prefer_in_place=False` for unowned hosts.

Native messaging is preferred over `Runtime.evaluate` + `chrome.runtime.sendMessage` because the persistent port already exists (`background.js:44`) and avoids an `externally_connectable` manifest change. Wire payloads match what `background.js:102-156` already dispatches.

## 10. Effort to ship

Extension is built. Install flow: one new file `engine/app/product/extension_installer.py` (~200 lines) plus a 50-line vision helper that reuses the K2.6 broker. Bridge change: one new function and a 5-line modification to `_cdp_navigate` consulting `owned_tabs.json` before reuse. Popover: one new TCC explainer bullet. Z-001: one new check ("after install, agent creates a tab in the Anticipy group; user-owned tab is untouched after the task ends").

Estimated effort: 6 to 8 focused hours. One agent, one PR, ships before tomorrow's investor demo if started in the next 3 hours.

## 11. Open questions for Omar

- Run install on every launch (idempotent fast no-op if present) or first launch only? Recommend every launch, auto-heals the Chrome-update case.
- TCC prompt at first launch or deferred to first user action? Recommend first launch, the explanation is fresh.
- Should I start the Chrome Web Store listing in parallel for v2?
- Enterprise-policy-blocked case (hospital, law firm Macs): ship a degraded mode without the extension and accept tab hijack risk, or hard-refuse? Recommend hard-refuse, alternative is hijacking a doctor's EHR tab.
- Record the install flow as a short clip in the popover for marketing surface ("look how easy this is")?
