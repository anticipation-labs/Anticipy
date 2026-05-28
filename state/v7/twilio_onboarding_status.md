# V7 Twilio Onboarding Cold-Start Status

Date: 2026-05-27. Engine: 127.0.0.1:8731 (running v7 head). Branch: main.

## What I found: stub, not real

The V2 B-001 spec calls for a real Twilio outbound voice call on fresh signup that delivers a friend-style interview and populates a dossier. The V7 engine has NO real Twilio voice infrastructure. Specifically:

1. `/api/dossier/outbound` (server.py:6244) is the only endpoint that even names "outbound." It imports `app.dossier.call` and calls `handle_outbound(payload)`. That module does not exist. Confirmed by `find engine/app -path "*dossier/call*"` returning zero hits, and by `curl -X POST /api/dossier/outbound` returning HTTP 500 with body "Internal Server Error" (ImportError on `from app.dossier import call`).
2. `/api/dossier/inbound` (server.py:6264) and `/api/dossier/events` (server.py:6295) import the same missing module. All three routes are dead on arrival.
3. `/api/onboarding/call_stub` (server.py:1533-1576) is an HONEST stub. It appends a row to `~/.anticipy/system_v1/voice_call_stubs.jsonl` with `is_stub: true` and `stub_reason: "voice provider (twilio or equivalent) not configured in this build"`. No Twilio REST client invoked. Verified end-to-end with the probe script.
4. The engine has zero `import twilio`, `from twilio`, `twilio.rest.Client`, or `api.twilio.com` references. The only mentions are docstrings and one notifier reference module (`engine/app/proactive/notifier.py:15`) which is also a comment.
5. `TWILIO_MOCK=true` is set in `.env.local` (line 39), but NO code path reads it. The variable is decorative right now.

## What works for cold-start without Twilio

The scripted `/api/onboarding/start` + `/api/onboarding/answer` (server.py:1439, 1458) flow does work. The browser-driven `/api/onboarding/chat_complete` (server.py:1626) also works: the probe fed it a 4-turn agent/wearer transcript and got back a populated `UserProfile` with 3 people in 9 seconds. The audio path `/api/onboarding/from_audio` (server.py:1783) is wired to parakeet-mlx + the broker but was not exercised in this probe.

## What is needed to make Twilio real (per V2 B-001)

1. Create `engine/app/dossier/__init__.py` and `engine/app/dossier/call.py` exporting `handle_outbound(payload) -> dict`, `handle_inbound(form) -> str` (TwiML), `recent_events(n)`, `recent_dossier_writes(n)`, `mock_mode() -> bool`.
2. `handle_outbound` should: read `TWILIO_ACCOUNT_SID/AUTH_TOKEN/PHONE_NUMBER`, instantiate `twilio.rest.Client`, call `client.calls.create(to=phone, from_=TWILIO_PHONE_NUMBER, url=<TwiML webhook>)`, return `{"ok": True, "call_sid": ...}`. Guard with the TWILIO_MOCK toggle so the test suite can run paid-free.
3. Add `twilio>=9.0` to `engine/uv.lock` / `requirements.txt` (currently absent).
4. Stand up a publicly-reachable TwiML webhook (`/api/dossier/inbound`) so Twilio can fetch the interview script. ngrok or a Vercel-fronted relay for dev.
5. Bridge the call transcript back into `_save_profile` / `_seed_profile_memory` (same boundary the chat path uses, server.py:1675-1676) so the dossier reflects the call.
6. Fix the `/api/dossier/active` lookup: it currently reads by `account_id` query param, but the onboarding paths write under the global `USER_ID` constant. They need to agree on the partition key, otherwise even a successful Twilio call's dossier will not show up in the loader.

## TWILIO_MOCK toggle status

Value in env: `TWILIO_MOCK=true`. Read by code: NO. The flag has no effect today; safe to leave on. When real Twilio lands, the new code must check it (default to true on absence).

## Recommendation

For the V7 cold-start, the text-chat path (`/api/onboarding/chat_complete`) plus the audio-upload path (`/api/onboarding/from_audio`) are sufficient to ship a working "stranger lands, signs up, gets a dossier" loop. Both already produce the canonical UserProfile via the frozen extractor. A real Twilio call is a P1 upgrade for the warmer onboarding voice, not a P0 blocker. Ship cold-start on chat+audio, file Twilio voice as a follow-up tracked against story B-001 in `tasks/v2_prd.json`.

## Evidence

`state/v7/twilio_e2e/v7-twilio-cold-start-20260527T071604Z/` (run.log, onb_start.json, outbound_probe.txt showing 500, call_stub.json with is_stub:true, chat_complete.json with 3 people, dossier_active_after_chat.json).
