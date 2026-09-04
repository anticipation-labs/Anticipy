# brain/ off Railway, onto Cloudflare Containers — the runbook

Measured **2026-09-04** against Cloudflare account `114587b715e702461766369b01d42fc7`
(`omar@anticipy.ai`), wrangler **4.129.0**, `@cloudflare/containers` **0.3.7**.

Nothing here was deployed. Every line marked **VERIFIED** is a command that ran on
this machine with the output shown; everything else is marked **DESIGN** and is a
plan, not a result.

---

## VERDICT

**POSSIBLE, and much closer than the older files in this directory claim — but
blocked before the first deploy, on three things, only one of which needs a human.**

> ### The exact blocking step
>
> ```
> $ npx wrangler containers build brain/ --tag anticipy-brain:probe
>   The Docker CLI is needed to build the image but could not be launched.
> ```
>
> `wrangler deploy` builds the image itself, through the same path. **There is no
> Docker-compatible CLI on this machine** (`docker`, `podman`, `colima`, `nerdctl`,
> `orb` — none on PATH, no Docker Desktop / OrbStack / Rancher in `/Applications`).
> Until a Docker-compatible engine exists somewhere, no image can be produced and
> nothing can be deployed.

Two more blockers sit in front of that, and both are **code that does not exist**,
not access anybody has to grant:

| # | Missing | Why it stops the deploy |
|---|---|---|
| 1 | `migration/workers/brain/src/index.ts` | `config/wrangler.brain.jsonc` names it as `main`. The file was never written. `wrangler deploy` fails at bundling, *before* it ever reaches Docker. |
| 2 | `brain/container_entry.py` | `workers/BRAIN.md` §4 designs it; it does not exist anywhere in this tree. Without it a container starts with an **empty** `/data`, and every owner's `memory.db` is gone on every restart — silently. This is the one that must not be skipped to "get something up". |
| 3 | A Docker-compatible engine | The build above. |

Order matters: 1 and 2 are writable from here, 3 is not.

---

## 1. Corrections to the existing files in this directory

Read this section before trusting `BLOCKERS.md`, `STATUS.md` or `workers/BRAIN.md`.
Two of their headline blockers are **gone**, and planning around them wastes a day.

| Claim | Where | Status today |
|---|---|---|
| *"Containers — Unauthorized. Requires the Workers Paid plan."* | `BLOCKERS.md`, `workers/BRAIN.md` header, `config/wrangler.brain.jsonc` header | **STALE — resolved.** `wrangler containers list` → `No containers found.` The plan upgrade landed. |
| *"R2 is NOT yet enabled — it is a separate opt-in."* | `BLOCKERS.md`, `spike/containers-availability.md` | **STALE — resolved.** Three buckets exist (below). |
| `"database_id": "REPLACE_WITH_PRODUCTION_D1_ID"` | `config/wrangler.brain.jsonc` | **Still a placeholder.** The value is `f341f23d-ec52-4b2f-9a2d-13117ebee86e`. |
| *"`brain/memory.py` is 3,900 lines"* | `workers/BRAIN.md` §1 | Wrong figure; it is **2,804**. (`brain/*.py` totals 22,614, which is the number BRAIN.md was reaching for.) |
| *"memory.db has an FTS5 virtual table and two triggers"* — implied load-bearing | `workers/BRAIN.md` §1 | True but **not load-bearing**. `brain/memory.py:195-196` says in so many words: *"Kept separate because it is optional: if this SQLite build lacks FTS5, the search falls back to LIKE and nothing breaks."* Do not let FTS5 drive the storage decision. |

**VERIFIED**, this machine, today:

```
$ npx wrangler containers list
No containers found.

$ npx wrangler containers images list
REPOSITORY  TAG                      # the registry is empty

$ npx wrangler r2 bucket list
anticipy-downloads                    2026-09-04T02:59:07Z
anticipy-evidence                     2026-09-04T02:59:06Z
anticipy-pocketbase-backups-production 2026-09-04T02:59:08Z

$ npx wrangler d1 list
anticipy-backend          f341f23d-ec52-4b2f-9a2d-13117ebee86e   17,002,496 bytes
anticipy-backend-staging  757fb0cd-1971-4daf-99b0-7183fe89bb10

$ npx wrangler whoami         # token scopes include, verbatim:
containers (write)   cloudchamber (write)   d1 (write)   workers (write)
```

