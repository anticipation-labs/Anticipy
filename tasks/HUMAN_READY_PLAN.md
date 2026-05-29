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

1. **Build `desktop/src/popover.html`** so the Mac app actually has a visible UI when the user clicks the tray icon. Show: empty-dossier onboarding nudge (3 buttons: call me, drop an MP3, type a chat) OR a Now / Next / Past 3-column layout if dossier is populated. Tauri commands `fetch_active_task` / `fetch_next_tasks` / `fetch_past_tasks` already exist in `desktop/src-tauri/src/lib.rs:1547-1549` — wire them.

2. **Replace status row jargon on `/app` and Mac app**. Currently visible: `REAL localhost engine | pending=mic-asr windows=18`. Replace with plain `"Anticipy is listening"` plus a small subtle "details" hover for the technical state. File: `src/app/app/page.tsx` for the website, `desktop/src/main.js` for the Mac app.

3. **Empty-dossier nudge on `/app` page**. When a logged-in user has an empty dossier, the current page shows a stale demo card ("Maya wants the incident runbook from last month" with "Heard: (no transcript)"). Replace with: "Welcome to Anticipy. Let's get to know you." + 3 buttons linking to /onboarding/chat, /onboarding/audio, /onboarding/call.

4. **Wire Twilio onboarding to fire on first launch**. `scripts/v7/twilio_onboarding_call.py` works in MOCK + LOCAL_FALLBACK. Need: when Anticipy.app launches and dossier is empty AND Twilio creds present in env, automatically trigger the call. File: `desktop/src-tauri/src/lib.rs` first-launch hook.

5. **Pre-prompt TCC permissions in Mac app**. macOS shows scary Allow/Deny dialogs cold when engine first uses mic/screen/Automation. Add a welcome screen in the Mac app explaining what permissions Anticipy needs and why, before the OS dialog fires.

6. **MP3 upload UX**. The `/onboarding/audio` page exists but verify it actually accepts a real .mp3 upload, sends it to the engine, the engine transcribes it via parakeet-mlx, and the dossier is populated from it. End-to-end smoke test.

7. **Ambient mic UX**. On first launch, prompt the user "Want Anticipy to listen ambiently?" → on yes, kick off /api/listen/start. On no, leave it in pull-only mode.

8. **Login wall fallback (new rule per owner 2026-05-28)**. When the engine hits a login wall on a real service, trigger an outbound Twilio call to ask for the credential. Implement in `engine/app/action_engine/` wrapper (without touching frozen action_engine internals).

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
