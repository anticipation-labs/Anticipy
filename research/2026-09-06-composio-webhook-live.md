# The expiry webhook, configured and proven on production

2026-09-06. The vendor half of the Connections spec's NEEDS RECONNECT surface.

## What was actually there before

Nothing. `GET /api/v3/webhook_subscriptions` returned `total_items: 0` — the
project had never had a webhook subscription at all. So even with the handler
deployed, no `connected_account.expired` would ever have arrived.

## Facts measured, not read off docs

- The path is **`/api/v3/webhook_subscriptions`**, with an UNDERSCORE. The
  vendor's own docs print `webhook-subscriptions` with a hyphen, and that 404s.
  Same for the rotate endpoint: `/rotate_secret`, not `/rotate-secret`.
- `POST` requires `webhook_url` and `enabled_events`. The API names the missing
  fields itself on an empty body, and names the bad value on an invalid event —
  which is how the event string was confirmed rather than assumed.
- The event is **`composio.connected_account.expired`**, exactly as the spec
  quotes it. `connected_account.expired`, `connection.expired` and
  `CONNECTED_ACCOUNT_EXPIRED` were never tried, because the first guess was
  accepted and a second POST would have created a second subscription.
- The secret comes back **64 characters, plain** — no `whsec_` prefix. The
  handler's `webhookKeyBytes` covers both shapes, so this needed no change.
- Verification is Standard Webhooks: `webhook-id` / `webhook-timestamp` /
  `webhook-signature`, HMAC-SHA256 over `{id}.{timestamp}.{raw body}`, base64,
  presented as `v1,<sig>`, 300-second window.

## Subscription

    ws_QetBGYGkLJwT -> https://api.anticipy.ai/connections/events
    events: [composio.connected_account.expired]

Exactly one, and the gate leg refuses to run if it ever finds two: two
subscriptions means two secrets, only one of which the Worker holds, and a leg
that picked the first would be green or red by luck.

## A secret was leaked into a transcript and rotated

The create call's response body was printed while probing the event enum, and
it carried the secret. The first ~40 characters reached a session transcript.
It was rotated immediately via `POST /webhook_subscriptions/{id}/rotate_secret`
and the exposed value is dead. The replacement went from the API response
straight into `wrangler secret put` inside one process, was never printed, and
the temp file was removed.

The lesson is small and cheap: when probing an API that mints credentials,
print the STATUS and the field NAMES, never the body.

## Proven on production, not in the repo

    POST /connections/events, unsigned              -> 403 {"ok":false,"error":"forbidden"}
    POST /connections/events, forged signature      -> 403
    POST /connections/events, signed but 301s stale -> 403
    POST /connections/events, correctly signed      -> 200 {"ok":true,"ignored":"no such connection"}
    POST /connections/events, signed, other event   -> 200 {"ok":true,"ignored":"not an expiry"}
    POST /connections/eventsX (the control)         -> 404
    GET  /connections/events                        -> 405, Allow: POST

Before `wrangler secret put`, the unsigned case was **503** — so the difference
between "deployed with no secret" and "deployed and verifying" is a before and
after on the same URL, not a reading of the source.

The signed case is the one that proves anything end to end: it exercises the
HMAC, the freshness window and the store read. It names an account no row
holds, so it writes nothing and touches no owner, which is what makes it safe
to run against production as often as anybody likes.

## The leg

`overnight/is_connect_live.py` leg 10, with 13 self-test cases. One status code
separates four states — 404 not deployed, 503 no secret, 403 refused, 200
handled — and the control path one character away proves a 403 is THIS route
rather than the zone refusing everything.

Without the leg, the feature could have silently stopped being deployed and
every scoreboard would have stayed green. That is the failure this repo keeps
having, and it is why the leg was written before anybody asked for it.

## Still not done

The webhook flips `connections.status` and `connect_nudges.state` to
`needs_reconnect`. The phone reads the first verbatim, so Connected Apps shows
it today. **The TEXT half cannot go out**: `installNudgeWiring` has zero callers
(`connections/due.ts` says so in its own header), so nothing fills the AskWriter
port and the spec's "Until then I'll use the browser" sentence is unwritten.
That is a separate job and it is not this one.
