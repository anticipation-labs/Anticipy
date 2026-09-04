# The fellowship API is on the Worker: 17 routes, every unauthenticated contract verified

2026-09-04. The Worker now serves the fellowship surface that
anticipyfellowship.com — a separate Vercel site — calls on this same backend.
Until today those 17 routes were 404 on the Worker, which meant a fellow could
not sign up, apply, verify, submit, or consent once traffic moved.

## Where the source came from

fellowship.pb.js and fellowship_guardian.pb.js are in no git commit; they were
recovered from a backup archive (migration/recovered/). So this is a port from
recovered source, not a reconstruction — but the recovered files were marked
MODIFIED in the working tree at snapshot time, so they are the most-recent
COMMITTED ancestor of what Railway runs, not provably byte-identical. Production
stays the arbiter, which is why every route was diffed against it.

## How it was ported

A workflow fanned out one agent per route (12 agents, 17 routes; the four
internal admin actions and three guardian routes grouped). Each read its slice
of the recovered source, inspected the D1 schema for the tables it writes,
transcribed the handler against a fixed shared-helper surface (fellows_base.ts)
so the outputs compose, and verified its UNAUTHENTICATED contract against
production with safe pre-write probes only. 12/12 completed, 0 errors.

Assembled into src/routes/fellows.ts (17 functions), wired in index.ts — public
`/fellows/*` above the HQ block (no key; each self-authenticates by email code,
session hash, or guardian token), the three `/internal/fellows/*` admin actions
beside `/internal/fellows` (each self-gates on X-Internal-Key).

## Verified: 17 of 17 identical to production

Every route probed on both origins with inputs that hit validation BEFORE any
write, email, or side effect — a malformed email, an under-13 birth year, a
non-US/CA country, a missing session, a bogus id, no key. Status codes and
response bodies match production exactly, field-for-field:

    /fellows/health          200, same four booleans
    /fellows/code            bad-email / bad-dob / under-13 / non-US-CA — all
                             four refusal strings byte-for-byte
    /fellows/verify          "That code isn't live any more..."
    /fellows/start           {field:"email", message:"That email doesn't look right."}
    /fellows/me,apply,progress,profile,submissions   401 {reauth:true}
    /fellows/guardian        GET 200, POST "That link is missing something..."
    /internal/fellows/*      401 {"error":"wrong key"} without the key

(The only raw-byte difference was JSON KEY ORDER — production emits {message,ok},
the port emits source order {ok,message}. Order-independent parse: 17/17 equal.
No client reads JSON by position.)

Full suite after: 150 passed / 0 failed on the Worker, no regression.

## What ships UNPROVEN, and why

The AUTHENTICATED halves could not be exercised without a fellow session, and
their side effects (Resend email, oembed HTTP verification, minor-consent
tokens, payout writes) must not be triggered against production as a test. So,
exactly as HQ's authenticated half:

  * /fellows/code's success path sends real mail and writes fellow_codes; the
    throttle layers (per-minute, per-hour, per-IP, global meter) are transcribed
    from source, not observed.
  * /fellows/verify and /fellows/start's session-minting is source-only.
  * /fellows/submissions (741 lines) does oembed verification against external
    platforms — the largest and least-tested handler.
  * The guardian consent flow (minors) and the internal payout/removal actions
    write real state; ported faithfully, verified only at the refusal boundary.

These must be diffed against production with a real fellow session before
anticipyfellowship.com is repointed. Risk is flagged per-function in fellows.ts.

## Still missing

POST /internal/fellows/pay — moves money, and it is in the UNTRACKED
fellowship_host.pb.js, which has no git blob. Only recoverable off the Railway
container. Not ported; will 404 on the Worker. The fellowship admin screen
therefore renders fully (GET /internal/fellows returns real data) but its Pay
button 404s until that file is read off the container.
