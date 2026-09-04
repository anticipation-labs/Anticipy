# CUTOVER — from today to Railway-off

Ordered, numbered, reversible. Every step has **preconditions**, **commands**,
**verify**, **rollback**. Phases are independently shippable: you can stop
after any phase and be in a supportable state indefinitely.

Companions: `CLIENTS.md` (who holds the old address), `VERIFICATION.md` (how to
prove nothing broke), `EXPORT.md` (get the data out), `SECRETS.md` (credential
inventory), `BLOCKERS.md` (what is stopping this today).

---

## The shape

| Phase | What moves | Risk | Reversible by |
|---|---|---|---|
| **0** | nothing — unblock the account, measure the tail | none | n/a |
| **1** | static assets + evidence host → R2 | low | flip an env var |
| **2** | `anticipy.ai` DNS → Cloudflare nameservers | **medium** | NS revert (slow) |
| **3** | `api.anticipy.ai` stable name + client rebuilds | low | clients keep old fallback |
| **4** | website → Workers, behind a preview URL | low | DNS unchanged |
| **5** | website → Workers, on the real domain | medium | DNS record flip |
| **6** | backend → Worker + D1 | **high** | `api.` record flip |
| **7** | brain → Containers | high | Railway service resume |
| **8** | decommission | irreversible | **nothing — hence the gate** |

**Phases 1–5 do not touch PocketBase.** That is deliberate: it is most of the
value and almost none of the risk, and it is worth shipping on its own even if
Phase 6 is never attempted.

---

# PHASE 0 — Unblock and instrument

Nothing moves. This phase exists because `BLOCKERS.md` establishes that four
apparently separate problems are one problem: **the Cloudflare account is on the
Workers Free plan.**

### 0.1 Upgrade to Workers Paid and enable R2

**Precondition:** owner has a payment method and has agreed to $5/month plus
usage.

Dashboard only — there is no wrangler command for the plan change.
Workers & Pages → Plans → Workers Paid. Then R2 → Enable.

**Verify:**

    wrangler containers list          # must NOT say "requires the Workers Paid plan"
    wrangler r2 bucket list           # must NOT say "Please enable R2 [code: 10042]"

**Rollback:** downgrade. Free of charge, and nothing has been built on it yet.

### 0.2 Confirm the R2 backups actually exist

**This is the single most important step in the document.** `BLOCKERS.md`
records that `backend/pb_migrations/1700000053_off_volume_backups.js` points
PocketBase's scheduled backups at `anticipy-pocketbase-backups-production`,
**on an account where R2 was not enabled.** Either they are landing in a
different account, or they have been failing silently. That bucket is the
stated safety net for discarding the Railway volume.

    wrangler r2 bucket list | grep anticipy-pocketbase-backups-production
    wrangler r2 object list anticipy-pocketbase-backups-production --limit 20

**Verify:** objects exist, and the newest is **less than 48 hours old**.

**If it is empty or stale: STOP.** Do not proceed past Phase 0. Fix backups
first, or accept — in writing, from the owner — that there is no restore point.

### 0.3 Instrument the tail

Per `CLIENTS.md` §4.5. You cannot evaluate the Phase 8 gate without this, and a
tail you did not measure from the start is one you cannot prove has ended. Log,
on the old backend, per request: `Host`, `X-Anticipy-Agent-ID`
(`guard.pb.js:200`–`:232`), presence of an account token (`guard.pb.js:404`),
and User-Agent.

**Verify:** a week later, you can answer "how many distinct agent ids called the
Railway hostname yesterday".

### 0.4 Baseline the website

    ./migration/runbooks/smoke.sh https://www.anticipy.ai \
      --json migration/runbooks/baseline-prod.json

**Verify:** `fail 0`. Measured 2026-09-03: **62 pages, 97 routes, 159 pass, 0
fail**. Commit that JSON — it is the oracle every later phase diffs against.

### Go / no-go — Phase 0

- [ ] `wrangler containers list` and `r2 bucket list` both succeed
- [ ] R2 backup bucket listed **by a human**, newest object < 48h
- [ ] Tail logging deployed and returning data
- [ ] `baseline-prod.json` committed, `fail 0`
- [ ] `ANTICIPY_SERVICE_TOKEN` and `ANTICIPY_VAULT_KEY` in hand (`BLOCKERS.md`)

---

