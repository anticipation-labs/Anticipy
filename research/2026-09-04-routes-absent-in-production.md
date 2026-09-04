# Routes this repo registers that production does not serve — 2026-09-04

Measured against `https://backend-production-61e0a.up.railway.app` while
reconciling `migration/spec/contract_tests.py` against the running PocketBase.
Eight of the suite's 42 failures are this one cause.

## The headline correction

The brief that opened this investigation named four absent routes. Only
**three** are absent. `POST /agent/upgrade-credential` is registered, is
running, and answers `403 {"error":"upgrade not authorized"}` from its own
handler in `agent_auth.pb.js:78-97`. Its contract test passes. It was never
a 404, and `extension/background.js:134-141` already documents the 403 as the
expected, deliberate outcome for this build:

> "It is authorized by the SERVER's master token, which this browser no longer
> holds ... So this call has been answered 403 since that release ... An
> install stuck here needs a reinstall, not another retry."

So the shipped Chrome extension is not calling a 404. It is calling a route
that exists and refuses it by design. Nothing to fix there.

The three genuinely absent routes are:

| route | registered at | production |
|---|---|---|
| `POST /evidence/share` | `evidence.pb.js:157` | 404 |
| `POST /me/phone/remove` | `phone_remove.pb.js:13` | 404 |
| `POST /me/profile/upsert` | `owner_profile_upsert.pb.js:23` | 404 |

Their 404 body is byte-identical to the body returned for a path that was never
routed at all (`POST /nonexistent-route-xyz`):
`{"data":{},"message":"The requested resource wasn't found.","status":404}`.
That is PocketBase's router-level miss, not a handler's refusal. The routes are
not registered.

## What is actually missing is whole FILES, not routes

`evidence.pb.js` registers three things, not one:

1. `routerUse` at line 56 — the access guard on `/api/files/`
2. `routerAdd POST /evidence/share` at line 157 — the share mint
3. `onRecordAfterCreateSuccess(..., "evidence")` at line 243 — the retention sweep

**All three are inert in production.** The guard is the measurable one. With it
loaded, `GET /api/files/<anything>/<id>/<file>` must answer
`404 {"error":"that evidence is not available"}` for every collection that is
not `evidence`, and must answer it for an unresolvable collection too. Measured:

    GET /api/files/owners/…/photo.png          -> {"message":"The requested resource wasn't found."}
    GET /api/files/evidence/…/photo.png        -> {"message":"The requested resource wasn't found."}
    GET /api/files/nosuchcollection/…/x.png    -> {"message":"Missing or invalid collection context."}

Those are PocketBase's native file-serving errors. The third one is conclusive:
a loaded guard would have caught the failing `findCollectionByNameOrId` and
returned its own sentence. The file is not participating in the request path at
all.

The same holds for the other two: `phone_remove.pb.js` and
`owner_profile_upsert.pb.js` each register exactly one route, and it is absent.

## Why: the deployed image corresponds to no commit in this repository

The tempting hypothesis was a stale image — production simply behind `main`. It
is not that, and the dates prove it. Hook files, by add-date, against whether
their routes answer:

| hook | added | live? |
|---|---|---|
| `owner_profile_owner.pb.js` | 2026-08-22 | yes |
| `evidence.pb.js` | 2026-08-25 | **NO** |
| `internal_hq.pb.js` | 2026-08-26 | yes |
| `owner_profile_upsert.pb.js` | 2026-09-01 | **NO** |
| `phone_remove.pb.js` | 2026-09-01 | **NO** |

A file added on 08-25 is missing while one added on 08-26 is present. No single
commit produces that set, so "production is pinned at commit X" cannot be the
explanation.

`pb_public` is the independent confirmation, and it is the strongest evidence
here because **a static file cannot throw at load**. Probing every file this
repo ships in `backend/pb_public`:

| file | added | production |
|---|---|---|
| `internal.html` | 2026-08-26 | 200 |
| `privacy.html` | 2026-08-12 | 200 |
| `setup.html` | 2026-07-30 | 200 |
| the three extension zips | 07-30..08-14 | 200 |
| `site.css` | 2026-08-22 | **404** |
| `theme.js` | 2026-08-22 | **404** |
| `mac.html` | 2026-08-30 | **404** |
| `mac/Anticipy-for-Mac.zip` | 2026-08-30 | **404** |

Identical non-monotonic shape: 08-22 assets missing, an 08-26 page present.
Two directories, two mechanisms (JS hook loading, static file serving), one
pattern. Whatever produced this selected files, it did not select a commit.

