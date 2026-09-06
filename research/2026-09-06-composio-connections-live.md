# Connections is not live. Measured, 2026-09-06.

**Read this before you believe the tests.** `migration/workers && npm test` is
15 suites green, `connect-routes` alone is 44 checks, `connections-store` 46,
`connections-provider` 169, and the spike behind the pure core has 1006. On the
production backend, at 04:08 UTC today, **a person cannot connect anything.**
Not "it is rough", not "it needs polish" — the URL in the text message answers
404 and the four tables the feature writes to do not exist.

That gap is the entire subject of HARNESS-LAWS law 3, and it is now instrumented:

    python3 overnight/is_connect_live.py

    IS CONNECT LIVE?   https://api.anticipy.ai   d1: anticipy-backend
    --------------------------------------------------------------------------
    [FAIL] 1  THE WORKER SERVES /c/                    404 application/json — the
             router's generic notFound(). routes/connect.ts is not on the
             deployed Worker: every link in a text 404s
    [....] 2  THE WIRING IS INSTALLED                  not measurable while leg 1
             is red — the route that would answer 503 is not deployed
    [FAIL] 3  THE FOUR TABLES EXIST ON LIVE D1         0 of 4 present on
             anticipy-backend; MISSING: app_usage_signals, connect_links,
             connect_nudges, connections
    [....] 4  A LINK CAN BE MINTED, AND ITS ROW LANDS  not attempted:
             connect_links does not exist on live D1 (leg 3)
    [PASS] 5  THE VENDOR KEY ANSWERS                   POST .../tool_router/session
             -> 201, a session id of 16 characters came back, and the connection
             tool is off (config.manage_connections says off, the tool list does
             not carry it) — the key in THIS environment, not the Worker's secret
    [....] 6  SOMEBODY HAS ACTUALLY CONNECTED AN APP   not measurable: the
             connections table could not be counted
    --------------------------------------------------------------------------
    exit 1

Exit 0 means a person can connect an app and somebody has. Exit 1 means
something we can SEE is broken. Exit 2 means a leg was not measured, and a leg
that was not measured does not pass — that third state is copied from
`overnight/firmware_gate.py` and it is the difference between "we looked and it
was fine" and "we never looked".

---

## What is live, measured today and not inferred

| thing | measured | how |
|---|---|---|
| the Worker itself | `GET api.anticipy.ai/api/health` -> **200** | curl |
| the Composio key | `POST backend.composio.dev/api/v3.1/tool_router/session` -> **201**, 16-character `session_id`, `config.manage_connections.enabled = false`, tool list is the five non-connection tools | gate leg 5 |
| the local write path | the four tables stood up in a scratch local D1 from `schema.sql` section 5, the probe row inserted, read back identical, deleted | `tests/test_is_connect_live.py::test_the_mint_probe_lands_in_a_real_d1` |

That is the whole list. One health check, one vendor key, and a schema that
works somewhere that is not production.

## What is not live

**1. `/c/` is not deployed.** `GET https://api.anticipy.ai/c/<43 chars>` answers
`{"code":404,"message":"The requested resource wasn't found.","data":{}}` — the
router's own `notFound()` from `src/pb/wire.ts`. `src/index.ts:190` routes
`/c/*` to `connectRoute`; the deployed Worker predates it. **Every link the
product could put in a text message today 404s.**

The apex is worse and it is worth knowing before somebody "improves" the link:

    https://anticipy.ai/c/<token>       -> 301 to www.anticipy.ai/c/<token>
    https://www.anticipy.ai/c/<token>   -> 307 to www.anticipy.ai/     (the token is dropped)

So the spec's own `anticipy.ai/c/{token}` spelling is a dead link today, which
is why `CONNECT_URL_BASE` is `https://api.anticipy.ai/c`. Moving it to the apex
means adding the route, deploying, confirming the apex serves this code, and
only then changing the constant — in that order, or every link already sitting
in somebody's message thread breaks.

**2. The four tables do not exist on `anticipy-backend`.** Measured directly:

    SELECT name FROM sqlite_master WHERE type='table' AND name IN
      ('app_usage_signals','connections','connect_nudges','connect_links')
    -> zero rows

37 tables are on that database. None of these four. `store.ts` refuses every
write to a missing table by name (`ConnectionsSchemaMissing`) rather than
turning it into a D1 1101, so the failure will at least be readable — but it is
still every write.

**3. The two secrets the wiring needs are not on the Worker.** `wrangler secret
list` for `anticipy-api` returns 15 names, and neither `COMPOSIO_API_KEY` nor
`GEMINI_API_KEY`/`GOOGLE_API_KEY` is among them. `connections/wiring.ts
missingConfig()` refuses to build the deps without both:

    DB                 present (wrangler.jsonc d1_databases)
    COMPOSIO_API_KEY   ABSENT   -> no catalog, no vendor link, no callback confirmation
    GEMINI_API_KEY     ABSENT   -> no permission sentences, and a consent page with
                                   a blank list of claims is refused rather than drawn

