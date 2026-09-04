# The deployed backend is not built from this repo

Measured 2026-09-04 against https://backend-production-61e0a.up.railway.app
while porting the evidence host and static assets to R2.

## Every static file differs. Not one matches.

`backend/pb_public/` is COPYed into the image at `backend/Dockerfile:11`, so
what production serves at those paths should be byte-identical to the repo.

    path                                    repo      prod  code  match
    /anticipy-extension.zip               277549    122423   200  NO
    /anticipy-claude-version-extension    277549    122423   200  NO
    /anticipy-codex-version-extension     277549    122423   200  NO
    /internal.html                        136244    141898   200  NO
    /privacy.html                          10839      7188   200  NO
    /setup.html                            12659     16747   200  NO
    /mac.html                               7304         0   404  NO
    /site.css                              19993         0   404  NO
    /theme.js                               2762         0   404  NO
    /mac/Anticipy-for-Mac.zip             388070         0   404  NO

    0 of 10 byte-identical.

Six serve DIFFERENT CONTENT. Four are absent entirely. `internal.html` --
the HQ single-page app -- is 5,654 bytes larger in production than in the repo,
so production's HQ is a build this tree does not contain.

## Four hook routes are also missing

404 on both POST and GET, while OPTIONS returns 204, so the server is up and the
path simply is not routed:

    POST /evidence/share            backend/pb_hooks/evidence.pb.js:157
    POST /me/phone/remove           backend/pb_hooks/phone_remove.pb.js:13
    POST /me/profile/upsert         backend/pb_hooks/owner_profile_upsert.pb.js:23
    POST /agent/upgrade-credential

And it is NOT simply an old image. `password_reset.pb.js` and
`phone_remove.pb.js` were changed in the SAME COMMIT (cd4a490f, 2026-09-01):

    POST /auth/reset/request  -> 200     password_reset.pb.js
    POST /me/phone/remove     -> 404     phone_remove.pb.js

Same commit. One route lives, one does not.

## What this costs today, before any migration

- `/evidence/share` mints the Twilio `MediaUrl` for the receipt photo.
  "Done = evidence" ends in a text carrying that screenshot. That is 404.
- `extension/background.js:142` calls `/agent/upgrade-credential`. A SHIPPED
  Chrome extension is calling a route that does not exist.
- `/mac/Anticipy-for-Mac.zip` is 404 even though `backend/deploy.sh` asserts
  the file exists before it will deploy -- so either deploy.sh has not run
  against this image, or it ran from a tree where the assertion passed and the
  upload did not.
- The extension being served is a DIFFERENT BUILD (122 KB vs 277 KB) from the
  one in this repo. Whatever users install is not what `extension/` contains.

## What it means for the Cloudflare port

**The repo cannot be used as the description of production.** Everything built
so far -- `migration/spec/CONTRACT.md`, `contract_tests.py`, the Worker in
`migration/workers/` -- was written FROM THE SOURCE. That was the only option,
and it is still the right artifact, but it describes a system that is not the
one running.

So:

1. The oracle must be calibrated against the LIVE server, not the source. That
   work is already underway and its 42 failures now read differently: some of
   them are not spec errors at all, they are this divergence showing through.
2. A cutover that replaces production with a faithful port of THIS REPO would
   CHANGE BEHAVIOUR -- possibly restoring routes that are currently dead, which
   sounds good, but also serving an HQ and an extension nobody has tested
   against the live data.
3. Nothing about the deployed image should be inferred. Every claim needs
   measuring against the server.

## Still unknown, and only Railway can answer

- Why those four hook files do not register while their neighbours do. The best
  clue in the tree is the comment at the top of `backend/pb_hooks/sms.pb.js`:
  PocketBase runs handlers in a POOLED JS RUNTIME where the enclosing file's
  top-level scope does not exist by the time a request arrives, and a file that
  throws during load is skipped with only a log line. A top-level statement that
  throws would produce exactly this shape.
- When the running image was built, and from what.
- Whether `backend/deploy.sh` has ever run successfully against it.

Railway's build and boot logs would settle all three in minutes. Nobody has
looked; the CLI is not installed on this machine and there is no token.

## Prior art in this repo

`research/2026-08-26-hq-deploy-clobber.md` records the image and the repo
diverging before. `CLAUDE.md`'s live-deploy rule exists because "prod has served
stale code twice". This is the third time, and it went unnoticed until a
migration forced a byte-level comparison.
