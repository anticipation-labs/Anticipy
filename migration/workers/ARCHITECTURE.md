# Replacing PocketBase with Workers + D1 + R2 + Durable Objects

Companion artifacts in this directory, referenced and not repeated:
`filter-dsl.ts` (the parser, 42 passing tests in `test/`), `wrangler.jsonc`,
`src/**` (the skeleton), `HQ.md` (the 38 `/internal/*` routes), `BRAIN.md`
(`brain/` on Containers). Upstream: `migration/spec/CONTRACT.md` is the
behavioural oracle, `migration/d1/RULES.md` is the authorization inventory,
`migration/d1/schema.sql` is the shape of the data, and
`migration/BLOCKERS.md` is what stops any of it today.

---

## §1. What is actually being replaced

| | Count | Where |
|---|---|---|
| Collections | 26 (12 product + 14 internal HQ) | 58 files in `backend/pb_migrations/` |
| `routerAdd` routes | 55 | across 20 `pb_hooks/*.pb.js` |
| `routerUse` middlewares | 6 | 4 of them are the authorization |
| `cronAdd` jobs | 2 | `internal_hq.pb.js:2139`, `:2642` |
| Hook code | 8,795 lines | `pb_hooks/` |
| Static bytes | ~1.3 MB | `pb_public/` |

The four policy middlewares, measured (`grep -v '^\s*//' | grep -v '^\s*$'`):

| File | Code lines | Registered |
|---|---|---|
| `workflow_guard.pb.js` | **395** | 6th |
| `research_lane.pb.js` | **228** | 5th |
| `guard.pb.js` | **223** | 2nd |
| `owner_profile_owner.pb.js` | **30** | 4th |

(The brief said `owner_profile_owner` was ~45. It is 30 code lines inside a
79-line file; the other 49 lines are the comment explaining why it is a
middleware and not a `required` column, and that comment is the load-bearing
part — see §3.7.)

---

## §1.5 What in this directory is measured, not asserted

Run in this checkout on 2026-09-03, so a reader can re-run any of them:

| Claim | How | Result |
|---|---|---|
| The parser handles every filter this product sends | `node --experimental-strip-types test/filter-dsl.test.ts` | **42 passed, 0 failed** |
| The skeleton type-checks against real Cloudflare types | `tsc --noEmit -p tsconfig.json` (`@cloudflare/workers-types`) | **0 errors** |
| The Worker bundles, bindings resolve, assets are found | `wrangler deploy --dry-run` (wrangler 4.129.0) | **106,867 B raw / 31,788 B gzip**, 11 asset files, 5 bindings |
| bcrypt does not bloat the bundle | same | 31 KB gzip **including `bcryptjs`**, against a 3 MB free / 10 MB paid ceiling |
| The four middlewares' code-line counts | `grep -v '^\s*//' \| grep -v '^\s*$' \| wc -l` | 395 / 228 / 223 / 30 |
| `?=`, `expand`, `fields`, `skipTotal`, multi-value columns are unused | `grep -rn` across `clients/ extension/ brain/ proof/` | 0 call sites each (§2.3) |
| `/api/realtime` has no shipped consumer | `grep -rn` across all five clients | confirmed (§8) |

The bundle figure matters for one specific reason: `BLOCKERS.md` records the
*website* Worker at 2.63 MB gzipped against the free plan's 3 MB — 88% of the
ceiling, with 370 KB of headroom. This is a **separate** Worker at 31 KB, so
adding the whole backend costs that headroom nothing. `wrangler.jsonc`'s header comment
explains why they must stay separate anyway.

---

## §2. THE CENTRAL PROBLEM: five clients speak the generic records API

Every client talks to `/api/collections/{name}/records` with PocketBase's
filter DSL. Call-site counts, measured by `grep -rn "api/collections"`:

| Client | Call sites |
|---|---|
| `proof/` harnesses | 215 |
| `extension/` | 93 |
| `brain/` | 74 |
| `clients/ios/` | 19 |
| `clients/macos/` | 2 |

There is no purpose-built API layer to swap, because **authorization is
implemented as string surgery on those filters**:

```js
// backend/pb_hooks/guard.pb.js:45-50
const ownedList = (ownerRef) => {
  const filter = e.request.url.query().get("filter") || "";
  return filter.indexOf(`owner_ref="${ownerRef}"`) >= 0 && filter.indexOf("||") < 0;
};

// backend/pb_hooks/research_lane.pb.js:441-442
q.set("filter", "(" + filter + ") && lane != \"research\" && lane != \""
  + SUPERVISED_LANE + "\" && lane != \"" + DEVICE_LANE + "\"");
```

### 2.1 Option A — reimplement the records API + DSL on Workers

No client changes. The Worker answers the same URLs with the same JSON and the
same filter grammar.

### 2.2 Option B — purpose-built endpoints, rewrite all five clients

`GET /jobs/queued`, `POST /jobs/{id}/claim`, and so on. Authorization becomes
a parameter instead of a parsed string.

### 2.3 RECOMMENDATION: **A**, and it is not close.

**The effort argument.** The reason A is cheap is a measurement, not an
opinion. Grep across `clients/`, `extension/`, `brain/`, `proof/` for the
records-API features this product actually uses:

| PocketBase feature | Call sites in this tree |
|---|---|
| `expand=` (relation expansion) | **0** |
| `fields=` (sparse fieldsets) | **0** |
| `skipTotal=` | **0** |
| Back-relation / dotted-path filters | **0** |
| `?=` / `?!=` (multi-value ANY-of) | **0** |
| `~` (LIKE) | **1** — `proof/day_zero_20.py:368` |
| Multi-value columns in the schema | **0** |

So "reimplement PocketBase's records API" is not the project it sounds like.
It is: `filter`, `sort`, `page`, `perPage`, five verbs, one list envelope. That
is `src/pb/records.ts` — **336 lines**, already written — plus the parser,
`filter-dsl.ts`, **789 lines with 42 passing tests**. Both exist in this
directory now. The hard part was the grammar, and the grammar is done.

**The risk argument, which is the real one.** Option B requires shipping five
new clients *simultaneously*, and two of them cannot be:

- **The Chrome extension is in the wild and cannot be recalled.** The tree says
  so in its own voice: `research_lane.pb.js` exists specifically to protect
  against "0.2.3-and-older extensions in the wild, whose filters cannot be
  recalled" (`brain/pb.py:19-26`, and `extension/background.js:80-88` on why
  the lane must be named explicitly). Under B, every un-updated install
  either breaks or keeps a legacy endpoint alive — and a legacy endpoint is
  option A with worse test coverage.