Note what is **not** in that bucket list: **`anticipy-owner-state`**, the durable
home this design gives every owner's mind. It has to be created (§6, step 3).

Also note `anticipy-pocketbase-backups-production` was created **today at 02:59**,
which means it is a *new, empty* bucket in the *new* account. `BLOCKERS.md`'s open
question — *"either those backups go to a different Cloudflare account, or they
have been failing"* — is therefore still open, and this bucket is **not** evidence
that a safety net exists. Do not discard the Railway volume on the strength of a
bucket that is three hours old and whose contents nobody has listed. (`wrangler`
has no `r2 object list`; only `get`/`put`/`delete`. Listing needs the dashboard or
an S3 client.)

---

## 2. What runs on Railway today, exactly

**VERIFIED** by reading the tree.

| Fact | Source |
|---|---|
| Image `python:3.11-slim`; deps `requests httpx tzdata boto3`; `CMD ["python","-m","brain.supervisor"]` | `brain/Dockerfile` |
| Build context is the **repo root** — `COPY brain /srv/brain` | `brain/Dockerfile:4` |
| `.railwayignore` strips 11 directories so the monorepo does not ride to the builder | `/.railwayignore` |
| **There is no `railway.json`, no `railway.toml`, no `Procfile`, no `nixpacks.toml`, no `requirements.txt`, no `pyproject.toml`** anywhere in the repo | `find` over the tree |
| Supervisor forks **one OS process per owner**: `Popen([sys.executable, "-m", "brain.worker"], env=…)` | `brain/supervisor.py:129` |
| Discovery every 15 s over HTTP, `GET /worker/owners`, shared-token auth | `brain/supervisor.py:30,54-58` → `backend/pb_hooks/worker_owners.pb.js:9-14` |
| Per-owner state `"/data/owners"/<ref>/{memory.db,clock_state.json}`, mode `0o700` | `brain/supervisor.py:32,95-100,122` |
| Child worker loop is `while True: … time.sleep(2)` | `brain/worker.py:44`, `:4659` |
| **The brain listens on no port at all** — `grep -E 'HTTPServer\|socketserver\|bind\(\|listen\(\|uvicorn\|flask\|FastAPI'` over `brain/` returns **nothing** | measured |
| 31 owners live | `SELECT COUNT(*) FROM owners` on D1 → **31** |
| Purge queue drained: 7 rows, 0 pending | `SELECT … FROM purges` on D1 |

> **The absence of a `railway.json` matters.** Every operational fact about the
> Railway service that is *not* in the Dockerfile — the volume mount path, the
> memory/CPU allocation, the restart policy, the replica count, and **the actual
> values of ~20 environment variables** — lives only in the Railway dashboard.
> None of it is in this repo, and none of it can be read from here. Whoever does
> the cutover must screenshot or export that service's Variables tab first; the
> inventory in §4 tells you which names to look for, but not their values.

---

## 3. The shape it has to take on Cloudflare — and the one hard fact behind it

**DESIGN**, but the runtime mechanics below are **VERIFIED** against the
`@cloudflare/containers@0.3.7` source, installed to
`migration/spike/containers-sdk/` for exactly this purpose.

```
   cron "* * * * *"
         │
         ▼
  BrainSupervisor (DO, singleton)          ── D1 anticipy-backend: SELECT owners
         │  RPC ensure(ref) / shutdown(ref)  ── D1: purges queue
         ▼
  OwnerBrain (DO, one per owner_ref) extends Container
         │  ctx.container.start({ envVars })
         ▼
  container  (brain/Dockerfile)
     container_entry.py
      ├─ pull memory.db + clock_state.json ◄── R2 anticipy-owner-state
      ├─ control HTTP server on :8731          ← THE PORT THAT DOES NOT EXIST YET
      ├─ snapshot thread ──────────────────►   R2 anticipy-owner-state
      └─ child: python -m brain.worker          (UNCHANGED — 22,614 lines untouched)
```

`brain/supervisor.py` is **not ported, it is replaced**, function by function
(the mapping table in `workers/BRAIN.md` §2 is correct and I am not repeating it).
`brain/worker.py` and everything it imports is **not touched**.

### 3.1 Containers sleep. The override that stops them is real — I read it.

