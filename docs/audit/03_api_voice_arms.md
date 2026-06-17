# Audit 03 — Hands & Voice (Calendar/Gmail API arm + Twilio voice/SMS)

> Scope: the "hands & voice" pillar — the API arm (Google Calendar / Gmail via Arcade) and the
> Twilio voice/SMS arm, plus how a card closes the loop back to the owner. Grounded in code
> (`file:line`), receipts ledgers, and fast deterministic stub tests only. NO live SMS/email/call
> was sent during this audit; the model brain was throttled, so `run_suite.sh` and any model path
> were deliberately NOT run. Live behavior below is asserted from code + receipts, not re-run here.

---

## What it is

Anticipy has three "arms" that turn a gated decision card into a real-world action, each behind a
uniform **mock-by-default / live-only-when-explicit** gate so live behavior is config-flipped, not
hardcoded:

- **API arm (Arcade):** Google Calendar + Gmail (and Slack/Docs reads). Turns a `create_event` /
  `send_email` / `send_email_draft` card into a real Google action, then proves success with an
  **independent read-back** — the actor never grades its own homework.
- **Voice/SMS arm (Twilio):** outbound SMS, outbound voice call (the canonical
  "calendar event made; I'll call you at 2:45" line), and a two-way inbound round-trip (owner texts
  `YES <code>` → the exact paused goal resumes; owner speaks on a ConversationRelay call → the same
  decider brain replies, words-only).
- **Loop closure:** a single shared `TextChannel`/`CallChannel` instance is the one audit log that
  carries timed reminders, asks, and browser-result texts back to the owner.

Money is the one hard action stop throughout; acting on a vent is the cardinal sin. The product is
the inference — these arms are the hands and mouth that make the inference real.

---

## How it works (file:line)

### API arm wiring (`control_core.py`)
- `ControlCore` builds `ApiHand(user_id, mode=ANTICIPY_HANDS_MODE [default "mock"], broker=TokenBroker(TokenVault))`
  at `control_core.py:350-351`, and registers it on the bus **last** so the real worker owns any
  intent a stub also claims (`control_core.py:379-383`). `user_id` comes from `ARCADE_USER_ID` /
  `ADMIN_EMAIL`, default `omar@anticipy.ai` (`control_core.py:342`).
- `INTENT_MAP` is imported FROM `api_hand` into `control_core` (`control_core.py:34`) —
  `api_hand.py:40-53` is the authoritative intent→Arcade-tool map (single source of truth). The
  dryrun preview reuses it (`control_core.py:2284-2292`).
- A **separate** onboarding/connection-status map, `_CONNECT_TOOL_BY_IDENTIFIER`
  (`control_core.py:271-278`) + `_connect_tool()` (`control_core.py:281-292`), drives
  `authorize_connection_loop` (`control_core.py:1922-1957`). It only reuses `INTENT_MAP` as a
  last-resort fallback (`control_core.py:292`) and reports connection STATUS — it does not execute.
- No-API intents reroute to the browser hand via the orchestrator's existing `alternates` config:
  `alternates={"post_to_x":"browse_task","create_event":"browse_task","message":"browse_task"}`
  (`control_core.py:386-391`); `api_hand` signals this with `status=failed` +
  `output.needs_other_worker=True` (`api_hand.py:250-255`), so the reroute needs no orchestrator change.

### The intent map (`api_hand.py:40-53`)
- `create_event` → `GoogleCalendar.CreateEvent`
- `send_email` → `Gmail.SendEmail`
- `send_email_draft` → `Gmail.WriteDraftEmail` (inline comment `:43` "creates a draft; NEVER sends")
- `message` → `Slack.SendMessageToChannel`
- reads: `read_calendar`→`GoogleCalendar.ListEvents`, `read_email`→`Gmail.ListEmails`,
  `read_contacts`→`Gmail.ListThreads`, `read_doc`→`GoogleDocs.GetDocumentById`
