# STATE

Current milestone: M0, ugly floor. Latest builder lap `20260606T020452Z` is PENDING judge review. M0 remains open. No milestone advances until a fresh held-out real day produces a real verified artifact in a separate judge session.

Proven:
- Setup completed on `autopilot/build`; `scripts/run_suite.sh` passed 29/29 in stub/mock mode; macOS app build passed; setup judge self-check ruled a planted fake FAKE at `logs/verdicts/setup-smoke_selfcheck.md`.
- Amended judge proof exists at `logs/verdicts/20260606T005447Z.md`: planted-fake self-check passed, computer-use self-test passed with screenshot, tamper scan was clean, Gemini OpenRouter cross-check agreed, and verdict was `BLOCKED_NO_HOLDOUT`.
- Control-plane audio plumbing proof: capped builder-visible MP3 smoke `20260606T013101Z` transcribed 90 seconds of speech-gated local audio, reached the live engine, posted 15 transcript lines, and produced 15 ignores with zero actions. This is not judge proof.
- Judge proof for `20260606T013339Z` exists at `logs/verdicts/20260606T013339Z.md`: planted-fake self-check passed, computer-use self-test passed with screenshot, tamper scan was clean, Gemini OpenRouter cross-check agreed, and verdict was `BLOCKED_NO_HOLDOUT`.
- Builder-side proof for `20260606T020452Z`: `bash scripts/run_suite.sh` passed 29/29; the required exact command `AUTOPILOT_LAP=20260606T020452Z bash scripts/realday.sh` completed on the builder-visible raw MP3, wrote `logs/trace/20260606T020452Z.jsonl` and `logs/last_realday.json`, processed 3,228 transcript segments, and returned 28 act, 385 ask, and 2,815 ignore decisions. This is not judge proof.
- No M0 real task is proven on a fresh unseen day. Builder-side raw audio runs and builder-side acts are not judge-verified artifacts.

Pending gates:
- No current hard human gate blocks M0.
- Non-blocking connector gates remain in `PENDING_FOR_OMAR.md`: Gmail compose scope, Google Docs Drive scope, Slack tool unavailable.
- Judge verdict for builder lap `20260606T020452Z` is PENDING.

Drift numbers:
- Builder-owned tests pass rate: 29/29, 100 percent, stub/mock coverage only.
- Reality judge verified pass rate on fresh unseen days under amended rules: 0/2 attempts verified, 0 percent. Current lap is pending and does not change the verified rate.
- Generalization: UNPROVEN. Real diverse users do not exist yet.
- Drift siren: builder test pass remains high while judge pass remains 0 percent. Do not advance a milestone from builder-side evidence.

Realday audio:
- One timestamped student MP3 is builder-visible in `realdays/raw/`.
- Four timestamped student MP3s are judge-only in `realdays/holdout/`.
- Builder must never read `realdays/holdout/`.
- Audio realdays are handled by local ffmpeg plus Whisper in `engine/anticipy_engine/capture/transcribe.py`; no always-on cloud STT.
- Lap `20260606T020452Z` changed capped audio selection only: when `ANTICIPY_REALDAY_AUDIO_MAX_SECONDS` is set, the cap now samples distributed speech chunks across the day instead of only the first capped seconds.
- The required exact realday command in lap `20260606T020452Z` had no cap env, so it ran the full builder-visible MP3 for 698.807 seconds.
- Holdout burn accounting remains: only a held-out day actually opened, transcribed, attempted, selected, or used in a verdict should rotate out. Inventory-only filename lists do not burn every listed day.

Dead ends not to retry blindly:
- Google Sheets and Google Docs canvas synthetic input.
- Amazon.ca Playwright automation.
- Anti-bot arms races for captcha or Cloudflare challenges.
- Always-on cloud transcription.
- Do not treat a verdict inventory list as proof that every listed holdout day was read or burned.
- Do not treat builder-side acts from noisy transcripts as proof of M0. The separate judge must verify a real artifact.

Law digest:
Never grade your own work. Reality in real apps is proof. No fake, no hardcode, no goal shrink. Oversight runs every lap regardless of cost. Work stays on `autopilot/build` until judge, different-family cross-check, diff scan, and tripwires all pass.
