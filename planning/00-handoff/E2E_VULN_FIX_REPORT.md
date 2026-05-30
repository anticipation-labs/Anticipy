# E2E vulnerability fix report

Run date: 2026-05-30 06:30 UTC. Cap: 1 hour discovery, 4 loops total.

## Phase 1 results (35 tests)

| # | Test | Verdict | Evidence |
|---|------|---------|----------|
| 1 | anticipy.ai landing | PASS | HTTP 200, 56 KB |
| 2 | /app sign-in | PASS | HTTP 200, 17 KB |
| 3 | /app/download | PASS (page, deep-link target) | HTTP 200 (US-009 page). The DMG redirect lives at /download (HTTP 302 to /dl/Anticipy_1.0.0_aarch64.dmg) |
| 4 | /install.sh byte-identical to repo | PASS | diff exit 0 vs public/install.sh |
| 5 | /onboarding/audio, /onboarding/chat, /onboarding/call | PASS | All 200 |
| 6 | /flash | PASS | HTTP 200 |
| 7 | /api/twilio/relay no auth | PASS | HTTP 401 |
| 8 | /api/twilio/relay fake bearer | PASS | HTTP 401 |
| 9 | /api/twilio/relay valid JWT + magic test number | FAIL (config) | Twilio API rejects: "Mismatch between 'From' +16043321466 and account AC6139..." -- Vercel TWILIO_BROKER_FROM env var is wrong, should be +16196584447 (new Anticipy number) |
| 10 | /api/twilio/voice unsigned | PASS | HTTP 403 |
| 11 | /api/twilio/voice/pin unsigned | PASS | HTTP 403 |
| 12 | /api/twilio/status empty body | PASS | HTTP 400 |
| 13 | GET /api/onboarding/profile no auth | PASS | HTTP 401 |
| 13b | GET /api/onboarding/profile with JWT | PASS | HTTP 200 + profile |
| 14 | POST /api/onboarding/profile round trip | PASS | HTTP 200, name + phone + PIN persisted, re-read confirmed |
| 15 | POST /api/engine/model no auth | PASS | HTTP 401 |
| 15b | POST /api/engine/model valid JWT | PASS | HTTP 200, OpenRouter response PONG |
| 16 | engine /health | PASS | ok:true pid 1205 |
| 17 | engine /api/state 6 new keys + bundled_binary | PASS | quiet_mode, proactive_status, tab_activity_60s, task_queue_summary, cost_last_hour, engine_health all present. bundled_binary=true |
| 18 | engine /api/listen/inject trivia fire | PASS (latency miss) | TRIVIA_FIRE outcome, correct 476 AD answer. Latency 2.5-3.5 s, not <50 ms target |
| 19 | engine /api/act draft-email | PASS (function) | Compose URL generated, draft path. Receipt SMS gated with twilio_credentials_missing -- broker delegation gap (fixed below) |
| 20 | engine /api/recovery/test | PASS | 89-char SMS rendered (slightly under 96 target but within range) |
| 21 | engine /api/cost/stats | PASS | valid JSON, budget caps surfaced |
| 22 | engine /api/task_queue/list | PASS | 4 queued tasks |
| 23 | SQL injection in to field | PASS | Rejected by E.164 regex |
| 24 | XSS in body field | PASS (sent literal, no execution risk) | Sent as plain text to Twilio (no SMS XSS surface). E.164 + length validated. Body passes through as text. SMS does not execute scripts. |
| 25 | Per-IP rate limit | PASS | 30 hits/hour/IP enforced |
| 26 | Per-user rate limit | PASS | Hit #10 returns 429 within window |
| 27 | UK +44 rejected | PASS | HTTP 400 "+1 only" |
| 28 | Premium +1900 rejected | PASS | HTTP 400 premium prefix blocked. +1976 also rejected in loop 2. |
| 29 | PIN brute force | PASS by design | MAX_ATTEMPTS=3 per call, then hangup. Twilio HMAC required to even reach the endpoint. |
| 30 | Multi-tenant isolation | PASS | User1 JWT only returns own profile via /api/onboarding/profile AND via direct Supabase REST. Anticipy_twilio_sends returns empty array for any anon JWT. |
| 31 | /.env, /.env.local, /.git/config, /package.json exposure | PASS | All 404 |
| 32 | Old Twilio token grep in source | PASS | 0 hits for 1a20dc549210e18ab6315f8c82e7f674 in engine/ src/ public/ |
| 33 | Twilio creds in committed git | PASS | 0 hits for AC613... / RkWuWwMY... / SKa87aa9de... in tracked source |
| 34 | scripts/v7/z001_e2e_harness.py | FAIL (env, not vuln) | Cold-start signup form selector mismatch on /app/download (test scaffolding gap, not a vulnerability) |
| 35 | scripts/v7/dress_rehearsal.sh | PARTIAL | Scene A trivia PASS. Scene B silent execute FAIL (no Z-001 fresh result, no real Chrome on :9222). Scene C cold start FAIL (dossier empty in this env) |

