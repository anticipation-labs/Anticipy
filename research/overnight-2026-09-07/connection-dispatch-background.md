# Connection planning without freezing the owner loop

2026-09-07. This correction replaces the proposed early-202/`ctx.waitUntil`
implementation before release. It does not change how a model interprets words,
which apps it selects, or which external actions are authorized.

## Why the initial async route was rejected

The proposed route returned HTTP 202 immediately while running all connection
planning in `ctx.waitUntil`. Cloudflare allows that work at most 30 seconds after
the response ends; unfinished promises are then cancelled. Several model and
catalog calls can exceed that. A durable database lease does not keep the Worker
invocation alive: the owner could otherwise wait five minutes for the expired
lease and restart the same overly long computation.

Verified against [Cloudflare's context documentation](https://developers.cloudflare.com/workers/runtime-apis/context/)
on 2026-09-07. The documentation distinguishes ongoing HTTP requests from the
30-second extension after returning a response, and recommends a Queue when
work must run fully out of band.

## What changed instead

- `/worker/connection-command` retains its original awaited HTTP response.
  Authentication, canonical stored event lookup, ownership, and the database
  execution fence remain unchanged. No new Queue or deployment binding is needed.
- `brain/connection_dispatch.py` provides one background HTTP worker. It admits
  at most one outstanding request rather than submitting an unbounded queue of
  futures. Completed results are retained in a bounded 16-entry cache keyed by
  **backend URL, owner reference, and input event ID**.
- `brain/worker.py::connection_command` immediately returns `pending` to the
  serial owner loop while that request runs. Existing handling preserves the
  original event for later polling. When the request completes, only its matching
  event can consume the result. Requests retain the existing 120-second network
  timeout.
- Only the HTTP request moves to the thread. Python conversation, memory writes,
  task release, and ordinary reply handling remain on the owner loop. Connection
  planning and its effects still run through the existing authenticated Worker
  and database lease, as they did before this correction.

The cache is an optimization, not authority. If a cache entry is evicted, a
subsequent poll asks the API about the same durable event again. It does not mint
a new task or bypass the API's execution fence. A failed request returns pending;
it does not authorize generic conversation to interpret an uncertain connection
effect as new work.

## Verification

```sh
python3 -m pytest -q tests/test_connection_command_dispatch.py tests/test_connection_dispatch_background.py
```

**9 tests passed.** Covered stored identity rather than caller text, API outcome
parsing, original-event retry, no duplicate generic interpretation, a deliberately
blocked request with 20 concurrent poll callers, no second request admitted while
one is running, owner-separated result consumption, exception recovery, and bounded
unconsumed-result memory.

```sh
cd migration/workers
node --experimental-strip-types --disable-warning=ExperimentalWarning test/connection-dispatch.test.ts
```

**9 Worker checks passed**, including ownership, durable command execution,
expired planning vs uncertain effects, and one saved reply/outbox across retries.

These tests use synthetic requests; no paid model or personal integration was
invoked. This removes the proposed platform-lifetime defect and the synchronous
wait on the owner loop. It does not establish completion of every live connection
flow, and requests which exceed their network timeout still require reconciliation
against the existing durable API state.

## Separate delivery findings sent to the parent for resolution

The new connection reply outbox originally claimed a permanent provider attempt
even when the API had no configured provider. That state is known to have caused
no external effect, so treating it like an ambiguous timeout prevents a separately
configured brain from delivering the saved reply. The same distinction matters
for a mock/skipped Python send. Unknown provider acceptance must remain fenced;
proven absence of a send needs a recoverable pending state.

The outbox's media argument also was not persisted across restart, although the
current ordinary reply call sites send text only. Finally, the new delivery-state
rows had no matching iOS reader at review time. Do not describe those rows alone
as a visible user-facing text-status indicator. The parent owns those follow-ups;
this document records the findings rather than claiming they are fixed here.
