# STATE

Current milestone: M0, ugly floor. Lap `20260606T013339Z` is a builder slice with judge verdict `PENDING`. It improved generic calendar-hold policy and ran the required uncapped builder-visible MP3 realday, but no milestone advances until a fresh held-out day produces a real verified artifact in a separate judge session.

Proven:
- Setup completed on `autopilot/build`; `scripts/run_suite.sh` passed 29/29 in stub/mock mode; macOS app build passed; setup judge self-check ruled a planted fake FAKE at `logs/verdicts/setup-smoke_selfcheck.md`.
- Amended judge proof exists at `logs/verdicts/20260606T005447Z.md`: planted-fake self-check passed, computer-use self-test passed with screenshot, tamper scan was clean, Gemini OpenRouter cross-check agreed, and verdict was `BLOCKED_NO_HOLDOUT`.
- Control-plane audio plumbing proof: capped builder-visible MP3 smoke `20260606T013101Z` transcribed 90 seconds of speech-gated local audio, reached the live engine, posted 15 transcript lines, and produced 15 ignores with zero actions. This is not judge proof.
- Builder-owned policy proof for `20260606T013339Z`: triage and harm-line batteries passed after adding generic calendar-hold phrasing, and `bash scripts/run_suite.sh` passed 29/29.
- Builder-visible whole-day run for `20260606T013339Z`: `AUTOPILOT_LAP=20260606T013339Z bash scripts/realday.sh` processed `realdays/raw/2026-05-20_07_34_11.mp3` with local Whisper `tiny.en`, 18,000.04 seconds of audio, 665 chunks, 3,228 kept segments, 26 act decisions, 387 asks, 2,815 ignores, 52 successful live-scorecard goals, total model cost 1.04, and wall time 617.016 seconds. This is not judge proof.
- No M0 real task is proven on a fresh unseen day. The builder-side Calendar event from lap `20260606T005447Z` and builder-visible realday actions from `20260606T013339Z` are not judge proof.

Pending gates:
- No current hard human gate blocks M0.
- Non-blocking connector gates remain in `PENDING_FOR_OMAR.md`: Gmail compose scope, Google Docs Drive scope, Slack tool unavailable.

Drift numbers:
- Builder-owned tests pass rate: 29/29, 100 percent, stub/mock coverage only.
- Reality judge verified pass rate on fresh unseen days under amended rules: 0/1 attempts verified, 0 percent.
- Generalization: UNPROVEN. Real diverse users do not exist yet.
- Quality drift to address next: the full builder-visible MP3 produced 387 asks, many from low-information repeated fragments, so realday coverage increased without fresh judge verification.

Realday audio:
- One timestamped student MP3 is builder-visible in `realdays/raw/`.
- Four timestamped student MP3s are judge-only in `realdays/holdout/`.
- Builder must never read `realdays/holdout/`.
- Audio realdays are handled by local ffmpeg plus Whisper in `engine/anticipy_engine/capture/transcribe.py`; no always-on cloud STT.

Dead ends not to retry blindly:
- Google Sheets and Google Docs canvas synthetic input.
- Amazon.ca Playwright automation.
- Anti-bot arms races for captcha or Cloudflare challenges.
- Always-on cloud transcription.

Law digest:
Never grade your own work. Reality in real apps is proof. No fake, no hardcode, no goal shrink. Oversight runs every lap regardless of cost. Work stays on `autopilot/build` until judge, different-family cross-check, diff scan, and tripwires all pass.
