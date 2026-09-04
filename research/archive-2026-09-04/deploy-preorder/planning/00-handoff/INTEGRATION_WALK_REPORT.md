# Integration Walk Report

Date: 2026-05-30 (Sat)
Walker: Integration Walker agent
DMG: https://www.anticipy.ai/dl/Anticipy_1.0.0_aarch64.dmg (downloaded 09:08 PDT)
Test instance: Option A (tmp install at /tmp/integration-walker-1780157314)

## Verdict

**RED.**

A stranger installs the DMG, gets a working menubar tray + a polished welcome popover in roughly 1 minute. Beyond that, the "magic" advertised in the welcome flow does not work, because the shipped product never starts the loopback bridge (port 7777) or relaunches Chrome on the CDP port (9222). The 90s cold-start magic fails in 0.5 ms on a fresh install. Silent execute falls back to "Which one did you mean?" because there is no dossier and no Chrome to drive. Omar would say "What."

## Question being answered

"Would Omar say 'Oh my god' in 120 seconds after install?"

No. He would see the popover and say "nice". He would tap a button and nothing real would happen because the engine has no contacts and no browser.

## Phase timing (from launch of /Applications-equivalent binary)

| Phase | T+ from install | Result |
|---|---|---|
| DMG download | -87s (pre-install) | 2.5 GB pulled, SHA bde9fcbc |
| DMG mount | -23s (pre-install) | mounted at /tmp/dmg-mount |
| App copy + dequarantine | -5s (pre-install) | 2.5 GB copied |
| Anticipy launched (binary fork) | 0s | pid 89589 |
| anticipy-engine sidecar spawned | ~1s | pid 89677, port 8731 |
| /health returns 200 | 56s | warm load of FastAPI + Parakeet |
| Tray [A] icon visible | already at 56s | rendered with welcome content |
| Popover opens on tray click | instant | rich welcome view, 4 CTAs |
| Cold-start fires | T+332s (manual delay) | FAILS in 0.5 ms |
| First trivia FIRE | T+498s (post-upload) | 18.22 ms answer, ElevenLabs TTS cached |
| First silent execute | T+512s | CLARIFY fallback, did NOT execute |

Stripped of my exploration overhead, the true install-to-popover-ready time is **about 60 seconds**. The first trivia from a synthetic mic upload returns in **under 20 ms** once you can reach it. Those parts feel Apple-quality.

## Top 3 friction points

1. **Cold-start magic dies in 0.5 ms.** `POST /api/coldstart/start` returns immediately and `GET /api/coldstart/status` shows `state=failed`, `last_error="loopback bridge or Chrome CDP not available; cannot inhale"`. The DMG ships only two binaries (`Anticipy` shell, `anticipy-engine` sidecar). It does NOT ship or auto-start a loopback bridge on 7777, and it does NOT relaunch the user's Chrome with `--remote-debugging-port=9222`. There is no API surface (`/api/chrome/launch`, `/api/bridge/start`) to bootstrap either. A stranger has zero path to the advertised "10 people in your dossier in 90 seconds" experience.

2. **Silent execute clarifies on the first try because there is no dossier.** `POST /api/listen/inject` with `"draft a thank-you email to Altaf Ebrahim about today"` returned `plan.mode="clarify"`, `question="Which one did you mean?"`, `_infra_fallback:true`. Direct `POST /api/act` returned the same. With no inhaled contacts and no Chrome CDP, the planner cannot resolve "Altaf Ebrahim" and cannot open Gmail to draft. The screenshot of a Gmail draft requested by Phase 5 does not exist.

3. **`ANTICIPY_PORT` env var is ignored.** I launched with `ANTICIPY_PORT=8744` to keep Omar's clean-room state untouched. The sidecar bound 8731 anyway (`/tmp/integration-walker-1780157314/home/.anticipy/engine.port` contains `8731`). That means two Anticipy installs cannot coexist on one machine, and operator-mode E2E tests that try to isolate ports collide. Two related ship-quality bugs surfaced in `product-engine.log`: a warning that `JWT_SECRET` is unset and is using an insecure development default, plus a warning that `PROFILE_ENCRYPTION_KEY` is unset and is using a derived development key. Both should be auto-generated and persisted at first launch.

## Other notes from the walk

- The tray icon is the chunky pixelated "A" (Resources/icons/tray@2x.png). Looks aggressively low-fi against the polished popover. Not Apple-quality.
- Bundle id is `ai.anticipy.app`, `LSUIElement=true` (correct).
- Onboarding asks 7 questions via `/api/onboarding/start` (text-only flow exists), but that path never bootstraps Chrome or bridge either, so even after onboarding you cannot execute.
- ASR (Parakeet bundled, 2.3 GB of the DMG) transcribes "Wait, when did the Roman Empire fall?" exactly. Trivia cache hit returns "476 AD ... 1453" with attribution to Wikipedia. ElevenLabs TTS spawned and cached. This is genuinely fast.
- Handoff says shell SHA `51b62bba`, sidecar `be7ffded`. Live DMG ships shell `7ecd4d8c`, sidecar `aab3b1b9`. Either the handoff is stale or those were truncated/different hashes.

## Screencap paths

All under `/tmp/integration-walker-1780157314/`:

- `SCREENCAP-menubar-tray.png`. Full menubar with the pixelated A tray icon visible at right.
- `SCREENCAP-menubar-zoom.png`. Close-up of the tray icon area.
- `SCREENCAP-popover-welcome.png`. Opened popover showing "Welcome to Anticipy" with 4 onboarding CTAs.

Supporting JSON in same dir:
- `coldstart-start.json`, `coldstart-final.json`. Proves cold-start failure.
- `trivia-upload.json`, `trivia-recent.json`. Proves trivia works.
- `silent-exec.json`, `act-direct.json`. Proves silent execute clarifies.
- `onboarding-start.json`. Onboarding question 1.
- `tauri.log` (empty), `home/.anticipy/product-engine.log` (engine log).

## Cleanup status

Test Tauri pid 89589 and engine pid 89677 left running per handoff request that work dir stay in place for owner review. `WORK=/tmp/integration-walker-1780157314` preserved.

Nothing in /Applications was touched. Nothing in ~/.anticipy was touched. Nothing in Omar's launchd was touched. Chrome 9222 stayed dead the whole walk (it was already dead at start).

## What would flip this to GREEN

The shipped DMG needs to either (a) bundle and auto-start a loopback bridge + Chrome CDP launcher on first run, or (b) ship a clear popover wizard that does this with one click and shows progress. As-is, the welcome popover is a beautiful door to an empty room.