# PHASE 1 — Static assets and the evidence host → R2

Lowest risk, highest immediate value, touches no client.

### 1.1 Delete what should not be shipped at all

**Precondition:** none.

    du -sh public/                       # 67M measured 2026-09-03
    du -sh public/images/originals_backup # 23M, unreferenced
    grep -rn "originals_backup" src/ || echo "NO REFERENCES — safe to delete"

    git rm -r public/images/originals_backup

**Verify:** `npm run build` succeeds; smoke stays green.
**Rollback:** `git revert`. The bytes are in git history.

### 1.2 Create the buckets

    wrangler r2 bucket create anticipy-assets
    wrangler r2 bucket create anticipy-evidence

**Verify:** `wrangler r2 bucket list` shows both.
**Rollback:** `wrangler r2 bucket delete <name>` — empty buckets, no data.

### 1.3 Move the evidence host

**Precondition:** 1.2 done. Read `backend/pb_hooks/evidence.pb.js` first.

This is the highest-value single move in Phase 1, because evidence blobs are
what filled the 5 GB Railway volume on 2026-08-15 and took PocketBase down
entirely ("disk I/O error", crash loop — `evidence.pb.js:~228`). Getting them
off a fixed-size volume removes a whole class of outage.

The constraint that governs it: evidence URLs are fetched by **Twilio**, from
Twilio's infrastructure, as an SMS `MediaUrl`. The URL is built at
`evidence.pb.js:212`–`:225` from `ANTICIPY_PUBLIC_URL`, falling back to the
origin of `ANTICIPY_TWILIO_WEBHOOK_URL`.

**The thing that makes this safe:** the share window is **15 minutes** and
**5 fetches** (`evidence.pb.js:158`–`:159`). No evidence URL in any already-sent
message outlives a 15-minute quiet period. There is no long tail here.

**Rollback:** unset `ANTICIPY_PUBLIC_URL`; new shares revert to the old origin
within one restart. Old URLs keep working — the blobs are still on the volume
until Phase 8.

### 1.4 Point the site's static assets at R2

    npx wrangler r2 object put anticipy-assets/videos/ --file … # or rclone/aws-cli

**Verify:** every asset 200s from the R2 custom domain; smoke green.
**Rollback:** revert the asset base env var; `public/` is still in the build.

### Go / no-go — Phase 1

- [ ] `smoke.sh` against prod: `fail 0`, and `smoke_diff.py` vs baseline clean
- [ ] An evidence photo sent by SMS **arrives with the picture visible** —
      test with a real message, not a curl. Twilio fetching is the whole point.
- [ ] Railway volume usage measurably falling
- [ ] Rollback rehearsed once (unset the var, confirm old path still serves)

---

# PHASE 2 — Move the DNS zone to Cloudflare

**This is the first genuinely risky step, and it is deliberately alone in its
phase.** Nothing else changes on the day you do it.

### 2.1 Why it is needed and why it is scary

Workers custom domains and Workers routes require the zone to be on
Cloudflare's nameservers. Today:

    $ dig +short anticipy.ai NS
    salvador.ns.porkbun.com.   fortaleza.ns.porkbun.com.
    curitiba.ns.porkbun.com.   maceio.ns.porkbun.com.

    $ dig +short anticipy.ai A          -> 76.76.21.21     (Vercel)
    $ dig +short www.anticipy.ai CNAME  -> cname.vercel-dns.com.

Moving nameservers moves **every** record: MX, SPF, DKIM, DMARC, any vendor
verification TXT. **Miss one and mail stops.** Mail failures are silent to you
and loud to everyone else.

### 2.2 Export the existing zone FIRST

**Precondition:** Porkbun access.

Export the full record set from Porkbun (dashboard export, or the API) to
`migration/config/porkbun-zone-<date>.txt`. Then independently confirm the
records that hurt most if lost:

    for t in A AAAA MX TXT CNAME NS SOA CAA; do
      echo "--- $t ---"; dig +short anticipy.ai $t
    done
    dig +short www.anticipy.ai CNAME
    dig +short _dmarc.anticipy.ai TXT
    dig +short anticipy.ai TXT | grep -i spf

**Verify:** the exported file contains every MX and every TXT the dig loop
printed. Diff them by hand. **Do not skip this.**

### 2.3 Lower TTLs — a full old-TTL ahead of the change

**Precondition:** 2.2 complete.