- `post_to_x` → `None` (comment `:51` "recognized app action with NO Arcade tool → routes to the
  browser hand"). `WRITE_INTENTS={send_email,send_email_draft,create_event,message}` (`:31`).

### Card → real event/draft (`api_hand.py` `handle()` `:249`)
- `tool = INTENT_MAP[intent]`. Defense-in-depth gates:
  - high-risk write missing `job.args["approved"]` → `needs_human` (`:262-264`)
  - `create_event` in LIVE is blocked unless it carries concrete `start_datetime` AND `end_datetime`
    (`_block_ungrounded_calendar_write`, `:599-615` / `:651-657`)
  - idempotency: a retried write that already produced proof returns success without re-sending
    (`:272-274`); a write whose side-effect already fired but is unconfirmed re-verifies via
    read-back ONLY, never re-executes (`:277-278`, `_reverify_fired :334-360`)
  - concurrency: writes go through reserve-or-join (`_run_write_guarded :287-323`) so two presses
    never double-fire.
- LIVE path `_execute` (`:362-430`): `_live_client` picks the per-user vault token if the broker has
  one for this `(user,app)` else the shared `ARCADE_API_KEY` (`:156-188`, `SecretToken.reveal()` at
  `:170` is the ONE plaintext point); `client.tools.authorize(...)`; if status `!= "completed"` →
  `needs_human {"connect": <Gmail|GoogleCalendar>, "connect_url": url}` (`:387-390`); then
  `client.tools.execute(tool_name, input=_tool_input(job), user_id=...)` (`:393`).
- `_tool_input` (`:236-247`): strips `approved`; applies `_ALIASES` (Gmail `to`/`recipients`/… →
  `recipient`, only when canonical absent, `:199-202`); fills the `ListEvents` required time window
  via `setdefault` (`:244-247`, `_listevents_window :217-234`).

### Read-back proof pattern (`api_hand.py`)
- The write's own `execute()` echo is NEVER trusted ("the actor must not grade its own homework",
  `:419-421`). After `execute` returns an id (`_find_id` over `_ID_KEYS`, `:548-563`), the hand
  records `_fired[ikey]` BEFORE the read-back (`:426`), then `_readback_or_fail` (`:446-505`) issues
  a SECOND, independent `client.tools.execute` against `READ_BACK[intent]`:
  - `READ_BACK` (`:65-79`): `create_event`→`GoogleCalendar.ListEvents`,
    `send_email`→`Gmail.ListEmails`, `send_email_draft`→`Gmail.ListDraftEmails`, `message`→`None`.
  - wrapped in `confirm_stable_artifact` with `reads >= 2` (`READ_BACK_READS = max(2,...) :35`;
    `agent/proof.py:40-84` returns confirmed only if EVERY read verifies — the write echo alone can
    never satisfy it), success only if `_read_contains_id` finds the written id (`:487-505`,
    `:521-534`).
  - `None` read tool → FAIL-CLOSED to `needs_human` `{unverified_write:True}` (`:448-457`); Slack
    `message` always hits this. Reads (non-writes) return the list value itself as proof, no
    read-back (`:406-412`).
  - MOCK mode runs the SAME read-back discipline via `_mock_readback` (`:362-377`, `:435-444`) and
    also fails closed.
- Enforced downstream: `orchestrator.py:555-573 _verify` rejects any proof with `self_attested=True`
  lacking `verified_by_read`, so a self-attested-only write is never marked done.

### Voice/SMS arm (`channels/`)
- One `Channel.send(to, message) -> dict` seam (`base.py:7`); `_stub()` is the never-send default.
  Three subclasses: `TextChannel` (SMS), `CallChannel` (voice), `AppChannel` (pure stub —
  `app.py:10-11` never sends). Bundled in `channels/__init__.py:Channels` (call/text/app).
- **Live gate:** `_live()` = `ANTICIPY_CHANNELS_MODE=="live"` AND `configured()`
  (`TWILIO_ACCOUNT_SID` + `AUTH_TOKEN` + `FROM` all present) — `text.py:30-31`, `call.py:37-38`. The
  one switch flipping mock↔live for both outbound surfaces.
- **Outbound SMS:** `TextChannel.send` (`text.py:33-40`) — not live → record
  `{"sent":true,"mock":true,...}` in `self.sent`, no network; live → `_twilio_send` (`text.py:42-55`)
  POSTs urlencoded `To/From/Body` to `.../Accounts/{sid}/Messages.json` with HTTP basic auth, 15s
  timeout. Raw `urllib`, no Twilio SDK.
