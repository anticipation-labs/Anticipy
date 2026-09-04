# EXPORT — get everything out before anything goes away

The owner's rule for this migration is *export everything first, then decide.*
Nothing is discarded, scaled to zero, or deleted until a **verified** export
exists on hardware Anticipy controls. This document is the ordered procedure.

Artifacts in this directory:

| File | What it is |
|---|---|
| `EXPORT.md` | this runbook |
| `export_pocketbase.sh` | pages every collection out of the live PocketBase, downloads every file-field blob, pulls the native archive, writes a manifest with per-collection row counts and a SHA-256 per file |
| `import_d1.py` | reads that export, emits D1 SQL, runs `wrangler d1 execute`, and reconciles source counts against destination counts |
| `reencrypt_vault.md` | **read this before cutover.** The company vault cannot survive the move as-is |

---

## The five durable stores

| # | Store | Where it lives | Covered by an existing backup? |
|---|---|---|---|
| 1 | PocketBase SQLite `/pb_data/data.db` (~264 MB, 26 collections in the repo **plus whatever else production has**) | Railway volume on service `backend` | yes — 09:00 UTC daily to R2, 14 generations (`backend/pb_migrations/1700000053_off_volume_backups.js:23-24`) |
| 2 | evidence file-field blobs under `/pb_data/storage` | same volume | only **inside** the archive zips — they are not rows and no REST listing enumerates them |
| 3 | brain per-owner state: `/data/owners/<owner_ref>/memory.db` + `clock_state.json`, plus the legacy `/data/clock_state.json` | a **second, separate** Railway volume on service `worker` | yes — daily verified zip to R2 under `worker/` (`brain/supervisor.py:358-362`, `brain/state_backup.py:153-163`). **Not** in any PocketBase backup |
| 4 | Supabase Postgres | Supabase project `ogbxpqkmsdrcuilafycn` | Supabase's own PITR. **Supabase stays** — the owner chose to leave it. It is documented here only so the recovery point is complete |
| 5 | Cloudflare R2 `anticipy-pocketbase-backups-production` | Cloudflare | it *is* the backup. Private, public access disabled, SSE-AES256 (`research/2026-08-31-database-resilience.md:52-59`) |

Two of these have no second copy anywhere and are the reason this runbook is
ordered the way it is:

- **The brain's memory** (#3) is the assistant's long-term mind — episodes,
  nodes, edges, profile facts, procedures, vetoed facts
  (`brain/memory.py:33-168`). It is a plain SQLite file per owner on a volume
  PocketBase cannot see, which is exactly why account deletion needed its own
  `purges` collection to reach it
  (`backend/pb_migrations/1700000039_purges.js:5-10`).
