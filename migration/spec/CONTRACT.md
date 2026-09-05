# The Behavioural Contract

**What this is.** The observable behaviour of the PocketBase backend at
`backend/`, written as a specification rather than as a description. Every
statement below is a claim about what an HTTP request produces, sourced to a
file and line. It exists because there is no test in this tree that exercises
the real PocketBase, so a port has no oracle. This document is the oracle, and
`migration/spec/contract_tests.py` is its executable half.

**How to use it.** Run `contract_tests.py` against the live PocketBase, record
the results, run it against the Cloudflare Worker, diff. A row that behaves
differently is either a bug in the port or a line in this document that was
wrong. Both are findings.

**Scope.** 20 files in `backend/pb_hooks/`, 8,795 lines:

| Kind | Count | Registered by |
|---|---|---|
| HTTP routes | 55 | `routerAdd` |
| Global middlewares | 6 | `routerUse` |
| Model hooks | 4 | `onRecordCreate` / `onRecordUpdate` / `onRecordAfterCreateSuccess` |
| Cron jobs | 2 | `cronAdd` |

Plus the whole of PocketBase's own generic REST API (`/api/collections/{name}/records`,
`/api/files/...`, `/api/realtime`, the auth endpoints), which the middlewares
gate but do not implement. **The generic API is part of the contract**: every
client in this tree speaks it directly. A port that exposes purpose-built
endpoints instead has not implemented this contract, it has replaced it — see
§8.

---

## §0. Conventions

### 0.1 Vocabulary of credentials

Six distinct things can authenticate a request. They are not interchangeable
and no route accepts more than the ones named in its own row.

| Name | Carried as | Who holds it | Where it is checked |
|---|---|---|---|
| **service token** | `X-Anticipy-Token: <ANTICIPY_SERVICE_TOKEN>` | the brain worker only | `guard.pb.js:37`, and independently by 5 routes |
| **account token** | `Authorization: <PocketBase auth token>` → `e.auth` | the iPhone app | `guard.pb.js:404`, `account_delete.pb.js:82` |
| **per-agent credential** | `X-Anticipy-Agent-ID` + `X-Anticipy-Agent-Token` | one Chrome install | `guard.pb.js:200-232`, `agent_key.pb.js:13`, `captcha_solve.pb.js:45` |
| **internal key** | `X-Internal-Key: <ANTICIPY_INTERNAL_KEY>` | the HQ team, shared | every `/internal/*` route |
| **HQ session** | `X-HQ-Session: <64 hex>` | one signed-in teammate | every living `/internal/*` route |
| **Clerk JWT** | request body `token`, HS256 under `CLERK_HQ_JWT_KEY` | anyone Clerk signed in | `internal_hq.pb.js:3400` only |
| *(none)* | — | anybody | the pairing bootstrap, `/agent/register`, `/auth/reset/*`, `/sms/inbound`, `/internal/cal/{token}`, `/internal/health`, `/fellows/hq` |

Two additional lease-shaped things are **not** credentials but are checked like
one: `X-Anticipy-Lease` (`workflow_guard.pb.js:193`) and the `X-Anticipy-Worker`
routing marker (`research_lane.pb.js:430`, only trusted when it arrives *with*
the service token).

### 0.2 The polarity rule

Stated in the source at `workflow_guard.pb.js:278-280`, and it governs
everything: *"Missing, unparseable, unresolvable, unrecognised, or unreachable
is a REJECTION, never a default. There is no fifth outcome that means
proceed."* Every place the current code violates that is called out below as a
**FAIL-OPEN** marker, because those are the places a port most easily gets
"right" in a way that changes behaviour.

There are exactly three deliberate fail-opens in the tree:

1. `guard.pb.js:26` — `ANTICIPY_SERVICE_TOKEN` unset means the entire data API
   is open. Local-dev affordance, live in production risk.
2. `workflow_guard.pb.js:24` — a job row with no `workflow_id` skips the whole
   state machine.
3. `research_lane.pb.js:431-433` — with no service token configured, the
   `X-Anticipy-Worker` header alone is believed.

And one deliberate fail-closed inversion: `internal_hq.pb.js:12-15` — with
`ANTICIPY_INTERNAL_KEY` unset, every `/internal/*` route answers **503**, it
does not open.

### 0.3 The JSVM isolation invariant

Repeated in eight files (`password_reset.pb.js:23-26`,
`audit_retention.pb.js:24-27`, `account_delete.pb.js:41-56`,
`evidence.pb.js:48-53`, `sms.pb.js:7-14`, `owner_profile_owner.pb.js:30-33`,
`research_lane.pb.js:273-277`, `internal_hq.pb.js:5-10`): a `const` at file top
level is **not in scope** inside a `routerAdd` callback. Every handler
redeclares every helper it uses.

This matters for the port in one specific way: **the duplication is the
contract**. Six copies of the pair-code date-parsing idiom, fourteen copies of
the HQ session door, two copies of `SHARE_FETCH_LIMIT`. When you consolidate
them into one shared function you must verify that all copies were in fact
identical, because several are not. Divergences found while writing this
document are marked **DIVERGENCE**.

### 0.4 Hook load order

PocketBase's JSVM plugin globs `pb_hooks/*.pb.js` and registers in glob
(lexicographic) order. `twilio_signature.js` does **not** match `*.pb.js` and is
therefore not a hook — it is `require`d by `sms.pb.js:101`. Middleware
execution order is therefore:

```
1. evidence.pb.js:56        (/api/files/* only)
2. guard.pb.js:24           (/api/collections/*, /api/realtime non-GET)
3. internal_hq.pb.js:4224   (/internal/*, /fellows/hq — CORS headers only)
4. owner_profile_owner.pb.js:34
5. research_lane.pb.js:272
6. workflow_guard.pb.js:6
```

**This ordering is load-bearing.** `guard.pb.js` refuses before
`research_lane.pb.js` and `workflow_guard.pb.js` ever see the request, so a
request that fails the guard produces `{"error":"forbidden"}` (403) and never a
409 workflow violation. A port that evaluates workflow rules first will produce
the wrong status code on a large class of requests. **UNVERIFIED**: that
PocketBase 0.30.4's glob is lexicographic rather than filesystem order — assert
it on the live instance before relying on it.

### 0.5 Response conventions

* `e.json(status, obj)` → `Content-Type: application/json`.
* `e.string(status, text)` → plain text (`sms.pb.js`, the OPTIONS preflight).
* `e.blob(status, ct, body)` → `/internal/cal/{token}` only.
* `e.html(status, body)` → `/fellows/hq` only.
* A middleware that calls `e.next()` produces whatever PocketBase itself would
  have produced. **The contract for those paths is PocketBase's own**: a
  successful record list is `{page, perPage, totalItems, totalPages, items[]}`;
  a 404 is `{"code":404,"message":"The requested resource wasn't found.","data":{}}`.

**Two PocketBase-native routes no hook registers, which the port must still
provide** because this migration's runbooks lean on them:
* `GET /api/health` → `200 {"code":200,"message":"API is healthy.","data":{}}`.
  The liveness probe. Not one of the 55.
* `GET /_/` — the Admin UI. `guard.pb.js:381-396` deliberately keeps it
  reachable (there is a production incident behind that block), but it must
  never be a way to read records.

---

## §1. THE SAFETY SYSTEM — `workflow_guard.pb.js`

`routerUse`, registered 6th. **This is the file the whole migration turns on.**
It is the only thing in the system that prevents a real-world action being
duplicated or falsely marked complete.

### 1.1 Applicability

```
path == /api/collections/jobs/records  OR  path startswith /api/collections/jobs/records/
AND method IN (POST, PATCH)
```
Anything else: `e.next()` (`:9-11`). **DELETE is not guarded at all** — a job row
can be destroyed without passing a single leg here. `jobs` has `deleteRule: ""`
(`pb_migrations/1700000001_jobs.js:22`), so any caller past `guard.pb.js` may
delete any job row.

On PATCH, `old` is loaded by id (`:17`); a lookup that throws leaves `old = null`,
and **a PATCH to a nonexistent id is then evaluated as if it were a create**,
including the ENTRY_STATUSES rule at `:217`.

### 1.2 The legacy escape hatch — FAIL-OPEN

```js
const workflow = String(body.workflow_id || oldWorkflow || "");
if (!workflow) return e.next();          // :24
```
**A job with no `workflow_id` skips this entire file.** Every leg below is
unreachable for such a row. `research_lane.pb.js:371-376` closes this for the
device lane specifically, and nothing closes it anywhere else.

### 1.3 Refusal shape

Every refusal is exactly:
```
409 {"error": "workflow violation", "detail": "<reason>"}
```
(`:26`). There is no other status code in this file. A port that returns 400 or
403 for any of these has broken the contract — brain/pb.py and the extension
both branch on 409.

### 1.4 Field derivation (body-or-row)

Every field is read as *body value if present, else the stored row's value,
else empty* (`:27-38`, helper `rowValue` at `:55`). One exception:
`nextVersion` uses `body.workflow_version != null` (not truthiness), so an
explicit `0` is honoured (`:30-31`).

`agentCaller` is true iff the `X-Anticipy-Agent-ID` header is non-empty
(`:36`) — **the header's mere presence, not its validity**. Validity was
established upstream by `guard.pb.js`.

### 1.5 The redundancy check (`params._workflow` mirrors the row)

`:44-96`. `params` is JSON-parsed; unparseable → `reject("workflow params are not parseable")`.
`params._workflow` absent or not an object → `reject("canonical workflow is missing from params")`.
`approval` and `receipt` are separately JSON-parsed off the row-or-body;
unparseable → `reject("row approval is not parseable")` / `reject("row receipt is not parseable")`.

Then **eleven equalities plus two deep-JSON comparisons must all hold**, or
`reject("job fields disagree with the embedded workflow")`:

| embedded key | must equal |
|---|---|
| `plan_id` | `workflow_id` |
| `version` | `workflow_version` |
| `state` | `workflow_state` |
| `goal` | `goal` |
| `consequence` | `consequence` |
| `lineage_key` | `lineage_key` |
| `owner_ref` | `owner_ref` |
| `scope_digest` | `scope_digest` |
| `effect_key` | `effect_key` |
| `attempts` | `attempts` (numeric) |
| `lease.token` | `lease_token` |
| `approval` (deep) | parsed `approval` column |
| `receipt` (deep) | parsed `receipt` column |

Deep comparison is **key-sorted-recursive JSON** (`ordered()` at `:70-78`,
`sameJSON` at `:79`). A port must reproduce the sort, or two semantically equal
approvals with different key order will disagree.

### 1.6 Required facts

`:97-103`. If `nextState ∈ {queued, running, succeeded}`, every name in
`embedded.required[]` must have a `embedded.facts[name]` that is neither `null`,
`undefined` nor `""` → else `reject("required facts are missing from the approved plan")`.

### 1.7 status ↔ state table

`:105-112`. Exact map; anything unlisted rejects with the template
`` reject(`status ${nextStatus} disagrees with state ${nextState}`) ``.

| status | permitted `workflow_state` |
|---|---|
| `awaiting_confirm` | `draft`, `awaiting_approval` |
| `queued` | `queued` |
| `running` | `running` |
| `needs_user` | `needs_user` |
| `done` | `succeeded` |
| `failed` | `failed` |
| `cancelled` | `cancelled` |

An unrecognised status has no entry, so `!stateForStatus[nextStatus]` is true
and it rejects. **Note the object-index hazard the file warns about elsewhere:
`stateForStatus["constructor"]` is truthy** (it inherits `Object.prototype.constructor`),
and `.includes` on a Function throws — which PocketBase surfaces as a 500, not a
409. **DIVERGENCE from the file's own stated discipline** (`:288-291`,
`:531-533`, `:441-444` all insist on arrays for exactly this reason);
this one table stayed an object. A port should use an array-of-pairs and
return the 409.

### 1.8 Universal requirements

`:113-118`:
* `!workflow || nextVersion < 1 || !lineage_key` → `reject("workflow id, version, and lineage are required")`
* `!owner_ref` → `reject("owner_ref is required for workflow jobs")`

### 1.9 THE PATCH LEG (`old` exists)

`:119-200`, in this order — **order is observable**, because the first
failure is the one reported:

1. `body.workflow_id` present and ≠ stored → `reject("workflow id is immutable")`
2. `body.owner_ref` present and ≠ stored → `reject("owner is immutable")`
3. `nextVersion < oldVersion` → `reject("workflow version cannot move backwards")`
4. **Transition table** (`:123-134`). `allowed[oldStatus]` must contain `nextStatus`, else
   `` reject(`illegal transition ${oldStatus} -> ${nextStatus}`) ``:

   | from | to |
   |---|---|
   | `awaiting_confirm` | `awaiting_confirm`, `queued`, `cancelled` |
   | `queued` | `queued`, `running`, `needs_user`, `cancelled` |
   | `running` | `running`, `needs_user`, `done`, `failed`, `cancelled`, `queued` |
   | `needs_user` | `needs_user`, `queued`, `cancelled` |
   | `failed` | `failed` |
   | `done` | `done` |
   | `cancelled` | `cancelled` |

   `failed`, `done` and `cancelled` are **absorbing**. An empty `oldStatus`
   (a row with no status) maps to `undefined` → `|| []` → nothing is allowed,
   so every transition off it rejects.
5. **Executor separation** (`:170-182`), checked *before* the version rule
   deliberately. If `agentCaller` AND any of:
   * `changesPlan` — `body.goal != null && body.goal !== old.goal`
   * `changesScope` — same shape on `scope_digest`
   * `changesEffect` — same shape on `effect_key`
   * `changesShelf2` — old `params._workflow` is readable AND any of
     `act`, `undo`, `announce`, `undo_of` differs by deep JSON, or `lineage_seq` differs numerically (`:163-169`)
   * `nextVersion !== oldVersion`
   * `changesApproval` — `body.approval != null && String(body.approval) !== old.approval`

   → `reject("an executor cannot rewrite or approve its plan")`.

   **`changesShelf2` is false when the OLD block cannot be parsed** (`:163`),
   deliberately (`:152-157`): a row already broken must stay parkable.
6. `(changesPlan || changesScope || changesEffect || changesShelf2) && nextVersion <= oldVersion`
   → `reject("changing a plan requires a new workflow version")`
7. **THE LEASE PROTOCOL** (`:188-200`). Applies when `oldStatus === "running"`
   AND `nextStatus !== "cancelled"`:
   * `old.lease_token` empty, or `X-Anticipy-Lease` header ≠ it →
     `reject("running update came from the wrong lease")`.
     Cancel is exempt: **a running job can always be cancelled without the lease.**
   * `expired` = `!old.lease_until || Date.parse(lease_until) <= now`.
     Note: `new Date("garbage").getTime()` is `NaN` and `NaN <= now` is **false**,
     so an *unparseable* `lease_until` reads as **not expired** — the opposite of
     the "missing or lapsed both fail closed" claim in the comment at `:196`.
     **DIVERGENCE / FAIL-OPEN.** `evidence.pb.js:129` gets this right with an
     explicit `isNaN` test; this file does not. A port must decide which
     behaviour it is implementing and the conformance suite pins the current one.
   * If expired and `nextStatus ∉ {queued, needs_user, failed}` →
     `reject("expired executor may only recover, park, or fail")`.

   **What an expired lease may still do:** re-queue itself, park to `needs_user`,
   or fail. It may not reach `done` (no false success after another executor is
   free to claim) and it may not stay `running`.

### 1.10 THE CREATE LEG (`old` is null) — ENTRY_STATUSES

`:201-221`. **This is the leg that exists because every other leg is keyed on a
transition and a POST is not one.** `jobs.createRule` is `""`
(`pb_migrations/1700000001_jobs.js:19`), so any caller may POST a row into
existence in any status.

```js
const ENTRY_STATUSES = ["awaiting_confirm", "queued"];
if (ENTRY_STATUSES.indexOf(nextStatus) < 0)
  return reject(`work cannot be created in ${nextStatus}`);
```

A create in `running`, `done`, `needs_user`, `failed`, `cancelled`, `""` or any
unrecognised string is refused. **Everything else in §1.9 is skipped on a create**
— no transition table, no immutability, no executor separation, no lease
protocol legs 1-7. What still runs on a create is: §1.5 redundancy, §1.6 facts,
§1.7 status↔state, §1.8 universals, and every leg in §1.11-§1.15 below.

### 1.11 SHELF 2 — earned, never spelled

`:222-632`. Read `:224-246` in the source before touching this; it is a warning
addressed to whoever ports it.

**The design.** Shelf 2 is `consequence === "reversible_local"`: work that runs
without waiting for a tap and is reported afterwards with a real undo. The
approval exemption for that lane **is not in any allowlist**. The allowlist is
one entry:

```js
const NO_APPROVAL_NEEDED = ["read_only"];   // :534  — an ARRAY, not an object-as-set
```

`read_only`'s exemption is earned by a client-side backstop
(`extension/background.js` fails any job whose consequence ≠ `read_only`).
Shelf 2 has no such backstop, so its exemption is earned **here, at request
time, by passing every leg**, and the variable is written so that *deleting the
leg removes the exemption* rather than granting it:

```js
let shelf2Earned = false;                                     // :597
if (live && consequence === SHELF2) {
  if (approvalRefusal() !== "") {                             // :614 stand-down
    const why = shelf2Refusal();
    if (why) return reject(why);
    shelf2Earned = true;                                      // :617
  }
}
...
if (live && !shelf2Earned && NO_APPROVAL_NEEDED.indexOf(consequence) < 0) {
  const why = approvalRefusal();
  if (why) return reject(why);                                // :631
}
```

**The stand-down at `:614` is the piece a port will get wrong.** Shelf 2 legs
run *only when the row has no valid approval*. A Shelf-2 row that *does* carry a
valid approval takes the ordinary approved path and is never asked the Shelf 2
questions — because a refused act is demoted and then tapped, and re-refusing it
forever was a real bug (`:598-611`).

**`live` is `nextStatus ∈ {queued, running}`** (`:594-595`). Shelf 2 legs and
the approval leg re-run at both, not only at `queued` (`:578-593`).

**The admitted sets** (`:286-314`), all parallel arrays, deliberately not
objects:

```
SHELF2                  = "reversible_local"
SHELF2_ACT_TYPES        = ["local_draft"]
SHELF2_REACH            = ["local_store"]
SHELF2_EXECUTOR         = ["anticipy_store"]
SHELF2_BINDS            = [["minted_by_us"]]
SHELF2_TARGET_PROVENANCE= ["minted_by_us"]
PROVENANCE_TAGS         = ["minted_by_us", "owner_supplied", "constant"]
GESTURE_KINDS           = ["tap"]
HAS_RUN                 = ["running", "needs_user", "done", "failed"]
```

**`shelf2Refusal()` (`:340-412`), in exact order.** All 15 codes:

| # | condition | code |
|---|---|---|
| 1 | `embedded.act` is not a plain object | `shelf2.act_type_not_admitted` |
| 2 | `act.act_type` ∉ `SHELF2_ACT_TYPES` | `shelf2.act_type_not_admitted` |
| 3 | `act.reach` ≠ `SHELF2_REACH[which]` | `shelf2.reach_disagrees` |
| 4 | `act.executor` ≠ `SHELF2_EXECUTOR[which]` | `shelf2.executor_disagrees` |
| 5 | `act.target` is not a plain object | `shelf2.act_target_unbound` |
| 6 | `act.target.provenance` ∉ `PROVENANCE_TAGS` | `shelf2.unknown_provenance` |
| 7 | `act.target.provenance` ≠ `SHELF2_TARGET_PROVENANCE[which]` | `shelf2.act_target_unbound` |
| 8 | `embedded.undo` not a plain object | `shelf2.no_undo_plan` |
| 9 | `undo.steps` not a non-empty array | `shelf2.no_undo_plan` |
| 10 | `undo.act_type` ≠ `act.act_type` | `shelf2.undo_addresses_another_act` |
| 11 | `undo.inputs` not an array | `shelf2.no_undo_plan` |
| 12 | any input not a plain object | `shelf2.no_undo_plan` |
| 13 | any input's `provenance` ∉ `PROVENANCE_TAGS` | `shelf2.unknown_provenance` |
| 14 | any input's `undo.held[provenance][ref]` is absent/`null`/`""` | `shelf2.unresolved_reference` |
| 15 | some tag in `SHELF2_BINDS[which]` is on no input | `shelf2.undo_binds_nothing` |
| 16 | the *target's own* ref does not resolve in `undo.held` | `shelf2.unresolved_reference` or `shelf2.unknown_provenance` |
| 17 | no input has both the target's `provenance` AND its `ref` | `shelf2.undo_misses_the_target` |
| 18 | `embedded.announce` not a plain object, or `announce.channel` blank after trim | `shelf2.no_announce_obligation` |
| 19 | row `owner_ref` empty, or `announce.owner_ref` ≠ it | `shelf2.announce_leaves_the_owner` |
| 20 | `!(Number(embedded.lineage_seq) >= 1)` | `shelf2.unordered_lineage` |

The act side (1-7) is settled **before the undo plan is read at all**
(`:348-350`), because the attack arrives with a flawless undo plan attached to a
lie about what the act reaches.

`ownValue()` (`:337`) uses `Object.prototype.hasOwnProperty.call` — inherited
property names never resolve a reference. A port using a plain `obj[key]` lookup
opens `constructor` as a valid provenance bucket.

