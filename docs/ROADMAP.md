# Anticipy V8 Roadmap

Author: V7 retro agent
Generated: 2026-05-28
Predecessor: `tasks/DONE.md`
Repo: /Users/omarebrahim/Developer/Anticipy-V7
Branch at handoff: main at `3a8b9fb2`

This roadmap is what V8 (the next Ralph Loop cycle) must do to turn V7's engineering pre-flight into V2 PRD "done." Items are ranked by what unblocks the most other items.

## V8 priorities ranked

### P0. W4: rebuild and ship the engine DMG so V7.2, V7.4, V7.5 flip green

Why first: 3 of 4 red gates in `state/check_done_v7.json` are downstream of "engine source has changed since the last DMG build." This is mechanical, not a research problem. It unblocks every other deploy-parity test and lets us re-run V7.18 clean-room installs against the fixed engine.

Concrete tasks:
1. Build `engine/` to a Mac arm64 binary via PyInstaller with parakeet bundled. Run from `engine/uv.lock` so the dependency set is reproducible.
2. Confirm DMG is over 2 GB (parakeet model weights are the heavy bit). Reject any build that comes back under 2 GB; that means parakeet did not get bundled.
3. Upload to the R2 public bucket `anticipy-downloads`. Compute SHA-256.
4. Update `state/builds/manifest.json` with the new SHA, commit, and timestamp.
5. Redeploy `src/` to Vercel so `/api/app/state` reports the new commit and `/dl/Anticipy_1.0.0_aarch64.dmg` serves the new DMG.
6. Re-run `scripts/v7/check_done.sh`. Verify V7.2, V7.4, V7.5 flip green.
7. Re-run V7.18 clean-room install on a fresh Mac account.

Owner suggestion: a builder agent with R2 + Vercel CLI in env.

### P1. W3a: land the clarify-reflex fix and re-score memory precision

Why second: the headline product quality issue is that the planner returns `mode=clarify` on 16 of 20 hard transcripts when the dossier already has the answer. The diagnosis, the four-step heuristic, and the unit-style assertions are documented in `state/v7/clarify_reflex_fix_notes.md`. The fix is staged in `engine/app/product/server.py` in the worktree. Land it as a named commit, then re-run the memory precision scorer to get a new composite score.

Concrete tasks:
1. Land the clarify-reflex fix per `state/v7/clarify_reflex_fix_notes.md` (consult `DossierLoader.people()` before falling through to the canned clarify; substantive task with `missing_slots=["recipient_email"]` when the recipient name is present but the email is not).
2. Add a pytest harness for the planner so the unit-style assertions in the notes file become real regression tests. Currently the engine has no pytest harness for the planner; ship one.
3. Re-run `scripts/v7/score_memory_precision.py` against the 20 hard transcripts. Target composite score is at least 0.75 (today 0.46).
4. Re-run the supervised stranger batch. Target V7.12 verb_category_count >= 20.

Owner suggestion: a builder agent with OpenRouter budget for the judge cascade re-run.

### P2. W5: wire CDP Input.insertText for Gmail draft persistence so Z-001 step 9 turns green

Why third: Z-001 step 9 is the single open step in the V2 PRD Phase 5 end-to-end story. Once it turns green, V2 PRD Z-001 is met.

Concrete tasks:
1. In `engine/app/product/server.py` (the `direct_gmail_compose` path used by `engine_act`), after opening the Gmail compose URL via CDP, wait for the compose iframe to load. Use CDP `Runtime.evaluate` to find the body textarea selector.
2. Use CDP `Input.insertText` to type the marker UUID + body content into the textarea. This triggers Gmail autosave (about 2 seconds) which commits the draft to the server.
3. Update `scripts/v7/z001_e2e_harness.py` step 9 to poll the Gmail drafts list (already wired) for the marker UUID with a 30 second budget.
4. Re-run Z-001 and confirm 9 of 9 steps green. Save evidence to `state/v7/z001_e2e_runs/<timestamp>/`.

Owner suggestion: same builder as W3a (both touch `server.py`).

### P3. W4 part 2: fix engine inject p95 30 s ceiling

Why fourth: the ceiling makes the strangers loop time out per persona, makes proactive day pipeline starve, and makes "Now / Next / Past" popover lag 30 seconds behind speech. Three root causes are documented in `state/v7/engine_load_profile_20260528T040453Z/analysis.md`. The fix is in scope for V8 because all three are inside `engine/` and ride on the same DMG rebuild as P0.