Current TTLs measured 2026-09-03: `anticipy.ai A` = **582 s** remaining of a
600 s record; `www` CNAME likewise. So the pre-lowering wait is short — but do
it anyway, because it is what makes Phase 5 and Phase 6 reversible in minutes
rather than hours.

In Porkbun, set **every** record to TTL **300**. Then wait **at least the
previous TTL** (600 s) so old cached copies expire.

    dig anticipy.ai A +noall +answer          # want ttl <= 300
    dig www.anticipy.ai +noall +answer

**Rollback:** raise them again. Costless.

### 2.4 Add the zone to Cloudflare, then switch NS

    # Create the zone in the dashboard, then confirm what Cloudflare imported:
    wrangler --version    # (zone records are dashboard/API, not wrangler)

Cloudflare auto-imports records on zone creation. **Audit that import against
`porkbun-zone-<date>.txt` line by line before switching NS.** Set every proxied
record to **DNS-only (grey cloud)** for now — proxying is a separate change and
must not ride along with the NS move.

Then change nameservers at Porkbun to the two Cloudflare assigned.

**Verify — over 24 hours, not 5 minutes:**

    dig +short anticipy.ai NS                 # want the cloudflare pair
    dig @1.1.1.1 +short anticipy.ai A         # want 76.76.21.21 still
    dig @8.8.8.8 +short www.anticipy.ai
    dig +short anticipy.ai MX                 # UNCHANGED
    # And the one that actually matters:
    #   send an email to a real address on this domain, and reply to it.

**Rollback:** set the Porkbun nameservers back. **This is slow** — up to 48h of
propagation — which is why 2.2's export and 2.4's audit are mandatory rather
than advisory. This is the least reversible step before Phase 8.

### Go / no-go — Phase 2

- [ ] Zone export saved and diffed against the Cloudflare import, by a human
- [ ] All TTLs ≤ 300, and one previous-TTL has elapsed
- [ ] `dig` from at least three resolvers agrees, 24h after the switch
- [ ] **Mail sent and received on the domain, both directions**
- [ ] Site still served by Vercel, smoke green — nothing should have moved yet

---

# PHASE 3 — The stable name, and the client rebuilds

Full detail in `CLIENTS.md` §3 and §5. Summary here for ordering.

**Precondition:** Phase 2 complete (or, if you take `CLIENTS.md` §3.1's advice,
this can run on Porkbun *before* Phase 2 — it is independent).

1. `api.anticipy.ai` → CNAME → Railway host, TTL 300. Add as a Railway custom
   domain so a certificate is issued for the new name.
2. Change the nine baked URLs (`CLIENTS.md` §1.1) to `https://api.anticipy.ai`.
3. Add the macOS `UserDefaults` escape hatch and the extension's
   `/agent/relocate` consumer (`CLIENTS.md` §3.3, §4.4).
4. Fix `website/index.html:408`.
5. Ship: iPhone (`workflow_dispatch` — the workflow only auto-fires on
   `jose_anticipy_system`, `.github/workflows/ios-testflight.yml:4`), Mac
   (`clients/macos/Tools/build_release.sh`), extension zip.

**Verify:**

    curl -sS -o /dev/null -w '%{http_code} %{ssl_verify_result}\n' \
      https://api.anticipy.ai/api/health         # want: 200 0

and, in the tail log from 0.3, requests arriving on the **new** Host header.

**Rollback:** the old hostname still answers; unupdated clients never noticed.

### Go / no-go — Phase 3

- [ ] `api.anticipy.ai` serves valid TLS and a 200 health check
- [ ] iPhone build processed by Apple; Mac zip notarized and stapled
- [ ] Tail log shows real traffic on the new Host
- [ ] **The Railway-hostname tail is trending down, and you can plot it**

---

# PHASE 4 — Website on Workers, on a preview URL

**The whole phase is invisible to users.** DNS is untouched.

**Precondition:** Phase 0. `@opennextjs/cloudflare@1.15.1` is already a
devDependency and `wrangler.jsonc` + `open-next.config.ts` already exist in the
tree — `spike/website-verification.md` proved 60/60 pages and 84/84 routes on
workerd.

**Pin the OpenNext version.** `spike/website-verification.md` records that
1.16.0 raised its `next` peer to `>=15`, and this site is on exactly
`next@14.2.35`. **Leaving Vercel requires no Next.js upgrade at 1.15.1 and does
require one at 1.16.0.** Do not let a caret bump make that decision for you.

