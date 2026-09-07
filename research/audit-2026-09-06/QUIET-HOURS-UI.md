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
