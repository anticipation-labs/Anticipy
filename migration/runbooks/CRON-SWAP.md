# Cron swap: `internal_hq_sweep` from PocketBase to the Worker

Written 2026-09-04. **Nothing in this file has been executed.** Every command
below is written out to be run by hand, in order, by someone who has read the
whole file first.

Supersedes the claim in `migration/CUTOVER-STATE.md:80-84` that "the swap is
reachable without the Railway CLI". It is not. See §1.

---

## 0. TL;DR

| | |
|---|---|
| Can PocketBase's API disable/delete a cron? | **No.** List and run-now only. |
| So what actually stops it? | A backend **code change + Railway redeploy**. There is no other lever. |
| What is the API good for, then? | It is the **verifier**, not the actuator. It is how you prove the sweep is gone. |
| Can this be done from this machine today? | **No.** The Railway CLI is not installed. |
| Is the Worker half ready? | **Yes.** Live, D1 + Twilio + Resend bound, trigger absent by design. |

---

## 1. (a) Does the PocketBase API support DISABLING or DELETING a cron?

**No.** Two independent proofs agree.

### Proof 1 — the source, at the pinned version

`backend/Dockerfile:3` pins `ARG PB_VERSION=0.30.4`. In
`pocketbase/pocketbase@v0.30.4`, `apis/cron.go` registers exactly two routes:

```go
subGroup.GET("", cronsList)
subGroup.POST("/{id}", cronRun)
```

No `DELETE`, no `PATCH`, no `PUT`. No disable, remove, or unregister of any
kind. `cronAdd` registrations live in the JSVM hook file and exist only for
as long as the process that loaded them.

### Proof 2 — the live server, probed read-only

```
GET /api/crons                      -> 401  "requires valid record authorization token"
GET /api/cronsXXX                   -> 404  "File not found."          (control)
GET /api/collections                -> 401                              (control)
GET /api/crons/internal_hq_sweep    -> 404  "File not found."
```

The last line is the decisive one. If any method beyond `POST` were registered
on `/api/crons/{id}`, the router would answer **401** (the superuser middleware
runs before the handler) or **405**. Instead it falls through to the *static
file* handler and 404s — the signature of a path with no `GET` route at all.
`/api/collections` proves 401-on-real-route is how this server behaves, and
`/api/cronsXXX` proves 404 is how it answers routes that do not exist.

### The OPTIONS probe is a trap — do not trust it

```
OPTIONS /api/crons/internal_hq_sweep   (with Origin + Access-Control-Request-Method)
-> 204, access-control-allow-methods: GET,HEAD,PUT,PATCH,POST,DELETE
```

This advertises `DELETE`. **It is meaningless.** It is PocketBase's default
CORS middleware emitting one static allow-list for every route on the server.
The 404 above disproves it directly: `GET` is in that header and `GET` does not
exist on the path. Never conclude a method exists from this header.

### The one thing `POST /api/crons/{id}` does

It **runs the job immediately**. On `internal_hq_sweep` that means sending real
SMS and email, and — because the sweep is claim-first (`internal_hq.pb.js:2139`
header comment) — consuming `remind_sent_at` / `followup_sent_at` on every row
it touches. It is the exact opposite of disabling. A previous manual run
consumed 9 follow-up claims. **Do not POST to this route.**

---

## 2. (b) The alternatives, and which one is real

| Option | Verdict |
|---|---|
| **Redeploy without the `cronAdd`** | ✅ The only real mechanism. |
| **Railway env flag** | ⚠️ No such flag exists today (`internal_hq.pb.js:2139` is unconditional). Adding one is itself a code change + redeploy — but it is the *right* one. See §3. |
| **Scale the service to zero** | ❌ Total outage. Railway still serves the API, HQ, the extension and the pendant (`CUTOVER-STATE.md`). This stops the product, not the cron. |
| **Starve it of `TWILIO_*` / `RESEND_API_KEY`** | ❌ **Actively harmful.** Claim-first means a sweep that cannot send still stamps the claim. Those reminders then never fire after cutover, silently. Already documented in `workers/wrangler.jsonc:161-166`. |
| **Edit `pb_hooks` on the volume** | ❌ Not possible. `Dockerfile:8` bakes hooks into `/app/pb_hooks`; the volume is `/pb_data`. No override path. |

### Blocker: the Railway CLI is not installed

`backend/deploy.sh` shells out to `railway up`. On this machine:

```
$ which railway
railway not found
```

So the PocketBase half cannot be executed from here at all until the CLI is
installed and authenticated, or the deploy is driven from the Railway
dashboard. This is the real access gap — not the API, which was never going
to work.

---

