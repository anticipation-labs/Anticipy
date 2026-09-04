# `brain/` on Cloudflare Containers

Companion artifact: **`migration/config/wrangler.brain.jsonc`** (schema-validated
against `node_modules/wrangler/config-schema.json`, wrangler 4.129.0).

Every claim about Cloudflare's container runtime below is sourced to a file that
is on this machine — `node_modules/wrangler/config-schema.json` for the config
surface, and `@cloudflare/containers@0.3.7`'s own published `dist/` for runtime
behaviour. Where I could not read a fact, it is in **§11 Unverified** and not
asserted anywhere else.

**This is blocked, and by exactly one thing.** `wrangler containers list` on
account `114587b715e702461766369b01d42fc7` answers *"Unauthorized: You do not
have access to Cloudflare Containers. Deploying containers requires the Workers
Paid plan"* (`migration/BLOCKERS.md`). Nothing here deploys until that is
resolved. It is written out in full so that the upgrade is the only remaining
step.

---

## 1. What runs today, exactly

| Fact | Source |
|---|---|
| Image is `python:3.11-slim`, deps `requests httpx tzdata boto3`, entrypoint `python -m brain.supervisor` | `brain/Dockerfile:2,12,14` |
| Supervisor discovers owners over HTTP, paged, 200/page | `brain/supervisor.py:54-58` → `backend/pb_hooks/worker_owners.pb.js:9-33` |
| Discovery cadence 15s | `brain/supervisor.py:30` |
| One **OS process per owner**: `Popen([sys.executable, "-m", "brain.worker"], env=…)` | `brain/supervisor.py:129` |
| Cap on running workers is 100, and it turns owners **away** rather than **evicting** them | `brain/supervisor.py:31,283-302` |
| Per-owner state dir `ANTICIPY_STATE_ROOT/<owner_ref>/` holding `memory.db` + `clock_state.json`, mode `0o700` | `brain/supervisor.py:84,95-100,122` |
| The child worker loop is `while True:` … `time.sleep(2)` | `brain/worker.py:4362`, `:4659`, `POLL_SECONDS = 2` at `:44` |
| Twilio inbound-webhook watchdog belongs to the **supervisor**, never a child | `brain/supervisor.py:110-114,334-336`; `WEBHOOK_CHECK_EVERY_SECONDS = 600` at `brain/worker.py:843` |
| Purge queue drains from the supervisor, `rmtree` on the owner's directory, marked only after the bytes are gone | `brain/supervisor.py:150-261` |
| Verified zipped state archives already upload to S3/R2 with **boto3** | `brain/state_backup.py:127-135,171-188` |

And the two things that make the port hard:

1. **`memory.db` is a real local SQLite file with an FTS5 virtual table and two
   triggers** — `brain/memory.py:198-208`, opened with `sqlite3.connect(str(path))`
   at `brain/memory.py:682`. 3,900 lines of `brain/memory.py` assume a
   synchronous local file handle.
2. **The worker keeps live signal in module globals**, not in any store:
   `MEETING_ARRIVALS`, `MEETING_ARMED`, `MEETING_LOW_SINCE`, `DIGEST_PENDING`,
   `MEETING_ARMED_AT` (`brain/worker.py:3074-3091`), `LAST_HEARD_AT`
   (`:3053`), and `_SENT_RECENTLY` (`:1074`). §6 is about what happens to those.

---

## 2. The shape on Cloudflare

```
              cron "* * * * *"                     service binding
                     │                          (site Worker, PB-shaped API)
                     ▼                                    ▲
        ┌────────────────────────┐                        │
        │  BrainSupervisor (DO)  │  ── D1: SELECT owners ─┼── anticipy-backend
        │  singleton             │  ── D1: purges queue   │
        └───────────┬────────────┘                        │
                    │ RPC: ensure(ref) / shutdown(ref)    │
                    ▼                                     │
        ┌────────────────────────┐                        │
        │  OwnerBrain (DO)       │   one per owner_ref    │
        │  extends Container     │                        │
        └───────────┬────────────┘                        │
                    │ ctx.container.start({ env })        │
                    ▼                                     │
        ┌────────────────────────────────────────────┐    │
        │  container: brain/Dockerfile               │    │
        │  container_entry.py                        │────┘
        │   ├─ pull memory.db + clock_state.json ◄── R2 anticipy-owner-state
        │   ├─ control HTTP server :8731             │
        │   ├─ snapshot thread ──────────────────►   R2 anticipy-owner-state
        │   ├─ daily verified zip (boto3) ───────►   R2 …-backups-production
        │   └─ child: python -m brain.worker  (UNCHANGED)
        └────────────────────────────────────────────┘
```

**`brain/supervisor.py` is not ported. It is replaced, function by function.**

| supervisor.py | Where it goes |
|---|---|
| `discover_owners()` `:38-73` | `BrainSupervisor.tick()`, one D1 `SELECT` — §3.3 |
| `child_environment()` `:76-115` | `OwnerBrain.envFor()` in TypeScript — §5.1 |
| `spawn_owner()` `:125-129` | `OwnerBrain.ensure()` → `this.start({ envVars })` |
| `stop_child()` `:132-140` | `OwnerBrain.shutdown()` → `this.stop("SIGTERM")` |
| `reconcile_children()` `:264-302` | `BrainSupervisor.tick()` — §3.3 |
| `purge_deleted_owners()` `:150-261` | `BrainSupervisor.purge()` — §4.6 |
| `ensure_inbound_webhook()` beat `:334-336` | the cron tick, once per fleet — §3.4 |
| `backup_state_to_s3()` beat `:358-368` | the container's own thread — §4.5 |

`brain/worker.py` and everything it imports — 22,614 lines — is **not touched**.
That is the whole point of the state design in §4.

---

## 3. The crux: containers sleep. Here is the answer.

### 3.1 The mechanism, read from the source

A container-backed DO is kept alive by a self-rearming alarm. The alarm handler
does three things in this order (`@cloudflare/containers@0.3.7`,
`dist/lib/container.js:1512-1588`):

```js
// dist/lib/container.js:1513-1517  — verbatim
// do not remove this, container DOs ALWAYS need an alarm right now.
// The only way for this DO to stop having alarms is:
//  1. The container is not running anymore.
//  2. Activity expired and it exits.
const prevAlarm = Date.now();
await this.ctx.storage.setAlarm(prevAlarm);
```

```js
// dist/lib/container.js:1566-1570  — verbatim
if (this.isActivityExpired()) {
    await this.onActivityExpired();
    // renewActivityTimeout makes sure we don't spam calls here
    this.renewActivityTimeout();
    return;
}
```

And the default `onActivityExpired` (`dist/lib/container.js:748-754`):

```js
async onActivityExpired() {
    console.log('Activity expired, signalling container to stop');
    if (!this.container.running) { return; }
    await this.stop();
}
```

### 3.2 So: **a persistent loop IS viable, and it is a one-line override**

The idle shutdown is *entirely* implemented by that default method. Override it
so it does not stop, and the alarm at `:1516` is still armed, `renewActivityTimeout()`
at `:1568` has already pushed the deadline out, and the next alarm falls through
to the sleep-and-rearm path at `:1573-1587`. The container never sleeps.

The package's own README says the same in prose (`README.md:141-142`):

> *"By default, this stops the container with a `SIGTERM`, but you can override
> this behaviour… However, if you don't stop the container here, the activity
> tracker will be renewed, and this lifecycle hook will be called again when the
> timer re-expires."*

This matters because **`brain/worker.py` has no inbound HTTP at all.** Its
liveness is a 2-second poll outward (`brain/worker.py:4659`). Nothing will ever
arrive to renew an activity timer, so under the default every owner's brain would
die 10 minutes after boot (`DEFAULT_SLEEP_AFTER = '10m'`,
`dist/lib/container.js:20`) and come back only when something happened to call it
— which nothing does.

**Do not** implement keep-alive by having the DO `fetch()` the container on a
timer. That works, but it makes liveness depend on a network round trip and it
counts against the DO's own request budget forever. The override is the supported
mechanism and it is free.

### 3.3 `BrainSupervisor` — discovery and reconcile

`brain/supervisor.py:54-58` calls `GET /worker/owners`, a route that exists
*only* because a shared-token request is not a PocketBase auth login
(`backend/pb_hooks/worker_owners.pb.js:3-8`). On Cloudflare that constraint
evaporates: the supervisor is inside the trust boundary and has a D1 binding.
**The route is not ported. Discovery becomes a query.**

```ts
// migration/workers/brain/src/index.ts  — BrainSupervisor.tick(), core
const { results } = await this.env.DB.prepare(
  `SELECT id, legacy_uuid FROM owners ORDER BY id`
).all<{ id: string; legacy_uuid: string }>();

// brain/supervisor.py:35 — the SAME guard, and it is load-bearing: this string
// is joined onto a state path and later deleted. A blank or hostile id must
// never reach either.
const SAFE_ID = /^[A-Za-z0-9_-]{8,64}$/;
const owners = results.filter(r => SAFE_ID.test(r.id));
```