- **The vault** (#1, collection `internal_passwords`) is ciphertext only the
  dying binary can read. See `reencrypt_vault.md`. **Do not reach cutover
  without doing that.**

---

## Credentials the owner must supply

Nothing in this runbook works without these, and none of them should be typed
into a shell that keeps history. Use `read -rs`, or a `.env` file with mode
`600` that you delete when you are done.

| Step | Name | Where it lives now | Why it is needed |
|---|---|---|---|
| 2 | `PB_SUPERUSER_EMAIL`, `PB_SUPERUSER_PASSWORD` | a `_superusers` record on the live backend | **Superuser, not the service token.** `guard.pb.js:395` lets a superuser past the production lock, and PocketBase superusers bypass collection API rules — which is the only way to read the fourteen `internal_*` HQ collections, every one of which was created with all rules `null` on purpose (`backend/pb_migrations/1700000038_internal_hq.js:22-27`). A service-token export returns **zero** HQ rows and looks like a success |
| 2 | `PB_URL` | the live backend origin | — |
| 3 | Railway account access to project `anticipy-production`, services `backend` and `worker` | Railway | to run the state backup on the worker container and to freeze writers |
| 4, 7 | `ANTICIPY_BACKUP_S3_ACCESS_KEY`, `ANTICIPY_BACKUP_S3_SECRET`, `ANTICIPY_BACKUP_S3_ENDPOINT`, `ANTICIPY_BACKUP_S3_BUCKET` | already set on services `backend` and `worker`; the R2 token is named `anticipy-production-database-backups` | to list and download the existing generations onto the operator's machine. This token is scoped to the backup bucket only (`research/2026-08-31-database-resilience.md:54-59`) |
| 5 | `ANTICIPY_VAULT_KEY_GCM` | **you generate it** | the new vault key. See `reencrypt_vault.md` step 2 |
| 6 | Supabase project access (service role or a dashboard login) | Supabase | to take the documentation backup of a store that is staying |
| 9 | Cloudflare account + `wrangler login`, D1 database name | Cloudflare | to run the import |

`ANTICIPY_VAULT_KEY` and `PB_SETTINGS_ENCRYPTION_KEY` are **never read or
typed by a human** in this procedure. They stay on the Railway services and are
used in-process.

---

## Tools on the operator's machine

```sh
curl --version        # any recent build
jq --version          # 1.6+
python3 --version     # 3.9+ is enough; import_d1.py is stdlib-only
node --version        # 18+, only for reencrypt_vault.md
unzip -v              # archive CRC checks
sqlite3 --version     # memory.db integrity checks
aws --version         # or rclone, to talk to R2's S3 API
railway --version     # Railway CLI, 5.30+
wrangler --version    # only for the import
```

Everything lands in one directory. Pick it now and keep it:

```sh
export EXPORT_DIR="$HOME/anticipy-export-$(date -u +%Y%m%d)"
mkdir -p "$EXPORT_DIR" && chmod 700 "$EXPORT_DIR"
```

> This directory will hold transcripts, phone numbers, email addresses,
> password-reset hashes and a photograph of every page an errand touched. Treat
> it as the most sensitive thing on the machine. Do not put it in Dropbox,
> iCloud Drive, or a git repository. See **Step 10**.

---

## Step 0 — confirm the recovery point that already exists, before touching anything

If the daily backups have silently stopped, you want to know that *now*, not
after freezing production.

```sh
export AWS_ACCESS_KEY_ID="$ANTICIPY_BACKUP_S3_ACCESS_KEY"
export AWS_SECRET_ACCESS_KEY="$ANTICIPY_BACKUP_S3_SECRET"
export AWS_DEFAULT_REGION=auto
R2="--endpoint-url $ANTICIPY_BACKUP_S3_ENDPOINT"
BUCKET="$ANTICIPY_BACKUP_S3_BUCKET"     # anticipy-pocketbase-backups-production

aws $R2 s3 ls "s3://$BUCKET/" --recursive --human-readable | tee "$EXPORT_DIR/r2-inventory-before.txt"
```

Read the listing for three things:

1. **A PocketBase archive from within the last 24 hours.** The cron is
   `0 9 * * *` with `cronMaxKeep = 14`
   (`1700000053_off_volume_backups.js:23-24`). Fourteen generations should be
   present. The migration sets no prefix, so PocketBase's own archives land at
   the bucket root; the hand-made bootstrap copy is under `pocketbase/bootstrap/`.
2. **A worker-state archive from within the last 24 hours**, under `worker/`
   (`brain/state_backup.py:162` — prefix defaults to `worker/`; `state-<stamp>.zip`).
3. **Nothing else you did not expect.**

If either #1 or #2 is missing or stale, **stop and fix the backup before
continuing.** A migration that begins from a broken recovery point has no
rollback.

---

## Step 1 — freeze the writers

Full read-only is not something PocketBase offers, so this is done by stopping
the things that write, in the order that produces the fewest surprises.

```sh
railway link --project anticipy-production

# 1a. The brain. It is the loudest writer -- one process per owner, writing
#     events, jobs, segments and its own memory.db continuously.
railway service worker
railway down --service worker        # or set replicas to 0 in the dashboard

# 1b. Watch the backend go quiet.
railway logs --service backend | tail -40
```

The phone, the Chrome extension and the Mac app can still write while the
backend is up. That is accepted and handled by **Step 9's delta pass** — the
alternative is a hard outage for the length of the export, which is not worth
buying. Announce a change freeze to whoever is using HQ.

Record the moment the freeze began; the delta pass needs it:

```sh
date -u +%Y-%m-%dT%H:%M:%SZ | tee "$EXPORT_DIR/freeze_started_at.txt"
```

Do **not** stop the `backend` service. `export_pocketbase.sh` talks to it, and
`backend/start.sh:17` deletes `auxiliary.db` on every boot — a restart is not
destructive to data, but there is no reason to take one.

---

## Step 2 — export PocketBase: rows, blobs, and the native archive

```sh
export PB_URL="https://<the live backend origin>"
read -rsp 'superuser email: ' PB_SUPERUSER_EMAIL; echo
read -rsp 'superuser password: ' PB_SUPERUSER_PASSWORD; echo
export PB_SUPERUSER_EMAIL PB_SUPERUSER_PASSWORD

bash migration/runbooks/export_pocketbase.sh "$EXPORT_DIR/pocketbase"
```

What it does, and why each part is there:

- **Enumerates collections from the server, not from the repo.** The repo's
  `backend/pb_migrations/` creates 26 collections (12 product + 14 `internal_*`).
  **Production has at least nine more.** `migration/d1/FELLOWSHIP-PRECEDENT.md`
  and `migration/d1/GAPS.md` name them: `fellows`, `fellow_applications`,
  `fellow_submissions`, `fellow_payouts`, `fellow_conversions`, `fellow_codes`,
  `fellow_clicks`, `fellow_progress`, `fellow_meter` — none created by any
  migration in this tree, two of them independently confirmed live in
  `research/2026-08-31-founder-identity-reset.md:112-114`. Their schemas are
  unknowable from the repo, which is the whole reason the script asks the
  server. It prints every collection the server names that the repo does not
  into `logs/unknown_collections.txt`, and exports it like any other. The
  repo-known list inside the script is a **diff aid, never a filter** — nothing
  is skipped for being unrecognised.

  `internal_people` may likewise carry columns no migration declares (HQ has a
  password route and a face route that nothing in this tree answers — see
  `migration/d1/GAPS.md`). The export takes whatever the server returns, so
  undeclared columns land in the NDJSON and `import_d1.py` creates columns for
  them.
- **Pages with an `id` cursor, never a `status` filter.**
  `research_lane.pb.js:436-442` rewrites the filter of any `GET` on
  `/api/collections/jobs/records` whose filter matches `status="queued"` and
  does not mention `lane`, appending
  `&& lane != "research" && lane != "supervised_read" && lane != "device_calendar"`.
  It has **no superuser exemption.** An export that filtered on status would
  silently drop three whole lanes of jobs and reconcile against a total that
  had been narrowed to match. The script's only filter is `id > "<last>"`.
- **Downloads every file-field blob.** Today that is `evidence.image` — a
  half-scale JPEG or PNG capped at 400 KB
  (`backend/pb_migrations/1700000045_evidence.js:72-74`). The script derives
  file fields from the collection definitions, so a field added after this was
  written is still collected. `evidence.pb.js:60,66` lets a superuser past the
  `/api/files/` door without spending the share-window fetch counter
  (`evidence.pb.js:131-132`), so exporting does not burn anyone's live share.
- **Pulls PocketBase's own archive of `/pb_data`.** This is not redundancy.
  See the next section.
- **Writes `manifest.json`** with, per collection: `total_items_reported` (what
  the server said), `rows_exported` (what landed on disk), `reconciles`,
  `fields_absent_from_output`, file-field names, blob count, and the NDJSON's
  byte length and SHA-256. Plus a flat `SHA256SUMS` over everything.
- **Exits non-zero** if any collection's row count does not reconcile, or if no
  native archive was obtained.

### The native archive is not optional

The REST API physically cannot return two classes of field:

- **Auth-collection system fields.** `owners` is `type: "auth"`
  (`backend/pb_migrations/1700000008_owners.js:19-23`); PocketBase injects
  `password` and `tokenKey` itself and does not serialise them. **No password
  hash comes out through REST.** If accounts are to keep working after the
  move, the hashes come from `data.db` inside the archive, or every user
  resets their password.
- **Fields declared hidden.** `agents.agent_token`
  (`backend/pb_migrations/1700000026_agent_tokens.js:11`) is the 256-bit
  per-agent credential every paired Chrome install authenticates with. Losing
  it means every extension re-pairs.

`export_pocketbase.sh` measures this rather than assuming it: any field that a
collection declares and that appears in **no** exported row is recorded in
`manifest.gaps` with the reason. Read that section of the summary.

The archive also carries `/pb_data/storage` — store #2 — which no REST listing
enumerates.

### Verify before moving on

```sh
( cd "$EXPORT_DIR/pocketbase" \
  && shasum -a 256 -c SHA256SUMS > /tmp/sums.out 2>&1 \
  && echo "every file matches its digest" \
  || { echo "DIGEST MISMATCH:"; grep -v ': OK$' /tmp/sums.out; false; } )

jq -r '"reconciled=\(.reconciled)  gaps=\(.gaps|length)  archive=\(.backup.path // "MISSING")"' \
  "$EXPORT_DIR/pocketbase/manifest.json"
unzip -tqq "$EXPORT_DIR/pocketbase/backup/"*.zip && echo "archive CRC ok"
```

(`logs/export.log` is not in `SHA256SUMS` — it is still being appended to when
the digests are taken. It is a transcript, not data.)

Open the archive and check the database inside it is a database:

```sh
tmp=$(mktemp -d)
unzip -q "$EXPORT_DIR/pocketbase/backup/"*.zip -d "$tmp"
sqlite3 "$tmp/pb_data/data.db" "PRAGMA quick_check;"          # expect: ok
sqlite3 "$tmp/pb_data/data.db" "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;" \
  | tee "$EXPORT_DIR/pocketbase/archive_tables.txt"
du -sh "$tmp/pb_data/storage" 2>/dev/null || echo "no storage directory in the archive"
rm -rf "$tmp"
```

Cross-check the archive's tables against the REST enumeration. A table in the
archive that is not in `collections.json` is a collection someone deleted from
the API but not from SQLite; a collection in `collections.json` that is not a
table is a view.

---

## Step 3 — the evidence blobs, checked

Already downloaded by step 2, but confirm the count matches the rows that claim
to have one:

```sh
jq -r 'select((.image // "") != "") | .id' \
  "$EXPORT_DIR/pocketbase/records/evidence.ndjson" | wc -l
jq '[.files[] | select(.collection == "evidence")] | length' \
  "$EXPORT_DIR/pocketbase/manifest.json"
```

These two numbers must be equal. If they are not, `manifest.gaps` names each
record whose blob failed and the HTTP status it failed with.

---

## Step 4 — the brain's per-owner state, off the second volume

This is the store with the least redundancy and the highest irreplaceability:
one SQLite database per owner holding everything the assistant remembers about
that person, on a volume nothing else backs up.

`brain/state_backup.py` already does this correctly and is already running
daily. Use it rather than writing something new — it copies each database
through **SQLite's online backup API** and runs `PRAGMA quick_check` before
uploading (`brain/state_backup.py:73-79`), refuses symlinks, validates JSON,
and verifies the uploaded object's size and SHA-256 metadata after the fact.
A `cp` of a live SQLite file does none of that.

### 4a. Force a fresh snapshot from inside the worker container

`railway run` executes **locally** with the remote environment injected — it
does not run in the container and cannot see `/data`. To reach the volume you
need a shell **in** the container:

```sh
railway service worker
railway ssh --service worker
```

Inside that shell:

```sh
ls -la /data /data/owners
du -sh /data
python -c "
from brain import state_backup
print(state_backup.backup_state_to_s3('/data'))
"
```

`/data` and not `/data/owners`: the supervisor backs up the whole volume root
(`brain/supervisor.py:33,360`), which also catches the legacy
`/data/clock_state.json` (`brain/worker.py:58`) that predates per-owner
directories. `state_files()` yields only `.db` and `.json`
(`brain/state_backup.py:55-64`), so nothing else on the volume is collected.

The call prints the R2 key it wrote, e.g. `worker/state-20260903T2340Z.zip`.
Record it.

> If the worker service was scaled to zero in step 1, scale it back to one
> replica for this step and stop it again afterwards — or do step 4 **before**
> step 1. A snapshot of a stopped container is still correct (nothing is
> writing), but you cannot `railway ssh` into a container that is not running.

### 4b. Pull it down and verify it independently

```sh
mkdir -p "$EXPORT_DIR/worker-state"
KEY="worker/state-YYYYMMDDTHHMMSSZ.zip"     # the key printed above
aws $R2 s3 cp "s3://$BUCKET/$KEY" "$EXPORT_DIR/worker-state/"

# every generation, not only the newest -- yesterday's copy is what you want
# when today's turns out to have been taken mid-corruption
aws $R2 s3 sync "s3://$BUCKET/worker/" "$EXPORT_DIR/worker-state/all/"
```

Then verify. This checks the zip's CRC, every SHA-256 in its own manifest, and
runs an integrity check on each `memory.db` it contains:

```sh
python3 - "$EXPORT_DIR/worker-state/$(basename "$KEY")" <<'PY'
import hashlib, json, sqlite3, sys, tempfile, zipfile, pathlib
path = sys.argv[1]
with zipfile.ZipFile(path) as z:
    bad = z.testzip()
    if bad:
        sys.exit("CRC FAILED on %s" % bad)
    manifest = json.loads(z.read("manifest.json"))
    print("format=%s created_at=%s files=%d"
          % (manifest["format"], manifest["created_at"], len(manifest["files"])))
    tmp = pathlib.Path(tempfile.mkdtemp())
    problems = []
    for entry in manifest["files"]:
        raw = z.read(entry["path"])
        if len(raw) != entry["bytes"]:
            problems.append("%s: %d bytes, manifest says %d"
                            % (entry["path"], len(raw), entry["bytes"]))
        digest = hashlib.sha256(raw).hexdigest()
        if digest != entry["sha256"]:
            problems.append("%s: sha256 mismatch" % entry["path"])
        if entry["path"].endswith(".db"):
            target = tmp / pathlib.Path(entry["path"]).name
            target.write_bytes(raw)
            verdict = sqlite3.connect(str(target)).execute("PRAGMA quick_check").fetchone()[0]
            tables = [r[0] for r in sqlite3.connect(str(target)).execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
            rows = {}
            for t in tables:
                try:
                    rows[t] = sqlite3.connect(str(target)).execute(
                        'SELECT count(*) FROM "%s"' % t).fetchone()[0]
                except Exception as exc:
                    rows[t] = "ERR %s" % exc
            print("  %-52s quick_check=%s  %s" % (entry["path"], verdict, rows))
            if verdict != "ok":
                problems.append("%s: quick_check=%s" % (entry["path"], verdict))
        else:
            json.loads(raw)          # a clock_state.json that will not parse is a problem
            print("  %-52s json ok (%d bytes)" % (entry["path"], len(raw)))
    if problems:
        for p in problems:
            print("  ! " + p)
        sys.exit("%d problem(s) -- this archive is NOT a valid recovery point" % len(problems))
    print("ALL FILES VERIFIED")
PY
```

### 4c. Cross-check the owner count

Every live owner must have a state directory in the archive, and every
directory in the archive must correspond to an owner or to a completed purge.

```sh
# owners in the export
jq -r '.id' "$EXPORT_DIR/pocketbase/records/owners.ndjson" | sort > /tmp/owners.txt
# owner directories in the state archive
unzip -l "$EXPORT_DIR/worker-state/$(basename "$KEY")" \
  | awk '{print $4}' | grep '^owners/' | cut -d/ -f2 | sort -u > /tmp/state_dirs.txt
comm -23 /tmp/owners.txt /tmp/state_dirs.txt   # owners with NO memory -- expected for brand-new accounts
comm -13 /tmp/owners.txt /tmp/state_dirs.txt   # memory with NO owner -- check against purges
jq -r '.owner_ref' "$EXPORT_DIR/pocketbase/records/purges.ndjson" | sort
```

The last known-good reference point: 9 owners, 8 owner profiles, 1 649 events,
196 jobs, 446 agent rows, and 18 durable SQLite/JSON files across nine owner
directories, on 2026-09-01
(`research/2026-08-31-database-resilience.md:80-88`). Today's numbers should be
that or larger, not smaller.

---

## Step 5 — re-encrypt the vault

**Do not skip this and do not defer it past decommissioning.**

`internal_passwords.secret_enc` is ciphertext from PocketBase's Go
`$security.encrypt` keyed by `ANTICIPY_VAULT_KEY`
(`backend/pb_hooks/internal_hq.pb.js:3079`), read back only by
`$security.decrypt` in that same binary (`:3140`). Plan on nothing in a Worker
being able to open it. The re-wrap has to happen while PocketBase is still
running.

Follow **`migration/runbooks/reencrypt_vault.md`** in full. It writes
`$EXPORT_DIR/pocketbase/vault/vault_rewrapped.json`, and `import_d1.py` refuses
to import the vault without it.

```sh
jq -r '"\(.format)  rows=\(.source_rows)  key=\(.key_env)  fp=\(.key_fingerprint)"' \
  "$EXPORT_DIR/pocketbase/vault/vault_rewrapped.json"
```

---

## Step 6 — Supabase (it stays; document it anyway)

Supabase is not moving. It is in this runbook because a recovery point that
covers four of five stores is not a recovery point.

```sh
mkdir -p "$EXPORT_DIR/supabase"
# schema, from the repo -- the migrations are already tracked
cp -R supabase/migrations "$EXPORT_DIR/supabase/migrations"

# data. Get the connection string from Supabase -> Project Settings -> Database.
# Never put it on a command line; export it and let pg_dump read the env.
read -rsp 'supabase connection string: ' PGURI; echo; export PGURI
pg_dump "$PGURI" --format=custom --no-owner --no-privileges \
  --file "$EXPORT_DIR/supabase/supabase-$(date -u +%Y%m%dT%H%M%SZ).dump"
unset PGURI
shasum -a 256 "$EXPORT_DIR/supabase/"*.dump > "$EXPORT_DIR/supabase/SHA256SUMS"
```

Confirm the dump is restorable — a dump nobody has opened is a hope:

```sh
pg_restore --list "$EXPORT_DIR/supabase/"*.dump | head -40
pg_restore --list "$EXPORT_DIR/supabase/"*.dump | grep -c 'TABLE DATA'
```

The tables the website actually touches (`src/`) include `anticipy_waitlist`,
`anticipy_admin_users`, `anticipy_profiles`, `anticipy_sessions`,
`anticipy_transcripts`, `anticipy_memory`, `anticipy_applications`,
`anticipy_google_tokens`, the `crm_*` family and the engine trajectory tables.
Spot-check that the `TABLE DATA` list covers them.

> If `pg_dump` is unavailable or the direct connection is blocked, use the
> Supabase dashboard's own backup/download, and record in
> `$EXPORT_DIR/supabase/README.txt` which mechanism produced the file and when.

---

## Step 7 — take a copy of R2 itself

R2 is store #5 and it is also the only off-site copy of #1 and #3. Pull the
generations down so the export does not depend on a Cloudflare account that is
about to be reorganised.

```sh
mkdir -p "$EXPORT_DIR/r2"
aws $R2 s3 sync "s3://$BUCKET/" "$EXPORT_DIR/r2/" --exclude '*' \
  --include '*.zip' --include 'worker/*' --include 'pocketbase/*'
aws $R2 s3 ls "s3://$BUCKET/" --recursive --human-readable \
  > "$EXPORT_DIR/r2-inventory-after.txt"
diff "$EXPORT_DIR/r2-inventory-before.txt" "$EXPORT_DIR/r2-inventory-after.txt" || true
```

The `diff` should show only the objects you deliberately created in steps 2 and
4. Anything else appearing during the freeze means something is still writing.

**Do not delete anything from R2 during this migration.** The bucket's
retention (14 generations each) is the rollback.

---

## Step 8 — the acceptance gate

Every box below must be ticked before **anything** is scaled down, deleted, or
pointed at Cloudflare. Write the result into
`$EXPORT_DIR/ACCEPTANCE.md` and date it.

- [ ] `manifest.json` `reconciled` is `true`, and every collection's
      `rows_exported` equals `total_items_reported`
- [ ] `shasum -a 256 -c SHA256SUMS` reports no failures
- [ ] every collection the server named is in `records/` — including the ones
      in `logs/unknown_collections.txt`
- [ ] the native archive downloaded, passed `unzip -t`, and its `data.db`
      passed `PRAGMA quick_check`
- [ ] the archive contains `pb_data/storage`, and the evidence blob count on
      disk equals the number of evidence rows that name an image
- [ ] `manifest.gaps` has been **read**, and every gap is either
      (a) covered by the native archive, or (b) written into `ACCEPTANCE.md` as
      an accepted loss with the owner's sign-off
- [ ] the worker-state archive verified: CRC, every manifest SHA-256, and
      `PRAGMA quick_check = ok` on every `memory.db`
- [ ] every owner id in `owners.ndjson` either has a state directory or is a
      genuinely new account with no memory yet
- [ ] `vault/vault_rewrapped.json` exists, opens under WebCrypto, is bound to
      its record ids, and `ANTICIPY_VAULT_KEY_GCM` is in the password manager
- [ ] the Supabase dump lists its tables under `pg_restore --list`
- [ ] `EXPORT_DIR` has been copied to a second physical location (Step 10)
- [ ] the owner has seen this checklist, ticked

Until this gate passes, the correct answer to "can we turn off Railway?" is
**no**, without qualification.

---

## Step 9 — the delta pass, at cutover

Steps 2–4 run against a system that phones and browsers can still write to.
The gap is closed at cutover, not before.

Immediately before flipping DNS/clients to the Worker:

1. **Stop the backend** (`railway down --service backend`) — now the write set
   is genuinely closed.
2. **Re-run the export** into a *second* directory:

   ```sh
   bash migration/runbooks/export_pocketbase.sh "$EXPORT_DIR/pocketbase-final"
   ```

3. **Diff the two.** New and changed rows, and — the part a timestamp query
   cannot see — deleted ones:

   ```sh
   for f in "$EXPORT_DIR"/pocketbase-final/records/*.ndjson; do
     n=$(basename "$f" .ndjson)
     old="$EXPORT_DIR/pocketbase/records/$n.ndjson"
     [ -f "$old" ] || { echo "NEW COLLECTION: $n"; continue; }
     added=$(comm -13 <(jq -r .id "$old" | sort) <(jq -r .id "$f" | sort) | wc -l)
     gone=$(comm -23 <(jq -r .id "$old" | sort) <(jq -r .id "$f" | sort) | wc -l)
     changed=$(comm -13 <(sort "$old") <(sort "$f") | wc -l)
     printf '%-28s +%-6s -%-6s ~%s\n' "$n" "$added" "$gone" "$changed"
   done
   ```

   A `-` count is a **delete**, which no `updated > <time>` query would ever
   have found. This is why the diff is on id sets and not on timestamps.

4. **Import `pocketbase-final`, not `pocketbase`.** The first export is the
   safety copy; the second is the one that goes to D1.
5. Repeat step 4a/4b for the worker state against the now-stopped worker.

---

## Step 10 — where the export lives afterwards

```sh
# a checksum of the whole thing, so a later copy can be proven identical
( cd "$EXPORT_DIR" && find . -type f -print0 | sort -z | xargs -0 shasum -a 256 ) \
  > "$EXPORT_DIR/../anticipy-export-$(date -u +%Y%m%d).SHA256SUMS"

# encrypt before it leaves the machine
tar -C "$(dirname "$EXPORT_DIR")" -cf - "$(basename "$EXPORT_DIR")" \
  | gpg --symmetric --cipher-algo AES256 \
        --output "$HOME/anticipy-export-$(date -u +%Y%m%d).tar.gpg"
```

- **Two physical locations**, at least one offline. One copy is not a backup.
- The passphrase goes in the team password manager next to
  `ANTICIPY_VAULT_KEY_GCM`.
- **Retention:** keep the encrypted archive until the Cloudflare deployment has
  run without a data incident for at least as long as the old backup horizon
  (14 days), and until the owner says so.
- **Destruction:** when it goes, it goes properly — `rm -P` on macOS, `shred -u`
  on Linux — including the unencrypted `EXPORT_DIR` once the `.tar.gpg` is
  verified. This directory contains other people's transcripts.

---

## Step 11 — import

```sh
python3 migration/runbooks/import_d1.py "$EXPORT_DIR/pocketbase-final" \
  --database anticipy --emit-only            # look at the SQL first
python3 migration/runbooks/import_d1.py "$EXPORT_DIR/pocketbase-final" \
  --database anticipy --deep-reconcile
```

It verifies the export against its own manifest before writing a byte, refuses
to carry the vault without the re-wrap receipt, and exits **3** if the
destination row counts, id bounds or id sets do not match the source. It writes
`d1/plan.json` and `d1/reconcile.json`.

Two flags worth knowing:

- `--schema-file migration/d1/schema.sql` — use the schema authored for the
  Worker instead of the permissive landing schema `import_d1.py` generates.
  The generated one makes every non-`id` column nullable on purpose: its only
  job is that no byte is lost.
- `--oversize` — `agent_llm_audit`'s four `*_json` columns are capped at
  **1 000 000 characters** each
  (`backend/pb_migrations/1700000032_agent_audit_large_payloads.js:11`), and
  `jobs.params` / `jobs.trace` at 100 000
  (`1700000033_job_params_large.js:10`, `1700000034_jobs_trace_large.js:10`).
  Rows over `--max-row-bytes` are isolated into their own statements by
  default, listed in `d1/oversized.ndjson`. If D1 rejects one, `--oversize=truncate`
  stores a marker plus the original length and SHA-256, and `--oversize=skip`
  quarantines the row and excludes it from the expected count. Both are lossy;
  both are recorded.

---

## What does **not** come out through this door

Written down so nobody discovers it later:

| Thing | Why | What to do instead |
|---|---|---|
| `owners.password`, `owners.tokenKey` | PocketBase never serialises auth system fields (`1700000008_owners.js:19-23`) | read them from `data.db` inside the native archive, or have every user reset their password at cutover |
| `agents.agent_token` | declared `hidden: true` (`1700000026_agent_tokens.js:11`) | same — or re-pair every Chrome install |
| PocketBase settings (SMTP, S3 credentials, the backup schedule) | encrypted at rest by `PB_SETTINGS_ENCRYPTION_KEY` (`backend/start.sh:33`) and not exposed as records | they are configuration, not data. Re-enter them on the Cloudflare side from the password manager |
| `internal_passwords.secret_enc` | Go-side crypto (`internal_hq.pb.js:3079,3140`) | `reencrypt_vault.md` — **before decommissioning** |
| PocketBase realtime subscriptions | a protocol, not a store | a Worker-side equivalent is a design question, not an export question |
| The 55 hook routes, 6 `routerUse` middlewares and 2 `cronAdd` jobs in `backend/pb_hooks/` (8 795 lines) | behaviour, not data | out of scope here; they belong to the Worker rewrite. Note the two crons: `internal_hq_sweep` every 5 minutes (`internal_hq.pb.js:2139`) and `internal_hq_prune` at 04:17 daily (`:2642`) — something has to keep doing that |

---

## Rollback

Nothing in Steps 0–8 mutates production. The only writes are:

- PocketBase creating one extra native archive (Step 2, `PB_CREATE_BACKUP=1`),
- the worker writing one extra state zip to R2 (Step 4a),
- one temporary hook route and one env flag for the vault re-wrap
  (`reencrypt_vault.md` steps 1 and 6, both reversed in step 6).

To abandon the migration at any point before cutover: bring the `worker`
service back up, remove `ANTICIPY_VAULT_REWRAP` and `vault_rewrap.pb.js`, and
delete the export archive per Step 10. Production is unchanged.

After cutover, rollback is repointing clients at the Railway backend, which is
still holding the data it always had — provided nothing has been deleted. **Do
not delete the Railway services, the volumes, or any R2 object until the
Cloudflare deployment has been live and correct for a full backup horizon.**

---

## Unverified

- **Not executed against production.** Every script here was exercised
  end-to-end against a mock PocketBase (superuser auth, `/api/collections`
  enumeration, cursor and offset paging, `/api/files/` blob download,
  `/api/backups` create/list/download) and, for `import_d1.py`, against a real
  `sqlite3` standing in for D1 behind a `wrangler` shim: schema application,
  data load, byte-exact round trip of a value containing `'`, `;`, a newline
  and an em-dash, deep id-set reconciliation, and a deliberately induced
  mismatch that correctly exited 3. It has **not** run against the live
  instance. Expect to iterate on the first real run.
- **Row counts and database size** (~264 MB, 26 collections) are taken from the
  task brief and from `research/2026-08-31-database-resilience.md:80-88`
  (2026-09-01). Not re-measured.
- **Whether PocketBase 0.30.4 exempts superusers from hidden-field stripping**
  is not asserted anywhere. `export_pocketbase.sh` measures it per collection
  and records the answer in `manifest.gaps`.
- **`GET /api/backups/{key}` authentication.** PocketBase's download route
  is documented as taking a short-lived file token in the query string; whether
  this build also accepts an `Authorization` header was not verified, so the
  script tries the file token first and falls back to the header.
- **Whether `POST /api/backups` stages the zip on the volume before uploading
  to R2.** `research/2026-08-31-database-resilience.md:39-42` says archives are
  "written directly to the private R2 bucket", which suggests no local staging,
  but the volume has filled twice (`backend/start.sh:19-31`) and this was not
  re-tested. `PB_CREATE_BACKUP=0` skips creation and downloads the newest
  existing archive if you want to avoid the question entirely.
- **`skipTotal=1`** is sent on paging requests as an optimisation. If this
  build does not know the parameter it is ignored; nothing depends on it.
- **D1's per-statement, per-row and per-database limits** are not quoted
  anywhere in these artifacts, because I could not verify current numbers.
  `import_d1.py` uses conservative configurable ceilings (`--max-file-bytes`
  400 000, `--max-row-bytes` 900 000, `--rows-per-insert` 50) and reports
  anything that exceeds them rather than guessing what D1 will accept.
- **Railway CLI specifics** — `railway down`, `railway ssh`, and
  `railway variables --unset` flag spellings were not verified against the
  installed CLI version. Confirm with `--help`, or use the dashboard.
- **The nine fellowship collections** are named from
  `migration/d1/FELLOWSHIP-PRECEDENT.md` and `migration/d1/GAPS.md` (two of
  them also from `research/2026-08-31-founder-identity-reset.md:112-114`).
  Their schemas and row counts are unknown until the export runs against the
  live instance; that is precisely why `export_pocketbase.sh` enumerates from
  the server rather than from any list. Whether there are exactly nine is also
  unknown — the export will say.
- **Whether stopping the `worker` service is sufficient to quiet PocketBase
  writes** was not measured. The phone, extension and Mac app write directly,
  which is why Step 9 exists.