## 3. The recommended shape: split the risky build away from the cutover moment

Doing this as one big deploy at the cutover minute is the worst version: an
image build (minutes, unpredictable) sitting on the critical path, with the
Worker's trigger the only thing you can move quickly.

Instead, **make the flip a variable, not a deploy.** Two steps, days apart.

### Step A — ahead of time, behaviourally inert

Wrap the registration only. Do not touch the 500-line body.

```js
// backend/pb_hooks/internal_hq.pb.js:2139
// MIGRATION CONTROL, not tape: exactly one sweep may own a database.
// Default is "pocketbase" so this deploy changes nothing. At cutover the
// Railway variable ANTICIPY_SWEEP_OWNER=worker unregisters this job.
// REMOVE THIS GUARD AND THIS WHOLE cronAdd BLOCK once cutover is signed off.
if (($os.getenv("ANTICIPY_SWEEP_OWNER") || "pocketbase") === "pocketbase") {
cronAdd("internal_hq_sweep", "*/5 * * * *", () => {
  ...
});
}
```

Deploy it, then **verify nothing changed** (§4 gives the auth call):

```sh
curl -s -A "$UA" -H "Authorization: $SU" \
  https://backend-production-61e0a.up.railway.app/api/crons \
  | python3 -m json.tool | grep -A2 internal_hq_sweep
```

`internal_hq_sweep` must still be listed at `*/5 * * * *`. If it is missing,
the guard's default is inverted — roll back immediately.

Note the guard is read at hook-load time, so it takes effect on restart. That
is fine: changing a Railway variable restarts the service anyway, and a
restart is ~30-60s with no image build, versus minutes for `railway up`.

### Step B — the cutover itself

That is §5.

---

## 4. Credentials you need and do not currently have

`GET /api/crons` is superuser-gated. Nothing in `.env.local` authenticates to
it — `ANTICIPY_SERVICE_TOKEN` is the *hooks'* god credential
(`guard.pb.js:25`), not a PocketBase superuser, and PocketBase's own router
never sees it.

The verification step needs a real `_superusers` login:

```sh
SU=$(curl -s -A "$UA" -X POST \
  https://backend-production-61e0a.up.railway.app/api/collections/_superusers/auth-with-password \
  -H 'Content-Type: application/json' \
  -d '{"identity":"<superuser email>","password":"<password>"}' \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["token"])')
```

**Get this before cutover, not during it.** Every verification gate in §5
depends on it, and a cutover you cannot verify is not a cutover.

---

## 5. The atomic sequence

### Preconditions — all must hold

- [ ] `CUTOVER-STATE.md` step 3 is **DONE**: `/internal/*` rewrites point at the
      Worker. Swapping crons while HQ still writes to Railway leaves the team
      editing one database and being reminded from another.
- [ ] D1 is the system of record and is current with PocketBase.
- [ ] Superuser token in hand (§4).
- [ ] Railway CLI installed and authenticated, **or** dashboard access ready (§2).
- [ ] Step A guard already deployed and verified inert (§3).

### Direction of the swap: OFF first, then ON. Never the reverse.

The two sides are wildly asymmetric:

- **PocketBase off** = a restart. Tens of seconds, imprecise, hard to reverse.
- **Worker on** = one API call. Seconds, precise, instantly reversible.

So do the slow, sticky side **first**, while the fast lever is still parked in
the safe position. This trades an **overlap** for a **gap**, which is the right
trade: an overlap is duplicate SMS to real customers and is unrecoverable. A
gap is at most one 5-minute tick of *late* reminders — the todos still carry
their due chips and the next tick picks them up. Nothing is lost, only delayed.

### The steps

**1. Note the tick boundary.** The sweep runs at `:00 :05 :10 …`. Start
immediately *after* a tick so you have the widest window.

**2. Turn PocketBase's sweep off** — set the variable in the Railway dashboard
(or CLI), which restarts the service:

```
ANTICIPY_SWEEP_OWNER=worker
```

**3. GATE — prove it is off against LIVE.** Repo-green is not done.

```sh
curl -s -A "$UA" -H "Authorization: $SU" \
  https://backend-production-61e0a.up.railway.app/api/crons
```

`internal_hq_sweep` **must be absent**. `internal_hq_prune` must still be
present — its presence is the control that proves you are reading a live,
booted server and not a cached or half-started one. Do not proceed on a
timeout or a 401; re-auth and re-check.

**4. Turn the Worker's sweep on.**

