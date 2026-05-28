# Anticipy v-final-prototype — CHANGELOG

Append-only ledger of every approach attempted and outcome. Do not re-attempt anything that has already failed here. Read at the start of every phase.

---

## 2026-05-13 — Session start

### Attempted approaches (this session)

- **WebSearch / WebFetch through the Claude Code harness** — currently broken with `API Error: 400 This model does not support the effort parameter`. Workaround: direct `curl` to public APIs (Hugging Face `/api/models`, Mistral `/v1/models`, DeepSeek `/v1/models`, Cerebras `/v1/models`). All worked. Do not retry WebSearch/WebFetch this session.

### Confirmed-and-still-broken approaches (carried over from prior rounds, per AUTONOMY_LOG.md and STATUS.md)

- **Cerebras 30 RPM free tier as the executor primary**, shipped in `extension/agent.js` with 2 s call spacing → guaranteed 429 cascade. Killed 0/35 overnight benchmark. Do not re-attempt without a paid Cerebras tier OR a server-driven call-spacing throttle delivered to the extension at runtime.
- **Server-driven `system_prompt` updates** can change the agent's prompt but cannot change tier order, spacing, model selection, or retry budget — those are baked into the shipped extension JS. Re-architecture requires an extension reload.
- **Patchright/Chromium subprocess on the wearer's machine** — explicitly off the table (cop-out #25). Wearer's actual Chrome only, via extension or `chrome.debugger`.
- **5-tier LLM provider rotation as the RPM fix** — tried, didn't work. The real fix is cache + queue + role split + (eventually) paid tier on one provider.
- **Single-model self-criticism in the executor** — degenerates per published research. Critic must run on a different model from the executor.

### Confirmed dead model/provider references in the codebase

These names still appear in code but the providers are explicitly forbidden by the prompt's provider whitelist:
- `claude*` (any version, Anthropic) — forbidden
- `kimi*`, `moonshot*` — forbidden
- `gpt-*`, `openai` — forbidden
- `deepgram` — forbidden (replaced by Parakeet local OR Mistral voxtral-mini)

Phase 2 archives every file that imports these.


---

## 2026-05-13 — Session 2 corrections (12 items, applied autonomously)

Per Omar's mid-session corrections to the v-final-prototype master prompt:

1. **Chrome attachment**: switched to REAL profile (`$HOME/Library/Application Support/Google/Chrome`) in `~/Library/LaunchAgents/com.anticipy.chrome.plist`. Sandbox profile at `~/.anticipy/chrome-profile/` is retained on disk but no longer the LaunchAgent target. The currently-loaded LaunchAgent instance still runs the sandbox Chrome on :9222 (because the running process holds the old args); on next Chrome restart by Omar, the new plist takes effect. Chrome supports only one instance per `--user-data-dir`, so the LaunchAgent's Chrome cannot start while Omar's main Chrome is running — `KeepAlive` will retry until Omar quits Chrome. Tab-group scoping ("Anticipy" group, background tabs only, never steal focus) is executor-side responsibility (Phase 5+ Mac app), not LaunchAgent. Documented for Mac app build.

2. **Executor architecture clarified**: the Mac Electron app shipped from anticipy.ai/download IS the production executor. It calls the Anthropic Computer Use API directly for canvas-app fallbacks (Google Sheets, Google Docs canvas, Figma). Claude Code Computer Use is the dev tool for THIS session's build work, NOT shipped to production users. Affects Phase 5 build: the Mac app integrates the Anthropic SDK's Computer Use endpoint, not Claude Code.

3. **WAV fixtures generated**: 17 hand-authored gold-standard utterances rendered as 16kHz mono WAV via `say --voice=Samantha --rate=180 -o ...aiff` then `afconvert -f WAVE -d LEI16@16000 -c 1`. Files at `engine/tests/fixtures/gold_standard/gs_{01..17}.wav`. The full audio→Intent pipeline (Parakeet → VAD → diarization → Stage 1 → Stage 1.5) tests against these. The remaining 15 utterances arrive when the synth-data generator (Phase 1 full) lands the boundary variants.

