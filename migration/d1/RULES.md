# API rules as they finally stand — and what each must become in a Worker

Source: the final state of `backend/pb_migrations/*.js` (58 files), PocketBase
0.30.4 (`backend/Dockerfile:3`). Every cell carries the migration `file:line`
that last set it.

---

## READ THIS FIRST

In PocketBase a rule is a *nullable* string, and the two empty-ish values mean
**opposite** things:

| value  | PocketBase meaning |
|--------|--------------------|
| `""`   | **PUBLIC.** Anyone, unauthenticated, may perform this operation on this collection through `/api/collections/<name>/records`. |
| `null` | **SUPERUSER ONLY.** No API caller may perform it at all — not a signed-in account, not the service token. Only server-side Go/JS holding the app DAO. |

`1700000008_owners.js:47` states it in the tree's own words: *`"" = any record
may authenticate. null would mean nobody can.`*

### 42 rule slots in this schema are `""`

Across **11 of the 12 product collections**. Plus `owners.authRule = ""`
(`1700000008_owners.js:48`).

**None of them is protected by the rule. Every one of them is protected by a
middleware that is not part of the schema** — `backend/pb_hooks/guard.pb.js:24`,
a `routerUse` that demands the `X-Anticipy-Token` header on every
`/api/collections/*` request whenever `ANTICIPY_SERVICE_TOKEN` is set
(`guard.pb.js:25-37`). The migration authors knew and wrote it down:

> `""` is not "public". It is what jobs (1700000001:17) and every other
> worker-read collection already use, because guard.pb.js is the real gate
> — `1700000042_purges_readable.js:24-27`

**Therefore: if you port the rules and not the middleware, the database is
world-readable and world-writable.** A literal carry-across of these 42 slots
publishes every transcript, every job, every profile (name, email, phone,
birthday, timezone, free-form `facts`) and every receipt photo to anyone who
can guess a URL. There is no second lock behind them.

`guard.pb.js` is 30,762 bytes of authorization logic that has no schema
representation at all. **It is the thing being migrated, not the rules.**

---

## The three principals the guard actually recognises

Read off `guard.pb.js` directly; the Worker must reproduce all three or clients
break.

| # | Principal | Proof it presents | Scope |
|---|-----------|-------------------|-------|
| 1 | **Service token** (`brain/`, the worker) | `X-Anticipy-Token: <ANTICIPY_SERVICE_TOKEN>` | `guard.pb.js:37` — total. Every collection, every method, no owner scoping. A god credential. |
| 2 | **A paired Chrome install** | `X-Anticipy-Agent-ID` + a ≥40-char `agent_token` resolved against the `agents` row (`guard.pb.js:226-233`) | Narrow and enumerated: PATCH its own agent row (`agent_token`,`last_seen`,`browser` only — `:236-239`); GET its owner's jobs list (`:240-242`); GET/PATCH one of its owner's job rows, but **never** the four "evidence" columns `watching_until`,`lane`,`owner_ref`,`owner` (`:261-273`); POST an `events` row only of kind `read_line`/`read_fact`, ≤400 chars, against a job in lane `supervised_read` whose `watching_until` is still in the future (`:297-320`); POST `evidence` for its own owner (`:342-347`). Anything else → 403 (`:348`). |
| 3 | **A signed-in account** (`owners` JWT) | PocketBase auth token | `guard.pb.js:398-451`. Only seven collections are reachable at all — `jobs, events, owner_profile, segments, agents, pendants, evidence` (`:417`) — and only as: a **list whose filter literally contains `owner_ref="<self>"` and contains no `\|\|`** (`:45-50, :447`); a POST whose body `owner_ref` equals self (`:448`); or a single record already owned by self (`:449-451`). |

Plus three unauthenticated doors that exist because a fresh device holds no
credential yet: agent self-registration (`:468-472`), pair-code lookup
(rate-limited, `:117-165`), and the one-shot claim of a not-yet-paired record.
And the auth endpoints themselves (`:367-378`), which must stay open or nobody
can sign in — a bug this file records having shipped once.

### The authorization primitive that has no Worker equivalent

```js
// guard.pb.js:45-50
const ownedList = (ownerRef) => {
  const filter = e.request.url.query().get("filter") || "";
  return filter.indexOf(`owner_ref="${ownerRef}"`) >= 0 && filter.indexOf("||") < 0;
};
```

Authorization here is **substring inspection of a client-authored PocketBase
filter DSL string**. `research_lane.pb.js:441-442` goes further and *rewrites*
it:

```js
q.set("filter", "(" + filter + ") && lane != \"research\" && lane != \""
  + SUPERVISED_LANE + "\" && lane != \"" + DEVICE_LANE + "\"");
```

A Worker over D1 cannot parse-and-rewrite a filter DSL it does not implement,
and should not: the check is fragile by construction (`owner_ref = "X"` with
spaces fails it; a nested `||` inside a quoted literal defeats it). **The
replacement is a per-collection query builder where `owner_ref` is bound from
the verified session and is not expressible by the caller at all.** That is a
strictly stronger property than the substring check, and it is the single
largest piece of work in this migration.

---

## PRODUCT COLLECTIONS (12)

`""` cells are marked **PUBLIC** in bold. That is not a formatting choice.

| Collection | listRule | viewRule | createRule | updateRule | deleteRule | What it must become in a Worker |
|---|---|---|---|---|---|---|
| **pendants** | **`""` PUBLIC**<br>`1700000000:19` | **`""` PUBLIC**<br>`:20` | **`""` PUBLIC**<br>`:21` | **`""` PUBLIC**<br>`:22` | **`""` PUBLIC**<br>`:23` | list/view: session-bound `WHERE owner_ref = :session_owner`. create: only the tokenless bootstrap path, and only a row with `paired=0` and `owner=''` (mirrors `guard.pb.js:468-472` for agents). update: only the one-shot claim — `paired` false→true, `owner_ref` = self, non-blank `owner` (`guard.pb.js:435-443`) — or the tokenless `last_seen`/`browser` heartbeat. **delete: service token only.** A public delete on the device table is a remote unpair for every customer. |
| **events** | **`""` PUBLIC**<br>`1700000000:38` | **`""` PUBLIC**<br>`:39` | **`""` PUBLIC**<br>`:40` | **`""` PUBLIC**<br>`:41` | **`""` PUBLIC**<br>`:42` | The densest table in the product — every transcript line the pendant ever heard. list/view: `WHERE owner_ref = :session_owner`, bound, never client-expressible. create: session owner, **or** the agent's narrow `read_line`/`read_fact` door (`guard.pb.js:297-320`) with all four of its conditions reproduced — kind allowlist, ≤400 chars, job in lane `supervised_read`, `watching_until` in the future. Missing or lapsed must **fail closed**. update/delete: service token only; nothing in any client updates or deletes an event. |
| **jobs** | **`""` PUBLIC**<br>`1700000001:17` | **`""` PUBLIC**<br>`:18` | **`""` PUBLIC**<br>`:19` | **`""` PUBLIC**<br>`:20` | **`""` PUBLIC**<br>`:21` | list: bound owner + the research-lane exclusion currently bolted on by string rewrite (`research_lane.pb.js:441-442`) — make it a `WHERE lane NOT IN (...)` clause in the builder. update: **the four-column deny-list is the security boundary, not a nicety.** `guard.pb.js:261-273` and its comment: a claimant that can write `watching_until` mints itself "a read nobody is watching"; one that can write `lane` launders a research job into browser-claimable work. Also port `workflow_guard.pb.js` (a `routerUse` at `:6`) — it refuses `done` without a receipt whose `verified` is true and whose `evidence` array is non-empty (`:202-211`). delete: service token only. |
| **agents** | **`""` PUBLIC**<br>`1700000002:24` | **`""` PUBLIC**<br>`:25` | **`""` PUBLIC**<br>`:26` | **`""` PUBLIC**<br>`:27` | **`""` PUBLIC**<br>`:28` | **`agent_token` is a bearer credential** and PocketBase hides it at the field level (`1700000026_agent_tokens.js:11`, `hidden: true`). D1 has no `hidden`. The Worker must never `SELECT *` this table into a response — enumerate columns. create: bootstrap only, `paired`/`owner` must be absent. view by `pair_code`: keep the counted-failure throttle (`guard.pb.js:117-165`, 10/IP and 60/all per 10 min) — six digits is a million codes and a script walks them in a day. update: the enumerated three columns for the agent itself, or the one-shot claim for a signed-in account. delete: service token only. |
| **owner_profile** | **`""` PUBLIC**<br>`1700000003:18` | **`""` PUBLIC**<br>`:19` | **`@request.body.owner_ref != ""`**<br>`1700000043:44` | **`""` PUBLIC**<br>`:21` | **`""` PUBLIC**<br>`:22` | Holds first name, last name, email, phone, birthday, timezone and free-form `facts`. The one non-empty rule in the tree is here: `createRule` was tightened from `""` because the combination of open-create and nullable `owner_ref` produced **3 orphan rows out of 10 in production** (`1700000043:6-8`) — permanently unreadable, still occupying the three-row window `sms.pb.js:166` uses to route an inbound text. In a Worker: `owner_ref` comes from the session and is never read from the body, which makes the rule unnecessary rather than ported. Keep `owner_profile_owner.pb.js` (`routerUse` at `:34`) as the same refusal one layer up. The `1700000054` unique index is the storage-level half and is in `schema.sql`. |
| **segments** | **`""` PUBLIC**<br>`1700000004:33` | **`""` PUBLIC**<br>`:34` | **`""` PUBLIC**<br>`:35` | **`""` PUBLIC**<br>`:36` | **`""` PUBLIC**<br>`:37` | Conversation envelopes: summaries and extracted entities. Same shape as `events`. list/view/create/update: bound owner. delete: service token only. |
| **owners** *(auth)* | `id = @request.auth.id`<br>`1700000008:50` | `id = @request.auth.id`<br>`:51` | **`""` PUBLIC**<br>`:52`, re-asserted `1700000013:23` | `id = @request.auth.id`<br>`:53` | `null` — superuser only<br>`:54` | **The only collection whose rules are already real authorization.** `authRule` is also `""` (`:48`) = any record may authenticate. The open `createRule` is deliberate and load-bearing: `1700000013` exists *because* production had `null` here and every signup returned 403 while the login screen looked fine. Keep signup open; keep read/write self-scoped. **delete stays impossible through the API** — deletion goes through `account_delete.pb.js`, which also writes the `purges` row. The hard part is not the rule: Workers have no native bcrypt, so the *verifier* must be rebuilt (see Unverified). `tokenKey` must be carried across or every live phone and Mac session dies at cutover. |
| **password_resets** | `null`<br>`1700000012:34` | `null`<br>`:35` | `null`<br>`:36` | `null`<br>`:37` | `null`<br>`:38` | **The strongest posture in the product half, and it is correct.** Reachable only from server code (`:10-12`). In a Worker: no route may expose this table at all. It holds SHA-256 of a 6-digit code — brute-forceable in a million tries if listable, which is why `attempts` is counted (`:24-26`). |
| **agent_llm_audit** | **`""` PUBLIC**<br>`1700000030:36` | **`""` PUBLIC**<br>`:37` | `null`<br>`:38` | `null`<br>`:39` | `null`<br>`:40` | Read-open so the service-token audit exporter can read it (`:34-35`); created only from inside the model proxy. **Its four `*_json` columns hold whole model requests and responses at up to 1 MB each** (`1700000032:11`) — i.e. verbatim prompts including the accessibility map of pages the user was signed into. Public list here is a full transcript leak of certification runs. Worker: service token only, no session path at all. Port `audit_retention.pb.js` — this table filled the 5 GB volume and took production down. |
| **agent_audit_sessions** | **`""` PUBLIC**<br>`1700000031:27` | **`""` PUBLIC**<br>`:28` | **`""` PUBLIC**<br>`:29` | **`""` PUBLIC**<br>`:30` | `null`<br>`:31` | A public **create** here is a public switch that turns retention of somebody's model traffic ON: it is the correlation window that makes untagged planner/verifier/recovery calls get written to `agent_llm_audit` (`:3-5`). Worker: service token only, all four operations. |
| **purges** | **`""` PUBLIC**<br>`1700000042:30` | **`""` PUBLIC**<br>`:31` | `null`<br>`1700000039:26` | **`""` PUBLIC**<br>`1700000044:36` | `null`<br>`1700000039:29` | The list of people who asked to be forgotten. `1700000039:26-28` says the intent exactly — *"a person asking to be forgotten must not be able to list who else asked"* — and then list/view were opened anyway (`1700000042`) because the worker's poll 403'd, and update was opened (`1700000044`) because stamping is a write. Both were the right call **given that `guard.pb.js` was the real gate**; both are a public erasure ledger without it. Worker: service token only, read + update. create stays server-internal (`account_delete.pb.js`), delete stays impossible — *"nothing should ever be able to erase the evidence that an erasure was asked for"* (`1700000044:31-33`). |
| **evidence** | **`""` PUBLIC**<br>`1700000045:85` | **`""` PUBLIC**<br>`:86` | **`""` PUBLIC**<br>`:87` | `null`<br>`:88` | `null`<br>`:89` | Screenshots of pages the user was logged into. `null` on update/delete is deliberate and is the whole security model of the collection: `share_expires` is what makes a public URL live or dead, so *"a caller who can PATCH it can mint itself a permanent public link to somebody's booking confirmation"* (`:42-45`). **Keep update and delete unreachable in the Worker, including for the service token's own generic routes** — only the named `/evidence/share` handler may move that column, and only for minutes. list/view: bound owner. create: agent credential whose resolved `owner_ref` equals the body's (`guard.pb.js:342-347`). Port the public-fetch counter (`fetches`, `:79-81`): expiry alone leaves a leaked URL an unlimited download for the length of the window. |

### Product-half summary

12 collections x 5 rules = **60 slots**, and they account for exactly:

* **42 are `""` (PUBLIC)** across 11 collections — pendants 5, events 5, jobs 5, agents 5, segments 5, owner_profile 4, agent_audit_sessions 4, purges 3, evidence 3, agent_llm_audit 2, owners 1. Plus `owners.authRule = ""`, which is a sixth rule outside this count.
* **14 are `null` (superuser only)** — password_resets 5, agent_llm_audit 3, evidence 2, purges 2, agent_audit_sessions 1, owners 1.
* **4 are a real expression** — `owners.listRule` / `viewRule` / `updateRule` (`id = @request.auth.id`, `1700000008:50-53`) and `owner_profile.createRule` (`@request.body.owner_ref != ""`, `1700000043:44`).

Four of sixty rule slots in the product half do authorization work of their
own. Forty-two delegate it to `guard.pb.js`, and fourteen refuse everyone.

---

## INTERNAL HQ (14)

**Every rule on every one of these 14 collections is `null`.** There is nothing
to flag and nothing to loosen. This is the correct posture and it is stated in
the migration itself:

> Five collections, every API rule null on purpose: these rows are reachable
> **ONLY** through the `/internal/*` hook routes in `internal_hq.pb.js` — never
> through `/api/collections/`, not even with the service token. The team
> dashboard is a separate room from the product, and the door between them
> stays shut. — `1700000038_internal_hq.js:5-8`

| Collection | list | view | create | update | delete | Set at | What it must become in a Worker |
|---|---|---|---|---|---|---|---|
| internal_people | `null` | `null` | `null` | `null` | `null` | `1700000038:20-24` | No generic route. Reachable only from the HQ Worker's own handlers. |
| internal_tracks | `null` | `null` | `null` | `null` | `null` | `1700000038:20-24` | ” |
| internal_todos | `null` | `null` | `null` | `null` | `null` | `1700000038:20-24` | ” |
| internal_events | `null` | `null` | `null` | `null` | `null` | `1700000038:20-24` | ” |
| internal_activity | `null` | `null` | `null` | `null` | `null` | `1700000038:20-24` | ” — append-only ledger; port `internal_hq_prune` (`internal_hq.pb.js:2642`), it exists because this table filled the volume. |
| internal_meter | `null` | `null` | `null` | `null` | `null` | `1700000038:20-24` | ” — the `login` row is the brute-force ceiling; *"a guard with no counter row fails open on the first attempt"* (`1700000048:347-348`). |
| internal_comments | `null` | `null` | `null` | `null` | `null` | `1700000048:187-194` | ” |
| internal_notifs | `null` | `null` | `null` | `null` | `null` | `1700000048:187-194` | ” |
| internal_reminders | `null` | `null` | `null` | `null` | `null` | `1700000048:187-194` | ” — port `internal_hq_sweep` (`internal_hq.pb.js:2139`, `*/5 * * * *`) as a Cron Trigger. |
| internal_sessions | `null` | `null` | `null` | `null` | `null` | `1700000048:187-194` | ” — `token_hash` is SHA-256 only. Never return it; never index a route on it that an unauthenticated caller can reach. |
| internal_config | `null` | `null` | `null` | `null` | `null` | `1700000048:187-194` | ” — must keep the `hq_v2_backfill` marker row or the one-shot boolean backfill re-runs and silently switches everyone's email back on (`1700000048:369-373`). |
| internal_expenses | `null` | `null` | `null` | `null` | `null` | `1700000050:25` — **inferred**, see below | ” |
| internal_passwords | `null` | `null` | `null` | `null` | `null` | `1700000050:25` — **inferred**, see below | ” — `secret_enc` is `$security.encrypt` ciphertext keyed by `ANTICIPY_VAULT_KEY`. See the migration hazard in `schema.sql` §2.13: a Worker cannot decrypt PocketBase's Go AES-GCM output without reimplementing it exactly. |
| internal_notes | `null` | `null` | `null` | `null` | `null` | `1700000052:13` — **inferred**, see below | ” |

**Inferred, not written:** `internal_expenses`, `internal_passwords` and
`internal_notes` are created by a `new Collection({type, name, fields, indexes})`
that passes **no rule properties at all** (`1700000050_expenses_vault.js:25`,
`1700000052_notes.js:13`). PocketBase's rule fields are `*string`, so the zero
value is `nil` = `null` = superuser-only, and both migrations assert exactly
that in their own headers (`1700000050:20-21`, `1700000052:10`). Not
independently confirmed against a running 0.30.4 instance — see Unverified.

HQ also authenticates entirely outside the collection rules:
`internal_hq.pb.js:4224` is a sixth `routerUse` covering `/internal/*` and
`/fellows/hq` (`:4226`), and identity is `internal_sessions.token_hash` +
`internal_people.code_hash`, not a PocketBase auth collection.

---

## The exposure ledger, if the 42 `""` slots are carried across literally

Ordered by how bad it is, not by table order.

1. **`events` list** — every transcript line the pendant has ever heard, for every customer, readable and **writable and deletable** by anyone.
2. **`evidence` list + create** — screenshots of pages users were signed into; and an open create is an anonymous upload endpoint into your storage bucket.
3. **`owner_profile` list** — name, email, phone, birthday, timezone, and the free-form `facts` blob, per person. Directly a re-identification set.
4. **`agent_llm_audit` list** — up to 1 MB of verbatim model request/response per row.
5. **`agents` list** — leaks `agent_token`, a live bearer credential, unless the Worker reproduces PocketBase's field-level `hidden`. D1 has no such thing.
6. **`jobs` update** — the four-column deny-list at `guard.pb.js:261-273` disappears; anyone forges `watching_until` and reads a supervised inbox with nobody watching.
7. **`purges` list** — the roster of people who asked to be erased.
8. **`pendants`/`agents` delete** — remote unpair for every customer, unauthenticated.

---

## Unverified

* **PocketBase's default rule value for a `new Collection()` that omits rule properties.** Asserted `null` above for `internal_expenses`, `internal_passwords` and `internal_notes` on the strength of Go's `*string` zero value and both migrations' own headers (`1700000050:20-21`, `1700000052:10`). Not confirmed against a live 0.30.4 instance. If PocketBase in fact defaults these to `""`, three HQ collections including **the password vault** are world-readable in production right now. **Verify this against production before anything else in this document.** The check is in `GAPS.md`.
* **`agent_audit_sessions.active` is declared `required: true` on a bool** (`1700000031:19`). If PocketBase's required-validator treats `false` as the zero value and refuses it, `active = false` was never writable through the record API, and the "inactive session" state the migration header describes (`:4-5`) is unreachable — sessions could only ever expire by `expires_at`, never be deactivated. Not tested. `schema.sql` deliberately emits no `CHECK` here either way.
* **The exact names of PocketBase's auto-created auth indexes** on `owners` (unique `tokenKey`, and a unique `email` index). PocketBase embeds the collection id in these names (e.g. `idx_tokenKey__<collectionId>`); `schema.sql` uses stable readable names instead. Harmless unless a migration script matches on the old name.
* **Whether `guard.pb.js` is currently *armed* in production** — its entire body is behind `if (!token) return e.next()` (`:25-26`), i.e. it is inert unless `ANTICIPY_SERVICE_TOKEN` is set in the Railway environment. If it is unset today, the 42 `""` slots are already live and this is an incident, not a migration risk. One request settles it; the command is in `GAPS.md`.
* **`bcrypt` in Workers.** `owners.password` holds bcrypt hashes PocketBase produced. Workers' WebCrypto has no bcrypt primitive, so verification needs a pure-JS/WASM bcrypt at some CPU cost per login, or a re-hash-on-next-successful-login migration to a WebCrypto-native KDF. Which of those is viable inside the Workers CPU limit is not verified here and is a real gate on cutover.