> ### ⚠️ FREEZE OTHER DEPLOYS FIRST — read §8 before this step.
>
> `anticipy-api` is being redeployed by another session every ~3 minutes right
> now. **Every `wrangler deploy` re-applies `triggers.crons` from that
> session's copy of `wrangler.jsonc`.** If you enable the sweep with the REST
> PUT below and someone else's deploy lands from a checkout that still reads
> `["17 4 * * *"]`, the sweep is silently switched back off. No error, no
> alert — reminders just stop. This is the "deaf ears for 30 hours" shape.
>
> Therefore: **edit `wrangler.jsonc` and get that commit into every working
> copy that deploys**, and confirm no other session will deploy during the
> swap, *before* touching the schedule.

Edit `migration/workers/wrangler.jsonc:169-171` so config and reality do not
drift — this is the source of truth, not the PUT:

```jsonc
"triggers": {
  "crons": ["*/5 * * * *", "17 4 * * *"]
},
```

then apply. Preferred — one call, no code redeploy, stable documented API:

```sh
TOK=$(grep -E '^oauth_token' \
  ~/Library/Preferences/.wrangler/config/default.toml | sed 's/.*= *"//; s/"$//')
ACCT=114587b715e702461766369b01d42fc7

curl -s -X PUT \
  -A "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)" \
  -H "Authorization: Bearer $TOK" \
  -H 'Content-Type: application/json' \
  "https://api.cloudflare.com/client/v4/accounts/$ACCT/workers/scripts/anticipy-api/schedules" \
  -d '[{"cron":"*/5 * * * *"},{"cron":"17 4 * * *"}]'
```

> **The PUT REPLACES the entire set.** Both crons must be in the body. Sending
> only `*/5` silently deletes the prune, and nothing will tell you — the
> D1 volume just starts growing.

Alternative: `npx wrangler triggers deploy --config migration/workers/wrangler.jsonc`
— reads the file so it cannot drift, but wrangler 4.129.0 prints
`🚧 wrangler triggers deploy is an experimental command`. Prefer the PUT.
`wrangler deploy` also works but redeploys the whole script, which is a much
larger blast radius than this change needs.

**5. GATE — prove it is on against LIVE:**

```sh
curl -s -A "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)" \
  -H "Authorization: Bearer $TOK" \
  "https://api.cloudflare.com/client/v4/accounts/$ACCT/workers/scripts/anticipy-api/schedules"
```

Both crons must be listed.

**6. GATE — prove it actually fired and sent.** The schedule existing is not
the sweep working; `is_the_brain_live.py`'s blind spot is exactly this shape.
Watch a real tick:

```sh
npx wrangler tail anticipy-api --config migration/workers/wrangler.jsonc
```

Across one 5-minute boundary you must see a `scheduled` invocation. Then
confirm rows moved — a `remind_sent_at` newly stamped in D1, and one real
message delivered. **Quiet is not green.** If the tick is silent, roll back.

### Rollback

- **Worker off** (fast, do this first): PUT the schedules back to
  `[{"cron":"17 4 * * *"}]`.
- **PocketBase on**: unset `ANTICIPY_SWEEP_OWNER` (or set it to `pocketbase`)
  and let it restart; re-verify via `GET /api/crons`.

---

## 6. Things found while writing this that are wrong elsewhere in the repo

1. **`migration/CUTOVER-STATE.md:80-82`** — "PocketBase turns out to expose
   `GET /api/crons` and `internal_hq_sweep` is listed there, so the swap is
   reachable without the Railway CLI." **False, and dangerous.** Listing is not
   removing. The only write on that surface is `POST /api/crons/{id}`, which
   *runs* the sweep. Someone acting on this sentence to "do the swap via the
   API" would fire real reminders and burn claims. Fix the sentence.

2. **`migration/workers/wrangler.jsonc:148-151`** — states the UTC/TZ risk
   backwards: "Harmless for the prune … NOT harmless for the sweep." The sweep
   is `*/5 * * * *` and, verified by reading `internal_hq.pb.js:2139-2640`, has
   **no** hour-of-day, `toLocale*`, or `ANTICIPY_INTERNAL_TZ` logic — it is
   driven entirely by absolute due timestamps, so container TZ cannot affect
   it. The fixed-hour job is the *prune*. The conclusion (both are fine)
   survives; the reasoning is inverted and should be corrected before someone
   plans around it.

3. **`ANTICIPY_ENV: "staging"` is inert and misleading.** It is declared in
   `wrangler.jsonc:193` and bound on the live Worker, but `grep -rn ANTICIPY_ENV src/`
   returns **nothing**. Nothing reads it. There is no staging-mode send
   suppression anywhere in `src/cron.ts`. With `TWILIO_*` and `RESEND_API_KEY`
   all bound, **the absent cron trigger is the only thing standing between this
   Worker and real SMS to real customers.** Anyone reading "staging" and
   assuming a safe mode is wrong.

