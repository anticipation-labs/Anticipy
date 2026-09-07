# SendBlue-only runtime — 7 September 2026

## Observed defect

The brain selected SendBlue for conversation delivery but constructed a Twilio
calling arm when legacy credentials existed. Missing SendBlue configuration could
attach that old arm to direct owner notifications while the conversational
transport reported mock. The API also retained an unset-provider Twilio fallback.
This is a configuration-dependent defect; it is not proof that Omar's reported
missing text was actually sent through Twilio.

## Repair

- SendBlue is the only selectable live provider in both deployed runtimes.
- Missing, incomplete, unknown, or explicitly retired settings disable sends.
- Both brain notification surfaces share the same SendBlue arm and owner guard.
  Disabled sending explicitly clears any pre-existing direct arm.
- Neither supervisor nor standalone worker checks or rewrites Twilio numbers.
  The historical helper is a no-op with no network implementation.
- POST /sms/inbound returns 410 without parsing, persistence, or dispatch.
- POST /sms/sendblue remains the authenticated inbound/status callback route.
- Historical low-level compatibility modules/tests and ignored deployment fields
  remain. No provider account was closed, and no provider-held history was erased.

## Adversarial verification

Tests cover old credentials alone, partial SendBlue credentials, explicit Twilio,
unknown provider, stale direct arms, both notification surfaces, wrong recipients,
provider timeouts/errors, response bodies, callbacks, and no fallback fetches.
The password-reset integration now checks the actual SendBlue JSON wire format.

Local HTTP: old endpoint returns 410; modern endpoint returns 503 because the
local fixture intentionally has no SendBlue secret. That 503 is not a live auth
proof. The deployed endpoint must be checked after release.

Evidence: work/audit/overnight-sendblue-api-full-3.log (entire Worker suite),
overnight-sendblue-typecheck-2.log, overnight-sendblue-final-focused-2.log
(98 passed). Final full Python and deployment evidence are recorded in STATE.md.
No messages were sent to real people by these tests.
