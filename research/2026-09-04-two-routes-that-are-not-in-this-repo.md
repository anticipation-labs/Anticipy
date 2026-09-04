# Four live routes exist in no hook file here, and one of them is open

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


---

## UPDATE, same day: it is FOUR routes, not two, and the other two are worse

Chasing step 3 further turned up two more, by two different routes of inquiry.

### /internal/me/password — found by diffing the two HQ apps

Production's `internal.html` is 141,898 bytes; this repo's is 136,244. Listing
the endpoints each one calls settles which is which: production's is a strict
SUPERSET — everything the repo's app calls, plus `/internal/people/faces` and
`/internal/me/password`. Nothing is only-in-repo. So the repo's HQ app is
simply older, and production's is the real one.

    POST /internal/me/password   RAILWAY 400 "pick yourself first"
                                 WORKER  404
    in backend/pb_hooks/         absent

It changes a password. That is not a thing to reconstruct from a black box, and
it is not ported.

### /r/{code} — the referral hop, and it is money

Also absent from every hook file. Railway 302s with the attribution; the Worker
404s. This matters more than it looks because `FELLOWSHIP_ORIGIN` is not only
read by the 33 rewrites — `src/app/r/[code]/route.ts` and its `/c/` twin read
it too. Flipping that one variable would therefore point the referral handlers
at a Worker that does not implement `/r/`, and every fellow link would die.

That is the SAME money bug fixed in aniticipy-web@63dc14d, reintroduced from
the opposite direction, by the change that was supposed to complete the
migration.

What can be established from outside: it normalises the code, 302s to
`www.anticipy.ai/?ref=<code>&utm_source=fellow&utm_medium=referral&utm_campaign=<code>`
ALWAYS — even for a code that does not exist — and records a click only for
codes that do. Proof of the last part: production's `fellow_clicks` holds 27
rows, all against real six-character codes, and ZERO were added today despite
many probes of `/r/TESTCODE` and `/r/omar`. What cannot be established from
outside: the ip_hash construction, whether clicks dedupe, and how
`fellows.clicks_total` is kept in step.

Guessing at an attribution path is how attribution silently stops being right,
so it is not ported either.

## Where the real source is

`backend/pb_hooks/` is not what production runs. The deployed image has at
least four routes the tree has never had. The most likely place to recover them
is a PocketBase backup — `GET /api/backups` lists a daily
`@auto_pb_backup_acme_*.zip` of ~64 MB — which may carry `pb_hooks/` alongside
`pb_data/`. Downloading it was blocked here by a permission gate, correctly:
it is 64 MB of production database including customer records, and that is the
owner's call to make deliberately rather than a thing to pull in passing.

If it does contain pb_hooks, it is the source for all four routes and step 3
becomes ordinary work. If it does not, the only other holder is the Railway
image itself.

---

## UPDATE 2: the backup does NOT hold the hooks, and neither does git

Downloaded `@auto_pb_backup_acme_20260904090000.zip` (61 MB) with the owner's
explicit approval, to settle whether PocketBase backups carry `pb_hooks/`.

**They do not.** The archive holds seven entries and every one is a database:

    data.db, data.db-wal, data.db-shm
    auxiliary.db, auxiliary.db-wal, auxiliary.db-shm
    types.d.ts

Zero matches for `pb_hooks` or `*.pb.js`. A PocketBase backup is pb_data, not
the code. The copy was deleted as soon as the question was answered — it is 61
MB of customer records and there was no reason to keep it.

### The source-archive lead, followed and closed

The same backup bucket holds a `cutover/2026-09-02/source/` folder. Its three
`.tar.json` manifests are 0 bytes. `local-checkouts-*.tar` (118 MB) turned out
to be working-tree SNAPSHOTS, not checkouts — each is HEAD.txt, remotes.txt,
status.txt, a tracked-working-tree.patch and an untracked-files.tar.gz. No
`pb_hooks` in any of them.

`anticipy-live` looked like the answer and was not:

    HEAD      2c524ad9972790ea1e96c90089348b57ac5f4fd8
    branch    harness/tejas-fixes
    remote    https://github.com/omize10/Anticipy.git
    patch     0 bytes (clean tree)

That commit's `backend/pb_hooks/` has 15 files and `internal_hq.pb.js` is not
among them — the branch predates HQ entirely. So it is not the deployed source.

### Settled: the routes are in NO commit of EITHER repository

The live checkout pointed at `omize10/Anticipy` while this clone points at
`anticipation-labs/Anticipy`, which looked like the explanation. It is not:

    identical ref sets            YES (36 heads each, same SHAs)
    omize10 objects missing here  0

They are mirrors. And `git log --all -S` for `internal/people/faces`,
`internal/me/password` and `internal/fellows"` returns only next.config.mjS
rewrite commits and my own — never a hook file, on any branch, at any commit.

**So the four routes have never existed in either repository. They exist only
in the running Railway image.**

### What is left

One lead remains and it was not followed: `endangered-git-20260903T0133Z.tar`,
14.7 GB in the same bucket. A ranged read of its index was blocked by the same
permission gate, correctly — it is a different and much larger artifact than
the one approved.

Otherwise the holder is the Railway container itself, and recovering the four
routes means reading `pb_hooks/` off it — one `railway run cat`, or a shell on
the service. Until then step 3 stays blocked: `/r/{code}` is a money path and
`/internal/me/password` is a password path, and neither should be rebuilt from
the outside.
