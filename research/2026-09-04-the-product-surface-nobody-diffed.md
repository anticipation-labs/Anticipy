# The collection API serves 4 of 36 collections, and one of the missing ones is shipped

2026-09-04. Every diff so far compared HQ — the team's dashboard. Nobody had
diffed the PRODUCT surface: what the pendant, the iPhone and the Chrome
extension actually call. Doing that found gaps HQ testing structurally could not.

## The measurement

`/api/collections/<c>/records?perPage=1` with the service token, both origins:

    collection          railway  worker
    owners              200      200
    jobs                200      200
    events              200      200
    agents              400      200     <-- worker MORE permissive
    evidence            200      404     <-- worker does not serve it
    agent_llm_audit     200      404     <-- worker does not serve it
    fellows             403      404
    fellow_clicks       403      404
    internal_todos      403      404
    internal_people     403      404

`migration/workers/src/pb/schema.ts` defines exactly four collections —
`owners, agents, jobs, events`. Production has 36.

## The one that is shipped and breaks

`extension/background.js:1355` POSTs the receipt photo:

    const r = await send(`${await base()}/api/collections/evidence/records`,
      { method: "POST", headers: h, body: form })

It is a MULTIPART upload — a JPEG blob plus `job` and `effect_key` — and the
comment above it explains that `Content-Type` is deliberately deleted so the
boundary survives. On the Worker that POST is a 404.

This is "done = evidence": the errand finishes and the receipt photo is what
proves it. The READ half is already ported (`/api/files/{c}/{id}/{name}` serves
evidence out of R2, share window and all). The WRITE half is not, so after
cutover there would be nothing to read.

It fails soft, which is worse for detection than for users:

    console.log(`evidence: could not deposit the receipt photo (${r.status}) — the errand still stands`)

A 404 there is one console line in a background script nobody is watching. The
job still completes and reports success. The receipts simply stop existing,
and the first person to notice is whoever opens an old errand looking for one.

## The 403-vs-404 rows are not equivalent

`fellows`, `internal_*` and friends are refused by both, but Railway says 403
(the guard refuses a collection it knows) and the Worker says 404 (it has never
heard of it). Both deny, so nothing leaks — but a client that branches on the
status, or a human reading logs during cutover, sees a different story. Worth
matching, and cheap.

## `agents` is the inverted one, and it is the interesting one

Railway answers 400 to a plain list; the Worker answers 200. That is the known
quirk where the deployed `agents` collection rejects any `sort=` and any
`totalItems` — it broke the export until a `nosort` paging mode was written.
Here the Worker is MORE PERMISSIVE than production.

More permissive is not automatically better: whatever made production refuse
may be load-bearing, and a client written against a 400 does not expect rows.
It needs a decision, not a default.

## Why HQ testing could not have caught any of this

146 green tests all exercise `/internal/*` or the four ported collections. The
extension, the iOS app and `brain/` speak to a different surface entirely, and
no leg in the suite has ever pointed at it. Same shape as the two other misses
today: the sweep that stamped without sending, and the auth secret that no
same-origin test could see.

The rule that keeps earning its keep: **enumerate from the LIVE surface, not
from the source tree, and diff the surface the CLIENTS use, not the one the
tests already cover.**
