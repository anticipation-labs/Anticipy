# What production serves that this repo cannot describe

`schema.sql` is a faithful reconstruction of the **26 collections the 58
migrations in `backend/pb_migrations/` create**. It is not a complete
description of the live PocketBase instance at
`backend-production-61e0a.up.railway.app`.

**Do not run the cutover with only `schema.sql`. It will silently leave tables
behind, and at least one of them is the one that pays people.**

---

## 1. The fellowship collections — CONFIRMED to exist, UNKNOWABLE FROM THIS REPO, and already staged on D1 by someone else

> ### UPDATE — read this before the rest of §1
>
> This section was written from the repo alone, which is the only thing this
> agent could read. A parallel audit then found the answer somewhere else, and
> it changes what the work is:
>
> **`migration/d1/FELLOWSHIP-PRECEDENT.md` in this same directory contains the
> real schema, read back from a live Cloudflare D1 database
> `anticipy-fellowship` (uuid `2f2abfae-9618-45f2-b53d-d302274bcb52`, created
> 2026-09-03T06:08Z) in account `114587b715e702461766369b01d42fc7`.** Somebody
> has already converted the fellowship to D1.
>
> What that changes:
>
> * **The bound is NINE tables, not two.** `fellows`, `fellow_applications`,
>   `fellow_submissions`, `fellow_payouts`, `fellow_conversions`,
>   `fellow_codes`, `fellow_clicks`, `fellow_progress`, `fellow_meter`. The
>   guess recorded below that a submissions collection exists was right and its
>   name is `fellow_submissions`; the guess that two collections was not a
>   bound was also right, and the real number is four and a half times larger.
> * **The type mapping is independently confirmed.** That database uses exactly
>   the conventions `schema.sql` arrived at from the migrations —
>   `text/select/relation/date/json -> TEXT NOT NULL DEFAULT ''`,
>   `number -> REAL NOT NULL DEFAULT 0`, `bool -> INTEGER NOT NULL DEFAULT 0`,
>   and partial-unique indexes preserved with their `WHERE col != ''`
>   predicate (e.g. `idx_fpayout_idem`, `idx_fsub_key`). Two conversions
>   reached the same answer separately.
>
> What it does **not** change, and why the command below is still the gate:
>
> * **Every one of those nine tables is EMPTY** (row counts verified at 0), and
>   `anticipyfellowship.com` still answers from Vercel fronting the Railway
>   PocketBase. It is a staged schema, not a cutover. **The rows — including
>   the payout ledger — still exist only in production PocketBase.**
> * **Nothing proves the staged schema matches the live collections.** It was
>   not generated from this repo (no fellowship migration exists here) and its
>   provenance is unknown. It could be ahead of production, behind it, or
>   hand-written. The superuser listing below is now a **reconciliation** step:
>   diff the live PocketBase collections against those nine tables before
>   trusting either.
> * **`fellow_payouts` carries money** (`amount_usd`, `commission_usd`,
>   `idempotency_key`). A schema mismatch there is not a migration defect, it
>   is a payment defect. Diff it column by column.
>
> The rest of §1 is left as written, because the evidence trail is still what
> justifies looking, and because the repo-only conclusion is still correct
> **about the repo**.

### The evidence, four independent sources

**(a) The website forwards five `/internal/fellows*` routes that nothing in
this repo answers.** `next.config.mjs:143-151`:

```js
{ source: "/internal/fellows",                      destination: `${FELLOWSHIP_ORIGIN}/internal/fellows` },
{ source: "/internal/fellows/remove",               destination: `${FELLOWSHIP_ORIGIN}/internal/fellows/remove` },
// These three existed in the backend and nowhere here, so past the site
// gate they 404'd at Vercel while answering 401 "wrong key" at the
// origin — alive, and unreachable through the domain. One of them is
// the route that pays a fellow.
{ source: "/internal/fellows/pay",                  destination: `${FELLOWSHIP_ORIGIN}/internal/fellows/pay` },
{ source: "/internal/fellows/submissions/remove",   destination: `${FELLOWSHIP_ORIGIN}/internal/fellows/submissions/remove` },
{ source: "/internal/fellows/submissions/release",  destination: `${FELLOWSHIP_ORIGIN}/internal/fellows/submissions/release` },
```

The comment at `next.config.mjs:145-148` is written by someone who had just
checked: *"These three existed in the backend and nowhere here… One of them is
the route that pays a fellow."* Routes were added to forward to handlers that
were **already live on the origin**.