Reconcile keeps `brain/supervisor.py:264-302`'s two properties exactly, because
both were bug fixes:

* **Everyone discovered is returned; the cap only bounds who is STARTED**
  (`supervisor.py:38-50`, `:279-291`). Truncating the list made the cap *evict*
  a live owner whose random id happened to sort low, and the eviction landed
  mid-write on `clock_state.json`.
* **Over capacity prints, loudly, every pass** (`supervisor.py:296-301`). Keep
  the log line; on Workers it lands in the observability stream that
  `wrangler.brain.jsonc` enables.

### 3.4 The Twilio watchdog: one caller, not N

`brain/supervisor.py:325-333` is a scar: on 2026-08-03 the number was repointed
at a stranger's Vercel app and every text went there for a day, because the role
had been baked into a child's environment at spawn and moved to a child already
started with `ANTICIPY_WEBHOOK_MANAGER=0`.

On Cloudflare the same failure has a new shape: N owner containers each with
credentials, each able to rewrite one shared Twilio number. So:

* `ANTICIPY_WEBHOOK_MANAGER=0` for every container (`wrangler.brain.jsonc` vars).
* `ANTICIPY_SUPERVISED=1` for every container, which is also what forces the
  empty `owner_phone` at `brain/worker.py:4264-4265`.
* The check runs **in the cron tick**, once per fleet, gated to the 10-minute
  beat of `WEBHOOK_CHECK_EVERY_SECONDS` (`brain/worker.py:843`).
* `ANTICIPY_TWILIO_WEBHOOK_URL` is **pinned** (`brain/worker.py:901` reads it),
  because a watchdog that derives the URL from its own host is a coin flip when
  there are a hundred hosts.

Porting `ensure_inbound_webhook()` (`brain/worker.py:843-1000`) to TypeScript is
~60 lines against `https://api.twilio.com/2010-04-01/Accounts/{sid}/IncomingPhoneNumbers`
(`brain/worker.py:937,991`). **It is the one piece of Python that must be
rewritten**, and it must be rewritten rather than left in a container, because
"exactly one process may check" is not a property any owner container has.

### 3.5 If the owner will not pay for always-on

Then the honest alternative, and what it costs:

**Cron Trigger + Durable Object, wake-on-event.** `sleepAfter = "5m"`, default
`onActivityExpired`. The site Worker, on receiving a transcript or an SMS
webhook, calls `env.OWNER_BRAIN.getByName(ref).ensure()`; a `*/5` cron drives the
clock lane. The container boots, drains, idles out.

What breaks, named precisely:

| Behaviour | Why it breaks |
|---|---|
| **The meeting posture** | Arming needs 10 lines inside 180s *in one process* (`brain/worker.py:3092-3093`, `MEETING_ARRIVALS` at `:3076`). A process that restarts between lines can never arm, so every long call gets interrupted — the exact failure the posture was built from (`:3058-3065`). |
| **The parked digest** | `DIGEST_PENDING` is a module global (`brain/worker.py:3086`). A composed digest that could not send is lost on shutdown, silently. |
| **The duplicate-SMS guard** | `_SENT_RECENTLY` (`brain/worker.py:1074-1076`) exists *specifically* to stop the "fifteen texts in sixty-five seconds" loop during a backend write outage (`:1060-1068`). It is process-local and empty on every wake. |
| **Live-conversation suppression** | `LAST_HEARD_AT` / `LIVE_CONVERSATION_S` (`brain/worker.py:3053-3057`) — she asks questions into a sentence that has not finished. |
| **Latency** | Container cold start + Python import + the R2 pull of `memory.db`, versus a 2-second poll. |

Three of those five are *outbound texts to a person's phone*. This is not a
performance trade, it is a behaviour trade, and the failure mode is "she texts
you fifteen times" or "she interrupts your meeting." **Recommendation: pay for
always-on.** If the wake-on-event shape is chosen anyway, the five globals above
must first be moved into `memory.db` — that is a real change to `brain/worker.py`
and it should be scoped before, not during, the migration.

---

## 4. Per-owner state: the ephemeral-disk problem

### 4.1 The decision

**R2 is the durable home. The container's local disk is a working copy. The
per-owner Durable Object is the single-writer lease. `brain/memory.py` is not
touched.**

Keys in bucket `anticipy-owner-state`:

```
owners/<owner_ref>/memory.db          ← SQLite, snapshotted through the online backup API
owners/<owner_ref>/clock_state.json
```

### 4.2 Why not the alternatives

**D1, one database per owner.** Rejected on three counts, any one of which is
fatal:

