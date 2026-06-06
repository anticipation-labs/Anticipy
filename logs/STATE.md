# STATE

Current milestone: M0, ugly floor. The amended judge ruled `BLOCKED_NO_HOLDOUT` for lap `20260606T005447Z` because the only held-out realdays are MP3 files and the realday runner rejects audio. The unproven builder slice is reverted by the gate. Next slice is generic MP3 realday ingestion, using only builder-visible raw audio or generic fixtures.

Proven:
- Setup completed on `autopilot/build`; `scripts/run_suite.sh` passed 29/29 in stub/mock mode; macOS app build passed; setup judge self-check ruled a planted fake FAKE at `logs/verdicts/setup-smoke_selfcheck.md`.
- Amended judge proof exists at `logs/verdicts/20260606T005447Z.md`: planted-fake self-check passed, computer-use self-test passed with screenshot, tamper scan was clean, Gemini OpenRouter cross-check agreed, and verdict was `BLOCKED_NO_HOLDOUT`.
- No M0 real task is proven on a fresh unseen day. The builder-side Calendar event from lap `20260606T005447Z` is not judge proof.

Pending gates:
- No current hard human gate blocks M0.
- Non-blocking connector gates remain in `PENDING_FOR_OMAR.md`: Gmail compose scope, Google Docs Drive scope, Slack tool unavailable.

Drift numbers:
- Builder-owned tests pass rate: 29/29, 100 percent, stub/mock coverage only.
- Reality judge verified pass rate on fresh unseen days under amended rules: 0/1 attempts verified, 0 percent.
- Generalization: UNPROVEN. Real diverse users do not exist yet.

Realday audio:
- One timestamped student MP3 is builder-visible in `realdays/raw/`.
- Four timestamped student MP3s are judge-only in `realdays/holdout/`.
- Builder must never read `realdays/holdout/`.

Dead ends not to retry blindly:
- Google Sheets and Google Docs canvas synthetic input.
- Amazon.ca Playwright automation.
- Anti-bot arms races for captcha or Cloudflare challenges.
- Always-on cloud transcription.

Law digest:
Never grade your own work. Reality in real apps is proof. No fake, no hardcode, no goal shrink. Oversight runs every lap regardless of cost. Work stays on `autopilot/build` until judge, different-family cross-check, diff scan, and tripwires all pass.
