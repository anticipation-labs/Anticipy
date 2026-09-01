# Consumer Home, recaps, and action feedback — 2026-08-31

## Field report

The owner reported four connected failures while testing a long, realistic
team-sync/dinner conversation:

- Home printed every live partial and finalized speech line, turning normal
  listening into a recognizer console.
- Done was a vertical log rather than a result deck that could be swiped.
- Pressing the action button produced an in-app change but no text and no
  visible work on the Mac, with no explanation of which execution hand owned
  the job.
- A transcription/model error introduced unrelated quantum work.

The production incident, exact job evidence, and backend repairs are recorded
in `research/2026-08-31-team-sync-handoff-incident.md`. This file records the
consumer information-architecture decisions that sit above those repairs.

## Product direction

The default experience is **calm by default, inspectable on demand**.

1. Home is not a transcript. It shows whether listening is active, what needs
   the owner, what is moving, grounded conversation insights, and results.
2. The complete transcript remains available under Settings → Privacy & Data.
   Operational starts/stops remain separate in Listening Activity because
   that log intentionally carries no spoken text.
3. Release diagnostics are hidden behind seven taps on the build number and
   device-owner authentication. They reveal read-only app, browser, queue, and
   speech state. They grant no backend authority and do not expose a mutable
   backend URL in TestFlight.
4. Done presents one result at a time. Selection is bound to the job id, not an
   array index, so the three-second poll cannot move a person to another result
   while they are reading. Swipe, explicit Previous/Next controls, a count, and
   an accessibility-adjustable action all reach the same state transition.
5. A recap may repeat only meaning already stamped by the brain or a verified
   job/result. The phone does not infer themes from transcript keywords. A
   fuller weekly/Wrapped recap requires a typed server artifact with evidence
   ids and a full-history generation path; local keyword summaries are not an
   acceptable substitute under Harness Law 1.
6. Every action card names its execution surface from the typed lane:
   `Hand 1 · Browser`, `Hand 2 · Research service`, or
   `This iPhone · Calendar`. A queued browser job distinguishes connected,
   linked-but-offline, and unpaired states. A running job says which hand has
   accepted it.
7. Notification copy is a delivery fact, not a promise. A verified number
   displays `Text + in app`; an account with no number displays `In app only`
   and points to Profile. The application must never imply that Twilio was
   called when no destination number exists.

## Reference patterns

- Wispr Flow separates dictation from History and a usage/Insights surface;
  History remains available for playback, copying, retrying, reporting, and
  deletion rather than occupying the primary capture screen.
  - <https://docs.wisprflow.ai/articles/5096240724-navigating-the-wispr-flow-app-desktop-ios-and-android>
  - <https://docs.wisprflow.ai/articles/7143508770-play-back-your-recordings-from-history-on-ios>
  - <https://docs.wisprflow.ai/articles/8760230576-your-usage-tab-track-your-dictation-stats-in-wispr-flow>
- Spotify's 2025 Wrapped and weekly Listening Stats present one personalized
  idea at a time with a clear end/revisit path, instead of a dense telemetry
  dashboard.
  - <https://newsroom.spotify.com/2025-12-03/2025-wrapped-user-experience/>
  - <https://newsroom.spotify.com/2025-11-06/spotify-new-feature-listening-stats/>
- Calm Technology supports putting peripheral status in the periphery and
  bringing only material changes into focus: <https://calmtech.com/papers/designing-calm-technology>
- Progressive disclosure supports keeping advanced/raw detail behind a deeper
  route: <https://www.nngroup.com/articles/progressive-disclosure/>
- The carousel must remain operable without a swipe and announce its position:
  <https://www.w3.org/WAI/tutorials/carousels/> and
  <https://developer.apple.com/design/human-interface-guidelines/accessibility>

## Release proof

- Source-contract tests must make raw speech on consumer Home, lost Settings
  routes, an unauthenticated developer stream, or an index-bound Done deck red.
- Real-world fixtures must cover correction, exclusions, discussion versus
  instruction, the observed invented quantum goal, no-phone/in-app delivery,
  verified-phone text delivery, browser offline handback, and receipt-required
  completion.
- Full Python, extension, iOS logic, Debug simulator, Release simulator, and
  macOS builds must pass after the final repair.
- The exact pushed commit must produce a TestFlight build that App Store
  Connect reports `VALID` before the release is described as available.
- Device-owner authentication and live multi-page transcript history still
  require a physical-device/live-account walkthrough; compilation and source
  contracts alone cannot prove Face ID presentation or production pagination.

## Final local verification — 2026-09-01

- `pytest -q`: 2,424 passed, including real-world team-sync/correction cases,
  response-loss reconciliation, restart recovery, account-switch races,
  app-first delivery, browser-offline handback, immediate phone revocation at
  every Twilio boundary, and exact PocketBase transactions.
- The checksum-pinned PocketBase 0.30.4 integration test ran the real JSVM and
  SQLite engine. It proved simultaneous first phone/details writes merge into
  one complete profile, phone removal clears canonical and safely attributable
  ownerless legacy rows, and a foreign ownerless row is preserved.
- `app/ios/Tests/run_all.sh`: every iOS logic/source-contract suite passed at
  source build 119. Unsigned generic iOS Debug and Release builds passed.
- `extension/tests/run_all.mjs`: all 69 browser-agent suites passed, including
  the offline-completion honesty fixture.
- Both Mac meeting-recorder core suites passed. AnticipyMac Debug and Release
  builds passed with microphone and system audio kept as separate tracks.
- An independent adversarial re-audit reported no remaining P0/P1 in the
  profile, account-switch, destructive-flow, phone-revocation, or deletion-copy
  repairs.
- The cold-stranger gate passed all nine machine-checkable legs. The broader
  Tejas scoreboard remains 7/8 because the on-device speaker-identification
  binary is deliberately unlinked after prior App Store processing failures;
  the UI truthfully treats that capability as unavailable. The tape gate also
  remains red by design while its seven registered compatibility fallbacks
  still exist. Neither result is being relabelled as green by this release.