- **The iOS app ships through App Review.** A backend cutover cannot be
  synchronised with an App Store release, so B needs both APIs live during the
  overlap regardless.

And a third, which is what actually decides it:

- **B moves the safety system at the same time as the datastore.**
  `workflow_guard.pb.js` is 395 lines that stop an executor approving its own
  plan and refuse a `done` with no verified evidence. `CONTRACT.md` §1 spends
  430 lines pinning it. Changing the *transport* and the *authorization
  shape* in one step means a failure has two possible causes and no oracle can
  tell them apart. A does exactly one thing: same wire, same rules, new engine.
  The contract suite is then a genuine differential test.

**The honest cost of A**, stated so nobody discovers it later:

1. A filter parser is now production authorization code. It is 789 lines you
   own forever, and a bug in it is an authorization bug. Mitigated by: it is
   parameterised (never interpolated), it refuses unknown identifiers, it has a
   test per real client filter, and §3.5's SQL scope injection means a parser
   bug still cannot cross an owner boundary.
2. You inherit PocketBase's quirks, including the ones that are bugs (§3.4).
3. `?=` is compiled as `=`. Correct *only* because no column is multi-valued;
   the compiler throws rather than degrading silently if one ever is.

**B is still the right destination.** Do it *after* the cutover, per client,
with the old surface still answering — which is what A makes possible and what
doing them together makes impossible.

---

## §3. Authorization: the four middlewares are the ONLY lock

> ### The single most dangerous sentence in this migration
>
> In PocketBase an API rule is a nullable string, and the two empty-ish values
> mean **opposite** things:
>
> | value | meaning |
> |---|---|
> | `""` | **PUBLIC.** Anyone, unauthenticated. |
> | `null` | **SUPERUSER ONLY.** No API caller at all. |
>
> **42 rule slots across 11 of the 12 product collections are `""`.**
> (`migration/d1/RULES.md` counted them.) The migration authors knew:
>
> > `""` is not "public". It is what jobs (1700000001:17) and every other
> > worker-read collection already use, because guard.pb.js is the real gate
> > — `1700000042_purges_readable.js:24-27`
>
> **D1 has no equivalent of an API rule at all.** There is no second lock
> behind these middlewares. If the chain is skipped, mis-ordered, or shipped
> with its switch off, every transcript, every job, every profile (name, email,
> phone, birthday, free-form `facts`) and every receipt photo is readable by
> anyone who can guess a URL.

### 3.1 Chain order is load-bearing

`CONTRACT.md` §0.4 fixes it, and the reason is the status code: `guard.pb.js`
refuses **before** `research_lane` and `workflow_guard` ever see the request,
so a guard failure is `403 {"error":"forbidden"}` and never a `409` workflow
violation. A port that evaluates workflow rules first answers wrongly on a
large class of requests, and the contract suite catches it as a diff.

```
1. files.ts              /api/files/*          evidence.pb.js:56
2. guard.ts              /api/collections/*    guard.pb.js:24
3. cors.ts               /internal/*           internal_hq.pb.js:4224   (see HQ.md)
4. ownerProfileOwner.ts                        owner_profile_owner.pb.js:34
5. researchLane.ts                             research_lane.pb.js:272
6. workflowGuard.ts                            workflow_guard.pb.js:6
```

Encoded once, in `src/policy/chain.ts`, as an ordered array. `runChain` stops
at the first `Response`, which is `e.next()`-vs-`return e.json()` semantics.

### 3.2 The three principals

Read off `guard.pb.js`; the Worker reproduces all three or clients break.
Resolution lives in `src/index.ts:resolvePrincipal`.

| # | Principal | Proof | Scope |
|---|---|---|---|
| 0 | **Service token** (`brain/`) | `X-Anticipy-Token` | Total. Every collection, every method, no owner scoping. A god credential. `guard.pb.js:37` |
| 1 | **A paired Chrome install** | `X-Anticipy-Agent-ID` + a ≥40-char `agent_token` resolved against `agents` | Enumerated and narrow. `guard.pb.js:226-347` |
| 5 | **A signed-in account** | `owners` JWT | 7 collections, owner-scoped. `guard.pb.js:403-453` |

Two ordering traps, both with incidents behind them, both preserved:

- **The superuser branch must sit ABOVE the account branch.** PocketBase fills
  `e.auth` for *any* auth record including a superuser, so `if (e.auth)`
  swallowed the dashboard and the Admin UI bounced to login on every
  `auth-refresh`. `guard.pb.js:381-396`.
- **An agent id that does not RESOLVE is a refusal, not a shrug.** Sending
  `X-Anticipy-Agent-ID` *commits* the caller to that identity. A failed lookup
  used to fall through into the anonymous pairing bootstrap, so a revoked
  credential silently received the anonymous surface. `guard.pb.js:203-220`.
  `resolvePrincipal` returns `anonymous` for an unresolved agent header and
  `guard.ts` turns it into a 403 by re-checking the header — deliberately not
  by falling through.

### 3.3 The filter DSL parser

`filter-dsl.ts`. Grammar, lexer, precedence-climbing parser, AST, and a
compiler to parameterised SQL. **Nothing is interpolated.** The only text
concatenated into SQL is a column name already looked up in a compile-time
schema map (`src/pb/schema.ts`); an unknown identifier is a hard 400.

Operators: `= != > >= < <= ~ !~ ?= ?!=` (plus `?~ ?!~ ?> ?>= ?< ?<=`),
`&& ||` with `&&` binding tighter, parenthesised grouping, single- and
double-quoted strings with backslash escapes, numbers, `true`/`false`/`null`,
and `@request.auth.id` / `@request.auth.*` / `@request.body.*` /
`@request.method`.

**The `!=` / NULL subtlety**, which the brief asked for by name. The tree
records the measurement at
`backend/pb_migrations/1700000043_owner_profile_needs_owner.js:27-30`:

> Measured on 0.30.4 rather than assumed, because `!=` in PocketBase filters
> carries IS-NOT semantics and a NULL might have satisfied `!= ""`: a create
> with `owner_ref` MISSING and a create with `owner_ref: ""` are both refused
> 400.

So the semantics reproduced are: **NULL and `''` are the same value.**
`col = ""` is true for both; `col != ""` is false for both. That is the only
reading consistent with the schema's own rule
(`migration/d1/schema.sql`, type-map note 1: *PocketBase NEVER writes SQL NULL
into a user field*), and getting it backwards on `owner_ref != ""` is the
difference between "3 orphan profiles" and "every profile".

The compiler expresses it as a **column-level** decision rather than a global
one, and this is the design choice worth understanding:

```ts
// filter-dsl.ts, Compiler.ref()
private ref(c) {
  const q = ident(c.name);
  if (!c.spec.nullable) return q;                       // bare column — INDEXABLE
  return c.spec.type === "number" ? `COALESCE(${q}, 0)` : `COALESCE(${q}, '')`;
}
```

`COALESCE(owner_ref,'') = ?` is correct **and unindexable** — it cannot use
`idx_jobs_owner`, and the jobs list is the hottest query in the product (every
extension install polls it every 30s, `extension/background.js:1721-1729`).
Because `schema.sql` declares every user column `NOT NULL DEFAULT ''`,
`nullable` is false everywhere and production always emits the bare column.
The COALESCE form exists for a column that is genuinely nullable, and flipping
that flag has a measurable cost — so the flag is where the decision belongs.

### 3.4 THE LIVE AUTHORIZATION BYPASS

`ownedList` inspects a *substring*. That is enough for the cases `CONTRACT.md`
§2.7 enumerates. It is not enough for this one, which §2.7 does **not** list:

```
GET /api/collections/jobs/records?filter=goal != 'owner_ref="<my own id>"'
```

- No `||`, so `filter.indexOf("||") < 0` passes.
- The literal substring `owner_ref="<my own id>"` is present — inside a
  **string literal** — so `filter.indexOf(...) >= 0` passes.
- `ownedList` returns true. PocketBase then runs
  `goal != 'owner_ref="…"'`, which is **true for essentially every row**.

Result: any signed-in account reads every other owner's `jobs`, `events`
(transcripts), `owner_profile` (name, email, phone, birthday, `facts`),
`segments`, `agents`, `pendants` and `evidence` — the seven collections
`guard.pb.js:416` admits. The same shape works against the agent rung.

`CONTRACT.md` §2.7 notes the adjacent case (a longer field name such as
`not_owner_ref`) and says "no such column exists today". The string-literal
variant needs no such column.

**It is pinned as a test.** `test/filter-dsl.test.ts`:

```ts
t("LIVE BUG: a string literal satisfies the substring rule while constraining nothing", () => {
  const attack = `goal != 'owner_ref="OWN123"'`;
  assert.equal(legacyOwnedList(attack, "OWN123"), true);   // the deployed guard says yes
  assert.equal(provesOwnerScope(parseFilter(attack), "OWN123"), false);
});
```

A second, smaller one in the same family: `research_lane.pb.js:279` decides
whether to append the lane exclusions using `/\blane\b/` against the **raw
string**, so `goal="pick a lane"` reads as "this poll names the lane" and the
exclusions are **skipped**. That is a fail-open on the guard that keeps
supervised reads away from old extensions. `mentionsField()` on the AST is
exact and closes it. Also pinned as a test.

**The fix, structurally.** `provesOwnerScope(ast, ownerRef)` returns true iff
every row that can satisfy the filter must have `owner_ref = ownerRef` — in
DNF, every disjunct carries that conjunct. It is *sound*, and it is a strict
widening in the honest direction: it accepts
`(owner_ref="X" && a) || (owner_ref="X" && b)` which the substring rule
refuses, and refuses the attack which the substring rule accepts.

### 3.5 …and the backstop, which is what actually closes it

Do not rely on the predicate. `guard.ts` sets `ctx.forcedScope` on every
owner-scoped path, and `records.ts` compiles it into the `WHERE` of every
list, view, update and delete:

```ts
// src/pb/records.ts, buildWhere()
if (req.forcedScope) {
  parts.push(`${quoteIdent(req.forcedScope.column)} = ?${nextIndex()}`);
  params.push(req.forcedScope.value);
}
```

So even a filter that slips past **both** predicates cannot read or write
another owner's rows. On `UPDATE`/`DELETE` the scope is part of the `WHERE`
rather than a pre-check, which also closes a TOCTOU the original had: a
pre-check plus an unscoped write lets two interleaved requests write a row the
first one proved was owned.

Migration path, so the contract suite stays a clean diff:

- **Phase 4a** — `LEGACY_OWNED_LIST_ONLY=1` in `vars`. The predicate is
  byte-identical to the deployed one; the scope injection is on anyway. The
  contract suite diffs clean.
- **Phase 4b** — add the AST assertion to `contract_tests.py` (the attack
  must 403), unset the var, re-run against both. **PocketBase now fails the new
  test and the Worker passes.** That is the point: it is the first test in this
  migration where the two backends *should* differ.
- **Then patch `guard.pb.js` on the live backend too**, so the hole is not open
  for the length of the migration.

### 3.6 The fail-open switch is deliberately not ported

`guard.pb.js:25` is `if (!token) return e.next()`. With
`ANTICIPY_SERVICE_TOKEN` unset the guard is a **no-op for every request**.
`design/LOGIN-DESIGN-2026-08-03.md:506` names the consequence: any collection
added later is unguarded by default, `/api/realtime` included, and the panic
button is gone. On PocketBase this was survivable because the collections'
own rules were a second layer for anything not `""`. **On D1 there is nothing
underneath.** So `guard.ts` refuses with `503` when the token is unset:

```ts
if (!env.ANTICIPY_SERVICE_TOKEN) {
  return refuse(503, "the data API is not configured",
    "ANTICIPY_SERVICE_TOKEN is unset; refusing rather than serving unguarded");
}
```

This is a deliberate divergence from the oracle and the contract suite will
show it as one. It is the right divergence: a backend that will not start is a
page in a runbook; a backend that starts wide open is not discovered at all.

### 3.7 `owner_profile_owner` — and the layer D1 cannot have

Two layers on PocketBase, and the second one is the one D1 loses:

1. The middleware (`owner_profile_owner.pb.js:34-79`) — a 400 with a sentence
   a client log can act on.
2. The collection's `createRule = '@request.body.owner_ref != ""'`
   (`1700000043:44`), which survives the hook file being renamed and applies
   **even to a caller holding the service token** — that token is a header the
   guard checks, not a PocketBase identity, so rules still ran against it.

`required` on the column was tried and rejected, and the reason still holds:
it would freeze the three live orphan rows, which hold the only copy of a
phone number, and they must stay patchable because patching them is how they
get adopted (`claim_legacy.pb.js:73-84`).

The D1 replacement for layer 2 is a `BEFORE INSERT` trigger — the statement is
in `src/policy/owner_profile_owner.ts` as `OWNER_PROFILE_INSERT_TRIGGER`. It
refuses an ownerless insert and leaves updates alone, which is exactly the
createRule's shape.