**(b) There is no handler for any of them in `backend/pb_hooks/`.** All 55
`routerAdd` calls across the 20 hook files were enumerated; the complete set of
forwarded routes with **no** handler in this tree is:

```
/internal/fellows
/internal/fellows/pay
/internal/fellows/remove
/internal/fellows/submissions/release
/internal/fellows/submissions/remove
/internal/me/password          <- see §2
/internal/people/faces         <- see §2
/r/:code                       <- see §3
```

The only two occurrences of "fellow" as a *route* in `internal_hq.pb.js` are
`GET /fellows/hq` (`:4250`, which serves the HQ page itself on a prefix the
edge forwards) and the `routerUse` path check at `:4226`. There is no fellows
data route anywhere in this repo.

**(c) A production incident report names both collections as live business
records.** `research/2026-08-31-founder-identity-reset.md:111-114`:

> The supplied work emails still appear in the separate `internal_people`,
> `fellows`, and `fellow_applications` business records. Those are not Anticipy
> consumer accounts and do not reserve an app login; deleting them would erase
> unrelated company/fellowship records, so they were deliberately left in place.

That is a first-hand report of someone reading rows out of both tables on the
production instance.

**(d) A migration in this repo refers to "the fellowship migrations" as
something that exists.** `1700000048_hq_v2.js:157-158`:

> One proven constructor per type: TextField and NumberField **are used by the
> fellowship migrations**, and `new Field({type:"bool"})` is the shape
> `1700000029_event_intent.js` used to add a bool to a live collection.

There are no fellowship migrations in `backend/pb_migrations/`. The author of
`1700000048` had them in front of them; this tree does not.

### What is unknowable *from this repo*

**Everything about their schema.** Not the field names, not the types, not
which are required, not the indexes, not the API rules, not the row counts, and
not whether either is an auth collection. `schema.sql` deliberately contains no
`fellows` table and no `fellow_applications` table, and inventing one would be
worse than omitting it: a wrong guess imports real money-adjacent records into
wrongly typed columns and the error surfaces at payout time.

Two things were *weakly* inferable from the routes, and both have since been
confirmed by `FELLOWSHIP-PRECEDENT.md` — recorded here as written, so the
inference and its confirmation can be compared:

* `/internal/fellows/pay` implies at least a payout state (amount, currency,
  paid-at, and some payment reference) somewhere on `fellows` or a third table.
  — **Confirmed:** `fellow_payouts` (batch, state, `idempotency_key`,
  `amount_usd`, `commission_usd`) plus `fellow_conversions`.
* `/internal/fellows/submissions/{remove,release}` implies a **third**
  collection — submissions — with a released/held flag. Its name is not known.
  It might be `fellow_submissions`; that is a guess and is written here only so
  that nobody reads "two collections" as a bound. **The bound is unknown.**
  — **Confirmed:** `fellow_submissions` exists, and the bound was nine.

### Where the schema can come from: only a superuser listing of production