### 4.1 Set secrets

Per `SECRETS.md`. Never `vars` for anything that authenticates.

    wrangler secret put SUPABASE_SERVICE_ROLE_KEY
    wrangler secret put STRIPE_SECRET_KEY
    wrangler secret put FELLOWSHIP_ORIGIN      # or vars — it is a hostname
    # …see SECRETS.md for the full list

`NEXT_PUBLIC_*` are **inlined into the client bundle at build time** and must be
build-time env, not Worker secrets.

### 4.2 Build and deploy to the workers.dev preview

    npx opennextjs-cloudflare build
    npx wrangler deploy --dry-run          # check the gzip number
    npx wrangler deploy

**Watch the bundle.** Measured 2.63 MB gzip against a 3 MB free ceiling — 88%.
On Workers Paid the ceiling is 10 MB, so Phase 0 also fixes this.

### 4.3 Verify against the preview

    ./migration/runbooks/smoke.sh https://anticipy-site.<subdomain>.workers.dev \
      --json migration/runbooks/cf-preview.json
    ./migration/runbooks/smoke_diff.py \
      migration/runbooks/baseline-prod.json migration/runbooks/cf-preview.json

**Verify:** `IDENTICAL (modulo accepted)` and `fail 0`. Then the manual list in
`VERIFICATION.md` §3 — the things a status code cannot see.

**Rollback:** none needed. Nothing is pointed at it.

### Go / no-go — Phase 4

- [ ] `smoke_diff` clean against the Phase 0 baseline
- [ ] `VERIFICATION.md` §3 manual checklist signed off
- [ ] Stripe **test-mode** webhook delivered to the preview and 200s
- [ ] "Add visitor location headers" managed transform enabled on the zone —
      `/api/geo` needs it (`spike/website-verification.md`)
- [ ] Bundle size recorded, with headroom noted

---

# PHASE 5 — Website on the real domain

### 5.1 Reproduce the apex → www redirect

**Do not skip this.** `anticipy.ai` 307s to `www.anticipy.ai`, and **that
redirect is Vercel project configuration, not code** — it is not in
`next.config.mjs`, not in `src/middleware.ts`, and `vercel.json` contains only
a cron entry. Verified:

    $ curl -sS -D- -o /dev/null https://anticipy.ai/ | grep -i '^location'
    location: https://www.anticipy.ai/

Leaving Vercel therefore **deletes** this redirect unless you rebuild it. If you
forget, every inbound link to the apex breaks, and the smoke script will not
catch it — it takes a base URL and both hosts answer.

Rebuild it as a Cloudflare Bulk Redirect (or a Redirect Rule) on the zone:
`anticipy.ai/*` → `https://www.anticipy.ai/$1`, 301, preserving query string.

### 5.2 Cut DNS

**Precondition:** Phase 4 green; TTLs at 300 since Phase 2; 5.1 rule created
and tested.

Add `www.anticipy.ai` as a **Custom Domain** on the Worker, which creates the
proxied record. Keep the old Vercel values written down.

**Verify — immediately and then at 15 minutes:**

    dig +short www.anticipy.ai
    curl -sS -D- -o /dev/null https://www.anticipy.ai/ | grep -i '^server'
    curl -sS -D- -o /dev/null https://anticipy.ai/    | grep -i '^location'

    ./migration/runbooks/smoke.sh https://www.anticipy.ai --json cf-live.json
    ./migration/runbooks/smoke_diff.py baseline-prod.json cf-live.json

**Rollback — the reason TTL is 300:** point `www` back at
`cname.vercel-dns.com` and disable the redirect rule. Full recovery in ~5
minutes. **The Vercel project must not be deleted in this phase** — it is the
rollback target.

### 5.3 Move the cron

`vercel.json` schedules `/api/cron/daily-digest` at `0 14 * * *`. Vercel Cron
dies with the Vercel project. Re-create it as a Workers Cron Trigger and
**confirm it has fired at least once** before Phase 8.

### Go / no-go — Phase 5

- [ ] `smoke_diff` clean against baseline, run against the **real** domain
- [ ] Apex redirect verified with curl, not assumed
- [ ] Stripe **live** webhook delivering and 200ing
- [ ] `/api/cron/daily-digest` observed firing on Workers
- [ ] 24 hours elapsed with no rollback, before starting Phase 6
- [ ] **Vercel project still exists**

