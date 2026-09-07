# Texting architecture and unfinished Sendblue migration

Inspected 2026-09-07 on `cloudflare-backend`, source HEAD `8948ca4`.
This is a source walkthrough, not a new live round-trip test or a repair.

## Actual message path

1. The owner texts the configured Anticipy Sendblue number in Messages.
2. Sendblue POSTs the incoming message to `/sms/sendblue`.
3. `migration/workers/src/routes/sendblue.ts` checks the shared webhook secret,
   receiving line, message handle, and content. `pb/sender.ts` resolves the
   sender against the owner's current account/profile phone. Unknown or
   ambiguous owners are not routed. The raw text is stored as an owner-scoped
   `sms_reply` event with a unique external event ID to deduplicate retries.
4. Connection-management language can be handled by the model-backed
   `connections/wiring.ts::handleInboundText` path: list connected apps,
   connect/disconnect an app, or choose work/personal accounts. It marks the
   event after replying. This is best effort: the independent brain poll can
   claim the same event first, allowing a duplicate answer.
5. `brain/worker.py::handle_inbound` feeds unprocessed messages to
   `brain/conversation.py::on_reply`. The classifier receives conversation
   turns, relevant memory, pending/blocked tasks, and recent outcomes. Its
   vocabulary includes new requests, confirmations, declines, modifications,
   answers to questions, and social chat. Interpretation can update work;
   execution still needs the appropriate permissions and available tools.
6. Conversation replies use a transport constructed with `SendblueArm` when
   Sendblue is selected and configured. `brain/sendblue_arm.py` POSTs
   `/api/send-message` with the sending line, recipient, content, and optional
   media/status callback. The Worker has a separate `messaging.ts::sendText`
   sender for connection links/codes, password resets, and connection notices.

Sendblue transports the words; it does not own Anticipy's memory or decide
which task a reply authorizes. The iOS app remains responsible for signup,
capture/permissions, and its own UI. Typed replies in the app are `app_reply`
events and suppress the SMS response. Durable conversation reconstruction
currently omits `app_reply`, so cross-channel continuity must not be described
as complete.

## Twilio remains executable

- Both provider selectors retain Twilio. With no explicit provider and missing
  Sendblue configuration, configured Twilio can be selected. This is a
  configuration fallback, not failover after a Sendblue HTTP error.
- The Python selector refuses an explicitly misconfigured provider by choosing
  mock. The Worker instead autodetects on an unrecognized provider name.
- `/sms/inbound` still routes to the Twilio webhook handler.
- `worker.py` still constructs `VoiceArm` when Twilio credentials exist. Some
  calling paths and generic delivery/error helpers still depend on it.
  `anticipy.voice` is overwritten with the selected text arm; the Sendblue
  wrapper refuses calls. Do not claim calling consistently works under
  Sendblue merely because a Twilio arm was constructed.
- `MessageTransport = TwilioTransport` is also a historical name: that adapter
  can wrap Sendblue. Renaming it alone would not remove real Twilio code.

## Defects and limits found in this walkthrough

1. **Meaning fallback violates Law 1.** `Conversation._classify` falls back on
   short-message length plus approval/refusal regexes when the model is absent,
   errors, or produces a malformed result. It can return confirm/decline.
   Ordinal and group-choice word lists also remain in reply handling. An
   unavailable interpretation must not manufacture authorization. This was
   inspected, not repaired or newly exercised live in this turn.
2. **Delivery callbacks are discarded.** `/sms/sendblue` returns 200 for
   outbound status updates without persisting their lifecycle. Initial API
   acceptance is not proof that the phone received a message.
3. **Group messages and media-only incoming messages are dropped.** A text
   accompanying media is retained without the media in the canonical event.
4. **Connection handler/brain race** and **app-reply history omission** above
   prevent a claim of one perfectly consistent conversation today.
5. A freshly erased account needs a new signup/current saved phone before
   incoming texts can resolve to its brain.

The complete Sendblue-only migration needs both senders and inbound routing
cleaned up, calling dependencies deliberately resolved, explicit production
configuration errors, persisted delivery status, model-only interpretation,
and an observed phone → brain → bounded task → phone test. No Twilio account,
credentials, runtime, or app build was changed for this explanation.

## Vendor behavior checked against primary documentation

- [Sending messages](https://docs.sendblue.com/getting-started/sending-messages):
  Sendblue provides iMessage with SMS fallback; that fallback does not require
  Anticipy to maintain a Twilio integration. Free shared-line accounts require
  recipient verification. A message can be queued before it is sent or
  delivered. The deployed account's current plan was not checked in this turn.
- [Webhooks](https://docs.sendblue.com/getting-started/webhooks/): inbound
  messages use a receive webhook; outbound status events can use a per-message
  callback or a configured outbound webhook.
- [Send API](https://docs.sendblue.com/api/resources/messages/methods/send):
  `/api/send-message` accepts `from_number`, `number`, and `content`.
