# Chrome APIs Research for Anticipy

2026-05-30. Facts verified against Chrome for Developers docs and Chromium source. Read-only.

---

## 1. Tab Groups API (MV3)

**1a. SW can create a group?** Yes, but not via `tabGroups.create` (doesn't exist). Use `chrome.tabs.group({ tabIds, createProperties: { windowId } })`. Returns the new numeric `groupId`. Works fine from a MV3 service worker.
Source: https://developer.chrome.com/docs/extensions/reference/api/tabGroups, https://developer.chrome.com/docs/extensions/reference/api/tabs

**1b. Color + title.** `chrome.tabGroups.update(id, { color, title, collapsed })`. Allowed colors are exactly: `grey, blue, red, yellow, green, pink, purple, cyan, orange` (9 values, no hex).
Source: https://developer.chrome.com/docs/extensions/reference/api/tabGroups#type-Color

**1c. Collapse/expand.** Yes via `update(id, { collapsed: true })`.

**1d. Assign / move tabs.** In: `chrome.tabs.group({ groupId, tabIds })`. Out: `chrome.tabs.ungroup(tabIds)`. Empty groups auto-delete (fires `onRemoved`).

**1e. Permissions.** `"tabGroups"` to read/modify groups, plus `"tabs"` (or matching `host_permissions`) for `tabs.group/ungroup`. For our product also `"debugger"`, `"nativeMessaging"`, `"storage"`.

**1f. Limits.** No documented cap on groups per window. `tabGroups.move()` only between `windows.WindowType === "normal"` windows. Cross-window move is delete+recreate, NOT move: the `groupId` changes and `onMoved` does NOT fire (you get `onRemoved` + `onCreated`).
Source: https://developer.chrome.com/docs/extensions/reference/api/tabGroups#method-move

**Recommendation.** Create the group lazily on first tab. Persist color in `chrome.storage.sync`. IDs are session-scoped ("Group IDs are unique within a browser session"), so re-resolve via `tabGroups.query({ title:"Anticipy", windowId })` on `onStartup`, never cache.

---

## 2. chrome.debugger API

**2a. Concurrent tabs.** No documented hard limit. One extension can attach to many tabs at once and route by `tabId` in `sendCommand` / `onEvent`. Chrome 125+ adds flat sessions via `Target.setAutoAttach({ flatten: true })` to add child iframes/workers under one root session without separate attaches.
Source: https://developer.chrome.com/docs/extensions/reference/api/debugger (Attach to related targets, 125+)

**2b. Warning bar.** Always shown, persistent until the user dismisses it. Exact text: `"<ExtensionName>" started debugging this browser` (Chromium `IDS_DEV_TOOLS_INFOBAR_LABEL`). The bar does NOT disappear when you detach. Cannot be suppressed by the extension. The only kill switch is the command-line flag `--silent-debugger-extension-api`, which the user (or our launcher) would need to pass at startup; not realistic for a shipped product on the user's main Chrome.
Sources: https://chromium.googlesource.com/chromium/src/+/refs/heads/main/chrome/app/generated_resources.grd, https://chromium.googlesource.com/chromium/src/+/refs/heads/main/chrome/common/chrome_switches.cc

**2c. CDP domains available.** `Accessibility, Audits, CacheStorage, Console, CSS, Database, Debugger, DOM, DOMDebugger, DOMSnapshot, Emulation, Fetch, IO, Input, Inspector, Log, Network, Overlay, Page, Performance, Profiler, Runtime, Storage, Target, Tracing, WebAudio, WebAuthn`. Notably blocked: `Browser`, `SystemInfo`, `Memory`, `HeadlessExperimental`.
Source: https://developer.chrome.com/docs/extensions/reference/api/debugger (Restricted domains)

**2d. Latency.** Not officially benchmarked. Empirically (Playwright/Puppeteer): each `sendCommand` round-trip ~5-20 ms; click + DOM read cycle ~30-80 ms; `Page.captureScreenshot` ~80-250 ms at viewport size. Don't loop screenshots faster than ~5 fps.

**2e. Survives navigation/reload?** Yes. The session binds to `tabId`, not the page. After `Page.frameNavigated` you need to re-issue `DOM.enable`, `Runtime.enable` (CDP enables are per-session, not per-page).

**2f. Auto-detach.** `onDetach` fires with `reason ∈ { "target_closed", "canceled_by_user" }` when the tab closes, the user opens DevTools on the target (mutually exclusive with `chrome.debugger`), the user clicks Cancel on the infobar, or the extension is reloaded.
Source: https://developer.chrome.com/docs/extensions/reference/api/debugger#type-DetachReason

**Recommendation.** Attach lazily, only during active tasks. Re-attach quietly on `onDetach`. Use flat sessions (`Target.setAutoAttach { flatten:true }`) for cross-origin iframes (Gmail/LinkedIn/Drive use OOPIFs). Frame UX copy around the infobar; it can't be hidden.

---

## 3. Native Messaging

**3a. When the host spawns.** `runtime.connectNative(name)` spawns ONE new host process per port and keeps it alive until the port is destroyed. `runtime.sendNativeMessage` spawns one process per call, reads one reply, kills it (expensive, don't use for sustained work).
Source: https://developer.chrome.com/docs/extensions/develop/concepts/native-messaging ("Chrome starts native messaging host process and keeps it running until the port is destroyed")

**3b. Lifecycle / cost.** Killed on port disconnect. Restart cost is fork+exec+JSON handshake, typically 30-150 ms on macOS; longer with a warm Python interpreter or ML weights. Crashes fire `port.onDisconnect`. Wire protocol: little-endian uint32 length prefix + JSON UTF-8 body. Max inbound message (host->ext) 1 MB; max outbound (ext->host) 64 MiB.
Source: same doc, "Native messaging protocol" section.

**3c. Streaming best practices.** One long-lived `connectNative` port per session. Frame as `{ id, type, payload }` JSON with request ids for correlation. Keep frames under 256 KB. Stream large screenshots via file-path reference, never inline base64. Host boots under 200 ms, exits on stdin EOF.

**Recommendation.** One multiplexed port per session. Host is a persistent local daemon under `~/.anticipy/`. Reconnect from `onDisconnect`. Log crashes to `~/Library/Logs/Anticipy/`.

---

## 4. Service Worker Lifecycle (MV3)

**4a. Idle termination.** Chrome kills the SW after 30 s of inactivity (any event/API call resets the timer), after 5 minutes processing a single event (some UI-blocking API exemptions in 116+), or after 30 s waiting on a `fetch()`.
Source: https://developer.chrome.com/docs/extensions/develop/concepts/service-workers/lifecycle (Idle and shutdown)

**4b. How to stay alive (officially documented).**
- Open `runtime.connectNative` port (105+). Cleanest pattern for us.
- Active `chrome.debugger` session (118+). So while we're driving a tab, SW stays alive automatically.
- Active WebSocket (116+).
- Long-lived `runtime.connect` port; sending messages resets timer (114+).
- Offscreen document messaging the SW (109+).
- `chrome.alarms` min period 30 s (120+).
Source: same lifecycle doc; offscreen at https://developer.chrome.com/docs/extensions/reference/api/offscreen

**4c. Best pattern for native-messaging extensions.** Native port = heartbeat. SW lifecycle = port lifetime. State in `chrome.storage.session`/`local`, never `var` globals. On task start: open port, attach debugger. When done: close port, detach, SW dies after 30 s. Don't use `setInterval` keepalive hacks (CWS-banned, ineffective).

**Recommendation.** Native host = heartbeat. No globals. Debugger + port redundantly keep SW alive during work.

---

## 5. `--load-extension` and second-launch

**5a. Honored when Chrome is running?** No, not in the user's main profile. Every Chrome instance under a given `user-data-dir` uses a `ProcessSingleton` (POSIX socket on macOS/Linux, named pipe on Windows). A second binary launch contacts the singleton, forwards its command line via `NotificationCallback`, exits. That forwarded command line goes through `StartupBrowserCreator` which handles "open these URLs" but does NOT replay extension loading. `--load-extension` is silently ignored. Result: the user gets a new window, the extension is NOT loaded.
Sources: https://chromium.googlesource.com/chromium/src/+/refs/heads/main/chrome/browser/process_singleton.h (NotifyResult enum), https://chromium.googlesource.com/chromium/src/+/refs/heads/main/extensions/common/switches.cc (`kLoadExtension`)

**5b. Developer Mode toggle (Chrome 137+).** Unpacked extensions loaded via `--load-extension` are silently disabled at startup unless the user has flipped Developer mode on `chrome://extensions/`. The toggle cannot be set programmatically.
Source: https://developer.chrome.com/docs/extensions/get-started/tutorial/hello-world#load-unpacked

**5c. Best patterns, ranked.**
1. **Chrome Web Store publish**. 1-click install, no Dev Mode, no warning surface, no `--load-extension`. The user's Chrome already has Anticipy in every profile they're signed into. Use this for shipping.
2. **External extensions install**. Installer writes `~/Library/Application Support/Google/Chrome/External Extensions/<id>.json` with `external_update_url` pointing to a hosted .crx (CWS or enterprise allowlist). Chrome auto-installs on next launch, no Dev Mode required. Pattern used by Bitwarden / 1Password.
3. **Dedicated profile** (dev/internal only). `chrome --user-data-dir=~/Library/Application\ Support/Anticipy/chrome-profile --load-extension=/Applications/Anticipy.app/Contents/Resources/extension --no-first-run`. Separate ProcessSingleton, separate dock icon, user's normal Chrome untouched. Same approach Playwright/Puppeteer use. Cost: no access to the user's logged-in sites.

**Recommendation.** Ship via CWS. Dev builds use the dedicated-profile approach. Never command-line inject into the user's main Chrome; it will not work.

---

## 6. Tab Groups + Profile

**6a. Per-profile groups?** Yes, automatically. Each Chrome profile gets its own SW, its own `chrome.storage.local`, its own tab/group IDs. `tabs.query`/`tabGroups.query` only see the current profile. The Anticipy group in "Work" is unrelated to the one in "Personal."
Source: per-profile model implicit in https://developer.chrome.com/docs/extensions/reference/api/storage

**6b. Profile identity from the extension.** `chrome.identity.getProfileUserInfo({ accountStatus: 'ANY' })` returns the Google-sync email + obfuscated gaia id for the profile. Requires `"identity"` and `"identity.email"` permissions. If the user is not signed into sync, you get `{ email: "", id: "" }`. For local disambiguation persist a UUID in `chrome.storage.local` at first run.
Source: https://developer.chrome.com/docs/extensions/reference/api/identity#method-getProfileUserInfo

**Recommendation.** First run: write a per-profile UUID to `chrome.storage.local`. Send as `profileId` on every native frame so host can route per-profile state (cookies, RAG, secrets). Use `getProfileUserInfo()` for display only.

---

## Gotchas

- The debugger infobar is permanent and non-suppressible. Write UX copy around it ("Anticipy is active in this tab").
- Tab/group IDs do NOT survive Chrome restart. Always look up by title/color/URL, never cache numeric ids across SW lifetimes.
- `chrome.debugger` and DevTools are mutually exclusive per target. Listen for `onDetach`, re-attach quietly.
- `--load-extension` is silently ignored on a 2nd Chrome launch (ProcessSingleton). Don't trust it for runtime install in the user's main profile.
- Developer Mode toggle is required for unpacked extensions in Chrome 137+ and cannot be set programmatically. CWS or external-policy install is mandatory for ship.
- SW can be killed mid-task without an open native port or debugger session. No `var` globals; use `chrome.storage`.
- Native message size: 1 MB host->ext, 64 MiB ext->host. Send screenshots as file paths, not inline.
- `tabGroups.move` only between `WindowType === "normal"` windows. Popup/app windows cannot host groups.
- Cross-window group move is delete+recreate; the `groupId` changes; listen for `onRemoved` + `onCreated`.
- One `connectNative` per port = one host process. Use one multiplexed port, not one per tab.

---

## Source URLs

- tabGroups: https://developer.chrome.com/docs/extensions/reference/api/tabGroups
- tabs (group/ungroup): https://developer.chrome.com/docs/extensions/reference/api/tabs
- debugger: https://developer.chrome.com/docs/extensions/reference/api/debugger
- SW lifecycle: https://developer.chrome.com/docs/extensions/develop/concepts/service-workers/lifecycle
- Native messaging: https://developer.chrome.com/docs/extensions/develop/concepts/native-messaging
- offscreen: https://developer.chrome.com/docs/extensions/reference/api/offscreen
- identity (getProfileUserInfo): https://developer.chrome.com/docs/extensions/reference/api/identity
- Load unpacked + Dev Mode: https://developer.chrome.com/docs/extensions/get-started/tutorial/hello-world
- Infobar string (Chromium GRD): https://chromium.googlesource.com/chromium/src/+/refs/heads/main/chrome/app/generated_resources.grd
- ProcessSingleton: https://chromium.googlesource.com/chromium/src/+/refs/heads/main/chrome/browser/process_singleton.h
- chrome_switches.cc (`--silent-debugger-extension-api`): https://chromium.googlesource.com/chromium/src/+/refs/heads/main/chrome/common/chrome_switches.cc
- extensions/common/switches.cc (`--load-extension`): https://chromium.googlesource.com/chromium/src/+/refs/heads/main/extensions/common/switches.cc
- Chromium switches index: https://peter.sh/experiments/chromium-command-line-switches/