---

# PHASE 6 — The backend

**The high-risk phase.** Everything before this was reversible in minutes.

Read `migration/spec/CONTRACT.md` and `migration/d1/` before starting. The
difficulty is not volume, it is shape: authorization is implemented by
**parsing and rewriting PocketBase filter strings** (`guard.pb.js` requires the
caller's filter to contain `owner_ref="X"` and to contain no `||`;
`research_lane.pb.js` appends `&& lane != "research"`). Every client speaks the
generic `/api/collections/{name}/records` API. **There is no purpose-built API
layer to swap.** A port that exposes tidy endpoints instead has not implemented
the contract, it has replaced it — and the clients in the field cannot be told.

### 6.1 The gate: contract tests green against BOTH backends

**Nothing in Phase 6 proceeds until this passes.** `contract_tests.py` is 2,525
lines and takes `BASE_URL`, by design, so it can be run twice and diffed.

    export ANTICIPY_SERVICE_TOKEN=… ANTICIPY_INTERNAL_KEY=…   # SECRETS.md

    BASE_URL=https://api.anticipy.ai \
      pytest migration/spec/contract_tests.py -q --junitxml=pb.xml

    BASE_URL=https://<worker-preview>.workers.dev \
      pytest migration/spec/contract_tests.py -q --junitxml=cf.xml

**Verify:** identical pass/fail/skip per test id. A test that **skips** on both
proves nothing — `BLOCKERS.md` records that **175 of 189 tests skip without
`ANTICIPY_SERVICE_TOKEN`**. A run that is green because it skipped is the exact
failure this gate exists to prevent. **Count the passes, not the exit code.**

### 6.2 Export, and verify the export

Follow `EXPORT.md` end to end. Two stores have no second copy: the brain's
per-owner `memory.db` (on a *separate* Railway volume), and
`internal_passwords`, which is ciphertext only the dying binary can read.
**`reencrypt_vault.md` must be done before cutover** — if it is not, you learn
the vault is unreadable only after the source is gone.

### 6.3 Import to D1 and reconcile

`import_d1.py` emits SQL, runs `wrangler d1 execute`, and reconciles source
against destination counts.

**Verify:** row counts match **per collection**, not in aggregate. Spot-check
the collections whose loss would be worst: `evidence`, `internal_passwords`,
`jobs`, `agents`.

### 6.4 Freeze, switch, watch

Per `CLIENTS.md` §4.2: **do not run two writable backends.** There is one
database and no reconciliation semantics for filter-string authorization.

1. Announce a maintenance window.
2. **Freeze writes on PocketBase** (reject mutating requests; keep reads).
3. Final incremental export + import; reconcile again.
4. Repoint `api.anticipy.ai` → Worker.
5. Watch.

A client still on the old host now gets **read-only degraded**, which is
recoverable. It does **not** get to write rows into a database nobody will
ever read again, which is not.

**Verify:**

    curl -sS https://api.anticipy.ai/api/health
    BASE_URL=https://api.anticipy.ai pytest migration/spec/contract_tests.py -q

Then, on real devices: iPhone loads and posts; extension claims a job;
Mac app syncs; **an SMS with an evidence photo arrives with the photo**.

**Rollback:** point `api.anticipy.ai` back at Railway and unfreeze. TTL 300, so
minutes. Rows written to D1 during the window are **orphaned** — export them
before unfreezing or accept the loss, explicitly.

### Go / no-go — Phase 6

- [ ] Contract tests: identical results both backends, **with the service
      token set**, and the pass count recorded (not just "green")
- [ ] Export verified; per-collection counts reconciled
- [ ] Vault re-encrypted per `reencrypt_vault.md`
- [ ] Brain state exported from the second volume
- [ ] Every client class exercised on real hardware post-switch
- [ ] Rollback rehearsed on staging, timed, and under 10 minutes

---

# PHASE 7 — The brain

`brain/` is 22,614 lines of Python running a long-running supervisor loop
(`python -m brain.supervisor`) against per-owner SQLite on a Railway volume.
Containers is the target and, per `BLOCKERS.md`, **the only one**: there is no
free substitute and the alternative is rewriting it as TypeScript on Cron
Triggers plus Durable Objects.