**`seqRefusal()` (`:474-486`)** — allocation ordering. Runs only when
`nextStatus === "queued"` AND `consequence === SHELF2` AND `embedded.undo_of` is
**not** a plain object (`:621`). Reads the lineage; for every act in it whose
`plan_id` ≠ this workflow, if `a.at >= this.lineage_seq` → `shelf2.unordered_lineage`.
A `lineage_seq < 1` returns `""` here and is owned by `shelf2Refusal`.

**`orderRefusal()` (`:488-512`)** — LIFO compensation ordering. Runs on every
`nextStatus === "queued"` write regardless of consequence (`:625`), and returns
`""` immediately if `embedded.undo_of` is not a plain object. Otherwise:
* `!undo_of.plan_id || !lineage_key || !(undo_of.act_seq >= 1)` → `shelf2.unordered_lineage`
* the named act must be findable in the lineage at exactly `act_seq`, else `shelf2.unordered_lineage`
* any act later in the lineage (`a.at > seq`) whose status ∈ `HAS_RUN` → `shelf2.superseded_by_later_act`

**`readLineage()` (`:429-468`)** — one query:
`findRecordsByFilter("jobs", 'lineage_key = {:k} && consequence = {:c}', "-created", 500, 0)`
with `c = "reversible_local"`. Any of: query threw, a row's `params` unparseable,
a row's `_workflow` not an object, a row's `lineage_seq < 1` → `shelf2.lineage_unreadable`.
Two acts at the same `lineage_seq` → `shelf2.unordered_lineage`. Rows whose
`_workflow.undo_of` is a plain object are skipped (a compensation is not an act).

`shelf2.lineage_unreadable` is told apart from `shelf2.unordered_lineage` on
purpose (`:329-334`): our own outage must be distinguishable from a real refusal.

### 1.12 The approval gate

`approvalRefusal()` at `:539-576`. Two refusal strings:

* `JSON.parse(body.approval || old.approval || "")` throws →
  `"consequential work needs parseable approval"`. **Note: an absent approval
  parses `""`, which throws, so absent and malformed give the same message.**