Concrete tasks (per the load profile analysis):
1. Make `listen_inject` `async def` and offload work via `await asyncio.to_thread`. Removes the double-thread that compounds GIL pressure. (`engine/app/product/server.py:4229`)
2. Replace the per-call `_with_timeout` thread spawn with a single module-level `ThreadPoolExecutor(max_workers=8)`. (`engine/app/product/server.py:826-843`)
3. Bound `_compose_task_from_memory`'s retry budget. Today 4 attempts with 1.5 + 3.5 + 5.5 = 10.5 s of wall-clock backoff. Cut to 1 retry + 1 s backoff. Short-circuit when outcome is ACTED or CONFIRMED. (`engine/app/product/server.py:4956-4971`)
4. Cache `_compose_task_from_memory` results by `(instruction, profile_hash, recent_window_hash)` for 60 s.
5. Raise ASR executor `max_workers` from 1 to 2 with `ANTICIPY_ASR_WORKERS` env override. (`engine/app/audiostack/audio.py:142-150`)
6. Fix the `_transcript_from_normalized` correctness bug at `engine/app/product/intent_extractor.py:170-184` (the `capture` dict check always wins and shadows the `text` fallback).

Performance targets:
- inject p95 under 5 s (today 30 s)
- intent_extract p95 under 4 s (today 10 s)
- ASR executor handles 2 concurrent uploads in `max(t1, t2)` not `t1 + t2`

### P4. M3 cloud sync round-trip verification

Why fifth: today's evidence shows the engine successfully posts to `https://www.anticipy.ai/api/dossiers/upsert` and `/api/resolution-traces/insert` and the server returns 200. We do not have a round-trip read test that confirms the data is queryable from the cloud after replication. This matters for the cross-device story.

Concrete tasks:
1. Write a verifier that posts a dossier with a unique marker via the engine, then queries `https://www.anticipy.ai/api/dossiers/get?user_id=<id>` and asserts the marker is present.
2. Same for resolution traces. Query by ingest_id.
3. Add as a new gate (V7.21 cloud sync round trip) or merge into V7.20.

Owner suggestion: a verifier agent.

### P5. Twilio B-001 real outbound call (V2 PRD Phase 4)

Why fifth: today only LOCAL_FALLBACK and MOCK_TWILIO paths are verified (see `state/v7/twilio_onboarding_20260528T045539Z/run.json`). Real Twilio voice is a P1 upgrade per `state/v7/twilio_onboarding_status.md`, not a P0 blocker for V2 PRD Phase 4 since the text-chat path already produces a populated dossier.

Concrete tasks (per `state/v7/twilio_onboarding_status.md`):
1. Create `engine/app/dossier/__init__.py` and `engine/app/dossier/call.py` with `handle_outbound`, `handle_inbound`, `recent_events`, `recent_dossier_writes`, `mock_mode`.
2. `handle_outbound` reads `TWILIO_ACCOUNT_SID` / `TWILIO_AUTH_TOKEN` / `TWILIO_PHONE_NUMBER`, calls `twilio.rest.Client.calls.create(to=phone, from_=TWILIO_PHONE_NUMBER, url=<TwiML webhook>)`, guarded by `TWILIO_MOCK`.
3. Add `twilio>=9.0` to `engine/uv.lock`.
4. Stand up a publicly-reachable TwiML webhook at `https://www.anticipy.ai/api/dossier/inbound`.
5. Bridge the call transcript back into `_save_profile` / `_seed_profile_memory` so the dossier reflects the call.

## Follow-up tasks we could not get to in V7

- `tasks/v2_prd.json` is not maintained in V7 (V7 uses 20 mechanical gates instead of V2 PRD stories). V8 should either (a) populate `tasks/v2_prd.json` against the V2 PRD phases for parity, or (b) explicitly retire that file in `docs/ANTICIPY_V2_PRD.md` and treat V7 gates as the V2 verifier surface.
- `.verifier/runs/` is referenced in `docs/ANTICIPY_V2_PRD.md` as the evidence root. V7 evidence actually lives under `state/v7/<run_name>/`. V8 should either move evidence to `.verifier/runs/` to match the PRD, or update the PRD to point at `state/v7/`.
- The full audit phase (Phase 0 of V2 PRD: A-001 through A-007) is not run as a named harness in V7. Most A-N stories are implicitly covered by V7 gates, but a single `scripts/v8/run_v2_audit.sh` would make the mapping explicit and let V8 produce `AUDIT_REPORT.md` per the PRD spec.
- Fresh-Mac wipe-and-replay (item 7 of "Definition of done" in `docs/ANTICIPY_V2_PRD.md`) has never been run. V8 should add a script that wipes `~/.anticipy/`, `~/Library/LaunchAgents/ai.anticipy.app.plist`, `~/Library/Application Support/Anticipy/`, and `/Applications/Anticipy.app`, then drives the Z-001 journey on the wiped machine.
- V7.20 strict screenshot-bytes verification produces 3 demoted stranger UUIDs per cycle. V8 should either tighten the screenshot capture path to never miss bytes or raise the threshold so demotions stop counting against V7.12.

## Performance and scale targets for V8

