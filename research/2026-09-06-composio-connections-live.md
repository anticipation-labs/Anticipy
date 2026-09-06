# Connections on production, 2026-09-06. Seven legs green, two unproven, nobody has connected.

**Read this before you believe the tests, and before you believe the gate's own
green legs.** `migration/workers && npm test` is green. `pytest -q` is green.
`overnight/is_connect_live.py` printed **5 PASS / 1 UNPROVEN** at 06:17 this
morning over its six legs — and at that moment a person still could not connect
an app, because the page the texted link led to had nothing on it to tap.

That is the gap this note exists to stop somebody rediscovering next month.
Everything below was measured against `api.anticipy.ai` and `anticipy-backend`
on **2026-09-06 between 06:17 and 07:25 UTC** with curl, `wrangler d1 execute`
and the gate itself. Nothing here is inferred from source unless it says so in
the sentence.

**Three legs were added today and the six older ones were renumbered.** The
order is now the order a person walks the chain in, because the gate's own
instruction to its reader is "work the first red leg" and that is only true if
the order is the order things happen in. A note quoting "leg 5" from earlier
today means the vendor key, which is **leg 8** now.

---

## The board, right now

    python3 overnight/is_connect_live.py            # exit 2

    IS CONNECT LIVE?   https://api.anticipy.ai   d1: anticipy-backend
    --------------------------------------------------------------------------
    [PASS] 1  THE SIX /me/connections ROUTES EXIST      all 6 answer 401 with
             connections_api.ts's own "Sign in first.", and the control
             /me/connectionsX answers the router's generic 404 — so those 401s
             are these routes and not a blanket refusal
    [PASS] 2  THE FOUR TABLES EXIST ON LIVE D1          all four present on
             anticipy-backend: app_usage_signals, connect_links, connect_nudges,
             connections
    [....] 3  THE CATALOG ANSWERS "ADD AN APP"          no owner credential in
             the environment (ANTICIPY_CONNECT_PROBE_CREDENTIAL or
             ANTICIPY_OWNER_TOKEN), so the catalog was not asked
    [PASS] 4  A LINK CAN BE MINTED, AND ITS ROW LANDS   one row inserted with the
             seven columns store.ts writes, read back identical, deleted, and
             confirmed gone
    [PASS] 5  THE WORKER SERVES /c/                     401 text/html with
             connect.ts's own CSP (form-action 'self')
    [PASS] 6  THE WIRING IS INSTALLED                   a connect.ts page was
             drawn, which only happens after WIRING(env) returned deps
    [PASS] 7  THE PAGE OFFERS A WAY IN                  the signed-out page
             carries 1 control(s) whose target resolves to /c/<43 chars>/code on
             our own host
    [PASS] 8  THE VENDOR KEY ANSWERS                    201, a session id of 16
             characters, connection tool off — the key in THIS environment
    [....] 9  SOMEBODY HAS ACTUALLY CONNECTED AN APP    nobody has connected
             anything yet
    --------------------------------------------------------------------------
    UNPROVEN — a leg that could not be measured does not pass.

Exit 0 means a person can connect an app and somebody has. Exit 1 means
something we can SEE is broken. Exit 2 means a leg was not measured, and a leg
that was not measured does not pass — that third state is copied from
`overnight/firmware_gate.py` and it is the difference between "we looked and it
was fine" and "we never looked".

**Exit 2 is not a pass.** Two legs are unproven, and the second of them is the
finish line.

---

## Leg 7 went red, and then green, in one hour. That is the whole point of it.

At **06:17 UTC** `GET https://api.anticipy.ai/c/<43 chars>`, signed out — the
exact request a person makes when they tap the link in a text — answered this,
in full, minus the stylesheet:

```html
<body>
<h1>Sign in to finish</h1>
<p>Sign in to Anticipy in this browser, then open this link again. It works for ten minutes.</p>

</body>
```

No anchor. No form. No button. **The end of the road for every person who tapped
a connect link.** And the way in already existed, one path segment away and
deployed: `GET /c/{token}/code` answered 200 with "Get a code by text" and a
form posting back to itself. `installConnectSessionReader(connectSession)` is
called at `src/index.ts:145`, so the cookie that flow mints is honoured by the
`/c/` page. The whole mechanism was live. The only thing missing was a link to
it — `refusalPage("sign-in-required")` called `plainPage(401, …)` without the
optional `back` argument, so nothing was drawn.