4. **chmod 700 `~/.anticipy/`** applied. `drwx------`. Personal data owner-only.

5. **Aevoy [ANTICIPY-Q] email protocol**: FROM `aevoy@anticipy.ai` via Resend; TO `omarkebrahim@gmail.com`. Reply path: Gmail API watch on the user's inbox filtered by `subject:[ANTICIPY-Q]`, body parsed against `Question ID: <uuid>`. Requires (a) Resend domain `anticipy.ai` configured to allow sending from `aevoy@`, (b) Gmail API OAuth for `omarkebrahim@gmail.com` with `gmail.readonly` scope. Both deferred to Phase 5+ build of the email-question runtime.

6. **Drop Uber, pick replacement skill**: Decision — Google Maps "Save directions / route to favorites". Reason: (a) has a non-destructive test mode (saving a route to "Saved" places is reversible; we can unsave to roll back), (b) generalizes to a category of "spatial memory" actions that other intents will trigger, (c) Google account is already authenticated on Omar's machine and used by the Calendar / Gmail skills, (d) no real-money risk like Uber's "I tested a fare quote and accidentally booked." Replaces Uber in the Phase 6 list.

7. **Hermes demotion thresholds spec'd**: skill drops below 70% success across the last 10 consecutive production runs → demote `active` → `shadow` AND queue for offline recompilation; below 50% over 5 consecutive runs → demote `shadow` → `retired` AND route those intents to the general executor (browser AX-tree + Computer Use fallback). Wired into `skill_library.status` lifecycle; the watchdog (Phase 9) runs the demotion check. Recompilation pipeline is Phase 9's queue, processes overnight.

8. **4-hour acceptance test is resumable**: if it fails at hour N, fix the gap and resume from `(N * 60)` minutes — replay-from-disk of captured audio. Restart from 0 ONLY if the fix changes the proactive engine's classification behavior (because previously-captured audio under the old classifier would now produce different intents, invalidating earlier minutes of the test). Captured audio rotates to `~/.anticipy/acceptance/test_N/`. Logged for Phase 10.

9. **Apple Developer cert check**: ran `security find-identity -v -p codesigning` — **0 valid identities found**. Omar needs to enroll at https://developer.apple.com/programs/enroll/ (3-7 day approval window). Phase 8 code-signing depends on this; queue it now in parallel. Aevoy `[ANTICIPY-Q]` email "Apple Developer enrollment needed" cannot send until the Aevoy runtime is built (correction #5), so this is logged here for Omar to act on directly. Once Omar enrolls and the cert is in his login keychain, the build pipeline picks it up automatically.

10. **Watchdog provider-responsiveness threshold**: 30s timeout on test call OR HTTP 401 OR HTTP 429 OR `quota_exceeded` response code = unresponsive. Three consecutive unresponsive checks → mark provider down, route around in the MAKER voter for 15 minutes, recheck. Wired into the Phase 9 watchdog spec.

11. **Nightly backup**: `~/.anticipy/` → Supabase storage bucket `anticipy-user-backups`, scoped to `user_id` path prefix, restorable via `engine/scripts/restore_user_data.py <user_id>`. Bucket policy: service_role write, per-user read. Backup runs nightly at 03:00 local via the watchdog LaunchAgent. Logged for Phase 9 build.

12. **FaceTime / multi-source audio**: wearer voiceprint compares against ALL incoming audio sources, not just the laptop mic. macOS `AVAudioEngine` taps the system mix (FaceTime callers, AirPods, room speakers). Segments matching wearer voiceprint fire the cascade. Segments matching other identified speakers (FaceTime callers' voiceprints stored as `kind:contact_voiceprint`) get logged to `anticipy_transcripts` with `is_wearer=false` but never fire intent extraction. Logged for Phase 3 diarization build.