| Metric | V7 today | V8 target | Source of truth |
|---|---|---|---|
| `/api/listen/inject` p95 | 30,023 ms | under 5,000 ms | `state/v7/engine_load_profile_20260528T040453Z/metrics.json` |
| `/api/intent/extract` p95 | 10,008 ms | under 4,000 ms | same |
| `/api/listen/status` p95 | 23 ms | unchanged | same |
| ASR worker concurrency | 1 | 2 (Apple Silicon GPU streams) | `engine/app/audiostack/audio.py:142` |
| Memory precision composite | 0.46 | 0.75 | `state/v7/memory_precision_20260528T031414Z.json` |
| Strangers last-20 pass rate | 18 of 20 | 20 of 20 | `state/stranger_breadth.json` |
| Verb categories distinct | 19 | 20+ | same |
| Stranger demotion rate | 3 demotions per 48 interactions | 0 demotions | same |
| Z-001 steps green | 8 of 9 | 9 of 9 | `state/v7/z001_e2e_runs/20260528T045740Z/result.json` |

## Hardware path (titanium pendant, post-funding)

V2 PRD explicitly defers the titanium pendant to post-funding. V7 already proves the software is hardware-ready via the Bluetooth mic selection path (V7.9 green). The pendant is a different physical input device speaking the same Bluetooth A2DP profile as any other wireless mic.

Order of operations once funded:
1. Pick a Bluetooth SoC for the pendant (Nordic nRF5340 or Apollo4 Blue are the two candidates per the BOM in `docs/BOM.md`).
2. Pair-and-discover handshake with the Mac app. The Mac app already has the device-selection UI; the pendant just needs to advertise as an A2DP source.
3. Battery: the BOM target is one-week always-on. Pendant ASR will likely stream to Mac, not run on-device, so the SoC is doing transport, not inference.
4. Industrial design lock. Per `docs/BOM.md`, target form factor is titanium milled, dome microphone array, magnetic clasp.
5. Pilot run of 25 units to Omar's beta list.

V8 does not build any of this. V8 documents the pendant interface contract so the hardware team can build against it without a software change.

## Notarization path (Apple Developer cert)

V2 PRD explicitly defers notarization. Today the DMG is ad-hoc signed and onboarding has a documented right-click-to-open animation per `AGENTS.md`. Notarization is a $99 per year Apple Developer Program enrollment plus a CI pipeline change to call `xcrun notarytool submit`.

V8 should:
1. Decide whether to enroll in Apple Developer Program (Omar decision, not loop decision).
2. If yes, wire `notarytool submit --apple-id <omar> --team-id <id> --password <app-specific> <dmg>` into the DMG build script.
3. Wait for Apple's notarization (typically 5 to 30 minutes).
4. Staple the ticket with `xcrun stapler staple <dmg>`.
5. Ship.

If no, V8 keeps the ad-hoc signed DMG and the right-click-to-open animation. The product still works; the UX is one extra click.

## Multi-user / per-device support

V2 PRD explicitly defers multi-user per Mac. One user per install today. V7 does not enforce this in code; it is a documentation contract.

V8 should:
1. Decide whether to enforce single-user via a check at engine startup (refuse to start if a different macOS user is already provisioned) or to leave it as a documentation contract.
2. If enforced, add the check in `engine/app/product/server.py` at the provisioning step and surface a clear error to the second user.

## Mobile (iOS) handoff

Not in V2 PRD scope. Listed here for V9 or later.

The pendant story works without iOS because the Mac is the listening device. iOS becomes relevant when (a) the pendant streams directly to iPhone instead of Mac, or (b) users want to draft and confirm on their phone instead of their laptop.

V8 should not build any of this. V8 captures the requirement so the cross-platform handoff (Supabase auth state, dossier sync) is designed correctly the first time it ships.

## What V8 does not do

- Does not implement the titanium pendant hardware. See "Hardware path" above.
- Does not implement notarization unless Omar enrolls in Apple Developer Program.
- Does not implement multi-user per Mac.
- Does not implement Intel Mac builds.
- Does not implement email verification.
- Does not implement a Chrome extension. The Mac app drives the user's real Chrome via CDP.

These are explicit non-goals.

## Exit criteria for V8

V8 is done when:
1. All 20 mechanical gates in `scripts/v7/check_done.sh` are green.
2. Z-001 end-to-end run shows 9 of 9 steps green and an actual Gmail draft visible in the user's Gmail inbox.
3. Memory precision composite score is at least 0.75 (today 0.46).
4. `/api/listen/inject` p95 is under 5 seconds under 100-way concurrent load.
5. Engine fixes in this cycle are packaged into a fresh DMG and shipped to R2.
6. Live `/api/app/state` reports the same commit as `origin/main`.
7. A fresh-Mac wipe-and-replay completes the Z-001 journey with no manual intervention.

Once 1 through 7 are met, V8 writes `tasks/V8_DONE.md` and the loop exits.
