# VERIFICATION — proving nothing broke

The owner asked to test every page end to end. This document says what "every"
means here (**62 pages, 97 API routes**), what already exists to test them with,
what does not, and how to run the part that does.

Artifacts in this directory:

| File | What it does |
|---|---|
| `smoke.sh` | probes all 62 pages and all 97 routes against any base URL |
| `smoke_diff.py` | diffs two `smoke.sh --json` runs — the actual cutover gate |

---

## §1. The inventory, and a correction

Derived from the filesystem, not typed:

    $ find src/app -name page.tsx  | wc -l      # 62
    $ find src/app -name route.ts  | wc -l      # 97

**97, not 94.** The brief for this work said 94 API routes; the tree has 97.
Two commands, both reproducible. Of those 97:

    $ # routes exporting a GET handler
    $ for f in $(find src/app -name route.ts); do \
        grep -qE '^export (async )?function GET|^export const GET' $f && echo x; done | wc -l
    51
    $ # routes with no GET at all
    46

**46 routes have no GET.** That single fact shapes everything below: you cannot
verify them by fetching them, and the ones you *could* verify by POSTing include
`/api/webhooks/stripe`, `/api/pre-orders/checkout`, and `/api/waitlist`. A test
suite that exercises those against production charges cards and sends mail.

Dynamic segments needing a sample value — 2 pages, 11 routes:

    pages   /crm/manufacturing/[folder]   /crm/manufacturing/file/[id]
    routes  /c/[handle]   /api/engine/twilio/voice-script/[intentId]
            /api/crm/{users,files,todos,expenses,contacts,decisions}/[id]
            /api/crm/users/[id]/password   /api/crm/{files,todos}/[id]/comments

---

## §2. What exists today, and what it actually covers

### 2.1 Playwright — real, working, and narrow

`playwright.config.ts` is configured and functional:

- `testDir: "./tests"` (`:4`)
- `baseURL: process.env.PLAYWRIGHT_BASE_URL || "http://localhost:3000"` (`:12`)
- `webServer` auto-starts `npm run dev` **unless** `PLAYWRIGHT_BASE_URL` is set
  (`:21`–`:28`)

That last point is the useful one: **it already supports running against a
deployed URL** with no config change.

    $ npx playwright test --list
    Total: 16 tests in 7 files

| Spec | Covers |
|---|---|
| `tests/crm/gate.spec.ts` | password gate, name picker |
| `tests/crm/dashboard.spec.ts` | dashboard |
| `tests/crm/todos.spec.ts` | create + delete a todo **via API** |
| `tests/crm/expenses.spec.ts` | CSV export endpoint |
| `tests/crm/log-receiver.spec.ts` | `POST /api/log` writes a row; rejects anon |
| `tests/crm/voice-decisions-burn-contacts-feed.spec.ts` | 7 CRM pages render |
| `tests/v6/upload-audio-no-live-mic.spec.ts` | audio upload path |

**Coverage, stated plainly:**

| | Covered | Total | Not covered |
|---|---|---|---|
| Pages | 12 (all under `/crm`) | 62 | **50** |
| API routes | ~11 | 97 | **~86** |

`find src/app/crm -name page.tsx` → 12, and every Playwright page assertion is
one of those 12. **Nothing outside `/crm` has a single browser test** — not the
marketing pages, not `/app`, not onboarding, not pre-orders, not `/internal`.

### 2.2 Two warnings about the Playwright suite

1. **It is destructive.** `todos.spec.ts` creates and deletes rows;
   `log-receiver.spec.ts` writes a row. Pointing `PLAYWRIGHT_BASE_URL` at
   production writes to production. Use a preview, or accept the rows.
2. It needs `CRM_PASSWORD` (`gate.spec.ts:14`). Without it the gate spec fails
   and the rest cascade.

### 2.3 The other two suites — neither tests the website