**Precondition:** Phase 6 stable for 7 days. Workers Paid (Phase 0).

The state directory is the hard part, not the code. `ANTICIPY_STATE_ROOT`
(default `/data/owners`) holds `<owner_ref>/memory.db` — the assistant's
long-term memory. Containers are ephemeral; that file is not. It needs durable
storage (R2, or D1) and a migration, and **`EXPORT.md` §3 must have exported it
before this phase starts**.

`brain` is repointed by `ANTICIPY_PB` (`brain/worker.py:43`,
`brain/supervisor.py:29`) — an env var and a restart.

**Rollback:** resume the Railway worker service; set `ANTICIPY_PB` back.
Keep it deployed and scaled to zero, not deleted.

### Go / no-go — Phase 7

- [ ] Memory survives a container restart — **verified by restarting it**
- [ ] Cron behaviour matches: the 2 `cronAdd` jobs observed firing
- [ ] A full task round-trips: SMS in → job → extension → evidence → SMS out
- [ ] 7 days stable before Phase 8

---

# PHASE 8 — Decommission

**Irreversible. Everything above exists so this step is boring.**

### 8.1 The gate — all five, or Railway keeps running

Restated from `CLIENTS.md` §4.3 because this is where it is enforced:

1. `api.anticipy.ai` has served Cloudflare for **14 consecutive days**, no rollback.
2. The old Railway hostname has logged **zero real-client requests for 14
   consecutive days**, per the Phase 0.3 tail log. **Measured, not assumed.**
3. `EXPORT.md` complete and verified — counts reconciled, blobs downloaded,
   vault re-encrypted and **decrypted once from the new key to prove it**.
4. Brain per-owner state exported from the second volume and verified.
5. R2 backups listed by a human and current.

> **Railway stays paid and running until all five are true.** Any one false ⇒
> it keeps running. The monthly cost is a rounding error against the data.

### 8.2 Order — the volume is last, and separate

    # 1. Scale to zero. DO NOT DELETE. Leave for 30 more days.
    #    A scaled-to-zero service can be resumed; a deleted volume cannot.

    # 2. After 30 quiet days at zero, and only then:
    #    snapshot both volumes one final time, off Railway, verified by
    #    restoring the snapshot somewhere and opening the database.

    # 3. Only after a RESTORE HAS BEEN PROVEN, delete the services.

**Verify a restore, do not verify a backup.** A backup you have never restored
is a hypothesis.

### 8.3 Vercel

Delete only after Phase 5 has been stable for 30 days. It is the website's
rollback target and it is nearly free to keep.

### Go / no-go — Phase 8

- [ ] All five conditions in 8.1, each with evidence attached
- [ ] Final snapshot **restored and opened** somewhere else
- [ ] Owner has explicitly signed off on the irreversible step
- [ ] 30 days at scale-zero elapsed before any deletion

---

## Unverified

- **Cloudflare Containers' actual limits** — memory, CPU, runtime, whether a
  long-running supervisor loop is supported at all, and what durable storage a
  container may attach. Phase 7 is written against the *shape* of the problem,
  not against verified product limits. **Verify before committing to Phase 7**;
  if Containers cannot host a persistent loop, Phase 7 becomes a rewrite and
  should be re-planned, not retried.
- **Whether Cloudflare's zone import captures every Porkbun record type.**
  Phase 2.2's manual diff exists because I could not verify this.
- **TestFlight and Chrome Web Store review times** — `CLIENTS.md` "Unverified".
- **The 15-minute evidence share window vs. Twilio's actual fetch latency.**
  `evidence.pb.js:158` sets 15 minutes; I did not verify Twilio always fetches
  within it. If it sometimes does not, evidence photos are *already*
  intermittently failing and Phase 1.3 is not the cause.
- **Whether D1 can hold the dataset.** `data.db` is ~264 MB per `EXPORT.md`.
  I did not verify the current per-database D1 size limit. **Check before
  Phase 6.3** — discovering it at import time is discovering it too late.
- **Whether freezing writes on PocketBase is achievable** without a code change
  to `backend/pb_hooks/`. Phase 6.4 assumes it is. If it needs a hook, that hook
  must be written and deployed in Phase 6.1, not improvised in the window.
- **Bulk Redirects vs Redirect Rules** for 5.1 — which is available on the
  account's plan, and the per-plan rule quota. Both exist; I did not verify
  entitlement.