`GEMINI_API_KEY` is the one that will surprise somebody: it is required because
`ANTICIPY_BROWSER_MODEL` in `wrangler.jsonc` is `google/gemini-3.1-pro-preview`,
and `missingConfig` routes on that prefix. **Deploying without these two puts a
503 behind every `/c/` URL** — better than a 404, still a dead product. Do the
secrets and the deploy in the same sitting.

**4. Nothing mints a link.** `connect_links` has exactly one writer
(`store.ts put()`) and, at the time of writing, no product path calls it. The
iOS side is the same shape: `ConnectedAppsModel.swift`'s default client throws
`NoConnectionsClient` from every method, so the screen is drawn over nothing.

**5. Nobody has connected anything through this product.** The vendor holds two
ACTIVE accounts for owner `sxkotd1h02qb6gw` from the week-1 spike (`gmail`
`ca_BNgvxQtJ703C`, `googlecalendar` `ca_sHENw6KtQ8Kx`, from
`research/2026-09-05-composio-connections.md`) — connected BY HAND, in a Chrome,
against raw vendor links. There is no row in this system for either of them,
because there is no table to hold one. That is not the feature working.

---

## The commands, in order

Each step ends with the check that proves it, because none of them is done until
it is proven against live.

### 1. The four tables

Whole file (idempotent — every statement in it is `IF NOT EXISTS`, and this is
the option to prefer, since it also reconciles anything else that has drifted):

    npx wrangler d1 execute anticipy-backend --remote --file=migration/d1/schema.sql

Or just this feature — the seven statements of section 5, comments stripped so a
runner that splits on `;` cannot cut one in half:

```sql
CREATE TABLE IF NOT EXISTS "app_usage_signals" (
  "user_id"       TEXT NOT NULL CHECK (length("user_id") = 15),
  "toolkit"       TEXT NOT NULL CHECK (length("toolkit") > 0),
  "source"        TEXT NOT NULL CHECK ("source" IN ('said','observer','mx','link','connected','asked')),
  "alias"         TEXT NOT NULL DEFAULT '' CHECK ("alias" IN ('','work','personal')),
  "weight"        REAL NOT NULL DEFAULT 0 CHECK ("weight" >= 0),
  "last_seen_at"  REAL NOT NULL DEFAULT 0,
  PRIMARY KEY ("user_id", "toolkit", "source", "alias")
);

CREATE TABLE IF NOT EXISTS "connections" (
  "connected_account_id" TEXT PRIMARY KEY NOT NULL CHECK (length("connected_account_id") > 0),
  "user_id"              TEXT NOT NULL CHECK (length("user_id") = 15),
  "toolkit"              TEXT NOT NULL CHECK (length("toolkit") > 0),
  "alias"                TEXT NOT NULL DEFAULT '' CHECK ("alias" IN ('','work','personal')),
  "status"               TEXT NOT NULL CHECK ("status" IN ('connected','needs_reconnect','disconnected')),
  "writes_enabled"       INTEGER NOT NULL DEFAULT 0 CHECK ("writes_enabled" IN (0,1)),
  "last_used_at"         REAL NULL
);

CREATE TABLE IF NOT EXISTS "connect_nudges" (
  "user_id"      TEXT NOT NULL CHECK (length("user_id") = 15),
  "toolkit"      TEXT NOT NULL CHECK (length("toolkit") > 0),
  "state"        TEXT NOT NULL CHECK ("state" IN ('never_asked','asked','declined','connected','needs_reconnect')),
  "level"        INTEGER NOT NULL DEFAULT 0 CHECK ("level" BETWEEN 0 AND 3),
  "snooze_until" REAL NULL,
  "trigger"      TEXT NULL CHECK ("trigger" IS NULL OR "trigger" IN ('in_task','repeated_use','laptop_closed','user_named_it','onboarding')),
  "sent_at"      REAL NULL,
  "acted_at"     REAL NULL,
  "channel"      TEXT NULL CHECK ("channel" IS NULL OR "channel" IN ('sms','ios')),
  PRIMARY KEY ("user_id", "toolkit")
);

CREATE TABLE IF NOT EXISTS "connect_links" (
  "token_handle" TEXT PRIMARY KEY NOT NULL CHECK (length("token_handle") = 64),
  "user_id"      TEXT NOT NULL CHECK (length("user_id") = 15),
  "toolkit"      TEXT NOT NULL CHECK (length("toolkit") > 0),
  "alias"        TEXT NOT NULL DEFAULT '' CHECK ("alias" IN ('','work','personal')),
  "expires_at"   REAL NOT NULL,
  "used_at"      REAL NULL,
  "completed_at" REAL NULL
);

CREATE INDEX IF NOT EXISTS "idx_connections_owner"    ON "connections"   ("user_id", "toolkit");
CREATE INDEX IF NOT EXISTS "idx_connect_links_owner"  ON "connect_links" ("user_id", "toolkit");
CREATE INDEX IF NOT EXISTS "idx_connect_links_expiry" ON "connect_links" ("expires_at");
```