It mattered more than that sentence suggests: `SettingsHomeView.runConnect`
mints the link on the phone and hands it to a browser. The person is signed in
on the phone and the browser is not, so that 401 was not an edge case — it was
the first thing every single user would have seen.

At **07:20 UTC** the same URL answered:

```html
<body>
<h1>Sign in to finish</h1>
<p>Anticipy needs to know it&#39;s you before it sets anything up. It can text a code to
the phone number on your account — or you can sign in to Anticipy in this browser and
open this link again.</p>
<p><a href="/c/{token}/code">Get a code by text</a></p>
</body>
```

Leg 7 went green against live in the same run that had been red an hour earlier.
Both readings are pinned offline — `is_connect_live.py --self-test` and
`tests/test_is_connect_live.py` both keep the 06:17 dead end as a fixture on
purpose. **A fixture that quietly followed the repair would leave the leg
untested against the only page it has ever had to catch.**

---

## What is live NOW, measured this hour

| thing | measured | how |
|---|---|---|
| the six `/me/connections` routes | each answers **401** `{"ok":false,"message":"Sign in first."}` with its own verb and no credential | gate leg 1 / curl |
| that those 401s mean something | `/me/connectionsX` answers the router's generic `{"code":404,…}`; `/me/connections/nope` answers connections_api.ts's own `"There's nothing at this address."` | gate leg 1's control |
| the four tables | `app_usage_signals`, `connect_links`, `connect_nudges`, `connections` all on `anticipy-backend` | gate leg 2 |
| the write path | one probe row inserted with the seven columns `store.ts put()` writes, read back column-for-column identical, deleted, deletion confirmed | gate leg 4, against **production** |
| `/c/{token}` | **401** `text/html` with connect.ts's own CSP (`form-action 'self'`), carrying one control to the code flow | gate legs 5–7 / curl |
| the wiring | a connect.ts page is drawn at all, which happens only after `WIRING(env)` returned deps — so `missingConfig()` returned null, so **`DB`, `COMPOSIO_API_KEY` and the model key are all set on the deployed Worker**. That is new since this morning's note, which recorded both secrets absent | gate leg 6, read against wiring.ts:331 |
| `/c/{token}/code` | **200**, "Get a code by text", with a form posting back to `/c/{token}/code` | gate leg 7's control / curl |
| the vendor key | `POST backend.composio.dev/api/v3.1/tool_router/session` → **201**, 16-character `session_id`, `config.manage_connections.enabled=false`, connection meta-tool absent from the tool list | gate leg 8, with the key in `.env.local` |
| connected accounts | **zero** rows with `status='connected'` | gate leg 9 |

One leftover: `connect_links` holds a single row, `user_id=qeuy6sv1raof9rw`,
`toolkit=notion`, `expires_at` 2026-09-06T05:44:40Z — **expired before this run
and never spent**. It is inert (`locate()` calls it dead) and it is somebody's
earlier hand-mint. Nothing prunes expired links; that is a housekeeping debt,
not a defect.

---

## What is NOT measured, said plainly, so nobody reads a gap as a pass

1. **`?q=` — "Add an app" — has never been asked on production.** Leg 3 is
   UNPROVEN because there is no owner credential in this environment, and it
   cannot be faked: `connectionsApiRoute` settles the credential before it
   builds a single dependency, so an anonymous caller gets 401 and never sees
   the port behind it.

   **And the source moved under this note while it was being written, which is
   exactly why an unmeasured leg is not a pass.** At 06:17 `connectionsApiDeps()`
   did not fill `ConnectionsApiDeps.search` at all, so `searchCatalog` took the
   `typeof deps.search !== "function"` branch and every `?q=` answered
   `refuse(503, "I couldn't look that up just now. Nothing has changed.")`. By
   07:25 the working tree carried `search: (query) => provider.search(query)`
   (connections_api.ts:400) and a `search()` on the provider — somebody else's
   change, landing in parallel. **Whether the DEPLOYED build carries it is not
   known**, and neither reading of the source is a measurement. If production
   still 503s, Add an app is broken for everybody and leg 3 is RED with that
   sentence quoted. Somebody has to point the gate at it:

       export ANTICIPY_CONNECT_PROBE_CREDENTIAL='<an owner auth token>'
       python3 overnight/is_connect_live.py --read-only

   The gate refuses to take that credential from `argv` — a secret on a command
   line is a secret in `ps`, in a shell history and in every CI log — and it
   refuses to send it anywhere but `anticipy.ai` and its subdomains, because
   `WORKER` comes from `ANTICIPY_PB` and that variable pointed at a different
   backend as recently as last week.