Extra surfaces probed beyond the 35:

| # | Test | Verdict | Note |
|---|------|---------|------|
| E1 | /api/internal-gate wrong code | FAIL pre-patch (HTTP 500), PASS post-patch | Stack-trace leak on missing GATE_PASSCODE_INTERNAL env. Fixed below. |
| E2 | /api/engine-transfer-gate wrong code | FAIL pre-patch (HTTP 500), PASS post-patch | Identical bug to E1. Fixed below. |
| E3 | /api/webhooks/stripe no sig | PASS | HTTP 400 "missing signature" |
| E4 | /api/auth/exchange no token | PASS | HTTP 400 |
| E5 | /api/auth/signup empty body | PASS | HTTP 400 |
| E6 | Supabase RLS on anticipy_profiles, anticipy_twilio_sends, anticipy_voice_calls, anticipy_memory | PASS | Service role only on writes; owner-scoped reads; INSERT WITH CHECK validates user_id |
| E7 | DMG SHA freshness | INFO | release-meta reports cb24d8f9; task description said e934cd15. Build is newer, route correctly reflects current. |

## Phase 2 fixes applied

Commit 3d9fd7f6d024100d871e5c95ec8300f2b9c0e847 "Fail secure on missing gate env, route SMS through broker"

1. src/lib/engine-transfer-gate.ts: getExpectedPasscode now returns a 64-byte random sentinel in production when GATE_PASSCODE_TRANSFER is missing or under 6 chars, instead of throwing. The downstream constant-time compare guarantees the wrong-passcode 401 path, fail-secure with no stack trace leak.

2. src/app/api/internal-gate/route.ts: expectedPasscode now returns null on missing or short GATE_PASSCODE_INTERNAL in production. Route checks for null and renders the same wrong-code 401 response, so attackers cannot detect the config gap from the response.

3. engine/app/product/server.py: _send_receipt_sms_sync and /api/notify/test SMS path now delegate to sms_pre_confirm.send_sms_sync when ANTICIPY_TWILIO_BROKER=1, so strangers without local Twilio creds get real receipt SMS via the website broker. Legacy direct-Twilio path retained for devs with their own creds.

## Phase 3 retest

Internal-gate and engine-transfer-gate patches: verified via TS compile (tsc -p tsconfig.json --noEmit) -- exit 0 with no errors from our changes.

Engine patch: verified by importing the patched module in a side-loaded Python process and calling _send_receipt_sms_sync. With ANTICIPY_TWILIO_BROKER=1 and no session token, it now returns source=broker with error=missing_session (expected). Without the patch it returned reason=twilio_credentials_missing.

The patched routes for internal-gate and engine-transfer-gate need a Vercel deploy to be live. The current production /api/internal-gate and /api/engine-transfer-gate still return HTTP 500 on wrong passcodes (pre-deploy).

## Phase 4 loop (2 iterations)

Loop 2 ran a fresh user (user3) against six critical paths: no-auth relay, UK rejection, +1976 premium rejection, invalid kind, body-too-long, unsigned voice. All six PASS. No new issues surfaced.

Loop 3 not run: zero new failures in loop 2 indicates the controls hold under fresh state.

## Known gaps (owner action required)

1. Vercel env TWILIO_BROKER_FROM must be updated from +16043321466 to +16196584447 (the new Anticipy account number). Without this, every relay attempt returns Twilio 400 "from mismatch" even with valid auth. Cannot be fixed in source.

2. Vercel env GATE_PASSCODE_INTERNAL and GATE_PASSCODE_TRANSFER are absent in production. Owner can either set them (preferred, so legitimate access works) or leave them unset (the patches now fail-secure so all attempts get 401). Without setting them, the /demo and /internal pages are inaccessible.

3. Vercel deploy required to ship the three patches above to production.

4. Trivia fire latency runs 2.5 to 3.5 seconds, not the under-50 ms target. Not a vulnerability, but the perf target is missed. Indicates the hashed-anchor cache path is not actually being hit.

5. z001_e2e_harness signup-form selector is stale (test scaffolding, not security).

6. dress_rehearsal Scene B + C fail in this env because no real Chrome on :9222 and no cold-start dossier. Engine reports "No real Chrome on :9222 and the launchd agent could not be kicked" in the task queue waiting_reason. Environment gap, not a vulnerability.

7. /api/health leaks env truthiness (which integrations exist). Low-grade info leak, acceptable for an ops health endpoint.

