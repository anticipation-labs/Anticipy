# The five route-status divergences between the Worker and production, each accounted for

2026-09-04. A completeness diff across the full enumerated non-fellows,
non-internal route set: 22 of 27 identical in status, 5 differing. None is a
regression. Recorded so nobody re-flags them.

    route                  rail  work  verdict
    /me/phone/remove       404   401   Worker RESTORES a route prod's image lost
    /me/profile/upsert     404   401   Worker RESTORES a route prod's image lost
    /api/realtime          200   410   realtime deliberately disabled; no client uses it
    /_/                    200   404   PocketBase admin UI; not part of the product
    /internal/docs         404   401   dead sidebar link; 401 vs 404 for a no-key caller

## /me/phone/remove and /me/profile/upsert — the Worker is AHEAD

Production returns 404 "resource wasn't found" for both. That is not the route
refusing an unauthenticated caller — it is the route NOT EXISTING on the
deployed image, exactly the four-missing-routes finding in
research/2026-09-04-production-is-not-this-repo.md. The repo has them, the Worker
ported them (service.ts), so the Worker answers 401 "Sign in first." — the route
exists and gates on auth.

The iPhone CALLS both: POST /me/profile/upsert (AnticipyBackend.swift:405) and
POST /me/phone/remove (:376). So on production today, "save profile" and "remove
phone" are BROKEN — they 404 — and moving to the Worker FIXES them. That is a
net improvement, but it is a behaviour change at cutover: calls that currently
fail start succeeding. Worth a line in the release notes, not a fix.

## /api/realtime — 410 on purpose

The Worker returns 410 Gone for the SSE realtime endpoint. No shipped client
uses it: extension/background.js:1723 asserts there is no EventSource or
WebSocket anywhere in the extension, and iOS polls. Production still serves it
(200), so a hypothetical future realtime client would break — but none exists.
If one is ever added, this endpoint has to be built on Durable Objects; until
then 410 is the honest answer.

## /_/ — no PocketBase admin UI

`/_/` is PocketBase's superuser dashboard. The Worker is not PocketBase and does
not serve it (404). Superuser administration on Cloudflare is the D1 console and
wrangler, not a served SPA. No product surface depends on `/_/`.

## /internal/docs — a dead link, 401 vs 404

The HQ sidebar links to /internal/docs; the route exists on neither backend.
Production 404s it (no handler). The Worker 401s it, because hqGate runs on the
whole /internal/ prefix before any per-route dispatch, so a no-key caller is
refused before the route's absence is discovered. With a key the Worker also
404s it, matching production for the only caller that matters (the HQ app, which
holds a key). Leaving it: making the Worker 404 unknown /internal paths for
no-key callers would weaken the "nothing under /internal answers without a key"
property to fix a dead link.