- **Outbound call:** `CallChannel.send` (`call.py:89-96`); `_twilio_call` (`call.py:98-116`) POSTs
  `To/From/Twiml` to `.../Calls.json` with an explicit base64 `Authorization` header (chosen over
  `HTTPBasicAuthHandler`, which only answers a matching-realm 401 — comment `:105-106`), returns
  `call_sid`+`status`. TwiML chosen by `call_twiml` (`call.py:79-87`): `ANTICIPY_CR_WSS_URL`
  starting `wss://` → two-way `conversation_relay_twiml`; else the one-shot `<Say>` fallback
  (`:41-53`, neural `Polly.Joanna-Neural`, XML-escaped, capped 3000 chars) speaking the fixed line
  and hanging up.
- **Shared instance:** `control_core.py:375-376` builds ONE `TextChannel` + ONE `CallChannel`, passes
  them to `ChannelWorker(text=...,call=...)` (`:377`) AND the SAME `TextChannel` into
  `ProactiveEngine(channel=..., user_contact=...)` (`:393-395`). So proactive asks/reminders and
  `notify_user`/worker share one transport and one `.sent` audit log.
- `ChannelWorker` (`core/workers/channel.py:34-70`) handles intents `send_text`/`call`, fails the
  Job if `rec['sent']` is false, proves success with `proof.message_id` = Twilio `call_sid` (live)
  or a deterministic `mock-`/`live-` id; `ChannelStub` still owns `send_email` (no real email channel
  — `core/workers/channel.py:24-31`). `notify_user` (`control_core.py:1834-1848`) is the generic
  "text the owner" door; recipient = arg | `ALERT_PHONE` | `TWILIO_TO` | `_user_contact()`.

### Inbound round-trip (`channels/inbound.py`)
- `InboundPoller` polls Twilio's Messages REST list (`_twilio_fetch :252-267`); `main.py:113-115`
  schedules `_inbound_scheduler` every `ANTICIPY_INBOUND_POLL_SECONDS` (default 15, 0 disables) ONLY
  when `live_ready()` (`:80-85`: live mode + full triad), so suite/mock never builds a transport.
- `poll_once` (`:88-125`): requires `OWNER_PHONE` (else refuses everything); marks each sid seen
  BEFORE acting (never replay an approval); drops non-owner senders and pre-floor stale messages.
- `_REPLY = ^(yes|no)(sep code{4,32})?$` (`:50`) → `core.resolve`, the ONE durable door (ledger F18,
  `:127-147`): a ≥4-char code matched as an ask-id prefix; a bare YES/NO resolves only when exactly
  ONE ask is pending. YES with steps re-drives the paused goal to done; YES without steps starts the
  ask-paused goal (`proactive.resolve_ask`, `proactive.py:500-533`); NO drops it (Room 5
  suppression). Ambiguous (0/many matches) resolves NOTHING but sends ONE bounded, budget-capped
  clarification SMS listing exact pending codes (F20, `_clarify :168-214`). Non-reply bodies →
  `core.owner_ingest('sms', body, execute_actions=True)` then a grounded reply (`agent_reply :150-165`).
- Two-way VOICE: `/cr` WebSocket (`main.py:1393+`) is a Twilio ConversationRelay socket running the
  SAME decider brain (`channels/conversation_relay.py`) — speech in as `{type:prompt}`, streamed
  reply out as `{type:text}`, words-only (never sends/books/pays; money stays ASK, vent SILENT),
  token-auth-gated, with per-call turn/duration caps.

### Loop closure (the 2:45 use case + browser result)
- **Timed reminder leg:** a self-reminder that grounded a `remind_ts` at capture is kept as a live
  Ready card by `_timed_reminder_card` (`control_core.py:802-826`, requires `kind=='open_loop'` AND
  `fields['remind_ts']`). The caller keeps the loop ACTIVE (`continue`, `control_core.py:1171-1188`),
  skipping the ignored-sync that historically killed the reminder. The background
  `_trigger_scheduler` (`main.py:83-91`) calls `proactive.trigger_tick()` every
  `ANTICIPY_TICK_SECONDS` (default 30; 0 disables → POST `/trigger/tick`, `main.py:108-110`,
  `1142-1144`). `trigger_tick` (`proactive.py:560-616`) lists open loops, runs
  `TriggerWatcher.tick` (`proactive/trigger.py:50-54`); `_due` (`:30-48`) fires once `remind_ts<=now`,
  guarded by an in-session `_fired` set AND the durable `fired_at` stamp (ledger D16 — restart never
  re-fires). **Mark-before-act:** `mark_loop fired_at` is stamped BEFORE any send; a failed stamp
  skips the fire (`proactive.py:591-602`). A loop with `remind_ts` routes to `_fire_reminder`
  (`:629-664`): harm-line re-gate (`harm.assess`) → budget/guard suppress → `voice.humanize_reminder`
  (`voice.py:62-83`; live model only under OpenRouter, deterministic warm nudge otherwise) →
  `self.channel.send(self.user_contact, text)` → `record_interruption` → mark `waiting`, glassbox
  `notify`. Decision = `notify` (one-way text, not an ask).
