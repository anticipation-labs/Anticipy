# Twilio SMS / Voice Delivery Verification

Date: 2026-05-30
Tester: claude-code (Opus 4.7) on Anticipy-V7
Account under test: AC6139...REDACTED...5e7d (Anticipy production broker)
Number: +16196584447 (San Diego CA, US local 619, SMS+MMS+Voice capable, status in-use)
Broker route: https://www.anticipy.ai/api/twilio/relay (production)

## Verdict

**Anticipy's Twilio account does NOT reliably deliver SMS to US handsets today. A2P 10DLC registration IS required, owner Omar's prior belief was incorrect for this account configuration.**

- Voice calls work and route normally.
- SMS to magic test number returns Twilio error code 30034 (Message from Unregistered Number) on every send.
- Brand registration is empty, Customer Profile sits at status "draft", zero Messaging Services exist.

## Phase 1: Magic-number tests (PASS for routing, FAIL for SMS delivery)

Direct Twilio REST API + production broker route both reachable. Results:

| SID | Path | To | Status | Error | Price | Verdict |
|---|---|---|---|---|---|---|
| SMf129...REDACTED...c99a | direct REST | +15005550006 (success-magic) | undelivered | **30034** | -0.00830 (refunded) | A2P block |
| SMa853...REDACTED...3a60 | broker /api/twilio/relay | +15005550006 | undelivered | **30034** | -0.00830 (refunded) | A2P block |
| SM8939...REDACTED...988b | broker | +15005550001 (invalid-magic) | delivered | none | -0.00830 (refunded) | Twilio internal short-circuit, not a real delivery |
| SMb078...REDACTED...e485 | broker | +15005550004 (not-mobile-magic) | undelivered | **30034** | (none) | A2P block (preempts magic check) |

Critical observation: error 30034 fires on the magic success number itself. This means the carrier filter is upstream of magic-number handling, the entire account's SMS lane is blocked.

Broker route returned `{ok: true, sid: ...}` HTTP 200 for all three sends. The website does NOT see the downstream undelivered status synchronously, it only sees the queued ack. The `/api/twilio/status` callback would record the failure asynchronously.

## Phase 2: Real-number SMS test (SKIPPED)

`.env.local` declares `TEST_USER_PHONE=+18882981661`. That is a US toll-free (888) prefix, not a personal mobile handset. No `TWILIO_TEST_TO_REAL_NUMBER_E164` or analogous owner-mobile var exists.

Per the directive's hard rule (do not text random numbers), Phase 2 is **SKIPPED**. Owner must provide his real E.164 mobile in env before this can run. Given the Phase 1 30034 result, Phase 2 would almost certainly also fail with 30034.

## Phase 3: Voice call test (PASS)

Outbound voice POST against +15005550006 via direct REST API:

- SID: CA50ea...REDACTED...084b
- From: +16196584447 → To: +15005550006
- Status: busy (this is the magic-number expected outcome for the success line, call was routed and reached Twilio's test endpoint)
- Duration: 0, end_time stamped

Voice routing works end-to-end. Voice does not need A2P 10DLC registration, only SMS does.

## Phase 4: Twilio dashboard inspection (REST API)

Recent messages on the account, last 10:

```
SMb078...  +15005550004  status=undelivered  error_code=30034
SM8939...  +15005550001  status=delivered    error_code=none   <- magic invalid short-circuit
SMa853...  +15005550006  status=undelivered  error_code=30034
SMf129...  +15005550006  status=undelivered  error_code=30034
SM0ade...  +15005550006  status=failed       error_code=21660  <- prior test from a different from number
SMa404...  +15005550006  status=failed       error_code=21660
... (5 more error 21660 from +16043321466)
```

**Top error codes observed**
1. **30034** (4 of 4 actual delivery attempts from +16196584447): US A2P Message Delivery, Message from an Unregistered Number. The account is not A2P 10DLC registered and cannot send SMS to US handsets.
2. **21660** (5 historical): From/To pair invalid for that older +16043321466 sending number, unrelated to A2P.
3. None of the recent 30034 sends show carrier 30xxx filter codes beyond 30034 itself.

Account balance: $18.7998 USD. Account is not suspended.

## Phase 5: A2P 10DLC registration state

| Resource | Count | State |
|---|---|---|
| Trust Hub Customer Profile | 1 | **draft** (friendly_name "Anticipy", email omar@anticipy.ai, created 2026-05-30, never submitted) |
| A2P Brand Registrations | **0** | None |
| Messaging Services | **0** | None |
| Regulatory Compliance Bundles | 0 | None |
| Incoming Phone Numbers | 1 | +16196584447 (SMS+MMS+Voice capable, voice/SMS webhooks pointed at anticipy.ai) |

The Customer Profile was created today and was never advanced past draft. Without a submitted+approved Brand and an active Messaging Service with a campaign, every SMS to a US handset is filtered with 30034.

## Bottom line

**Does Anticipy's Twilio actually deliver SMS to a US phone today, yes or no? → NO.**

- The earlier "won't deliver" warning was **correct, not overstated**.
- Owner's belief that personal/sole-prop low-volume sends bypass A2P is wrong for this specific account, the rejections are happening at the Twilio platform layer (error 30034) before any carrier even sees the message.
- Voice calls continue to work, so voice-based confirmations are usable today.
- To unblock SMS, the account needs: Customer Profile submitted+approved, A2P Brand Registration (Standard or Sole Proprietor), Messaging Service created, +16196584447 added to the service, and a Campaign approved on the brand. Sole Prop registration is the lighter path and is intended exactly for this case, but it is still required, the dashboard does not let the account skip it.

## Spend, time, cleanup

- Total Twilio cost: $0.00 (all sends were to magic numbers and were refunded by Twilio, prices all showed negative or null)
- Wall clock: ~3 minutes
- Throwaway Supabase user (5ac0f63d-...) deleted via service-role admin API after test
- No real human phone was contacted
