# SHELF 2 — the law that makes an act admissible, built

Date: 2026-08-25
Branch: `jose_anticipy_system`
Commit: `5f66016c`
Spec: `docs/superpowers/specs/2026-08-24-shelf-2-redesign.md` (`2f5bdd64`)
Card: SHELF 2 — act-and-tell with one-tap undo (Omar's ruling, 2026-08-24)

Files touched, and nothing else:

- `brain/workflow.py`
- `backend/pb_hooks/workflow_guard.pb.js`
- `tests/test_shelf2_admissible.py` (new, 39 tests)
- `tests/test_shelf2_guard_leg.py` (new, 46 tests)

---

## 1. What was built, in one sentence

The two-sided admissible test — **an act is admissible only when undoing it
requires nothing the act produced, AND its declared reach is persisted on the
row and bound to its admitted act type** — implemented in Python as a
transition floor and in the database guard as the leg that is the price of the
new `consequence` value.

**There is no reversibility classifier.** Not a word list, not a domain list,
not a threshold, and not a model call returning a bit. §5.1's finding is that
the classifier is the wrong object, and this build takes it literally.

## 2. The shape, and why each piece is the shape it is

### 2.1 The meaning question goes to a model; the release decision does not

The model is asked for an **artifact** — *"what exactly would undo this, step
by step?"* — and the artifact is checked mechanically. Nothing in this build
asks whether an act is reversible, how confident anything is, or what a
sentence meant.

### 2.2 The undo side: resolution, never names (§5.2)

`UndoPlan` carries a closed, typed input list. Each `UndoInput` is
`(name, provenance, ref)`; `held` is the values we already have, bucketed by
provenance. `_resolves()` reads **`provenance` and `ref` only** and refuses on:

- an unrecognised provenance tag (the vocabulary is closed at three:
  `minted_by_us` / `owner_supplied` / `constant`),
- a bucket that is not a mapping,
- a reference the bucket does not hold,
- a reference that resolves to nothing.

`name` is stored for a human and **nothing branches on it**. `steps` is stored
and **never parsed**.

The proof that this is a seatbelt and not a word list is a matched pair of
tests, in both layers:

| input | outcome |
|---|---|
| a field named `owner_supplied_reference` that does **not** resolve | REFUSED |
| a field named `{{confirmation_number}}` that **does** resolve | ADMITTED |

Any implementation that scanned for `{{…}}`, `${`, `<…>` or the word
"confirmation" fails one of those two. An implementation that reads names
fails both. §5.2 names this defeat explicitly — *"trivially defeated by a model
that names a field `owner_supplied_reference` and fills it from the
response"* — and it is why the representation was part of the requirement.

**What resolution actually buys, stated so nobody over-claims it.** The check
runs at the `queued` transition, which is *before the act runs*. So a reference
that could only be filled by the counterparty's response cannot resolve, and
that is the mechanical content of "known-good before acting". It does **not**
prove the value is real — a model can write a plausible fiction, which is
§8.4's stated residual, contained by the admitted set not being the model's to
widen.

### 2.3 The act side: the label attack (§5.4)

The §5.4 attack arrives **with a flawless undo plan**: declare
`act_type: local_draft`, mint your own uuid, write a provenance-clean undo of
`DELETE /drafts/{id}`, and create the Gmail draft §6.1 excludes by name. Every
check the first revision of the spec specified is a check on the undo, and the
undo is impeccable.

So `Plan` now carries `ActDeclaration(act_type, reach, executor)`, **persisted**
into `params._workflow` and re-checked by the database. The admitted set
records the reach and executor each act type is permitted, and a plan whose
declaration disagrees is refused **before its undo plan is read**. Both layers
have a test asserting that ordering by the *reason returned*, not merely by the
rejection — a row with a wrong reach and a broken undo must name the reach.

`touches` could not supply this. §9 is right: it is a Python call argument with
a lifetime of one decision, it is not on `Plan`, not a column, and the string
does not appear in `backend/`, `extension/` or `app/ios/`.

**Reach vocabulary.** A separate, act-type-scoped vocabulary (`local_store`)
rather than `touches`'s compute/read/world, which §9 leaves open. None of those
three is honest about a write that never leaves our own store: not a read, not
compute, and calling it "world" would put it on Shelf 3.

### 2.4 The admitted set is a floor with one member (§6.1, §10.3)

`ADMITTED_ACT_TYPES` holds exactly `local_draft`, recording reach, executor,
the provenances its undo must bind, and its evidence — which currently says in
so many words that §10.1 conditions 2, 3 and 5 are **unmet**. A test asserts
the set has one member, and another compares the Python constant against the
guard's, because §6.4 licenses a constant only while a reader can check it in a
single diff.

### 2.5 The §8.5 guard leg — the highest-risk item, and the trap

A third `consequence` value now fails **closed** at the database. The cheapest
way past that rejection is one list literal:

```js
const NO_APPROVAL_NEEDED = ["read_only", "reversible_local"];   // NOT DONE
```

It reads as compliance with §8.5 and it turns off the only database-level
backstop for the new lane. `read_only`'s exemption is *earned* by
`extension/background.js: runSupervisedReadJob`, which fails any job whose
consequence is not `read_only` outright. Shelf 2 would inherit the exemption
and none of the backstop.

**So the exemption is not spelled anywhere.** `NO_APPROVAL_NEEDED` still reads
`["read_only"]`. The Shelf 2 value earns its exemption by passing every leg,
and it is written that way round on purpose: **delete the leg and the lane goes
back to demanding approval**, rather than quietly running unattended. A naked
allowlist entry fails the other way. Two tests hold this: a source check that
the shelf-2 value is not in the array, and a mutation that adds it (killed).

Legs, in the order they run:

| leg | refusal cause |
|---|---|
| act declaration present and in the admitted set | `shelf2.act_type_not_admitted` |
| declared reach equals the admitted reach | `shelf2.reach_disagrees` |
| declared executor equals the admitted executor | `shelf2.executor_disagrees` |
| undo plan present, an object, with steps | `shelf2.no_undo_plan` |
| undo addresses this act type | `shelf2.undo_addresses_another_act` |
| every provenance tag recognised | `shelf2.unknown_provenance` |
| every reference resolves | `shelf2.unresolved_reference` |
| the undo binds what this act type needs | `shelf2.undo_binds_nothing` |
| announcement obligation on the row | `shelf2.no_announce_obligation` |
| the tell is addressed to the owner | `shelf2.announce_leaves_the_owner` |
| the act has a lineage position | `shelf2.unordered_lineage` |
| the lineage can be read at all | `shelf2.lineage_unreadable` |
| nothing later in the lineage has run | `shelf2.superseded_by_later_act` |

Every cause is an enumerated `Refusal` member, never free text (§11), and a
test asserts the database can name every cause Python can produce.

**The JSVM prototype hazard, applied everywhere and not just where the file
already warned about it.** The admitted set, the provenance vocabulary, the
gesture kinds and the ran-statuses are all **arrays with `indexOf`**, and every
map lookup goes through `Object.prototype.hasOwnProperty.call`. Tests drive
`constructor`, `toString`, `valueOf`, `hasOwnProperty` and `__proto__` through
the act type, the provenance tag and the reference, and they assert the
**cause**, not merely the rejection — because a rejection from some other leg
downstream would otherwise hide a lookup that reads a prototype. Two mutations
in this build survived until those assertions were tightened.

### 2.6 LIFO within a lineage (§7.4)

`compensation_is_current()` in Python, and an `orderRefusal()` leg in the guard
keyed on **`undo_of` being present, not on the consequence** — a compensating
plan carries the owner's own gesture as authority (§8.6), so it is ordinary
approved work, and a leg keyed on the Shelf 2 consequence would never fire on
the one row it exists for.

The guard queries the lineage, locates the act being compensated, refuses if it
is absent or not where the plan says it is, and then refuses if any later act
has run. `running`, `needs_user`, `done` and `failed` all count as having run:
a failed successor is exactly the case nobody can be sure about.

**Floor polarity throughout**, and with the two failures kept apart:
`shelf2.lineage_unreadable` (the query threw, answered with a non-list, or a
row would not parse) is a different cause from `shelf2.unordered_lineage` (the
undo has no position, or names an act that is not there). §10.5(a) is emphatic
that our own store blinking must not read as a counterparty refusal — *"one
outage on a Tuesday kills the shelf permanently"* — and §11 counts by cause.

### 2.7 §7.3's seam, in the two places I own

A tap is a gesture, not wording. `Approval` now carries an optional `Gesture`,
and `approve_by_gesture()` is a second door that demands **binding** where
`approve()` demands words: an authenticated actor, a `kind` from a closed set,
and the same plan id, version and scope digest words would have been bound to.
A gesture cannot carry `changes` — a tap has no content, so it cannot supply a
fact.

The guard accepts a bound gesture in place of `owner_words`. This is a
**widening of the final authority**, so it is tested against every way it could
become a hole: a gesture bound to another version, another scope, another plan;
an unauthenticated one; an unrecognised kind; one that is not an object; and
**an approval with neither words nor a gesture, which is still refused**. The
existing `an executor cannot rewrite or approve its plan` refusal still covers
an agent caller minting one.

`approve()` still raises on empty words. The speech path did not get cheaper.

### 2.8 Nothing raises, and the refused work is not stranded

`assert_valid()` grew **no new rule**. §3's surviving rule binds: a law that can
be false for a legitimately stored row makes that row unparseable forever, and
the scar above `_consequence_or_safe` is twelve lines about exactly that.

So: every Shelf 2 sub-object parses **tolerantly** (`from_dict` returns `None`
for anything malformed and never throws), and the law lives in the transition
functions — `_shelf2_lane()`, applied in `new_plan`, `merge` and
`recover_expired`. Refused work goes to `AWAITING_APPROVAL` carrying its
enumerated reason, which is §5.2's *"the work goes to Shelf 3 and waits for a
tap"* — and a test proves he can then tap and it runs.

## 3. Two real holes found by attacking my own work (Law 6)

Both were found by mutating a fix out and watching **nothing fail**, not by
reading the spec.

**(a) `merge()` promoted refused work into the unattended lane.** `merge`
recomputes the next state from the consequence alone, so an act refused at mint
— no undo plan, a reach that disagrees, anything — was handed the lane that
runs without a tap by an ordinary amendment it had nothing to do with. A
correction to the goal is not a safety finding. `recover_expired` was the same
door: a row that lost its undo evidence between attempts was recovered straight
back into the lane. Both now re-run the floor.

**(b) An undo plan that binds nothing passed vacuously.** `_resolves` iterates
the inputs, so an undo plan with **no inputs at all** satisfies it trivially:
"delete the draft row whose id we minted" with no id bound. Every other leg
waved it through. Fixed by recording, per act type in the admitted set, the
provenances its undo must bind — `local_draft` must bind a `minted_by_us`
reference, which is §6.1's client-minted id.

## 4. Evidence

| | |
|---|---|
| Suite before | 1824 passed, 0 failed (`--ignore=tests/test_day_zero_oracle.py`, which cannot collect: `playwright` is not installed — pre-existing) |
| Suite after | 1973 passed, 0 failed |
| Mine | 85 tests (39 + 46) |
| Mutations, Python | 21 applied, **0 survivors** |
| Mutations, guard | 26 applied, **0 survivors** |

The delta is larger than 85 because other agents committed into this tree while
I worked.

**At the exact moment of commit** the suite showed **1 failed, 1972 passed** —
`tests/test_research_shape_parity.py`, another agent mid-edit on
`brain/research.py`, a file I do not own. A re-run immediately after shows 1973
passed, 0 failed. Reported rather than rounded.

The mutation batteries are in the scratchpad
(`.../shelf2jose/mutate.py`, `mutate_js.py`) and are not committed; both restore
from a backup after each mutation and read the exit code of the command.

Gates, unchanged by this work: `tape_gate` RED (by design, Law 2 —
I introduced no tape), `tejas_gate` first failing leg 6 (the speaker engine is
not linked), `done_gate` first failing leg 6 (a stranger). None of them moved.

## 5. NOT PROVEN — read this before believing anything above

**Nothing here has been verified against LIVE (Law 3).** The ears are dead:
zero transcript rows have reached production in ~31 hours and builds 76–80
delivered none. `railway up` reports success while failing, and `afd4380a`
being in the repo is not evidence it is in prod. Every claim in this document
is a claim about the repo.

**Nothing mints a `reversible_local` plan today.** `brain/anticipy_core.py`
does not pass `act`, `undo`, `announce` or `lineage_seq` to `new_plan`, and it
is not my file. The lane exists, the law is enforced at both layers, and **no
production path reaches it**. That is §6.4's sequencing followed on purpose —
the guard leg, the persisted reach and the seam go *in front* of the first
admission because they are wrong today whether or not this shelf ever ships —
but it means the shelf does not act yet, and saying otherwise would be false.

**§10.1's conditions 2, 3 and 5 are unmet**, and the admitted set's own
evidence field says so. There are zero live end-to-end undos, no adversarial
silent-failure probe, and the announcement obligation is a *record* here but
has no delivery, retry or clearing mechanism anywhere. Per §8.3, **no act type
may be admitted until that mechanism exists — including day one's.**

**§8.7's residual stands untouched.** Nothing checks the *steps*. A plan that
declares the right reach and whose steps go elsewhere is caught by nothing here,
and no mechanical check of steps is proposed, because a check over URLs or step
text would be the word list this whole card refuses.

**Resolution proves presence, not truth.** See §2.2. A model that writes a
plausible fiction is §8.4's residual and it is not closed.

**The guard's lineage query is unverified against a real PocketBase.** The call
shape follows `claim_legacy.pb.js` and `password_reset.pb.js`, but it has never
run against a live JSVM. A wrong shape throws, which the leg catches and turns
into `shelf2.lineage_unreadable` — it fails closed, so the risk is an undo that
always refuses, not one that wrongly runs. **This is the first thing to check
after a deploy.**

**The LIFO leg runs at the `queued` transition only**, not at `running`. An act
that completes between a compensating plan being queued and being claimed is
not caught. Closing it costs a lineage query on every claim; that is a decision
somebody should make deliberately.

**The Shelf 2 fields live only in `params._workflow`, not in dedicated
columns.** The guard's row-vs-embedded redundancy check therefore does not
cover them. That is not a hole in the same sense (there is only one copy, so
nothing can disagree), but it is a missing defence-in-depth, and closing it
needs a migration I do not own.

## 6. Handed to whoever owns the other files

**`app/ios/` — the undo button is explicitly out of my scope; here is what it
needs.**

1. `approvalFields(for:)` must **not** put a synthetic string in
   `owner_words`. *"tapped undo"* is one line of Swift away at all times, and
   it would put a sentence he never said into the one field whose entire
   purpose is that he did. It must build the `gesture` object instead:
   `{kind: "tap", actor: <authenticated owner id>, plan_id, plan_version,
   scope_digest, made_at}`. Both Python and the database now accept exactly
   that shape and refuse every mis-bound variant.
2. `reconciliation.owner_words` is the fourth site (§7.3) and is minted in the
   same Swift function. Any gesture representation has to answer for it too.
   **I did not change that leg**, so it still demands words.
3. A typed reply of "undo" **is** words and should keep using `approve()`
   honestly. The two must not be stored as the same thing.
4. The tap writes an **event**, not a plan (§7.2.1). The brain mints the
   compensating plan.

**The executor — this is the one that matters most.** §8.7's containment is
that day one's act type *runs against our own store through our own code path*.
Nothing in my files can enforce that: the plan merely *declares*
`executor: anticipy_store`. The worker needs the mirror of
`runSupervisedReadJob`: **refuse any job whose `consequence` is
`reversible_local` unless it is being run through the local-store path, never
handed to a browser session.** Without it the executor declaration is a label
on a process that can do anything the session can do.

**`brain/anticipy_core.py`** (not mine):
- `_pending_class()` returns `stored == "consequential"`, so Shelf 2 work would
  dedupe against read-only work — the 2026-08-04 scar in that function's own
  docstring pointed at a new lane. It needs its own partition, not a boolean.
- Whoever wires the lane must supply `act`, `undo`, `announce` and a
  `lineage_seq` that is genuinely `1 + max(seq in lineage)`.

**Stage 1's `undo()` does not exist in `brain/workflow.py`.** The spec says it
"survives untouched and this spec assumes it"; it is not built. I deliberately
did **not** build it to the plan's written form, because that form calls
`approve(fresh, owner_words=owner_words)` with a synthesised
`"tapped undo on …"` string — which is precisely the §7.3 seam defect. Whoever
builds it should use `approve_by_gesture()` and set `undo_of` so the LIFO leg
fires.

**Not built, on purpose (§6.4's sequencing note):** `overnight/shelf2_gate.py`,
the admitted set as repo data carrying committed receipts, and the live-undo
evidence pipeline. All three belong **behind** the first admission; building an
evidence pipeline for a set of one, where the one is a row in our own database,
is machinery for a decision nobody is making yet. **All three are required
before the second admission.**

**Still open from the spec, untouched here:** `terminalReceiptEvidence` (§2.1)
is a page-prose regex deciding that an external effect occurred, and it is a
Law 1 violation that exists today. This build does not rely on it and does not
cite it as precedent. §10.1 condition 6 makes its repair a precondition of the
first admission whose effect leaves our store; §13.5 hands the choice of repair
back to Omar.

## 7. Law compliance

- **Law 1.** No regex, word list or threshold decides meaning. The checker
  resolves typed, provenance-tagged references and never inspects a field name
  or parses prose; the act-side check compares two stored values. The closed
  vocabularies (`Provenance`, `ADMITTED_ACT_TYPES`, `GESTURE_KINDS`,
  `HAS_RUN`) are structure and can only refuse, which is the seatbelt
  exemption. §2.1's existing violation is named, not extended.
- **Law 2.** **No tape shipped.** No `TAPE:` comment was added, no registry
  entry, no ledger line — because none was needed.
- **Law 3.** Not satisfied and not claimed. §5 above says so plainly.
- **Law 4.** This file, committed the day the work was done.
- **Law 5.** This is structure (step 5) and it is seatbelt-shaped. It is not a
  rule written while she is deaf: it examines what a plan touches and what its
  undo depends on, never what his words meant.
- **Law 6.** Self-reviewed to convergence: 47 mutations, two real holes found
  and closed, four weak tests strengthened after they failed to kill a
  mutation. The residuals in §5 are stated rather than papered over.
