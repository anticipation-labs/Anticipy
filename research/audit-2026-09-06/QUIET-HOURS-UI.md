# Quiet-hours visibility — build 160

The waiting-task card now displays a moon icon and “Quiet hours · proactive
texts paused,” followed by the end time and “You can answer here now.”
It reads the account's current timing policy from the authenticated API rather
than deriving the state from the phone's clock or from a saved phone number.

`GET /me/notification-policy` uses the canonical profile time zone and the
existing outreach window, 22:00–08:00. Responses are private, not cached by
HTTP, and expire within 60 seconds or at the next hour boundary, whichever
comes first. An expired or failed read becomes “Text status unavailable.”
Outside quiet hours the card says “Text delivery unconfirmed”; this route is
policy evidence, not a message receipt. The feature does not claim that an
individual text was sent or guarantee an 08:00 send.

Verification before release:

- All iOS logic suites passed; source build 160 is set in both project files.
- Xcode 26.6 simulator build passed, with local signing disabled.
- The actual app was launched against a local-only API and synthetic account.
  The moon, title and explanatory text were visually inspected on the card.
- Full Worker test chain passed under Node 24 and TypeScript passed.
- Clock tests cover midnight, 21:59/22:00, 07:59/08:00, both DST transitions,
  another time zone, expiration, malformed zones, and account isolation.
- The local HTTP release proof passed 24 checks, including the new endpoint
  and cleanup. The local database first needed the already-existing erasure
  migration; that setup issue was corrected without changing production.

Private test logs and screenshot: `work/audit/quiet-*.log` and
`work/audit/quiet-card-simulator.png`. No diagnostic text was sent.
Live deployment and App Store Connect readbacks are recorded after release.

This implements the owner's immediate request to expose nighttime suppression.
The separate interpretation and durable per-question delivery work described
in GENERAL-REPAIR-CONTRACT.md remains open.

## Release verified

- Source commit: `9f0c015722e8fd421520140b5953ce2ad139647c`.
- API deployment 34097698408 passed 32 live checks. The public URL serves
  that commit and version `94471851-061f-4f82-8b59-80c55d4df227`.
- iOS release 34097685571 uploaded 1.1.1 build 160 successfully.
- Independent App Store Connect query 34099052668 reports `VALID`, not
  expired, and `IN_BETA_TESTING` internally. Internal can install the build;
  the owner's previously verified tester membership is present. Installation
  of the new build on the physical phone has not been observed.
- The first query ran before Apple indexed the upload and found no build;
  it is superseded by the successful readback above.
- Local synthetic accounts were removed and the local test server stopped.

Structured evidence: `quiet-release-results.json`.
