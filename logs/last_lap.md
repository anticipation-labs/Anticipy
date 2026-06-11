# Last Lap

Lap: 20260611T051236Z
Date: 2026-06-11
Phase: P2-brain CLOSED -> TARGET v6 STAGE B item 3 (P3-voice plumbing)
Slice: GROUNDWORK enabling the P3 closure lap — channels/call.py is a real Twilio
Calls channel (mock/live/audit like text.py), a real ChannelWorker owns
send_text/call on the bus, and channels/inbound.py closes the reply loop:
YES/NO+code resolves pending asks through ControlCore.resolve (F18), other inbound
is owner speech into /owner/ingest. All buildable+testable without OWNER_PHONE; no
official metric can move (dev bank saturated, default path must stay inert) —
pre-registered exactly so.

What changed:
- engine/anticipy_engine/channels/call.py: dead stub -> real CallChannel. Mock by
  default (sent=mock, .sent audit); live ONLY with ANTICIPY_CHANNELS_MODE=live +
  TWILIO_ACCOUNT_SID/AUTH_TOKEN/FROM. Researched REST shape: POST Calls.json with
  To/From/Twiml=<Response><Say> (XML-escaped, bounded under the 4000-char Twiml
  cap), explicit Authorization header (NOT text.py's realm-dependent
  HTTPBasicAuthHandler — ledger F19), response sid/status kept as the gate_P3
  read-back handle.
- engine/anticipy_engine/core/workers/channel.py: +ChannelWorker (real worker,
  frozen contract): send_text -> TextChannel, call -> CallChannel; success ONLY
  when the channel reports sent (failed live send -> Result failed, no proof);
  proof = Twilio sid live / deterministic mock id; recipient falls back to the
  control core's contact seam. ChannelStub keeps send_email and stays the
  scriptable test fake.
- engine/anticipy_engine/core/control_core.py: ChannelWorker registered LAST
  (owns send_text/call); ONE shared TextChannel instance feeds both the proactive
  ask path and the worker (single audit trail); notify_user routes through the
  real worker; _user_contact() returns OWNER_PHONE/ALERT_PHONE/TWILIO_TO ONLY in
  live channel mode (placeholder everywhere else, so persona-run artifacts never
  carry the real number — B8 engine-side, scoped); resolve() gained the F18
  durable fallback: when the in-memory goal->record map misses, scan
  owner_cards/*.json for execution.goal_id == resolved goal and write back.
- engine/anticipy_engine/channels/inbound.py (NEW): InboundPoller. Researched
  list shape: GET Messages.json?To=<our number>&PageSize=50, basic auth header;
  newness via persisted seen-sid set + cold-start time floor (NO DateSent
  inequality params — encoding risk avoided). Owner-only ("from" must equal
  OWNER_PHONE; unset OWNER_PHONE -> refuse everything), direction must be
  "inbound", sids marked seen BEFORE acting (a crash loses one message toward
  silence, never replays an approval). "YES/NO [code]" (code = >=4-char ask-id
  prefix; bare YES/NO only when exactly ONE ask pending; anything ambiguous
  resolves NOTHING — ledger F20: the refusal is silent, live-UX gap) ->
  ControlCore.resolve. Non-reply -> core.owner_ingest("sms", ..., execute_actions
  =True): the same Action Engine door, harm-line still rules.
- engine/anticipy_engine/core/proactive.py: the ask SMS now carries the short
  reply code ("Reply YES <code> ... NO <code>") — decision-inert (body is never
  collected/scored; proven below).
- engine/anticipy_engine/main.py: lifespan starts the inbound poll task ONLY when
  InboundPoller.live_ready() (live mode + Twilio triad) and
  ANTICIPY_INBOUND_POLL_SECONDS>0 (default 15; 0 disables). Suite/stub/mock runs
  never construct a transport.
- Tests: test_channels.py un-staled (real mock channels + TwiML escaping/bound
  pins); test_channel_worker.py NEW (mock proof contract, honest failure, stub
  keeps send_email); test_inbound.py NEW (code round-trip incl. the ask-SMS code
  pin, ambiguity/sender/stale/outbound/replay refusals, F18 map-cleared durable
  write-back, sms-source owner cards, OWNER_PHONE-unset refusal). run_suite.sh:
  +channels +channel_worker +inbound.

Eval numbers I saw (verify_gate recomputes the official ones):
- Suite: 42/42 green (was 39).
- Default path, stub full bank (run -pre): BIT-IDENTICAL to ratchet bests on all
  9 aggregates (catch 1.0/1.0, false 0, harm 0, interrupt 0.625/1.0, recall 1.0,
  correct 0.6788, e2e 0.3427, worst contractor_luis). Per-line diff vs lap
  045035Z-pre: 16/16 persona-days identical on (line, decision, category, reason,
  detrimental, decider).
- Owner lane (run -owner, ANTICIPY_OWNER_INGEST=1): EXACTLY unchanged — catch
  0.5054 / worst 0.2222 (founder_jin), false 0, harm 0, interrupt 0.875/1.5,
  e2e 0.0208, recall_worst 0.25.
- Zero model calls, zero spend, zero real-world artifacts (mock channels; live
  paths env-gated off and never exercised).

Honest counting:
- This lap moves NO official metric and closes no gate — groundwork, named build
  lap it enables: the P3 closure lap (gate_P3.sh: real outbound TTS call read
  back status=completed, inbound reply resolves a pending ask, trigger->call
  <= 60s), which needs OWNER_PHONE confirmed (PENDING_FOR_OMAR item 2) + live
  Twilio env + ANTICIPY_CHANNELS_MODE=live. Every gate_P3 component now has a
  mock pin.

Next:
- P3 closure lap (human-gated on OWNER_PHONE): live legs — one real test call
  (self-owned number, read back by call sid, status=completed), one real inbound
  YES resolving a real pending ask, trigger->call latency. Port F19's explicit-
  auth-header pattern to text.py FIRST if the live SMS leg fails auth.
- F20 (ambiguous reply is silently refused): bounded clarification reply listing
  pending codes — budget-capped; pin refusal + exactly-one clarification send.
- D16 sibling now binds live ops: proactive.pending is in-memory, so an engine
  restart between ask and YES strands the ask itself (the F18 record linkage
  survives; the pending map doesn't). decider_deferred.json pattern exists to copy.
- Foreman calls carried: F17 (one brain — spine/hybrid extractor for the owner
  card extractor's 0.5054/0.2222 catch ceiling), C22 shingle scan (factory-side),
  whether owner-lane thresholds enter a gate.
