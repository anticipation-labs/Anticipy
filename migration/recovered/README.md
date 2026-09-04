# Deployed hook source recovered from a backup archive

These two files are **not** in any commit of `anticipation-labs/Anticipy` or its
mirror `omize10/Anticipy` — I checked every branch and every commit. They were
running on Railway and existed nowhere a `git log` could reach them. They are
here so that is no longer true.

## Provenance, exactly

    archive   cutover/2026-09-02/source/endangered-git-20260903T0133Z.tar
              (14.7 GB, in PocketBase's own backup bucket)
    repo      endangered-git/recovery/  — a git object dump, files named by SHA
    branch    recovery/full-reconstructed @ a962a8f237677ece8fd21c7a2b1ad3a3cb9e0cf6
    blobs     fellowship.pb.js           0eb1af32f197860f63a084f141389cf6f9e1782a
              fellowship_guardian.pb.js  3f6104d76dfbbfadd42e384b80519991b5f8e41c

Recovered by walking the tar's header chain to build an index without
downloading the archive (38,871 entries, ~1 MB of ranged reads), computing each
blob's byte offset from the cumulative entry sizes, range-reading just those two
objects, and zlib-decompressing them. Total downloaded: well under 2 MB of
14.7 GB.

Grepping the index for "pb_hooks" finds nothing and that is not evidence of
absence — a git object dump names files by SHA, not by path. The way in was the
`status.txt` beside the object dump, which lists paths AND their blob hashes.

## What they contain

`fellowship.pb.js` (113,393 bytes) defines 16 routes:

    GET  /fellows/confirm            POST /fellows/apply
    GET  /fellows/health             POST /fellows/code
    GET  /fellows/me                 POST /fellows/profile
    GET  /internal/fellows           POST /fellows/progress
    GET  /r/{code}                   POST /fellows/start
                                     POST /fellows/submissions
                                     POST /fellows/submissions/remove
                                     POST /fellows/verify
                                     POST /internal/fellows/remove
                                     POST /internal/fellows/submissions/release
                                     POST /internal/fellows/submissions/remove

`fellowship_guardian.pb.js` (17,670 bytes) defines 3:

    GET /fellows/guardian   POST /fellows/guardian   POST /fellows/guardian/link

## The caveat that matters

`status.txt` records both files as `.M` — MODIFIED IN THE WORKING TREE. The
blobs above are the committed HEAD/index versions; whatever local edit was
uncommitted at snapshot time is not in the object store and is not here. So
these are the deployed source's most recent COMMITTED ancestor, not
provably byte-identical to what Railway runs. Diff any port against live
production before trusting it.

## Still missing, and not recoverable this way

`backend/pb_hooks/fellowship_host.pb.js` was UNTRACKED at the snapshot — no
blob exists, and the recovery repo has no `untracked-files.tar.gz`. It is the
most likely home of the three routes still unported:

    GET  /internal/people/faces      (currently reverse-engineered)
    POST /internal/me/password       (not ported — it changes a password)
    POST /internal/fellows/pay       (not ported — it moves money)

Reading `pb_hooks/` off the Railway container remains the way to get those.