- **Browser-result leg:** a web task becomes `_browser_action_ask` (`control_core.py:738-771`):
  registers a pending ask (`category='browser_action'`) and immediately texts the confirm-first ask.
  On YES, `core.resolve` (`control_core.py:2068-2091`) detects the category and fires
  `_run_browser_and_confirm` as a detached `asyncio.create_task` (`:2082-2085`) so it never blocks
  the reply; that task (`:773-800`) texts "On it…", runs `browse_act` in a thread, then texts
  "Done — …" (or a graceful-failure offer) — same channel as the reminder leg.

### Honest live-readiness checklist
- `GET /readiness` via `_connect_readiness()` (`main.py:484-570`): four capabilities
  (`google_arcade`, `twilio`, `browser_bridge`, `apple_signing`), each live/needs_connect by config
  presence; `overall=all_live` only when all four are live. `control_core.channel_status`
  (`:463-514`, surfaced at `/channels`) exposes mode + status without leaking the phone number.

---

## Talk & call (voice/SMS loop)

The voice/SMS loop is the mouth that closes the inference. Three concrete flows:

1. **Reminder → text (the 2:45 use case).** A due `remind_ts` loop fires as a one-way **NOTIFY**:
   harm-line re-gated, budget/guard checked, humanized, `self.channel.send(user_contact, text)`,
   loop marked `waiting`. No goal, no ask. Durable across restarts via the `fired_at` mark-before-act
   stamp (`proactive.py:591-602`, `trigger.py:33-34`).

2. **Voice call (the canonical line).** `CallChannel` one-shot TwiML `<Say>` speaks
   "calendar event made; I'll call you at 2:45" with `Polly.Joanna-Neural` and hangs up — the
   no-LLM, no-socket fallback (`call.py:40-53`, `:79-87`). Stub test produced the exact
   `<Response><Say voice="Polly.Joanna-Neural">…</Say></Response>`. If `ANTICIPY_CR_WSS_URL` is set,
   the call instead opens a two-way ConversationRelay socket reusing the decider brain (`/cr`,
   `main.py:1393-1452`).

3. **Inbound round-trip (owner → engine → owner).** An owner SMS `YES <code>` resumes the exact
   paused goal through the single durable door `core.resolve`; a bare YES/NO resolves only when one
   ask is pending; ambiguity sends ONE budget-capped clarification listing the pending codes; non-reply
   speech is ingested and answered. The poller is owner-gated, replay-safe (mark-seen-before-act),
   and only constructs a transport under the full live triad.

**Stub-test evidence (deterministic, no network, all PASS this session):**
- `test_channels.py` (mock mode) → "text/call real (mock mode, audited)": `send()` returns
  `mock=True/sent=True`, no network.
- `test_inbound.py` → YES/NO+code → `ControlCore.resolve` (F18), speech → `owner_ingest`,
  ambiguity/sender/stale/replay refused, F20 clarify.
- `test_conversation_relay.py` → 5 PASS incl. a simulated ConversationRelay exchange (NO real Twilio).

---

## PROVEN-LIVE vs MOCK vs OWNER-GATED (be precise)