2. **The code flow has never been driven end to end.** The gate GETs
   `/c/{token}/code` and never POSTs it, deliberately: `POST` texts a six-digit
   code to a real person's phone and is rate-limited per link and per owner
   (`MAX_CODES_PER_LINK = 3`, `MAX_CODES_PER_OWNER = 5`). So nothing here proves
   the text arrives, that `/verify` mints a cookie, or that
   `ANTICIPY_AUTH_SECRET` is set on the Worker — and `sessionKey()` **fails
   closed** on an unset secret, which means no code session exists at all and
   the page keeps asking for a sign-in. **The control leg 7 now finds could lead
   to a door that does not open, and this gate cannot tell you.** That needs a
   human with a phone, or a script under `proof/`.

3. **Nobody has connected anything.** Leg 9 is UNPROVEN and stays UNPROVEN at
   zero. That is the state of a feature nobody has been offered, not a failure —
   a gate that cried failure the day before launch would teach its reader to
   ignore it, which is how the ears stayed deaf for thirty hours next to a green
   board. It turns green on the first real connection and it is worth more than
   every other leg combined.

4. **Leg 8 measures the key in THIS environment, not the Worker's secret.** They
   are different objects. Leg 6 is the evidence that the Worker has one at all
   (it could not draw a page otherwise); `wrangler secret list` is the evidence
   of which names are set.

---

## Exactly what has to happen before a person can connect, in order

1. ~~Put a control on the signed-out `/c/` page.~~ **Done 2026-09-06 07:20**,
   proven by gate leg 7 against live.
2. **Drive the code flow once, with a real phone.** Tap "Get a code by text",
   receive the text, enter the code, land back on the connect page with the
   app's name and three sentences on it. This is the next thing to do and it is
   the largest unmeasured stretch of the chain. *Proof:* a human, or a `proof/`
   script; the gate will not POST that route.
3. **Prove the catalog search on production.** A `provider.search` and the
   `ConnectionsApiDeps.search` filler both landed in the tree today; nothing has
   asked the deployed build whether it carries them. Repo-green is not done.
   *Proof:* gate leg 3 green, with a credential exported.
4. **Give the gate an owner credential in whatever runs it**, or leg 3 is
   permanently UNPROVEN and the gate can never exit 0.
5. **Then a real person taps and completes one connection.** *Proof:* gate leg 9
   goes green, which is the only evidence any of this ever worked end to end.

### Three live facts worth not rediscovering

- **The apex still does not serve the page.** `https://anticipy.ai/c/<token>`
  answers 301 to `www`, and `www` answers 307 to `https://www.anticipy.ai/` —
  the token is dropped. A zone-level redirect intercepts before the Worker route
  is consulted, so this is a dashboard change, not a code one. Links are minted
  on `api.anticipy.ai` for that reason (`CONNECT_URL_BASE`), and the phone
  accepts both hosts (`ConnectHandoff.connectLinkHosts`).
- **Cloudflare injects an analytics `<script>` into the connect page, for some
  callers and not others.** Measured: the same URL was 1003 bytes to curl and
  1370 bytes to the gate, and the difference is
  `<script type="module" src="https://static.cloudflareinsights.com/beacon.min.js/…">`
  inserted by the edge after connect.ts wrote the response. Our own CSP is
  `default-src 'none'` with no `script-src`, so the browser refuses to run it —
  the page is not executing third-party code today. It is still a third-party
  script tag injected into the one screen in the product where a person hands
  over a key to something of theirs, and it deserves a deliberate decision (Web
  Analytics off for this route, or accepted knowingly) rather than a surprise.
  It does not affect leg 7: the beacon has a `src`, and the scan reads `href`
  and `action`.
- **`handleLink`'s header comment is stale** (`connections_api.ts:1045-1056`): it
  says the phone refuses what the route mints because
  `ConnectHandoff.connectLinkHosts` is `["anticipy.ai"]`. It is
  `["anticipy.ai", "api.anticipy.ai"]` as of today, so the phone accepts it. The
  comment is in a file this change does not own; it is recorded here rather than
  edited so the next reader does not chase a defect that was fixed.