- **`pytest`** — `pytest.ini` sets `testpaths = tests`; 160 `.py` files. This is
  the **product** suite (brain, engine, backend behaviour), not the website. It
  does not exercise a single Next.js route.
- **`__tests__/dedup.test.mts`** — **orphaned.** `package.json` has no `test`
  script (`scripts` is `dev`/`build`/`start`/`lint`). Its own header says run it
  with `node --experimental-strip-types --test __tests__/dedup.test.mts`. Nothing
  in CI does.

### 2.4 So: what must be written

| Need | Status |
|---|---|
| Every page returns its expected status | **written — `smoke.sh`** |
| Every API route is mounted and not 5xx | **written — `smoke.sh`** |
| Old vs new backend produce identical results | **written — `smoke_diff.py`** |
| The 50 non-CRM pages render *correctly* | **missing** — §3 covers it manually |
| Auth/session flows survive the move | **missing** — §3.2 |
| Payment + webhook flows survive | **missing** — §3.3 |

`smoke.sh` closes the breadth gap — every page, every route, one command. It
does not close the depth gap, and §3 says so rather than pretending otherwise.

---

## §3. The manual checklist — what a status code cannot see

**A page that 200s can still be wrong.** These are the failures `smoke.sh` is
structurally blind to. Walk them by hand on the preview before Phase 5, and
again on the real domain after.

### 3.1 Rendering and assets
- [ ] Home page: hero video plays, fonts load, no console errors
- [ ] `/app`, `/funded`, `/compare`, `/vs/*`, `/for/*` — images resolve
      (Phase 1 moved 67 MB of them to R2; a broken `<img>` still 200s the page)
- [ ] `/apple-icon` — replaced by a static PNG in the port
      (`spike/website-verification.md`); confirm the tab icon is right
- [ ] Open Graph: paste a link into Slack, confirm the card renders

### 3.2 Auth and session — the highest-risk area
- [ ] `/admin/login` → `/admin`: sign in, cookie set, survives a reload
- [ ] `/analytics/login` → `/analytics`
- [ ] `/crm` gate: wrong password rejected, right password admits
- [ ] `/internal/*` returns **401 without** the cookie and **200 with** it
      (`src/middleware.ts:149`–`:176`). Verify **both** directions — a gate that
      fails open still 401s for the anonymous prober.
- [ ] Sign out actually clears the session

### 3.3 Money and third parties
- [ ] `/pre-orders/purchase` → Stripe checkout in **test mode**, end to end
- [ ] `POST /api/webhooks/stripe` — signature verifies on Workers.
      Stripe signs the payload, not the URL, so the host change is safe, **but
      the endpoint must be re-registered** if the origin changes
- [ ] `/api/twilio/*` — Twilio signs over the **full URL**
      (`backend/pb_hooks/sms.pb.js:17`, `:64`–`:65`). **A host change breaks
      signature validation unless `ANTICIPY_TWILIO_WEBHOOK_URL` and the Twilio
      console are updated in the same window.** This is the one external
      integration where the URL is part of the credential.
- [ ] `/api/waitlist` — a real signup arrives
- [ ] `/api/geo` — returns a plausible city; needs the zone's "Add visitor
      location headers" transform (`spike/website-verification.md`)

### 3.4 Client end-to-end — after Phase 6 only
- [ ] iPhone: launch, sign in, post an event
- [ ] Extension: claim a job, run it, report back
- [ ] Mac: sign in, sync
- [ ] **SMS with an evidence photo arrives with the photo visible** — this
      exercises R2, the share window, and Twilio's fetch in one act

---

## §4. Running it

### 4.1 Baseline before anything moves

    ./migration/runbooks/smoke.sh https://www.anticipy.ai \
      --json migration/runbooks/baseline-prod.json

Measured 2026-09-03 against production:

    smoke  https://www.anticipy.ai
      pages   62
      routes  97
      pass    159
      fail    0

Commit that JSON. It is the oracle.