1. `brain/memory.py:198-208` creates `episodes_fts` as `CREATE VIRTUAL TABLE …
   USING fts5` with two triggers. D1 does not accept FTS5 virtual tables *(see
   §11 — I did not run the probe against their D1; the command is there)*. The
   fallback path exists (`brain/memory.py:194-196`: "if this SQLite build lacks
   FTS5, the search falls back to LIKE") — so recall degrades from indexed
   full-text to a table scan, on the store that IS the product.
2. D1 speaks HTTP, not DB-API. Every one of `brain/memory.py`'s synchronous
   `self.db.execute(...)` calls becomes an `await`. That is a rewrite of a
   150 KB file whose correctness is the assistant's memory.
3. Database count. Onboarding an owner would mean provisioning a D1 database
   (a control-plane call, not a data write), and per-account database limits
   apply *(§11)*.

**Durable Object SQLite storage.** Same rewrite as (2), plus the Python process
cannot address DO SQL at all — it would need an HTTP shim through the DO for
every query, on the hot path of a 2-second loop.

**R2 with no local copy** (mount-like access). SQLite over object storage is not
a thing; there is no page-level protocol.

### 4.3 How the working copy is kept honest

`brain/state_backup.py` already contains every primitive needed, and none of it
is Railway-specific:

* `_snapshot_sqlite()` `:75-81` copies through SQLite's **online backup API** and
  runs `PRAGMA quick_check`, so a snapshot is never a half-written page —
  precisely the reason a byte-for-byte copy was rejected (`:5-7`).
* `state_files()` `:55-64` refuses symlinks out of the state root.
* `_sha256()` `:67-72` and the post-upload `head_object` verification at
  `:182-187` mean a snapshot that did not land is an exception, not a silence.

`brain/container_entry.py` (new, §8) wraps those:

1. **On boot** — `GET` the two R2 keys into `/data/owners/<ref>/`. Absent keys
   are a brand-new owner, not an error (`brain/memory.py` creates the schema
   with `CREATE TABLE IF NOT EXISTS`).
2. **Every `ANTICIPY_STATE_SNAPSHOT_SECONDS`** (60) — if `memory.db`'s mtime
   moved, snapshot and `PUT`.
3. **On `SIGTERM`** — stop the child, final snapshot, `PUT`, exit. This is what
   `rollout_active_grace_period: 3600` in the wrangler config exists to protect.

### 4.4 The loss window, stated plainly

**Up to 60 seconds of episodes on an ungraceful kill.** SIGTERM is graceful and
loses nothing. A hardware-level loss of the container between snapshots loses
whatever was heard in that minute.

That is strictly better than today in one respect and worse in another, and both
should be said: today a crash loses *nothing* (the file is on a persistent
volume), but today a volume loss loses *everything* between nightly archives
(`ANTICIPY_STATE_BACKUP_SECONDS = 86400`, `brain/supervisor.py:34`). The new
shape trades a 24-hour disaster window for a 60-second crash window.

If 60 seconds is judged too much: the upgrade is to write each `hear()` episode
to the owner's DO SQLite as an append-only journal before it goes to `memory.db`,
and replay the journal after a restore. That is a real change to
`brain/memory.py`'s write path and it is **not** in scope here. Do not pretend
the 60s window is zero.

### 4.5 The verified archive keeps working, unchanged

`brain/state_backup.backup_state_to_s3()` is already boto3-against-S3 with a
configurable `endpoint_url` (`:127-135`). R2 is S3-compatible. **Confirmed:
reuse it as-is**, moved from the supervisor's beat (`brain/supervisor.py:358-368`)
into the container's own thread, scoped to that owner's directory.

Four environment variables, unchanged in name (`brain/state_backup.py:22-27`):
`ANTICIPY_BACKUP_S3_BUCKET`, `_ENDPOINT`, `_ACCESS_KEY`, `_SECRET`. The endpoint
becomes `https://<account_id>.r2.cloudflarestorage.com`; the credentials become
an R2 API token's access key pair.

**Two things to test before trusting it**, because they have plausibly never run
against R2 (`migration/BLOCKERS.md` records that R2 is not enabled on this
account at all):

* `:173` passes `ServerSideEncryption: "AES256"` on upload. Verify R2 accepts
  that header rather than rejecting the `PutObject` *(§11)*.
* `:177-179` sets user metadata `sha256` / `format` / `file-count` and `:186`
  re-reads it lowercase from `head_object`. Verify R2 round-trips user metadata
  with the same casing behaviour *(§11)*.

Both fail loudly if wrong — `:185` and `:187` raise — which is the correct
posture. Run one upload before the cutover, not during it.

### 4.6 Purge: `rmtree` becomes an R2 prefix delete

`brain/supervisor.py:150-261` is the most carefully-reasoned function in the
file and every one of its guards must survive:

| Guard | `supervisor.py` | On Cloudflare |
|---|---|---|
| Only purge a ref discovery says is **gone** | `:196-198` | same `live_refs` set, from the SAME D1 snapshot the reconcile just used |
| One snapshot for both decisions | `:338-354` | one `SELECT`, passed to both `reconcile()` and `purge()` |
| `_SAFE_ID` before joining onto the state root | `:202-204` | `SAFE_ID.test(ref)` before building the R2 prefix |
| Also purge the **legacy** paths for the founder | `:206-222` | the legacy owner has no separate R2 prefix; see the migration in §4.7 — after it, `owners/<ref>/` is the only home, and this branch is retired **only once that is verified per-owner** |
| Symlink at the target is an integrity signal, refuse | `:231-234` | not expressible in R2; the equivalent is that a `list` under the prefix returns only keys we wrote |
| Mark `memory_purged` **only after** the bytes are gone | `:248-260` | `list` → `delete` → re-`list` returns empty → `UPDATE purges` |

The last row is the one that turns a privacy promise into a lie if it is fumbled
(`:176-178`). Re-list before marking.

### 4.7 Migrating the owners who already exist

The archive is the migration path — it already contains exactly the right thing.
`backup_state_to_s3(STATE_VOLUME_ROOT)` (`brain/supervisor.py:360`, with
`STATE_VOLUME_ROOT` defaulting to `/data` at `:33`) zips paths *relative to
`/data`*, so the entries are already `owners/<ref>/memory.db`.

```bash
#!/usr/bin/env bash
# migration/runbooks/brain_state_to_r2.sh
# Move every owner's durable mind from the Railway volume into R2.
# Run with the Railway supervisor STOPPED. Read §4.7 of migration/workers/BRAIN.md.
set -euo pipefail

: "${R2_ENDPOINT:?}" "${R2_ACCESS_KEY_ID:?}" "${R2_SECRET_ACCESS_KEY:?}"
ARCHIVE_BUCKET="${ARCHIVE_BUCKET:?the bucket ANTICIPY_BACKUP_S3_BUCKET names}"
LIVE_BUCKET="${LIVE_BUCKET:-anticipy-owner-state}"
WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT

export AWS_ACCESS_KEY_ID="$R2_ACCESS_KEY_ID"
export AWS_SECRET_ACCESS_KEY="$R2_SECRET_ACCESS_KEY"
export AWS_DEFAULT_REGION=auto
S3="aws s3 --endpoint-url $R2_ENDPOINT"

# 1. THE FRESHEST ARCHIVE, not the newest-looking one. Keys are
#    worker/state-YYYYMMDDTHHMMSSZ.zip (brain/state_backup.py:163), so
#    lexicographic order IS chronological order. That is why the prune at
#    state_backup.py:144 sorts by key.
KEY="$($S3 ls "s3://$ARCHIVE_BUCKET/worker/" | awk '{print $4}' | grep '\.zip$' | sort | tail -1)"
test -n "$KEY" || { echo "FATAL: no state archive under worker/ in $ARCHIVE_BUCKET"; exit 1; }
echo "using worker/$KEY"
$S3 cp "s3://$ARCHIVE_BUCKET/worker/$KEY" "$WORK/state.zip"

# 2. VERIFY IT BEFORE TRUSTING IT. The manifest carries a sha256 per file
#    (state_backup.py:106-110) and nothing has ever checked it on the way back.
unzip -q "$WORK/state.zip" -d "$WORK/x"
python3 - "$WORK/x" <<'PY'
import hashlib, json, pathlib, sys
root = pathlib.Path(sys.argv[1])
manifest = json.loads((root / "manifest.json").read_text())
bad = []
for f in manifest["files"]:
    p = root / f["path"]
    if not p.is_file():
        bad.append(f"{f['path']}: missing"); continue
    d = hashlib.sha256(p.read_bytes()).hexdigest()
    if d != f["sha256"]:
        bad.append(f"{f['path']}: sha256 {d} != {f['sha256']}")
if bad:
    print("ARCHIVE IS NOT INTACT — DO NOT CUT OVER"); [print(" ", b) for b in bad]; sys.exit(1)
print(f"archive verified: {len(manifest['files'])} files, created {manifest['created_at']}")
PY

# 3. EXPLODE IT INTO PER-OWNER KEYS. The zip is already rooted at
#    owners/<ref>/… because state_backup zipped ANTICIPY_STATE_VOLUME_ROOT
#    (/data), one level above ANTICIPY_STATE_ROOT (/data/owners).
test -d "$WORK/x/owners" || { echo "FATAL: archive has no owners/ — was ANTICIPY_STATE_VOLUME_ROOT set to /data?"; exit 1; }
$S3 sync "$WORK/x/owners/" "s3://$LIVE_BUCKET/owners/" --exclude '*' --include '*/memory.db' --include '*/clock_state.json'

# 4. COUNT BOTH SIDES. A migration that moved 6 of 7 minds and said nothing is
#    the failure mode; the seventh person just stops being remembered.
LOCAL=$(find "$WORK/x/owners" -mindepth 1 -maxdepth 1 -type d | wc -l | tr -d ' ')
REMOTE=$($S3 ls "s3://$LIVE_BUCKET/owners/" | grep -c 'PRE' || true)
echo "owners in archive: $LOCAL   prefixes in R2: $REMOTE"
test "$LOCAL" = "$REMOTE" || { echo "MISMATCH — investigate before cutting over"; exit 1; }
echo OK
```

**The founder is a special case and it will bite you.** `brain/supervisor.py:86-100`
deliberately keeps the pre-migration founder on the *old* `ANTICIPY_MEMORY_DB` /
`ANTICIPY_CLOCK_STATE` paths whenever `legacy_uuid == ANTICIPY_OWNER_ID`. For
that one account there is **no `<state root>/<ref>/` directory**, so step 3 above
will not carry it. Before running the script, read the live values of those two
variables off the Railway service and copy those two files to
`owners/<their_ref>/memory.db` and `owners/<their_ref>/clock_state.json` by hand.
`supervisor.py:206-222` is a comment explaining that exactly this oversight once
marked a purge complete over a memory database still fully on disk.

---

## 5. Every environment variable `brain/` reads

Collected by grepping `os.environ` / `os.getenv` / `values.get` across `brain/*.py`.
**Scope** says who sets it: `var` = plaintext in `wrangler.brain.jsonc`; `secret`
= `wrangler secret put`; `per-owner` = computed by `OwnerBrain` at container
start; `derived` = set by `container_entry.py`.

### 5.1 Per-owner — computed, never inherited

| Variable | Read at | Value |
|---|---|---|
| `ANTICIPY_OWNER_REF` | `worker.py:50`, `:3576` | the D1 `owners.id` |
| `ANTICIPY_OWNER_ID` | `worker.py:51`, `supervisor.py:88` | `legacy_uuid` or, empty, the ref (`supervisor.py:94`) |
| `ANTICIPY_MEMORY_DB` | `worker.py:4257` | `/data/owners/<ref>/memory.db` |
| `ANTICIPY_CLOCK_STATE` | `worker.py:58` | `/data/owners/<ref>/clock_state.json` |
| `ANTICIPY_OWNER_PHONE` | `worker.py:4265` | **never set.** `supervisor.py:107-108` `pop()`s it, and `worker.py:4264` blanks it again when `ANTICIPY_SUPERVISED=1`. Two layers, because a missing `pop()` once sent one owner's texts to another's phone (`supervisor.py:101-106`). Do not add it to `vars`. |
| `ANTICIPY_STATE_GENERATION` | new, `container_entry.py` | monotonic counter from the DO; the zombie-writer guard (§8) |

### 5.2 Secrets — `wrangler secret put --config migration/config/wrangler.brain.jsonc <NAME>`

| Secret | Read at | What it is |
|---|---|---|
| `ANTICIPY_SERVICE_TOKEN` | `brain/pb.py:24` | the only credential the brain holds; sent as `X-Anticipy-Token` (`pb.py:26`) |
| `OPENROUTER_API_KEY` | `brain/llm.py:218` | primary model, `https://openrouter.ai/api/v1/chat/completions` (`llm.py:21`) |
| `GEMINI_API_KEY` | `brain/llm.py:214` | fallback, `generativelanguage.googleapis.com` (`llm.py:22`) |
| `BRAVE_API_KEY` | `worker.py:1737`, `anticipy_core.py:3630,3919` | also **gates the research lane existing at all** at `anticipy_core.py:3919` |
| `TAVILY_API_KEY` | `worker.py:1738`, `:1838` | second search provider |
| `TWILIO_ACCOUNT_SID` | `voice_arm.py:58,163`, `worker.py:937` | |
| `TWILIO_AUTH_TOKEN` | `voice_arm.py:58,164` | |
| `TWILIO_API_KEY_SID` | `voice_arm.py:161` | optional; API-key auth instead of the auth token |
| `TWILIO_API_KEY_SECRET` | `voice_arm.py:162` | optional, pairs with the above |
| `TWILIO_PHONE_NUMBER` | `voice_arm.py:358` (`os.environ[...]`, raises if absent), `worker.py:922` | |
| `ANTICIPY_BACKUP_S3_ACCESS_KEY` | `state_backup.py:49` | R2 API token key id |
| `ANTICIPY_BACKUP_S3_SECRET` | `state_backup.py:50` | R2 API token secret |
| `ANTICIPY_BACKUP_S3_BUCKET` | `state_backup.py:48` | secret only because it must stay in lockstep with the credential pair; `state_backup.py:43-45` makes a *partial* configuration a hard error, never an opt-out |
| `ANTICIPY_BACKUP_S3_ENDPOINT` | `state_backup.py:48` | `https://<account_id>.r2.cloudflarestorage.com` |

### 5.3 Plain vars — all present in `wrangler.brain.jsonc`

| Variable | Read at | Default in code |
|---|---|---|
| `ANTICIPY_PB` | `worker.py:43`, `supervisor.py:29`, `evidence.py:75`, `voice_arm.py:325` | `http://127.0.0.1:8090` |
| `ANTICIPY_STATE_ROOT` | `supervisor.py:32,84,147` | `/data/owners` |
| `ANTICIPY_STATE_VOLUME_ROOT` | `supervisor.py:33` | `/data` |
| `ANTICIPY_TZ` | `llm.py:47`, `worker.py:56` | `America/Vancouver` |
| `ANTICIPY_MODEL` | `llm.py:24` | `deepseek/deepseek-v3.2` |
| `ANTICIPY_GEMINI_MODEL` | `llm.py:220` | `gemini-2.5-flash` |
| `ANTICIPY_MAX_OWNER_WORKERS` | `supervisor.py:31` | `100` |
| `ANTICIPY_OWNER_DISCOVERY_SECONDS` | `supervisor.py:30` | `15` |
| `ANTICIPY_STATE_BACKUP_SECONDS` | `supervisor.py:34` | `86400` |
| `ANTICIPY_STATE_BACKUP_PREFIX` | `state_backup.py:162` | `worker/` |
| `ANTICIPY_STATE_BACKUP_KEEP` | `state_backup.py:164` | `14` |
| `ANTICIPY_BACKUP_REQUIRED` | `state_backup.py:40` | unset; **set to `1`** |
| `ANTICIPY_BACKUP_S3_REGION` | `state_backup.py:51` | `auto` |
| `ANTICIPY_SEGMENTS` | `worker.py:4305` | `1`. Note `:4300-4304`: this is **off only when explicitly off**; a path here reads as on. |
| `ANTICIPY_SUPERVISED` | `worker.py:4264`, `:4416` | **`1`**, always |
| `ANTICIPY_WEBHOOK_MANAGER` | `worker.py:4417` | **`0`**, always — §3.4 |
| `ANTICIPY_TWILIO_WEBHOOK_URL` | `worker.py:901` | pin it — §3.4 |
| `ANTICIPY_STATE_R2_PREFIX` | new, `container_entry.py` | `owners` |
| `ANTICIPY_STATE_SNAPSHOT_SECONDS` | new, `container_entry.py` | `60` |

### 5.4 Deliberately unset

| Variable | Read at | Why |
|---|---|---|
| `ANTICIPY_AUX_MODEL` | `llm.py:39` | empty means "no aux model"; leave empty until somebody chooses one |
| `ANTICIPY_STRONG_MODEL` | `orchestrator.py:406` | same |
| `ANTICIPY_LINKS` | `worker.py:3622` | opt-in feature flag |
| `ANTICIPY_LLM_LEDGER` | `llm.py:164` | a local file path; the container disk is ephemeral, so a ledger written there is lost. If it is wanted, send it to R2 or drop the feature — **do not** point it at `/data` and believe it persists. |
| `ANTICIPY_SEGMENT_TRIAGE` | `sorter.py:524` | opt-in |
| `TWILIO_FROM` | `worker.py:922` | legacy alias for `TWILIO_PHONE_NUMBER`; set one, not both |
| `TWILIO_MOCK` | `voice_arm.py:196` | test-only |
| `TWILIO_API_BASE` | `voice_arm.py:120` | test-only. **`voice_arm.py:283-295` treats a loopback value as a reason to refuse to send** — never set it in production. |
| `PYTEST_CURRENT_TEST` | (pytest) | not ours |

---

## 6. What actually changes about the brain's behaviour

| | Today | On Containers |
|---|---|---|
| Owner isolation | one OS process (`supervisor.py:129`) | one container + one DO per owner — **stronger**: separate kernels, not separate PIDs |
| Job poll | 2s (`worker.py:44,4659`) | **unchanged**, inside the container |
| Discovery | 15s (`supervisor.py:30`) | 60s (cron floor) |
| Owner crash blast radius | one child; parent respawns next pass | one container; `onStop` restarts it — **unchanged in effect** |
| `memory.db` durability | continuous, persistent volume | ≤60s window (§4.4) |
| `memory.db` disaster recovery | nightly zip, one shared volume | per-owner R2 object, versionable, plus the nightly zip |
| Twilio watchdog | supervisor process | cron tick (§3.4) |
| Fleet cap | soft, logs "AT CAPACITY" | soft **and** hard (`max_instances`); keep both equal |
| Cost | one Railway container + one volume | billed per running container-second (§9) |

---

## 7. Egress

### 7.1 The subrequest limit does not apply where you think

`brain/`'s outbound calls are made by Python `requests`/`httpx` **inside a
Linux container**. They are not `fetch()` from workerd and **do not count
against a Worker's subrequest budget.** The container has ordinary internet
access: `enableInternet = true` is the class default
(`@cloudflare/containers` `dist/lib/container.js:325`).

The Worker-side subrequest budget applies only to `BrainSupervisor` and
`OwnerBrain` themselves, and their per-tick work is: one D1 query, one D1 purge
query, up to N `getByName(...).ensure()` DO calls, and (once per 10 minutes) the
Twilio watchdog fetch. `wrangler.brain.jsonc` sets no `limits` override because
none is needed at N=100. Revisit at N≈900 *(§11 — I have not verified the exact
current subrequest ceiling for a DO invocation; the `limits.subrequests` knob
exists in the config schema and is the place to raise it)*.

Destinations, all verified in source:

| Host | From | Volume |
|---|---|---|
| `openrouter.ai` | `brain/llm.py:21`, 60s timeout at `:327` | every reasoning turn |
| `generativelanguage.googleapis.com` | `brain/llm.py:22`, `:387` | fallback |
| `api.twilio.com` | `brain/voice_arm.py:120`, `brain/worker.py:937,991` | every text + the watchdog |
| `api.search.brave.com` | `brain/research.py:29` | research lane |
| `api.tavily.com` | `brain/research.py:30` | research lane |
| `<account>.r2.cloudflarestorage.com` | `brain/state_backup.py:129` | snapshots + daily zip |
| `ANTICIPY_PB` | `brain/pb.py:36-51` | every 2 seconds |
| **arbitrary** | `brain/research.py` open-web fetches | research lane |

### 7.2 Two things worth doing, and one that cannot be done

**Do: keep the SSRF guard.** `brain/research.py:948-950` blocks
`http://2130706433`, `0x7f000001`, `2852039166` and friends, and `:189` calls out
a `302 Location: http://169.254.169.254` redirect. A container has no cloud
metadata endpoint to steal, but the guard also stops the research lane being
pointed at internal addresses, and it costs nothing to keep.

**Do: consider routing `ANTICIPY_PB` over the service binding.** The `Container`
class supports intercepting outbound traffic by hostname and handling it in the
Worker (`dist/lib/container.d.ts:49-58`, `setOutboundByHost` at `:98`). That lets
the container keep calling `http://backend.internal` with plain `requests` while
the bytes never leave Cloudflare, and `ANTICIPY_SERVICE_TOKEN` never crosses the
public internet:

```ts
export class OwnerBrain extends Container<Env> {
  static outboundByHost = {
    "backend.internal": (req: Request, env: Env) => env.BACKEND.fetch(req),
  };
}
```

The API surface is verified from the package's own types. **Whether it behaves
correctly for a 2-second poll at N=100 is not** — treat it as the second step,
after the public-URL version is proven working.

**Cannot: lock egress to an allowlist.** `allowedHosts` / `deniedHosts` exist
(`dist/lib/container.js:330-333`) and would be the right control for a
model-calling worker. The research lane fetches arbitrary open-web URLs by
design, so an allowlist would silently break it. Use `deniedHosts` for known-bad
destinations instead, and leave the allowlist alone.

---

## 8. The two new files

Neither exists yet. Both are complete; write them at the paths named.

### 8.1 `migration/workers/brain/src/index.ts`

```ts
// The Worker half of the brain. Replaces brain/supervisor.py's process
// management with Durable Objects, and nothing else: brain/worker.py and its
// 22,614 lines run unchanged inside the container.
import { Container } from "@cloudflare/containers";
import { DurableObject } from "cloudflare:workers";

export interface Env {
  OWNER_BRAIN: DurableObjectNamespace<OwnerBrain>;
  BRAIN_SUPERVISOR: DurableObjectNamespace<BrainSupervisor>;
  DB: D1Database;
  OWNER_STATE: R2Bucket;
  STATE_ARCHIVE: R2Bucket;
  BACKEND: Fetcher;

  // vars (migration/config/wrangler.brain.jsonc)
  ANTICIPY_PB: string;
  ANTICIPY_STATE_ROOT: string;
  ANTICIPY_STATE_VOLUME_ROOT: string;
  ANTICIPY_STATE_R2_PREFIX: string;
  ANTICIPY_STATE_SNAPSHOT_SECONDS: string;
  ANTICIPY_STATE_BACKUP_SECONDS: string;
  ANTICIPY_STATE_BACKUP_PREFIX: string;
  ANTICIPY_STATE_BACKUP_KEEP: string;
  ANTICIPY_BACKUP_REQUIRED: string;
  ANTICIPY_BACKUP_S3_REGION: string;
  ANTICIPY_MAX_OWNER_WORKERS: string;
  ANTICIPY_OWNER_DISCOVERY_SECONDS: string;
  ANTICIPY_TZ: string;
  ANTICIPY_MODEL: string;
  ANTICIPY_GEMINI_MODEL: string;
  ANTICIPY_SEGMENTS: string;
  ANTICIPY_SUPERVISED: string;
  ANTICIPY_WEBHOOK_MANAGER: string;
  ANTICIPY_TWILIO_WEBHOOK_URL: string;

  // secrets (wrangler secret put) — §5.2
  ANTICIPY_SERVICE_TOKEN: string;
  OPENROUTER_API_KEY: string;
  GEMINI_API_KEY: string;
  BRAVE_API_KEY: string;
  TAVILY_API_KEY: string;
  TWILIO_ACCOUNT_SID: string;
  TWILIO_AUTH_TOKEN: string;
  TWILIO_API_KEY_SID?: string;
  TWILIO_API_KEY_SECRET?: string;
  TWILIO_PHONE_NUMBER: string;
  ANTICIPY_BACKUP_S3_BUCKET: string;
  ANTICIPY_BACKUP_S3_ENDPOINT: string;
  ANTICIPY_BACKUP_S3_ACCESS_KEY: string;
  ANTICIPY_BACKUP_S3_SECRET: string;
}

// brain/supervisor.py:35. Load-bearing: this string is joined onto a state
// path and later deleted. A blank or hostile id must never reach either.
const SAFE_ID = /^[A-Za-z0-9_-]{8,64}$/;

type Owner = { id: string; legacy_uuid: string };

// The port container_entry.py's control server listens on. It exists only so
// the DO can health-check and demand a flush; brain/worker.py has no HTTP.
const CONTROL_PORT = 8731;

/** One owner's brain. One container. One Durable Object. */
export class OwnerBrain extends Container<Env> {
  defaultPort = CONTROL_PORT;
  requiredPorts = [CONTROL_PORT];

  // A backstop, not the mechanism. onActivityExpired() below is what actually
  // keeps this alive; sleepAfter only decides how often that hook is asked.
  sleepAfter = "1h";

  enableInternet = true;

  /**
   * THE ONE OVERRIDE THAT MAKES A POLL LOOP POSSIBLE ON CONTAINERS.
   *
   * The default (@cloudflare/containers dist/lib/container.js:748-754) sends
   * SIGTERM when the activity timer expires. Activity means inbound requests,
   * and brain/worker.py has NO inbound anything — its liveness is a 2-second
   * outward poll (brain/worker.py:4659). Under the default every owner's brain
   * would be killed an hour after boot and nothing would ever wake it.
   *
   * Not stopping here is supported, not a trick: the alarm is re-armed at the
   * top of every alarm (dist/lib/container.js:1516) and renewActivityTimeout()
   * runs immediately after this returns (:1568). README.md:141-142 documents
   * exactly this. See migration/workers/BRAIN.md §3.2.
   */
  override async onActivityExpired(): Promise<void> {
    const ref = await this.ctx.storage.get<string>("owner_ref");
    console.log(`brain stays up · owner=${ref ?? "?"} (activity timer ignored by design)`);
    // Deliberately no this.stop(). Deliberately no super call.
  }

  override onStart(): void {
    void this.ctx.storage.get<string>("owner_ref").then((ref) =>
      console.log(`owner worker started · owner=${ref ?? "?"}`)
    );
  }

  /**
   * brain/supervisor.py:274-278 — a child that has exited is dropped from the
   * table and respawned on the next pass. Here the DO outlives the container,
   * so the restart is immediate rather than up-to-15-seconds later.
   *
   * A container that exits 0 because it was asked to (shutdown()) must NOT be
   * restarted, or a deleted account's brain resurrects itself forever.
   */
  override async onStop(params: { exitCode: number; reason: string }): Promise<void> {
    const stopping = await this.ctx.storage.get<boolean>("stopping");
    const ref = (await this.ctx.storage.get<string>("owner_ref")) ?? "?";
    console.log(`owner container stopped · owner=${ref} · exit=${params.exitCode} · ${params.reason}`);
    if (stopping) return;
    const owner = await this.ctx.storage.get<Owner>("owner");
    if (!owner) return;
    console.log(`owner container restarting · owner=${ref}`);
    await this.launch(owner);
  }

  override onError(error: unknown): unknown {
    // NOT rethrown, unlike the default (dist/lib/container.js:761-764). A throw
    // here aborts the alarm, and an aborted alarm is a brain that goes quiet
    // with nothing in any log saying so — the exact failure shape
    // brain/supervisor.py:325-333 was written about.
    console.error("owner container error (not fatal):", error);
    return undefined;
  }

  /** Called by BrainSupervisor every tick. Idempotent. */
  async ensure(owner: Owner): Promise<{ running: boolean }> {
    if (!SAFE_ID.test(owner.id)) throw new Error("invalid owner id");
    await this.ctx.storage.put("owner", owner);
    await this.ctx.storage.put("owner_ref", owner.id);
    await this.ctx.storage.put("stopping", false);
    const state = await this.getState();
    if (state.status === "healthy" || state.status === "running") {
      return { running: true };
    }
    await this.launch(owner);
    return { running: false };
  }

  /** brain/supervisor.py:132-140 — SIGTERM, then wait. */
  async shutdown(): Promise<void> {
    await this.ctx.storage.put("stopping", true);
    // container_entry.py's SIGTERM handler stops the child, takes a final
    // snapshot and PUTs it. That flush is the whole reason this is SIGTERM and
    // not destroy().
    await this.stop("SIGTERM");
  }

  /** Health, for the supervisor's log line. Never starts the container. */
  async health(): Promise<{ status: string }> {
    const state = await this.getState();
    return { status: state.status };
  }

  private async launch(owner: Owner): Promise<void> {
    // Monotonic, persisted in DO storage. Handed to the container so a zombie
    // from an earlier incarnation cannot overwrite a newer snapshot in R2.
    // See container_entry.py's _generation_guard and BRAIN.md §8.2.
    const generation = ((await this.ctx.storage.get<number>("generation")) ?? 0) + 1;
    await this.ctx.storage.put("generation", generation);

    await this.startAndWaitForPorts({
      ports: [CONTROL_PORT],
      startOptions: {
        envVars: this.envFor(owner, generation),
        labels: { owner_ref: owner.id },
      },
      cancellationOptions: {
        // Cold start is image pull + Python import + an R2 GET of memory.db.
        // The default is ~8s (dist/lib/container.d.ts:169) and that is not
        // enough for a large memory.db on a cold node.
        portReadyTimeoutMS: 120_000,
      },
    });
  }

  /**
   * brain/supervisor.py:76-115, in TypeScript. Read that function alongside
   * this one; every line here is one of its lines.
   */
  private envFor(owner: Owner, generation: number): Record<string, string> {
    const e = this.env;
    const dir = `${e.ANTICIPY_STATE_ROOT}/${owner.id}`;
    return {
      // ---- identity (supervisor.py:93-100)
      ANTICIPY_OWNER_REF: owner.id,
      ANTICIPY_OWNER_ID: owner.legacy_uuid || owner.id,
      ANTICIPY_MEMORY_DB: `${dir}/memory.db`,
      ANTICIPY_CLOCK_STATE: `${dir}/clock_state.json`,
      // ANTICIPY_OWNER_PHONE is ABSENT ON PURPOSE (supervisor.py:101-108).
      // Adding it here re-creates the bug where one owner's texts went to
      // another owner's phone, in both directions.

      // ---- posture (supervisor.py:109-114)
      ANTICIPY_SUPERVISED: "1",
      ANTICIPY_WEBHOOK_MANAGER: "0",

      // ---- state (BRAIN.md §4)
      ANTICIPY_STATE_ROOT: e.ANTICIPY_STATE_ROOT,
      ANTICIPY_STATE_VOLUME_ROOT: e.ANTICIPY_STATE_VOLUME_ROOT,
      ANTICIPY_STATE_R2_PREFIX: e.ANTICIPY_STATE_R2_PREFIX,
      ANTICIPY_STATE_SNAPSHOT_SECONDS: e.ANTICIPY_STATE_SNAPSHOT_SECONDS,
      ANTICIPY_STATE_GENERATION: String(generation),

      // ---- backend + models
      ANTICIPY_PB: e.ANTICIPY_PB,
      ANTICIPY_SERVICE_TOKEN: e.ANTICIPY_SERVICE_TOKEN,
      ANTICIPY_TZ: e.ANTICIPY_TZ,
      ANTICIPY_MODEL: e.ANTICIPY_MODEL,
      ANTICIPY_GEMINI_MODEL: e.ANTICIPY_GEMINI_MODEL,
      ANTICIPY_SEGMENTS: e.ANTICIPY_SEGMENTS,
      ANTICIPY_TWILIO_WEBHOOK_URL: e.ANTICIPY_TWILIO_WEBHOOK_URL,
      OPENROUTER_API_KEY: e.OPENROUTER_API_KEY,
      GEMINI_API_KEY: e.GEMINI_API_KEY,
      BRAVE_API_KEY: e.BRAVE_API_KEY,
      TAVILY_API_KEY: e.TAVILY_API_KEY,

      // ---- twilio
      TWILIO_ACCOUNT_SID: e.TWILIO_ACCOUNT_SID,
      TWILIO_AUTH_TOKEN: e.TWILIO_AUTH_TOKEN,
      TWILIO_PHONE_NUMBER: e.TWILIO_PHONE_NUMBER,
      ...(e.TWILIO_API_KEY_SID ? { TWILIO_API_KEY_SID: e.TWILIO_API_KEY_SID } : {}),
      ...(e.TWILIO_API_KEY_SECRET ? { TWILIO_API_KEY_SECRET: e.TWILIO_API_KEY_SECRET } : {}),

      // ---- archives (brain/state_backup.py:22-27; a PARTIAL set is a hard
      // error at :43-45, never a silent opt-out — pass all five or none)
      ANTICIPY_BACKUP_REQUIRED: e.ANTICIPY_BACKUP_REQUIRED,
      ANTICIPY_BACKUP_S3_BUCKET: e.ANTICIPY_BACKUP_S3_BUCKET,
      ANTICIPY_BACKUP_S3_ENDPOINT: e.ANTICIPY_BACKUP_S3_ENDPOINT,
      ANTICIPY_BACKUP_S3_ACCESS_KEY: e.ANTICIPY_BACKUP_S3_ACCESS_KEY,
      ANTICIPY_BACKUP_S3_SECRET: e.ANTICIPY_BACKUP_S3_SECRET,
      ANTICIPY_BACKUP_S3_REGION: e.ANTICIPY_BACKUP_S3_REGION,
      ANTICIPY_STATE_BACKUP_SECONDS: e.ANTICIPY_STATE_BACKUP_SECONDS,
      ANTICIPY_STATE_BACKUP_PREFIX: e.ANTICIPY_STATE_BACKUP_PREFIX,
      ANTICIPY_STATE_BACKUP_KEEP: e.ANTICIPY_STATE_BACKUP_KEEP,
    };
  }
}

/** brain/supervisor.py's main() loop, minus the process table. Singleton. */
export class BrainSupervisor extends DurableObject<Env> {
  async tick(): Promise<void> {
    // ONE discovery snapshot, used for BOTH decisions. brain/supervisor.py:338-341:
    // fetching it twice lets an account disappear between the two calls and
    // have its memory purged on evidence the reconcile never saw.
    let owners: Owner[];
    try {
      owners = await this.discover();
    } catch (err) {
      console.log(`owner discovery failed (retrying): ${err}`);
      return; // supervisor.py:344-345, and :350-352: no purge without a list
    }

    await this.reconcile(owners);

    try {
      await this.purge(new Set(owners.map((o) => o.id)));
    } catch (err) {
      console.log(`purge pass failed (retrying): ${err}`);
    }
  }

  /** brain/supervisor.py:38-73, as a query. See BRAIN.md §3.3. */
  private async discover(): Promise<Owner[]> {
    const { results } = await this.env.DB.prepare(
      `SELECT id, legacy_uuid FROM owners ORDER BY id`
    ).all<Owner>();
    return (results ?? [])
      .filter((r) => SAFE_ID.test(String(r.id ?? "")))
      .map((r) => ({ id: String(r.id), legacy_uuid: String(r.legacy_uuid ?? "") }));
  }

  /**
   * brain/supervisor.py:264-302. Two properties are bug fixes and must survive:
   *  1. the cap bounds who is STARTED, never who keeps running (:279-282);
   *  2. being over capacity prints, loudly, every pass (:296-301).
   */
  private async reconcile(owners: Owner[]): Promise<void> {
    const cap = Math.max(1, parseInt(this.env.ANTICIPY_MAX_OWNER_WORKERS || "100", 10));
    const wanted = new Map(owners.map((o) => [o.id, o]));
    const known = new Set((await this.ctx.storage.get<string[]>("known")) ?? []);

    // Gone from discovery -> stop. Only ever for a ref discovery no longer names.
    for (const ref of known) {
      if (wanted.has(ref)) continue;
      try {
        await this.env.OWNER_BRAIN.getByName(ref).shutdown();
        console.log(`owner worker stopped · owner=${ref}`);
      } catch (err) {
        console.log(`stop failed for ${ref} (will retry): ${err}`);
      }
      known.delete(ref);
    }

    // Already-running owners are counted first so a newer signup can never
    // take a running owner's slot (supervisor.py:279-282).
    const running = [...wanted.keys()].filter((ref) => known.has(ref));
    let room = cap - running.length;
    const unserved: string[] = [];

    for (const [ref, owner] of wanted) {
      if (known.has(ref)) {
        // Cheap and idempotent: restarts anything that died between ticks.
        try { await this.env.OWNER_BRAIN.getByName(ref).ensure(owner); }
        catch (err) { console.log(`ensure failed for ${ref} (will retry): ${err}`); }
        continue;
      }
      if (room <= 0) { unserved.push(ref); continue; }
      try {
        await this.env.OWNER_BRAIN.getByName(ref).ensure(owner);
        known.add(ref);
        room -= 1;
      } catch (err) {
        console.log(`start failed for ${ref} (will retry): ${err}`);
      }
    }

    await this.ctx.storage.put("known", [...known]);

    if (unserved.length) {
      // Silently dropping accounts is how a fleet reads as healthy while
      // somebody gets nothing at all. supervisor.py:294-301, verbatim intent.
      console.log(
        `AT CAPACITY: ${known.size} workers running ` +
        `(ANTICIPY_MAX_OWNER_WORKERS=${cap}) — ` +
        `${unserved.length} owner(s) have no worker: ` +
        unserved.slice(0, 10).join(", ") + (unserved.length > 10 ? " …" : "")
      );
    }
  }

  /**
   * brain/supervisor.py:150-261, with rmtree replaced by an R2 prefix delete.
   * Read that docstring. Every guard below is one of its paragraphs.
   */
  private async purge(liveRefs: Set<string>): Promise<number> {
    const { results } = await this.env.DB.prepare(
      `SELECT id, owner_ref, legacy_uuid FROM purges WHERE memory_purged = 0 LIMIT 50`
    ).all<{ id: string; owner_ref: string; legacy_uuid: string }>();

    let done = 0;
    for (const row of results ?? []) {
      const ref = String(row.owner_ref ?? "").trim();

      // An account that still exists has not been deleted, whatever the queue
      // says. Left pending on purpose (supervisor.py:194-198).
      if (liveRefs.has(ref)) { console.log(`purge deferred: account ${ref} is still live`); continue; }

      // The same guard discovery uses. That prefix is one delete away from
      // every other owner's mind (supervisor.py:199-204).
      if (!SAFE_ID.test(ref)) { console.log(`purge skipped, unsafe owner ref: ${ref}`); continue; }

      const prefix = `${this.env.ANTICIPY_STATE_R2_PREFIX}/${ref}/`;
      try {
        let cursor: string | undefined;
        do {
          const page = await this.env.OWNER_STATE.list({ prefix, cursor });
          if (page.objects.length) {
            await this.env.OWNER_STATE.delete(page.objects.map((o) => o.key));
          }
          cursor = page.truncated ? page.cursor : undefined;
        } while (cursor);

        // RE-LIST BEFORE MARKING. supervisor.py:176-178: a delete that reports
        // success while the data is still there is the one outcome that turns a
        // privacy promise into a lie. Nothing left is a COMPLETED purge —
        // the account may simply never have been spoken to (:248-249).
        const after = await this.env.OWNER_STATE.list({ prefix });
        if (after.objects.length) {
          console.log(`purge incomplete for ${ref}: ${after.objects.length} object(s) remain`);
          continue;
        }
      } catch (err) {
        console.log(`purge failed for ${ref} (will retry): ${err}`);
        continue;
      }

      try {
        await this.env.DB.prepare(
          `UPDATE purges SET memory_purged = 1, purged_at = ? WHERE id = ?`
        ).bind(new Date().toISOString().replace(/\.\d{3}Z$/, "Z"), row.id).run();
        done += 1;
        console.log(`purged durable memory · owner=${ref} · ${prefix}`);
      } catch (err) {
        // Bytes gone, row still pending. The next pass finds nothing to delete
        // and marks it — which is why "already absent" counts as success above.
        console.log(`purge mark failed for ${ref} (harmless, will retry): ${err}`);
      }
    }
    return done;
  }
}

export default {
  async scheduled(_c: ScheduledController, env: Env, ctx: ExecutionContext) {
    const sup = env.BRAIN_SUPERVISOR.getByName("singleton");
    ctx.waitUntil(sup.tick());
    // TODO before cutover: the Twilio inbound-webhook watchdog, once per fleet,
    // on the 10-minute beat of brain/worker.py:843. See BRAIN.md §3.4. It is
    // the ONE piece of Python that must be rewritten, because "exactly one
    // process may check" is not a property any owner container has.
  },

  // No public route (workers_dev:false, no routes[]). This handler exists only
  // so the site Worker can wake an owner over the service binding.
  async fetch(): Promise<Response> {
    return new Response("no", { status: 404 });
  },
} satisfies ExportedHandler<Env>;
```

### 8.2 `brain/container_entry.py`

Replaces `python -m brain.supervisor` as the image's `CMD`. It is deliberately
thin: pull, supervise one child, snapshot, flush on SIGTERM.

```python
"""Container entrypoint: one owner's brain, with R2 standing in for the volume.

brain/supervisor.py ran N children on a persistent Railway volume. On Cloudflare
the DO decides WHO runs (migration/workers/brain/src/index.ts) and this file runs
exactly one child on an EPHEMERAL disk, with R2 as the durable copy.

Nothing in brain/worker.py, brain/memory.py or brain/state_backup.py changes.
memory.db stays a real local SQLite file, so FTS5 (brain/memory.py:198) keeps
working and no query becomes a network call.
"""
from __future__ import annotations

import http.server
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import threading
import time

from . import state_backup

OWNER_REF = os.environ.get("ANTICIPY_OWNER_REF", "").strip()
STATE_ROOT = Path(os.environ.get("ANTICIPY_STATE_ROOT", "/data/owners"))
R2_PREFIX = os.environ.get("ANTICIPY_STATE_R2_PREFIX", "owners").strip("/")
SNAPSHOT_SECONDS = max(15, int(os.environ.get("ANTICIPY_STATE_SNAPSHOT_SECONDS") or "60"))
ARCHIVE_SECONDS = max(300, int(os.environ.get("ANTICIPY_STATE_BACKUP_SECONDS") or "86400"))
GENERATION = int(os.environ.get("ANTICIPY_STATE_GENERATION") or "1")
CONTROL_PORT = 8731

OWNER_DIR = STATE_ROOT / OWNER_REF
MEMORY_DB = Path(os.environ.get("ANTICIPY_MEMORY_DB") or (OWNER_DIR / "memory.db"))
CLOCK_STATE = Path(os.environ.get("ANTICIPY_CLOCK_STATE") or (OWNER_DIR / "clock_state.json"))

_stopping = threading.Event()
_last_snapshot_ok = 0.0


def _client():
    """The same S3 client brain/state_backup.py:127-135 already builds, from the
    same four variables. A partial configuration raises there (:43-45) rather
    than silently disabling backups, and that is the behaviour we want here too:
    on Cloudflare, R2 is not optional — it is the disk."""
    config = state_backup.backup_config()
    if config is None:
        raise RuntimeError("R2 configuration is absent; on Cloudflare it is the durable store")
    return state_backup._client(config), config["bucket"]


def _key(name: str) -> str:
    return f"{R2_PREFIX}/{OWNER_REF}/{name}"


def pull_state() -> None:
    """Bring this owner's durable mind onto local disk.

    A missing object is a brand-new owner, not an error: brain/memory.py's
    SCHEMA is all CREATE TABLE IF NOT EXISTS (:33 onward), so an absent file
    becomes a correct empty database on first open.
    """
    s3, bucket = _client()
    OWNER_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    for target in (MEMORY_DB, CLOCK_STATE):
        key = _key(target.name)
        try:
            s3.download_file(bucket, key, str(target))
            print(f"state pulled · {key} -> {target} ({target.stat().st_size} bytes)")
        except Exception as exc:
            if "404" in str(exc) or "Not Found" in str(exc) or "NoSuchKey" in str(exc):
                print(f"no stored {target.name} for {OWNER_REF} — starting fresh")
                continue
            # Anything else is NOT "starting fresh". Starting fresh over a
            # transient R2 error means an owner wakes up with no memory of
            # anybody, and then that empty database is snapshotted back over
            # the real one a minute later. Refuse to start instead.
            raise RuntimeError(f"could not read {key}: {exc}") from exc


def _generation_guard(s3, bucket: str, key: str) -> bool:
    """Refuse to overwrite a snapshot written by a NEWER incarnation.

    The DO is a single writer per owner by construction, but a container whose
    DO has already been replaced can still be alive and holding a file handle.
    Its generation is lower, so it loses.
    """
    try:
        head = s3.head_object(Bucket=bucket, Key=key)
    except Exception:
        return True   # nothing there yet
    stored = int((head.get("Metadata") or {}).get("generation") or 0)
    if stored > GENERATION:
        print(f"REFUSING SNAPSHOT: {key} was written by generation {stored} > mine {GENERATION}")
        return False
    return True


def snapshot(reason: str) -> None:
    """Copy memory.db through SQLite's online backup API and PUT both files.

    brain/state_backup.py:75-81 is reused verbatim: it runs PRAGMA quick_check
    and raises if the copy is not 'ok'. Copying a live SQLite file byte-for-byte
    can capture it between writes (state_backup.py:5-7) — that is why this is
    not a plain upload.
    """
    global _last_snapshot_ok
    s3, bucket = _client()
    with tempfile.TemporaryDirectory(prefix="anticipy-snap-") as tmp:
        if MEMORY_DB.exists():
            staged = Path(tmp) / "memory.db"
            state_backup._snapshot_sqlite(MEMORY_DB, staged)
            key = _key("memory.db")
            if _generation_guard(s3, bucket, key):
                s3.upload_file(str(staged), bucket, key, ExtraArgs={"Metadata": {
                    "generation": str(GENERATION),
                    "sha256": state_backup._sha256(staged),
                    "owner-ref": OWNER_REF,
                }})
        if CLOCK_STATE.exists():
            raw = CLOCK_STATE.read_bytes()
            json.loads(raw)          # state_backup.py:104 — never ship a torn JSON file
            key = _key("clock_state.json")
            if _generation_guard(s3, bucket, key):
                s3.put_object(Bucket=bucket, Key=key, Body=raw,
                              Metadata={"generation": str(GENERATION), "owner-ref": OWNER_REF})
    _last_snapshot_ok = time.time()
    print(f"state snapshot ok · owner={OWNER_REF} · {reason}")


def snapshot_loop() -> None:
    last_mtime = 0.0
    next_archive = time.monotonic() + 300
    while not _stopping.is_set():
        _stopping.wait(SNAPSHOT_SECONDS)
        if _stopping.is_set():
            break
        try:
            mtime = MEMORY_DB.stat().st_mtime if MEMORY_DB.exists() else 0.0
            if mtime != last_mtime:
                snapshot("periodic")
                last_mtime = mtime
        except Exception as exc:
            # Visible and retried, never fatal: brain/supervisor.py:365-368 took
            # the same posture, and for the same reason — a backup failure must
            # not stop the owner being heard.
            print(f"STATE SNAPSHOT FAILED (retrying): {exc}")
        if time.monotonic() >= next_archive:
            try:
                uploaded = state_backup.backup_state_to_s3(OWNER_DIR.parent)
                if uploaded:
                    print(f"worker state backup verified · key={uploaded}")
                next_archive = time.monotonic() + ARCHIVE_SECONDS
            except Exception as exc:
                print(f"WORKER STATE BACKUP FAILED (retrying): {exc}")
                next_archive = time.monotonic() + min(900, ARCHIVE_SECONDS)


class Control(http.server.BaseHTTPRequestHandler):
    """The port OwnerBrain waits on. brain/worker.py serves no HTTP, so without
    this there is nothing for startAndWaitForPorts() to observe and no way for
    the DO to demand a flush."""

    def _reply(self, code: int, body: dict) -> None:
        payload = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        if self.path in ("/ping", "/health"):
            alive = CHILD is not None and CHILD.poll() is None
            return self._reply(200 if alive else 503, {
                "owner_ref": OWNER_REF,
                "worker_alive": alive,
                "generation": GENERATION,
                "last_snapshot_age_s": round(time.time() - _last_snapshot_ok, 1) if _last_snapshot_ok else None,
            })
        return self._reply(404, {"error": "not found"})

    def do_POST(self):
        if self.path == "/flush":
            try:
                snapshot("on demand")
                return self._reply(200, {"ok": True})
            except Exception as exc:
                return self._reply(500, {"error": str(exc)})
        return self._reply(404, {"error": "not found"})

    def log_message(self, *_args):
        pass   # the control server must not drown the worker's own output


CHILD: subprocess.Popen | None = None


def main() -> int:
    global CHILD
    if not OWNER_REF:
        print("ERROR: ANTICIPY_OWNER_REF is unset — refusing to start an unscoped worker")
        return 2

    pull_state()

    # brain/supervisor.py:118-122 — the parent creates the directory before the
    # child can, mode 0700.
    for path in (MEMORY_DB, CLOCK_STATE):
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)

    server = http.server.ThreadingHTTPServer(("0.0.0.0", CONTROL_PORT), Control)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    threading.Thread(target=snapshot_loop, daemon=True).start()

    def request_stop(_signum, _frame):
        _stopping.set()
    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)

    # A CHILD process, not an in-process import, for the reason
    # brain/supervisor.py:1-10 gives: worker/Memory/Conversation hold mutable
    # module globals, and a crash in one must not take the snapshot thread down
    # with it.
    CHILD = subprocess.Popen([sys.executable, "-m", "brain.worker"], env=os.environ.copy())

    while not _stopping.is_set():
        if CHILD.poll() is not None:
            print(f"worker exited ({CHILD.returncode}) — snapshotting and letting the DO restart us")
            break
        time.sleep(1)

    # brain/supervisor.py:132-140 — SIGTERM, wait 10s, then SIGKILL.
    if CHILD.poll() is None:
        CHILD.terminate()
        try:
            CHILD.wait(timeout=10)
        except subprocess.TimeoutExpired:
            CHILD.kill()
            CHILD.wait(timeout=5)

    # THE FLUSH. This is what makes the loss window 0 on a graceful stop, and it
    # is why OwnerBrain.shutdown() sends SIGTERM instead of destroy() and why
    # rollout_active_grace_period is 3600 in wrangler.brain.jsonc.
    try:
        snapshot("shutdown")
    except Exception as exc:
        print(f"FINAL SNAPSHOT FAILED: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

**One-line change to `brain/Dockerfile:14`:**

```dockerfile
CMD ["python", "-m", "brain.container_entry"]
```

Everything else in that Dockerfile stays, including the `tzdata` pip package,
which is not optional — `brain/llm.py:47` builds a `ZoneInfo` at *import* time
and `python:3.11-slim` ships no system tzdb (`brain/Dockerfile:5-11`).

---

## 9. Cost, in the only honest form available

Containers bill for running instances. `brain/worker.py` is a 2-second poll loop
that never idles, so **every owner is billed for every second of every day.**
The shape is:

```
monthly ≈ owners × 2_592_000 s × (vCPU_rate × 0.25 + GiB_rate × 1.0) + egress
```

for `instance_type: "basic"` (¼ vCPU, 1 GiB — `config-schema.json`,
`ContainerApp.instance_type`). **I have not verified the current per-second
rates** (§11): read them off Cloudflare's pricing page and put the number in
`migration/BLOCKERS.md` before anyone commits. The point that does not need the
rate: this is a *per-owner always-on* bill, and it grows linearly with signups,
where the Railway bill was one container for all of them.

Two levers, if the number is wrong:

* `instance_type: "lite"` (1/16 vCPU, 256 MiB). `brain/memory.py` plus httpx
  plus the Python runtime in 256 MiB is plausible but unmeasured — measure the
  RSS of one real owner before choosing it.
* The wake-on-event shape in §3.5, with the five globals moved into `memory.db`
  first. That is the only design here that stops billing an idle owner.

---

## 10. Cutover order

1. **Upgrade to Workers Paid and enable R2.** Nothing below is possible first
   (`migration/BLOCKERS.md`).
2. Create bucket `anticipy-owner-state`. Confirm — by listing it — that the
   archive bucket `ANTICIPY_BACKUP_S3_BUCKET` names actually exists and is
   current. `migration/BLOCKERS.md` records that R2 is not enabled on this
   account, so those nightly PocketBase and worker-state backups have either
   been going somewhere else or failing.
3. Prove `brain/state_backup.py` against R2 with **one** manual upload: the
   `ServerSideEncryption` header and the user-metadata round trip (§4.5).
4. `npm i @cloudflare/containers@0.3.7` at the repo root; write the two files
   from §8; change `brain/Dockerfile:14`.
5. Fill `database_id` in `wrangler.brain.jsonc`; `wrangler secret put` the 15
   secrets in §5.2.
6. Deploy with `max_instances: 1` and a `vars.ANTICIPY_MAX_OWNER_WORKERS` of
   `1`. Run **one** owner — not the founder — against the live backend. Watch
   for: container reaches healthy; `state pulled`; `state snapshot ok` inside
   90 seconds; the brain answers a real text.
7. **Stop the Railway supervisor.** Run `migration/runbooks/brain_state_to_r2.sh`
   (§4.7) plus the founder's manual copy. Verify the counts match.
8. Raise both caps to 100. Redeploy. Watch `AT CAPACITY` never print.
9. Leave Railway's volume **in place, unmounted, undeleted** for two weeks. The
   R2 archive is a claim about a backup nobody has restored from yet; the volume
   is the thing that is known to work.

---

## 11. Unverified

Everything below is a thing I could not check from this machine. None of it is
asserted as fact anywhere above.

1. **D1 and FTS5.** I did not run `CREATE VIRTUAL TABLE … USING fts5` against
   their D1. The probe, if anyone wants the answer:
   `npx wrangler d1 execute anticipy-backend-staging --remote --command "CREATE VIRTUAL TABLE _fts_probe USING fts5(x); DROP TABLE _fts_probe;"`.
   The §4 recommendation does not depend on the answer — it keeps SQLite local
   precisely so the question does not arise.
2. **D1 databases per account.** I did not verify any limit. Relevant only to
   the rejected database-per-owner design.
3. **R2 and `ServerSideEncryption: "AES256"`** on `PutObject`
   (`brain/state_backup.py:173`). Untested against R2 — see §4.5, step 3 of §10.
4. **R2 user-metadata casing.** `state_backup.py:186` lowercases keys read back
   from `head_object`. S3 lowercases; whether R2 does is untested.
5. **Container pricing.** Rates not read; §9 gives the formula, not a number.
6. **Container maximum lifetime.** I found no ceiling in the package or the
   config schema, and §3.2's mechanism has no expiry in its code path. Whether
   the *platform* caps how long one instance may run is not something the
   package can tell me. Assume instances are replaced, and rely on
   `OwnerBrain.onStop()` to restart — that is why it is written.
7. **`ScheduledController` / DO RPC under a cron trigger.** The `scheduled`
   handler calling a DO stub by RPC is ordinary, but I did not execute it.
8. **`setOutboundByHost` / service-binding egress at N=100** (§7.2). The API
   surface is read from `@cloudflare/containers@0.3.7`'s own type definitions;
   its behaviour under a 2-second poll from a hundred containers is not.
9. **Worker subrequest ceiling** for a DO invocation (§7.1). The
   `limits.subrequests` knob is confirmed present in the config schema; the
   default value is not verified.
10. **`brain/worker.py` memory footprint.** No RSS measurement was taken, so
    `instance_type: "basic"` is a reasoned choice, not a measured one.
11. **The archive bucket's real name and health.** `ANTICIPY_BACKUP_S3_BUCKET`
    is an environment variable (`backend/pb_migrations/1700000053_off_volume_backups.js:27`),
    not a literal in the repo. `anticipy-pocketbase-backups-production` comes
    from `migration/BLOCKERS.md`, which also records that R2 is not enabled on
    this account.
12. **`owners.legacy_uuid` and the `purges` table in D1.** I read the column
    names from `backend/pb_hooks/worker_owners.pb.js:24` and
    `brain/supervisor.py:192,215,252`. `migration/d1/schema.sql:419,569` has
    both tables; I did not diff every column against production, and
    `migration/d1/GAPS.md` says nobody should assume the repo describes it fully.
