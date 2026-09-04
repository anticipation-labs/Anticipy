# Two live routes exist in no hook file here, and one of them is open

2026-09-04. Found by the cutover pre-flight, which is the only reason they were
found at all.

## How

Step 3 of the cutover is "repoint the website", which is one variable:
`next.config.mjs:10` `FELLOWSHIP_ORIGIN`, read by 33 rewrites. Before flipping
it, every one of those 33 destinations was called on BOTH origins with the same
key and the status codes compared.

    31 identical.
     2 answered 200 on Railway and 404 on the Worker:

       GET /internal/people/faces
       GET /internal/fellows

Neither appears in `grep -rn 'routerAdd' backend/pb_hooks/*.js`. They are not
in this repository. Had the flip gone ahead on the strength of "HQ is fully
ported", the team's avatars and the entire Fellowship dashboard would have
started 404ing, and the first report would have been a person saying the page
looked broken.

This is the same finding as
`research/2026-09-04-production-is-not-this-repo.md`, arriving from the
opposite direction: that one measured files in the image that are MISSING from
the tree; this one found routes in the image that were never IN the tree.

## The data was already here; only the routes were missing

All nine `fellow_*` tables migrated cleanly — fellows (39), fellow_submissions
(5), fellow_conversions (0), fellow_clicks (27), fellow_codes (2), plus
applications, payouts, progress and meter. So this was never a data gap. The
export was complete; the route inventory was not, because the inventory was
built from the hook files rather than from what production actually answers.

**The lesson for the remaining cutover steps: enumerate from the LIVE surface,
not from the source tree.** The source tree is not what is running.

## Production as the specification

With no source to port from, production's live responses were the spec, and
every rule below was found by reproducing them exactly rather than guessed:

    fellows      WHERE status != 'removed' ORDER BY created DESC
                 VERIFIED: the same 12 rows of 39, in the same order.
                 (27 are 'removed'. A removed fellow keeps its row — the row is
                 the record that they were here — and stops being listed.)
    submissions  ORDER BY created DESC
                 VERIFIED: same 5 ids, same order.
    conversions  UNVERIFIED. Empty on both sides, so no projection is
                 checkable. Deliberately narrower than the table: the payout
                 plumbing (payout_key, payout_attempts, payout_ref, entered_by)
                 is left out, on the principle that an unverifiable projection
                 should err small.
    faces        the 6 ACTIVE people, id and name only. SET VERIFIED.
                 ORDER NOT VERIFIED — see below.

Final check: same top-level keys, same field names, same row counts, same ids
on every list, against live production.

## The ordering that could not be derived

`/internal/people/faces` returns Omar, Jose, Arav, Claude, Tejas, Tejass. That
is not any ordering of any column in `internal_people` — not name, created,
updated, last_in, id or is_admin, ascending or descending. (Curiously the first
three descend by id and the last three ascend by it, which is not one sort.)

`name ASC` is used instead, matching /internal/state's people list, and this
paragraph exists so nobody later mistakes a chosen order for a reproduced one.
For a row of avatars the order is cosmetic; the SET is what matters and it is
verified.

## FLAGGED: /internal/people/faces is UNGATED

Verified against production with no `X-Internal-Key` at all:

    GET /internal/people/faces  ->  200
    {"people":[{"id":"z1i584ytodst3qn","name":"Omar"}, ...]}

Six full names and six internal record ids, to anyone who asks. `/internal/
fellows` beside it answers 401.

It is reproduced here rather than quietly tightened, because a migration is the
wrong moment to change who can read something: closing it on the Worker while
Railway still serves it open would look fixed and not be, and closing it on
both is a product decision with a page behind it that might break.

**This is the owner's call, not mine.** Closing it is a two-line change on each
side — put the route behind the same key check `/internal/fellows` already uses
— and worth doing deliberately, together, once someone confirms what draws
those avatars and whether that caller holds a key.