**UNVERIFIED: that D1's control plane accepts `CREATE TRIGGER`.** SQLite does.
If D1 does not, the rule lives only in the middleware plus the post-import
assertion in `schema.sql` SECTION 4 — and that fact must be written into
`RULES.md` rather than quietly accepted, because it means a service-token
caller can create an orphan again.

---

## §4. AUTH: reimplementing the `owners` collection

### 4.1 bcrypt on workerd — **SETTLED, with a receipt**

Library: **`bcryptjs`** (pure JS, no WASM, no native module). Already a
dependency of this repo at `package.json:20`, with `@types/bcryptjs` at `:16`.

`migration/spike/bcrypt-on-workerd.md` ran it on a real workerd
(`wrangler dev --local`, wrangler 4.129.0, `compatibility_flags:
["nodejs_compat"]`):

```
verify_2a_correct: true      verify_2a_wrong:   false
verify_2b_correct: true      verify_2b_wrong:   false
```

Both prefixes verify and both reject a wrong password. **This is measured, not
assumed.** Existing accounts keep their logins.

What came with it is a hard constraint: **~50 ms of CPU per verify** at cost
factor 10 (Go's `bcrypt.DefaultCost`, which wrote the production hashes). The
free plan's 10 ms CPU ceiling means login does not run slowly there — it
**fails, every time**, with an exceeded-CPU error. `wrangler.jsonc` sets
`limits.cpu_ms: 200`, which requires Workers Paid.

**Do not lower the cost factor to fit.** It silently downgrades every stored
password and cannot be undone without the plaintext.

One more CPU cost, added on purpose: `authWithPassword` compares against a
`DUMMY_HASH` when no account matches, so a nonexistent account spends the same
~50 ms as a wrong password. Without it the endpoint is an account-existence
oracle, and this tree already treats guessability as a live threat
(`guard.pb.js:56-115`).

### 4.2 Three things must be carried across, or the cutover locks everyone out

| Column | Why | Source |
|---|---|---|
| `owners.password` | the bcrypt digest | `schema.sql:432` |
| `owners.tokenKey` | per-record salt in every issued JWT — rotating it is what "log out everywhere", a password change and an account deletion *are* | `schema.sql:444-448` |
| **neither is exportable over REST** | PocketBase hides both; they exist only inside `/pb_data/data.db` | `schema.sql:437-443`, corroborated at `import_d1.py:214-216` |

So the cutover needs a **native PocketBase archive** as well as a REST export.
A REST-only export locks every existing customer out of their account and
unpairs every browser — **and it will look like a clean run.**
(`agents.agent_token` is on the same hidden list, which is the unpairing half.)

### 4.3 Tokens, and the one thing that does log people out

`src/pb/auth.ts` issues an HS256 JWT over `{id, type, collectionName, exp}`,
7-day TTL, keyed on `HMAC(ANTICIPY_AUTH_SECRET ‖ tokenKey)`.

Verification order is the security property, and it is not the obvious order:

```
read `id` from the UNVERIFIED payload   -> use it ONLY as a database key
load the row, take its tokenKey         -> derive the HMAC key
verify the signature                    -> only now is anything trusted
```

An attacker who edits the `id` claim gets a different `tokenKey` and the
signature fails.

**Invalidation on delete is a property of the design, not a sweep.** A deleted
account has no row, so there is no `tokenKey`, so nothing verifies. No
revocation list to keep and nothing to expire.

**The one real regression, stated plainly:** PocketBase's own signing-key
derivation is an internal of the Go binary, which is fetched at image build
time (`backend/Dockerfile:3-6`) and is not in this tree. So **tokens minted by
PocketBase will not verify on the Worker.** Every live session ends at
cutover.

The cost is one silent re-login, because both mobile clients re-authenticate
from stored credentials rather than only from a token. Say it in the cutover
notes anyway — a person who is signed out without warning files a bug.

### 4.4 `@request.auth.id`, and the superuser that has no home

`@request.auth.id` is resolved to a bound parameter at compile time, not
matched textually — `filterToSQL("id = @request.auth.id", { ctx })`. With no
session it resolves to `null` and compiles to `("id" IS NULL)`, so an
anonymous caller matches nothing rather than everything. Test:
*"@request.auth.id with no session is NULL, so `id = @request.auth.id` matches
nothing"*.

`owners`' own rules (`1700000008_owners.js:50-53`) are
`listRule/viewRule/updateRule = "id = @request.auth.id"`, which this reproduces
exactly.

**PocketBase's `_superusers` collection has no D1 equivalent.**
`schema.sql:158-163` is explicit: HQ identity is `internal_sessions` +
`internal_people.code_hash`, product identity is `owners`. So the dashboard
rung (`guard.pb.js:394-396`) has nothing to resolve against, and every
superuser-gated surface must be re-homed:

| Superuser-gated today | Becomes |
|---|---|
| `/_/` Admin UI | **gone.** Nothing replaces it. `wrangler d1 execute` is the console. |
| `evidence.pb.js:66` superuser passthrough on `/api/files/*` | the service token, which the operator already holds |
| the vault reveal route in `runbooks/reencrypt_vault.md` | temporary, and deleted at step 6 before this matters |
| `guard.pb.js:462` `_superusers` login passthrough | dropped with the collection |

This is a real loss of capability. It is also the loss that makes the
`""`-rules problem safe to leave behind: there is no admin surface that could
be reached by guessing a URL, because there is no admin surface.

---

## §5. `e.app.store()` → a Durable Object

`guard.pb.js:116-195` counts failed pair-code guesses in `e.app.store()`,
PocketBase's app-wide KV, measured on 0.30.4 to be shared across the isolated
hook runtimes (`:93-99`).

**A Worker has no such process.** Requests land in whichever isolate the edge
picks, anywhere on the network:

- A module-level `Map` is **per-isolate**. A guesser distributing across colos
  gets an unlimited number of independent counters. A counter that resets by
  opening a new connection is not a counter.
- **Workers KV is eventually consistent** with cached reads. Two concurrent
  guesses both read `fails: 9` and both proceed. Read-modify-write on a rate
  limiter needs **serialisation**.

A Durable Object gives serialisation: one instance, one thread, requests
queued. The instance is named `"global"` so there is exactly one everywhere,
which is what the all-callers ceiling wanted and could only approximate.

Class in `src/do/PairCodeCounter.ts`. Constants preserved verbatim:
`WINDOW_MS = 10min`, `MAX_PER_IP = 10`, `MAX_ALL = 60`. Fixed window, not
sliding, for the original's stated reason: one read and one write per failed
attempt, and a guesser cannot spend less by pacing himself.

Three properties carried over deliberately:

- **A successful pairing spends nothing.** An ordinary person is untouched.
- **A miss falls through to an empty list**, so the phone can say "that code
  didn't match" instead of "I can't reach Anticipy"
  (`SettingsView.swift:270-284`). Only the ceiling refuses.
- **No counter means refuse (503).** "Serving lookups that nobody is counting
  is the exact hole this closes" (`guard.pb.js:126-135`).

**What genuinely improves.** `guard.pb.js:101-104` admits that behind
Railway's edge `e.realIP()` gives every caller the same bucket, so the per-IP
ceiling was doing no work and only the all-callers one bounded the walk. On
Cloudflare, `CF-Connecting-IP` is stamped by the edge and is not
caller-controllable, so the per-IP bucket becomes real for the first time.
And DO serialisation removes the lost-increment race the original documents at
`:170-172`.

**What does not improve, and must not be claimed to** (`guard.pb.js:110-115`):
this makes the walk slow and loud, it does not end it. The code is permanent
once minted (`agent_auth.pb.js:19-25`). The cure is a code that expires with a
popup that refreshes it — a change to the pairing ceremony, not to this file.

---

## §6. `$security.encrypt/decrypt` → WebCrypto

**This is a one-way door and it is already documented.**
`migration/runbooks/reencrypt_vault.md` is the procedure; do not re-derive it.
The summary, and the dependency this architecture has on it:

`internal_passwords.secret_enc` is ciphertext written by PocketBase's **Go**
`$security.encrypt` keyed by `ANTICIPY_VAULT_KEY`
(`internal_hq.pb.js:3079`), and the only thing that has ever read it back is
`$security.decrypt` at `:3140` inside that same binary. The wire format is an
undocumented internal of the dependency being decommissioned.

**Plan on nothing in a Worker being able to open those bytes.** The vault must
be re-wrapped on the PocketBase side, while `$security.decrypt` still exists.
There is no later: once the container is deleted, every row in
`internal_passwords` is a service name, a username, and noise.
`import_d1.py` enforces the ordering — it refuses a non-empty `secret_enc`
without the `vault_rewrapped.json` receipt.

The Worker-side target format, and what it buys:

```
AES-256-GCM · 12-byte random IV · 128-bit tag · AAD = the record id
token: v1.<base64url iv>.<base64url ciphertext‖tag>
key:   ANTICIPY_VAULT_KEY_GCM (32 raw bytes, base64 in env) — a NEW key
```

The AAD binding is not decoration: a ciphertext copied from one vault row onto
another fails to decrypt instead of revealing the wrong service's password.
`$security.encrypt` passes no AAD, so today that swap succeeds.

The other `$security.*` calls port cleanly and are not one-way doors:

| PocketBase | Worker |
|---|---|
| `$security.sha256(s)` | `crypto.subtle.digest("SHA-256", …)` → hex (`src/llm.ts:sha256Hex`) |
| `$security.equal(a,b)` | `timingSafeEqual` (`src/index.ts`) |
| `$security.randomStringWithAlphabet(n, α)` | `crypto.getRandomValues` + alphabet (`src/pb/wire.ts:newRecordId`) |
| `$security.parseJWT(tok, key)` | `crypto.subtle.verify("HMAC", …)` (`src/pb/auth.ts`) |

`$security.equal` has ~40 call sites in `internal_hq.pb.js` and **zero** in
`guard.pb.js:37`, which compares the service token with `===`. Every secret
comparison in the Worker goes through `timingSafeEqual`; that is a small
improvement taken for free.

---

## §7. `$http.send({timeout: 95})` vs Workers subrequest limits

`agent_key.pb.js:337` and `:389` — the LLM proxy — wait up to **95 seconds** on
Gemini or OpenRouter. That is a deliberate ceiling on a slow model call.

Three different Workers constraints get conflated here. Separating them:

| Constraint | Free | Paid | Does the 95s call hit it? |
|---|---|---|---|
| **CPU time** | 10 ms | 30 s default, `limits.cpu_ms` raisable | **No.** Waiting on `fetch()` spends no CPU. A 95s model call costs a few ms of it. |
| **Subrequests per invocation** | 50 | 1000 | **No.** This handler makes 1 provider call + a small number of D1 writes for the audit row. |
| **Wall clock** | — | — | **This is the open question.** |

**UNVERIFIED, and it is the thing to test before Phase 5:** whether
Cloudflare's edge terminates a *response that has not started* after an
interval shorter than 95 s. This handler cannot start streaming early — it has
to read the provider's whole JSON, transform it, and write an audit row
(`agent_key.pb.js:129-146`) — so a client-facing idle timeout would bite. The
spike is one line: point a Worker at a deliberately slow endpoint and time the
failure.

**Mitigation if it does bite, and it is cheap.** Cap the upstream at the
measured ceiling with `AbortSignal.timeout()` and return the same `502` the
handler already returns for a provider that answers badly. The extension
already retries that path, so a shorter ceiling costs throughput, not
correctness. `src/llm.ts` is written this way already — `UPSTREAM_TIMEOUT_MS`
is a named constant precisely so it can be lowered from a measurement.

The one thing that **must not** be dropped: `fetch()` has no `timeout` option.
Without `AbortSignal.timeout()` a hung provider holds the invocation open
indefinitely, where PocketBase's option bounded it. That is a regression
introduced by *omission*, which is the easiest kind to ship.

**Ported 2026-09-05.** `src/llm.ts` is the whole route now — the refusal
ladder, the meter (one atomic `UPDATE`), the ledger, both providers, the 95 s
`AbortSignal.timeout`. Its header carries what is still UNVERIFIED: the edge's
idle timeout (the spike above has not been run) and the real providers. The
proof that does exist is `scripts/llm_contract_local.sh`: a real workerd, a
fake provider (`scripts/fake_llm_provider.py`) reached through
`LLM_PROVIDER_BASE` — honoured for a loopback host only, so a mis-set var can
never send a vendor key elsewhere — and `contract_tests.py::TestAgentLlmProxy`
asserting the 512 floor on the wire, the `json_object` passthrough, the
byte-identical 429 text, the audit rows in D1, and that no key reaches a
response. `test/llm-proxy.test.ts` pins the pure half to the hook and reads
the floor and the 429 text out of the extension's own source.

The other timeouts in the tree, for completeness: `captcha_solve.pb.js` 30 s,
`password_reset.pb.js` 15 s, `internal_hq.pb.js` 60 s and 15 s. All far inside
any limit; all need the same explicit `AbortSignal`.

The cron sweep is the one place subrequests could bite: it sends Twilio
messages in a loop (`sendSMS`, `internal_hq.pb.js:2164-2190`). `src/cron.ts` batches to 50
per tick, which is inside the free ceiling and comfortably inside the paid one.
The original had no such cap because a Go process needs none.

---

## §8. realtime / SSE: **the claim is confirmed. Drop it.**

The audit says `/api/realtime` is guarded but has no live consumer. I checked
independently rather than taking it:

| Where | Result |
|---|---|
| `extension/` | **None.** And the extension says so in its own voice: *"There is no push channel: grep extension/ for EventSource or WebSocket and you find nothing. The only recurring wake is the 0.5-minute chrome.alarms floor"* — `extension/background.js:1721-1725` |
| `clients/ios/` | none |
| `clients/macos/` | none |
| `brain/` | none |
| `src/` (website) | none |
| **Consumers found** | `proof/test_backend.py:50,60` (a conformance probe) and `proof/hands_battery.py:405,434` (a **mock server**, not a client) |

One stale reference exists and is worth naming so nobody re-derives from it:
`design/LOGIN-DESIGN-2026-08-03.md:488` describes
`background.js:418-437` opening `EventSource(${BASE}/api/realtime)`. That code
is **gone** from the current `background.js`, and the file that replaced it
documents its own absence at `:1721`. The design doc is a month older than the
code.

**Recommendation: do not port it.** The reasons are not only "nobody uses it":

- PocketBase evaluates `listRule` **per subscriber** for realtime, and denied
  clients receive *nothing* — no error, no close
  (`design/LOGIN-DESIGN-2026-08-03.md:488`). Reproducing that
  silent-denial semantics on Workers is real work for a channel with no reader.
- It would need a Durable Object per subscription topic plus WebSocket
  hibernation, which is the single largest piece of new infrastructure in this
  whole migration — for zero shipped consumers.
- `guard.pb.js:31-36` guards only the **non-GET** to `/api/realtime` (opening
  the SSE channel is harmless because `EventSource` cannot send headers). So
  the guarded surface is one POST that attaches subscriptions.

`src/index.ts` answers `/api/realtime` with **410 and a sentence naming the
decision**, rather than 404:

```
"realtime is not served by this backend" /
"no shipped client subscribes; the extension polls on a 30s alarm
 (extension/background.js:1721-1729). See migration/workers/ARCHITECTURE.md §8."
```

A future client that tries gets an answer instead of a silent nothing.
`contract_tests.py:814-819` currently asserts the guarded POST is refused; it
will need to accept 410 as well as 403, and that edit is a Phase-4 checklist
item, not a surprise.

---

## §9. Static files

Two problems that look like one.

### A. `pb_public/` — Workers Static Assets

Five static files and four zips, `COPY`ed into the image at
`backend/Dockerfile:11`. Immutable per deploy, no auth, no counting.

| File | Size |
|---|---|
| `internal.html` | 136 KB (the HQ SPA — see `HQ.md`) |
| `setup.html` / `privacy.html` / `mac.html` | 12.7 / 10.8 / 7.3 KB |
| `site.css` / `theme.js` | 20.0 / 2.8 KB |
| `anticipy-extension.zip` | 277,549 B |
| `anticipy-claude-version-extension.zip` | 277,549 B — **byte-identical** |
| `anticipy-codex-version-extension.zip` | 277,549 B — **byte-identical** |
| `mac/Anticipy-for-Mac.zip` | 388,070 B |

→ **Static Assets**, not R2. They ship in the deploy, serve from the edge with
no Worker invocation, cost nothing per request, and version with the code that
references them — which R2 would not. Total ~1.3 MB.

Staged by `npm run stage:assets` (copies `backend/pb_public/` into
`migration/workers/public/`) rather than committing a second copy of the zips.
(The extension zips are 338,456 B each at 0.13.0 as of 2026-09-05; the table
above is the 2026-09-03 measurement.)

**A staged copy can go stale with no diff to show it**, and did: on 2026-09-05
the deployed Worker served an extension zip at 0.12.0 while
`backend/pb_public/` held 0.13.0. `scripts/check_staged_assets.py`
(`npm run check:assets`) compares every zip under the two directories by
sha256 and exits 1 on any missing, differing or extra zip, naming the manifest
version of each; run it before every deploy, and overnight/stranger_gate.py is
the place to wire it.

The three identical extension zips are a deploy-channel decision, not a
storage one. Leave them until someone decides otherwise.

### `/mac/Anticipy-for-Mac.zip` currently 404s in production

Worth being precise about, because the tree **contradicts** the obvious causes:

- the file **is** tracked in git (`git ls-files backend/pb_public/`)
- it **is** 388,070 bytes on disk
- it **is** copied into the image (`Dockerfile:11 COPY pb_public /app/pb_public`)
- `backend/.railwayignore` excludes only `pb_data/`, `pocketbase`, `pb.zip`,
  `pb.log`

So a build-time exclusion is **not** the cause. Whatever is — a stale image, a
PocketBase static-route quirk on a nested directory, a proxy rule — is not
visible from this checkout. **UNVERIFIED: I cannot reach production.**

What matters for the migration: Static Assets makes the *class* of bug
impossible, because the file is enumerated at deploy time and `wrangler deploy`
prints the manifest. Two lines on the cutover checklist so it cannot 404
silently a second time:

```sh
curl -sI https://<worker>/mac/Anticipy-for-Mac.zip | head -1   # expect 200
curl -sI https://<worker>/anticipy-extension.zip   | head -1   # expect 200
```

### B. `evidence.image` — R2, behind the Worker

Every property is the opposite of (A): written at runtime, per-owner,
authorised per fetch, and **counted** (a share window spends a 5-fetch
ceiling, `evidence.pb.js:130-145`).

→ **R2**, reached only through `src/assets.ts:serveFile`. **Never a public
bucket and never a custom domain on the bucket.** The whole point of
`evidence.pb.js:56-147` is that the bytes are reachable only through a gate
that checks the share window and increments `fetches`; a public R2 URL is that
gate deleted. Twilio fetches these by `MediaUrl` from its own infrastructure,
so the URL handed out is this Worker's `/api/files/...`.

One improvement taken while porting: the fetch counter is a **conditional
UPDATE** (`SET fetches = fetches + 1 WHERE id = ? AND fetches = ?`) rather than
read-then-write, so two concurrent Twilio fetches on the same row cannot both
read 4 and both serve. That race existed on PocketBase too.

R2 key layout mirrors PocketBase's on-disk one by record id —
`evidence/<recordId>/<filename>` — so the export script can copy without
knowing collection ids.

---

## §10. Cron

| PocketBase | Cron Trigger | Detail |
|---|---|---|
| `cronAdd("internal_hq_sweep", "*/5 * * * *")` `internal_hq.pb.js:2139` | `"*/5 * * * *"` | ~500 lines: due reminders, `REMIND_MAX_TRIES = 3`, notification fan-out, Twilio send |
| `cronAdd("internal_hq_prune", "17 4 * * *")` `internal_hq.pb.js:2642` | `"17 4 * * *"` | four bounded `DELETE`s, 200 rows each |

Cloudflare's `scheduled` handler receives `event.cron` — the literal schedule
string from `wrangler.jsonc` — so one Worker carries both and dispatches on it
(`src/cron.ts`). **The strings in `wrangler.jsonc` are the routing key**;
changing one there without changing the switch silently stops a job.

Three differences that change the code:

1. **Cron Triggers are UTC, always.** PocketBase's cron ran in the container's
   timezone. `17 4 * * *` may not be the same 04:17. Harmless for the prune
   (a 60-day cutoff), **not harmless for the sweep**, which sends SMS
   reminders. **UNVERIFIED: the Railway container's TZ.** Confirm before
   cutover.
2. **No shared process memory.** Anything a tick kept between runs must live in
   D1 or a DO. Verified by reading `internal_hq.pb.js:2139-2636`: the sweep
   keeps nothing — every piece of state is a row. Nothing to move.
3. **Subrequest budget.** Each Twilio send is one. `src/cron.ts` batches to 50
   reminders per tick; the original had no cap because a Go process needs none.

Two deletions on the way, both safe: the hand-rolled base64
(`internal_hq.pb.js:2150-2162`) exists because the JSVM has no `btoa`; Workers
do. And `$http.send({timeout: 15})` becomes `AbortSignal.timeout(15_000)` —
**required**, not optional, per §7.

`prune`'s four statements go in one `env.DB.batch()`. The original wraps each
block in its own try/catch so one failing table does not stop the others; D1's
batch is atomic, so equivalent independence would need four awaits. It does not
matter here — four bounded `DELETE`s on four different tables — so the atomic
form is kept and a failure is loud.

---

## §11. Cascade delete: PocketBase's `cascadeDelete` is Go, not SQL

`schema.sql:1018-1066` establishes this and it belongs in the Worker's
contract too: PocketBase creates **no foreign keys**. `cascadeDelete: true` on
six relation fields is code in the Go record deleter. **Deleting an owner in D1
therefore deletes nothing** unless the Worker runs the statements itself.

Real `FOREIGN KEY` constraints are deliberately not declared: documented orphan
rows exist (`owner_profile` with `owner_ref = ''`) and `''` is not `NULL`, so
an enforced FK would reject their import outright.

One reviewed function, one `env.DB.batch()` (atomic), `:owner` bound once:

```sql
DELETE FROM "password_resets" WHERE "owner"     = ?1;
DELETE FROM "jobs"            WHERE "owner_ref" = ?1;
DELETE FROM "events"          WHERE "owner_ref" = ?1;
DELETE FROM "owner_profile"   WHERE "owner_ref" = ?1;
DELETE FROM "segments"        WHERE "owner_ref" = ?1;
DELETE FROM "agents"          WHERE "owner_ref" = ?1;
DELETE FROM "pendants"        WHERE "owner_ref" = ?1;
DELETE FROM "owners"          WHERE "id"        = ?1;
```

And then, **separately and not as a cascade**, whatever
`account_delete.pb.js:69` enumerates for the non-relation tables
(`evidence.owner_ref`, `agent_llm_audit.owner_ref`,
`agent_audit_sessions.owner_ref` — and **not** `purges.owner_ref`, which must
outlive the account), plus the `INSERT` into `purges` that records the request
so it survives the deletion.

---

## §12. Phased sequence

Every phase ends at the same gate: **`migration/spec/contract_tests.py` run
against both backends and diffed.** The suite is 189 tests by `BLOCKERS.md`'s count (165 `def test_` functions,
some parametrised), standard library only, and skips rather than fails on a missing credential.