The default idle-shutdown is one method, and overriding it is the whole answer:

```js
// node_modules/@cloudflare/containers/dist/lib/container.js:748-754  — verbatim
async onActivityExpired() {
    console.log('Activity expired, signalling container to stop');
    if (!this.container.running) { return; }
    await this.stop();
}
```

```js
// :1513-1517 — verbatim
// do not remove this, container DOs ALWAYS need an alarm right now.
const prevAlarm = Date.now();
await this.ctx.storage.setAlarm(prevAlarm);

// :1567-1570 — verbatim
await this.onActivityExpired();
// renewActivityTimeout makes sure we don't spam calls here
this.renewActivityTimeout();
```

So: override `onActivityExpired()` to a no-op, and the alarm at `:1516` is still
armed and `renewActivityTimeout()` at `:1569` has already pushed the deadline out.
The container never sleeps. `DEFAULT_SLEEP_AFTER = '10m'` (`:20`) is what would
otherwise kill every owner's brain ten minutes after boot — and **nothing would
ever wake it**, because the brain has no inbound HTTP and its liveness is a
2-second poll *outward*.

Do **not** implement keep-alive by having the DO `fetch()` the container on a
timer. It works, and it makes liveness depend on a network round-trip forever.

### 3.2 The finding that is mine, and it is the one I would not ship without

**A container with no listening port cannot be proven alive.** Verified in the
same source:

- `start()` does not require a port (`:552` — *"without waiting for ports to be ready"*).
- `startAndWaitForPorts()` does.
- `fetch()` into a container throws without one: *"No port configured for this
  container. Set the `defaultPort` in your Container subclass…"* (`:986-987`).

So the naive port-free port of `brain/` **starts, and is then completely opaque**.
The DO knows the container was started. It cannot know whether `python -m
brain.worker` inside it is still running, crashed on import, or is wedged.

That is precisely the failure shape this repo already has a law and a gate for.
`CLAUDE.md`: *"`are_the_ears_live.py` exists because the ears went deaf for 30
hours and nothing noticed."* The container platform would give us a *second*
silent one-directional failure, with a green dashboard over it.

**Therefore `container_entry.py` MUST expose a control port (8731), and
`OwnerBrain` MUST use `startAndWaitForPorts` rather than `start`.** The port is
not a nicety for later; it is the only thing that turns "the platform says
running" into "the brain is actually thinking". Treat it as part of the minimum,
and set `defaultPort = 8731` on the subclass.

---

## 4. Environment: the complete inventory

**VERIFIED** — every `os.environ` reference in `brain/` (`os.getenv` returns none).

### 4.1 Non-secret → `vars` in wrangler config, passed via `start({ envVars })`

Already correct in `config/wrangler.brain.jsonc`, which is a good file. Names:

```
ANTICIPY_PB                       ANTICIPY_STATE_ROOT
ANTICIPY_STATE_VOLUME_ROOT        ANTICIPY_STATE_BACKUP_SECONDS
ANTICIPY_STATE_BACKUP_PREFIX      ANTICIPY_STATE_BACKUP_KEEP
ANTICIPY_BACKUP_REQUIRED          ANTICIPY_BACKUP_S3_REGION
ANTICIPY_MAX_OWNER_WORKERS        ANTICIPY_OWNER_DISCOVERY_SECONDS
ANTICIPY_TZ                       ANTICIPY_MODEL
ANTICIPY_GEMINI_MODEL             ANTICIPY_SEGMENTS
ANTICIPY_SUPERVISED               ANTICIPY_WEBHOOK_MANAGER
ANTICIPY_TWILIO_WEBHOOK_URL
```

Not yet in that file, and read by `brain/`: `ANTICIPY_AUX_MODEL`,
`ANTICIPY_STRONG_MODEL`, `ANTICIPY_LINKS`, `ANTICIPY_LLM_LEDGER`,
`ANTICIPY_SEGMENT_TRIAGE`, `TWILIO_API_BASE`, `TWILIO_MOCK`. Read their live
values off the Railway dashboard before assuming the defaults are what production
runs.

### 4.2 Per-owner, computed at spawn — never configured

`ANTICIPY_OWNER_REF`, `ANTICIPY_OWNER_ID`, `ANTICIPY_MEMORY_DB`,
`ANTICIPY_CLOCK_STATE`, `ANTICIPY_OWNER_PHONE`.

