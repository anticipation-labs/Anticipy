# The oracle is not calibrated yet

`contract_tests.py` was written FROM THE SOURCE of `backend/pb_hooks/`. It has
never been reconciled against what the running PocketBase actually answers, and
the first run against production shows why that step is not optional:

    187 tests: 42 failed, 75 passed, 70 skipped   (against LIVE PocketBase)

A test that fails against the thing it describes cannot judge a port. Until this
run is green, a Worker failure and a spec error are indistinguishable, and the
suite is worse than no suite because it looks authoritative.

## What the failures are, as far as they are understood

The one examined in full is representative of at least part of the set:

    test_ENTRY_STATUSES_a_post_may_only_create_held_or_queued[running]
      expected: 409  "work cannot be created in running"
      actual:   409  "running work needs an actor and lease"

The STATUS MATCHES. PocketBase did refuse the create; a DIFFERENT guard leg
fired first and said something else. The security property holds — a job cannot
be POSTed straight into `running` — and the test simply asserted which sentence
would come back, when several legs can refuse the same request and the order
between them is not part of the contract anyone wrote down.

That is over-specification, and the fix is to assert the refusal and only pin
the exact wording where the wording IS the contract (password_reset's identical
reply, evidence's single public sentence).

BUT NOT ALL OF THEM ARE THAT. Some failures are status-code differences, and a
status-code difference is either a spec error or a real divergence between the
hooks as read and the hooks as deployed. The second would matter a great deal:
`research/2026-08-26-hq-deploy-clobber.md` records that the deployed image and
the repo have diverged before, and CLAUDE.md's live-deploy rule exists because
"prod has served stale code twice". Each one has to be opened individually.
Do not assume they are all cosmetic.

## How to use this file

`pocketbase.xml` is the recorded reference run. Work through the failures:

  1. Open the hook source for the rule.
  2. Decide: is the TEST wrong, or is PRODUCTION not running the code in this repo?
  3. Fix the test, or write the divergence into research/ as a finding.

Only when this run is green does `BASE_URL=<worker>` mean anything.

## What IS already proven

- The Worker runs on real Cloudflare with D1, R2 and the Durable Object bound.
- It matches PocketBase on the guard's core behaviour: 403 without the service
  token, 200 with it, on `/api/collections/*`.
- It IMPROVES on it where the original fails open. PocketBase's guard.pb.js
  begins `if (!token) return e.next();` — no token means the whole database is
  public. The Worker answers 503 "refusing rather than serving unguarded".
- 14 tests (anonymous + offline) pass against both.