**Use `www.anticipy.ai`, not `anticipy.ai`.** The apex 307s to `www` — a Vercel
project redirect that is **not in the codebase**. Against the apex, every check
scores 307 and the run is meaningless. (That the redirect is invisible to this
script is exactly why `CUTOVER.md` 5.1 makes rebuilding it its own step.)

### 4.2 Against a Workers preview

    ./migration/runbooks/smoke.sh https://anticipy-site.<subdomain>.workers.dev \
      --json migration/runbooks/cf-preview.json

### 4.3 The gate: diff them

    ./migration/runbooks/smoke_diff.py \
      migration/runbooks/baseline-prod.json \
      migration/runbooks/cf-preview.json

Exit 0 = the two agree and the new one is green. **Both conditions.** "The new
one is green" alone is not the gate: a route that 401s on Vercel because a
secret is set and 401s on Workers because the secret is *missing* is the same
number and not the same behaviour. The diff catches the change; a single green
run cannot.

Differences that are genuinely correct go in `ACCEPTED` in `smoke_diff.py`,
**with a reason**. It starts empty on purpose.

### 4.4 Playwright against the same target

    CRM_PASSWORD=… PLAYWRIGHT_BASE_URL=https://<preview>.workers.dev \
      npx playwright test

Setting `PLAYWRIGHT_BASE_URL` suppresses the local `webServer`
(`playwright.config.ts:21`). **Do not point this at production** (§2.2).

---

## §5. How `smoke.sh` decides pass/fail

Worth reading before trusting it.

- **The route list is derived from the filesystem at run time**, so a route
  added tomorrow is covered tomorrow. A hand-maintained list stops covering new
  routes silently, exactly when it matters.
- **It never sends POST/PUT/PATCH/DELETE.** For the 46 GET-less routes it sends
  `OPTIONS`, falling back to `GET`. A **405 is a pass** — it proves the route is
  mounted, dispatched, and answering, which is the only claim the script makes.
- **It does not follow redirects.** A 301 that lands somewhere wrong is a
  different bug from a 301 that is not emitted; `-L` would merge them.
- **Pages** are checked against an expected status (`expect_for`): 401 for
  `/internal/*`, 301 for `/engine*`, 307 for the redirecting ones, else 200.
- **Routes** pass on anything that is not 5xx and not a transport failure.
- **One 5xx is allowlisted**, with its citation:
  `/api/engine/deepgram-key` → 503, retired 2026-05-13
  (`src/app/api/engine/deepgram-key/route.ts:6`, `:24`).
- **Dynamic segments get deliberately non-existent sample values.** The claim is
  "the route handles a miss", not "this row exists". A 404 passes; a 500 does
  not.
- **`--gate-cookie` flips the `/internal/*` expectation from 401 to 200.** The
  cookie is `anticipy_internal_gate` (`src/middleware.ts:6`) and its value is a
  signed `"<exp>.<hmac>"` pair, not a passcode (`:26`–`:38`) — obtain it by
  passing the gate in a browser and copying it from devtools. Expecting 401
  unconditionally would let "the gate is broken and everyone is locked out"
  score as a pass, so the expectation moves with the flag.

---

## Unverified

- **`--gate-cookie` has not been exercised.** The five `/internal/*` pages were
  only ever verified in their **401** state; the 200 path behind the gate is
  untested by this script. §3.2 covers it manually.
- **No route was tested with a real credential.** Every 401/403 in the green
  baseline is the unauthenticated path. The authenticated behaviour of those
  routes is unverified by `smoke.sh` on either backend.
- **`smoke_diff.py` was exercised on two runs of the same backend**, which
  proved the mechanics but not its behaviour on genuine drift. Its output on a
  real prod-vs-Workers diff is unobserved.
- **The Playwright suite has not been run** in this session — the 16 tests are
  from `--list`, which collects without executing. Whether they currently pass
  is unknown; `CRM_PASSWORD` was not available.
- **`/dl/*` and `/download` return 302** to an external host; the script does
  not follow them, so whether the DMG actually downloads is unverified here.
