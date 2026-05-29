# Anticipy human-ready plan

## Goal
A brand-new human installs Anticipy from anticipy.ai, opens the Mac app, gets walked through onboarding (call OR mp3 OR chat OR ambient), starts using it without jargon. No engineer-only UI artifacts visible.

## Bar (verifier checks)
- Engine + bridge + Chrome alive
- Z-001 end-to-end: 9 / 9 PASS
- 18-CHECK non-audio: at least 14 / 15 PASS (audio CHECKs 06/09/10 explicitly skipped per owner)
- Mac app shows at least one visible window
- desktop/src/popover.html exists
- All 3 onboarding pages reachable on website: /onboarding/chat, /onboarding/audio, /onboarding/call
- Status row in plain English (no "pending=mic-asr windows=18" jargon)

## Items, in priority order


2. **Replace status row jargon on `/app` and Mac app**. DONE earlier 2026-05-28 (commits 2aef626b + 406b07f8). src/app/app/page.tsx now reads "Anticipy / Listening through your microphone / Heard something just now" instead of "REAL localhost engine | pending=mic-asr windows=18". The Mac app popover is built from desktop/src/popover.html and never showed that jargon; the website was the only surface.

3. **Empty-dossier nudge on `/app` page**. DONE earlier 2026-05-28 (commit ee30f12a). Empty state on /app now shows a 3-card Welcome picker (call / MP3 / chat) instead of the stale "Maya wants the incident runbook" demo card. The gate is `run.proposal && run.transcript` so we never surface a proposal whose transcript is gone.

4. **Wire Twilio onboarding to fire on first launch**. DONE earlier 2026-05-28 (commit db3410ef). /api/onboarding/call_stub now spawns the real outbound Twilio call (via scripts/v7/twilio_onboarding_call.py) when TWILIO_ACCOUNT_SID + TWILIO_AUTH_TOKEN + TWILIO_PHONE_NUMBER are present AND TWILIO_TEST_TO_REAL_NUMBER=1 AND TWILIO_MOCK is not truthy. Without those it stays a safe stub. The Mac app first-launch detection of "dossier empty + creds present" happens implicitly via the onboarding/call page calling this endpoint.

5. **Pre-prompt TCC permissions in Mac app**. DONE earlier 2026-05-28 (commit fcde9857). desktop/src/popover.html welcome state now shows a perm-note card explaining macOS will ask for mic / screenshots / Automation, why each is needed, and that the user can revoke any of them later in System Settings.

6. **MP3 upload UX**. DONE 2026-05-29. End-to-end smoke verified: POST /api/onboarding/from_audio with audio/mpeg body, engine transcribed via parakeet-mlx (66 chars on a 12.5KB sample), broker extracted profile (people resolved). Evidence: proof-artifacts/mp3_upload_20260529/from_audio_response.json. Z-001 9/9 PASS after (state/v7/z001_e2e_runs/20260529T010807Z). Root cause of earlier ModuleNotFoundError _lzma was source engine launched with pyenv 3.10.14 (built without xz); restart with engine/.venv/bin/python3 (3.11.12) fixed it. Packaged engine in /Applications/Anticipy.app bundles its own Python via PyInstaller so users are unaffected.

7. **Ambient mic UX**. DONE 2026-05-29. The welcome state of the tray popover already had a "Skip onboarding, just listen" card; its handler was wired to a Tauri command that does not exist (`set_ambient_only_mode`). Replaced with a direct POST to http://127.0.0.1:8731/api/listen/start and an inline status box (success: "Listening through <device>. Close this and get on with your day." / failure: surfaces the engine error). Verified end-to-end against running engine: 200 with `{"on":true,"audio_device":{"name":"BlackHole 2ch",...}}`. Z-001 still 9/9 PASS (state/v7/z001_e2e_runs/20260529T011346Z). File: desktop/src/popover.html.

8. **Login wall fallback (new rule per owner 2026-05-28)**. DONE 2026-05-29. New sibling module engine/app/product/login_wall_responder.py (does NOT touch frozen action_engine/). Two new endpoints on server.py: GET /api/action/login_wall_detect (pure detection, no side effects) and POST /api/action/login_wall_notify (places Twilio call + macOS say fallback). Detector matches against 23 known login hosts (Google, Microsoft, Slack, Trello, Atlassian, Notion, Linear, GitHub, X, LinkedIn, Stripe, Amazon, Apple ID, Dropbox, Okta, Auth0, Calendly, etc.) plus a title-hint fallback. The Twilio TwiML deliberately does NOT ask the user to speak the password (ASR on secrets is unreliable and leaves a recorded trail); instead it tells the user to type the password into the open browser window. Verified live: gmail signin → service "Google"; gmail inbox → not a wall; "Log In" title → wall on unknown host; notify without phone + without TWILIO creds → twilio skipped, say-fallback spoken. Z-001 9/9 PASS after (state/v7/z001_e2e_runs/20260529T011856Z). Evidence: proof-artifacts/login_wall_20260529/probes.json.

9. **DMG rebuild + reship**. BUILD FIX SHIPPED 2026-05-29. The PyInstaller --onefile step was OOM-killed during the final CArchive packaging because UPX was compressing in-memory and several heavy transitive deps (skimage, matplotlib, IPython, jupyter, notebook, pytest, tkinter, PyQt5/6, PySide2/6) were being bundled even though the engine never imports them. Added `--noupx` and an EXCLUDES list to desktop/scripts/build-engine-sidecar.sh. New sidecar builds in ~72s, lands at 163.9 MiB at desktop/src-tauri/bin/anticipy-engine-aarch64-apple-darwin, signed and verified. Smoke-tested: binary starts on a free port and serves /health correctly. sklearn is intentionally NOT excluded because app/memory_v2/draw.py imports it for the TF-IDF embedding fallback and the caller does not catch ImportError. The reship-to-R2 step is now unblocked: `bash scripts/ship.sh` will run end-to-end given a clean git tree and R2_* env credentials.

10. **Remove or hide unused legacy Chrome extension paths**. DONE 2026-05-29. Moved via `git mv`: extension/ → _archive/legacy_extension_v1/, extension_v2/ → _archive/legacy_extension_v2/, extension_v3/ → _archive/legacy_extension_v3/. Added _archive/README.md explaining these are not part of the shipping product (V2 PRD: Mac DMG is the install surface, engine drives real Chrome via CDP, no user-facing browser extension). Did NOT delete engine/app/ws_bridge.py / orchestrator.py / main.py extension references (dormant code paths not in the current product flow; deleting them would balloon the blast radius of this cleanup and risk regressing Z-001). Did NOT modify installer/install.sh or public/install.sh (separate legacy concern). Z-001 still 9/9 PASS.

## What is DONE already (do not re-touch)
- Z-001 9/9 PASS (proven, evidence at state/v7/z001_e2e_runs/20260528T235937Z/)
- DMG download URL fix (commit 3edd1c4e)
- OpenRouter model ID fix (commit 1907a4aa)
- M3 Supabase cloud sync (commit de1a8c38)
- Twilio onboarding code (commit c6491d2e), MOCK + LOCAL_FALLBACK both PASS
- Memory partition fix (commit 349f0241)
- Bridge async-rewrite (commit d376981a) — 50/50 success
