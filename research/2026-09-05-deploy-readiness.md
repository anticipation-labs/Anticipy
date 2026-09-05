# Is the backend safe to deploy? — 2026-09-05, measured against LIVE

`backend/deploy.sh` ships all of `pb_public/`, `pb_hooks/` and `pb_migrations/`
together, and there are three migrations plus ~670 lines of hook changes that
have never been live. The extension rebuild (0.12.0) rides on the same deploy.
This is the pre-deploy audit, every fact checked against the live service, not
inferred from the tree. It answers the one question that matters: what could
this deploy break that a rollback cannot un-break?

**Verdict: nothing found. Every destructive path was checked against live data
and each one is a no-op today.** The deploy is still an outward-facing act and
was not run inside this file.

## The three migrations

| migration | what it does | destructive? | live check | rollback |
|---|---|---|---|---|
| `1700000053_off_volume_backups` | turns on PocketBase's daily S3 backup, 14 kept | no | **throws at boot if any of 4 `ANTICIPY_BACKUP_S3_*` envs is unset** — checked on the live service, all four SET (plus REGION) | clean: disables S3, keeps 2 |
| `1700000054_owner_profile_canonical` | **deletes duplicate `owner_profile` rows** (newest survives) then adds a unique index on `owner_ref` | **YES** — `app.delete()` on older duplicates | live: 6 rows, 6 distinct `owner_ref`, **0 duplicates → deletes nothing** | drops the index only; a deleted row would NOT come back, which is why the live count matters |
| `1700000055_active_commitment_identity` | adds `commitment_key` field + partial unique index on `jobs` | no (additive) | schema-only | drops index + field |

The one that could lose data — 054 — was written correctly (newest-first sort,
`owned[0]` kept byte-for-byte, verification throws so the transaction aborts on
any doubt) AND has nothing to delete on the live volume today. If it ran on a
volume that DID have duplicates, the older ones would be gone for good; that is
the only irreversible thing in this deploy and it is currently a no-op.

## What the deploy also ships, read from the diff

`pb_hooks/`: `owner_profile_upsert` (+198), `phone_remove` (+120), `sms` (+95
inbound signature handling), `research_lane` (+71), `job_commitment_identity`
(+19), `password_reset` (±30). `start.sh` (+7). These have Python-side tests in
`tests/` and the two-sided contract the Brief describes, but **none of them has
run on the live host**, and hooks are where PocketBase surprises live — a JS
error in a hook takes the route down, not the process.

## What was NOT checked, and cannot be from here

- Whether the live PocketBase version accepts all three migration APIs
  (`app.findRecordsByFilter`, `jobs.fields.removeById`) — the Dockerfile pins
  0.30.4 and the migrations were written against it, but the running container
  was not queried for its version.
- Whether the four backup envs hold VALID credentials, only that they are set.
  A wrong key fails the 09:00 backup cron, not the boot.
- The hooks against live traffic. `proof/postdeploy_production.py` exists for
  exactly this and must be run after, not before.

## How to know it worked — the post-deploy sequence, in order

    python3 overnight/is_it_live.py            # served extension = 0.12.0, byte-identical
    python3 overnight/stranger_gate.py         # leg 1 THE HANDS ARE DOWNLOADABLE goes green
    python3 proof/postdeploy_production.py     # read-only acceptance + signed-SMS probe
    python3 overnight/are_the_ears_live.py     # speech still arriving after the hook changes

Law 3: until `is_it_live` says 0.12.0, nothing in the browser region is done.