| Capability | Status | Basis |
|---|---|---|
| **Calendar `create_event` + read-back-by-id** | **PROVEN-LIVE (once, stale on disk)** | RECEIPTS.md:596-604 (Slice 11, 2026-06-15): real `GoogleCalendar.CreateEvent`, `proof.verified_by_read=GoogleCalendar.ListEvents`, event independently re-observed; commits fa6ba3b, eab3375. Corroborated by a stray file of 11 real opaque event IDs. **Caveat:** the durable glassbox proof `reality_check.py:157-166` scans for has rotated out (glassbox is non-durable, `glassbox.py:17-52`); not re-confirmable on disk today without a fresh live run, and not re-run this session. |
| **Calendar reads (`read_calendar`/ListEvents)** | **PROVEN-LIVE** | Real ListEvents returning real events (receipts). |
| **`DeleteEvent` (test-artifact cleanup)** | **NOT WIRED — manual/out-of-band** | No `DeleteEvent`/`delete_event` anywhere in `engine/anticipy_engine/` (greps empty; only vent-guard regexes and SQLite `DELETE FROM`). Live cleanup was done by hand via Arcade `GoogleCalendar.DeleteEvent` (FOREMAN_STATE.md:48, FAILURE_MODES.md:375-377). The "create → read-back → delete" round trip is **create + read-back in code; delete out-of-band**. |
| **`send_email` (Gmail.SendEmail)** | **OWNER-GATED (never run live)** | Catalog-confirmed name; no live send receipt (intentional — would be a real send). Connect-gated on Gmail scope grant. |
| **`send_email_draft` (Gmail.WriteDraftEmail) + draft read-back (ListDraftEmails)** | **OWNER-GATED / MOCK** | Wired + catalog-confirmed (api_hand.py:65-79 comment), but never run live — connect-gated until Omar grants the gmail.compose scope (api_hand.py:38-39; RECEIPTS.md:607-608). Removed from the press-go auto-execute whitelist (`press_go.py:61 WHITELIST={create_event, write_memory}`); a draft is a **prepared-handback** (control_core.py:2287-2288, RECEIPTS.md:144). |
| **`message` (Slack.SendMessageToChannel)** | **STRUCTURALLY UNCONFIRMABLE** | `READ_BACK["message"]=None` → always fail-closes to `needs_human` (api_hand.py:78, :448-457). No live receipt. |
| **`post_to_x`** | **CONFIG/CODE-ONLY (reroute to browser)** | `INTENT_MAP[post_to_x]=None` → `needs_other_worker` → orchestrator `alternates` → `browse_task`. No live X-post receipt. |
| **Outbound SMS (Twilio)** | **PROVEN-LIVE once → reverted to MOCK** | RECEIPTS.md:584-587: delivered SID `SM7e3b2cd824d491dd09cbba598a6f3ab8` status=delivered, reminder SIDs `SM0ea17ce…`/`SM97b2b35…`. **Caveat:** that proof lives ONLY in RECEIPTS.md + HANDOFF_2026-06-15.md — no Twilio SID, no REST read-back, no `"mock":false` entry in the reachable glassbox/data stores in this checkout (the 26 glassbox `ask_sent` entries show the mock default `+10000000000`). The project's own history corrected an EARLIER live-SID claim as a fabrication (RECEIPTS.md:357-359), so this warrants a fresh failable check before relying on it. Currently OFF (`.env.local ANTICIPY_CHANNELS_MODE=mock`). |
| **Inbound SMS poll (Twilio)** | **PROVEN-LIVE (on-disk corroborated)** | `.anticipy-data/inbound_seen.json` holds 12 real Twilio inbound SIDs + epoch floor 1781363390.04 (2026-06-13T15:09:50Z) — written only by `InboundPoller._mark_seen` after a real fetch. This is the ONE on-disk live corroboration; the outbound half is not equally evidenced locally. |
| **Outbound VOICE (the 2:45 call)** | **OWNER-GATED — NEVER placed live** | RECEIPTS.md:357-360 corrected a prior "Voice LIVE" claim as a fabrication; no real `CA`-prefixed call SID exists anywhere; `gate_P3.sh` never passed; PENDING_FOR_OMAR.md:41-43 confirms no outbound call ever placed. `_twilio_call` is `# pragma: no cover`. |
| **Full inbound human round-trip (real owner text → auto-reply)** | **LIVE-PROOF-OPEN** | Each leg unit-/live-proven; the whole composition (Omar actually texting the number) was not exercised (RECEIPTS.md:590-591). |
| **AppChannel / real email channel** | **STUB / ABSENT** | `app.py:10-11` never sends; `ChannelStub` still owns `send_email` — no real email transport. |
| **Per-user account mesh (TokenVault/TokenBroker)** | **WIRED, no app connected** | `.anticipy-data/vault` is EMPTY; live API falls back to the shared `ARCADE_API_KEY` (api_hand.py:164-188, RECEIPTS.md:361-369). |
| **Mock paths (no real send without the flag)** | **VERIFIED this session (no real send)** | Clean-env stub: `Text/CallChannel.send()` → `mock=True/sent=True`, zero network. The `_live()` logic gate flips True with mode=live + creds, but `send()` was NOT called in that state. |