```sh
BASE_URL=https://backend-production-61e0a.up.railway.app \
  python3 -m pytest migration/spec/contract_tests.py -m "not destructive" \
  --junitxml=/tmp/pocketbase.xml

BASE_URL=https://anticipy-api.<account>.workers.dev \
  python3 -m pytest migration/spec/contract_tests.py -m "not destructive" \
  --junitxml=/tmp/worker.xml

diff <(grep -oE 'name="[^"]+"' /tmp/pocketbase.xml) \
     <(grep -oE 'name="[^"]+"' /tmp/worker.xml)
```

**175 of the 189 tests skip without `ANTICIPY_SERVICE_TOKEN`**
(`BLOCKERS.md`). Getting that token is a Phase 0 item, not a Phase 4 one — a
green run of 14 tests is not a checkpoint.

### Phase 0 — unblock. No code.

`BLOCKERS.md` establishes that four findings are one finding: **the account is
on the Workers free plan.** Containers unavailable, R2 not enabled, bcrypt
login exceeds the 10 ms CPU cap, website bundle at 88% of the 3 MB ceiling.
One $5/month upgrade.

Also required before anything else:

- `ANTICIPY_SERVICE_TOKEN` (unblocks 175 tests)
- `ANTICIPY_VAULT_KEY` **presence confirmed** (not read) — §6
- PocketBase superuser credentials, to export and to discover any collection
  this repo does not know about (`d1/GAPS.md`: **nine fellowship collections**
  no migration creates)
