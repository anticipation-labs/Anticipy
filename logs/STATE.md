# STATE

Current milestone: M0, ugly floor. Latest lap `20260606T013339Z` was judged `BLOCKED_NO_HOLDOUT`; the unproven builder commit `1cbf82337d2a8fb4550720945f79bd2d31e9a360` was reverted by `9bdc118`. M0 remains open. No milestone advances until a fresh held-out real day produces a real verified artifact in a separate judge session.

Proven:
- Setup completed on `autopilot/build`; `scripts/run_suite.sh` passed 29/29 in stub/mock mode; macOS app build passed; setup judge self-check ruled a planted fake FAKE at `logs/verdicts/setup-smoke_selfcheck.md`.
- Amended judge proof exists at `logs/verdicts/20260606T005447Z.md`: planted-fake self-check passed, computer-use self-test passed with screenshot, tamper scan was clean, Gemini OpenRouter cross-check agreed, and verdict was `BLOCKED_NO_HOLDOUT`.
- Control-plane audio plumbing proof: capped builder-visible MP3 smoke `20260606T013101Z` transcribed 90 seconds of speech-gated local audio, reached the live engine, posted 15 transcript lines, and produced 15 ignores with zero actions. This is not judge proof.
- Judge proof for `20260606T013339Z` exists at `logs/verdicts/20260606T013339Z.md`: planted-fake self-check passed, computer-use self-test passed with screenshot, tamper scan was clean, Gemini OpenRouter cross-check agreed, and verdict was `BLOCKED_NO_HOLDOUT`.
- No M0 real task is proven on a fresh unseen day. Builder-side Calendar events and builder-visible raw audio runs are not judge proof.

Pending gates:
- No current hard human gate blocks M0.
- Non-blocking connector gates remain in `PENDING_FOR_OMAR.md`: Gmail compose scope, Google Docs Drive scope, Slack tool unavailable.

Drift numbers:
- Builder-owned tests pass rate: 29/29, 100 percent, stub/mock coverage only.
- Reality judge verified pass rate on fresh unseen days under amended rules: 0/2 attempts verified, 0 percent.
- Generalization: UNPROVEN. Real diverse users do not exist yet.
- Drift siren: builder test pass remains high while judge pass remains 0 percent. Do not advance a milestone from builder-side evidence.

Realday audio:
- One timestamped student MP3 is builder-visible in `realdays/raw/`.
- Four timestamped student MP3s are judge-only in `realdays/holdout/`.
- Builder must never read `realdays/holdout/`.
- Audio realdays are handled by local ffmpeg plus Whisper in `engine/anticipy_engine/capture/transcribe.py`; no always-on cloud STT.
- Current control-plane repair in progress: the 013339 judge treated all holdout files as unusable because an older verdict named them as inventory. Holdout burn accounting is being clarified without reading holdout contents: only a held-out day actually opened, transcribed, attempted, or used in a verdict should rotate out.

Dead ends not to retry blindly:
- Google Sheets and Google Docs canvas synthetic input.
- Amazon.ca Playwright automation.
- Anti-bot arms races for captcha or Cloudflare challenges.
- Always-on cloud transcription.
- Do not treat a verdict inventory list as proof that every listed holdout day was read or burned.

Law digest:
Never grade your own work. Reality in real apps is proof. No fake, no hardcode, no goal shrink. Oversight runs every lap regardless of cost. Work stays on `autopilot/build` until judge, different-family cross-check, diff scan, and tripwires all pass.