```sh
# ---------------------------------------------------------------------------
# 0. Inputs. Never echo these; never paste values into a file or a PR.
#    Names only:
#      PB_SUPERUSER_EMAIL / PB_SUPERUSER_PASSWORD   a PocketBase superuser
#      ANTICIPY_SERVICE_TOKEN                        the guard's shared secret
#    Create the superuser, if none is to hand, from inside the Railway
#    container (it is a local-only command and mints no network exposure):
#      railway run --service backend -- ./pocketbase superuser create <email> <password> --dir /pb_data
#    Delete it again when finished — research/2026-08-31-founder-identity-reset.md:102-103
#    records doing exactly that for the temporary `codex-*` superusers.
# ---------------------------------------------------------------------------
PB=https://backend-production-61e0a.up.railway.app

# 1. Authenticate as a superuser.
#    guard.pb.js:462 lets /api/collections/_superusers/* through untokened,
#    precisely so the dashboard can log in.
TOKEN=$(curl -sS -X POST "$PB/api/collections/_superusers/auth-with-password" \
  -H 'Content-Type: application/json' \
  --data-binary "{\"identity\":\"$PB_SUPERUSER_EMAIL\",\"password\":\"$PB_SUPERUSER_PASSWORD\"}" \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["token"])')

# 2. THE COMMAND. Every collection on the live instance, complete: fields,
#    types, required flags, indexes and all five API rules.
#    guard.pb.js:33 guards paths beginning "/api/collections/" — with the
#    trailing slash — so the bare collections endpoint is not gated. The
#    X-Anticipy-Token header is sent anyway so this still works if the guard
#    is ever tightened.
curl -sS "$PB/api/collections?perPage=500" \
  -H "Authorization: $TOKEN" \
  -H "X-Anticipy-Token: $ANTICIPY_SERVICE_TOKEN" \
  > production-collections.json

# 3. What this repo cannot account for.
python3 - <<'PY'
import json
known = {
 "pendants","events","jobs","agents","owner_profile","segments","owners",
 "password_resets","agent_llm_audit","agent_audit_sessions","purges","evidence",
 "internal_people","internal_tracks","internal_todos","internal_events",
 "internal_activity","internal_meter","internal_comments","internal_notifs",
 "internal_reminders","internal_sessions","internal_config",
 "internal_expenses","internal_passwords","internal_notes",
}
d = json.load(open("production-collections.json"))
items = d["items"] if isinstance(d, dict) else d
live = {c["name"]: c for c in items if not c.get("system")}
print("live non-system collections:", len(live))
print("\nMISSING FROM THIS REPO (no migration creates these):")
for n in sorted(set(live) - known):
    c = live[n]
    print(f"  {n}  type={c['type']}  fields={len(c.get('fields',[]))}  "
          f"rules={[c.get(k) for k in ('listRule','viewRule','createRule','updateRule','deleteRule')]}")
print("\nIN THIS REPO BUT NOT LIVE (dropped, or never deployed):")
for n in sorted(known - set(live)):
    print("  " + n)
print("\nFIELD DRIFT on shared collections:")
for n in sorted(known & set(live)):
    print(f"  {n}: " + ", ".join(f"{f['name']}:{f['type']}" for f in live[n].get("fields", [])))
PY
```

Step 3's third block is not optional garnish — it is how §2 below gets
answered at the same time, for free.

### Turning the answer into DDL

Once `production-collections.json` exists, emit the missing tables with the
same conventions `schema.sql` uses (`NOT NULL DEFAULT ''` / `0`, quoted
identifiers, indexes carried verbatim). Append the output to `schema.sql`
**after reading it** — this generator is a first draft, not a decision.

It has been exercised against a synthetic fixture shaped like PocketBase
0.23+ collection JSON (an `auth` collection with a hidden field and a unique
index, and a `base` collection with `select` and `file` fields); its output
applies cleanly to SQLite. It has **not** been run against real production
output, because no production credential exists in this environment. Read what
it emits before you run it.

```sh
python3 - <<'PY' >> fellows.generated.sql
import json
TYPE = {"text":"TEXT","email":"TEXT","url":"TEXT","editor":"TEXT","json":"TEXT",
        "date":"TEXT","autodate":"TEXT","relation":"TEXT","file":"TEXT",
        "select":"TEXT","password":"TEXT","number":"REAL","bool":"INTEGER",
        "geoPoint":"TEXT"}
d = json.load(open("production-collections.json"))
items = d["items"] if isinstance(d, dict) else d
for c in items:
    if c.get("system") or not c["name"].startswith("fellow"):
        continue
    print(f'\n-- {c["name"]}  (type={c["type"]}) '
          f'rules: list={c.get("listRule")!r} view={c.get("viewRule")!r} '
          f'create={c.get("createRule")!r} update={c.get("updateRule")!r} '
          f'delete={c.get("deleteRule")!r}')
    print(f'CREATE TABLE IF NOT EXISTS "{c["name"]}" (')
    # (defn, trailing-comment) pairs. The comma has to be placed BEFORE the
    # comment or the comment eats it and the next column line is a syntax
    # error -- caught by actually running this, not by reading it.
    cols = [('  "id" TEXT PRIMARY KEY NOT NULL', "")]
    if c["type"] == "auth":
        for n in ("email","tokenKey","password"):
            cols.append((f'  "{n}" TEXT NOT NULL DEFAULT \'\'', "  -- auth system field"))
        for n in ("emailVisibility","verified"):
            cols.append((f'  "{n}" INTEGER NOT NULL DEFAULT 0', "  -- auth system field"))
    for f in c.get("fields", []):
        if f["name"] == "id" or f.get("system"):
            continue
        sqlt = TYPE.get(f["type"], "TEXT")
        dflt = "0" if sqlt in ("REAL","INTEGER") else "''"
        chk = ""
        if f.get("required") and sqlt == "TEXT":
            chk = f' CHECK (length("{f["name"]}") > 0)'
        note = f'  -- {f["type"]}' + (" required" if f.get("required") else "")
        if f.get("hidden"):
            note += " HIDDEN: never SELECT * this column into a response"
        if f["type"] == "file":
            note += " (filename only; the bytes must move to R2)"
        cols.append((f'  "{f["name"]}" {sqlt} NOT NULL DEFAULT {dflt}{chk}', note))
    for i, (defn, note) in enumerate(cols):
        print(defn + ("," if i < len(cols) - 1 else "") + note)
    print(");")
    # Indexes come back as PocketBase wrote them, backticked. Valid SQLite.
    for idx in c.get("indexes", []):
        print(idx.rstrip(";") + ";")
PY
```

