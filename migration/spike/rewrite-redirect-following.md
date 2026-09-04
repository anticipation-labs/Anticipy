# FINDING: OpenNext follows redirects that Vercel passes through

Found 2026-09-04 by diffing `smoke.sh` output between production and the
Cloudflare build. It is the exact class of breakage that diff exists to catch:
nothing errors, every status is a success, and a paid feature stops working.

## The observation

`next.config.mjs:82-83` rewrites the referral links to the backend:

    { source: "/r/:code", destination: `${FELLOWSHIP_ORIGIN}/r/:code` },
    { source: "/c/:code", destination: `${FELLOWSHIP_ORIGIN}/r/:code` },

Railway answers `/r/<code>` with a redirect that CARRIES THE ATTRIBUTION:

    HTTP/2 302
    location: https://www.anticipy.ai/?ref=CODE&utm_source=fellow
              &utm_medium=referral&utm_campaign=CODE

Production passes that 302 straight to the browser. The Cloudflare build does
not:

    production   HTTP/2 302  location: ...?ref=CODE&utm_source=fellow...
    cloudflare   HTTP/1.1 200 OK
                 Server: Vercel          <-- the giveaway
                 Age: 253596
                 <title>Anticipy: the AI pendant...</title>

`Server: Vercel` on a response from the local Worker means the rewrite DID
reach Railway, Railway DID answer 302, and then the Worker's own `fetch()`
followed that redirect to anticipy.ai and returned the final page as its own
200. Workers' `fetch()` defaults to `redirect: "follow"`; Vercel's rewrite
proxy does not follow.

## Why it matters more than a status code

The redirect IS the product here. Everything that makes a referral countable
lives in the hop:

  * `?ref=CODE` has to arrive in the BROWSER's address bar for first-touch
    analytics to see it. Swallowed server-side, it never does.
  * `utm_source=fellow&utm_medium=referral&utm_campaign=CODE` likewise.
  * Any `Set-Cookie` on the redirect response is consumed by the Worker's
    fetch instead of being handed to the visitor.

So on Cloudflare the visitor still lands on a working homepage -- and the
fellow who sent them is not credited. Nothing 500s. Nothing is logged. The
smoke run scores it 200/pass. `/internal/fellows/pay` is a real route
(next.config.mjs:151); this is money.

## The fix

Whatever serves these rewrites must not follow. In a Worker that is
`fetch(url, { redirect: "manual" })`, and the 3xx plus its `Location` and
`Set-Cookie` are returned verbatim. Wherever the `/internal/*` and `/r/`
rewrites are reimplemented, this is a required property, not a nicety.

BEFORE CUTOVER, check every one of the 34 rewrites for the same shape: any
destination that answers 3xx is affected. `/r/:code` and `/c/:code` are
confirmed. The `/internal/*` routes could not be tested from here -- they sit
behind the middleware passcode gate and return 401 identically on both
platforms -- so they are UNVERIFIED, not proven safe. `smoke.sh --gate-cookie`
exists for exactly that and needs a signed gate cookie to run.

## Related, and fixed separately

`src/app/c/[handle]/route.ts` was a filesystem route for the SAME path. The
2026-08-22 commit "Serve the fellowship from anticipy.ai, and retire the UGC
creator programme" added the `/c/:code` rewrite but never deleted the old
handler. On Vercel the rewrite won; on OpenNext the filesystem route won, so
Cloudflare silently resurrected the retired programme's handler -- one that
queries `anticipy_ugc_creators`, a table `next.config.mjs:38-41` records was
NEVER CREATED in Supabase. Removed, so both platforms now agree the rewrite
owns `/c/`.

---

## RESOLVED 2026-09-04 — fixed, and the mechanism proven rather than argued

`aniticipy-web@63dc14d` on branch `cloudflare`.

Both paths stopped being rewrites. They are route handlers now:
`src/app/r/[code]/route.ts` and `src/app/c/[code]/route.ts`, each forwarding
the hop with `redirect: "manual"` and returning the upstream status, `Location`
and `Set-Cookie` verbatim. The two rewrites are deleted from `next.config.mjs`.

Doing it in application code rather than hunting for an OpenNext proxy option
is deliberate: the behaviour then stops depending on which proxy is underneath,
so it cannot regress on an OpenNext upgrade or a move back to Vercel.

### The mechanism, isolated on workerd

A throwaway Worker, same upstream URL, only the option differs:

    fetch(url)                        -> 200, location: null
    fetch(url, {redirect: "manual"})  -> 302, location: ...?ref=testcode&utm_...

That is the whole bug in two lines. The 200 is why nothing ever alerted.

### The fix, verified on both runtimes

    node    (next start)   GET /r/TESTCODE -> 302 ...?ref=testcode&utm_...
    workerd (wrangler dev) GET /r/TESTCODE -> 302 ...?ref=testcode&utm_...
    workerd                GET /c/TESTCODE -> 302 ...?ref=testcode&utm_...

An unrecognised code still 307s to the homepage instead of dead-ending, because
these links are printed in bios and burned into video captions where a typo
cannot be corrected afterwards.

### The other 33 rewrites: mostly cleared, honestly

The doc above said the `/internal/*` rewrites could not be tested because they
401 behind the middleware gate. That was the wrong control. The gate is a
VERCEL-side middleware; redirect shape is a property of the UPSTREAM. Probing
Railway directly bypasses the gate entirely and answers the question:

  * 9 destinations are GET-reachable (200/401). **None answers 3xx.**
  * 24 answer 404 to a GET. That is not a missing route -- PocketBase registers
    routes per method, so a GET against a POST-only route is a 404 by
    construction. Their redirect shape is genuinely **UNVERIFIED**; verifying
    them needs `ANTICIPY_INTERNAL_KEY` and a POST, and POSTing to live routes
    like `/internal/fellows/pay` is not a probe anyone should run.

So the bug was confined to `/r/` and `/c/`, which are fixed. The 24 POST-only
routes stay on the cutover checklist -- and the cutover repoints them at the
Worker, where this property is owned by our code rather than inherited.