Do not paste these into a `--command` with their comments still on: several of
the comments in `schema.sql` contain semicolons. Use `--file`, or the stripped
text above.

**Check:**

    npx wrangler d1 execute anticipy-backend --remote --command \
      "SELECT name FROM sqlite_master WHERE type='table' AND name IN
       ('app_usage_signals','connections','connect_nudges','connect_links')"

Four names back. Anything less and gate leg 3 will say which.

### 2. The two secrets, BEFORE the deploy

    cd migration/workers
    npx wrangler secret put COMPOSIO_API_KEY      # value is in .env.local
    npx wrangler secret put GEMINI_API_KEY        # or GOOGLE_API_KEY; either is read

**Check:** `npx wrangler secret list` shows both names (never values).

### 3. The deploy

    cd migration/workers && npx wrangler deploy

**Check — and this is the step the whole file exists for:**

    python3 overnight/is_connect_live.py

Leg 1 must stop being red. If leg 2 then goes red, the Worker is deployed and
the wiring refused: the missing variable's NAME is in the log line, not on the
page (a 503 page that named an environment variable would be telling a stranger
about our configuration), so read it with

    cd migration/workers && npx wrangler tail --format pretty

and look for `connect wiring: not installed on this Worker — <NAME> is unset`.

### 4. Re-run the gate until it stops going down

Legs 4 and 6 only become measurable once 1–3 are green. Leg 4 writes one row to
production and deletes it; `--read-only` skips that and honestly reports the leg
as UNPROVEN.

---

## What remains before a person can tap a link

The three steps above make the page reachable. They do not make the feature
exist. Still missing, in the order a person would hit them:

1. **Something has to mint a `connect_links` row and put the URL in front of the
   person.** No product path calls `store.put()` today. The spec's shape: the
   nudge state machine decides an ask is due, mints our token, and texts
   `api.anticipy.ai/c/{token}`. Never a raw vendor link — that mistake was made
   once already and is item 4 of `research/2026-09-05-composio-connections.md`.
2. **Something has to mint the browser session.** `/c/` requires the signed-in
   session to BE the owner the token was minted for. A tapped link from a phone
   with no `anticipy_session` cookie answers 401 with "Sign in to finish", which
   is correct and is also a dead end until something sets that cookie —
   `HttpOnly; Secure; SameSite=Lax`, scoped to the apex, carrying the same
   `owners` auth token the phone sends in `Authorization`.
3. **The iOS client has to stop throwing.** Every method of
   `ConnectedAppsModel`'s default client throws `NoConnectionsClient`, so the
   Connected Apps screen renders over an error.
4. **The nudge state machine, the signals table's writer, and Settings' write
   opt-in** — all four tables have exactly one writer between them and no
   product path yet.
5. **The Gmail scope debt.** The spike's connection holds
   `https://mail.google.com/` — read, compose, send and permanently delete. It
   is a debt with a name in the 2026-09-05 note; when Anticipy's own Google
   OAuth app is filed, that connection is disconnected and remade narrow.

---

## What this gate cannot tell you, said plainly

- **It cannot tell you the page is correct.** It probes as a signed-out caller
  and gets a refusal by design; nothing here renders a consent page or reads a
  permission sentence. The register rules ("connect your Notion", never
  "authorize", never the vendor's name) are checked by the suite, not by this.
- **It cannot tell you a real person's tap works.** No browser, no session
  cookie, no vendor round trip. Leg 6 turning green is the first evidence any of
  that ever worked, which is exactly why zero is UNPROVEN rather than red — and
  why a green leg 6 is worth more than every other leg combined.
- **Leg 4 proves the DATABASE accepts the row store.ts writes, not that the
  product mints one.** It writes its own probe row: a `token_handle` of 32
  random bytes with no preimage anybody holds, an owner id that is not an owner,
  an `expires_at` in the past and a NULL `used_at`, deleted immediately and the
  deletion confirmed. Four independent reasons it can never be redeemed, because
  a gate that writes to production has to earn it.
- **It does not read anybody's words.** Law 1: every comparison in it is over an
  HTTP status code, a CSP header this Worker mints itself, four table names,
  seven column values it wrote itself, and one vendor status code.

## Files

- `overnight/is_connect_live.py` — the gate. `--self-test` runs every verdict
  offline; `--read-only` skips the one leg that writes.
- `tests/test_is_connect_live.py` — 46 tests, including the local-D1 proof that
  the mint probe really lands. 17 mutations run against the gate, 17 killed:
  every one of them a way this gate could quietly lie (an unwired 503 downgraded
  to "unproven", zero connections reported as a failure, the router's 404 read as
  a connect page, an unreadable D1 printed as zero tables, the probe row's expiry
  or owner scoping dropped, the read-back or the delete-confirmation skipped, a
  vendor session that confirms nothing waved through).
- `migration/d1/schema.sql` section 5 — the four tables, and the only book.
- `research/2026-09-05-composio-connections.md` — what the spike learned and
  what it got wrong first.