### Three rules for handling these tables during cutover

0. **Reconcile the staged D1 database against production before using either.**
   `FELLOWSHIP-PRECEDENT.md` is a schema with no rows; production PocketBase is
   rows with an unread schema. Neither alone is the answer. Diff them with the
   listing command above, column by column, and settle `fellow_payouts` first.
1. **Copy them before you understand them.** Row-level export
   (`/api/collections/fellows/records?perPage=500&page=N` with both headers)
   costs nothing and is reversible; a cutover that discovers on the far side
   that nobody exported the payout ledger is not.
2. **They are not Anticipy consumer data.** `research/2026-08-31-founder-identity-reset.md:112-114`
   is explicit that these are company/fellowship business records and that a
   privacy sweep aimed at `owners` deliberately left them alone. Whatever
   retention or deletion policy the product half gets, these need their own
   decision — do not fold them into the `purges` flow by accident.

---

## 2. `internal_people` may have columns no migration declares

Two HQ routes are forwarded by the website and have **no handler in this repo**:

```
/internal/me/password        next.config.mjs:142
/internal/people/faces       next.config.mjs:141
```

and the commit that added them (`bd5d6706`, *"Forward the welcome-screen
routes"*) describes them as *"The cast list (people/faces) and the
self-service password change (me/password)"* — i.e. features already live on
the origin.

Neither is expressible against `internal_people` as `schema.sql` declares it:

* `schema.sql` §2.1 has `code_hash` (SHA-256 of a **login code**,
  `1700000048_hq_v2.js:211`). It has **no password column**. A self-service
  *password* change implies either a second credential column or that
  `code_hash` was repurposed — unknown either way.
* There is **no avatar, photo, face or image column** on `internal_people` in
  any of the 58 migrations, and `1700000045_evidence.js:16-18` states flatly
  that there were *"zero `type: "file"` fields across all 44 prior
  migrations"*. A cast list of faces needs somewhere for an image to live.

**Consequence:** `schema.sql`'s `internal_people` may be a subset of the live
table, and an import written against it would silently drop those columns.
Step 3 of the command above ("FIELD DRIFT on shared collections") answers this
in the same request that answers §1. **Run it before writing the importer, not
after.**

The same caveat applies to any other collection: this repo's migrations are the
*applied* history only if nobody has ever edited a collection through the
PocketBase Admin UI, and nothing in the tree proves that.

---

## 3. Smaller unknowns, listed so they are not discovered late

| Unknown | Evidence | Why it might mean a table |
|---|---|---|
| `/r/:code` and `/c/:code` | `next.config.mjs:82-83`, commented *"A fellow's minted link"* | A referral/attribution code resolved server-side. Could be a column on `fellows`; could be its own table with click counts. Not in this repo. |
| `/internal/docs` | `backend/pb_public/internal.html` — a nav anchor, not a fetch | Links to a Docs surface that is neither served by `pb_hooks` nor forwarded by `next.config.mjs`. Probably an external link; verify before assuming. |
| Rows in collections whose *rules* were changed in the Admin UI | none — absence of evidence | `RULES.md` reconstructs rules from migrations. A UI edit leaves no migration. The `production-collections.json` from §1 is the authority; diff it against `RULES.md`. |
| The `internal.html` actually deployed | repo copy references 24 `/internal/*` routes; the backend serves 38 | The deployed SPA is a different build from `backend/pb_public/internal.html` (136 KB here). Whichever is newer determines which routes are truly live. |

---

## 4. Fallback if no superuser credential can be produced

The R2 backup bucket already holds nightly snapshots of the whole PocketBase
data directory — `1700000053_off_volume_backups.js:22-33` sets
`backups.cron = "0 9 * * *"`, `cronMaxKeep = 14`, and an S3 target whose bucket
is `anticipy-pocketbase-backups-production`
(`extension/tests/test_backup_volume_footprint.mjs:33`). A snapshot contains
`data.db`, and PocketBase 0.23+ keeps the collection definitions **in that
database**, as ordinary rows.

```sh
# Bucket-scoped credentials only. Env var names, never values:
#   ANTICIPY_BACKUP_S3_ENDPOINT / _ACCESS_KEY / _SECRET / _BUCKET / _REGION
export AWS_ACCESS_KEY_ID="$ANTICIPY_BACKUP_S3_ACCESS_KEY"
export AWS_SECRET_ACCESS_KEY="$ANTICIPY_BACKUP_S3_SECRET"

aws s3 ls "s3://$ANTICIPY_BACKUP_S3_BUCKET/" \
  --endpoint-url "$ANTICIPY_BACKUP_S3_ENDPOINT" | sort | tail -3

aws s3 cp "s3://$ANTICIPY_BACKUP_S3_BUCKET/<newest>.zip" ./pb-backup.zip \
  --endpoint-url "$ANTICIPY_BACKUP_S3_ENDPOINT"

unzip -q pb-backup.zip -d pb-backup && ls pb-backup

# Find the collections table, then read it. The table name is asserted below
# from PocketBase's v0.23+ layout and is UNVERIFIED — discover it rather than
# assume it:
sqlite3 pb-backup/data.db ".tables"
sqlite3 pb-backup/data.db ".schema _collections"

sqlite3 pb-backup/data.db \
  "SELECT name, type FROM _collections ORDER BY name;"

sqlite3 -json pb-backup/data.db \
  "SELECT name, type, fields, indexes, listRule, viewRule, createRule,
          updateRule, deleteRule
     FROM _collections
    WHERE name LIKE 'fellow%' OR name = 'internal_people';" \
  > production-collections-from-backup.json
```

Two warnings on this path:

* **The backup is a snapshot, not the live instance.** Anything changed since
  09:00 UTC is not in it. Good enough to *learn a schema*, not good enough to
  be the source of truth for a data cutover.
* **`_params` is encrypted, `_collections` is not.** `backend/start.sh:35`
  runs PocketBase with `--encryptionEnv=PB_SETTINGS_ENCRYPTION_KEY`, which
  encrypts the *settings* blob (including the S3 credentials it stores). The
  collection definitions are ordinary rows and read fine without the key. If
  `.schema _collections` shows encrypted-looking content, stop and use the
  superuser API path in §1 instead.

---

## Unverified

* **Whether the nine staged D1 tables in `FELLOWSHIP-PRECEDENT.md` match the
  live PocketBase collections.** Not verified by this agent — that file's own
  provenance note says the staged tables are empty and the site still serves
  from Railway. Treat it as a strong lead, not as production truth, until the
  diff in §1 has been run.
* **Whether `fellows` is a `base` or an `auth` collection in PocketBase.**
  `FELLOWSHIP-PRECEDENT.md` shows a `session_hash` column and an index on it,
  which reads like hand-rolled sessions rather than a PocketBase auth
  collection — but that is the D1 side, not the PocketBase side. If the live
  collection is `auth`, it carries `password`/`tokenKey`/`verified` like
  `owners` and inherits the same bcrypt-on-Workers problem recorded in
  `RULES.md`. Not checked.
* **`_collections` as the table name in PocketBase 0.30.4.** Asserted from the
  v0.23+ schema layout; the fallback in §4 discovers it with `.tables` rather
  than depending on the assertion.
* **Whether `GET /api/collections` really escapes `guard.pb.js`.** Read off
  `guard.pb.js:33` (`path.startsWith("/api/collections/")` — with the trailing
  slash) and not tested against the live instance. The command sends
  `X-Anticipy-Token` anyway so it works either way.
* **Whether the production instance's applied migration list matches this
  repo's 58 files.** Not checkable from here. `SELECT file FROM _migrations
  ORDER BY file;` against the backup in §4 answers it, and would also reveal
  the fellowship migrations by name — which is the cheapest possible way to
  learn what this tree is missing.
