# Recovering hook source that exists in no git repository

2026-09-04. `fellowship.pb.js` was running on Railway and was in no commit of
either repository. It is now at `migration/recovered/fellowship.pb.js`.

## The problem

Four routes answered on production and 404'd on the Worker, and none of them
was in `backend/pb_hooks/`. `git log --all -S` across every branch found
nothing, and `omize10/Anticipy` — which the live checkout pointed at — turned
out to be a byte-identical mirror of `anticipation-labs/Anticipy`: same 36
refs, zero objects missing locally. Two of the four are a money path
(`/r/{code}`) and a password path (`/internal/me/password`), so reconstructing
them from the outside was the wrong move.

## What did not work, and why it is worth writing down

  * The PocketBase daily backup holds `data.db` and `auxiliary.db` and nothing
    else. A PocketBase backup is pb_data, not code.
  * `local-checkouts-*.tar` holds working-tree SNAPSHOTS — HEAD.txt,
    status.txt, remotes.txt, a patch, an untracked tarball — not checkouts.
  * `untracked-hq/` looked perfect and was a red herring: it is an untracked
    NEXT.JS HQ on branch `codex/anticipy-hq`, a parallel implementation, not
    the PocketBase hooks.
  * **Grepping the archive index for "pb_hooks" returns zero, and that is not
    evidence of absence.** The archive stores git OBJECT DUMPS, named by SHA.
    A path never appears. This nearly ended the search.

## What worked

`status.txt` sits beside each object dump and is `git status --porcelain=v2`,
which prints paths AND blob hashes:

    1 .M ... 0eb1af32f197860f63a084f141389cf6f9e1782a ... backend/pb_hooks/fellowship.pb.js
    1 .M ... 3f6104d76dfbbfadd42e384b80519991b5f8e41c ... backend/pb_hooks/fellowship_guardian.pb.js
    ?                                                     backend/pb_hooks/fellowship_host.pb.js

A path-to-SHA index, sitting next to a SHA-addressed object store.

## Getting 130 KB out of 14.7 GB without downloading 14.7 GB

The endpoint honours `Range` (`accept-ranges: bytes`), and a tar is a chain of
512-byte headers each declaring its payload size. So:

1. Walk the chain — read a header, take its `size`, skip to the next. Only
   headers are read. 38,871 entries indexed for about 1 MB of traffic.
2. The walk yields sizes in order, so every entry's byte offset is a running
   sum computed locally. No second pass.
3. Range-read exactly the two blobs. zlib-decompress; strip the
   `blob <len>\0` header.

Total downloaded: under 2 MB of a 14,726,164,480-byte archive. The file token
expires mid-scan, so the reader refreshes it on a 403 and continues.

## What the recovery changed

`/internal/fellows` had already been reverse-engineered from production's live
response and matched it on rows, ids and order. The source showed three things
that black-box matching could not:

    parental_consent   getString, a STRING — the port had made it a boolean
                       because the name reads like one
    conversions        carries hold_until; the port had invented `source` and
                       `paid_at` and omitted hold_until. Unfalsifiable from
                       outside because the table is empty on both sides.
    limits             fellows 500, submissions 200, conversions 300 — the port
                       had used 500 for all three

All three are fixed. `/internal/fellows` is now field-for-field identical to
production across 12 fellows and 5 submissions, ids and order included.

`/r/{code}` is ported for the first time — it could not be before. The parts
that were invisible from outside:

    ip_hash    sha256(ip + ANTICIPY_FELLOW_SALT), default salt "anticipy-fellows"
    dedupe     one click per code per ip_hash per HOUR
    XFF first  behind the anticipy.ai rewrite the peer address is Vercel for
               everyone, so deduping on it would credit a fellow once no matter
               how many people tapped
    revoked    code_revoked suppresses the click but NOT the redirect

Verified: `Location` byte-identical to Railway's for a valid code, an unknown
code and an invalid one. Finding that also surfaced `ANTICIPY_SITE_URL` —
Railway sends people to `www.anticipy.ai` while the file's default is the apex,
so every referral would have landed on a different host.

## Still open

`fellowship_host.pb.js` was UNTRACKED, so no blob exists and the recovery repo
has no untracked tarball. It is the likely home of `/internal/people/faces`
(still reverse-engineered here), `/internal/me/password` and
`/internal/fellows/pay`. Reading `pb_hooks/` off the Railway container is the
way to get those.

**And a caveat on what was recovered:** `status.txt` marks both files `.M` —
modified in the working tree. These blobs are the committed HEAD versions; an
uncommitted edit at snapshot time is not in the object store. So this is the
deployed source's most recent committed ancestor, not provably what Railway
runs. Every port off it was diffed against live production anyway, which is the
only check that settles it.
