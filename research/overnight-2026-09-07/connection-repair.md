# One conversation, one connection operation

The SMS webhook handled connection commands independently of the brain. A
poll could interpret the same message again. App input skipped that handler.
Its executor also required a phone, and its link minter required messaging
configuration even when only an in-app link was requested.

Both text providers and the brain now dispatch the stored event through one
owner-scoped D1 invocation. Planning is leased; execution has a separate
persistent fence. Retries recover the saved outcome. An uncertain external
operation is not repeated. An unavailable reply store produces an explicit
uncertainty answer when storage recovers. The app receives the durable answer
before the SMS channel makes a single delivery attempt.

The command model sees the prior conversation, measured source, speaker and
an explicitly targeted task card. A separate question identifies the catalog
search term; another chooses an actual returned toolkit. No app names or
semantic word matching are added to production. A missing target app causes a
question; a quoted instruction or completed report does not authorize a change.
Link creation now needs only its store, clock and public URL.

The hand router also runs without a public-search credential. Real-model D1
probes select the connected API for a query-based source lookup, and refuse
to invent a provider document ID when only an ID-based tool is available.

Validation before deployment:
- Full Python tests: 3,090 passed, two skipped.
- Full API tests and TypeScript checks pass on Node 24.
- Nine D1 dispatch checks cover concurrency, auth/owner boundaries, channel,
  expired leases, failed persistence and account deletion.
- Eleven real-model connection contrasts pass, including actual saved links,
  contextual yes, card-specific yes, quoted commands and an unknown app.
- The first model probes exposed missing link wiring; later probes exposed
  the deeper dependency on messaging. Those earlier failures remain in the
  private audit logs. Labels 1–4 are not the final passing proof.

Scope: the command path accepts owner app input and SMS. Ambient speech and
proactive offers need their own source/consent reasoning and remain separate
work. This is not proof of multi-step API task execution or provider OAuth
completion. The simulated catalog has no real account or mailbox credentials.

Deployment and live results will be appended after verification.