Every served file that does exist also **differs by hash** from this branch's
copy — `internal.html`, `privacy.html`, `setup.html` and all three extension
zips. The deployed `internal.html` is 141,898 bytes against this branch's
136,244: not an older, smaller build, a *different* one.

`research/2026-08-26-hq-deploy-clobber.md` already diagnosed this class and
names the mechanism: the Railway `backend` service is shared by several branch
lanes, and `railway up` uploads one lane's `backend/` directory wholesale, so
"deploying a feature branch that lacks another live lane removes that lane from
the image even though its database remains on the Railway volume." That note's
recovery is the exact fingerprint of what is running now — production was
rebuilt from "an exact archive of the active container, with only these changes
overlaid: `pb_hooks/internal_hq.pb.js`, the six HQ migrations, and the last
known-good `pb_public/internal.html`."

That overlay list explains the anomaly precisely. The only post-08-22 artifacts
present in the image are exactly the three things the overlay added. Everything
that lived solely on the pendant lane and was not in the archived container —
`site.css` and `theme.js` (08-22), `evidence.pb.js` (08-25) — was never
restored, because the recovery deliberately overlaid nothing else. Everything
created after 08-26 on any lane has simply never been deployed.

`backend/deploy.sh:23` corroborates it from the other side. It asserts
`test -f "$stage_dir/pb_public/mac/Anticipy-for-Mac.zip"` before uploading, and
that file is present in this tree (388,070 bytes) yet 404s in production. A
deploy through `deploy.sh` could not have produced the running image. The
guardrail that note closed with — "every backend deployment must be a union of
the active product lanes" — is not being met today.

## Hypotheses tested and rejected

* **A hook throws at load, so PocketBase skips registering it.** Rejected.
  All three files are the most conservatively written in `pb_hooks/`: not one
  has a single top-level executable statement other than its `routerAdd` /
  `routerUse` calls, and each carries an explicit comment saying so
  (`phone_remove.pb.js:11-12`, `evidence.pb.js:48-53`) — the pooled-JSVM
  discipline `sms.pb.js` and `account_delete.pb.js:42-56` document. There is no
  top-level `$os.getenv().x`, no `require()`, no undefined symbol to touch.
* **goja rejects some modern syntax in these files.** Rejected, and backwards.
  All 20 hook files pass `node --check`. The three absent files use *less*
  modern syntax than the loaded ones: they contain no spread, no `class`, no
  optional chaining, while `internal_hq.pb.js` — which loads fine — uses spread
  17 times and `class` once.
* **A `routerUse` middleware intercepts first.** Rejected. `guard.pb.js:29-35`
  guards only `/api/collections/` and `/api/realtime`, and an interception
  would produce that middleware's own refusal, not PocketBase's router-miss
  body.
* **A name or ordering collision.** Rejected. No path is registered twice
  anywhere in `pb_hooks/`, and the loaded/absent split does not follow
  alphabetical load order — `password_reset.pb.js` sorts between the two absent
  `owner_*`/`phone_*` files and is live.
* **The migration threw, as it once did.** Rejected for the current state, and
  worth recording because it is the *old* version of this bug.
  `1700000045_evidence.js:106-113` documents that this migration used to throw
  on every boot (`image.type` read as a property, not called as a method), that
  PocketBase refuses to start when a migration throws, and that
  "`/evidence/share` answered PocketBase's own 404 and everyone read that as
  'not deployed yet'." That is fixed: the `evidence` collection **exists** in
  production today (200, 0 rows). Today's 404 has the same symptom and a
  different cause, which is exactly why it was worth re-deriving rather than
  assuming.

## The measuring instrument this produced

Collections cannot date the image. PocketBase records applied migrations on the
`/pb_data` volume, so a collection persists across a clobber that drops the
migration file — `evidence` is present in production while its hook is gone.
**Only hooks and `pb_public` read the image**, because both are loaded fresh
from the container at boot. Any future check of "what is actually deployed"
should probe those two and ignore the schema.

## What this costs in production, right now

1. **"Done = evidence" is broken end to end.** The mint is 404, so the worker
   cannot obtain a `MediaUrl`, so the completion text cannot carry the receipt
   photo. This is the product promise in `evidence.pb.js:9-17`.