- **Confirm where the PocketBase backups actually land.** R2 is not enabled on
  this account, yet `1700000053_off_volume_backups.js` points backups at
  `anticipy-pocketbase-backups-production`. Either they go to a different
  account or they have been failing. Nobody discards the Railway volume until
  somebody has **listed** that bucket.

**Gate:** baseline run against PocketBase with all credentials present. That
XML is the oracle for every phase after this. **Checkpoint: 189/189 accounted
for — passed or explained.**

### Phase 1 — read-only shadow

Import a snapshot into D1. Deploy the Worker serving **GET only**, on
`workers.dev`, with no client pointed at it. `src/pb/records.ts` list + view,
`src/pb/schema.ts` generated from `schema.sql`, `filter-dsl.ts` wired in.

**Gate:** contract suite `-m "anonymous"` against both. Plus a differential
replay: take the real filter strings from `extension/background.js:77-90`,
`brain/worker.py:115-127` and `proof/`, fire each at both backends, diff the
`items` arrays. **Checkpoint: identical rows for every filter the product
sends.** Any diff is a parser bug and is fixed before writes exist.

### Phase 2 — auth

`src/pb/auth.ts` against imported hashes. Sign in as a real test account on
both.

**Gate:** `-m "needs_account"` against both, plus the bcrypt CPU measurement
re-run on the deployed Worker rather than on `--local`.
**Checkpoint: an existing account signs in on the Worker with its existing
password, and `wrangler tail` shows the CPU figure.**

