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


2. **Replace status row jargon on `/app` and Mac app**. Currently visible: `REAL localhost engine | pending=mic-asr windows=18`. Replace with plain `"Anticipy is listening"` plus a small subtle "details" hover for the technical state. File: `src/app/app/page.tsx` for the website, `desktop/src/main.js` for the Mac app.

3. **Empty-dossier nudge on `/app` page**. When a logged-in user has an empty dossier, the current page shows a stale demo card ("Maya wants the incident runbook from last month" with "Heard: (no transcript)"). Replace with: "Welcome to Anticipy. Let's get to know you." + 3 buttons linking to /onboarding/chat, /onboarding/audio, /onboarding/call.

4. **Wire Twilio onboarding to fire on first launch**. `scripts/v7/twilio_onboarding_call.py` works in MOCK + LOCAL_FALLBACK. Need: when Anticipy.app launches and dossier is empty AND Twilio creds present in env, automatically trigger the call. File: `desktop/src-tauri/src/lib.rs` first-launch hook.

5. **Pre-prompt TCC permissions in Mac app**. macOS shows scary Allow/Deny dialogs cold when engine first uses mic/screen/Automation. Add a welcome screen in the Mac app explaining what permissions Anticipy needs and why, before the OS dialog fires.

6. **MP3 upload UX**. DONE 2026-05-29. End-to-end smoke verified: POST /api/onboarding/from_audio with audio/mpeg body, engine transcribed via parakeet-mlx (66 chars on a 12.5KB sample), broker extracted profile (people resolved). Evidence: proof-artifacts/mp3_upload_20260529/from_audio_response.json. Z-001 9/9 PASS after (state/v7/z001_e2e_runs/20260529T010807Z). Root cause of earlier ModuleNotFoundError _lzma was source engine launched with pyenv 3.10.14 (built without xz); restart with engine/.venv/bin/python3 (3.11.12) fixed it. Packaged engine in /Applications/Anticipy.app bundles its own Python via PyInstaller so users are unaffected.

7. **Ambient mic UX**. DONE 2026-05-29. The welcome state of the tray popover already had a "Skip onboarding, just listen" card; its handler was wired to a Tauri command that does not exist (`set_ambient_only_mode`). Replaced with a direct POST to http://127.0.0.1:8731/api/listen/start and an inline status box (success: "Listening through <device>. Close this and get on with your day." / failure: surfaces the engine error). Verified end-to-end against running engine: 200 with `{"on":true,"audio_device":{"name":"BlackHole 2ch",...}}`. Z-001 still 9/9 PASS (state/v7/z001_e2e_runs/20260529T011346Z). File: desktop/src/popover.html.

8. **Login wall fallback (new rule per owner 2026-05-28)**. DONE 2026-05-29. New sibling module engine/app/product/login_wall_responder.py (does NOT touch frozen action_engine/). Two new endpoints on server.py: GET /api/action/login_wall_detect (pure detection, no side effects) and POST /api/action/login_wall_notify (places Twilio call + macOS say fallback). Detector matches against 23 known login hosts (Google, Microsoft, Slack, Trello, Atlassian, Notion, Linear, GitHub, X, LinkedIn, Stripe, Amazon, Apple ID, Dropbox, Okta, Auth0, Calendly, etc.) plus a title-hint fallback. The Twilio TwiML deliberately does NOT ask the user to speak the password (ASR on secrets is unreliable and leaves a recorded trail); instead it tells the user to type the password into the open browser window. Verified live: gmail signin → service "Google"; gmail inbox → not a wall; "Log In" title → wall on unknown host; notify without phone + without TWILIO creds → twilio skipped, say-fallback spoken. Z-001 9/9 PASS after (state/v7/z001_e2e_runs/20260529T011856Z). Evidence: proof-artifacts/login_wall_20260529/probes.json.

9. **DMG rebuild + reship**. `ship.sh` keeps OOM-killing pyinstaller. Fix the build (chunked imports, no parakeet bundling in the engine binary, or stream from disk). Without this, real users get yesterday's engine.

10. **Remove or hide unused legacy Chrome extension paths** (`extension/`, `extension_v2/`, `extension_v3/`). The product per V2 PRD does not need a user-facing extension; install.sh installing one is a contradiction.

## What is DONE already (do not re-touch)
- Z-001 9/9 PASS (proven, evidence at state/v7/z001_e2e_runs/20260528T235937Z/)
- DMG download URL fix (commit 3edd1c4e)
- OpenRouter model ID fix (commit 1907a4aa)
- M3 Supabase cloud sync (commit de1a8c38)
- Twilio onboarding code (commit c6491d2e), MOCK + LOCAL_FALLBACK both PASS
- Memory partition fix (commit 349f0241)
- Bridge async-rewrite (commit d376981a) — 50/50 success
