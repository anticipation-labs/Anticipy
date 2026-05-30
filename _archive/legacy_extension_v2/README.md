# Anticipy Bridge (extension_v2)

A **thin relay** Chrome extension. The agent brain — LLM calls, prompts,
provider rotation, rate limiting, memory, all of it — lives on the Anticipy
server. This extension just forwards DOM commands to your tabs.

> **Why this exists.** The previous `extension/` baked ~1,800 LOC of agent
> logic into `agent.js`. Every prompt tweak or provider change required a
> reinstall. This version is "evergreen": redeploy the server, the extension
> picks up new behavior automatically.

## Architecture

```
   ┌──────────┐  WebSocket  ┌─────────────┐  chrome.tabs  ┌──────────┐
   │  server  │  ◄────────► │ background  │  ◄──────────► │ content  │
   │  /ws/agent│            │ service     │  sendMessage  │  scripts │
   └──────────┘             │  worker     │               │ (per tab)│
                            └─────────────┘               └──────────┘
                                  ▲
                                  │ chrome.runtime.sendMessage
                                  ▼
                            ┌─────────────┐
                            │   popup.js  │
                            └─────────────┘
```

- **`background.js`** keeps a single WebSocket open to the engine. It
  receives commands (`navigate`, `click`, `type`, `extract`,
  `getDOMSnapshot`, `screenshot`, `create_tab`, `close_tab`, `done`) and
  dispatches them to the right tab. Results go back over the WS.
- **`content.js`** is injected programmatically into the active tabs and
  performs the actual DOM operations.
- **`popup.html/js/css`** is the user-facing UI: enter access code, send a
  task, see current step, hit Cancel.

There is no `agent.js`. There are no API keys in client storage.

## Permissions

```json
"permissions": ["tabs", "tabGroups", "scripting", "storage", "activeTab"],
"host_permissions": ["<all_urls>"]
```

`<all_urls>` is required so `chrome.scripting.executeScript` can inject
`content.js` into any site the agent visits. We do not use a static
`content_scripts` block, so the script runs only on tabs the agent
explicitly touches.

## WebSocket protocol

Connection URL: `wss://anticipy.ai/ws/agent?userId=<id>&code=<accessCode>`

### Extension → server

| Message | Sent when |
| --- | --- |
| `{type: "task_start", taskId, task, tabGroupId}` | User submits a task in the popup. |
| `{type: "result", cmdId, ok, tabId?, data?, error?}` | Reply to every server command. |
| `{type: "cancel", taskId, reason?}` | User clicks Cancel, or all task tabs were closed. |
| `{type: "ping", t}` | Every 25 s to defeat MV3 service-worker eviction. |
| `{type: "error", cmdId?, message}` | Unknown command type or fatal client error. |

### Server → extension

| Message | Effect |
| --- | --- |
| `{type: "navigate", cmdId, url, tabId?}` | `location.href = url` in the chosen tab. |
| `{type: "click", cmdId, selector, tabId?}` | `document.querySelector(selector).click()`. |
| `{type: "type", cmdId, selector, text, submit?, tabId?}` | Set value with native setter, dispatch input/change, optional Enter. |
| `{type: "extract", cmdId, selector?, includeHtml?, tabId?}` | Returns `{text, html?}`. |
| `{type: "getDOMSnapshot", cmdId, selector?, limit?, tabId?}` | Returns `{url, title, html}`. |
| `{type: "screenshot", cmdId, tabId?}` | Returns `{dataUrl}` via `chrome.tabs.captureVisibleTab`. |
| `{type: "create_tab", cmdId, url?}` | Opens a new tab inside the Anticipy group. |
| `{type: "close_tab", cmdId, tabId}` | Closes a specific tab. |
| `{type: "task_step", step}` | UI hint only — popup shows current step. |
| `{type: "done", summary?}` | Marks task finished. Tabs stay open for inspection. |
| `{type: "pong"}` | Keepalive ack. |

`cmdId` is server-assigned and echoed back so the server can correlate.

## Tab group lifecycle

Every task opens a Chrome tab group titled **"Anticipy"** (color: blue).
The agent works inside it; your other tabs are untouched. The user can
close the entire group at any time — `chrome.tabs.onRemoved` fires for
each tab and the extension sends `{type: "cancel", reason: "tabs_closed"}`
to the server.

## Cancel flow (end-to-end)

1. User clicks the red **Cancel** button in the popup.
2. Popup → `chrome.runtime.sendMessage({type: "popup:cancel_task"})`.
3. Background sends `{type: "cancel", taskId}` over the WS.
4. Background closes every tab in the Anticipy group.
5. Server aborts the task loop on receipt of `cancel`.

## Install for development

1. Open `chrome://extensions`, enable **Developer mode**.
2. Click **Load unpacked**, point it at `extension_v2/`.
3. Click the toolbar icon, enter your access code (paired with a row in
   `engine_users` via `/api/extension/auth`).
4. Submit a task. A new "Anticipy" tab group opens.

For local dev against a non-prod server, the popup's optional **Server URL**
field accepts `ws://localhost:8000/ws/agent`.

## Run the unit tests

```
node --test extension_v2/test_message_protocol.js
```

7/7 tests cover navigate/click/extract/screenshot, plus error/done paths.
No external dependencies — uses Node's built-in `node:test`.

## Manual smoke test against a mock server

```bash
# 1. Run a stub WebSocket server (any of these works):
npx wscat -l 9000

# 2. In the popup, set Server URL to: ws://localhost:9000
# 3. Authenticate with your access code (still goes to /api/extension/auth).
# 4. Submit a dummy task: "say hi"
# 5. wscat will receive: {"type":"task_start","taskId":"...","task":"say hi","tabGroupId":N}
# 6. From wscat, send back: {"type":"navigate","cmdId":"1","url":"https://example.com"}
# 7. Confirm the agent tab navigates.
# 8. Send: {"type":"done","summary":"hello!"}  → popup shows "Done."
```

## What lives where

| Concern | Location |
| --- | --- |
| LLM calls / provider rotation | server (`engine/app/`) — gone from extension. |
| API keys | server env vars — never sent to extension. |
| Memory / lessons | server (`engine/app/memory.py`) — gone from extension. |
| Rate limiting | server — gone from extension. |
| Step / time budgets | server safety circuit-breaker — extension has no caps. |
| DOM execution | extension `content.js`. |
| Tab management | extension `background.js`. |
| User input + Cancel | extension `popup.*`. |
