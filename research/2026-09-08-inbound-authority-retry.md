# Inbound SMS authority — local verification, 8 September 2026

The layer audit identified a loss path: periodic profile refresh correctly
clears the outbound phone cache when the canonical read fails, but
handle_inbound interpreted that empty cache as proof that the owner's next SMS
came from a stranger. It stamped ignored_nonowner and permanently discarded
the answer. Conversely a stale matching cache could authorize a removed
number before the next refresh.

The SMS authorization boundary now reads the canonical phone before claiming
the event. A failed read leaves the same event id unclaimed and unmarked,
clears the outbound cache, and reaches no connection handler, model, queue
mutation, or reply. A later successful read allows the same event to proceed.
A verified empty phone or mismatching sender is still rejected. The actual
sender must be present in the webhook's goal field; missing identity can no
longer borrow the worker's cached owner number. Signed-in app replies and typed
transcripts retain their account-based authority and do not depend on this
phone read. Outbound replies retain their separate final canonical recheck.

Seven new regressions failed before the change; all eight dedicated tests pass
afterward. Sixty-six combined inbound, one-answer, phone-revocation, multitenant,
direct-queue, consolidation, connection-dispatch, and input-priority tests pass.
Independent review found no actionable regression and reran the inbound and
one-answer subset successfully. The legacy one-answer test that previously
endorsed a missing sender authenticating through fallback now requires refusal.
The never-silent offline proof supplies an explicit canonical phone fixture.
Its stale check for two removed per-kind polling calls initially failed; it now
drives the real shared direct-input poll, verifies the account-scoped filter,
and observes both transport kinds reaching the handler. All nine proof checks
pass, including error replies staying available in the app.

No production, SMS provider, or real model calls were made. A new canonical
backend read per nonempty inbound SMS is the latency/cost tradeoff; losing a
profile read cannot safely confer authority from a stale cached value. This
change does not bind an SMS approval to an earlier task revision and is not a
live proof of sender identity or provider delivery.