2. **The evidence host has no lock on it — this is a security finding, not a
   missing feature.** `1700000045_evidence.js:84-88` sets
   `listRule/viewRule/createRule = ""`, which in PocketBase means *public*. The
   migration's own comment says that is safe because it is "gated by
   guard.pb.js". That is true for `/api/collections/` — `guard.pb.js` is live
   and refuses. It is **not** true for `/api/files/`, which `guard.pb.js:29-35`
   does not cover and which `evidence.pb.js`'s absent `routerUse` was the sole
   guard for. So on the deployed server the file's central promise — "the
   normal state of an evidence photo is *not on the internet*", default deny
   until `share_expires` is set, a minutes-long window, a five-fetch ceiling —
   holds nowhere. Any stored evidence image would be anonymously fetchable by
   URL, permanently, with no counter. The only remaining barrier is path
   unguessability, which `evidence.pb.js:24-26` explicitly refuses to rely on:
   "unguessability is not a lock, it is a delay, so it is not relied on."

   Not currently exploitable: the `evidence` collection has **0 rows**, and
   with the mint 404 nothing in the tree can upload one. The exposure is latent,
   not live. But the guard must land *before* the first photo is written, not
   after — and the mint and the guard are in the same file, so whatever deploy
   fixes the feature is the deploy that closes the hole. They cannot be
   separated, which is the one piece of luck here.

3. **The image retention sweep is gone too.** `evidence.pb.js:243-268` caps
   evidence at 20 rows per owner and 60 total, on a 5 GB volume that has filled
   twice and taken the product down both times (`start.sh:10-13`,
   `audit_retention.pb.js:3-11`), where PocketBase's own backups triple the
   footprint of every stored byte. That cap does not exist on the running
   server. Again latent at 0 rows, and again it must be live before the first
   write, not after.

4. **Privacy and profile endpoints are unreachable.** `POST /me/phone/remove`
   is the only route that clears a phone number from both `owners.phone` and
   every `owner_profile` row; `POST /me/profile/upsert` is the only writer that
   enforces the eight-field allowlist. Both 404. Whatever the clients do
   instead is doing it without those guarantees.

5. **The Mac download is 404.** `/mac.html` and `/mac/Anticipy-for-Mac.zip` are
   both absent, against a stated directive that "any new user can download the
   Mac app from anticipy.ai/app". Same root cause, same fix.

## What would confirm it from the server side

None of the below was available from here — the Railway CLI is not installed in
this environment and I did not deploy, redeploy, or write anything to
production. In rough order of decisiveness:

1. `railway logs --service backend` across a boot. PocketBase logs a warning
   per hook file it fails to load. **Silence about `evidence.pb.js` is the
   confirmation**: a file that is absent produces no warning at all, whereas a
   file that threw produces a named one. This single check separates the two
   remaining stories cleanly.
2. The same boot log should show `evidence: a place a receipt photo can live…`
   and the `owner_profile: kept newest canonical row…` console lines if those
   migrations are in the image. Their absence dates the migration set.
3. `railway run --service backend ls -la /app/pb_hooks /app/pb_public` — a
   direct listing of the image, which settles it outright.
4. Railway's deployment history for service `backend`
   (project `c0a0f512-6ce0-43aa-b338-781d912e5ae3`): the timestamp and source
   of the currently-active deployment, compared against deployment
   `f2bc1a95-00a7-40c1-9bef-cb129724a247`, the 2026-08-26 clobber recovery. If
   the active deployment *is* that one, this note is fully explained.

## Still unknown

* Whether the running image contains the `1700000045_evidence.js` and
  `1700000054_owner_profile_canonical.js` migration files. The collections they
  touch exist, but they exist on the volume and would survive the file's
  removal, so presence of the schema proves nothing about the image. Testing
  the 08-31 migration's unique index on `owner_profile.owner_ref` requires a
  write, and I did not make one. The six live `owner_profile` rows have
  distinct `owner_ref` values, which is consistent with the migration having run
  and equally consistent with it never having been needed.
* Which lane's `backend/` tree the active image was built from, and whether the
  deployed `internal.html` (larger than this branch's) exists in any branch here.
* Whether any client is currently writing profile or phone changes by another
  path, and with what guarantees, given both endpoints 404.

## Suite changes made

Eight tests are marked `xfail` naming this file, rather than being weakened or
deleted. Each still executes and would be reported as an unexpected pass the
moment the missing hooks are deployed — which is the point: the marks are a
record of a server defect, not an adjustment to the contract.

* `TestEvidenceDoor` (all six) — the three `/api/files/` guard tests are the
  security ones; their asserted sentence, "that evidence is not available", is
  the wording the brief requires to stay exact, and it does. It is the server
  that no longer says it.
* `TestServiceRoutes::test_phone_remove_requires_an_account`
* `TestServiceRoutes::test_profile_upsert_requires_an_account`

Against the Cloudflare Worker these should all XPASS, and an XPASS here means
the port implements something PocketBase currently does not serve. That is a
correct and useful diff, not noise.