### Phase 3 — the guard, in `LEGACY_OWNED_LIST_ONLY=1` mode

`src/policy/guard.ts` + `PairCodeCounter`. Predicate byte-identical to the
deployed one; scope injection on regardless (§3.5).

**Gate:** `-m "guard_on"` and `-m "needs_agent"` against both.
**Checkpoint: zero diffs.** This is the phase where a diff means the port is
wrong, not that the oracle is.

Then, still in Phase 3: add the §3.4 attack as a new contract test. It should
**pass on the Worker and fail on PocketBase**. Unset the var. Patch
`guard.pb.js` on the live backend so the hole is not open for the length of
the migration.

### Phase 4 — writes, and the safety system

`create`/`update`/`remove`, `researchLane`, and **the whole of
`workflowGuard`** — including Shelf 2, the approval gate, reconciliation after
an uncertain effect, and "done needs verified evidence"
(`workflow_guard.pb.js:286-673`, ~36 named refusal codes). `src/policy/
workflow_guard.ts` is transcribed only to `:220` and says so; the rest is this
phase.

**This Worker must not serve the `jobs` collection in production until that is
complete.** A half-transcribed safety ladder is worse than an absent one,
because it looks finished.

**Gate:** the full suite with `-m destructive` and
`ANTICIPY_ALLOW_DESTRUCTIVE=1`, against a **staging** PocketBase restored from
backup — never production. **Checkpoint: all ~90 §1 assertions green on both,
and the two XMLs differ only in the tests deliberately changed (§3.6's 503,
§8's 410, §3.4's new assertion).** That list of intended differences is written
down before the run, not rationalised after it.