---

## What this gate cannot tell you

- **It cannot tell you the page is correct.** It probes as a signed-out caller
  and gets a refusal by design; nothing here renders a consent page or reads a
  permission sentence. The register rules ("connect your Notion", never
  "authorize", never the vendor's name) are checked by the Worker's own suite,
  not by this.
- **Leg 7 proves a control EXISTS, not that it works.** It resolves the target of
  an `href` or an `action` and checks the path and the host. Whether tapping it
  produces a text is item 2 above, and is unmeasured.
- **Leg 4 proves the DATABASE accepts the row `store.ts` writes, not that the
  product mints one.** It writes its own probe row: a `token_handle` of 32
  random bytes with no preimage anybody holds, an owner id that is not an owner,
  an `expires_at` in the past and a NULL `used_at`, deleted immediately and the
  deletion confirmed. Four independent reasons it can never be redeemed, because
  a gate that writes to production has to earn it.
- **It does not read anybody's words.** HARNESS-LAWS law 1: every comparison in
  it is over an HTTP status code and verb, a CSP header this Worker mints
  itself, two sentences this Worker writes for two named cases, four table
  names, seven column values it wrote itself, the target of an HTML attribute
  resolved as a URL, the length of a JSON array, and one vendor status code. The
  one string it sends into the product — the catalog probe query, one letter —
  is not an app name and is not matched against anything here.

## Each new leg carries a CONTROL, and that is not decoration

A leg that cannot fail for the right reason is worse than no leg. Each of the
three added today can only ever *withhold* green when its control fails:

- **Leg 1** asks `/me/connectionsX`, which is deliberately not a route. It must
  answer the router's generic 404. A Worker that answered 401 to every path
  would otherwise light all six routes green while measuring the edge.
- **Leg 3** asks `GET /me/connections` with the same credential first. If the
  list route accepts it and the catalog refuses, the catalog is what is wrong;
  if the list route refuses it too, the credential is stale and the leg is
  UNPROVEN. A stale token reported as a broken catalog sends the reader to write
  a search adapter that was never the problem.
- **Leg 7** runs its scan over `/c/{token}/code` first — a page whose own form
  posts to exactly the path the scan looks for. If the scan comes back empty
  *there*, the scan is broken and the leg is UNPROVEN, not red. A pattern that
  silently stopped matching is the specific way an instrument lies, and it has
  produced false "it is tested" readings in this repo.

## Files

- `overnight/is_connect_live.py` — the gate. Nine legs. `--self-test` runs 61
  verdicts offline against shapes this system has actually had; `--read-only`
  skips the one leg that writes; `--catalog-query` changes what leg 3 types into
  the search box.
- `tests/test_is_connect_live.py` — **88 tests**, including the local-D1 proof
  that the mint probe really lands and a test that reads
  `CONNECTIONS_API_ROUTES` and `METHOD` out of `connections_api.ts` so the
  gate's six paths and verbs cannot drift from the Worker's. Collected by
  `pytest -q` (pytest.ini `testpaths = tests`), which is what CI runs
  (`.github/workflows/system-invariants.yml`).
  **18 mutations run against the gate, 18 killed**: a missing route waved
  through, leg 1's control skipped, an anonymous 2xx accepted, the catalog 503
  downgraded to UNPROVEN, a refused credential blamed on the catalog, an empty
  catalog answer called green, a dead-end page called green, leg 7's calibration
  skipped, a control on somebody else's host accepted, a route path and a route
  verb each typed wrong, the router's 404 read as a refusal, the anonymous
  probes carrying a credential, the control page POSTed to, the catalog asked
  without the credential, the credential zone loosened to a bare suffix test,
  the credential zone dropped entirely, and zero connections called red.
- `migration/d1/schema.sql` section 5 — the four tables, and the only book.
- `research/2026-09-05-composio-connections.md` — what the spike learned and
  what it got wrong first.

### One gap in CI worth someone's attention

`.github/workflows/system-invariants.yml` triggers on `tests/**`, `overnight/**`,
`brain/**`, `backend/**` and `extension/**` — **not** on `migration/**`. So a
change to `connections_api.ts` alone does not run the test that pins the gate's
six paths and verbs against it. Adding `migration/**` to both path lists is one
line in a file this change does not own.