**Current runtime gates (`.env.local`):** `ANTICIPY_HANDS_MODE=live` (:100),
`ANTICIPY_CHANNELS_MODE=mock` (:114), `ANTICIPY_INBOUND_POLL_SECONDS=0` (:119),
`STRIPE_SECRET_KEY` empty (:81). An engine process is running (PID 42847 on :8787), per
CERTIFICATION_NOW.md started SAFE (channels=mock, poll=0) — **not** verified against the live process
env this session (no `.env*` file found by the searches run here; the running process's actual mode
was not inspected to avoid live behavior). `factory/.halt` is present (live-channel halt;
`owner_phone.confirmed` dated 2026-06-13). Stripe is unarmed by design — money is the only hard stop.

---

## Working together

- **One audit log spans every loop-closing text.** `control_core.text_channel` IS
  `proactive.channel` (`control_core.py:375` → `:393-395`; `proactive.py:101`). Reminders, asks, and
  browser-result texts all flow through one `TextChannel.sent` trail and share the one mock/live
  decision — any consumer of `.sent` sees all legs interleaved.
- **Two single sources of truth keep the API arm consistent.** `INTENT_MAP` (execution) and
  `READ_BACK` (proof) are parallel maps; adding a new app action means updating both, plus the
  separate onboarding map `_CONNECT_TOOL_BY_IDENTIFIER` (`control_core.py:271-292`), which must stay
  in sync but is distinct from execution.
- **No-API intents flow API → browser with no orchestrator change.** `api_hand` returns
  `needs_other_worker`; `control_core` `alternates` reroute `create_event`/`message`/`post_to_x` to
  `browse_task` (`api_hand.py:250-255`, `control_core.py:388`, `orchestrator.py:522-526`,
  `browser_hand.py:139`).
- **The brain reaches both mouths.** `notify_user` (the owner-text door) routes through
  `channel_worker send_text`; inbound `core.resolve` re-drives a paused goal that can then act via
  the API arm, and the browser-result leg texts back through the same channel — so a single decision
  can be executed (API/browser) and reported (SMS/voice) over the shared seam.
- **The `/cr` voice loop reuses the SAME decider** as text (`conversation_relay.py`, no fork),
  keeping voice and text on one inference, words-only on the call.

---

## Honest verdict

The **architecture of the hands & voice pillar is real and disciplined**, not theatrical: every send
is mock-by-default behind one explicit `_live()` switch; every API write is gated by an independent
second read-back that the actor cannot fake (enforced again at `_verify`); the timed-reminder leg is
fire-once durable via mark-before-act; the inbound round-trip resolves through one durable door with
replay/owner/stale guards; money is hard-stopped and Slack/unknown reads fail closed. All of this is
**code-read + stub-test verified** this session (`test_channels`, `test_inbound`,
`test_conversation_relay`, `test_api_hand`, `test_api_readback`, `test_api_calendar_window` all green,
deterministic, no network, no model).

But **live coverage is thin and uneven, and the receipts carry an honesty scar.** What is genuinely
proven-live and re-confirmable today is narrow: **calendar create+read-back+reads** (proven once,
though the durable glassbox proof has since rotated off disk) and **the inbound SMS poll** (12 real
SIDs on disk). Everything else is either **owner-gated** (Gmail send/draft on a scope grant; the 2:45
voice call never placed; Stripe unarmed) or **claimed-live-but-not-locally-re-confirmable** — most
sharply the **outbound SMS**: its delivered SIDs live ONLY in two markdown files, with no Twilio
read-back and no non-mock entry in any reachable store, and the project itself previously corrected a
fabricated voice/SMS live-SID claim. The "create → read-back → **delete**" round trip overstates the
code: **delete is not a wired intent** and was done by hand, which FAILURE_MODES flags as a recurring
stray-event source.

**Net:** strong, safety-first plumbing with one credible live calendar proof and one on-disk inbound
proof; the rest is gated or asserted. Before claiming this pillar "done," re-run a fresh **failable**
live check for outbound SMS and the 2:45 call, write the calendar read-back proof to non-rotating
storage, and either wire a `DeleteEvent` intent or restate the round trip as "create + read-back;
cleanup manual." Live SMS/email/call were deliberately NOT exercised here, and the model-dependent
paths (`humanize_reminder`, `agent_reply`, `/cr` replies) were verified only on their deterministic
fallback paths, not against the live brain.