### Phase 5 — the 55 routes, R2, cron, HQ

The product routes (`CONTRACT.md` §6), the 38 HQ routes (`HQ.md`), evidence
into R2, both Cron Triggers, static assets.

Ordering constraint that cannot move: **the vault re-wrap
(`runbooks/reencrypt_vault.md`) happens while PocketBase is still alive.**
`import_d1.py` refuses to proceed without its receipt.

**Gate:** full suite, all markers, both backends. Plus the static-asset curls
from §9. **Checkpoint: the intended-difference list is still the whole diff.**

### Phase 6 — cutover

Freeze writes → final export (**native archive AND REST**, §4.2) → import →
re-point DNS. `next.config.mjs` has 34 rewrites to
`backend-production-61e0a.up.railway.app`; they change in one commit.

**Gate:** the suite against the Worker at the production hostname, then a
manual pass: pair a browser, run one job end to end, receive one SMS, open one
evidence photo through a share link.
**Checkpoint: green, and the Railway service is STOPPED, not deleted.**

### Phase 7 — decommission

Not before: the R2 backup bucket has been listed and is current, the vault
receipt is verified (`reencrypt_vault.md` step 5), and the Worker has served
production for long enough to cover a full cron cycle of both jobs.

---

## §13. Unverified

Things I could not confirm from this checkout. None is asserted elsewhere in
this document without this marker.

1. **PocketBase 0.30.4's exact filter-to-SQL generation.** `filter-dsl.ts`
   reproduces *behaviour* described in this tree
   (`1700000043:27-30` for `!=`/NULL) and standard fexpr grammar. The Go
   source is not in this checkout — the binary is fetched at image build time
   (`backend/Dockerfile:3-6`). **Settle it by diffing `items` arrays**, not by
   reading code: Phase 1's differential replay is exactly that test.
2. **`~` escaping, byte-exact.** `likePattern()` reconstructs
   "wrap in `%…%` unless the value already contains an unescaped `%`, escaping
   `\ % _`". The emitted SQL adds `ESCAPE '\'`, which SQLite needs for `\%` to
   mean a literal `%` and which PocketBase may not emit. **Deliberate
   divergence**, unobservable for the one `~` call site in the tree
   (`proof/day_zero_20.py:368`, value `rig/<tag>`, no wildcards).
3. **Exponent notation in filter numbers** (`1e3`). Not lexed. I do not believe
   fexpr supports it; no call site uses it.
4. **`//` comments in filters.** fexpr accepts them; this parser refuses them.
   I did not confirm PocketBase's acceptance against a live instance — but the
   refusal is correct either way, since a comment is a place to hide a
   substring that satisfies `ownedList`.
5. **That D1 accepts `CREATE TRIGGER`.** SQLite does; D1's control plane was
   not tested. §3.7 says what to do if not.
6. **`new_sqlite_classes` vs `new_classes`** for the Durable Object migration
   tag, for this account and compatibility date. A deploy-time error either
   way, not a runtime surprise — check `wrangler deploy --dry-run`.
7. **Whether a Worker can hold a 95-second upstream `fetch()` open** before the
   edge closes the client connection. §7. This is the one worth spiking early.
8. **The Railway container's timezone**, and therefore whether `17 4 * * *`
   keeps its hour under UTC Cron Triggers. §10.
9. **Why `/mac/Anticipy-for-Mac.zip` 404s in production.** The tree contradicts
   every build-time explanation (§9). I cannot reach production.
10. **PocketBase's record-auth JWT signing-key derivation.** Not readable here,
    so §4.3's "every session ends at cutover" is a *design decision* taken in
    its absence, not a measured incompatibility. If someone later demonstrates
    a byte-compatible derivation, sessions could survive — but nothing in this
    architecture depends on that.
11. **That PocketBase 0.30.4's hook glob is lexicographic**, which is what
    fixes the chain order. `CONTRACT.md` §0.4 flags the same thing. Assert it
    on the live instance.
12. **Workers plan limits** are stated from general knowledge of the platform,
    not from a document in this checkout: CPU 10 ms free / 30 s paid default,
    subrequests 50 free / 1000 paid, script size 3 MB gz free / 10 MB gz paid.
    The only one this design is sensitive to is the CPU figure, and
    `BLOCKERS.md` reaches the same conclusion from an independent measurement.
13. **The nine fellowship collections** (`d1/GAPS.md`) are outside everything
    above. No middleware in this tree touches them and no schema here describes
    them. One of the routes with no handler in this repo is **the route that
    pays a fellow**. That is a gap in the migration, not in this document.
