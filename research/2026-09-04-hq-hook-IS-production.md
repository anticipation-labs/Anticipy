# internal_hq.pb.js IS what production runs — 35/35, and it unblocks the HQ port

2026-09-04. This narrows `2026-09-04-production-is-not-this-repo.md`, which was
right about what it measured and wrong about how far it generalised. Read both.

## Why this was worth measuring

HQ's ~33 data routes were the last big piece of the Cloudflare port and they
were parked as BLOCKED, on this reasoning: production is not built from this
repo, so porting from `backend/pb_hooks/internal_hq.pb.js` would be porting
from a source that may not be production's, and `ANTICIPY_INTERNAL_KEY` is not
on this machine so nothing could be checked afterwards. Porting blind is what
CLAUDE.md law 6 exists to stop.

Both halves of that turn out to be too pessimistic, and the fix was to find an
oracle that does not need the key.

## The oracle: unauthenticated behaviour is a fingerprint

Every gated handler in that file checks the key as its FIRST statement and
returns 401 before touching anything (verified by reading, which is also why
probing with POST is safe: nothing runs). So the unauthenticated response of
every route is observable from outside, needs no credential, and is specified
line-by-line by the source. If the deployed file were a different build, the
exceptions would not line up.

All 37 declared routes were probed with their declared method and no key.
Two were excluded: `/internal/health` (public) and `/internal/cal/{token}`
(parameterised). Of the remaining 35:

  * 28 returned `401 {"error":"wrong key"}` — as the source says.
  * 7 did NOT return 401 — and the source predicts every one of them:

        GET  /fellows/hq                200 HTML   ungated; serves ANTICIPY_HQ_PAGE
        GET  /internal/research/status  410        "the AI surface was removed from HQ"
        POST /internal/research         410        same
        POST /internal/router           410        same
        POST /internal/clerk/exchange   400        "no Clerk token in the request"
                                                   -- token checked BEFORE the key
        POST /internal/session          200        "That code didn't match anyone.
                                                    Check it and try again."
        POST /internal/session/end      200        {"ok":true} -- already signed out

**35 of 35 conform**, matching not just status codes but the error strings
verbatim, including the three-way 410 and the deliberately indistinguishable
session reply. `GET /internal/health` independently returns exactly what the
source constructs, `version: "hq-2"` included.

A build that merely resembled this file would not reproduce seven distinct
exceptions and their exact wording.

## The correction this forces

`production-is-not-this-repo.md` proved, correctly:

  * 10/10 `pb_public/` static files differ or are absent, `internal.html`
    among them (5,654 bytes larger in production);
  * 4 hook routes 404 to POST while a route from the SAME COMMIT answers 200.

None of that evidence came from `internal_hq.pb.js`. The four missing routes
live in `evidence.pb.js`, `phone_remove.pb.js`, `owner_profile_upsert.pb.js`
and the agent hook. The differing assets are assets. So the accurate statement
is narrower and more useful than "production is not this repo":

  **Production's pb_public/ ASSETS are not this tree's, and at least four hook
  FILES are missing from the deployed image — but internal_hq.pb.js is present
  and is this version of it.**

`/fellows/hq` shows both halves at once, cleanly: the ROUTE is this repo's
(it conforms), and the HTML it hands back is NOT (it reads `internal.html`
off disk, and that file differs). Route layer and asset layer diverged
separately and must be reasoned about separately.

## What the HQ port may now assume, and what it still may not

MAY: `internal_hq.pb.js` is the correct source to port from. It is no longer
a guess.

MAY: unauthenticated conformance is a runnable gate leg, today, with no
credential. Every ported route must reproduce the table above against the
Worker. That covers the whole gate surface -- 401 vs 400 vs 410 vs 200 -- which
is the part most likely to be got wrong in a port and the part that is a
security property.

MAY NOT: authenticated behaviour is still unverified. Response bodies, filters,
pagination, write semantics and the dual-auth session path cannot be diffed
against production without `ANTICIPY_INTERNAL_KEY`. Porting them from source is
legitimate; calling them DONE is not, under law 3 -- nothing is fixed until its
gate leg is green against LIVE.

So the port proceeds, and the authenticated half ships as UNPROVEN until the
key is available. That is a real distinction and it goes in STATUS.md, not in
a commit message that later reads as a green tick.

## Reproducing

    grep -oE 'routerAdd\("(GET|POST|PUT|PATCH|DELETE)", *"[^"]+"' \
      backend/pb_hooks/internal_hq.pb.js | sed 's/routerAdd("//; s/", *"/ /; s/"$//'

then probe each with its declared method, no `X-Internal-Key`, and diff the
status and body against the source.