`OwnerBrain.envFor()` must reproduce `brain/supervisor.py:76-115` **including the
`env.pop("ANTICIPY_OWNER_PHONE")`** on line 109. That `pop` is a scar: without it
a second signup got a worker bound to the founder's phone number, and cross-account
SMS flowed in both directions. Port the comment with the code.

### 4.3 Secrets → `wrangler secret put`, one per line, never in the config file

```
ANTICIPY_SERVICE_TOKEN        OPENROUTER_API_KEY        GEMINI_API_KEY
BRAVE_API_KEY                 TAVILY_API_KEY
TWILIO_ACCOUNT_SID            TWILIO_AUTH_TOKEN         TWILIO_PHONE_NUMBER
TWILIO_FROM                   TWILIO_API_KEY_SID        TWILIO_API_KEY_SECRET
ANTICIPY_BACKUP_S3_BUCKET     ANTICIPY_BACKUP_S3_ENDPOINT
ANTICIPY_BACKUP_S3_ACCESS_KEY ANTICIPY_BACKUP_S3_SECRET
```

A Worker secret is not automatically a *container* environment variable — the DO
has to read `this.env.X` and put it in the `envVars` object it passes to `start()`.
Forgetting one is a container that boots and then fails on first use, which under
§3.2's opaque-container problem is invisible. The control port's `/health` should
report which of these arrived non-empty (names only, never values).

> **`STATUS.md` says every value in `.env.local` should be treated as burned** —
> all 38 arrived by chat. Do not copy them onto Cloudflare and call it done;
> rotate at the vendor, then set. `ANTICIPY_INTERNAL_KEY` is the expensive one:
> `cal_url = sha256(teamKey + personId)`, so rotating it invalidates every
> subscribed calendar feed.

---

## 5. Persistent state — the actual hard part

### 5.1 What is on the volume

Two files per owner, under `ANTICIPY_STATE_ROOT` (`/data/owners/<ref>/`):

- **`memory.db`** — real local SQLite, opened `sqlite3.connect(str(path))`
  (`brain/memory.py:682`). This is the assistant's long-term memory. 31 owners.
- **`clock_state.json`** — the outreach limiter. `brain/supervisor.py` has a
  comment recording that a half-written one *"read back as the permissive default
  and wiped their outreach limit too"*. It is small and it is dangerous.

### 5.2 D1 is the wrong answer. R2 is the right one.

The task framing offered "D1 or R2". It is **R2**, and the reasoning is not taste:

- `brain/memory.py` is 2,804 lines built on a **synchronous local file handle**.
  D1 is reached over HTTP, asynchronously, from a Worker binding. Porting memory
  to D1 means rewriting all 2,804 lines *and* it means the DO, not the container,
  owns memory — which breaks the whole "worker.py is untouched" premise.
- FTS5 does not decide this. It is explicitly optional (`memory.py:195-196`) and
  degrades to `LIKE`. (D1 blocks `pragma_compile_options()` with `SQLITE_AUTH
  [7500]`, so its FTS5 support is unverifiable from here anyway — and irrelevant.)
- **Single-writer is guaranteed**, which is what makes whole-file R2 safe:
  `getByName(owner_ref)` yields exactly one DO per owner, so exactly one container
  per owner, so exactly one process with that file open. No merge problem exists.

So: **R2 `anticipy-owner-state`, keys `owners/<ref>/memory.db` and
`owners/<ref>/clock_state.json`.** Container disk is scratch.

### 5.3 What `container_entry.py` must do (it does not exist — write it)

1. **On boot, before starting the child**: GET both objects from R2 into
   `/data/owners/<ref>/`. Absent object = new owner, create the directory `0o700`
   and continue. A *failed* GET (as against a 404) must **abort the boot**, loudly.
   Booting on an empty dir when the object exists is how 31 people lose their
   memory quietly.
2. **Start the control HTTP server on :8731** (§3.2) before starting the child, so
   `startAndWaitForPorts` has something to see.
3. **`exec` the child** `python -m brain.worker` with the environment it is given.
4. **Snapshot loop**, every `ANTICIPY_STATE_SNAPSHOT_SECONDS` (60 s recommended):
   copy `memory.db` through **SQLite's online backup API** — never a byte copy of a
   live file — and PUT to R2. `brain/state_backup.py:73-81` already has exactly
   this routine (`_snapshot_sqlite`, with a `PRAGMA quick_check` afterwards);
   reuse it, do not rewrite it.
