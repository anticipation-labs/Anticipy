# Anticipy — Mac Electron App Migration Plan

**Status:** plan-only, no code written. Read-only planning pass.
**Date:** 2026-05-13
**Supersedes (where conflicting):** the extension+chrome.debugger architecture in `/Users/omarebrahim/Developer/Anticipy-DEV-FINAL/PLAN.md` Layer 0 (M0.1–M0.3). Everything in `PLAN.md` Layers 1–6 (axtree, trajectory cache, verifier, multi-agent, captcha) survives unchanged because they live in the Python engine.
**Constraint applied throughout:** Omar's Chrome is currently running without `--remote-debugging-port=9222`. **No step in this plan kills, restarts, or relaunches Omar's running Chrome.**

---

## 1. UI-TARS-Desktop fork

**Fork target.** `omize10/anticipy-desktop` (Omar's existing GitHub namespace `omize10`, matching the author of `22a77f6`/`b3eeb05`/`0e351d4`). Reason: there is no `anticipy-org` namespace yet; creating one is a side-quest. Rename can happen later by transferring the repo — `git remote set-url` is the only local change required.

**Branch naming.**
- `main` — tracks upstream `bytedance/UI-TARS-Desktop:main` via merge commits only (no rebase, so the upstream history stays readable for security audit).
- `anticipy/integrate` — the long-running integration branch. All Anticipy customisation lands here.
- Feature branches off `anticipy/integrate`: `anticipy/strip-openai`, `anticipy/strip-telemetry`, `anticipy/wire-engine-ws`, `anticipy/patchright-attach`, `anticipy/skill-runner`. Squash-merge each into `anticipy/integrate`.

**What gets stripped out of upstream.** UI-TARS-Desktop's repo layout (verified from its public structure) is an Electron + React monorepo with `apps/` (the desktop shell), `packages/` (shared libs), and `pnpm` workspaces. The strip points:

| What | Where (upstream path) | Why |
|---|---|---|
| OpenAI SDK | `apps/ui-tars/src/main/services/openai/*`, `packages/agent-infra/*openai*`, and `package.json` `openai` dep | Forbidden provider per v-final-prototype whitelist |
| Anthropic SDK | same shape under `*/anthropic/*`, `@anthropic-ai/sdk` dep | Forbidden |
| Built-in UI-TARS model client | `apps/ui-tars/src/main/agent/*` (calls UI-TARS-7B on volcengine/ByteDance hosts) | We use our own Python engine for inference; never call a model directly from Electron |
| Telemetry / mixpanel | `apps/ui-tars/src/main/services/telemetry/*` (mixpanel/posthog code path) | We don't ship third-party telemetry. Replace with a no-op shim that writes to `~/.anticipy/electron.log` only. |
| Default model picker in renderer | `apps/ui-tars/src/renderer/src/components/Settings/Models/*` | Replaced with a fixed "Anticipy engine @ ws://127.0.0.1:8000" connection card — no user model choice surfaces |
| Sample/demo prompts | `apps/ui-tars/src/renderer/src/store/__samples__/*` (or equivalent) | Replaced with Anticipy-brand demo prompts |

Each strip is a `git rm -r` of the directory plus a corresponding entry removal in the workspace's `package.json` (`pnpm` dep tree). Verify with `pnpm install --frozen-lockfile` succeeding after the strip.

**One-line summary.** Keep the Electron shell, window chrome, IPC plumbing, and macOS code-signing harness. Throw away the model wiring entirely.

---

## 2. Replacement provider plumbing: Electron talks to Python over WS

**Hard rule:** The Electron app **never** holds an LLM API key and **never** calls Cerebras / Mistral / Gemini / Groq directly. The engine at `/Users/omarebrahim/Developer/Anticipy-DEV-FINAL/engine/app/` already owns the cascade (`MODEL_CHAIN` and `ROLE_CHAINS` in `engine/app/config.py`, lines 136–349 — already rewired in `22a77f6`).

**Wire protocol.** The engine already exposes `ws://127.0.0.1:8000/ws/task` (see `engine/app/main.py` line 873). The Electron app becomes a third WS client alongside the existing browser-extension and Next.js `/engine` page clients. Reuse the existing frame shape — no new endpoint, no new auth flow.

Outbound from Electron → engine:
```json
{ "type": "task", "id": "<uuid>", "token": "<jwt>", "text": "<user request>", "context": { "source": "electron", "version": "0.1.0" } }
{ "type": "confirm", "value": "yes" | "no" | "" }
{ "type": "cancel", "id": "<uuid>" }
{ "type": "ping" }
```

Inbound engine → Electron (already emitted by `main.py:ws_task`):
```json
{ "type": "step",    "step": 3, "message": "Navigating to gmail.com" }
{ "type": "ask",     "prompt": "Confirm sending email to alice@example.com?" }
{ "type": "result",  "ok": true, "data": "<plain English summary>" }
{ "type": "error",   "message": "<user-facing reason>" }
{ "type": "pong" }
```

**Auth.** Existing JWT minted by `engine/app/auth.py`. On first launch, Electron prompts for the same access code + login the website uses. JWT stored at `~/Library/Application Support/Anticipy/auth.json` (macOS keychain when shippable, but file-backed during prototype).

**Subprocess ownership.** Electron's main process owns the engine. On app start, the main process spawns `engine/.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000` via `child_process.spawn`. Health-check the `/health` endpoint (already exists in `main.py`) on 250 ms intervals up to 30 s. If engine fails to come up, surface a clean error and refuse to open the main window.

**Why WS not HTTP.** The engine streams `step` / `ask` events. Polling would lose the streaming-feel UX that the current `/engine` page provides.

---

## 3. browser-harness integration

**What it is (per the user's directive):** `browser-use/browser-harness` is the self-healing CDP-attach harness from the browser-use authors. In our process tree it sits **inside the Python engine**, not inside Electron.

**Process tree:**
```
Electron (main)
├── BrowserWindow (renderer)
└── child: python uvicorn app.main:app
            └── child (lazy, started on first action task):
                  patchright.async_api.async_playwright().chromium.connect_over_cdp(<endpoint>)
                  └── uses browser-harness as the CDP transport with reconnect
```

The engine owns the subprocess. Electron does not directly launch Chrome and does not directly speak CDP. This matches Section 2 above (Electron is dumb pipe), keeps secrets in one place, and makes the Electron app replaceable without touching the engine.

**The Chrome attach problem.** Omar's current Chrome is running on his default profile **without** `--remote-debugging-port=9222`. Two facts decide the strategy:

1. Chrome 136+ refuses `--remote-debugging-port` against the **default** `--user-data-dir`. Per `research/browser.md` line 154 and `PLAN.md` risk #4, this profile-lockdown is permanent upstream policy.
2. Killing Omar's running Chrome to relaunch with the flag is a **destructive action** explicitly forbidden in this task.

**The chosen attach cascade** (selector chain at the *browser-attach* layer, mirroring the per-action selector chain in §4):

1. **Patchright over `chrome.debugger` extension bridge** — primary. The thin extension at `extension/bridge/` (per `PLAN.md` M0.2) speaks WebSocket back to the engine. Patchright's `connect_over_cdp` consumes whatever CDP transport we hand it; we hand it the WebSocket relay. **No `--remote-debugging-port` needed.** No Chrome restart needed. Yellow bar surfaces — see §6.
2. **Nodriver** — fallback. License is AGPL (per `research/browser.md` line 106), so we cannot link it into the engine if/when the engine is distributed under a non-AGPL license. **Plan: keep Nodriver call-out as an out-of-process subprocess** (`subprocess.Popen(["nodriver-runner", ...])`) so its license boundary is preserved. Fall back to this only if the extension is uninstalled or `chrome.debugger.attach` fails.
3. **macOS AXUIElement Accessibility API** — final fallback. Native-side, called from Python via `pyobjc` (`AppKit` + `ApplicationServices`). Cannot type into a content-editable cleanly but **can** read text, click by accessibility label, and scroll. Use when Chrome is wedged behind a sign-on that defeats CDP.

**Who owns the subprocess.** The engine. `engine/app/bridge_cdp.py` (a new module, replaces `engine/app/bridge.py` and `engine/app/bridge_extension.py` over time) owns:
- the WebSocket server endpoint that the bridge extension connects back to,
- the Patchright `connect_over_cdp` lifecycle,
- the Nodriver subprocess (lazy, only on fallback),
- the AXUIElement bridge (lazy, only on fallback).

**Chrome flag injection (NOT a current-Chrome restart).** When/if Omar voluntarily restarts Chrome later, ship a LaunchAgent at `~/Library/LaunchAgents/ai.anticipy.chrome-debug.plist` that sets the flag on **next** Chrome start. The agent does **not** launch Chrome itself. Until then, the extension+`chrome.debugger` path is the only working attach. This satisfies the constraint cleanly.

---

## 4. Skill execution path

**Skill shape.** A skill is a Python program at `/Users/omarebrahim/Developer/Anticipy-DEV-FINAL/engine/app/skills/<skill_id>.py`. Each module exposes:

```python
# engine/app/skills/<skill_id>.py
SKILL_ID = "gmail.compose"
INTENT_PATTERNS = ["send an email to ...", "email <person> ..."]

async def run(ctx: SkillContext, args: dict) -> SkillResult:
    # 4-step selector chain per element:
    #   1. ctx.page.get_by_role("textbox", name="To")
    #   2. ctx.page.get_by_label("To recipients")
    #   3. ctx.page.get_by_test_id("composeTo")
    #   4. ctx.page.locator("text=To").first
    ...
```

**Dispatch path (Electron → result):**

1. Electron sends `{type:"task", text:"send Alice a note about lunch", id:"abc"}` over `ws://127.0.0.1:8000/ws/task`.
2. `engine/app/router.py:classify` decides action vs read-only (already exists).
3. **NEW** `engine/app/skill_router.py` matches the intent against `INTENT_PATTERNS` from every skill module loaded at engine boot. The match returns `skill_id` + extracted args. On no-match, fall through to the generic Browser Use loop (preserves current behaviour for unhandled tasks).
4. `engine/app/orchestrator.py:run_task` (existing) is extended to call `skills.<skill_id>.run(ctx, args)`.
5. The skill drives `ctx.page` — a Patchright `Page` connected through `engine/app/bridge_cdp.py` to the user's Chrome via the extension bridge.
6. Each step within the skill streams `{type:"step", message:"..."}` back over the same WebSocket using the orchestrator's existing `send_msg` channel (`engine/app/main.py` line 899).
7. On completion, the skill returns `SkillResult(ok=True, summary="Sent.")`. Orchestrator sends `{type:"result", ok:true, data:"Sent."}`. Verifier (`engine/app/end_state_verifier.py`, existing) runs first and can override `ok=true` to `false` with a `missing` field.

**The 4-step selector chain is enforced by `SkillContext.find()`.** Skills never call `page.click(selector)` directly. They call `await ctx.find("compose-to-field").click()`. `SkillContext.find` walks the 4-step chain and caches the winning selector in `engine_trajectories` (`engine/app/trajectory_cache.py`) for the same `(skill_id, page_url_path)` tuple. Next run is one selector lookup, not four.

**Initial skill set to plan for (not build yet):** `gmail.compose`, `gmail.read_unread`, `calendar.create_event`, `calendar.today`, `amazon.add_to_cart`, `resy.book_reservation` — the same six the v-final-prototype acceptance test gates on.

---

## 5. Retirement of `extension/`, `extension_v2`, `extension_v3`, `extension_v4`, `native_host/`

Runtime relevance audit (verified by reading manifests + `PROGRESS.md` line 16 "Production extension path: 0/35"):

| Dir | Status today | Action | Order |
|---|---|---|---|
| `extension_v4/` (manifest v6.0.0, native-messaging) | **Last shipped to users.** Per `PROGRESS.md` it is the production install path. 0/35 last benchmark — broken on Cerebras RPM ceiling, not on extension code. | **Keep as-is until Mac app ships to ≥1 paying user.** Then deprecation: in-app banner ("Move to the Mac app, this extension is read-only after <date>") for 30 days, then disable command handling but keep installed (avoids the extension auto-uninstalling and surprising users). | LAST to retire |
| `extension_v3/` | Older bridge; superseded by v4. | Move to `archive/2026-05-pre-mac-app/extension_v3/` once Mac app reaches dogfood. | 2nd |
| `extension_v2/` | The "dumb DOM proxy" that `engine/app/ws_bridge.py` documents. Useful as the bridge-pattern reference. | Move to `archive/...` but keep the protocol comment block from `ws_bridge.py` lines 10–34 because the new Mac-app bridge extension reuses the same `cmdId / result` shape. | 3rd |
| `extension/` (v2.0.0, the original) | Long obsolete. | Archive immediately. | 1st (now) |
| `native_host/` | Companion to `extension_v4` (the `com.anticipy.agent` native-messaging host). Currently in use by v4 installs. | **Retire only when v4 retires.** Same date. | LAST to retire (paired with v4) |

**New replacement:** `extension/bridge/` (per `PLAN.md` M0.2) — the thin `chrome.debugger` relay. Lives in the same repo for now; lives in its own Chrome Web Store listing for production. **The Mac app installs and signs this extension on first run** via a side-load instruction page (the existing `https://anticipy.ai/anticipy-extension.zip` mechanism in `PLAN.md` risk #1).

**Customer comm requirement.** The v4 deprecation requires a Resend-driven email to every wearer of every existing install. Out of scope for this plan, but list it in `.anticipy/CHANGELOG.md` as a blocker before deletion.

---

## 6. Risks

1. **Yellow `chrome.debugger` bar.** Unavoidable. Same UX as Anthropic's Claude for Chrome. Accept it. Surface a one-time onboarding tooltip on first attach: "The yellow bar at the top of Chrome means Anticipy is connected. Closing the bar disconnects me." This converts a surprise into a feature.
2. **Chrome 136+ remote-debugging-port lockdown.** Already designed around. The extension bridge replaces TCP. **Imperfect alternative considered and rejected:** a separate Chrome profile (`--user-data-dir=~/Library/Application Support/Google/Chrome-Anticipy`) would technically allow `--remote-debugging-port=9222`, but the user would have to log into Gmail / Resy / Amazon **again in the second profile**, which defeats the "use the user's real session" premise.
3. **Chrome restart constraint.** Omar's Chrome is hot. The LaunchAgent flag (§3) only applies on Omar's next voluntary restart. Until then, the extension+`chrome.debugger` path **is** the working path — there is no degraded mode where we need the port. Plan ships green even if Omar never restarts Chrome.
4. **Patchright + `chrome.debugger` simultaneous attach.** `chrome.debugger.attach` is exclusive per tab — DevTools windows on the same tab will disconnect us, and vice versa. Mitigation: on `Inspector.detached` CDP event, the engine surfaces "Anticipy disconnected because you opened DevTools" instead of retrying-and-losing.
5. **AGPL contamination via Nodriver fallback.** Nodriver MUST be a subprocess invoked at runtime, never an `import`. Enforce in code review.
6. **macOS code-signing for the Electron app.** Stripping UI-TARS-Desktop's signing identity means re-signing under Omar's Apple Developer ID. Not blocked technically but blocks distribution. Track as a Phase 11 item, not Phase 1.
7. **Engine subprocess lifetime.** If Electron quits while a long-running skill is mid-execution, the orchestrator must cleanup gracefully. The existing `signal.SIGTERM` handler in `engine/app/main.py:lifespan` covers this; verify in integration test.

---

## Shippable in this session — punch list

**Autonomous agent (no Omar interaction) CAN do right now:**
- A. Create `omize10/anticipy-desktop` as an empty repo on GitHub via `gh repo create` (Omar's `gh` is already auth'd — verifiable by `gh auth status`).
- B. Add UI-TARS-Desktop as a remote: `git remote add upstream https://github.com/bytedance/UI-TARS-Desktop.git`, fetch, branch `anticipy/integrate` off the upstream tag at HEAD.
- C. Produce the strip-list diff (the `git rm -r` paths from §1) as a single commit on `anticipy/strip-openai` against the freshly forked tree, **without pushing**. This is the largest mechanical lift and is safe to do offline.
- D. Author `engine/app/bridge_cdp.py` skeleton + `engine/app/skill_router.py` skeleton + `engine/app/skills/__init__.py` against the existing engine — wired but no concrete skill yet. Compiles and passes a smoke `pytest` that imports the package.
- E. Add `extension/bridge/manifest.json` + `extension/bridge/background.js` from the PLAN.md M0.2 spec (~200 LOC). Local unpacked load — does not require Web Store submission.
- F. Add a new entry to `engine/app/main.py:ws_task` accepting `context.source == "electron"` and treating it identically to existing clients. One-line change.
- G. Write `.anticipy/MAC_APP_PLAN.md` (this document).

**Blocked on Omar:**
- α. **Confirming `omize10` is the correct GitHub namespace** (or directing to `anticipy-org`). Not destructive but irreversible-ish (renaming a repo breaks clones).
- β. **Apple Developer ID** for code signing the Electron app. No agent path here.
- γ. **Chrome Web Store developer-account access** to list the new bridge extension. Sideload works for dogfood; store listing is a paid + manual step.
- δ. **Voluntary Chrome restart** (eventually) to pick up `--remote-debugging-port=9222` from the LaunchAgent. Not required for v1 — extension bridge works around it — but lets the engine bypass the yellow bar via Patchright direct-attach if Omar ever wants that mode. **Will not be done by an agent.**
- ε. **Customer comm sign-off** for v4 extension deprecation (per §5 last paragraph).
- ζ. **Mistral key rotation** (per `PROGRESS.md` "Phase 0 honest gates" #5) — unrelated to this plan but blocks production.

---

### Critical Files for Implementation
- `/Users/omarebrahim/Developer/Anticipy-DEV-FINAL/engine/app/main.py` (WebSocket endpoint reused for the Electron client; line 873 `ws_task`)
- `/Users/omarebrahim/Developer/Anticipy-DEV-FINAL/engine/app/config.py` (provider cascade already rewired; the Electron app must not duplicate this)
- `/Users/omarebrahim/Developer/Anticipy-DEV-FINAL/engine/app/ws_bridge.py` (the existing extension wire-protocol contract that the new bridge extension reproduces; the `cmdId/result/cancel/ping` shape in lines 10–34 carries forward verbatim)
- `/Users/omarebrahim/Developer/Anticipy-DEV-FINAL/engine/app/orchestrator.py` (the task runner that gains the `skills.<id>.run(...)` dispatch in §4)
- `/Users/omarebrahim/Developer/Anticipy-DEV-FINAL/PLAN.md` (Layers 1–6 survive verbatim — the Mac-app migration only replaces Layer 0)