4. **Secret-name drift.** `wrangler.jsonc:181-184` documents
   `ANTICIPY_VAULT_KEY_GCM` as the re-wrapped key that cutover generates, and
   says the old `ANTICIPY_VAULT_KEY` is "deliberately NOT carried". The live
   Worker has `ANTICIPY_VAULT_KEY` and **not** `ANTICIPY_VAULT_KEY_GCM`. Also
   absent versus that comment: `ANTICIPY_AUTH_SECRET`, `GOOGLE_API_KEY`.
   None of these are on the sweep's path, so they do not block this swap — but
   the vault one contradicts `runbooks/reencrypt_vault.md` and should be
   settled before cutover.

---

## 8. Concurrent deploys are live on `anticipy-api` — the biggest hazard here

Observed while writing this file, 2026-09-04, from the deployments API:

```
2026-09-04T21:38:26Z  omar@anticipy.ai  wrangler  a3bf0db2
2026-09-04T21:35:25Z  omar@anticipy.ai  wrangler  90c72c6a
2026-09-04T21:32:47Z  omar@anticipy.ai  wrangler  b2e33d44
2026-09-04T21:14:06Z  omar@anticipy.ai  wrangler  113579f4
```

Another session is deploying this Worker every ~3 minutes. **None of these are
mine — this session deployed nothing.**

Two consequences:

1. **`modified_on` on the schedules endpoint is not a change-detector.** It
   advanced 21:32:49 → 21:38:27 while the cron set stayed `["17 4 * * *"]`,
   because each script deploy rewrites the schedule set even when the crons are
   identical. Every gate in §5 must assert on the **`cron` values**, never on
   `modified_on` or `created_on`.

2. **A concurrent deploy will silently revert the swap.** `wrangler deploy`
   applies `triggers.crons` from its own `wrangler.jsonc`. Enabling the sweep
   out-of-band with the REST PUT, while another checkout still says
   `["17 4 * * *"]`, means the next deploy turns the sweep back off with no
   signal. Since PocketBase's sweep is *also* off by then, that is **both
   sweeps off** — every reminder, nudge and digest stops, and the first person
   to notice is a customer.

**This is why §5 step 4 says freeze deploys and land the `wrangler.jsonc` edit
first.** The PUT is the fast actuator; the committed config is what makes it
stick. Do not use one without the other.

A cheap standing guard after cutover — assert the live set, not the file:

```sh
curl -s -A "$UA" -H "Authorization: Bearer $TOK" \
  "https://api.cloudflare.com/client/v4/accounts/$ACCT/workers/scripts/anticipy-api/schedules" \
  | python3 -c 'import sys,json; c=sorted(s["cron"] for s in json.load(sys.stdin)["result"]["schedules"]); print(c); exit(0 if c==["*/5 * * * *","17 4 * * *"] else 1)'
```

Worth a gate leg alongside `are_the_ears_live.py`, and for the same reason:
the failure is silence, and nothing currently watches for it.

---

## 7. Evidence log (all read-only, 2026-09-04)

```
PocketBase  v0.30.4                       backend/Dockerfile:3
            GET  /api/health        200   {"message":"API is healthy."}
            GET  /api/crons         401   real route, superuser-gated
            GET  /api/cronsXXX      404   control: absent routes 404
            GET  /api/crons/internal_hq_sweep
                                    404   => no GET/DELETE/PATCH on {id}
            apis/cron.go @v0.30.4         GET "" + POST "/{id}" ONLY

Worker      anticipy-api            200   server: cloudflare, cf-ray present
            live schedules                ["17 4 * * *"]  — sweep absent ✓
            bindings                      DB(d1), EVIDENCE(r2),
                                          PAIR_CODE_COUNTER(do), ASSETS
            secrets                       TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN,
                                          TWILIO_PHONE_NUMBER, TWILIO_FROM,
                                          RESEND_API_KEY  — sweep CAN send
            account                 114587b715e702461766369b01d42fc7

Tooling     wrangler 4.129.0, OAuth, omar@anticipy.ai
            railway CLI             NOT INSTALLED  <- blocks the PocketBase half

Concurrency anticipy-api deployed by ANOTHER session at 21:32:47, 21:35:25,
            21:38:26 (~every 3 min). Not this session. See §8.
```

**Nothing in this runbook was executed.** No POST/PATCH/DELETE was sent to
Railway; no Railway, Vercel, DNS or Porkbun setting was touched; no Cloudflare
write was made. The only Cloudflare calls were GETs plus one
`wrangler triggers deploy --dry-run`, which exits before deploying.