5. **On SIGTERM**: stop the child, take one final snapshot, PUT, *then* exit.
   `config/wrangler.brain.jsonc` already sets `rollout_active_grace_period: 3600`
   to give this somewhere to happen.
6. **The daily verified-zip archive** (`state_backup.backup_state_to_s3`) keeps
   working unchanged — it is boto3 against an S3 endpoint, and R2 speaks S3. It
   needs the four `ANTICIPY_BACKUP_S3_*` secrets and an R2 S3 endpoint URL
   (`https://<account_id>.r2.cloudflarestorage.com`) plus an R2 **API token**,
   which is a different credential from the OAuth login and does not exist yet.

**The snapshot interval IS the crash-loss window.** At 60 s, a container lost
without SIGTERM costs that owner up to a minute of memory. Say that number out
loud to the owner before picking it; do not let it be discovered after an incident.

### 5.4 The one-way door

Moving 31 owners' `memory.db` off the Railway volume is a **data migration, not a
config change**, and the source is deleted at the end. The order is:

1. Copy the volume off Railway to a local staging dir (Railway CLI / a one-off
   container that tars `/data` — this repo has no tooling for it).
2. `PRAGMA integrity_check` every one of the 31 databases locally.
3. `wrangler r2 object put` each into `anticipy-owner-state`.
4. Read each back and compare SHA-256. `brain/state_backup.py:66-71` has `_sha256`.
5. Only then cut over. **Keep the Railway volume for at least a week.**

---

## 6. The runbook

Steps 1-2 are code that does not exist. Step 3 onward is mechanical.

**1. Write `migration/workers/brain/src/index.ts`.** Two DO classes,
`OwnerBrain extends Container` and `BrainSupervisor`, plus a `scheduled()` handler.
`config/wrangler.brain.jsonc` already declares both bindings and the `v1`
`new_sqlite_classes` migration. Required, from §3-§4:

```ts
export class OwnerBrain extends Container<Env> {
  defaultPort = 8731;              // §3.2 — without this it is unobservable
  requiredPorts = [8731];
  sleepAfter = '24h';
  override async onActivityExpired() { /* deliberately empty — §3.1 */ }
}
```

and `BrainSupervisor.tick()` doing `SELECT id, legacy_uuid FROM owners ORDER BY id`
against `env.DB`, filtered by `/^[A-Za-z0-9_-]{8,64}$/` — the same guard as
`brain/supervisor.py:35`, which is load-bearing because that string is joined onto
a state path and later deleted. Preserve `reconcile_children`'s two properties:
the cap **turns owners away, never evicts**, and over-capacity **prints every pass**.

`npm install @cloudflare/containers` in `migration/workers/` first — it is **not**
currently installed anywhere in this tree (I installed 0.3.7 to
`migration/spike/containers-sdk/` only to read its source).

**2. Write `brain/container_entry.py`** to §5.3, and change `brain/Dockerfile`'s
`CMD` to it. Add `boto3` — already there. The image otherwise does not change.

**3. Create the bucket and fix the placeholder.**

```
npx wrangler r2 bucket create anticipy-owner-state
# then in config/wrangler.brain.jsonc:
#   "database_id": "f341f23d-ec52-4b2f-9a2d-13117ebee86e"
```

**4. Get a Docker-compatible engine.** Two roads, and they are not equivalent:

- *Locally, for iteration*: Docker Desktop, OrbStack, or Podman +
  `WRANGLER_DOCKER_BIN` / `DOCKER_HOST`.