* Otherwise, ALL of these must hold or → `"approval is not bound to this exact plan version"`:
  * `approval.plan_id === workflow`
  * `Number(approval.plan_version) === nextVersion`
  * `scope_digest` (body-or-row) is non-empty
  * `approval.scope_digest === scope_digest`
  * `words || tapped` where:
    * `words` = `String(approval.owner_words || "").trim()` non-empty
    * `tapped` = **all five** of:
      * `approval.gesture` is a plain object
      * `gesture.kind ∈ GESTURE_KINDS` (i.e. `"tap"`)
      * **`String(gesture.actor).trim() === rowValue("owner_ref")`** — the tap's
        actor must be the owner. Any other actor (another account, a service
        identity, the executor's own agent id) buys nothing.
      * `gesture.plan_id === workflow`
      * `Number(gesture.plan_version) === nextVersion`
      * `gesture.scope_digest === scope`

**The approval binding is therefore: plan id + plan version + scope digest, and
either spoken words or a tap whose actor is the owner.** An executor cannot
mint one — §1.9 leg 5 refuses `changesApproval` from an agent caller *before*
this gate runs.

### 1.13 Reconciliation after an uncertain effect

`:633-647`. Fires only when `nextStatus === "queued"` AND `old` exists AND
`old.effect_uncertain` is true.
* `JSON.parse(body.reconciliation)` throws (including absent) →
  `reject("uncertain effect needs reconciliation before retry")`
* else any of these → `reject("uncertain effect was not proven safe to retry")`:
  * `uncertain` is still true (body value if present, else the row's)
  * `!reconciliation.verified`
  * `reconciliation.effect_key !== effect_key`
  * `reconciliation.conclusion !== "not_applied"`
  * `!reconciliation.owner_words`
  * `reconciliation.evidence` is not a non-empty array

### 1.14 Lease possession by target status

`:648-661`.
* `nextStatus === "running"`: `lease_token`, `claimed_by` and `lease_until`
  (each body-or-row) must all be non-empty → else `reject("running work needs an actor and lease")`;
  and `Date.parse(lease_until) <= now` → `reject("running lease must expire in the future")`.
  (Same `NaN` asymmetry as §1.9: an unparseable `lease_until` passes.)
* Otherwise, **when `!old` (a create) or `oldStatus === "running"`**: a non-empty
  `lease_token` → `reject("non-running work may not retain an execution lease")`.
  The `!old` clause exists so a row cannot be *born* holding execution authority.

### 1.15 done needs verified evidence for this exact effect

`:662-671`. Only when `nextStatus === "done"`:
* `JSON.parse(body.receipt || old.receipt || "")` throws → `reject("done needs a parseable receipt")`
* any of: `!receipt.verified`, `receipt.effect_key !== effect_key` (body-or-row),
  `receipt.evidence` not an array, `receipt.evidence.length === 0`
  → `reject("done needs verified evidence for this exact effect")`

**"This exact effect" is the whole rule**: a receipt honestly describing a
*different* effect is refused, which is what stops a retry's receipt marking the
original attempt complete.

### 1.16 The complete refusal inventory

29 `return reject(...)` call sites; 25 with a literal or template message, 4
with a computed reason. **42 distinct refusal strings** reach the client:

**Structural (4):** `workflow params are not parseable` · `canonical workflow is
missing from params` · `row approval is not parseable` · `row receipt is not parseable`

**Agreement (2):** `job fields disagree with the embedded workflow` · `required
facts are missing from the approved plan`

**Shape (3):** `` status ${nextStatus} disagrees with state ${nextState} `` ·
`workflow id, version, and lineage are required` · `owner_ref is required for workflow jobs`

**Immutability & transition (5):** `workflow id is immutable` · `owner is
immutable` · `workflow version cannot move backwards` ·
`` illegal transition ${oldStatus} -> ${nextStatus} `` · `` work cannot be created in ${nextStatus} ``

**Authority (3):** `an executor cannot rewrite or approve its plan` · `changing a
plan requires a new workflow version` · `running update came from the wrong lease`

**Lease (4):** `expired executor may only recover, park, or fail` · `running work
needs an actor and lease` · `running lease must expire in the future` ·
`non-running work may not retain an execution lease`

**Approval (2):** `consequential work needs parseable approval` · `approval is not
bound to this exact plan version`

**Reconciliation (2):** `uncertain effect needs reconciliation before retry` ·
`uncertain effect was not proven safe to retry`

**Receipt (2):** `done needs a parseable receipt` · `done needs verified evidence
for this exact effect`

**Shelf 2 (15):** `shelf2.act_type_not_admitted` · `shelf2.reach_disagrees` ·
`shelf2.executor_disagrees` · `shelf2.no_undo_plan` ·
`shelf2.undo_addresses_another_act` · `shelf2.unknown_provenance` ·
`shelf2.unresolved_reference` · `shelf2.undo_binds_nothing` ·
`shelf2.act_target_unbound` · `shelf2.undo_misses_the_target` ·
`shelf2.no_announce_obligation` · `shelf2.announce_leaves_the_owner` ·
`shelf2.unordered_lineage` · `shelf2.lineage_unreadable` · `shelf2.superseded_by_later_act`

### 1.17 Side effects

**None.** This middleware writes nothing, calls nothing external, and increments
no counter. It either refuses or calls `e.next()`. That is the one property that
makes it safely re-runnable, and a port must preserve it.

---

## §2. THE SAFETY SYSTEM — `guard.pb.js`

`routerUse`, registered 2nd. The production lock on the entire data API.

### 2.1 The fail-open switch

```js
const token = $os.getenv("ANTICIPY_SERVICE_TOKEN");
if (!token) return e.next();                     // :25-26
```

**With `ANTICIPY_SERVICE_TOKEN` unset, this file does nothing at all.** Every
collection is then governed only by its own PocketBase rules, and `jobs`,
`agents`, `evidence`, `events` etc. all carry `listRule/viewRule/createRule/updateRule = ""`
(open to anyone) — see `pb_migrations/1700000001_jobs.js:19-23`.

For the port: **this is the single highest-consequence line in the tree.** A
Cloudflare Worker that reads the token from an unset binding and takes the same
branch publishes the whole database. The conformance suite asserts the
token-present behaviour; it cannot assert the token-absent behaviour without
being pointed at a deliberately unconfigured instance.

### 2.2 Applicability

```js
guarded = path.startsWith("/api/collections/")
       || (path === "/api/realtime" && method !== "GET")     // :32-34
```
`GET /api/realtime` (opening the SSE channel) is deliberately ungated —
EventSource cannot send headers, and the POST that attaches subscriptions is
what carries data.

### 2.3 The ladder, in order

Each rung either returns `e.next()`, returns a refusal, or falls to the next.
**Order is the contract.**

```
0.  X-Anticipy-Token === ANTICIPY_SERVICE_TOKEN            -> next()          :37
1.  X-Anticipy-Agent-ID present                            -> agent branch    :202
      (terminal: resolves and is authorised, or 403)
2.  /api/collections/owners/<auth endpoint>                -> next()          :367
3.  POST /api/collections/owners/records (signup)          -> next()          :377
4.  e.hasSuperuserAuth()                                   -> next()          :394
5.  e.auth (an account token)                              -> owner branch    :404
      (terminal: 403 or next())
6.  /api/collections/_superusers/*                         -> next()          :462
7.  POST /api/collections/agents/records (registration)                       :466
8.  GET agents|pendants records (pair lookup / owner lookup)                   :486
9.  PATCH agents|pendants/<id> (claim)                                        :511
10. everything else                                        -> 403 forbidden   :550
```

Rung 4 **must** stay above rung 5 (`:381-393`): in PocketBase 0.30.4 `e.auth` is
populated for superusers too, so an `if (e.auth)` above it makes the superuser
allowance unreachable and the Admin UI's `auth-refresh` returns
`{"error":"account is not allowed to access that collection"}`.

### 2.4 Rung 0 — the service token

`X-Anticipy-Token` equal to `ANTICIPY_SERVICE_TOKEN` → unconditional `e.next()`.
Only the brain worker holds it. Not a constant-time compare (`===`) —
**DIVERGENCE** from `internal_hq.pb.js`, which uses `$security.equal`
throughout. A port using a constant-time compare here is strictly better and
observationally identical.

### 2.5 Rung 1 — the per-agent credential, and why it is terminal

`:197-357`. **Sending `X-Anticipy-Agent-ID` at all COMMITS the caller to that
identity.**

```js
if (agentToken.length >= 40) {                    // :226 — the column's own min
  agent = findFirstRecordByFilter("agents",
    'agent_id = {:id} && agent_token = {:token}', {id, token});
}
if (!agent) return e.json(403, {"error": "agent credential is not recognized"});  // :356
```

A token shorter than 40 chars skips the query entirely (that is the
`agent_token` column minimum, `pb_migrations/1700000026_agent_tokens.js:12`) and
lands on the same 403. **A thrown lookup and an empty one are deliberately not
distinguished** (`:349-354`). Nothing falls through to the anonymous bootstrap.

Note the credential does **not** require `paired = true` here (unlike
`/agent/key` and `/agent/llm`, which do). An unpaired agent with a valid token
gets an empty `owner_ref` and therefore fails every `ownerRef && ...` clause
below, landing on `403 {"error": "agent is not allowed to access that record"}`.

Once resolved, `ownerRef = agent.owner_ref` and exactly five things are permitted:

**(a) Self-patch** — `PATCH /api/collections/agents/records/<agent.id>` where
**every** body key ∈ `{agent_token, last_seen, browser}` (`:235-238`).
An empty body satisfies `every` vacuously and is allowed.

**(b) Own jobs list** — `GET /api/collections/jobs/records` where
`ownedList(ownerRef)` holds. See §2.7.

**(c) Own job read/write, minus evidence columns** — path
`/api/collections/jobs/records/<id>`, method GET or PATCH, and the stored row's
`owner_ref === ownerRef` (`:262-264`). Then:

```js
const EVIDENCE = { watching_until: 1, lane: 1, owner_ref: 1, owner: 1 };   // :261
writesEvidence = any body key in EVIDENCE
echo          = every body key is either not in EVIDENCE,
                or is owner_ref whose value === ownerRef
allow iff (!writesEvidence || echo)                                        // :271
```

**A claimant may describe its own progress and nothing else.** `watching_until`
would mint the supervision `research_lane.pb.js` checks; `lane` would remove the
row from every lane-keyed leg. `owner_ref` echoed back unchanged is allowed
because PocketBase clients resend fields.

Note `EVIDENCE` is an object-as-set, so a body key named `constructor` is
"evidence" and a body key named `toString` is too. That direction is
fail-*closed* (it refuses more), so it is a wart, not a hole.

**(d) Narration into `events`** — `POST /api/collections/events/records` only
when **all** of (`:297-322`):
* `body.kind ∈ {"read_line", "read_fact"}`
* `body.owner_ref === ownerRef` (required, not merely permitted)
* `0 < String(body.text).length <= 400`
* `jobs[body.goal]` exists, has `owner_ref === ownerRef`, and `lane === "supervised_read"`
* that job's `watching_until` parses to a time strictly in the future

**(e) Evidence deposit** — `POST /api/collections/evidence/records` where
`body.owner_ref === ownerRef` (`:342-346`). Create only. `evidence` has
`updateRule: null, deleteRule: null` (`pb_migrations/1700000045_evidence.js:88-89`),
so PocketBase itself refuses update and delete regardless of this branch.

Anything else from a resolved agent: `403 {"error": "agent is not allowed to access that record"}`.

### 2.6 Rungs 2-3 — the front door

`:367-379`. Unconditional `e.next()` for:
* `path` starting `/api/collections/owners/` and ending in one of
  `auth-with-password`, `auth-with-oauth2`, `auth-with-otp`, `request-otp`,
  `auth-refresh`, `request-password-reset`, `confirm-password-reset`,
  `request-verification`, `confirm-verification`, `auth-methods`
* `POST /api/collections/owners/records` (signup — governed by the collection's
  own `createRule`)

Both exist because the guard was gating login itself.

### 2.7 Rung 5 — the account branch, and `ownedList`

`:403-453`. Terminal: it returns or refuses, never falls through.

```js
const ownedList = (ownerRef) => {
  const filter = url.query().get("filter") || "";
  return filter.indexOf(`owner_ref="${ownerRef}"`) >= 0
      && filter.indexOf("||") < 0;                            // :45-50
};
```

**THE FILTER RULE, stated exactly.** A list request is authorised iff its
`filter` query parameter (a) contains the literal substring
`owner_ref="<id>"` — double quotes, no spaces around `=` — and (b) contains no
`||` anywhere. `&&` can only narrow the owner set; `||` can widen it.

This is the authorization model. **It is string inspection of a query DSL, and
it is why there is no purpose-built API to swap.** Consequences a port must
reproduce or consciously replace:

* `filter=owner_ref="X"` — allowed.
* `filter=owner_ref="X" && status="queued"` — allowed.
* `filter=owner_ref = "X"` (spaces) — **refused**, the substring does not match.
* `filter=owner_ref='X'` (single quotes) — **refused**.
* `filter=owner_ref="X" || owner_ref="Y"` — refused by the `||` test.
* `filter=status="queued" && (owner_ref="X" || owner_ref="Y")` — refused.
* `filter=owner_ref="X" && notes~"a||b"` — **refused**, because `||` inside a
  string literal is not distinguished from an operator.
* A filter containing `owner_ref="X"` as part of a *longer field name*
  (e.g. `not_owner_ref="X"`) would pass the substring test. No such column
  exists today; a port that adds one opens this.

Path matching (`:416`):
```
^/api/collections/(jobs|events|owner_profile|segments|agents|pendants|evidence)/records(?:/([^/]+))?$
```
Any other collection under an account token → `403 {"error": "account is not allowed to access that collection"}`.

Then, in order:
1. `path === /api/collections/owners/records/<authId>` (any method) → `next()` (`:408`)
2. **Pair-code lookup**, pre-owner: no record id, GET, collection ∈ {agents, pendants},
   and `filter` matches `/^\s*pair_code\s*=\s*"(\d{6})"\s*$/` → `pairLookup()` (§2.8)
3. **Claim**: record id present, PATCH, collection ∈ {agents, pendants}, and
   the stored row has `paired === false`, and `body.paired === true`, and
   `body.owner_ref === authId`, and `body.owner` is a non-blank string → `next()` (`:441-443`)
4. `ownedList(authId)` on a list GET → `next()`
5. `POST` with `body.owner_ref === authId` → `next()`
6. record id whose stored `owner_ref === authId`, and body either omits
   `owner_ref` or echoes `authId` → `next()`
7. otherwise `403 {"error": "record belongs to a different owner"}`

**The blank-owner ban** in step 3 (`:437-440`) exists because a claim naming no
`owner` produced the phone-paired/browser-orphaned split-brain that shipped on
2026-08-14.

### 2.8 `pairLookup` — the guess ceiling

`:116-195`. Called from two places: the signed-in branch (`:432`) and the
anonymous bootstrap (`:494`). Identical logic both times.

```
WINDOW_MS   = 10 * 60 * 1000      fixed window, not sliding
MAX_PER_IP  = 10                  per e.realIP()
MAX_ALL     = 60                  across every caller
PREFIX      = "anticipy_pair_fails:"
ALL_KEY     = "anticipy_pair_fails_all"
```

Counter storage is `e.app.store()` — PocketBase's process-wide in-memory KV,
shared across the isolated hook runtimes. Buckets are plain strings
`"<windowStartMs>|<failures>"` because only exported primitives cross runtime
boundaries.

Order of operations:
1. `e.app.store()` unavailable → **503**
   `{"error":"pairing is briefly unavailable","detail":"the server cannot count pair code attempts right now"}`.
   *Refusing is the honest failure* — serving lookups nobody counts is the hole.
2. Read both buckets. A bucket that is missing, unparseable, or older than
   `WINDOW_MS` restarts from now with 0 failures.
3. `mine.fails >= 10 || all.fails >= 60` → **429**
   `{"error":"too many pair code attempts","detail":"wait a few minutes, then read the current code off the extension popup"}`
4. `findFirstRecordByFilter(collection, 'pair_code = {:code}')`.
   * Found AND `paired === false` → `e.next()`. **A successful pairing spends nothing.**
   * Otherwise spend one failure on both buckets (a lost increment under
     concurrency costs a guess, not the ceiling — `:170-172`).
   * If `all` had just rolled over, sweep stale per-IP keys (`:182-189`) — at most
     once per ten minutes, never on the pairing path.
   * Not found → `e.next()` (PocketBase answers an empty list, so the phone can
     say "that code didn't match" instead of "I can't reach Anticipy").
   * Found but **already paired** → **403**
     `{"error":"that pair code is already paired","detail":"read the current code off the extension popup"}`

**Honest scope, recorded in the source (`:110-115`):** this makes the walk slow
and loud, it does not end it. Pair codes are permanent once minted
(`agent_auth.pb.js:47-53`). Behind Railway's edge every caller may share one
`realIP()` bucket, which over-throttles; `MAX_ALL` is what actually bounds the
walk.

**Port hazard:** `e.app.store()` is per-process memory. A Cloudflare Worker has
no process. See §8.2.

### 2.9 Rungs 7-9 — the tokenless pairing bootstrap

**Rung 7 — agent self-registration** (`:466-470`).
`POST /api/collections/agents/records` with a body carrying neither a truthy
`paired` nor a truthy `owner` → `next()`. Otherwise `403 {"error":"forbidden"}`.

**Rung 8 — anonymous lookup** (`:486-501`). `GET` on the agents or pendants
records path:
* `perPage > 50` → `403 {"error":"forbidden"}` (parsed with `parseInt(..., 10)`,
  default `"30"`; a non-numeric value yields `NaN` and `NaN > 50` is false, so it
  passes)
* `filter` fully matching `/^\s*pair_code\s*=\s*"(\d{6})"\s*$/` → `pairLookup()`
* `filter` fully matching `/^\s*owner\s*=\s*"[A-Za-z0-9._-]{8,64}"\s*$/` → `next()`
  (a fresh app install finds its own paired agent by its high-entropy owner id)
* anything else → `403 {"error":"forbidden"}`

**THE FILTER MUST MATCH WHOLE** (`:476-485`). This was `.test()` against the raw
filter, which matches a substring, so
`?filter=pair_code="000000" || id!=""&perPage=500` returned every agent row to
an anonymous caller — proven live against production on 2026-08-03. The anchors
`^\s*` and `\s*$` are the fix and are non-negotiable in a port.

**Rung 9 — anonymous claim** (`:511-548`). `PATCH` on
`/api/collections/agents/records/<id>` or the pendants equivalent:
* `"owner_ref" in body` → **403**
  `{"error":"pair from the signed-in app","detail":"an owner_ref may only be claimed by the account it belongs to"}`.
  An unauthenticated caller could otherwise register their own agent and PATCH a
  harvested victim `owner_ref` onto it.
* Otherwise allowed iff the row exists, the body has ≥1 key, **every** key ∈
  `{owner, paired, last_seen, browser}`, and either:
  * `touchesPairing` is false (`owner` and `paired` both absent) — **so a paired
    row's `last_seen`/`browser` ARE still tokenlessly writable**, stated plainly
    at `:506-510`; the worst an anonymous caller achieves is making an agent look
    alive — or
  * the row is not yet paired **and** `body.owner` is a non-blank string.
* Otherwise `403 {"error":"forbidden"}`.

### 2.10 Rung 10

`return e.json(403, {"error": "forbidden"})` (`:550`). Anything reaching here.

### 2.11 Side effects

Two: the pair-code failure counters in `e.app.store()`, and a `console.log` on
an unrecognised agent credential (`:355`) and on a missing store (`:130`).
No rows written, no external calls.

---

## §3. THE SAFETY SYSTEM — `research_lane.pb.js`

`routerUse`, registered 5th — **after** `guard.pb.js`, so everything here has
already passed the guard.

### 3.1 Who counts as the worker

```js
const serviceToken = $os.getenv("ANTICIPY_SERVICE_TOKEN") || "";
const marker       = !!e.request.header.get("X-Anticipy-Worker");
const fromWorker   = serviceToken
  ? (marker && e.request.header.get("X-Anticipy-Token") === serviceToken)
  : marker;                                                  // :429-433
```

With a service token configured, `fromWorker` requires **both** the marker and
the token. With none configured it believes the bare header — the third
deliberate fail-open (§0.2). This is a *routing* distinction, not a credential:
the worker and the extension hold the same service token, so request shape is
the only thing that can tell them apart.

### 3.2 LEG 1 — THE FILTER REWRITE

`:436-452`. Fires on `GET /api/collections/jobs/records` when `!fromWorker`.

```js
const QUEUED_POLL  = /status\s*=\s*"queued"/;
const MENTIONS_LANE= /\blane\b/;

if (QUEUED_POLL.test(filter) && !MENTIONS_LANE.test(filter)) {
  q.set("filter", "(" + filter + ") && lane != \"research\""
                + " && lane != \"supervised_read\""
                + " && lane != \"device_calendar\"");
  e.request.url.rawQuery = q.encode();
}
```

**The server rewrites the caller's query.** A jobs list whose filter mentions
`status="queued"` and does not mention `lane` is silently narrowed to exclude
three lanes. Extensions in the wild (0.2.3 and older) poll with
`status="queued" && (owner="…" || owner="")` and would otherwise claim research
work forever; client code cannot be recalled, so the server rewrites.

Interactions a port must preserve:
* The rewrite happens **after** `guard.pb.js` has already evaluated `ownedList`
  against the *original* filter. Rewriting earlier would change the guard's
  answer (the appended clauses contain no `||`, so in practice the outcome is
  the same, but the ordering is what makes that true).
* A filter that mentions `lane` anywhere — including inside a string literal —
  is left alone.
* A filter using `status = "queued"` with spaces still matches (`\s*` in the regex).
* `status='queued'` (single quotes) does **not** match, and is not rewritten.
* A rewrite that throws is caught and logged; the request proceeds unrewritten
  (`:445-450`). Layer 2 still holds the invariant.

`e.next()` unconditionally after this leg — GET requests never reach the claim legs.

### 3.3 Applicability of the write legs

`creates = POST /api/collections/jobs/records`;
`updates = PATCH /api/collections/jobs/records/<id>` (`:456-458`).
On an update the row is read once (`:467-469`); a read that throws leaves
`rec = null`.

Lane values are normalised: `String(v).trim().toLowerCase()` (`:474`). Raw
comparison let `Supervised_Read` and `" research "` escape both the research
refusal and the lease requirement at once.

### 3.4 LEG 2 — the lane is immutable

`:556-562`. On an **update** only, when the body names a lane that differs from
the stored lane and this is not a research handback → **403**:

```json
{"error": "a job's lane is decided when it is minted, never rewritten",
 "detail": "the lane says which hand may run this errand, so a claimant that could name it could name its way out of every check on it"}
```

Keyed on the method, not on `rec`: a PATCH whose row cannot be read must not let
its body become the authority on the lane. Echoing the stored value unchanged is
allowed.

### 3.5 The research handback — the one legitimate lane change

`isResearchHandback()` at `:509-544`. Deliberately narrower than `fromWorker`.
**All** must hold:
* this is an update, `fromWorker` is true, `rec` exists
* stored lane is `"research"`, body lane is `""` (the empty browser lane)
* stored `status === "queued"`
* the body's keys are exactly `{lane, params}` — `params` required, nothing else permitted
* both old and new `params` parse to plain objects
* `_workflow` is deep-identical between them
* old `params._research_gate` is a plain object with `handback === true`
* new `_research_gate` is a plain object, does **not** have an own `handback`
  key, and has a boolean `researched`
* every other top-level `params` key is deep-identical in both directions,
  except `_research_gate` and `procedure`
* every `_research_gate` key is identical in both directions, except
  `handback`, `why` and `researched`

Anything short of that is an ordinary lane rewrite and is refused. *A service
credential is not permission to rewrite a plan.*

### 3.6 LEG 3 — device-lane shape

`:571-583`. Fires on **create and update**, for `lane === "device_calendar"`,
only while the write leaves the row live (`status ∈ {queued, running}`, body
value if present else the row's).

`deviceShapeRefusal()` (`:351-415`) reads **both** the stored row and this
request — "the row says it, and this write does not un-say it" — and returns a
sentence, or `""`:

| condition | detail |
|---|---|
| no `workflow_id` stated, or any stated one is blank | `a calendar errand with no workflow skips the confirmation gate entirely` |
| any stated `consequence` ≠ `"consequential"`, and the offending one is `read_only` | `read_only carries an approval exemption that is earned by a backstop this lane does not have — a calendar write acts on the world` |
| ... and the offending one is `reversible_local` | `Shelf 2 admits local_draft and nothing else; EventKit assigns the event identifier on save, which is the undo shape §6.1 excludes` |
| ... any other value, including `""` | `` a calendar errand must be held for a tap; this one says "<value>" `` |
| a declared act type ∉ `["calendar_write","calendar_undo"]` | `` the device lane carries calendar acts and nothing else; this one declares "<value>" `` |
| no act declared anywhere, or any place declares `null` | `a calendar errand has to say which calendar act it is; this one declares none` |

Refusal is **403**:
```json
{"error": "that calendar errand is not safe to run yet", "detail": "<the sentence above>"}
```

`declaredActTypes()` (`:316-341`) reads `params._workflow.act.act_type` from
the row and, if present, from the body. A body `params` may already be an
object; a row's is always a string. `null` means "that place declared no act I
could read", and every cause of `null` is the same answer, because a refusal
that distinguishes them tells a forger which shape to send next.

### 3.7 LEG 4 — separation of duties on the device lane

`:596-631`. Still inside `lane === "device_calendar"`. `rewritesApproval` is
`body.approval != null && String(body.approval) !== rec.approval` (an echo is
not a rewrite).

* **On a create**, `rewritesApproval` → **403**
  ```json
  {"error":"the tap and the errand it releases are two separate writes",
   "detail":"an errand that does not yet exist has not been tapped; mint it held, show it to him, then write the tap onto the row"}
  ```
* **On any write** where `rewritesApproval` AND (`live` OR `"claimed_by" in body`
  OR `body.status === "running"`) → **403**
  ```json
  {"error":"the tap and the errand it releases are two separate writes",
   "detail":"a hand may not mint the approval for the act it is about to perform; leave the errand held, write the tap, then release it"}
  ```

This is a refusal and nothing else — the file contains no approval check, never
parses an approval, and can never let a row through *because* one is present.
It exists because `workflow_guard`'s executor-separation leg is keyed on the
agent header, which the phone does not send, so on the one lane where the
executor *is* the phone that leg cannot fire.

### 3.8 Creates stop here

`if (creates) return e.next();` (`:637`). Every claim leg below is PATCH-only:
a row born carrying `claimed_by` is a row with a label on it; it still cannot
run until a PATCH moves it, and that PATCH is what the claim legs judge.

### 3.9 LEG 5 — the claim legs

`claims = ("claimed_by" in b) || b.status === "running"` (`:639`).
Fires only when `claims && !fromWorker`.

**Research:** `lane === "research"` and `body.claimed_by !== "worker-research"`
→ **403** `{"error":"research jobs run in the worker, never in a browser"}`.
The claimant-name belt is honoured for research and nothing else — extending it
would hand every reader a one-line bypass of the supervision lease.

**Supervised read:** `lane === "supervised_read"` and the **stored** row's
`watching_until` does not parse to a time strictly in the future → **403**
`{"error":"a read nobody is watching is not a supervised read — open the app and stay on the screen"}`.
Read off the row, never off the request: a claimant cannot mint its own
permission in the same breath as claiming. Missing, unparseable and past all
take the same path — this fails closed.

Re-checked on **every** claiming PATCH, not once at the start, because `claims`
is also true for `status="running"` — so the extension's own progress updates
are refused the moment the 30-second lease lapses.

**Routing, both directions** (`:704-721`), skipped entirely for a superuser:
```js
let superuser = false;
try { superuser = e.hasSuperuserAuth(); } catch (_) { superuser = false; }
const ownerSession = !!e.auth;
if (!superuser) {
  if (lane === "device_calendar" && !ownerSession)
    403 {"error":"a calendar errand happens on your phone, never in a browser"}
  if (lane !== "device_calendar" && ownerSession)
    403 {"error":"your phone does not run browser errands — it approves them"}
}
```
A thrown `hasSuperuserAuth` reads as **false**, not true — one unanswered
question must not switch both legs off. Placed after the research leg on purpose:
an owner session stamping `claimed_by: "worker-research"` walks past that leg's
legacy belt and is caught here.

### 3.10 Side effects

One: the query-string rewrite in Leg 1 mutates `e.request.url.rawQuery` for the
rest of the chain. Nothing is written, nothing external is called.

---

## §4. THE SAFETY SYSTEM — the remaining three

### 4.1 `evidence.pb.js` — the anonymous fetch door

**`routerUse`, registered 1st.** `:56-147`. Applies to `path.startsWith("/api/files/")`.

The exposure this exists to bound, stated at `:9-17`: Twilio's `MediaUrl` does
not accept bytes, a `data:` URI, or an authenticated URL. It takes a URL,
fetches it **from its own infrastructure with no credential of ours**, and
attaches what comes back. So there must be an https URL that answers an
anonymous GET with a photograph of a page the owner was logged into.

```
SHARE_FETCH_LIMIT = 5           :57
```

Order:
1. `e.hasSuperuserAuth()` → `next()` (`:66`). Same ordering trap as `guard.pb.js`.
2. Parse `/api/files/{collectionKey}/{recordId}/{filename}`; either part
   missing → `gone()`.
3. **Resolve the collection, never compare the string** (`:80-89`): PocketBase
   accepts the collection's 15-char id here as well as its name, so a gate
   matching the literal `"evidence"` is walked past by anyone who read the id off
   a collections listing. `findCollectionByNameOrId(collectionKey).name` must
   equal `"evidence"`, else `gone()`. **Every other collection fails closed.**
4. `findRecordById("evidence", recordId)` — thrown and missing get the same
   answer, `gone()`.
5. **Two non-public doors, neither of which spends the ceiling or needs a window:**
   * `ANTICIPY_SERVICE_TOKEN` set AND `X-Anticipy-Token` equals it → `next()`
   * `e.auth` present AND `e.auth.collection().name === "owners"` AND
     `e.auth.id === rec.owner_ref` → `next()`.
     **The collection must be checked as well as the id** — `e.auth` is populated
     for any auth record, so a paired agent row whose id happened to match an
     `owner_ref` would otherwise read somebody's screenshots.
6. **The public door:**
   * `share_expires` empty → `gone()`. **DEFAULT DENY: a row nobody deliberately
     shared has no public URL at all.**
   * `until = Date.parse(share_expires)`; `!until || isNaN(until) || until <= now`
     → `gone()`. The explicit `isNaN` is the correct form of the idiom that
     `workflow_guard.pb.js:196` gets wrong.
   * `spent = Number(rec.fetches || 0)`; `!(spent >= 0) || spent >= 5` → `gone()`
   * increment `fetches` and save. **If the save throws, `gone()`** (`:134-145`) —
     serving what nobody is counting is the exact hole the ceiling closes. It
     costs a text that arrives without its picture, which is the designed fallback.
   * → `next()`

**Every refusal is the same:** `404 {"error": "that evidence is not available"}`.
"No such row", "never shared", "expired" and "spent" are deliberately
indistinguishable — telling them apart turns the endpoint into an oracle for
walking record ids.

**Side effects:** `evidence.fetches` incremented by 1 on each successful public
fetch. A `console.log` when the count could not be persisted.

### 4.2 `owner_profile_owner.pb.js` — a profile with no owner

`routerUse`, registered 4th. `:34-78`. Applies to
`/api/collections/owner_profile/records[/*]`, POST and PATCH only.

`owner_ref` is a `maxSelect:1` relation, so a client may legitimately send it as
an id **or as a one-element array**; `named()` (`:47-50`) accepts both and
requires a non-blank string.

* **POST** without a named `owner_ref` → **400**
  ```json
  {"error":"owner_profile needs an owner",
   "detail":"owner_ref must name the account this profile belongs to; a profile created without one can never be read back, because every lookup in the product filters on owner_ref. Sign in first, then save."}
  ```
* **PATCH** where `"owner_ref" in body` and it is **not** named → **400**
  ```json
  {"error":"owner_profile needs an owner",
   "detail":"clearing owner_ref would strand this profile: nothing can find a profile that names no account."}
  ```
* A PATCH that never mentions `owner_ref` is left alone — that is the ordinary
  case and it includes the adoption of a legacy row and every write to the three
  orphans already in production.

400, not 403: this is a malformed record, not a permission problem.
`claim_legacy`'s adoption runs through `e.app.save()` inside a hook, not through
the router, so nothing here can block a rescue.

### 4.3 `internal_hq.pb.js:4224` — the CORS middleware

`routerUse`, registered 3rd. Applies when `path.startsWith("/internal/")` or
`path === "/fellows/hq"`. Sets, **only when the request's `Origin` is in the
allow list**:

```
Access-Control-Allow-Origin:  <the request's own Origin, echoed>
Vary: Origin
Access-Control-Allow-Headers: X-Internal-Key, X-HQ-Session, Content-Type
Access-Control-Allow-Methods: GET, POST, PATCH, OPTIONS
Access-Control-Max-Age: 86400
```

Allow list: `[ANTICIPY_HQ_ORIGIN || "https://www.anticipy.ai", "https://anticipy.ai"]`.
**Never `*`** — these routes carry a credential in a custom header. Always calls
`e.next()`; it refuses nothing.

---

## §5. THE SAFETY SYSTEM — `password_reset.pb.js` and `account_delete.pb.js`

### 5.1 `POST /auth/reset/request`

`:28-180`. **Unauthenticated.** Lives outside `/api/collections/`, so
`guard.pb.js` does not gate it.

**Request:** `{"email": "..."}`

**Response — always, for every outcome:**
```
200 {"ok": true,
     "message": "If that account exists and has a phone number, a code is on its way by text."}
```

There is no other response from this route. Not for a missing body, not for a
missing email, not for an unknown account, not for an account with no phone, not
for a throttle hit, not for a Twilio failure, not for a failed database write.
**The reply is identical whether or not the account exists** — otherwise this
endpoint answers "does Omar have an account here?" one address at a time.

Constants (`:34-36`): `RESET_TTL_SECONDS = 600`, `RESET_MIN_GAP_SECONDS = 60`,
`RESET_MAX_PER_HOUR = 5`.

Flow:
1. `email` lowercased and trimmed; blank → `same()`.
2. `findFirstRecordByFilter("owners", "email = {:email}")`; throw or miss → `same()`.
3. **Phone resolution** (`:55-73`): if the account has ≥1 `owner_profile` row
   (newest by `-updated`), that row's `phone` is canonical **including when it is
   empty**. Only an account with *no* profile row at all falls back to
   `owners.phone`. A profile read that throws → `same()` (unknown is not absent;
   a failed read must never resurrect a stale number).
4. Blank phone → `same()`.
5. **Throttle** (`:80-93`): read the newest 20 `password_resets` for this owner.
   Any row created within 60 s that is not `used` → `same()`. ≥5 rows created
   within the last hour → `same()`.
6. Mint `code = $security.randomStringWithAlphabet(6, "0123456789")`.
7. **Send FIRST, persist second** (`:97-98`). If the text cannot leave the
   building, no live code is left in the database pretending it did. Credential
   preference: `TWILIO_API_KEY_SID` + `TWILIO_API_KEY_SECRET` if **both** are
   set, else `TWILIO_ACCOUNT_SID` + `TWILIO_AUTH_TOKEN`. Half-set logs a warning
   and falls back. Missing `sid`/`from`/`user`/`secret` → log and `same()`.
   Non-2xx or a thrown request → log and `same()`.
   Base URL is `TWILIO_API_BASE || "https://api.twilio.com"`.
   Message body, verbatim:
   `"<code> is your Anticipy code to set a new password. It works for 10 minutes. If you didn't ask for this, ignore it and your password stays as it is."`
8. **Persist**: a `password_resets` row with `owner`, `code_hash = $security.sha256(code)`,
   `expires = now + 600s (ISO)`, `attempts = 0`, `used = false`.
   **Only the SHA-256 is stored** — a dump of the table is useless, and there is
   no route anywhere that can read a code back out. A failed save is logged and
   still answers `same()`.

**Side effects:** one outbound Twilio HTTP POST; one `password_resets` row.

### 5.2 `POST /auth/reset/confirm`

`:182-250`. `RESET_MAX_ATTEMPTS = 5`.

**Request:** `{"email":"...", "code":"123456", "password":"..."}`

**Responses:**
* `400 {"ok":false,"message":"That code isn't right, or it has expired. Ask for a new one."}`
  — for: unreadable body, blank email, blank code, unknown account, no unused
  reset row, expired row, attempts exceeded, wrong code.
* `400 {"ok":false,"message":"Pick a password with at least 8 characters."}`
  — when `password.length < 8`, checked **before** the account lookup, so it is
  the one refusal that is not enumeration-safe. It leaks nothing about accounts.
* `500 {"ok":false,"message":"Something went wrong on my end. Try again."}`
  — the password could not be set.
* `200 {"ok":true,"message":"Done — sign in with your new password."}`

Flow after the account resolves: take the newest row matching
`owner = {:o} && used = false`.
* **Expiry**: `isNaN(expMs) || now > expMs` → mark `used = true`, save, refuse.
  An unparseable `expires` is treated as expired (correct polarity, unlike
  `workflow_guard`).
* **Guess counting**: `attempts = (attempts || 0) + 1`, set on the record.
  `attempts > 5` → mark `used = true`, save, refuse. **The count is incremented
  before the comparison**, so a miss and a hit cost the same.
* **Comparison**: `$security.equal($security.sha256(code), rec.code_hash)`.
  Constant-time — this is the one comparison an attacker gets to repeat. A
  mismatch saves the incremented count and refuses.
* **Success**: `owner.setPassword(password)`, save owner, `rec.used = true`, save.
  **Single use.**

**Side effects:** the `password_resets` row's `attempts`/`used`; the owner's
password hash and `tokenKey` (which invalidates every existing session for that
account — PocketBase behaviour, not this file's).

### 5.3 `POST /me/delete` — which identifier may match which column

`account_delete.pb.js:57-222`. **Account token required.**

**Request:** `{"confirm": "delete"}`, `Authorization: <account token>`

**Refusals, in order:**
| condition | response |
|---|---|
| no `e.auth` | `401 {"ok":false,"message":"Sign in first."}` |
| `e.auth.collection().name !== "owners"` | `403 {"ok":false,"message":"Only an account can delete itself."}` |
| `body.confirm !== "delete"` | `400 {"ok":false,"message":"Send {\"confirm\":\"delete\"} to confirm. This cannot be undone."}` |
| `auth.id` blank after trim | `400 {"ok":false,"message":"No account on that token."}` |

The superuser check exists because `e.auth` is populated for `_superusers` too;
without it a superuser token drives this handler and writes a purge row naming
its own id (`:85-88`).

`confirm` is **proof of intent, not merely of possession** (`:95-100`): a bearer
token is stateless and valid until `tokenKey` rotates, so one replayed request
from a stolen phone or a logged `Authorization` header would otherwise be a total
wipe with no second step.

**THE TABLE — the entire security of this endpoint** (`:58-80`):

| collection | legacy column |
|---|---|
| `jobs` | `owner` |
| `segments` | `owner` |
| `agents` | `owner` |
| `owner_profile` | **`owner_id`** |
| `pendants` | `owner` |
| `agent_llm_audit` | *(none)* |
| `agent_audit_sessions` | *(none)* |
| `evidence` | *(none)* |
| `events` | *(none — last and largest, so a timeout lands on the cheapest table to retry)* |

**Which value may match which column** (`:117-124`) — this is the rule:

```
ref    = auth.id           may match: owner_ref  AND the legacy column
legacy = auth.legacy_uuid  may match: the legacy column ONLY, and only if len >= 8
```

**Why the obvious loop-both-over-both is a vulnerability** (`:13-30`):
`legacy_uuid` is a plain, client-writable field on `owners` (`createRule` is
open, `updateRule` is self) and the iOS client posts it verbatim at signup. A
value read from it is a **claim**, never proof of anything about accounts.
Applied to `owner_ref` it becomes: sign up declaring
`legacy_uuid = <victim account id>`, POST here, and the victim's jobs, segments,
agents, profile and transcripts are gone. **The victim's id is not even secret**
— `guard.pb.js`'s deliberately anonymous six-digit pair-code lookup hands it out
(`claim_legacy.pb.js:50-58` documents that as a real, exploited path).

**Naming the column per collection is the second half of the same bug**
(`:32-39`): a filter naming a column that does not exist throws for the *whole*
query, so querying `owner` on `owner_profile` threw, was swallowed, and left the
densest PII in the system behind while still reporting a count. And
`sms.pb.js` resolves inbound texts against `owner_profile.phone` **before**
`owners`, so that residue kept routing somebody's texts after they believed they
were gone.

**Error handling:** a query that throws now marks the table `failed` (`:133-140`)
— it is a real failure, not an expected missing column. A row that will not
delete does the same.

**Terminal responses:**
* Any `failed` table → **500**, and **nothing further happens** — no purge row,
  no account deletion, so the caller still has an account to retry with:
  ```json
  {"ok":false,"message":"I couldn't delete all of it, so I've stopped rather than tell you I had.  Try again.","deleted":{...},"failed":["..."]}
  ```
  *(exact message: `"I couldn't delete all of it, so I've stopped rather than tell you I had. Try again."`)*
* Purge row could not be written → **500**
  `{"ok":false,"message":"I deleted what I could reach but couldn't schedule the rest. Try again.","deleted":{...}}`
* Account delete threw → **409**
  `{"ok":false,"message":"I deleted your data but couldn't close the account itself. Ask me again — what's already gone stays gone.","deleted":{...},"account_deleted":false,"memory_purge":"waiting on the account closing"}`
* Success → **200**
  `{"ok":true,"deleted":{...},"account_deleted":true,"memory_purge":"scheduled"}`

**Ordering is load-bearing** (`:166-200`): the `purges` row (`owner_ref`,
`legacy_uuid`, `memory_purged: false`, `requested_at`) is written **before** the
account is deleted, because memory is a per-owner SQLite file on the brain's
volume that PocketBase cannot reach, and a crash between the two must not leave
memory on disk with no account left to name it. The supervisor defers any purge
whose ref discovery still returns, so a purge row naming a surviving account is
deferred rather than dangerous. `legacy_uuid` rides along because the
pre-migration founder's memory lives outside `<state root>/<owner_ref>`.

Deleting the account last invalidates the token that authorised the call — which
is correct, there is nothing left for it to authorise — and cascades
`password_resets`, a required relation.

**Side effects:** rows deleted across nine collections (including the stored
evidence *files*, since deleting the record is what removes them from the
volume); one `purges` row; the `owners` record; a `console.log` naming the
counts.

---

## §6. THE PRODUCT ROUTES (17)

Routes 1-3 (`/auth/reset/*`, `/me/delete`) are in §5. The remaining 14 follow.
None of them lives under `/api/collections/`, so **`guard.pb.js` gates none of
them** — each does its own authentication.

### 6.1 `POST /agent/register` — unauthenticated

`agent_auth.pb.js:5-72`.

**Request:** `{"agent_id": "<20-100 chars of [A-Za-z0-9._-]>", "browser": "<optional>"}`

| condition | response |
|---|---|
| `agent_id` fails `/^[A-Za-z0-9._-]{20,100}$/` | `400 {"error":"valid agent_id required"}` |
| an `agents` row already has that `agent_id` | `409 {"error":"agent already registered"}` |
| the `agent_id` lookup **threw** | `503 {"error":"could not check the agent id right now"}` |
| could not allocate a pair code, or the save threw | `500 {"error":"agent registration failed"}` |
| success | `200 {"id","agent_id","agent_token","pair_code"}` |

**An exception is not an answer** (`:13-31`). Both lookups use
`findRecordsByFilter(...) || []` and read *length*, so an empty array is
"nothing matched" and a throw stays a failure. Previously a transient DB error
made a candidate pair code look free — and `pair_code` carries **no unique
index** (only `agent_id` does,
`pb_migrations/1700000002_agents.js`) — so a duplicate saved, two browsers wore
one code, and the phone claimed whichever row came back first.

Minting: `agent_token = randomStringWithAlphabet(64, [A-Za-z0-9])`;
`pair_code` = up to 20 attempts at `randomStringWithAlphabet(6, "0123456789")`,
each checked for collision. Row is saved `paired: false`, `browser` sliced to
500 chars, `last_seen = now`.

**The token is returned exactly once and never appears in any collection
response** (`agent_token` is a hidden field).

**Side effects:** one `agents` row.

### 6.2 `POST /agent/upgrade-credential` — service token

`agent_auth.pb.js:78-98`. One-release bridge for installs paired before
per-agent credentials existed.

| condition | response |
|---|---|
| `ANTICIPY_SERVICE_TOKEN` unset, or `X-Anticipy-Token` ≠ it | `403 {"error":"upgrade not authorized"}` |
| no row at `body.record_id`, or its `agent_id` ≠ `body.agent_id` | `404 {"error":"agent not found"}` |
| success | `200 {"agent_token": "<existing or freshly minted>"}` |

**Side effects:** the `agents` row is saved (with its existing token if it had
one, else a new 64-char token).

### 6.3 `GET /agent/key` — per-agent credential

`agent_key.pb.js:7-60`. Query `?agent_id=…`, header `X-Anticipy-Agent-Token`.

| condition | response |
|---|---|
| `agent_id` blank or token shorter than 40 | `400 {"error":"agent credentials required"}` |
| lookup `agent_id && agent_token && paired = true` throws or misses | `403 {"error":"not a paired agent"}` |
| the resolved row has a blank `owner_ref` | `409 {"error":"paired agent has no canonical owner; pair it again from the signed-in app"}` |
| neither `GEMINI_API_KEY` nor `OPENROUTER_API_KEY` is set | `503 {"error":"backend has no model configured"}` |
| success | `200 {...}` (below) |

```json
{"llm_proxy": true,
 "owner_ref": "<id>",
 "owner": {"first_name","last_name","email","phone","birthday","facts"} | null,
 "model": "<ANTICIPY_BROWSER_MODEL || anthropic/claude-sonnet-4.6>",
 "vision_model": "<ANTICIPY_VISION_MODEL || google/gemini-2.5-flash>"}
```

**The vendor key never leaves this backend.** `owner` is the newest
`owner_profile` for that `owner_ref`, or `null` if there is none or the lookup
threw. **PII on the wire:** name, email, phone, birthday and free-text facts go
to a paired browser extension. That is deliberate (a booking form asks the same
four things every time) and it is a fact a port must not accidentally widen.

**Side effects:** none.

### 6.4 `POST /agent/llm` — per-agent credential, the model proxy

`agent_key.pb.js:65-415`. The longest route in the product half of the tree.

| # | condition | response |
|---|---|---|
| 1 | `agent_id` blank or token < 40 | `400 {"error":"agent credentials required"}` |
| 2 | paired-agent lookup throws or misses | `403 {"error":"not a paired agent"}` |
| 3 | resolved row's `owner_ref` blank after trim | `403 {"error":"this agent is not attached to an account"}` |
| 4 | hourly meter ≥ 400 | `429 {"error":"too many model calls in the last hour","detail":"this browser hit its hourly limit; it resumes at the top of the hour"}` |
| 5 | no `GEMINI_API_KEY` and no `OPENROUTER_API_KEY` | `503 {"error":"backend has no model configured"}` |
| 6 | body not valid JSON | `400 {"error":"valid JSON required"}` |
| 7 | `body.model` ∉ {browser model, vision model} | `403 {"error":"model is not enabled for browser agents"}` |
| 8 | non-Google model and no `OPENROUTER_API_KEY` | `503 {"error":"requested model provider is not configured"}` |
| 9 | `messages` not an array of 1-40 | `400 {"error":"messages must contain 1 to 40 items"}` |
| 10 | any role ∉ {system, user, assistant} | `400 {"error":"unsupported message role"}` |
| 11 | serialized payload > 900,000 chars | `413 {"error":"model request too large"}` |
| 12 | (Gemini path) no usable content after conversion | `400 {"error":"messages contain no usable content"}` |
| 13 | provider returned no JSON | `502 {"error":"model returned no JSON"}` |
| 14 | (Gemini) provider non-2xx | `<provider status> {"error":"model provider rejected request"}` |
| 15 | (Gemini) no text in the candidate | `502 {"error":"model returned no text"}` |
| 16 | any throw in the send block | `502 {"error":"model proxy unavailable"}` |

Rule 3 exists because without it the endpoint was **an open LLM proxy billed to
us**: register (no credential needed), self-pair, loop forever (`:167-174`).

**The meter** (`:181-200`): `HOURLY_CALL_CEILING = 400`, counted on the `agents`
row as `llm_hour` (`YYYY-MM-DDTHH`) + `llm_calls`. A stored hour ≠ this hour
resets the count to 0. **The meter's own failure never blocks real work** — a
throw is logged and the request proceeds (`:197-200`). That is a deliberate
fail-open on the *budget*, not on authorisation.

**Model routing** (`:220-225`): a model whose id starts `google/` uses the
direct Google endpoint with the `google/` prefix stripped. Every other model
goes to OpenRouter. **Do not choose a provider merely because its key exists** —
that previously made a DeepSeek request run on Gemini while the client and the
audit row still said DeepSeek.

`max_tokens` is clamped to `[512, 4096]`, default 512 (`:231-241`); `temperature`
is forced to 0 for non-Gemini-3. Gemini 3 gets `thinkingLevel: "low"` and keeps
its default temperature; Gemini 2.x gets `thinkingBudget: 0`. **The floor was
64 until 2026-09-05**: the browser model is a thinking model whose reasoning
counts against `max_tokens`, and at 64 its one-token verdicts came back cut off
mid-word on 15 of 22 measured pages
(research/evals/login-wall-2026-09-05/FINDINGS.md). The extension floors at the
same number (`MODEL_REPLY_FLOOR`, extension/agent_loop.js); the proxy is the
second lock on the same door. Both provider calls are bounded at 95 s
(`timeout: 95`, `:337`/`:389`; the Worker: `AbortSignal.timeout`), and a
timeout is rule 16.

**Success shapes differ by provider.** Google:
```json
{"choices":[{"message":{"content":"<joined parts>"}}], "model":"<bare model>", "provider":"google"}
```
The Worker port (`migration/workers/src/llm.ts`) answers a **superset** on this
path: `choices[0].finish_reason` (`STOP`→`stop`, `MAX_TOKENS`→`length`) and
`usage` `{prompt_tokens, completion_tokens, total_tokens}` when Google reports
them. Additive only — the extension reads `choices[0].message.content` and
nothing else.
OpenRouter: the provider's own JSON, returned verbatim with the provider's own
status code (`:408`) — **including non-2xx**, which is why rule 14 has no
OpenRouter twin.

**The Worker's meter** increments in ONE atomic `UPDATE` (a stored hour that is
not this hour restarts at 1), where the hook read-modify-wrote and could lose a
step when one browser's calls overlapped; the 429 decision reads the row the
credential lookup fetched, as the hook does. **The Worker's proof** is
`migration/workers/scripts/llm_contract_local.sh`: `TestAgentLlmProxy` against a
real workerd and a fake provider reached through `LLM_PROVIDER_BASE` (honoured
for a loopback host only) — the floor on the wire, the `json_object`
passthrough, the byte-identical 429 text, the audit rows in D1, and that no key
reaches any response. The real providers and the edge's idle timeout are NOT
covered by it; `src/llm.ts`'s header lists both as unverified.

**The audit ledger.** A row in `agent_llm_audit` is written only when a
`task_tag` is found (`:118-120`): either `[AUDIT:<tag>]` inside the serialized
messages (`:113-117`), or an active, unexpired `agent_audit_sessions` row for
this `agent_id`. **Image bytes are redacted before storage** (`:69-112`):
`data:...;base64,` payloads become `"<meta>,[IMAGE_BYTES_REDACTED]"` plus
`sha256`, `encoded_chars` and `approximate_bytes`. The same is done to Gemini's
`inlineData`. Audit failures are logged and never break execution.

**Side effects:** `agents.llm_hour` / `llm_calls`; up to one `agent_llm_audit`
row per call, written twice (begin + finish) — which triggers the retention
sweep in §7.2; one outbound HTTPS call to Google or OpenRouter.

### 6.5 `POST /agent/solve-captcha` — per-agent credential

`captcha_solve.pb.js:22-131`. Constants inside the handler:
`HOURLY_SOLVE_CEILING = 25`, `POLL_TIMEOUT_MS = 120000`, `POLL_EVERY_MS = 3000`
(the last two are declared but unused — the route hands back a ticket instead of
polling).

| condition | response |
|---|---|
| `CAPSOLVER_API_KEY` unset | `501 {"error":"solving is not configured"}` |
| `agent_id` blank, or token blank, or token shorter than **20** | `400 {"error":"agent credentials required"}` |
| paired lookup throws or misses | `403 {"error":"not a paired agent"}` |
| `owner_ref` blank after trim | `403 {"error":"this agent is not attached to an account"}` |
| body unreadable | `400 {"error":"unreadable request"}` |
| `websiteURL` or `websiteKey` blank | `400 {"error":"websiteURL and websiteKey are required"}` |
| host matches `NEVER_SOLVE` | `403 {"error":"this site is never solved automatically","detail":"a challenge on money or identity belongs to the person"}` |
| `type` ∉ {recaptcha_v2, recaptcha_v3, hcaptcha, turnstile} | `400 {"error":"unsupported challenge type","detail":"<type>"}` |
| hourly ≥ 25 | `429 {"error":"too many solves this hour"}` |
| CapSolver returned `errorId` or no `taskId` | `502 {"error":"the solver refused the task","detail":"<code>"}` |
| success | `202 {"taskId":"…","type":"<kind>"}` |

**DIVERGENCE:** the token minimum here is 20, not the 40 used by
`guard.pb.js:226`, `/agent/key` and `/agent/llm`. A port that unifies them on 40
will refuse a class of request this route currently accepts (though no such
token can exist, since the column's minimum is 40).

`NEVER_SOLVE` (`:31`) — money and consent on one list:
```
(^|\.)(chase|wellsfargo|bankofamerica|citi|rbc|td|scotiabank|bmo|cibc|tangerine|
 wealthsimple|questrade|robinhood|coinbase|binance|kraken|paypal|venmo|wise|
 revolut|stripe|irs|cra-arc|gc)\.(com|ca|net|org|gov)$
| accounts\.google\.com | login\.microsoftonline\.com | appleid\.apple\.com | id\.gov
```
matched case-insensitively against `websiteURL.split("/")[2]`.

The hourly counter is stamped **after** CapSolver accepts the task (`:123-125`),
so a refused task does not spend the budget. Counted on the agent row as
`solve_hour` + `solve_calls`.

**Side effects:** `agents.solve_hour`/`solve_calls`; one outbound POST to
`https://api.capsolver.com/createTask`.

### 6.6 `POST /agent/solve-captcha/result` — per-agent credential

`captcha_solve.pb.js:134-183`. Same credential rules (token ≥ 20), no
`owner_ref` requirement, no meter.

| condition | response |
|---|---|
| `CAPSOLVER_API_KEY` unset | `501 {"error":"solving is not configured"}` |
| credentials missing/short | `400 {"error":"agent credentials required"}` |
| lookup misses or throws | `403 {"error":"not a paired agent"}` |
| body unreadable | `400 {"error":"unreadable request"}` |
| `taskId` blank | `400 {"error":"taskId is required"}` |
| the solver could not be reached | `502 {"error":"could not reach the solver"}` |
| solver returned `errorId` | `502 {"error":"the solver could not do it","detail":"<code>"}` |
| `status !== "ready"` | `200 {"status":"processing"}` |
| ready but no token in the solution | `502 {"error":"solver returned no token"}` |
| ready | `200 {"status":"ready","token":"<token>"}` |

Token is read as `solution.gRecaptchaResponse || solution.token || solution.captchaToken`.

**Side effects:** one outbound POST to CapSolver's `getTaskResult`.

### 6.7 `POST /evidence/share` — service token only

`evidence.pb.js:157-224`. `SHARE_WINDOW_MS = 15 * 60 * 1000`, `SHARE_FETCH_LIMIT = 5`.

| condition | response |
|---|---|
| `ANTICIPY_SERVICE_TOKEN` unset **or** `X-Anticipy-Token` ≠ it | `403 {"error":"forbidden"}` |

The truthiness test is the whole guard (`:162-164`): `getenv` returns `""` when
unset and `"" === ""` is true for a missing header, which is how a token check
silently becomes an open door.

**Every other outcome is `200`.** An absent picture is an answer, not an error
(`:169-173`) — a `MediaUrl` that 404s makes Twilio fail the *whole* message, so a
caller who cannot be given a URL must be told so in a form it will act on:

```json
{"ok": false, "reason": "<why>", "url": "", "expires": ""}
```

`reason` is one of: `no evidence was named` · `that evidence is gone` ·
`that evidence has no picture` · `no https base url is configured for this backend` ·
`could not open a share window: <error>`.

Base URL resolution (`:189-203`): `ANTICIPY_PUBLIC_URL` if set, else the
`https://host` origin of `ANTICIPY_TWILIO_WEBHOOK_URL`, trailing slashes
stripped. Anything not starting `https://` is refused — a wrong origin is a
MediaUrl Twilio cannot fetch, and that fails the message rather than dropping
the picture.

Success:
```json
{"ok": true,
 "url": "<base>/api/files/evidence/<record id>/<stored filename>",
 "expires": "<ISO, now + 15 min>",
 "fetches": 5}
```

**Side effects:** `evidence.share_expires` set, and **`evidence.fetches` reset to
0** (`:210-212`) — a fresh window gets a fresh ceiling, or re-sharing a picture
already fetched five times opens a window nothing can come through.

### 6.8 `POST /auth/claim` — account token

`claim_legacy.pb.js:39-101`.

**Request:** `{"legacy_uuid": "…"}`

| condition | response |
|---|---|
| no `e.auth` | `401 {"ok":false,"message":"Sign in first."}` |
| `legacy` non-empty and ≠ `auth.legacy_uuid` (both trimmed) | `403 {"ok":false,"message":"That device isn't on this account."}` |
| otherwise | `200 {"ok":true,"claimed":{"jobs":n,"owner_profile":n,"segments":n,"agents":n,"events":n}}` |

**The uuid must be the one recorded on this account at sign-up** (`:63-67`).
Without that check the attack was: read a stranger's uuid off a pair code, sign
up a throwaway account, POST it here, and every legacy row moved — including the
`owner_profile` carrying that person's name, email, phone and birthday. And
because `sms.pb.js` resolves an inbound number through `owner_profile` before
`owners`, every "yes, go ahead" the real owner texted was thereafter filed under
the stranger and released into the stranger's browser.
`owners.legacy_uuid` is UNIQUE (`idx_owners_legacy`, migration 1700000008) and
the app posts back the value it registered, so equality against the recorded one
is the entire test — **and an account with nothing recorded can claim nothing**
(a blank `legacy` skips the length-8 gate below and claims zero rows).

**Adoption rule 1** — only when `legacy.length >= 8`, for each of
`jobs`, `owner_profile`, `segments`, `agents`:
```
filter: <field> = {:u} && owner_ref = ''      where field = "owner_id" for owner_profile, else "owner"
sort:   -created,  limit 500
action: set owner_ref = auth.id, save
```
A per-table throw is swallowed and the count stays 0. `agents` was missing from
this list until 2026-08-05, and the fix did not work for two days because
`agents` had no `owner_ref` column until migration 1700000022 — the query threw
and the throw was swallowed.

**Adoption rule 2 — transcripts.** `events` has never had an owner column, so
there is no evidence on the row at all. They are claimed **only when this is the
single account on the whole instance**: `findRecordsByFilter("owners","id != ''","-created",2,0)`
must return exactly one row and it must be this account. Then up to 2000
`events` with `owner_ref = ''` are adopted. With two or more accounts the honest
answer is to leave them unowned and invisible rather than hand one person
another person's transcripts.

**Side effects:** up to 2000 + 4×500 record updates; one `console.log`.

### 6.9 `POST /me/phone/remove` — account token

`phone_remove.pb.js:13-120`.

| condition | response |
|---|---|
| no `e.auth` | `401 {"ok":false,"message":"Sign in first."}` |
| `auth.collection().name !== "owners"` | `403 {"ok":false,"message":"Only an account can remove its own phone number."}` |
| `auth.id` blank | `400 {"ok":false,"message":"No account on that token."}` |
| the transaction rolled back | `500 {"ok":false,"message":"I couldn't verify that every copy was removed, so the change was not completed."}` |
| post-commit verification failed | `500 {"ok":false,"message":"The server could not verify the removal. Refresh your account before relying on it."}` |
| success | `200 {"ok":true,"phone":"","clearedProfiles":n}` |

Inside one `runInTransaction` (`:35-78`):
* `owners.phone = ""`, saved.
* Every `owner_profile` matching the ownership filter, paged 200 at a time, gets
  `phone = ""`. The filter is:
  ```
  with a legacy uuid:  (owner_ref = {:ref} || (owner_ref = '' && (owner_id = {:ref} || owner_id = {:legacy})))
  without:             (owner_ref = {:ref} || (owner_ref = '' && owner_id = {:ref}))
  ```
  The ownerless residue is included because `claim_legacy` historically swallowed
  individual save failures, and such a row is still safely attributable by
  `owner_id`. Revocation must cover it or an old number stays routable after a
  200.
* **In-transaction proof before commit** (`:66-77`): re-read the owner and assert
  its phone is blank; re-query for any matching profile with `phone != ''` and
  assert none. Either throws and everything rolls back together.

**Then the same proof again through the normal app after commit** (`:87-111`),
to catch a future transaction/runtime regression before the client is told it can
start fresh. Unknown is failure; it is never interpreted as an empty phone.

**Side effects:** the `owners` row; every matching `owner_profile` row; a
`console.log` of the count.

### 6.10 `POST /me/profile/upsert` — account token

`owner_profile_upsert.pb.js:23-198`. One authenticated partial write in, one
complete canonical profile out.

| condition | response |
|---|---|
| no `e.auth` | `401 {"ok":false,"message":"Sign in first."}` |
| not an `owners` record | `403 {"ok":false,"message":"Only an account can update its own profile."}` |
| `auth.id` blank | `400 {"ok":false,"message":"No account on that token."}` |
| body unreadable | `400 {"ok":false,"message":"The profile update was unreadable."}` |
| body is not a non-array object | `400 {"ok":false,"message":"The profile update must be an object."}` |
| any key ∉ the editable set | `400 {"ok":false,"message":"That field is not part of the owner profile."}` |
| any value is not a string | `400 {"ok":false,"message":"Profile fields must be text."}` |
| transaction rolled back | `500 {"ok":false,"message":"I couldn't verify the complete profile, so nothing was reported as saved."}` |
| post-commit verification failed | `500 {"ok":false,"message":"The server could not verify the saved profile. Refresh before relying on it."}` |
| success | `200 {"ok":true,"profile":{...},"removedDuplicates":n}` |

Editable set (`:53-66`): `phone`, `name`, `first_name`, `last_name`, `email`,
`birthday`, `facts`, `timezone`.

**Presence, not truthiness, is the contract** (`:130-133`): `""` clears a field;
omission keeps the current row's value (or the account seed on the first row).

Inside one transaction:
* Read the owner (a failed read aborts; it is never converted into empty seeds).
* `findRecordsByFilter("owner_profile", "owner_ref = {:ref}", "-updated,-created,-id", 0, 0)`.
  `findRecordsByFilter` returns `[]` for a known absence and throws for an
  unknown read — that distinction is why this must not use a try/catch around
  `findFirstRecordByFilter` (`:92-95`).
* If rows exist: `profiles[0]` is canonical **for every field, including an empty
  phone written by the removal flow**; every older duplicate is deleted and
  counted. Older non-empty duplicates never value-merge back in.
* If none: create one and seed every editable field from the same-named field on
  `owners`.
* `owner_ref = auth.id` always. `owner_id` = existing value, else
  `owners.legacy_uuid`, else `auth.id` — never blank.
* Apply the body's present fields.
* Save, then **prove**: exactly one row for this owner, its id equals the saved
  one, and every explicitly-supplied field reads back byte-identical. Else throw
  and roll back.

Post-commit it re-proves uniqueness and this request's explicit fields only — a
concurrent partial writer may legitimately have changed a field this request
omitted — then returns the latest complete row:
```json
{"id","owner_ref","owner_id","phone","name","first_name","last_name","email","birthday","facts","timezone"}
```

The storage-level backstop for two simultaneous first writers is the unique
partial index from `pb_migrations/1700000054_owner_profile_canonical.js`.

**Side effects:** one `owner_profile` row created or updated; zero or more
duplicates deleted.

### 6.11 `GET /worker/owners` — service token only

`worker_owners.pb.js:9-33`.

| condition | response |
|---|---|
| `ANTICIPY_SERVICE_TOKEN` unset **or** `X-Anticipy-Token` ≠ it | `403 {"error":"forbidden"}` |
| success | `200 {"page","perPage","totalItems","totalPages","items":[{"id","legacy_uuid"}]}` |

Query: `page` (min 1), `perPage` (clamped to 1-200, default 200).
Ordering `+id`. Filter `id != ''`.

**Only two identifiers.** Never email, phone, password metadata, tokens or
profile fields. Private account discovery for the brain supervisor, which needs
this because a backend-wide shared-token request is not an auth-model login and
therefore cannot use the ordinary owners list route.

**Side effects:** none.

### 6.12 `POST /sms/inbound` — Twilio HMAC, unauthenticated otherwise

`sms.pb.js:24-296`. The most refusal-dense route in the tree, and every refusal
says which check refused, because the only symptom of the last inbound outage
lived on Twilio's side of the wire as error 11200.

| # | condition | response |
|---|---|---|
| 1 | `TWILIO_AUTH_TOKEN` unset | `503` text `sms webhook is not configured` |
| 2 | `Content-Type` does not start `application/x-www-form-urlencoded` | `415` text `unsupported content type` |
| 3 | no candidate URL validates the signature (or no signature at all) | `403` text `forbidden` |
| 4 | `TWILIO_ACCOUNT_SID` set and `AccountSid` ≠ it | `403` text `forbidden` |
| 5 | `TWILIO_PHONE_NUMBER`/`TWILIO_FROM` set and `To` ≠ it | `403` text `forbidden` |
| 6 | `MessageSid` fails `/^SM[a-fA-F0-9]{32}$/` | `403` text `forbidden` |
| 7 | phone ownership could not be fully verified | `500` text `temporary routing failure` |
| 8 | otherwise | `200`, `Content-Type: application/xml`, body `<?xml version='1.0' encoding='UTF-8'?><Response></Response>` |

**`TWILIO_AUTH_TOKEN` is load-bearing and cannot be migrated to an API key**
(`:16-23`). Twilio signs an inbound webhook with the account auth token and with
nothing else; there is no API-key equivalent for `X-Twilio-Signature`. Anyone
who "finishes" the outbound key migration by deleting it turns every text into a
503 and the product looks simply deaf.

**Signature validation** (`:41-138`). Twilio signs the *exact URL it requested*,
so the URL is derived from the request rather than from an env var. Candidates,
in order:
1. `<scheme>://<X-Forwarded-Host or request host><path><?rawQuery>` for both
   schemes — `https` first unless `X-Forwarded-Proto` is exactly `http`.
2. `ANTICIPY_TWILIO_WEBHOOK_URL`, still honoured as the escape hatch.

Extra candidates cannot weaken anything: each still has to produce a matching
HMAC under `TWILIO_AUTH_TOKEN`, which an attacker who can set a `Host` header
still does not have.

**Twilio signs the POST body parameters only.** PocketBase's
`requestInfo().body` merges the URL query into the form (Go's `ParseForm` does
that), so **every query-string key is deleted from the params before signing**
(`:113-121`). Verified against a live PocketBase 0.30.4 on 2026-08-19: a request
to `.../sms/inbound?token=abc123` only passed when `token` was signed as if it
were a form field, which Twilio will never do.

The algorithm itself is `twilio_signature.js`: `base64(HMAC-SHA1(authToken,
url + concat(sorted key + value)))`, array values sorted within a key, compared
in constant time. Pure ES5, dependency-free, cross-checked in tests against
Twilio's published vector and Python's `hmac`.

**Owner resolution — a phone number is a routing address, not an identity**
(`:160-239`). Two candidate sets, always unioned:
* Every `owner_profile` whose `phone` equals `From` (paged 200), then each
  candidate `owner_ref` resolved back through *its own newest profile*; the
  candidate survives only if that canonical row still carries this number. A
  phone match on an old duplicate profile is not current authority.
* Every `owners` row whose `phone` equals `From` (paged 200), admitted **only if
  that account has no `owner_profile` row at all**. `owners.phone` is the sign-up
  seed; once a profile exists it is canonical even when its phone is empty.

Any read failure anywhere sets `routingUnknown = true`. **A partial candidate set
is never safe enough to pick an account, even when the surviving set contains
exactly one row** → 500, so Twilio retries.

**Everything above the acceptance line refuses; everything below decides whether
the request becomes an event** (`:252-293`), and each non-event outcome logs
loudly, because an unrecognised sender used to produce empty TwiML and no log at
all — which reads from Twilio's console as a perfectly healthy webhook:

| outcome | log |
|---|---|
| blank `From` or `Body` | `sms/inbound 200 but dropped: empty From or Body; MessageSid=…` |
| duplicate `MessageSid` already in `events.external_event_id` | `sms/inbound 200, already handled: MessageSid=…` |
| 0 matches | `sms/inbound 200 but DROPPED: no account owns the sender route — …` |
| >1 match | `sms/inbound 200 but DROPPED: N accounts claim the sender route — ambiguous, refusing to pick whose browser to drive.` |
| exactly 1 | an `events` row is written |

The event row: `device_id="sms"`, `kind="sms_reply"`, `text=<trimmed Body>`,
`decision=""`, `goal=<sender phone>`, `owner_ref=<the single match>`,
`external_event_id=<MessageSid>`. A save that throws is logged **and rethrown**,
so Twilio retries.

**DIVERGENCE / latent bug:** the duplicate check at `:244-250` calls
`findFirstRecordByFilter` and sets `duplicate = true` **before** the call can
throw — but `findFirstRecordByFilter` *throws* when nothing matches, so
`duplicate` is set only when a row was found, and the empty case lands in the
`catch`. The logic is correct by accident of ordering; a port that changes to a
`findRecordsByFilter(...).length` idiom must invert the condition, not copy the
shape.

**Side effects:** at most one `events` row; several `console.log` lines.

### 6.13 `POST /transcription/token` — account token, permanently refusing

`transcription_token.pb.js:42-59`.

| condition | response |
|---|---|
| no `e.auth` | `401 {"error":"sign in first"}` |
| otherwise | `410 {"error":"transcription tokens are not issued","reason":"raw audio never leaves a device (design/LOCAL-FIRST.md rule 1)","replacement":"on-device transcription; see LocalTranscriber.swift"}` |

**410 GONE, deliberately, not 502 or 503** (`:51-54`): those mean "try again
later" and the phone's catch block schedules a retry on them, so a
temporary-sounding refusal would spin a reconnect loop forever against a
decision that is permanent. The route is kept refusing rather than deleted
because a deleted route answers 404 and a 404 reads as "you have the wrong URL".

The vendor is deliberately **not** named in the response string —
`overnight/no_vendor_ears.py` greps live code for the hostname, and a gate that
its own refusal notice sets off is a gate somebody will soften.

**Side effects:** one `console.log`.

### 6.14 `POST /admin/purge-audit` — service token only

`audit_retention.pb.js:23-67`. `AUDIT_KEEP = 300`, `PURGE_BATCH = 200`.

| condition | response |
|---|---|
| `ANTICIPY_SERVICE_TOKEN` unset **or** `X-Anticipy-Token` ≠ it | `403 {"error":"forbidden"}` |
| the drain threw | `200 {"ok":false,"deleted":n,"error":"<err>","trace":[…]}` |
| otherwise | `200 {"ok":true,"deleted":n,"more":<bool>,"keep":n}` |

`body.keep`, if present, overrides 300 (`Math.max(0, parseInt(...) || 0)`).
Surplus is found by sorting `-created` and offsetting by `keep`, so exactly the
oldest rows past the keep window are taken, `PURGE_BATCH` at a time. A delete
that fails does not abort the drain — on a wedged disk the next record may well
succeed and every freed page helps. `more` is true when at least one surplus row
remains.

This exists because the ledger grew to 3,639 records of up to 1 MB each and
filled the 5 GB production volume to 4996 MB, at which point SQLite could not
write **any** row. The visible symptom was cruel: a password-reset text went out
(the send happens before the save) but the code could never be stored, so the
correct code was rejected every time.

**Side effects:** up to 200 `agent_llm_audit` rows deleted.

---

## §7. HQ — `internal_hq.pb.js` (38 routes, 2 crons)

The team dashboard. `ANTICIPY_INTERNAL_KEY` is the shared team key;
`X-HQ-Session` is a per-person token. **The whole file is fail-CLOSED on
configuration**: with `ANTICIPY_INTERNAL_KEY` unset, every route except
`GET /internal/health`, the OPTIONS preflight and `GET /fellows/hq` answers
`503 {"error":"internal HQ is not configured"}` (`:12-15`). That is the
deliberate inversion of `guard.pb.js`'s fail-open — *a fresh deploy that forgot
one variable must not publish the team's phone numbers.*

### 7.0 The four authentication patterns

Every HQ route uses exactly one of these. Implement them once in the port and
then check each route against the table in §7.1, because **they are not
interchangeable and three of them differ in whether they check `active`.**

**Pattern A — dual auth, GET-shaped** (`/internal/state` `:59-99`,
`/internal/me` `:3476-3501`):
```
if X-HQ-Session present:
    resolve session -> person; if that fails for ANY reason -> 401 {"reauth": true}
    NEVER fall through to the key branch
else:
    $security.equal(X-Internal-Key, ANTICIPY_INTERNAL_KEY) or -> 401 {"error":"wrong key"}
    actor := findRecordById("internal_people", query.actor_id)   // optional on /state
```

**Pattern B — dual auth, body-shaped** (12 routes):
```
if X-HQ-Session present:
    resolve or -> 401 {"reauth": true}
else:
    key check or -> 401 {"error":"wrong key"}
    actor := findRecordById("internal_people", body.actor_id)
             miss -> 400 {"error":"pick yourself first"}
    !actor.active -> 400 {"error":"that person is deactivated"}
```

**Pattern C — the session door** (16 routes, `:334-369` and 15 verbatim copies).
Added 2026-08-23 because these handlers predated personal sessions and answered
"wrong key" to a signed-in teammate:
```
__k := ANTICIPY_INTERNAL_KEY;  if !__k -> 503
if X-HQ-Session present:
    resolve or -> 401 {"reauth": true}
    body.actor_id := session person's id      // OVERWRITES whatever the client claimed
    e.request.header.set("X-Internal-Key", __k)   // so the check below passes untouched
<then the handler's ordinary key path runs unchanged>
```
`e.requestInfo()` is cached per request, so the `actor_id` write is the one the
rest of the handler sees. **A session must never impersonate**, which is why the
client's `actor_id` is overwritten rather than compared.

**Session resolution**, identical in all 28 copies:
```js
sess = findFirstRecordByFilter("internal_sessions", "token_hash = {:h}",
                               { h: $security.sha256(token) });
exp  = String(sess.expires).trim().replace(" ", "T");
if (!/([Zz]|[+-]\d{2}:?\d{2})$/.test(exp)) exp += "Z";     // the ZZ/NaN trap
t = Date.parse(exp);
ok = !isNaN(t) && Date.now() < t
     && findRecordById("internal_people", sess.person).active
```
The regex guard exists because PocketBase 0.30.4 already ends its datetimes with
`Z`; blindly appending a second one produced `…880ZZ` → Invalid Date → `NaN`,
and `isNaN(NaN)` is true, so a branch could never fire. That bug pinned the
research slot forever (`:2501-2508`). **Any failure — no row, unparseable date,
expired, deactivated person — is the same 401 `{"reauth": true}`.**

**`active` is re-checked on every request**, so a deactivated person's live
session is refused immediately; the row deletion in `PATCH /internal/people`
(`:588-594`) is belt-and-braces so a *reactivation* does not silently restore a
thirty-day-old token.

### 7.1 Route table

| # | Route | Pattern | Extra authority | Notes |
|---|---|---|---|---|
| 1 | `GET /internal/health` | none | — | §7.2 |
| 2 | `POST /internal/login` | key **in body** | — | §7.3 |
| 3 | `GET /internal/state` | A | admins get `signins` | §7.4 |
| 4 | `POST /internal/people` | C | admin to mint a code or set `is_admin` | §7.5 |
| 5 | `PATCH /internal/people` | C | self-or-admin; admin for role/active | §7.6 |
| 6 | `POST /internal/todos` | C | — | §7.7 |
| 7 | `PATCH /internal/todos` | C | — | §7.8 |
| 8 | `POST /internal/todos/delete` | C | creator or admin | §7.9 |
| 9 | `POST /internal/events` | C | — | §7.10 |
| 10 | `POST /internal/events/delete` | C | creator or admin | §7.10 |
| 11 | `POST /internal/tracks` | C | **admin only** | §7.11 |
| 12 | `POST /internal/router` | — | — | **410, dead** §7.12 |
| 13 | `POST /internal/assistant` | C | admin for `create_project` | §7.13 |
| 14 | `POST /internal/research` | — | — | **410, dead** §7.12 |
| 15 | `GET /internal/research/status` | — | — | **410, dead** §7.12 |
| 16 | `POST /internal/session` | none — the code IS the credential | — | §7.14 |
| 17 | `POST /internal/expenses` | C | — | §7.15 |
| 18 | `POST /internal/expenses/delete` | C | creator or admin | §7.15 |
| 19 | `POST /internal/passwords` | C + vault key | — | §7.16 |
| 20 | `POST /internal/passwords/reveal` | C + vault key | — | §7.16 |
| 21 | `POST /internal/passwords/delete` | C | **anyone active** | §7.16 |
| 22 | `POST /internal/notes` | C | — | §7.17 |
| 23 | `POST /internal/notes/delete` | C | creator or admin | §7.17 |
| 24 | `GET /internal/cal/{token}` | the token itself | — | §7.18 |
| 25 | `POST /internal/clerk/exchange` | Clerk HS256 JWT | must match an active person's email | §7.19 |
| 26 | `POST /internal/session/end` | session (optional) | — | §7.20 |
| 27 | `GET /internal/me` | A (actor **required**) | — | §7.21 |
| 28 | `POST /internal/people/code` | B | **admin only** | §7.22 |
| 29 | `POST /internal/comments` | B | — | §7.23 |
| 30 | `PATCH /internal/comments` | B | **author only, never admin** | §7.23 |
| 31 | `POST /internal/comments/delete` | B | author or admin | §7.23 |
| 32 | `POST /internal/reminders` | B | — | §7.24 |
| 33 | `POST /internal/reminders/delete` | B | creator or admin | §7.24 |
| 34 | `POST /internal/notifs/read` | B | own rows only | §7.25 |
| 35 | `POST /internal/tracks/delete` | B | **admin only** | §7.26 |
| 36 | `POST /internal/settings` | B | **admin only** | §7.27 |
| 37 | `OPTIONS /internal/{path...}` | none | — | `204`, empty body, always |
| 38 | `GET /fellows/hq` | none | — | §7.28 |

**DIVERGENCE — the `active` check is not uniform.** Pattern B always checks it.
Pattern C does not: `POST /internal/todos` (`:657`), `PATCH /internal/todos`
(`:842`), `POST /internal/todos/delete` (`:1086`), `POST /internal/events`
(`:1155`), `POST /internal/events/delete` (`:1225`), `POST /internal/tracks`
(`:1285`) and `POST /internal/assistant` (`:1475`) resolve the actor and **never
ask whether they are active**, while `POST /internal/expenses` (`:2928`), the
password routes and the note routes do. So with the shared team key, a
deactivated person's id can still create a task but not an expense. Pin the
current behaviour; do not "fix" it silently.

### 7.2 `GET /internal/health` — no auth, leaks nothing

`:20-37`. Always `200`:
```json
{"ok": true, "gated": <bool>, "version": "hq-2",
 "channels": {"email": <bool>, "sms": <bool>}}
```
`gated` = `ANTICIPY_INTERNAL_KEY` is non-empty.
`channels.email` = `RESEND_API_KEY` present.
`channels.sms` = `TWILIO_ACCOUNT_SID` **and** `TWILIO_AUTH_TOKEN` **and**
(`TWILIO_PHONE_NUMBER` or `TWILIO_FROM`).

**Derived from env presence, never from a literal** (`:22-30`). The Settings
screen used to draw "Connected" from hardcoded strings — a surface reporting the
claim instead of asking it. A boolean cannot leak a key.

### 7.3 `POST /internal/login`

`:42-50`. Request `{"key": "…"}`.
* `ANTICIPY_INTERNAL_KEY` unset → `503 {"error":"internal HQ is not configured"}`
* `!$security.equal(body.key, key)` → `401 {"error":"wrong key"}`
* else `200 {"ok": true}`

Exists so the gate screen can validate before storing. **No rate limit.**

### 7.4 `GET /internal/state`

`:55-328`. Pattern A. `actor_id` arrives as a **query parameter** (a GET has no
body) and is optional; its only effect is scoping notifications and unlocking
the sign-in list.

Response keys: `people`, `tracks`, `todos`, `events`, `activity`, `comments`,
`notifs`, `reminders`, `signins`, `expenses`, `passwords`, `notes`, `config`,
`channels`, `me`, `via_session`, `meters`.

**Every projection is explicit, and that is a security control, not a style
choice:**
* `people` (`:113-120`) exposes `has_code: !!code_hash` — **never `code_hash`
  itself**. A `return p` here would hand every offline cracker the hash of every
  login code in the building.
* `passwords` (`:265-268`) is metadata only. **`secret_enc` never rides in
  state**, not even encrypted.
* `signins` (`:297-306`) is admin-only, and projects only `person` and `created`
  — **never `token_hash` or `ip`.** Sign-in history is a list of when each
  teammate was at their desk; that is an admin's answer, not a thing every
  member reads about every other member.
* `comments` (`:209-220`) is filtered to todos already in this payload, so it
  cannot become a keyed window onto the comment history of tasks the caller was
  never shown. A tombstoned comment's `text` is blanked on the way out as well
  as on delete.
* `notifs` (`:224-235`) only when there is an actor, and only that actor's rows.
* `reminders` (`:238-248`) only unsent ones (`sent_at = ''`) on visible todos.

Query windows: people 200 by `+name`; tracks 50 by `+created`; todos
`status = 'open' || done_at >= <14 days ago>` 500 by `-created`; events
`date >= <yesterday, date only>` 200 by `+date`; activity 50 by `-created`;
comments 400 by `-created`; notifs 100; reminders 300 by `+fire_at`; expenses
500 by `-date`; passwords 200 by `+service`; notes 300 by `-updated`; config 20;
signins 10 by `-created`.

**The todo filter is `status = 'open' || done_at >= cut`** (`:153-155`), so a
*cancelled* row stays visible for its fourteen days instead of vanishing the
instant somebody drops it. The comment at `:146-152` is the important one for a
port: the board vocabulary (`todo/doing/waiting/blocked`) lives in a separate
`stage` column **precisely so this filter, the cron's reminder filter and the
assistant's board dump — all three keyed on `status = 'open'` — do not have to
change.** Widening `status` would make a task moved to "In progress" silently
stop being reminded about, with nothing red anywhere.

`config` defaults to `{team_name:"Anticipy", perm_assign:"everyone", perm_delete:"creator"}`
and only those three keys are read out of `internal_config`.
`meters.llm_used`/`llm_ceiling` (default 60 from `ANTICIPY_INTERNAL_LLM_CEILING`)
and `meters.research_job_id`.

Every section is individually `try`-wrapped: a failing query yields an empty
array, never a 500.

### 7.5 `POST /internal/people` — self-serve join

`:333-478`. Pattern C.

| condition | response |
|---|---|
| `name` blank or > 120 | `400 {"error":"a name between 1 and 120 characters, please"}` |
| `email` set and fails `/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/` | `400 {"error":"that email doesn't look right"}` |
| `phone` set and fails `/^\+?\d{8,15}$/` | `400 {"error":"phone should be digits with an optional +, like +16045550142"}` |
| an **active** person already has that name (case-insensitive) | `400 {"error":"<name> is already on the team — pick yourself from the list instead"}` |
| `remind_pref` set and ∉ {inapp,email,sms,both} | `400 {"error":"reminders are in-app, email, sms or both"}` |
| `mint_code` truthy and `actor_id` does not resolve | `400 {"error":"pick yourself first"}` |
| ...and that person is inactive | `400 {"error":"that person is deactivated"}` |
| ...and that person is not an admin | `403 {"error":"only an admin can hand out login codes"}` |
| `is_admin` truthy in the body and the minter is not a confirmed admin | `403 {"error":"only an admin can make someone an administrator"}` |
| success | `200 {...}` |

`phone` is normalised by stripping spaces, parentheses and hyphens **before**
validation.

**Minting a code is an admin act and only an admin act** (`:404-410`): without
that branch, anyone holding the shared key could mint a code for a new **admin**
account and convert "holds the shared key" into "is a person with a durable
session".

The code (`:436-457`): **Crockford base32, eight characters, SHA-256 only.**
Alphabet `0123456789ABCDEFGHJKMNPQRSTVWXYZ` — no I, L, O or U, so reading a code
aloud cannot land on the wrong character. 32^8 ≈ 1.1e12 against the
40-attempts-an-hour ceiling in `POST /internal/session` is not a brute force.
Stored as `$security.sha256(plain)`; **there is deliberately no route anywhere
in this file that can read a code back out.**

Response: `{id, name, email, phone, role, focus, tz, remind_pref, is_admin, active}`,
plus `code: "XXXX-XXXX"` **only when one was minted** — the plaintext leaves the
building exactly here, exactly once. It is not logged, not written to activity,
and not in `/internal/state`.

**Side effects:** one `internal_people` row; one `internal_activity` row
(`person.join`).

### 7.6 `PATCH /internal/people`

`:483-606`. Pattern C.

| condition | response |
|---|---|
| `actor_id` does not resolve | `400 {"error":"who is making this change? actor_id missing"}` |
| actor is inactive | `400 {"error":"that person is deactivated"}` |
| `person_id` does not resolve | `404 {"error":"no such person"}` |
| body has `is_admin` or `active`, and actor is not admin | `403 {"error":"only an admin can change roles"}` |
| target ≠ actor and actor is not admin | `403 {"error":"you can only edit your own details"}` |
| bad email | `400 {"error":"that email doesn't look right"}` |
| bad phone | `400 {"error":"phone should be digits with an optional +"}` |
| bad `remind_pref` | `400 {"error":"reminders are in-app, email, sms or both"}` |
| deactivating the **last** active admin | `400 {"error":"that's the last admin — promote someone else first"}` |
| success | `200 {"ok": true}` |

Presence-keyed fields: `email`, `phone`, `role` (80), `focus` (140), `tz` (60),
`remind_pref`, `email_on`, `sms_on`, `is_admin`, `active`.

**`code_hash` is deliberately not patchable here** (`:567-570`) — rotating a
credential has to sign the old sessions out, and that happens in exactly one
place. A second door onto this field would be a second door that forgets to
close them.

**Deactivating deletes every session row for that person immediately**
(`:583-594`), up to 200.

**Side effects:** the person row; up to 200 session deletions; one
`internal_activity` row (`person.update`).

### 7.7 `POST /internal/todos`

`:611-791`. Pattern C. Validation, in order:

| condition | response |
|---|---|
| `actor_id` does not resolve | `400 {"error":"who is creating this? pick yourself first"}` |
| `title` blank or > 500 | `400 {"error":"a title between 1 and 500 characters, please"}` |
| `track` does not resolve | `400 {"error":"that board doesn't exist"}` |
| that track is not `active` | `400 {"error":"that board is archived"}` |
| any assignee id does not resolve | `400 {"error":"one of the flagged people doesn't exist"}` |
| `due` set and fails `/^\d{4}-\d{2}-\d{2}$/` | `400 {"error":"due date should be YYYY-MM-DD"}` |
| `stage` ∉ {todo,doing,waiting,blocked} | `400 {"error":"pick a stage"}` |
| `priority` ∉ {urgent,important,normal,later} | `400 {"error":"priority is urgent, important, normal or later"}` |
| `due_time` set and fails `/^\d{2}:\d{2}$/` | `400 {"error":"a time looks like 14:30"}` |
| `repeat_rule` set and fails the rule regex | `400 {"error":"that repeat isn't one I know"}` |
| any watcher id does not resolve | `400 {"error":"one of the watchers doesn't exist"}` |
| `subtasks` longer than 40 | `400 {"error":"forty subtasks is plenty — the rest are their own task"}` |
| `remind_at` set and fails `/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/` | `400 {"error":"reminder time looks malformed"}` |
| `remind_at` set and `remind_channel` ∉ {email,sms,both} | `400 {"error":"pick a reminder channel: email, sms or both"}` |
| **nobody the reminder targets is reachable** | `400 {"error":"<missing list joined by '; '>"}` or `400 {"error":"nobody flagged has contact details yet"}` |
| success | `200 {"id": "<todo id>"}` |

Repeat rule regex (`:689`):
`/^(none|daily|weekdays|weekly|monthly|every:[2-9]|every:[12]\d|weekly:(mon|tue|wed|thu|fri|sat|sun))$/`

**The reachability refusal** (`:720-738`) — *a reminder that cannot reach anybody
is a lie on a card*. Recipients are the assignees, or the actor if there are
none. Reachable means at least one recipient satisfies the needed channel.

Defaults written: `status="open"`, `remind_sent_at=""`, `followup_sent_at=""`,
`remind_attempts=0`, `attachments="[]"`, `cmt_count=0`. `hold_reason` is stored
**only** when the stage is `blocked` or `waiting`. `notes` is sliced to 20,000.

**Side effects:** one `internal_todos` row; one `internal_activity` row
(`todo.create`); one `internal_notifs` row per assignee **who is not the actor**
(kind `assign`).

### 7.8 `PATCH /internal/todos`

`:796-1035`. Pattern C.

| condition | response |
|---|---|
| `actor_id` does not resolve | `400 {"error":"pick yourself first"}` |
| `todo_id` does not resolve | `404 {"error":"that item is gone"}` |
| `title` present, blank or > 500 | `400 {"error":"a title between 1 and 500 characters"}` |
| bad `due` / `stage` / `priority` / `due_time` / `repeat_rule` / `subtasks` length | as §7.7 |
| an assignee or watcher id does not resolve | `400` as §7.7 |
| `attachments` longer than 20 | `400 {"error":"twenty links is the ceiling"}` |
| an attachment url does not start `http://` or `https://` | `400 {"error":"a link has to start with http:// or https://"}` |
| `remind_at` malformed | `400 {"error":"reminder time looks malformed"}` |
| `remind_at` non-empty and `remind_channel` present but invalid | `400 {"error":"pick email, sms or both"}` |
| `status` ∉ {open,done,cancelled} | `400 {"error":"status is open, done or cancelled"}` |
| success | `200 {"ok": true}` |

**No permission check at all beyond having a key or a session** — anyone on the
team may edit any task. Deletion is where the creator/admin rule lives.

**A LINK AND A NAME, NEVER AN UPLOAD** (`:934-941`): only `http(s)` is stored, so
a pasted `javascript:` or `data:` URL cannot become a click target on a page
three people trust. Each attachment is stored as `{n, url, by: actor, at: ISO}`.

**Snapshot before write** (`:847-854`): `wasAssignees`, `wasDue`, `wasStage`,
`wasStatus` are captured first, and **every notification below is guarded on a
real transition against those values, not on the field merely being present in
the body** — otherwise a page that PATCHes its whole form on every keystroke
would text the assignee about a deadline that never moved.

**Finishing is idempotent** (`:958-984`). `done_at`/`done_by` are stamped only on
a real `open → done|cancelled` transition; `justFinished` is true only for
`done`. Re-opening clears both. Arav's first minutes on the board produced six
`todo.done` rows for three todos; a trail that says a thing happened twice is
simply wrong.

`remind_at` present **re-arms**: `remind_sent_at=""` and `remind_attempts=0`
(`:950-951`).

Stage changes to anything other than `blocked`/`waiting` clear `hold_reason`.

**Side effects:** the todo row; one `internal_activity` row only when
`justFinished` (`todo.done`); and `internal_notifs` rows, **one per real
transition**, never to the actor:
* new assignees → `assign`
* `due` actually changed → `deadline` to assignees **and** watchers
* stage became `blocked` from something else → `task` to `created_by`
* just finished from `open` → `done` to `created_by` and watchers

### 7.9 `POST /internal/todos/delete`

`:1040-1104`. Pattern C.
* `actor_id` unresolved → `400 {"error":"pick yourself first"}`
* `todo_id` unresolved → `404 {"error":"already gone"}`
* not the creator and not an admin → `403 {"error":"only the person who added it — or an admin — can delete it"}`
* else `200 {"ok": true}`

**Side effects:** the todo row is hard-deleted; one `internal_activity` row
(`todo.delete`). Comments and reminders pointing at it are **not** cleaned up —
`/internal/state` filters them out by `todoIds`, and the cron retires an orphaned
reminder on its next pass (`:2326-2329`).

### 7.10 `POST /internal/events` and `/internal/events/delete`

`:1109-1234`. Pattern C.

Create: `actor_id` unresolved → `400 {"error":"pick yourself first"}`;
`title` blank or > 300 → `400 {"error":"a title between 1 and 300 characters"}`;
`date` failing `/^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2})?$/` →
`400 {"error":"date should be YYYY-MM-DD (optionally THH:mm)"}`.
Success `200 {"id": "…"}`. `notes` sliced to 5,000. Side effects: the row plus an
`event.create` activity row.

Delete: unresolved event → `404 {"error":"already gone"}`; not creator and not
admin → `403 {"error":"only its creator or an admin can delete it"}`; else
`200 {"ok": true}`. **No activity row is written on event deletion** —
DIVERGENCE from todo deletion, which does write one.

### 7.11 `POST /internal/tracks` — admin-only upsert

`:1239-1342`. Pattern C.
* `actor_id` unresolved → `400 {"error":"pick yourself first"}`
* not admin → `403 {"error":"only an admin can manage boards"}`
* a member id does not resolve → `400 {"error":"one of those members doesn't exist"}`
* `track_id` given but unresolved → `404 {"error":"no such board"}`
* update with `name` present and blank → `400 {"error":"a board needs a name"}`
* create with blank or >120 name → `400 {"error":"a board name between 1 and 120 characters"}`
* `owner` given but unresolved → `400 {"error":"that owner isn't on the team"}`
* success → `200 {"id": "…"}`

**`active` and `archived` are different things and both are kept** (`:1317-1321`):
`active=false` takes a project out of the New Task picker (the guard in
`POST /internal/todos` refuses "that board is archived"); `archived=true` only
greys the card. Collapsing them would mean you cannot put a project away without
breaking every task on it.

**Side effects:** the track row; one `track.update` activity row.

### 7.12 The three dead AI routes — `410`

`POST /internal/router` (`:1350`), `POST /internal/research` (`:2015`),
`GET /internal/research/status` (`:2089`).

**Every one of them returns, unconditionally and as its first statement:**
```
410 {"error": "the AI surface was removed from HQ"}
```
No auth check runs, no key is read, no 503 is possible. The bodies below are
unreachable and are kept only because cutting a block out of a 4,276-line file by
hand is how you take the whole of HQ down with a stray brace (`:1356-1359`).

**For the port: implement the 410 and delete the bodies.** They are the only
place in the tree that creates a `jobs` row server-side (`:2112-2120`), bypassing
both `guard.pb.js` and `research_lane.pb.js` — dead code that, if revived, is a
hole in two guards at once.

### 7.13 `POST /internal/assistant` — the acting chat

`:1465-2007`. Pattern C. **Revived the same day it was killed**, because the ask
was "a little chat button on the side that can control the to-dos — not an
AI-first interface".

| condition | response |
|---|---|
| `actor_id` unresolved | `400 {"error":"pick yourself first"}` |
| `messages` not an array of 1-12 | `400 {"error":"between 1 and 12 messages"}` |
| hourly LLM meter ≥ ceiling | `429 {"error":"the team's AI budget for this hour is used up","resumes":"top of the hour"}` |
| total content > 6,000 chars | `400 {"error":"that conversation got long — start fresh"}` |
| `OPENROUTER_API_KEY` unset | `503 {"error":"no AI key configured on the server"}` |
| the model call threw | `502 {"error":"the AI didn't answer — try again"}` |

Everything else is **200**, including every refusal the assistant itself makes.
Three response shapes:
```json
{"say": "<= 800 chars"}
{"done": {"summary": "…", "action": {…}}}
{"say": "Sorry — say that again?"}          // unparseable model output
```

Meter: `internal_meter` row `name='llm'`, fields `hour` (`YYYY-MM-DDTHH`) and
`calls`; ceiling `ANTICIPY_INTERNAL_LLM_CEILING || 60`. **The attempt is counted
before the model call**, and a meter failure is logged and never blocking.

Model: `ANTICIPY_INTERNAL_MODEL || "google/gemini-3.7-flash"` via OpenRouter,
`temperature: 0`, `max_tokens: 2000`, `response_format: {type:"json_object"}`,
60-second timeout. **`max_tokens` 2000 is load-bearing** (`:1672-1682`): at 700
this failed ~2 in 5 with `finish_reason: "length"` because the model spends
reasoning tokens against the same budget. Do not "optimise" by excluding
reasoning — that drops it to 0/5.

**The assistant is given the board** (`:1574-1608`): open todos (newest 60,
titles clipped to 90) with track name, assignee names, stage, priority, due and
age; plus the last 12 activity subjects; plus the names of people with neither
email nor phone. Without it, asked "what is on the board right now?", it answered
"I don't have direct visibility... check the dashboard directly" *from inside
the dashboard*.

**Thirteen actions.** Every one of them is validated **in code**, with the same
lists the CRUD routes use, copied inline: *the system prompt is a wish, the
branch is the guarantee* (`:1916-1921`).

| action | resolution & refusals | writes |
|---|---|---|
| `create_todo` | track by name (default `"Company"`), each assignee by name; ambiguity or miss → `{"say": "<why>"}` | `internal_todos` row + activity |
| `complete_todo` | todo by title substring | sets `status=done`, `done_at`, `done_by` + activity |
| `delete_todo` | **creator or admin, same rule as the delete button** — else `{"say":"Only <name> or an admin can delete …"}` | hard delete + activity |
| `assign_todo` | names; empty list → `{"say":"Flag it to whom?"}` | `assignees` + activity |
| `set_reminder` | `remind_at` must match the ISO-minute prefix | `remind_at`, `remind_channel`, clears `remind_sent_at`, `remind_attempts=0` + activity |
| `create_event` | title and `YYYY-MM-DD[THH:mm]` | `internal_events` row + activity |
| `add_person` | duplicate active name → `{"say":"<name> is already on the team."}`; email/phone validated | `internal_people` row, **`is_admin: false`, `active: true`** + activity |
| `set_contact` | exactly one active name match; needs `email` or `phone` present | the person row + activity |
| `set_priority` | ∈ {urgent,important,normal,later} | `priority` + activity |
| `set_stage` | ∈ {todo,doing,waiting,blocked}; `hold_reason` kept only for blocked/waiting | `stage`, `hold_reason` + activity |
| `add_subtask` | ≥40 existing → `{"say":"That one already has forty steps…"}` | `subtasks` + activity |
| `comment` | text required | `internal_comments` row, `cmt_count`+1 + activity |
| `create_project` | **admin only** → `{"say":"Only an admin can start a project — ask Omar."}`; duplicate name refused | `internal_tracks` row + activity |

Name resolution (`:1703-1745`): a person matches on exact name **or prefix**;
zero → "I don't know anyone called X"; more than one → "which X — A or B?".
A track matches on exact name **or substring**. A todo matches on a title
substring of ≥3 chars among the 200 newest **open** todos; more than one →
"that matches N items — be more specific".

**No `set_admin`, no `deactivate`, no `delete_person`, no `delete_project`, no
`reveal_password`.** The assistant gets no more power than the person talking to
it has, and several powers less.

Any throw inside the action block → `200 {"say":"That didn't go through — try it by hand?"}`.
An unknown action type → `200 {"say":"I don't know how to do that yet."}`.

**`set_stage` cannot write `done`** — that would take the row out of the reminder
cron, `/internal/state` and the assistant's own board in one keystroke.

**Side effects:** the LLM meter; one OpenRouter call; whatever the action writes;
one `internal_activity` row per successful action (`assistant.action`).

### 7.14 `POST /internal/session` — the code is the credential

`:2714-2834`. **The one new security surface in the file.**

**503 when the key is unset even though this route does not check the key**
(`:2715-2719`): a half-configured deploy must not leave one door open in an area
every other door has shut.

**ONE SENTENCE FOR EVERY FAILURE** (`:2724-2730`). Wrong code, revoked code,
deactivated person, tripped ceiling, unwritable session row, missing meter that
could not be created — all of it:
```
200 {"ok": false, "message": "That code didn't match anyone. Check it and try again."}
```
Different messages would tell a stranger whether a code exists, whether the
person is still on the team, and whether they are being rate limited — three
facts they can only use.

**Normalisation** (`:2738-2740`), Crockford as intended:
uppercase → strip everything outside `[A-Z0-9]` → `I`→`1`, `L`→`1`, `O`→`0`,
`U`→`V`. Length must then be exactly 8.

**GLOBAL HOURLY CEILING, COUNTED ON THE ATTEMPT, BEFORE THE COMPARISON**
(`:2742-2766`). `ANTICIPY_HQ_LOGIN_CEILING || 40`, on the `internal_meter` row
`name='login'`. Global rather than per-IP because an attacker rotates addresses
and a three-person team never reaches forty tries in an hour. **If the meter row
is missing it is created** rather than the ceiling being skipped — *a
brute-force guard that silently stops counting is worse than none, because
everything downstream keeps reporting that it is guarded.* If it cannot be
created or saved, the route refuses. **Fail closed.**

Lookup is `code_hash = sha256(normalised)`, and the result is **re-compared with
`$security.equal`** anyway (`:2779`) — the lookup is by hash so a dump is not a
pile of live credentials, and the timing-safe compare stops a byte-at-a-time
oracle against the hash. Then `active` is re-checked.

Session: `token = randomStringWithAlphabet(64, "0123456789abcdef")`, stored as
`sha256(token)` with `expires = now + 30 days`, plus `ip` (first
`X-Forwarded-For` element, else `e.realIP()`, 60 chars) and `ua` (200 chars).
**Only the hash is stored.**

**Keep the last ten sign-ins per person** (`:2808-2812`), reading 60 and deleting
from index 10 — the collection doubles as "Who's been in lately", and unbounded
growth is how the volume filled once already.

Success:
```json
{"ok": true, "token": "<64 hex>", "expires": "<ISO>",
 "person": {"id","name","is_admin","role","focus","tz","remind_pref","email_on","sms_on"}}
```

**Side effects:** the `login` meter; one `internal_sessions` row; up to 50
session deletions; `internal_people.last_in`; one `person.signin` activity row
whose subject distinguishes a first sign-in.

### 7.15 Expenses

`:2882-3006`. Pattern C, **and both routes check `active`.**

Create: `title` blank → `400 {"error":"what was the expense for?"}`;
`amount` not a positive finite number → `400 {"error":"amount has to be a positive number"}`;
`date` set and malformed → `400 {"error":"date should be YYYY-MM-DD"}`;
a save throw → `500 {"error":"could not save the expense"}`; else `200 {"ok":true,"id":"…"}`.
`amount` is rounded to 2 decimals; `currency` ∈ {CAD, USD} defaulting to CAD;
`date` defaults to today; `person` and `created_by` are both the actor.

Delete: unresolved → `404 {"error":"that expense is already gone"}`;
not `created_by` and not admin → `403 {"error":"only whoever logged it (or an admin) can delete it"}`;
else `200 {"ok": true}`. **No activity row either way.**

### 7.16 The vault

`:3013-3198`. Pattern C plus, on the first two routes only, a vault-key check:
`ANTICIPY_VAULT_KEY` must be **exactly 32 characters** or
`503 {"error":"the vault is not configured"}`.

**`POST /internal/passwords`** (upsert):
`password_id` given but unresolved → `404 {"error":"that entry is gone"}`;
creating with a blank `service` → `400 {"error":"which tool is this for?"}`;
encryption threw → `500 {"error":"could not encrypt that"}`; save threw →
`500 {"error":"could not save"}`; else `200 {"ok":true,"id":"…"}`.
Fields are presence-keyed: `service` (120), `username` (200), `url` (500),
`notes` (2000). **`secret` is written only when present AND non-empty**
(`:3076-3081`) — an edit to fix a typo in the URL must never blank the password.
Stored as `$security.encrypt(secret[:500], vaultKey)`.

**`POST /internal/passwords/reveal`**: unresolved → `404 {"error":"that entry is gone"}`;
decryption threw → `500 {"error":"could not decrypt — was the vault key rotated?"}`;
else `200 {"ok":true,"secret":"<plaintext>"}`.
**Any active teammate may reveal any vault entry.** There is no admin gate, no
per-entry ACL, no rate limit, and no activity row. That is the current contract;
a port must reproduce it or change it deliberately.

**`POST /internal/passwords/delete`**: **no vault-key check**; unresolved →
`404 {"error":"already gone"}`; else `200 {"ok":true}`. **Any active teammate may
delete any entry.** No creator/admin rule — DIVERGENCE from every other delete
route in the file.

### 7.17 Notes

`:3204-3326`. Pattern C, both check `active`.

Upsert: `note_id` given but unresolved → `404 {"error":"that note is gone"}`;
after applying the presence-keyed fields, a row with neither title nor body →
`400 {"error":"an empty note isn't worth keeping"}`; save threw →
`500 {"error":"could not save the note"}`; else `200 {"ok":true,"id":"…"}`.
`title` 200, `body` 50,000, `track` 32. `created_by` on create, `updated_by`
always. **Anyone edits; deleting stays with the creator or an admin.**

Delete: unresolved → `404 {"error":"already gone"}`; not creator and not admin →
`403 {"error":"only whoever started it (or an admin) can delete a note"}`; else
`200 {"ok":true}`.

### 7.18 `GET /internal/cal/{token}` — the calendar feed

`:3328-3383`. **AUTH IS THE TOKEN ITSELF**: `sha256(ANTICIPY_INTERNAL_KEY + personId)`,
deterministic on purpose — no new column, no minting flow, and rotating the team
key revokes every feed at once.

* key unset → `503 {"error":"internal HQ is not configured"}`
* the path value, with a trailing `.ics` stripped, failing `/^[0-9a-f]{64}$/` →
  `404 {"error":"not found"}`
* no active person whose derived token matches (compared with `$security.equal`
  against every active person, up to 200) → `404 {"error":"not found"}`
* else `200`, `Content-Type: text/calendar; charset=utf-8`

Body: a VCALENDAR containing this person's **open, dated** todos where they are
an assignee (up to 500, summary `HQ: <title>`), plus **every** team event with a
date (up to 200). All-day `DTSTART;VALUE=DATE:YYYYMMDD` entries — a feed that
guesses at hours puts wrong hours on somebody's phone. Text is ICS-escaped
(`\\`, `\;`, `\,`, newline → `\n`) and clipped to 250 chars. CRLF line endings.

**The cost, stated honestly** (`:2871-2873`): a leaked feed URL stays valid until
the key rotates. For a three-person team whose feed contains task titles, that
trade is taken knowingly. Note the feed also carries **every team event to every
person**, not only their own.

Served from the Railway origin directly because the anticipy.ai edge sits behind
a passcode gate and Google's fetcher will never have the cookie.

### 7.19 `POST /internal/clerk/exchange`

`:3385-3451`.

| condition | response |
|---|---|
| `ANTICIPY_INTERNAL_KEY` unset | `503 {"error":"internal HQ is not configured"}` |
| `CLERK_HQ_JWT_KEY` unset | `503 {"error":"Clerk sign-in is not configured"}` |
| `body.token` blank or not three dot-separated parts | `400 {"error":"no Clerk token in the request"}` |
| `$security.parseJWT(token, jwtKey)` threw or returned nothing | `401 {"error":"Clerk did not recognise that sign-in"}` |
| `claims.email` blank after trim, or `claims.sub` absent | `401 {"error":"Clerk did not recognise that sign-in"}` |
| no **active** `internal_people` row with `email:lower = <that email>` | `403 {"error":"You signed in as <email>, but nobody in HQ has that email. Ask an admin to add it to your person on the People page."}` |
| session row could not be written | `500 {"error":"could not start a session"}` |
| success | `200 {"ok":true,"token","expires","person":{"id","name","is_admin"}}` |

**HS256, not Clerk's default RS256** (`:2850-2857`): the JSVM cannot check an
RS256 signature, and Clerk's server-side verify endpoint answers 410
(deprecated, tried 2026-08-23). The page asks Clerk for a token minted from the
`hq` JWT **template** — HS256, signed with a key only Clerk and this backend
hold, 60-second life, carrying the email as a claim. `parseJWT` checks signature
and expiry here. No Clerk API call, and **the email comes from Clerk's signature
rather than from the client**.

`sub` and `email` are re-checked because a claim that is merely absent would
otherwise sail through as an empty string.

**Signing up to Clerk is open to the world; membership of HQ is decided by the
People page — this route is the wall between those two facts.**

Session minting is `/internal/session`'s, verbatim in shape: same collection,
hash-only storage, 30-day expiry, keep-ten. Naming the email in the 403 is safe
because the caller has just proven to Clerk that they own it.

**DIVERGENCE:** no activity row is written here, where `/internal/session`
writes a `person.signin`. A Clerk sign-in is invisible in the feed.

### 7.20 `POST /internal/session/end`

`:3453-3466`. Key unset → 503. No `X-HQ-Session` header → `200 {"ok":true}`
("already signed out; say so plainly"). Otherwise delete the row whose
`token_hash` matches and return `200 {"ok":true}`. **Always 200** — whether that
token existed is not a thing this route reports.

### 7.21 `GET /internal/me`

`:3472-3532`. Pattern A, but **the actor is required** in the key branch:
unresolved or missing `actor_id` → `400 {"error":"pick yourself first"}`;
inactive → `400 {"error":"that person is deactivated"}`.

```json
{"via_session": <bool>,
 "person": {"id","name","is_admin","role","focus","tz","email","phone",
            "remind_pref","email_on","sms_on","has_code",
            "cal_url": "https://<RAILWAY_PUBLIC_DOMAIN or request host>/internal/cal/<sha256(key+id)>.ics"},
 "team_name": "...", "perm_assign": "...", "perm_delete": "..."}
```

`via_session` is returned **because the page hides the "You're looking at HQ as
Ari" switcher when it is true** — a real session must not be able to pretend to
be somebody else, and the control that would let it simply is not drawn.

`has_code` is a boolean; the hash never leaves.

### 7.22 `POST /internal/people/code` — rotate a login code

`:3538-3603`. Pattern B, then `!actor.is_admin` →
`403 {"error":"only an admin can hand out login codes"}`.
`person_id` unresolved → `404 {"error":"no such person"}`.

Mints a fresh 8-char Crockford code, stores `sha256`, stamps `code_set_at`.

**A RESET SIGNS THE OLD CODE OUT** (`:3578-3587`): every session row for that
person is deleted, up to 200, and the count is reported. Rotating `code_hash`
alone would leave every session minted with the previous code alive for up to
thirty days — a revoked credential outliving its revocation.

Response: `200 {"code":"XXXX-XXXX","signed_out":n,"name":"…"}`.
**The code never appears in the activity row** — an activity feed is read by
everyone.

**Side effects:** the person row; up to 200 session deletions; one `person.code`
activity row.

### 7.23 Comments

`:3608-3816`. Pattern B.

**POST**: `todo_id` unresolved → `404 {"error":"that item is gone"}`;
blank text → `400 {"error":"say something first"}`;
`parent` given but unresolved → `404 {"error":"that comment is gone"}`;
`parent` belonging to a different todo → `400 {"error":"that reply doesn't belong to this task"}`
(letting one point at a comment on a different task would put somebody's sentence
under a task they never opened). Success `200 {"id","created"}`. Text clipped to 4,000.
`author_name` is denormalised so the thread still reads right after somebody is
deactivated.

**Mentions, then everybody else, and never both** (`:3668-3700`): a `told` map
seeded with the actor's own id means nobody is notified twice and nobody is
notified about their own comment. `@Name` and `@FirstName` are matched against
**active** people only, **longest name first**, so `@Jose` inside `@Joseph`
cannot claim the wrong person. Then assignees (`comment`), then watchers
(`comment`).

**PATCH**: not the author → `403 {"error":"only the person who wrote it can edit it"}`.
**Editing is not an admin power** (`:3750-3751`) — an admin can remove a comment;
putting different words in somebody else's mouth is a different thing entirely.
A tombstoned comment → `404 {"error":"that comment is gone"}`. Blank text → 400.
Success sets `text` and stamps `edited_at` (the mark that makes the thread
honest) → `200 {"ok":true}`.

**delete**: author or admin, else
`403 {"error":"only the person who wrote it — or an admin — can remove it"}`.
Already deleted → `200 {"ok":true}` (idempotent).
**A TOMBSTONE, NOT A DELETE** (`:3803-3807`): `deleted = true` and `text = ""`.
Deleting the row would orphan every reply hanging off it, and an orphaned reply
is a sentence with no question above it. `cmt_count` is decremented, floored at 0.

### 7.24 Reminders

`:3821-3991`. Pattern B.

**POST**: `todo_id` unresolved → `404 {"error":"that item is gone"}`;
`rule` ∉ {`at`, `one_hour_before`, `one_day_before`, `when_overdue`, `daily_until_done`}
→ `400 {"error":"I don't know that kind of reminder"}`;
`channel` ∉ {inapp,email,sms,both} → `400 {"error":"reminders are in-app, email, sms or both"}`;
`person` given but unresolved → `400 {"error":"that person isn't on the team"}`;
**nobody reachable** (skipped entirely for `inapp`, which always reaches — it is a
row in their tray) → `400 {"error":"<missing joined by '; '>"}` or
`400 {"error":"nobody on this has contact details yet"}`;
`tz_offset` present and outside `[-840, 840]` →
`400 {"error":"that timezone offset isn't a real one"}`;
an explicit `at` that will not parse → `400 {"error":"that time looks malformed"}`;
no `at` and the todo has no `YYYY-MM-DD` due →
`400 {"error":"give the task a deadline first, or tell me a time"}`.
Success `200 {"id","fire_at","label"}`.

**THE OFFSET COMES FROM THE BROWSER** (`:3898-3905`), deliberately: this runtime
has no timezone database — there is no `Intl` — so the only alternatives were a
hand-maintained offset table that is wrong twice a year and silently, or asking
the one participant that genuinely knows. It is range-validated so a hostile
value cannot push a reminder years away. Absent, everything is treated as UTC and
the label says the UTC time, so nothing on screen claims an hour it cannot deliver.

Anchor: explicit `at` (any ISO-ish string, `Z` appended if it carries no zone),
else `Date.UTC(due, due_time || "09:00") - offMin*60000`.
Fire time and label:

| rule | fire | label |
|---|---|---|
| `at` | anchor | `At the deadline` |
| `one_hour_before` | anchor − 3600000 | `One hour before` |
| `one_day_before` | anchor − 86400000 | `One day before` |
| `when_overdue` | anchor + 60000 | `When it goes overdue` |
| `daily_until_done` | anchor | `Every day until it's done` |

A fire time already in the past is pushed to `now + 60000`, so "one hour before"
on something due in ten minutes still says something.

**delete**: unresolved → `404 {"error":"already gone"}`; not `created_by` and not
admin → `403 {"error":"only the person who set it — or an admin — can take it off"}`;
else `200 {"ok":true}`.

### 7.25 `POST /internal/notifs/read`

`:3996-4053`. Pattern B. Body is `{"all": true}` **or** `{"ids": [...]}`;
neither → `400 {"error":"which ones? send ids, or all:true"}`.
`all` marks up to 500 of the actor's unread rows read. `ids` is capped at 200 and
**every row whose `person` is not the actor is silently skipped** — marking
somebody else's notification read would hide a thing they were told, from them,
with no trace.
Success `200 {"ok":true,"unread":n}` where `n` counts up to 200 remaining unread.

### 7.26 `POST /internal/tracks/delete` — admin only

`:4058-4130`. Pattern B, then `!actor.is_admin` →
`403 {"error":"only an admin can remove a project"}`;
`track_id` unresolved → `404 {"error":"already gone"}`.

**DELETING A PROJECT MUST NEVER DELETE WORK** (`:4093-4097`). A home is chosen
among the other tracks: a track literally named `company` (case-insensitive)
wins, otherwise the first other track by `+created`. **If there is none →
`400 {"error":"that's the only project — make another one first"}`.** Then every
todo on the doomed track (up to 500) is moved to the home track and counted.

Success `200 {"moved":n,"moved_to":"<home id>"}`. Side effects: up to 500 todo
updates; the track row; one `track.delete` activity row naming the count.

A todo whose `track` points at a row that no longer exists is invisible on every
screen that groups by project — gone without ever appearing in the activity feed
as gone.

### 7.27 `POST /internal/settings` — admin only

`:4135-4197`. Pattern B, then `!actor.is_admin` →
`403 {"error":"only an admin can change team settings"}`.
Presence-keyed:
* `team_name` blank → `400 {"error":"the team needs a name"}`; clipped to 120
* `perm_assign` ∉ {everyone, admins} → `400 {"error":"everyone, or admins only"}`
* `perm_delete` ∉ {admins, creator} → `400 {"error":"admins only, or the creator and admins"}`

Each is upserted into `internal_config` by `key`. Success `200 {"ok":true}` plus
a `settings.update` activity row.

**Note:** `perm_assign` and `perm_delete` are stored and reported and **enforced
nowhere** in this file — every delete route hardcodes creator-or-admin. Stored
intentions with no motor.

### 7.28 `GET /fellows/hq` — the page

`:4250-4276`. No auth. Reads `ANTICIPY_HQ_PAGE || "pb_public/internal.html"`.

**FAIL VISIBLY, NOT PARTLY** (`:4258-4262`): if the file is under 200 bytes or
does not contain `<!doctype` (case-insensitively), serve **503** with one honest
sentence naming the path (HTML-escaped) rather than half a document. A page that
renders with its script missing looks like a broken product; a page that says it
could not load looks like a thing to go and fix.

Otherwise `200 text/html`, plus `X-Robots-Tag: noindex, nofollow`.
The page ships no data and no secrets — everything it shows it fetches through
the keyed or session routes — which is what makes it safe to serve from a public
prefix at all.

---

## §8. MODEL HOOKS AND CRONS

These fire on **every** write path — the HTTP API, an internal `e.app.save()`,
the dashboard, a migration. A port that implements them only on the HTTP path
has not implemented them.

### 8.1 `job_commitment_identity.pb.js` — commitment release

`onRecordCreate("jobs")` and `onRecordUpdate("jobs")`, `:10-19`.

```js
if (status ∈ {"done", "failed", "cancelled"}) record.commitment_key = "";
```

`commitment_key` is a SHA-256 of tenant id + memory node id, and a **unique
partial index** (`idx_jobs_active_commitment`, migration 1700000055) refuses two
occupied rows for the same durable promise. Clearing it before a terminal row is
persisted keeps the history available and lets an intentional later retry acquire
the identity.

**These are model hooks, not HTTP hooks** (`:8-9`): browser, worker, dashboard
and internal saves all cross the same boundary. A create that arrives already
terminal is also cleared — which cannot happen through the HTTP API, because
`workflow_guard`'s ENTRY_STATUSES refuses it, but can happen through an internal
save.

### 8.2 `audit_retention.pb.js` — the standing cap

`onRecordAfterCreateSuccess("agent_llm_audit")`, `:71-83`. `AUDIT_KEEP = 300`.
After every audit write, find up to 25 rows past the newest 300 by `-created` and
delete them. Every failure is swallowed: **never let housekeeping break the write
that triggered it.**

Because `/agent/llm` saves the audit row **twice** (begin and finish), the sweep
runs once per proxied model call.

### 8.3 `evidence.pb.js` — the evidence sweep

`onRecordAfterCreateSuccess("evidence")`, `:244-269`.
`KEEP_PER_OWNER = 20`, `KEEP_TOTAL = 60`, `SWEEP_BATCH = 25`.

Two ceilings, because one was not enough last time. First, up to 25 rows past
this owner's newest 20; then up to 25 rows past the global newest 60. Every
failure swallowed.

The arithmetic (`:238-243`): at the field's 400 KB ceiling, 60 × 400 KB = 24 MB
live and about 72 MB at peak with both nightly snapshots — PocketBase's scheduled
backup zips `pb_data` (storage included) onto the same volume and keeps two, so
peak footprint is three copies of every stored byte.

**The per-owner cap is the privacy half of the same sweep**: nobody's screenshots
accumulate indefinitely just because they were the quiet account. It is **not** an
erasure control — `account_delete.pb.js` is (`:73-77`).

### 8.4 `cronAdd("internal_hq_sweep", "*/5 * * * *")`

`internal_hq.pb.js:2139-2636`. **Cron handlers have no `e`; everything goes
through the global `$app`.** `REMIND_MAX_TRIES = 3`.

**CLAIM-FIRST, THEN SEND** — the deliberate inversion of the password-reset rule
(`:2180-2187`). This cron refires every five minutes forever, so send-first with
a failed persist means **unbounded duplicate texts** (the worker lived exactly
that loop). Claim-first with a failed send loses at most one nudge, and the todo
still sits on the board with its due chip. The stamp rolls back only when *every*
channel failed.

**Pass A — one-shot reminders** (`:2228-2276`). Query:
`status = 'open' && remind_at != '' && remind_at <= now && remind_sent_at = ''`,
`+remind_at`, 20 rows.
Per row: stamp `remind_sent_at = now` and save **first**; then send to each
recipient on the row's channel. Recipients are the assignees, or `created_by` if
there are none, filtered to active people (`recipientsOf`, `:2212-2224`).
* any send succeeded → reset `remind_attempts` to 0 if it was non-zero; log
  `reminder.sent`
* nothing sent → `remind_attempts += 1`. At ≥3, **keep the claim** and log
  `reminder.gave_up`. Below 3, roll `remind_sent_at` back to `""` and log
  `reminder.failed`.

**Pass B — follow-ups, one nudge ever** (`:2278-2299`). Query:
`status = 'open' && due != '' && due <= <2 days ago> && followup_sent_at = ''`,
`+due`, 10 rows. Stamp `followup_sent_at` first. Email **or**, only if there is
no email, SMS. No retry budget: a failure is simply not logged.

**Pass C — `internal_reminders`** (`:2301-2406`). Query:
`sent_at = '' && fire_at != '' && fire_at <= now`, `+fire_at`, 20 rows.
* The todo is gone or not `open` → stamp `sent_at` and move on. *Firing a bell
  about a task nobody can open is worse than silence.*
* Stamp `sent_at` first, then send. `person` empty means every recipient of the
  todo, the same rule Pass A uses.
* `channel === "inapp"` writes an `internal_notifs` row (kind `deadline`, with
  `emailed_at` and `smsed_at` pre-stamped so the digest never re-sends it) and
  always counts as sent — it never touches the retry budget.
* Email/SMS additionally respect `person.email_on` / `person.sms_on`
  (`!== false`), which Pass A does **not** — DIVERGENCE.
* On success, **and only after a successful send**, a `daily_until_done` rule
  re-arms: `fire_at = now + 24h`, `sent_at = ""`, `attempts = 0`. Re-arming
  before would let an undeliverable rule walk its `fire_at` forward forever and
  the give-up counter would never run.
* On total failure, the same 3-try budget as Pass A.

**Pass D — the notification digest** (`:2408-2488`).
**ONE MESSAGE PER PERSON PER SWEEP, never one per event.** `SETTLE_MS = 10 min`:
a notification is not eligible until it has sat unread for ten minutes, so a
burst collects into one digest instead of racing the first one out the door.

Query `read = false && emailed_at = ''`, `+created`, 200 rows; age is checked in
JS with `pbTime()` because `created` is an autodate PocketBase writes as
`"2026-08-22 04:11:34.880Z"` and comparing that against a JS `toISOString()` is
the exact shape of bug that has already produced NaN and a permanently jammed
queue in this file. Up to 20 rows per person.

Per person: a missing or deactivated person gets the whole batch stamped
(`emailed_at` and `smsed_at`) so it stops being reconsidered every five minutes
forever, and nothing is sent. Otherwise `wantEmail` / `wantSMS` are derived from
`remind_pref`, `email_on`/`sms_on` and the presence of an address.
**THE CLAIM IS WRITTEN ON EVERY ROW IN THE BATCH BEFORE ANY SEND** (`:2456-2463`)
— if the process dies between here and the Resend call the person misses one
digest, and every one of those events is still in their tray unread. The other
way round they would get the same text every five minutes until somebody
restarted the backend.
"In-app only" is a real answer, not a failure: the rows are stamped, the tray
fills, the phone stays quiet.
Email subject `"<n> update(s) in Anticipy HQ"`; body is `text/`, **not** `html/`
— a comment body is whatever somebody typed, and the only safe thing to do at
this boundary is send it as text so no mail client is asked to parse it as
markup. SMS carries the first two lines plus "…and N more." and the short link,
clipped to 300.

**Pass E — the research-slot backstop** (`:2490-2515`). Clears
`internal_meter[name='research'].live_job_id` when the job is terminal, when the
job cannot be read at all, or when it has not been `updated` in 30 minutes.
The `pbTime()` fix here is the ZZ/NaN bug that pinned the slot forever.

**Pass F — the repeat motor** (`:2517-2635`). `repeat_rule` was stored and
validated since hq_v2 and nothing ever acted on it. Query
`repeat_rule != '' && repeat_rule != 'none' && due != ''`, `-due`, 500 rows.
Series key is `title|track|repeat_rule`; the instance with the greatest `due`
carries the torch. Local day is a **fixed UTC-8** (`:2531-2533`) — this VM has no
timezone database, and for a day-granular generator the only cost of ignoring DST
is that new items appear at 1am Vancouver in summer.
`nextAfter()` supports `daily`, `every:N` (2-29), `weekdays` (skips Sat/Sun),
`weekly`, `weekly:<dow>`, `monthly` (clamped to the month's last day).
**Missed cycles are not backfilled** — after downtime the series resumes at the
most recent scheduled date ≤ today, one item, not a pile (guarded at 400
iterations). A row already existing at `title+track+due` is skipped.
The new row copies title, notes, track, assignees, watchers, priority,
`created_by`, `due_time` and `repeat_rule`; sets `stage="todo"`, `status="open"`;
**wipes every subtask checkmark**; moves `remind_at` forward by the same distance
the due date moved; zeroes `remind_sent_at`, `followup_sent_at`,
`remind_attempts`, `cmt_count`, `attachments`, `hold_reason`.
**Completion does not stop a series** — "on his calendar every day" means every
day, done or not. To end one, set its repeat to `none`.
One `repeat.laydown` activity row when anything was made.

**Outbound transports.** `sendSMS` uses `TWILIO_ACCOUNT_SID` +
**`TWILIO_AUTH_TOKEN`** (not the API key pair — DIVERGENCE from
`password_reset.pb.js`, which prefers the scoped key) with a hand-rolled base64
Basic header. `sendEmail` uses `RESEND_API_KEY` against
`https://api.resend.com/emails`, from `Anticipy HQ <notifications@aevoy.com>`.
Both return a boolean and swallow every error.

### 8.5 `cronAdd("internal_hq_prune", "17 4 * * *")`

`internal_hq.pb.js:2642-2682`. Four sweeps, each capped at 200 rows and each
individually try-wrapped:

| collection | filter | why |
|---|---|---|
| `internal_activity` | `created <= <60 days ago>` | this ledger filled the volume once |
| `internal_sessions` | `expires != '' && expires <= now` | housekeeping only — expired sessions are already refused on every request; **this is not a security control and must not be mistaken for one** |
| `internal_notifs` | `read = true && created <= <30 days ago>` | **UNREAD ROWS ARE NEVER PRUNED, at any age** — a thing somebody was told and has not seen is the one row here that still has a job to do |
| `internal_reminders` | `sent_at != '' && sent_at <= <30 days ago>` | a live one is left alone however far in the future it points |

---

## §9. CROSS-CUTTING INVARIANTS AND PORTING HAZARDS

Ranked by what breaks if the port gets it wrong.

### 9.1 The generic REST API *is* the interface

`iOS`, `macOS`, the Chrome extension, `brain/pb.py` and ~30 proof harnesses all
speak `/api/collections/{name}/records` with PocketBase's filter DSL, and
authorization is implemented by **parsing and rewriting those filter strings**
(`guard.pb.js:45-50`, `research_lane.pb.js:436-452`). There is no purpose-built
API layer to swap.

A Cloudflare port therefore has exactly three honest options, and it should pick
one deliberately rather than drift:

1. **Reimplement the surface.** Build `/api/collections/{name}/records` on D1,
   including enough of the filter DSL to serve `owner_ref="X" && status="queued"`,
   `pair_code="123456"`, `lineage_key={:k} && consequence={:c}`, `sent_at = ''`,
   `email:lower = {:em}`, and `date >= {:cut}`. Every client keeps working
   unchanged. This is the largest piece of work and the only one that does not
   require shipping five clients at once.
2. **Reimplement the surface as a translation layer** in front of purpose-built
   endpoints — same wire format, different internals. Same client compatibility;
   the filter parser is still required, but it becomes a query planner rather
   than a string matcher, which is strictly better security.
3. **Replace the surface and reship every client.** iOS through TestFlight,
   macOS through the DMG, the extension through the Chrome store, the firmware,
   and the worker. Extensions in the wild cannot be recalled —
   `research_lane.pb.js:11-16` is a monument to that fact. Any client that is not
   updated stops working the day the old backend is turned off.

The conformance suite in `contract_tests.py` is written against the wire format,
so it is the same suite under options 1 and 2 and is largely useless under 3 —
which is itself a useful signal about the size of option 3.

### 9.2 Things with no Cloudflare equivalent

| what | where | why it does not port as-is |
|---|---|---|
| `e.app.store()` | `guard.pb.js:124` | process-wide in-memory KV. A Worker has no process. The pair-code counters need **Durable Objects** (strong consistency, which is what a ceiling needs) or a D1 table with a periodic sweep. KV is eventually consistent and would let the ceiling be walked around. |
| `e.app.runInTransaction()` | `phone_remove.pb.js:35`, `owner_profile_upsert.pb.js:87` | D1 has batch, not interactive, transactions. Both routes read → decide → write → **verify inside the transaction**. Rewrite as a D1 batch plus a post-commit verification, and accept that the pre-commit proof becomes a post-commit proof. |
| `cronAdd` | 2 crons | **Cloudflare Cron Triggers.** `*/5 * * * *` and `17 4 * * *` are both expressible. The 5-minute sweep does up to ~50 outbound HTTP calls; check it against the Worker CPU/subrequest limits. **UNVERIFIED**: the current subrequest ceiling per Worker invocation — measure before assuming the sweep fits in one. |
| `$security.encrypt` / `decrypt` | `internal_hq.pb.js:3079, 3140` | PocketBase's AES-GCM with a 32-char key. WebCrypto can do this, but **the ciphertext format must match byte-for-byte or every stored vault secret becomes unreadable**. Decide before migrating whether to re-encrypt on the way over. |
| `$security.parseJWT` | `internal_hq.pb.js:3400` | HS256 verify; WebCrypto does this natively. Straightforward. |
| `$security.sha256`, `$security.equal`, `$security.randomStringWithAlphabet` | everywhere | WebCrypto + `crypto.getRandomValues`. Note `$security.equal` is timing-safe and several call sites depend on that. |
| `$os.readFile` | `internal_hq.pb.js:4256` | serving `pb_public/internal.html` (136 KB). Becomes a static asset or an embedded string. |
| `e.realIP()` | `guard.pb.js:153`, `internal_hq.pb.js:2794` | `CF-Connecting-IP`. **Better** than the current value, which behind Railway's edge may collapse every caller into one bucket. |
| stored files | `evidence.image` | **R2.** `/api/files/evidence/{id}/{filename}` must keep its exact shape — it is the URL Twilio fetches. |
| PocketBase auth tokens | `e.auth` | JWTs signed with the record's `tokenKey`. Any port must keep verifying tokens the iPhone already holds, or every user is signed out on cutover. |

### 9.3 Behaviours that look like bugs and are not

Do not "fix" these during the port; the conformance suite pins them.

* `guard.pb.js` **fails open** with no service token (`:26`).
* `workflow_guard.pb.js` **skips entirely** for a job with no `workflow_id` (`:24`).
* `/agent/llm`'s meter **fails open** — a meter that cannot be read does not block
  the call (`:197-200`).
* `/internal/session`'s meter **fails closed** — a meter that cannot be created or
  saved refuses the login (`:2759, 2766`).
* `/evidence/share` returns **200 with `ok:false`** for every non-auth failure,
  because a broken `MediaUrl` fails the whole text message.
* `/auth/reset/request` returns **200 with the same sentence** for every outcome.
* `/internal/session` returns **200 with `ok:false`** and the same sentence for
  every failure.
* `/sms/inbound` returns **200 with empty TwiML** for a dropped message and
  **500** for an uncertain one, because 500 is what makes Twilio retry.
* `/api/files/*` returns **404 with one sentence** for all four public-door
  refusals.
* The pair-code lookup returns **`e.next()`** (an empty PocketBase list) for a
  miss and **403** for a hit on an already-paired row.

### 9.4 Behaviours that ARE bugs, recorded so a port does not inherit them silently

Each is a **DIVERGENCE** noted in place above. None should be changed without a
decision, because clients may depend on the current shape.

1. `workflow_guard.pb.js:196` — an **unparseable** `lease_until` reads as *not
   expired* (`NaN <= now` is false), contradicting the comment two lines up.
   `evidence.pb.js:129` gets the same idiom right with an explicit `isNaN`.
   Same at `:653` for the running-lease check.
2. `workflow_guard.pb.js:105-112` — `stateForStatus` is an object-as-set, so
   `status="constructor"` takes a different path from every other unknown status
   (a 500 rather than a 409), in a file that argues three separate times against
   exactly this.
3. `captcha_solve.pb.js:40, 140` — agent token minimum 20, where every other call
   site uses 40.
4. `internal_hq.pb.js` — Pattern C routes do **not** check `actor.active`; Pattern
   B routes do. Seven routes differ.
5. `internal_hq.pb.js:3146-3198` — `POST /internal/passwords/delete` has no
   creator-or-admin rule and no vault-key check, unlike every other delete route.
6. `internal_hq.pb.js:3087-3144` — `passwords/reveal` has no admin gate, no rate
   limit and writes no activity row.
7. `internal_hq.pb.js:3385-3451` — a Clerk sign-in writes no `person.signin`
   activity row, so it is invisible in the feed where a code sign-in is not.
8. `internal_hq.pb.js:1179-1234` — event deletion writes no activity row.
9. `internal_hq.pb.js:4178-4187` — `perm_assign` and `perm_delete` are stored,
   reported by two routes, and enforced nowhere.
10. `internal_hq.pb.js:2246-2251` vs `:2369-2372` — Pass A ignores
    `email_on`/`sms_on`; Pass C honours them.
11. `internal_hq.pb.js:2164-2183` — the HQ cron's SMS uses the account auth token
    while `password_reset.pb.js:110-118` prefers the scoped API key.
12. `sms.pb.js:244-250` — the duplicate check is correct only by accident of
    statement ordering around a throwing lookup.
13. `guard.pb.js:37` — the service-token comparison is `===`, not timing-safe,
    where the HQ file uses `$security.equal` throughout.
14. `guard.pb.js:491` — a non-numeric `perPage` yields `NaN`, and `NaN > 50` is
    false, so it passes the cap check.

### 9.5 The five things that must be true on cutover day

1. `ANTICIPY_SERVICE_TOKEN` is set on the new backend **before** any client points
   at it. Unset means the whole database is public.
2. `ANTICIPY_INTERNAL_KEY` is set, or every HQ route answers 503 and the team
   dashboard is dark. (This is the safe direction, but it is still an outage.)
3. `TWILIO_AUTH_TOKEN` is present — inbound SMS is HMAC-verified with the account
   auth token and nothing else. Without it the product looks simply deaf.
4. `ANTICIPY_VAULT_KEY` is exactly 32 characters and is **the same value**, or
   every stored vault secret is unreadable.
5. Existing PocketBase auth tokens still verify, or every iPhone is signed out.

---

## §10. THE CONFORMANCE SUITE

`migration/spec/contract_tests.py`. Pytest, standard library only (no `requests`),
parameterised over environment variables so the identical file runs against
PocketBase and against the Worker.

```bash
# against the live backend
BASE_URL=https://backend-production-61e0a.up.railway.app \
  python3 -m pytest migration/spec/contract_tests.py -v -m "not destructive" \
  --junitxml=/tmp/pocketbase.xml

# against the port
BASE_URL=https://api.anticipy.workers.dev \
  python3 -m pytest migration/spec/contract_tests.py -v -m "not destructive" \
  --junitxml=/tmp/worker.xml

diff <(grep -o 'name="[^"]*"' /tmp/pocketbase.xml) \
     <(grep -o 'name="[^"]*"' /tmp/worker.xml)
```

Environment variables it reads (all optional except `BASE_URL`; a missing one
**skips** the tests that need it, with a message naming the variable):

| variable | unlocks |
|---|---|
| `BASE_URL` | everything — without it every test skips |
| `ANTICIPY_SERVICE_TOKEN` | the guard's token rung, `/worker/owners`, `/evidence/share`, `/admin/purge-audit`, `/agent/upgrade-credential` |
| `ANTICIPY_INTERNAL_KEY` | every keyed HQ route |
| `ANTICIPY_TEST_OWNER_EMAIL` + `ANTICIPY_TEST_OWNER_PASSWORD` | the account-token rungs |
| `ANTICIPY_TEST_AGENT_ID` + `ANTICIPY_TEST_AGENT_TOKEN` | the per-agent rungs |
| `ANTICIPY_TEST_ACTOR_ID` | HQ routes that need a resolvable person |
| `ANTICIPY_TEST_ADMIN_ACTOR_ID` | HQ admin routes |
| `ANTICIPY_TEST_JOB_ID` | the workflow-guard PATCH legs |
| `ANTICIPY_ALLOW_DESTRUCTIVE=1` | plus `-m destructive` |

Markers are registered by `migration/spec/conftest.py`, which is kept out of the
repo-root `pytest.ini` on purpose: that file sets `testpaths = tests` for the
product suite, while this one is pointed at a `BASE_URL` rather than at this
checkout. The markers are `destructive` (writes or deletes real rows),
`anonymous` (needs no credential at all — the zero-secret baseline that must
still pass the morning after cutover), `slow` (spends a rate-limit budget),
`offline` (reads CONTRACT.md and nothing else), `guard_on`, and the four
`needs_*` credential markers.

The **`anonymous`** subset is the one to run first against anything new. It
contains the fail-open alarm: an anonymous `GET` of `events`, `owners`, `jobs`,
`owner_profile` and `internal_passwords` must be refused and must return no
`items`, because every non-HQ collection rule is `""` — which in PocketBase
means PUBLIC, not closed. One missing environment variable turns the whole
database world-readable, and a migration is precisely the moment an environment
variable goes missing.

**What the suite deliberately cannot assert**, so it does not pretend to:
* `guard.pb.js`'s fail-open — that needs an instance with no service token.
* The two crons — they are exercised by `test_cron_contract_is_documented`, which
  only checks that this document and the schedule agree.
* Outbound Twilio/Resend/OpenRouter/CapSolver behaviour.
* `/me/delete`, which is irreversible and is `destructive` + skipped by default
  even then.

**Verified while writing this**: the suite collects 189 tests; with no
`BASE_URL` set, 183 skip and the 6 `offline` document-agreement tests pass;
against a deliberately contract-faithful stub backend, all 69 tests that need
no credential pass and the rest skip. That proves the suite is internally
consistent and that a compliant implementation can satisfy it. It does **not**
prove any assertion matches the real PocketBase — that is what the first run
against the live backend is for, and any test that fails there is a line in
this document to correct, not a test to delete.

---

## Unverified

Everything below is a claim I could **not** confirm by reading the tree. Each
one is a question to settle against the running instance before relying on this
document.

**PocketBase runtime semantics (no PocketBase 0.30.4 was available to run):**

1. **Hook load order.** §0.4 asserts `pb_hooks/*.pb.js` is globbed
   lexicographically, which makes `evidence → guard → internal_hq → owner_profile_owner
   → research_lane → workflow_guard` the middleware order. I inferred this from
   Go's `filepath.Glob` returning sorted names; I did not verify PocketBase uses
   `Glob` rather than a directory walk. **If the order differs, several status
   codes in this document are wrong** — a request refused by the guard would
   surface as a 409 rather than a 403.
2. **`e.app.store()` lifetime and scope.** The source claims (`guard.pb.js:93-99`)
   it is shared across isolated hook runtimes and survives between requests,
   "measured on 0.30.4 against a local rig". I did not re-measure. Whether it
   survives a worker-pool rotation, and whether it is per-process or per-instance,
   decides whether the pair-code ceiling is real today.
3. **`e.requestInfo()` caching.** The session door (`internal_hq.pb.js:346-347,
   366`) mutates `body.actor_id` and relies on later `e.requestInfo()` calls
   returning the same object. If it re-parses, **every Pattern C route silently
   falls back to client-asserted identity while still returning 200** — which is
   exactly the impersonation the block exists to prevent. This is the single
   highest-value thing on this list to verify.
4. **`e.request.header.set()`** actually mutating the header the same handler
   later reads (`internal_hq.pb.js:367`). Same failure mode as (3).
5. **`e.request.url.rawQuery` assignment** (`research_lane.pb.js:443`) taking
   effect for PocketBase's own downstream query parsing. If it does not, the lane
   filter rewrite is decorative and only the claim-write refusal holds.
6. **`findFirstRecordByFilter` throws on no match** rather than returning null.
   Several routes depend on this (`sms.pb.js:244-250` correctly, others by
   catching). I inferred it from the pervasive try/catch idiom, not from the API.
7. **`e.auth` is populated for `_superusers`.** Asserted three times in the source
   (`guard.pb.js:383-386`, `account_delete.pb.js:85-88`, `evidence.pb.js:112-115`)
   with a specific reproduction, but not re-verified.
8. **`$security.encrypt`'s exact algorithm and output encoding.** §9.2 says
   AES-GCM; I did not confirm mode, IV placement or encoding. Migrating vault
   ciphertext without this is data loss.
9. **`e.blob`, `e.html`, `e.string` header behaviour** — whether they override an
   explicitly set `Content-Type`.
10. **PocketBase's own error bodies** for a 404 record, a failed `createRule`, and
    a validation error. §0.5 quotes the shape from memory of PocketBase's format;
    the conformance suite therefore asserts only status codes on those paths.

**Cloudflare platform (I did not consult current docs and will not guess):**

11. **Subrequest limit per Worker invocation.** The 5-minute HQ sweep can issue
    ~50 outbound HTTP calls in one run. Whether that fits in one Cron Trigger
    invocation is unverified and decides whether the sweep needs fanning out.
12. **Cron Trigger minimum interval** and whether `*/5 * * * *` is accepted
    verbatim.
13. **D1 transaction semantics** — §9.2 asserts batch-only, no interactive
    transactions. Verify before rewriting `phone_remove` and
    `owner_profile_upsert`, both of which currently prove their work *inside* the
    transaction.
14. **Durable Object consistency guarantees** for the pair-code and HQ-login
    ceilings. I assert DOs are the right home; I did not verify the consistency
    model against what a counting ceiling needs.
15. **R2 + Worker request URL shape** for `/api/files/evidence/{id}/{filename}`.
    The URL must be byte-identical because Twilio fetches it.
16. **Whether Workers can verify PocketBase's existing auth tokens** without
    re-issuing them. If not, cutover signs every user out.

**Facts about this tree I asserted from a single reading:**

17. The route/middleware/cron counts (55 / 6 / 2) come from `grep` over
    `backend/pb_hooks/*.js` and match the brief. The **4** model hooks
    (`onRecordCreate`, `onRecordUpdate`, two `onRecordAfterCreateSuccess`) were
    not in the brief's count and may be counted differently elsewhere.
18. The brief said `workflow_guard.pb.js` has **22** `reject()` reasons. I count
    **29** `return reject(...)` call sites yielding **42** distinct refusal
    strings (25 literal/template + 2 approval + 15 Shelf 2). §1.16 lists all 42.
    Either the brief counted only the non-Shelf-2 literals (25) or a different
    grouping; the enumeration in §1.16 is what the tests assert.
19. Client-side claims — that `brain/pb.py` sends `X-Anticipy-Worker` on every
    request, that `extension/background.js` never sends the service token, that
    `AnticipyBackend.swift:144` carries the account token alone — are quoted from
    the hook comments. I read the hooks, not the clients. If the port changes
    what a client sends, these become false without anything going red.
20. `GET /api/health` and `GET /_/` are asserted from PocketBase's documented
    behaviour, not from anything in this tree — no hook registers either.
21. `pb_public/internal.html` is described as a 136 KB HQ SPA; I did not open it.
    `GET /fellows/hq`'s 200-byte / `<!doctype` sanity check is the only thing this
    document says about its contents.
22. Whether any migration after `1700000055` exists on the live instance but not
    in this tree. The document describes the schema as the migrations define it.

**Deliberately not asserted:**

23. Whether any of the DIVERGENCEs in §9.4 is currently being exploited, or
    whether any is load-bearing for a client. Each is recorded as a fact about
    the code and a decision for a human, not as a recommendation.
24. Timing. Nothing in this document says how fast any route is, and the
    conformance suite asserts no latency.
