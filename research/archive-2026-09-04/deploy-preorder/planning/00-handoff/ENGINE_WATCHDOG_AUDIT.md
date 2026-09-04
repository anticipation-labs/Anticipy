# Engine Watchdog Audit

Date: 2026-05-29
Scope: what happens if `/Applications/Anticipy.app/Contents/MacOS/anticipy-engine` silently crashes.

## TL;DR

Nothing restarts it. The Tauri parent spawns the engine once at app launch, stores the `Child` handle in `ENGINE_CHILD`, and never polls `try_wait()` or re-spawns on exit. There is no launchd plist for the engine binary. There is no internal self-monitoring loop in `engine/app/product/server.py`. If the engine pid dies while Anticipy.app is still running, the engine stays dead until the user quits and relaunches the app, or until an external watchdog (this PR) restarts it.

## Evidence: how the engine is started

`desktop/src-tauri/src/lib.rs:1043` `start_engine_sidecar(app)` is called exactly once from the Tauri `setup` closure (line 1597) on a detached thread. It:

1. Probes `engine_health_ok(8731)` (TCP GET `/health` with 1s timeout, line 1015).
2. If healthy, emits `engine-ready` and returns. This is the "engine already running, attach" path.
3. Otherwise locates the sidecar binary next to the app binary (`engine_sidecar_path`, line 1033) and `Command::spawn`s it with `ANTICIPY_PORT=8731`, stdout/stderr piped to `~/.anticipy/product-engine.log`.
4. Stores the `Child` in `static ENGINE_CHILD: OnceLock<Mutex<Option<Child>>>` (line 1109).
5. Polls health for 45 s. On success emits `engine-ready`. On timeout emits `engine-error`.

After step 5, the Tauri code does not look at the child again. There is no `try_wait`, no signal handler, no `tokio::spawn` watchdog task. The only references to `ENGINE_CHILD` in the file are at the spawn site.

## Evidence: no launchd plist for the engine

Currently loaded anticipy services (`launchctl list | grep anticipy`):

| Label | PID | Purpose |
|---|---|---|
| `com.anticipy.chrome` | 2143 | Chrome CDP on :9222 with `KeepAlive` |
| `com.anticipy.claude-remote-control` | 8494 | Claude CLI remote control with `KeepAlive` |
| `com.anticipy.content.broll` | - | Periodic content task |
| `com.anticipy.content.nudge` | - | Periodic content task |
| `com.anticipy.content.script` | - | Periodic content task |
| `com.anticipy.content.watcher` | 2165 | Content watcher |

No `com.anticipy.engine*` is loaded. The only engine-adjacent plist file on disk is `~/Library/LaunchAgents/ai.anticipy.watchdog.plist.disabled-by-claude-20260519-171413`, which is a disabled python watchdog that ran every 300 s out of the old DEV-FINAL venv. It was never engine-binary-aware and is currently turned off.

`com.anticipy.chrome.plist` DOES use `KeepAlive { SuccessfulExit=false; Crashed=true }` for the Chrome process. That pattern is the model the engine plist should follow, but no engine equivalent exists.

## Evidence: no in-process self-monitor

`engine/app/product/server.py` grep for `watchdog|heartbeat|self_monitor`: no hits. The `/health` endpoint at line 412 is a passive probe (caller polls it). The server has no thread that watches its own subprocesses or re-execs on internal error. FastAPI / uvicorn does not auto-restart on its own.

## Conclusion: real failure modes today

1. Engine process gets SIGKILL'd (OOM, manual kill, `pkill anticipy-engine`): Tauri sees no event, popover starts returning fetch errors, user has to Quit Anticipy from the tray and re-open.
2. Engine panics on a worker thread and exits cleanly: same outcome.
3. Engine hangs but pid alive (deadlock, blocked GIL): `/health` stops responding within 1 s. Nothing detects this either. Same outcome.
4. Engine is restarted by a build / install (`/Applications/Anticipy.app` replaced): Tauri parent still holds the old `Child` handle. Probably dies on the next button click.

For a Mac that has to keep running for a demo or for a customer's daily use, this is a real reliability gap.

## Recommendation: implement gap

Add an external `launchd` watchdog with these properties:

- Polls `127.0.0.1:8731/health` every 30 s.
- Restarts engine only after 3 consecutive failures (90 s grace) so a single slow request does not trigger a restart.
- Uses the production binary at `/Applications/Anticipy.app/Contents/MacOS/anticipy-engine`.
- Logs to `~/Library/Logs/anticipy-watchdog.log`.
- Honors a kill switch at `~/.anticipy/.watchdog_off` so planned restarts and dev work do not fight the watchdog.
- Plist file written to `~/Library/LaunchAgents/com.anticipy.engine-watchdog.plist` but NOT loaded into launchctl without owner consent (`launchctl load` mutates shared state).

This sits OUTSIDE Tauri so it survives Anticipy.app being quit, and OUTSIDE the engine process so a crashed engine cannot disable its own watchdog. Both `com.anticipy.chrome` and `com.anticipy.claude-remote-control` already use the same launchd-as-supervisor pattern, so the operational model is familiar.

Not adding restart logic to the Tauri parent (would only help when Anticipy.app is running) and not adding a self-monitor inside the engine (a hung engine cannot rescue itself).
