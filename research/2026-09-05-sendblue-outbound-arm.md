# Sendblue as the brain's outbound message channel (2026-09-05)

What was built, what a deploy needs, what proves it, and what is NOT done.

## What was missing

The brain had one way to reach a phone: `brain/voice_arm.py` (Twilio). The
transport above it (`brain/conversation.py TwilioTransport`) only ever called
`arm.text(to, body, media)` and propagated exceptions — provider-neutral by
construction — but the worker built it over the Twilio arm and nothing else,
and the startup checks that read and rewrite a Twilio number's inbound
binding ran unconditionally.

## What replaced it

- `brain/sendblue_arm.py` — `SendblueArm.text(to, body, media=None)` with
  VoiceArm's contract to the field: `{"sid": message_handle, "status":
  <lowercased>, "delivered": status in voice_arm.DELIVERED_STATES}`, and
  `voice_arm.SendFailed` on a non-2xx, no JSON, no `message_handle`, a status
  in `("error", "declined") + voice_arm.DEAD_STATES`, or any `error_code`.
  POST `${SENDBLUE_API_BASE}/api/send-message`, JSON
  `{from_number, number, content[, media_url][, status_callback]}`, headers
  `sb-api-key-id` / `sb-api-secret-key`, timeout 15 s.
- The rig guard is `voice_arm._rig_reason`, the same function in the same
  order (muzzle → this arm's own loopback exemption → pytest → local
  backend). `_rig_reason` grew one parameter — the arm's OWN
  physical-impossibility check — so `TWILIO_API_BASE` on loopback can never
  exempt a Sendblue send and vice versa (`tests/test_sendblue_arm.py::
  test_the_loopback_exemption_is_per_arm`).
- `voice_arm.muzzled()` now honours `ANTICIPY_SMS_MOCK` beside `TWILIO_MOCK`
  (`voice_arm.MUZZLE_ENV`, `muzzle_flag()` names which one refused).
- `brain/sendblue_arm.py choose_provider()` is the ONE provider rule:
  `ANTICIPY_SMS_PROVIDER` names a vendor; unset, Sendblue when its three
  variables are all set, else Twilio when its credentials are, else mock.
  POLARITY: a vendor that is named but not configured is **mock**, never the
  other vendor. Read by the worker's transport build, the banner, and
  `overnight/does_she_reach_them.py`.
- `brain/worker.py`: `MessageTransport` (alias of `TwilioTransport`) over the
  chosen arm; banner `sms=sendblue:…<key tail>` / `sms=twilio` / `sms=mock`
  (`sms=live` is gone — `proof/local_rig.sh` now refuses unless the banner
  says `sms=mock`, which is strictly stronger than the old grep for one
  vendor's word). `ensure_inbound_webhook()` returns before touching Twilio
  unless the provider is Twilio; the worker and the supervisor both call it,
  so one gate covers the fleet. One startup line (`inbound_ear_note`) says
  Sendblue's webhook lives in its dashboard (Developer → Webhooks) and must
  point at `${ANTICIPY_PB}/sms/sendblue`.
- The Twilio `VoiceArm` is still built whenever Twilio is configured: calls
  stay on Twilio (Sendblue does not dial; `SendblueArm.call` raises
  `CallRefused` saying so). `anticipy.voice` is the SAME arm the conversation
  texts through, so notify_owner's direct-text fallback cannot reach a
  retired vendor.
- Media: the words are the floor. `one_url` + the `+1` rule, exactly as
  VoiceArm. One retry without the picture, and ONLY when it is certain
  nothing went out: a non-2xx, or a 2xx whose status is a documented
  not-sent one (ERROR "failed to send", DECLINED "rejected"). A 2xx with a
  live status and an `error_code` is a message Sendblue HAS: it raises and
  is never re-sent.

## The exact environment a deploy needs

Required for the Sendblue provider (all three, or the worker is not on
Sendblue):

    SENDBLUE_API_KEY_ID=...          # public-ish; the banner shows its last 4
    SENDBLUE_API_SECRET_KEY=...      # never logged; scrubbed from every line
    SENDBLUE_FROM_NUMBER=+1XXXXXXXXXX  # E.164, one of the account's Sendblue numbers

Optional:

    ANTICIPY_SMS_PROVIDER=sendblue|twilio   # names the vendor outright
    SENDBLUE_STATUS_CALLBACK=https://.../   # rides as status_callback when set
    SENDBLUE_API_BASE=https://api.sendblue.com   # loopback = proof mode only
    ANTICIPY_SMS_MOCK=1                     # muzzle, both arms (TWILIO_MOCK still works)

Leave `TWILIO_*` in place if calls should still be possible; with Sendblue
chosen the worker will not touch the Twilio number's inbound binding.

`worker up` must print `sms=sendblue:…<last4 of SENDBLUE_API_KEY_ID>` — that
line is the deploy proof, and `sms=mock` after a deploy means the three
variables did not all arrive.

## What proves it

- `proof/sendblue_outbound_proof.py` — a loopback fake Sendblue; the real
  arm through the real `MessageTransport` and `Conversation.say()`; 32 PROVEN
  lines, 14 requests recorded, 0 sent. Run as a subprocess by
  `tests/test_sendblue_arm.py`.
- `tests/test_sendblue_arm.py` (36 tests), `tests/test_sms_provider_selection.py`
  (15), six Sendblue legs added to `tests/test_reach_gate.py`.
- `overnight/does_she_reach_them.py` now runs one leg per CONFIGURED vendor
  (Twilio's leg is byte-for-byte the fetch it was; Sendblue's reads
  `GET /api/v2/messages?is_outbound=true` and reshapes rows into the one
  receipt `unreachable()` judges) and says which vendor the worker texts
  through. UNPROVEN (exit 2) when the worker's vendor cannot be read.

The LIVE leg (Law 3): after a deploy with the three variables set, the
worker's log carries `sms=sendblue:…XXXX`, and `python3
overnight/does_she_reach_them.py` with `SENDBLUE_*` in the gate's
environment reads real receipts for the numbers she wrote to. Until a real
handset has shown a DELIVERED row, this arm is repo-green and not live-green.

## Mutation testing

See the commit message; the three mutations (rig guard removed, ERROR read
as delivered, provider default flipped) each turn a named test red and the
restore is byte-identical.

## NOT done — plainly

- **Inbound is not this change.** `POST /sms/sendblue` on the Worker is
  step 2 of the switch in `research/2026-09-05-cloudflare-era-plan.md` and
  is being built separately (`migration/workers/src/routes/sendblue.ts`).
  Until it is deployed and the dashboard webhook points at it, the owner can
  be TEXTED on Sendblue and cannot REPLY on it.
- **The Worker's own two texts** (HQ reminder sweep, password-reset code)
  went to Sendblue in `79cabc10` (`migration/workers/src/messaging.ts`),
  with the same env names. One polarity differs and is deliberate on both
  sides: an UNRECOGNISED `ANTICIPY_SMS_PROVIDER` value makes the brain
  `mock` (a typo is not a vendor), while the Worker logs it and chooses by
  what is configured. A named-but-unconfigured vendor is "nothing sent" on
  both. The PocketBase reset-code hook (`backend/pb_hooks/password_reset.pb.js`)
  still speaks Twilio only; PocketBase is the retiring backend.
- **Nothing here has been run against api.sendblue.com.** The request shape
  is what docs.sendblue.com documents (read 2026-09-05: send-message body
  fields; `/api/v2/messages` list fields and statuses REGISTERED, PENDING,
  QUEUED, ACCEPTED, SENT, DELIVERED, ERROR, DECLINED, RECEIVED). Whether a
  media_url refusal arrives as a 4xx or as a 200/ERROR is unmeasured; both
  shapes retry without the picture.
- Media to non-+1 numbers is withheld, mirroring Twilio, though iMessage
  would carry it: unmeasured, so foreign strangers get today's behaviour.
