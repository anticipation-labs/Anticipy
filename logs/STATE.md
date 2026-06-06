# STATE

Current milestone: M0, ugly floor. Latest judged lap `20260606T070041Z` was `FAKE`: the separate judge ran a held-out realday, found `act=31`, `ask=271`, `ignore=1690`, and verified no current-lap Calendar, Gmail, browser, or other external real-world artifact. The unproven builder code slice from commit `04f28eacac4529ab39898a0158b3b632237f96f4` was reverted by the failed-lap gate. M0 remains open until a fresh held-out real day produces a real verified artifact in a separate judge session.

Proven:
- Setup completed on `autopilot/build`; `scripts/run_suite.sh` passed 29/29 in stub/mock mode; macOS app build passed; setup judge self-check ruled a planted fake FAKE at `logs/verdicts/setup-smoke_selfcheck.md`.
- Prior amended judge proofs exist through `logs/verdicts/20260606T060511Z.md`. Each kept proof includes planted-fake self-check, computer-use self-test, tamper scan, different-family OpenRouter cross-check, and a separate verdict. None verified an M0 real artifact.
- Judge proof for `20260606T070041Z` exists at `logs/verdicts/20260606T070041Z.md`: planted-fake self-check passed, computer-use self-test passed with screenshot, tamper scan was clean for the target builder commit, a held-out MP3 ran end to end, Calendar and Gmail read-back/screenshots found no current-lap artifact, Gemini OpenRouter cross-check agreed with `FAKE`, and no held-out day rotated out.
- Amendment 2 is active: raw traces, `logs/last_realday.json`, transcript files, `.anticipy-data/`, and raw verdict JSON/JSONL are local-only and ignored. Builder-readable durable files contain verdicts, counts, proof links, and lessons only, not raw held-out transcript text.
- No M0 real task is proven on a fresh unseen day. Builder-side raw audio runs, builder-side acts, DuckDuckGo searches, read-context proof, write-memory proof, channel-stub proof, stale eval artifacts, support-only internal proof, and unjudged app input work are not judge-verified M0 proof.

Pending gates:
- No current hard human gate blocks M0.
- Non-blocking connector gates remain in `PENDING_FOR_OMAR.md`: Gmail compose scope, Google Docs Drive scope, Slack tool unavailable.
- Judge laps `20260606T020452Z`, `20260606T025532Z`, `20260606T060511Z`, and `20260606T070041Z` found Gmail read-only connector read-back returns `auth_status: pending`; UI screenshots were used for those verdicts, but a future Gmail artifact still needs connector read-back or a recorded scope gate.

Drift numbers:
- Builder-owned tests pass rate: 29/29, 100 percent, stub/mock coverage only.
- Reality judge verified pass rate on fresh unseen days under amended rules: 0/6 attempts verified, 0 percent.
- Latest held-out judge run: `act=31`, `ask=271`, `ignore=1690`; verified external artifacts: 0.
- Generalization: UNPROVEN. Real diverse users do not exist yet.
- Held-out availability: only 4 held-out task-bearing real days are available locally, so the 5-day generalization bar cannot be honestly satisfied yet. Generalization remains UNPROVEN.
- Drift siren: DRIFT is active. Builder test pass remains high while judge pass remains 0 percent. Do not advance a milestone from builder-side evidence.

Realday audio:
- One timestamped student MP3 is builder-visible in `realdays/raw/`.
- Four timestamped student MP3s are in `realdays/holdout/`. Under Amendment 2, a held-out day is burned only when it contributes to a milestone PASS. Failed or blocked laps do not burn held-out days, and the judge may reuse those days because the builder must never read held-out content.
- Builder must never read `realdays/holdout/`.
- Audio realdays are handled by local ffmpeg plus Whisper in `engine/anticipy_engine/capture/transcribe.py`; no always-on cloud STT.
- Lap `20260606T070041Z` ran builder-visible raw audio in the builder session and a held-out MP3 in the separate judge session. The builder did not read holdout. The Steve Jobs / Bill Gates interview is a silence control only and never counts for task completion.

Dead ends not to retry blindly:
- Google Sheets and Google Docs canvas synthetic input.
- Amazon.ca Playwright automation.
- Anti-bot arms races for captcha or Cloudflare challenges.
- Always-on cloud transcription.
- Do not treat a verdict inventory list as proof that every listed holdout day was read or burned.
- Do not treat DuckDuckGo/browser search pages, read-context, write-memory, channel-stub proof, or screenshot-only browser proof as completed real-world actions for tasks that require sending, booking, creating, buying, posting, submitting, calling, or changing an external artifact.
- Do not let the planner type a whole task into the browser search bar as a substitute for decomposition. Explicit information lookup may search; action tasks must route to API hands, the real browser agent hand, or ask/needs-human.
- Do not allow stale eval-literal goals such as old M0 proof Calendar/Gmail tasks, previous-lap ids, or old sent-mail subjects to contaminate held-out plans.
- The `20260606T070041Z` app input slice was not proven by the judge and was reverted. If retrying M2, make the input directly visible and inspectable in the app when pending asks fill the surface, and still require a real judged action before claiming M2.

Next:
- Start the next fresh builder lap by moving a product perimeter slice while still running the whole-house realday. Prefer M2 real app input with direct UI proofability, or another perimeter milestone, rather than another inference-only or proof-guard lap.
- Preserve the latest lesson: the system can generate many apparent done goals from internal `read_context`; that is not real work. Real action goals must decompose into API hands, the real browser agent hand, or ask/needs-human.
- If planner/routing is touched, stop whole-task browser search as a substitute for planning at the planner boundary, not with more hand-level regexes.
- The next lap must still run the builder-visible realday and then be judged on a held-out realday with planted-fake self-check, computer-use self-test, diff scan, real app proof, and different-family cross-check. Failed judge runs do not burn held-out days.
- Do not shrink M0 and do not count builder-visible raw audio as proof.

Law digest:
Never grade your own work. Reality in real apps is proof. No fake, no hardcode, no goal shrink. Build/test actions must be safe, reversible, and self-owned. Raw held-out derivatives never enter git. Oversight runs every lap regardless of cost.