- *For production*: **CI, not a laptop.** `.github/workflows/system-invariants.yml`
  already runs on `ubuntu-latest`, which has Docker, and already triggers on
  `brain/**`. A production image built by hand on one Mac is unreproducible and
  unattested, and this repo has been served a stale image twice
  (`research/2026-08-26-hq-deploy-clobber.md`, and `CLAUDE.md`'s live-deploy rule).
  Add a job that builds, pushes, and then runs the §7 verification.

**5. Dry-run before anything real.** From the repo root:

```
npx wrangler deploy --dry-run --config migration/config/wrangler.brain.jsonc
```

**6. Secrets**, all of §4.3, `--config migration/config/wrangler.brain.jsonc`.

**7. Migrate the 31 databases** per §5.4. Not as part of a deploy.

**8. Deploy**, then §7 — and only after §7 is green, stop the Railway service.
**Never run both.** Two supervisors against one backend is two brains per owner:
duplicate outreach, duplicate SMS, and two writers on one `clock_state.json`,
whose failure mode this repo has already recorded.

---

## 7. Verification — the part that makes it true

`CLAUDE.md` law 3: *"Nothing is fixed until its gate leg is green against LIVE.
Prod has served stale code twice. Repo-green is not done."* `wrangler deploy`
reports success while failing, the same way `railway up` does.

| Leg | Command | Green means |
|---|---|---|
| The app exists | `npx wrangler containers list` | not `No containers found` |
| Instances are up | `npx wrangler containers instances <ID>` | ~31, running |
| The image is the one we built | `npx wrangler containers images list` | tag matches the CI build SHA |
| **The brain is thinking** | `python3 overnight/are_the_ears_live.py` with `ANTICIPY_BACKEND_URL` pointed at the new origin | speech arriving *and* server writes — the asymmetry test |
| No over-speaking | `python3 overnight/is_the_brain_live.py` | as today |
| Nothing regressed | `python3 overnight/tejas_gate.py`, `done_gate.py`, `stranger_gate.py` | as today |

The gates read `ANTICIPY_BACKEND_URL` from the environment
(`overnight/is_it_live.py:29`), so they re-point without edits.

**`are_the_ears_live.py` is the one that matters here**, and it is worth saying
why: it is the only gate whose control is *rows the server wrote*, so it can see a
one-directional failure. A container that starts and whose child died is exactly
that shape. Run it against LIVE before Railway is turned off, not after.

There is currently **no gate that says "the container is running the code we
built"**. §3.2's control port is what would make one possible. Write it with the
migration, not after.

---

## 8. Cost, since it is a real number and nobody has said it

31 owners, one always-on `basic` container each — `basic` = ¼ vCPU, 1 GiB, 4 GB
disk (`node_modules/wrangler/config-schema.json`, `ContainerApp.instance_type`).
**31 containers running 24/7 is the entire cost model**, and it is a different
shape from one Railway service with 31 processes on it.

The brain is I/O-bound — a 2-second poll and HTTP calls to models — so `basic` is
right and `lite` (1/16 vCPU, 256 MiB) is worth measuring against. Do the arithmetic
against Cloudflare's current container pricing before deploying 31 of anything;
`config/wrangler.brain.jsonc`'s `max_instances: 100` is a ceiling, not a forecast,
and it is deliberately equal to `ANTICIPY_MAX_OWNER_WORKERS` so the platform and
the application cannot disagree silently.

---

## 9. Not verified — do not let these be read as facts

- **No container was built, pushed, or deployed.** Nothing in §6 has been executed.
- **Cloudflare's container pricing** — not looked up. §8 is a shape, not a quote.
- **Whether a container may run indefinitely** without a platform-side maximum
  lifetime. §3.1 proves the *SDK* will not stop it; it does not prove the platform
  never will. This is the single largest remaining unknown in the design, and it
  is answerable only by running one for a day.
- **The Railway service's dashboard configuration** — volume path, resources,
  restart policy, and the live values of ~20 env vars. Not in the repo, not
  readable from here (§2).
- **Whether the PocketBase/worker backups exist and are current.** The bucket is
  three hours old and empty as far as anyone here knows (§1).
- **`anticipy-backend` D1 as the discovery source.** The `owners` (31 rows) and
  `purges` (7 rows, 0 pending) tables are confirmed present and queryable. Whether
  that D1 is *authoritative* depends on the cutover in `CUTOVER-STATE.md`, which
  says plainly: nothing serves from Cloudflare yet. **Migrating the brain to read
  D1 before the backend cutover would point the brain at a database no one is
  writing to** — the brain would go quiet with every dashboard green. `brain/` is
  step 6 of that file's ordering for a reason. Do not reorder it.

---

*Written 2026-09-04. Companion to `workers/BRAIN.md` (the design, still sound —
read §1 here for its stale headers) and `config/wrangler.brain.jsonc` (the config,
still needs the D1 id).*
