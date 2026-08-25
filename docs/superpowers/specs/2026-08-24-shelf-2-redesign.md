# SHELF 2 — act-and-tell with one-tap undo — redesign

> Status: SPEC, second revision. Not a plan, not a sequence, no code. Somebody
> else sequences it.
> Supersedes the struck Stage 2 of `docs/superpowers/plans/2026-08-25-shelf-2-undo.md`.
> Stage 1 of that plan (undo as a compensating plan, moment #28) survives
> untouched and this spec assumes it.
>
> Card: SHELF 2, Omar's ruling of 2026-08-24, three shelves.
> Brief: `docs/BRIEF.html` moments 25, 26, 27, 28, 30, 31, 48, 49.
> Laws: `HARNESS-LAWS.md` (1, 2, 3, 4, 6 all bind here).
> Jose's assigned part: review the reversibility classifier. §5 is that review,
> and its finding is that the classifier is the wrong object.
>
> **Revision note (Law 4).** The first revision (`9dc712a4`) survived an
> adversarial pass with "build it with changes": four Criticals, seven
> Importants, one missing sentence. This revision answers them. What changed,
> in one line each: the admissible test is now **two-sided** (§5.4); the
> headline rule is demoted from *the rule* to *the entry condition* (§4, §8.2);
> **narration leaves Shelf 2** and is re-filed as a Shelf-1 change (§6.2);
> `terminalReceiptEvidence` is **carved out** of §2's non-goal as a defect
> (§2); §5.2 now states the **representation** of an undo plan's inputs; §8.5
> is rewritten against a guard that has since been half-fixed, and the trap
> that creates is the first thing it says. Nothing on the survived list was
> weakened to make any of that easier.
>
> **Citation convention (Law 4, and because line numbers rot within hours in
> this tree).** Every code citation in this file is `path: symbol @ commit`.
> Where the enclosing symbol is anonymous — `workflow_guard.pb.js` is one
> `routerUse` callback — the anchor is a unique identifier or reject string
> from that file, which is greppable and stable in a way a line number is not.
> All citations below were re-verified at **`e5b14c3e`**. The first revision
> used `file:line`; several had already rotted, and two were wrong at its own
> commit (`anticipy_core.py:587` named the `touches` branch, not the deny-list
> return it was cited for; `agent_loop.js:1721-1726` was off by one at both
> ends). This convention exists because of that, not in spite of it.

---

## 1. Goal

Give the owner a middle shelf: work that runs **without waiting for a tap**,
and is **reported afterwards with a real undo**. Shelf 1 (math, lookups) runs
silently. Shelf 3 (money, messages to other humans, deletes) taps first,
forever. Shelf 2 is the register in between, and today there is nothing in it —
`Consequence` has exactly two values (`brain/workflow.py: Consequence @ e5b14c3e`).

The card's own safety claim is the thing to preserve, verbatim: **the plan
carries its own undo recipe *before* acting.** Everything below is an attempt
to make that sentence literally true rather than decoratively true.

## 2. Non-goals

- **No change to Shelf 3.** Money, messages to other humans, deletes: tap
  first. No reversibility finding, no receipt, no host history, no owner
  impatience overrides this. It is not a default, it is a wall.
- **No modification of `is_consequential()`** for the hold/run split of
  existing work. This spec adds a third destination; it does not move anything
  that is held today into a lane that runs.
- **No reversibility classifier.** See §5. This is a non-goal on purpose.
- **Not a plan.** No tasks, no ordering, no estimates.
- **No new verification vocabulary — with one carve-out, and the carve-out is
  a defect, not a preference.**

### 2.1 The carve-out: `terminalReceiptEvidence` is testimony releasing

The first revision listed the existing receipt vocabulary as reusable and
named `terminalReceiptEvidence` approvingly, as work that *"already accepts
'successfully cancelled' plus a reference as terminal first-party proof."*
**Read again against the code, it is neither terminal nor first-party, and
this spec must not stand on it.**

`extension/agent_loop.js: terminalReceiptEvidence @ e5b14c3e` builds
`` `${state?.title}\n${state?.text}` `` — **the page** — and returns true when
two regexes both match that string: a success phrase
(`successfully cancelled|…|booking … confirmed`) and a reference-number shape
(`confirmation|reference|receipt|… [:#-] X4J-9021`). Its caller,
`extension/agent_loop.js: verifyDone @ e5b14c3e`, then does this:

```js
if (effectState && terminalReceiptEvidence(state)) {
  return { verified: true, reason: "", evidence: verificationEvidence(
    state, facts, "terminal-receipt+approved-pre-effect-fields") };
}
```

It returns `{ verified: true }` **outright, before the LLM verifier is asked
anything**. The receipt is then stamped verified, and the database's `done`
leg (`backend/pb_hooks/workflow_guard.pb.js: reject("done needs verified
evidence for this exact effect") @ e5b14c3e`) accepts it, because that leg
checks the flag and never its provenance.

So a page that prints *"Successfully cancelled — confirmation number:
X4J-9021"* and cancels nothing produces a verified receipt and a `done`
transition. **In this spec's own vocabulary that is testimony releasing**
(§4), and mechanically it is a page-prose regex deciding that an external
effect occurred — a plain Law 1 violation, of exactly the shape the
2026-08-24 audit was counting.

**When it bites.** Not on day one: day one's admitted act never leaves our
store, nothing runs `verifyDone` for it, and the receipt is our own row. It
bites **the moment §10.4 opens a door onto a third-party system**, because
§4.1's first consequence says the release and the proof have a single root — and
this is the proof half rotting while the release half is being carefully
built. A shelf whose release mechanism is airtight and whose proof mechanism
accepts page prose has moved the hole, not closed it.

**Therefore:** carved out of the non-goal. `terminalReceiptEvidence` is not
reused by this spec, is not cited as precedent by it, and its repair is a
**precondition of the first non-local admission** (§10.1, new condition 6).
The shape of the repair is not this spec's to choose and is handed back in
§13.5, because the two candidate repairs cost the owner different things.

## 3. What was killed, and why it stays killed

Three independent adversarial passes struck the original design before a line
of code. Recorded here so nobody rebuilds it (Law 4).

**The dead premise, verbatim from the plan that carried it:** *"the release is
the executor's possession of a captured undo handle, which is a fact, not a
judgement."*

**It is false.** Every field of that handle is page-authored input. `policy` is
a sentence the site printed. `cancelUrl` is an href the site rendered.
`deadline` is a date the site typed. A site that wants non-refundable bookings
needs only to display the words "free cancellation" to harvest unattended
commits from us. Possession of a string the adversary wrote is not possession
of a capability. This is the same class of mistake as moment 48 — page content
is data, never orders — applied to a field instead of a sentence.

**The concrete failure it produces**, stated so it cannot be argued away as
theoretical:

> A restaurant page displays "Free cancellation up to 24 hours" and renders a
> Cancel link. We book 19:00 Thursday for four without asking, because the
> handle was captured and the handle said reversible. We announce it with an
> Undo tap. He taps at 19:40. The link 404s — or it cancels a different rate
> class, or the reference was never a reference. The table is still held, his
> card is still on file, and the first true thing he hears about any of it is a
> no-show fee. The undo failed **silently**, and the act was irreversible from
> the moment it ran.

That is precisely the one dangerous edge the card names: calling an
irreversible act reversible. The dead design's release mechanism *was* the
dangerous edge.

**The second kill, which also stands:** the design put its central law in
`brain/workflow.py: Plan.assert_valid @ e5b14c3e`. That function runs via
`Plan.from_dict` / `from_params`, which is called unguarded at
`brain/worker.py: release_stranded_research @ e5b14c3e` and
`brain/worker.py: run_research_jobs @ e5b14c3e`, and at
`brain/anticipy_core.py: Anticipy._release_freshest_held`,
`Anticipy._cancel_job` and `Anticipy._merge_into @ e5b14c3e` — verified against
the tree today; the struck plan cited `anticipy_core.py:3572`, and the first
revision of this spec cited `:1172, :2946, :3974`, and all four numbers have
since moved. **The hazard is
unchanged by the drift, which is the argument for citing symbols.** It also
runs inside a bare `except Exception: return None` on the Send path. A stored
SUCCEEDED row that lost its undo evidence would become permanently
unparseable, and the scar block above
`brain/workflow.py: _consequence_or_safe @ e5b14c3e` is twelve lines about
exactly that — one malformed row threw out of `hear()`, the event was marked
error and never retried, *"and nothing was ever said to him about any of it."*

**Rule that survives and binds this spec:** `assert_valid` must never grow a
rule that can be false for a legitimately stored row. A law of this kind
belongs in a TRANSITION guard, mirrored in `backend/pb_hooks/workflow_guard.pb.js`,
or it uses the cautious-coercion shape of
`brain/workflow.py: _state_after_unreadable @ e5b14c3e` — never a raise.

**The successor idea in that plan's postscript is also declined.** It proposed
"proven host": a per-HOST allowlist, a host admitted after one live end-to-end
undo. That is a domain list wearing a receipt. A host is not a stable identity
— the same host serves a different page tomorrow, to a different rate class, in
a different country, behind a different A/B arm — and the thing we would have
proven is that one page once cancelled once. §10 replaces it with admission
keyed on a **capability we hold**, never on a host we visited. §10.1's
condition 2 now applies that same objection to itself.

## 4. The reversibility question, answered

**Question:** what evidence of reversibility can we trust, given that
everything the page tells us is untrusted input?

**Answer:** only evidence that does not describe the outside world at all.

Reversibility asserted *about* an external system is testimony from a party
with an interest in the answer. That is true of the page. It is also true of
the provider's API flag, of the confirmation email, and of the cancellation
policy PDF — all of them are the counterparty telling us what the counterparty
intends to allow, and all of them can be wrong without anybody lying, because a
policy is a statement about the future. **Testimony can never be a release. It
can only ever be a refusal.**

This holds under pressure, which is the reason it survived. A *signed,
timestamped, contractually-backed provider assertion* is the strongest form of
this evidence anyone has proposed, and it does not change category: it raises
the cost of lying and it makes a liar identifiable afterwards, which is
recourse, not release. Recourse is what you have instead of safety once the
harm has landed.

The three directions the card offered, weighed:

| Direction | Verdict |
|---|---|
| **Provider-side confirmation** instead of page-scraped handles | Better, and still testimony. A provider flag is authored by the counterparty under a contract rather than by an arbitrary page, which raises the cost of lying without changing what kind of thing it is. It also drags in a second problem: verifying against the owner's inbox means reading the owner's mail, and tonight's audit already found a word list deciding consent to do that. **Not a day-one release.** Admissible later only as corroboration inside §10's door, never as the release itself. |
| **Prove the undo by doing it** (scratch run) | Converts a claim into evidence, and cannot be a per-act release. For most act types the scratch run *is* the harm — two bookings, two emails, a rate limit, a blacklist — and where it is harmless it proves the wrong thing: that *that* booking was cancellable, not that *this* one will be. Sites vary by rate class, by attempt number, by time of day. **Kept as an admission instrument in §10, never as a runtime check.** |
| **Shelf 2 starts tiny and grows one act-type at a time** | Correct, and this spec takes it. |

**The rule that falls out — and it is the entry condition, not the whole spec:**

> **An act is admissible to Shelf 2 only when undoing it requires nothing the
> act produced.**

If the undo needs a handle, a URL, a reference number, a deadline, a session,
or a record id that the act itself created and the counterparty controls, then
the undo recipe cannot be complete before the act — it contains a hole to be
filled by the party we are defending against. The card asked for a recipe that
is known-good **before** acting. This rule is what that sentence means when
taken literally, and taking it literally is the redesign.

### 4.1 It is necessary and it is not sufficient

The first revision called this rule *"the whole spec"*. That sentence was
wrong, and the demonstration is inside this spec's own requirements rather
than out at the edge of it. §8.2 works it through. The short form:

**An act can satisfy this rule completely and still not be fully reversible.**
The rule constrains what the *undo* depends on. It says nothing about what the
*act* leaves behind that no undo addresses. Day one's act leaves such a
residue — the tell — and the tell is required by §8.3, so the residue is not
an oversight this spec can design away. It is a cost the spec accepts and must
therefore name.

So the rule is the **entry condition**: an act that fails it is refused, full
stop, and no amount of evidence buys it in. What makes an admitted act
*operationally* safe is the entry condition **plus the other four conditions of
§10.1** — live undo evidence, the silent-failure probe, the Shelf 3 wall, and
the durable announcement. Any argument of the form "it passes the structural
test, therefore it is safe to run unattended" is the argument this section
exists to refuse.

Two consequences of the entry condition are worth stating out loud, because
they are the load-bearing half:

1. **The same property makes the undo's receipt trustworthy.** An undo that
   depends on nothing the counterparty authored produces a receipt the
   counterparty did not author either. On day one, where the effect never
   leaves our own store, the undo's evidence is our own row — first-party by
   construction. We are not trusting a stranger's "cancelled successfully"; we
   are reading our own database. The safety of the release and the safety of
   the proof have the same root, which is why this shelf is small: it is small
   exactly where trust runs out. (It is also why §2.1 matters: the existing
   proof path for non-local work reads page prose.)

2. **A captured handle remains necessary and never sufficient.** Its absence is
   still a refusal signal. Its presence is not a release. The asymmetry is
   Law 1's floor/ceiling distinction applied to evidence: a check that can only
   add a hold may lean on anything; a check that releases may lean only on what
   we own.

## 5. The test an act must pass — and why there is no classifier

### 5.1 The review Jose was asked for

The card says: *"review the reversibility classifier — the one dangerous edge
is calling an irreversible act reversible."*

**Finding: do not build a reversibility classifier.** Not as a word list, not
as a domain list, not as a threshold, and — this is the part that is easy to
miss — **not as a model call either.**

A word list or domain list would be the Law 1 violation the 2026-08-24 audit
found 61 times, and the one where a word list decided consent to read the
owner's mail is the same shape. That much is obvious. The less obvious half:
asking a model "is this act reversible?" and releasing on `true` fails for a
different reason. It is a question about the future behaviour of a third party
under conditions nobody has observed, the answer is a single bit, and a wrong
bit in the unsafe direction is unrecoverable and invisible. A bit cannot be
audited. It can only be believed.

### 5.2 What replaces it

**Ask the model for an artifact, and check the artifact mechanically.**

- The **meaning question** — *"what exactly would undo this, step by step?"* —
  goes to the model, with full context, asked on its own. That is a real
  question about the world and it belongs to a model (Law 1), and it follows
  the established shape in this repo: one question asked alone, never a ninth
  key in an existing JSON reply, four states because "no" and "nobody
  answered" are different things. `party_verdict`, `ends_in_the_world`,
  `check_sufficiency` and `work_is_licensed` in `brain/orchestrator.py` are the
  four worked examples.
- The **release decision** is a structural property of what the model wrote,
  not of how confident it was: *does this undo plan contain any field that can
  only be filled from the act's response?* That is a seatbelt check — it
  examines what a plan touches and what it depends on, not how a sentence was
  worded — and it sits squarely in Law 1's seatbelt exemption.

Call it **the pre-written undo test**:

> A stored, complete, executable undo plan exists **before** the act runs, with
> **zero unbound fields**. Every input it needs is already held: minted by us,
> supplied by the owner, or constant. Nothing in it is a placeholder awaiting a
> value the counterparty will return.

**The representation, which the first revision left unstated — and that
omission is what would have produced the Law 1 violation.** "Zero unbound
fields" and "minted by us / supplied by the owner / constant" are the right
enumeration and it is closed. But an enumeration with no stated representation
leaves the implementer exactly one implementable check: look at the field
*names*, or scan the values for placeholder syntax (`{{…}}`, `<…>`,
`${…}`). Both are a word list wearing a different coat, and both are trivially
defeated by a model that names a field `owner_supplied_reference` and fills it
from the response. So the representation is part of the requirement:

> **The undo plan's inputs are a typed, closed list of provenance-tagged
> references — `minted_by_us` / `owner_supplied` / `constant` — each resolvable
> to a stored value at the moment the plan is written. The checker resolves
> every reference and refuses on any that does not resolve. It never inspects a
> field name and never parses prose.**

Three properties of that sentence are load-bearing and none of them are
decoration:

- **Typed and closed.** A fourth provenance tag is a schema change, visible in
  a diff, not a string a model can invent at runtime. An unrecognised tag is a
  refusal, per the floor polarity below.
- **Resolvable at write time.** This is the mechanical form of "before the act
  runs". A reference that resolves only after the act is, by construction, a
  hole the counterparty fills — and the checker discovers this by *trying to
  resolve it and failing*, not by reading what it is called.
- **Never a name, never prose.** This is the clause that keeps the check
  inside Law 1's seatbelt exemption instead of outside it. A checker that
  reads field names is deciding meaning from tokens; a checker that resolves
  references is asking a mechanical question with a mechanical answer.

**Polarity: this is a FLOOR.** No verdict, no undo plan, an unparseable undo
plan, an unrecognised provenance tag, a reference that does not resolve, a dead
model call, a timeout, an empty response — every one of those is the same
answer as "there is money here." Refuse; the work goes to Shelf 3 and waits for
a tap. A floor that lifts on silence lifts itself. The enumeration is closed:
there is no fifth outcome that means "proceed".

**Why this is auditable where a bit is not.** The undo plan is a durable
artifact on the row. It can be read by a human, replayed in a test, diffed
against what actually ran, and mutation-tested. When it is wrong, it is wrong
*in a way somebody can point at*. That is the difference between an eval and a
hope.

### 5.3 What the model is *not* asked

It is not asked whether the act is reversible. It is not asked how confident it
is. It is not asked to rate risk. It is not given a scale. If a future draft
reintroduces any of those, it has reintroduced the bit, and the reason it will
look attractive is that it widens the shelf — which is precisely the incentive
the pre-registration in §10 exists to defuse.

### 5.4 The admissible test is two-sided, and the first revision bound only one side

§5.2 binds **what the undo touches**. Nothing in the first revision bound
**what the act touches**. That is not a gap at the edge of the design; it is a
door in the middle of it.

**The attack does not widen the admitted set. It enters it.**

> A plan declares `act_type: "local_draft"` and a reach of `read`. Its steps
> are: open `mail.google.com`, compose, save as draft. Its undo plan is
> `DELETE /drafts/{id}` where `{id}` is a uuid **we minted before the act ran**
> — tagged `minted_by_us`, resolvable at write time, zero unbound fields,
> provenance-clean. It passes §5.2 outright. It passes the admitted-set check
> outright, because the label it declared is a member of the set. It runs
> unattended. **It creates the Gmail draft §6.1 excludes by name.**

Nothing in the first revision catches this, because every check the first
revision specifies is a check on the *undo*, and the undo is impeccable. The
act is simply not the act it said it was. Note that the attack needs no lying
counterparty and no adversarial page: a model that writes a plausible plan for
a label is sufficient, and §8.4 already concedes that a model can write a
plausible plan.

**And the reach is persisted nowhere.** Verified at `e5b14c3e`:

- `touches` is a field on `brain/orchestrator.py: Decision @ e5b14c3e`, set
  inside `brain/orchestrator.py: Brain.triage @ e5b14c3e`, where a value
  outside `TOUCHES = ("compute", "read", "world")` becomes `None`.
- It is passed as a **call argument**, and only ever that — from
  `brain/anticipy_core.py: Anticipy.hear @ e5b14c3e` down through
  `Anticipy._queue_job`, `Anticipy._same_pending` and
  `Anticipy._refines_pending` into
  `brain/anticipy_core.py: is_consequential @ e5b14c3e`.
- It is **not a field on** `brain/workflow.py: Plan @ e5b14c3e`. That
  dataclass has eighteen fields and none of them is `touches`.
- It is **not a column** on the `jobs` row
  (`backend/pb_migrations/1700000025_job_workflows.js @ e5b14c3e` adds
  `workflow_id, workflow_version, workflow_state, consequence, lineage_key,
  effect_key, scope_digest, approval, receipt, reconciliation, lease_token,
  lease_until, source_event_ids, effect_uncertain` — no reach field).
- The string `touches` **does not appear anywhere** in `backend/`,
  `extension/`, or `app/ios/`.

So it lives for the duration of one Python call and is then gone. §8.5's
proposed positive law has nothing to read: **the guard cannot check a declared
reach that never reached it.**

**The requirement, both sides. An act is admissible only when all three hold:**

1. **Undo side.** Zero unbound fields; every input a typed, provenance-tagged
   reference that resolves at write time (§5.2).
2. **Act side.** The act's **declared reach is bound to its admitted act
   type**. The admitted set (§10.3) records, per act type, the reach that type
   is permitted. A plan claiming that type whose declared reach differs is
   refused — whatever its undo plan says, and before its undo plan is even
   examined.
3. **Persistence, and it is the requirement rather than an implementation
   detail.** The declared reach is written onto the `Plan` and onto the row,
   and is checked at the same transition guard leg as the undo plan (§8.5). A
   check that runs only in the Python that minted the plan is not a check; it
   is a comment. This is the same argument §8.5 makes about the guard and it
   applies here first, because §8.5's leg cannot be written until this field
   exists.

**What this does not do, said plainly, because it is the residual and it is
not small.** Binding the *declared* reach catches a plan whose declaration
disagrees with its type. It does not catch a plan that declares `read`, is
typed `local_draft`, and whose **steps** still open Gmail — because the steps
are the thing nobody has checked, and no mechanical check of steps is
proposed here (one would be a word list over URLs, which is the violation).

That residual is §8.7, and it dictates day one's shape: **day one's admitted
act type must be executed against our own store through our own code path,
never handed to a browser session.** An act type executed by a general browser
agent has no declared reach worth the name — the declaration is a label
attached to a process that can do anything the session can do. This is a
constraint on the *executor*, not on the model, and it is the only form of
this check that is mechanical rather than interpretive.

## 6. What Shelf 2 admits on day one

Applying §4's entry condition and §5.4's two-sided test honestly. This list is
short. Saying so plainly is the point; a small shelf that is honestly safe
beats a wide one that is not.

### 6.1 ADMITTED — one act type: a draft that is a row in our own store

Drafting, held locally. A drafted email, message, or document that lives in our
storage and is shown only to the owner. Nothing left his world. The undo is
"discard our row", written in full before the draft exists, needing nothing but
an id we minted.

This is the whole of the admitted *acting* set on day one. One item.

**The id must be client-minted, and that is a requirement rather than a
convenience.** The precedent is already in the file the plan lives in:
`brain/workflow.py: new_plan @ e5b14c3e` writes `plan_id=plan_id or
str(uuid.uuid4())` — the id exists before anything is stored, so nothing has to
be returned before the undo can be written. The draft id follows that shape
exactly. A draft whose id is assigned by the store on insert cannot have a
`minted_by_us` reference resolved at write time (§5.2), so it fails the test
for a reason that has nothing to do with whether the store is ours: the
provenance is the point, not the ownership.

**Executed by our own code path, never by the browser executor** (§5.4). A
"draft in our store" that reaches the store by driving a page is a browser
session with a label on it.

Note what this excludes, and why the line is where it is: **a draft created in
his Gmail account is not admitted.** The effect left into a third-party system
and the undo needs a message id the provider returned — a hole in the recipe,
filled by the counterparty, after the act. Same act in English, opposite side
of the line. That the same word lands on both sides is the clearest evidence
available that a word list could never have drawn this boundary. And per §5.4,
the exclusion has to be enforced against the *plan's persisted reach*, not
against the string `local_draft`, or the attack in §5.4 walks straight through
it.

### 6.2 NOT A SHELF 2 DELIVERABLE — the narration of Shelf 1 work

The first revision admitted *"the announcement of Shelf 1 work that was
already permitted"* as half of day one, on the grounds that it carries zero new
risk surface. The zero-risk claim is true. **Admitting it here is still wrong,
for three reasons, and it is re-filed as a Shelf-1 change.**

**Reason 1 — it defeats §10.6, which is the only thing that can kill this
shelf.** Narration is the half most likely to move taps-per-week, because it
is the half he can feel. Shipped inside Shelf 2, it makes §10.6's abandonment
test unanswerable: *"the admitted set is still only local drafts and
narration, and taps-per-week has not fallen"* can never be evaluated cleanly,
because narration would be moving the number that the machinery is being
judged by. The machinery survives on a metric the machinery did not move. That
is sunk-cost reasoning with a scoreboard attached, and §10.6 exists precisely
to prevent it. **A pre-registered abandonment test that the shipped bundle can
game is not pre-registered.**

**Reason 2 — as it exists in the tree, narration is model-composed from the
intention, which §7.1's own first wording rule forbids.** The path, verified:

- `brain/anticipy_core.py: Anticipy._voice @ e5b14c3e` calls
  `self.llm.chat(VOICE_SYSTEM, json.dumps(context), temperature=0.7)`.
- The act branch of `brain/anticipy_core.py: Anticipy.hear @ e5b14c3e` calls it
  with `{"situation": "held for approval" if held else "quietly started",
  "heard": line, "goal": decision.goal, "assumption": decision.assumption}`.
  `"heard"` is **raw overheard transcript text**; `"goal"` is **the
  intention**.

So the sentence is composed, at temperature 0.7, from the intention and the
overheard line — the exact thing §7.1's first rule prohibits (*"composed from
the receipt, never from the intention"*), and the reason it prohibits it is
that an announcement generated from the plan is a confident lie waiting for
the first failure.

**The repo has already ruled on this next door, in the same file.**
`brain/anticipy_core.py: Anticipy.meeting_digest @ e5b14c3e` says it in its
own docstring: *"Template on purpose, not `_voice`: a digest's content is goal
strings that already passed the goal-level name guard, and running them back
through a temperature-0.7 composer is how 'Dr. Evans' happened."* An
announcement of completed work is the same object as a digest — a report about
what already happened — and it gets the same answer.

`_voice` does carry a guard: `invented_names(text, context)` discards a
composition containing a name-shaped token absent from the context dict, after
the live incident where it wrote *"meeting with Dr. Evans"* about a goal
naming nobody. That guard catches **a person who does not exist**. It does not
catch **a claim that is not true**, which is the failure mode of an
announcement.

**Reason 3 — the first revision named the wrong object, and there is no branch
to switch on.** It cited `say_handling` as the mechanism that *"says 'On it:
…' only where work was never held"*. `brain/anticipy_core.py:
Anticipy.say_handling @ e5b14c3e` is the **template fallback**, reached only
when `_voice` returns `None` — the call is `self._voice({...}) or
self.say_handling(decision.goal, held)`. "On it: …" is what he hears when the
model call died, not the mechanism.

And the narration does not merely go unsent — **there is no code path that
would send it.** In `Anticipy.hear`'s act branch, `handled` is composed for
both held and not-held work, and then every branch that reaches `notify_owner`
is guarded by `held`:

```
if   write_failed:                                       → handled = None
elif held and not repeat and _may_say(...):              → notify_owner(handled)
elif held and repeat:                                    → stay quiet
elif held and not explicit and _told_him_before(goal):   → stay quiet
elif held and not explicit:                              → cancel the card
```

There is **no `not held` branch at all**. The "quietly started" string is
composed and dropped on the floor. So adding narration is not enabling a
feature; it is writing a send branch that has never existed, and that branch
needs its own may-say discipline, its own dedupe, and its own quiet-hours
behaviour — the three things every other speaking path in that file carries a
dated scar comment about (2026-07-31, three texts in two minutes; 2026-08-07,
a held card he was never told about; 2026-08-11, a question with no card
behind it). That is a Shelf-1 feature with its own risk of making her
exhausting, and it deserves its own review rather than a paragraph inside a
safety spec.

**Where it goes.** Narration of already-permitted Shelf 1 work is a **Shelf-1
change**: it moves no permission boundary by one inch, it needs none of this
spec's machinery, and it ships and is measured on its own line in §11, against
its own baseline. §7.1's wording rules govern it — those are wording rules,
not shelf rules — which means its composition either obeys the
receipt-not-intention rule or it is a template, per `meeting_digest`'s
precedent.

**What Shelf 2 loses by this:** the more attractive half of the first
revision's day one. §6.4 restates the size accordingly, and does not round it
up.

### 6.3 NOT ADMITTED on day one — and each for a stated reason

| Act | Why not |
|---|---|
| A free-cancellation booking | Fails the entry condition outright: the cancel URL and reference come from the act. This is the card's headline example and it does not ship on day one. |
| Anything touching money, another human, or a delete | Shelf 3. Not a reversibility question. |
| A calendar event, a form submission, an account change | Fails the entry condition today for the same reason as the booking. §10.4 describes the specific door one of these could come through, and it is narrower than it sounds. |
| A draft created in the owner's Gmail account | §6.1. And per §5.4 this is the act the label attack impersonates, so it is the one whose *persisted reach* check has to be right before anything ships. |
| Any act executed by the browser agent | §5.4: a declared reach on a general browser session is a label on a process that can do anything the session can do. |
| Reading the owner's mail to corroborate a cancellation | Separate consent question, currently decided by a word list per tonight's audit. Not fixed here and not leaned on here. |

### 6.4 The honest summary, and the honest size

**Day one Shelf 2 is one act type: a draft that is a row in our own store.**
Narration is not part of it (§6.2).

Sized honestly and in the register a person would use: day one is **a drafting
feature with an undo button, plus the guard repairs that should have shipped
anyway** — §8.5's positive law, §5.4's persisted reach, §7.3's seam, §2.1's
receipt defect. That is **defensible to build**. It is **not "the new middle
ground"**, which is what the card is titled.

Both sentences are written here, next to each other, on purpose: **the gap
between them is where the pressure to widen will come from.** Somebody will
read the second sentence, feel the shortfall, and reach for the smallest edit
that closes it. §8.5 documents what that edit looks like when it arrives.

The machinery argument still holds and is the reason to build it at all: the
pre-written undo plan, the persisted reach, the durable announcement, the
compensating plan, the receipt — that is the expensive part, and it is proven
end to end on the one act type where the receipt is first-party by
construction, so widening later is a matter of admitting an act type through a
stated door (§10) rather than rebuilding the shelf.

**Sequencing note, since somebody will sequence this.** Three things named in
§10 belong **behind** the first admission, not in front of it: the persisted
admitted set as repo data (§10.3), the live-undo evidence pipeline (§10.1
condition 2), and `overnight/shelf2_gate.py`. Building an evidence pipeline
for an admitted set of exactly one, where the one is a row in our own
database, is machinery for a decision nobody is making yet. What goes **in
front** is the work that is wrong today whether or not this shelf ever ships:
the §8.5 positive law, §5.4's persisted reach, §7.3's seam.

This is a sequencing claim and not a licence: while the set has one member it
may be a constant that a reader can check in a single diff. **The repo-data
form and the gate leg are required before the second admission**, because the
second admission is the first one nobody can hold in their head, and §10.3's
argument for storing evidence with membership is unchanged.

## 7. What the announcement says, and what the tap does

### 7.1 Two registers, and the tap appears only when it does something

A decorative Undo teaches the owner that Undo is decorative, and the next time
it matters he will not reach for it. So:

**Narration — no tap.** Work in flight that touches nothing outside. Present
tense, and it names the next thing he will actually receive, because the value
of the sentence is that he can stop waiting:

> *"i'm on the restaurant's site now — i'll text you the times."*

The card's own example, unchanged, and true today. No Undo, because there is
nothing to undo. If he wants it stopped he says so, which is the existing
cancel path, not an undo. **This register is a Shelf-1 change and does not
ship inside Shelf 2 (§6.2); the rules below govern it wherever it ships,
because they are wording rules, not shelf rules.**

**Act-and-tell — with a tap.** Past tense, names the exact thing done, offers
the undo in the same breath:

> *"drafted the email to your landlord about the boiler — [undo] if you'd
> rather i hadn't."*

Rules the wording must hold to:

- **Composed from the receipt, never from the intention.** The announcement
  says what the receipt says happened. An announcement generated from the plan
  is a confident lie waiting for the first failure, and moment 30 is already
  the repo's standard here: an honest report beats a claim. (This is the rule
  the existing `_voice` path breaks — §6.2, reason 2.)
- **Never promises the undo will succeed.** It offers a tap, not an outcome.
  "cancel anytime" is a promise about a third party; "[undo] if you'd rather I
  hadn't" is a promise about a button.
- **Names the act precisely enough that he can tell it is wrong.** "drafted the
  email to your landlord" is checkable; "handled that for you" is not, and an
  announcement he cannot check is worth nothing as a safety mechanism.

### 7.2 What the tap does

1. **The tap writes an event, not a plan.** The app records an authenticated
   owner gesture bound to `plan_id` + `version` + `scope_digest`. The brain
   mints the plan. An executor that could mint its own undo could mint its own
   anything; the guard's `reject("an executor cannot rewrite or approve its
   plan")` (`backend/pb_hooks/workflow_guard.pb.js @ e5b14c3e`) already refuses
   that, and the tap must not become a hole in it.
2. **The finished plan is not touched.** `SUCCEEDED` stays terminal, and
   `brain/workflow.py: cancel @ e5b14c3e` keeps raising *"completed work
   cannot be cancelled retroactively"*, because retracting the record of
   something that really happened destroys the only evidence that it did. Undo
   is a **compensating plan in the same lineage**. This is Stage 1's
   architecture and it survived every pass; it is reused, not redesigned.
3. **The compensating plan cannot claim success without proof.** The guard's
   `reject("done needs verified evidence for this exact effect")` already
   refuses a `done` without a verified receipt whose `effect_key` matches. This
   is the existing mechanism the card under-uses, and it is most of the answer
   to "the undo can fail silently": **the database will not let the undo be
   marked done on a claim.** On day one the evidence is our own deleted row —
   and per §2.1, this leg checks `receipt.verified` and not its provenance, so
   it is exactly as good as whatever set that flag.
4. **The owner gets a second message either way.** "undone — here it is gone",
   or "couldn't undo it. here's what i tried and what's still standing." The
   second message is the one that matters and it must be as easy to send as the
   first, or the failure path silently rots.
5. **Undo is last-in-first-out within a lineage, and refuses otherwise.** See
   §7.4. This is new in this revision and it is not optional.

### 7.3 The tap has no words, and three places require words

`brain/workflow.py: Approval @ e5b14c3e` declares `owner_words: str`, and
`brain/workflow.py: Plan @ e5b14c3e` documents `authority_text` as *"Exact
owner-authored wording that grants the plan its concrete detail. Models may
shorten `goal`; this text is never model-owned and is bound into the signed
scope/effect payload whenever it exists."* A tap is a gesture, not wording.
Stuffing a synthetic string into `owner_words` to satisfy the check would put a
sentence the owner never said into the field whose entire purpose is that he
did say it.

This spec does not resolve it; it names it as a seam that must be resolved
before the undo lane ships, and states the constraint: **an owner gesture must
be recorded as a gesture** — authenticated, bound to plan id, version and scope
digest, and distinguishable at a glance from speech. A typed reply of "undo"
*is* words and can use the existing field honestly. A tap is not, and the two
must not be stored as the same thing.

**The seam is enforced in three places, not one**, and a fix that misses any of
them ships a lane that fails in a different layer than the one it was tested
in. Verified at `e5b14c3e`:

1. **Python.** `brain/workflow.py: approve @ e5b14c3e` — `words =
   owner_words.strip()`; `if not words: raise WorkflowViolation("approval must
   retain the owner's actual words")`.
2. **The database.** `backend/pb_hooks/workflow_guard.pb.js @ e5b14c3e`, in the
   `NO_APPROVAL_NEEDED` block: `|| !approval.owner_words` →
   `reject("approval is not bound to this exact plan version")`. This is the
   self-declared final authority, and it refuses an empty string.
3. **The app, which is where the field is minted.**
   `app/ios/Anticipy/AnticipyApp.swift: approvalFields(for:) @ e5b14c3e` builds
   `"owner_words": ownerWords` into the approval dictionary. This is the layer
   closest to the gesture and furthest from the law, and therefore the layer
   where a synthetic string would actually get invented — *"tapped undo"* is
   one line of Swift away at all times.

A fourth site is adjacent and will be reached by the same fix:
`reconciliation.owner_words`, required by the same guard file's
`reject("uncertain effect was not proven safe to retry")` and minted in the
same Swift function. Any gesture representation has to answer for both.

### 7.4 Ordering: undo is LIFO within a lineage

**New in this revision; the first had no ordering law at all.**

An undo plan is written **before** its act runs, against the state as it was
then. Applying it later applies a compensation computed against a world that
may no longer exist. Two individually-undoable acts, undone out of order,
produce an outcome neither undo promised:

> Act A drafts the boiler email — row `d`, version 1. He is told. Twenty
> minutes later act B revises it in place — row `d`, version 2. He is told
> again. Undo(A) is *"delete row `d`"*; undo(B) is *"restore row `d` to version
> 1"*. He taps undo on A, and the row is gone; the receipt is genuine and the
> announcement is true. He then taps undo on B, still on screen, and the row is
> **restored**. A draft he was told forty seconds ago was gone is back, and
> both receipts are honest.

Every check in §5 passes at every step. Both undos required nothing their act
produced. The composition is what fails.

**The law:**

> A compensating plan may run only when **no later admitted act in the same
> `lineage_key` has run since the act it compensates**. If one has, the tap
> does not run the compensating plan. It becomes a Shelf 3 question — *"you
> asked me to undo the draft, but I've changed it since. here's what's there
> now"* — and waits for a tap.

`lineage_key` is already on the row and already required by the guard
(`reject("workflow id, version, and lineage are required")`,
`backend/pb_hooks/workflow_guard.pb.js @ e5b14c3e`), so the check has the field
it needs. Refusing here is cheap: he asked to undo, and instead of a wrong
undo he gets a true sentence and a tap. **Polarity is the floor again:** if we
cannot determine the ordering, we refuse the undo and ask.

## 8. The one dangerous edge, explicitly

The classifier is wrong in the unsafe direction. Enumerated, each with what
catches it, and where nothing does, said so.

**8.1 — The undo recipe is complete but the undo fails at run time.** Session
expired, endpoint gone, record already changed. A complete recipe is not a
guaranteed effect.
*Caught by:* the compensating plan cannot reach `done` without a verified
receipt (`reject("done needs verified evidence for this exact effect")`). It
fails loudly, into `failed`, and §7.2.4's second message goes out. **And it
triggers automatic demotion** — §10.5, whose trigger this revision narrows so
that our own outage is not mistaken for a counterparty refusal.

**8.2 — The act did more than we recorded — and on day one, by requirement.**
The undo undoes the effect we know about; an unrecorded side effect stands. A
booking that also charged a card; a submission that also subscribed.

The first revision answered this with *"on day one, structurally impossible —
nothing left our store."* **That is false, and it is false because of §8.3.**

> §8.3 requires that an act may not run unattended unless its announcement is
> on the same durable path as the act: *"the tell is part of the work."*
> The tell is an SMS. So the day-one act is: write a row, **and send him a
> text**. He taps undo forty seconds later. The row is deleted, the receipt is
> genuine, §7.2.4's second message goes out, and *"drafted the email to your
> landlord about the boiler"* is permanently in his message history, in the
> carrier's records, and in Twilio's logs.
>
> **The undo required nothing the act produced, and the act was still not
> fully reversible.**

§8.3 wins that contradiction — the durable tell is not negotiable, because the
alternative is moment 49, an act he never hears about. So the residue is not a
defect to design away. It is a cost this spec accepts, and §4.1 demotes the
headline rule accordingly.

*What actually contains it,* since "structurally impossible" no longer does:

- **The residue is bounded by audience, and that bound is already law.** The
  tell goes to the owner and to nobody else, ever. Any act whose *tell* would
  reach a third party is Shelf 3 by §10.1 condition 4, which is absolute. An
  irreversible trace in the owner's own message history about work done for
  the owner is the thinnest residue this shelf can leave and still be
  act-and-tell rather than act-and-hope.
- **§7.1's wording rules are what make it survivable.** A residue that *"names
  the act precisely enough that he can tell it is wrong"* is a residue he
  would have wanted; a residue that says "handled that for you" is noise he
  can neither check nor undo. This is the second job those rules do.
- **The four non-structural conditions of §10.1** are what carry the safety
  argument from here on, per §4.1. The structural test is the door; it is not
  the room.
- **For widening, nothing changes:** the hazard as originally stated — an
  unrecorded effect in a third-party system — returns in full the instant the
  set widens, which is why §10.1's condition 3 adversarial probe is a hard
  requirement and not a nicety.

**8.3 — The phone dies between the act and the announcement (moment 49).** He
never learns an act happened, so he never undoes it. Silence is
indistinguishable from nothing having happened.
*Caught by:* `effect_key` plus `effect_uncertain` plus the reconciliation
requirement (`reject("uncertain effect was not proven safe to retry")`,
`backend/pb_hooks/workflow_guard.pb.js @ e5b14c3e`) already refuse a retry of
an uncertain effect without evidence it was not applied — that is moment 49's
"no re-texts, no ghost cards" and it is already built. **The new requirement
this spec adds:** an act may not run unattended unless its announcement is on
the same durable path as the act. *Act-and-tell* means the tell is part of the
work, not a best-effort text afterwards. An act that ran and was not announced
is an open obligation, not a completed job. **This requirement is what makes
§8.2 true, and it is kept anyway** — an irreversible line in his own message
history is a smaller harm than an act he never hears about.

*This requirement has no mechanism today, and that is a live defect.*
`brain/anticipy_core.py: Anticipy.notify_owner @ e5b14c3e` returns
`{"skipped": "no transport"}` — a **truthy dict** — when no transport is
configured, so `if not notify_owner(...)` reads a send that never happened as a
send that succeeded. Its own comment records the cost: *"On 2026-08-16 she
composed his questions, stamped them delivered and sent nothing for ten hours:
'he didn't text me once during our testing.'"* One escape has since been
closed (`can_notify_owner`, same file, distinguishes a real person we cannot
reach from a rig with no Twilio), but the truthy no-op remains for the
transport-less case, and there is **no durable obligation record anywhere** —
no "announced" column, no retry, nothing that outlives the process.

So "the announcement is durable" is currently an assertion with nothing behind
it. The requirement, stated so it is buildable: **the obligation to announce
is a row, written in the same transaction as the act, cleared only by evidence
of delivery, and surviving a restart.** Not a return value, and not a boolean
in memory. Until it exists, §10.1 condition 5 is unmeetable and no act type may
be admitted — including day one's.

**8.4 — The model writes a plausible undo plan for an act that has no undo.**
The recipe parses, binds, and is fiction.
*Caught by:* nothing, at the level of a single act — and this is the honest
residual risk. What contains it is that the admitted set (§6) is not the
model's to widen. A well-formed undo plan for an unadmitted act type is
refused whatever it says. The model's artifact is a **necessary condition
inside an already-closed set**, never a way into the set. This is why §10's
door is human, evidence-bearing, and pre-registered: it is the only thing
standing between a persuasive model and a wide shelf.

**8.5 — The middle shelf disables the gate by existing. Read this section
before you open the guard file.**

*This is the single highest-risk line item in this card, and the shape of the
risk changed after the first revision was written.*

**What has already shipped.** When the first revision was written, the guard
read `if (nextStatus === "queued" && consequence === "consequential")`, so
approval was demanded only when that one string was spelled exactly right, and
any third value reached `queued` unapproved. **That has been fixed** —
commit `afd4380a`, *"The final authority demanded approval only when one word
was spelled right"*. The file now reads:

```js
// An ARRAY, not an object-as-set: `{ read_only: 1 }[consequence]` is truthy
// for "constructor", "toString" and every other inherited property name, so
// the obvious lookup hands an attacker an exemption keyword.
const NO_APPROVAL_NEEDED = ["read_only"];
if (nextStatus === "queued" && NO_APPROVAL_NEEDED.indexOf(consequence) < 0) {
  // approval must be parseable and bound to this exact plan version
}
```

**What that means for whoever implements this shelf, and it is the trap.** A
third `Consequence` value now fails **closed**. Every Shelf 2 row is rejected
at `queued` — `"consequential work needs parseable approval"`, or `"approval is
not bound to this exact plan version"` — because a Shelf 2 act has no approval.
Not having one is the entire point of the shelf.

The implementer will hit that rejection, open the file, find §8.5's first
prescription already implemented, read `NO_APPROVAL_NEEDED` as *the list of
lanes that run without a tap*, observe that Shelf 2 is by definition a lane
that runs without a tap, and write:

```js
const NO_APPROVAL_NEEDED = ["read_only", "reversible"];   // ← DO NOT
```

**One edit. It reads as compliance with this very section.** It turns off
database-level approval for the new lane and puts **nothing in its place** —
which is the whole of the danger, because `read_only`'s exemption is earned
by a backstop that Shelf 2 does not have: `extension/background.js:
runSupervisedReadJob @ e5b14c3e` fails any job whose `consequence !==
"read_only"` outright, and nothing in that lane acts on the world. Shelf 2
would inherit the exemption and none of the backstop.

**So the positive law is the requirement, and the allowlist entry is
admissible only as its consequence.** In the order it must be built:

> A Shelf 2 `consequence` value may be added to `NO_APPROVAL_NEEDED`
> **only in the same diff that adds a Shelf 2 leg to the same file**, and that
> leg must reject `queued` unless **all** of the following hold of the embedded
> `_workflow`:
>
> **a.** an undo plan is present and parses;
> **b.** its inputs are a typed, closed list of provenance-tagged references,
> and the guard **resolves every one of them** against stored values on the row
> (§5.2) — it resolves them, it does not read their names;
> **c.** the plan's `act_type` is a member of the persisted admitted set;
> **d.** the plan's **persisted declared reach** (§5.4) equals the reach the
> admitted set records for that `act_type`;
> **e.** the announcement obligation is recorded on the row (§8.3);
> **f.** no later act in the same `lineage_key` invalidates it, for a
> compensating plan (§7.4).
>
> Any of a–f missing, unparseable, or unresolvable is a **rejection**, never a
> default.

The shape already exists in the file: `reject("required facts are missing from
the approved plan")` is the same move — refuse a `queued` whose required facts
are absent from the approved plan. The middle shelf needs its own instance of
it, and **that instance is the price of the allowlist entry.**

**Two more places a third value lands, both verified, because a guard fix that
stops at the guard is not a fix:**

- **`brain/workflow.py: Plan.assert_valid @ e5b14c3e`** requires version-bound
  approval only when `self.consequence == Consequence.CONSEQUENTIAL`. A third
  value skips that raise too. That is *correct* for a lane meant to run
  unattended — and it means **Python contributes nothing at all to the new
  lane's admissibility.** The whole of the new lane's law is the guard leg
  above, which is why it is a precondition rather than a follow-up. It must
  **not** be fixed by adding a rule to `assert_valid`: §3's transition rule
  binds, and a rule there that can be false for a legitimately stored row makes
  that row unparseable forever.
- **`brain/anticipy_core.py: Anticipy._pending_class @ e5b14c3e`** returns
  `stored == "consequential"`, so a third value reads as *not* consequential.
  This is a **dedupe partition, not an approval gate** — the first revision
  called it "the same polarity" as the guard, which overstated it. The real
  consequence is narrower and still real: Shelf 2 work would dedupe against
  read-only work, which is the 2026-08-04 scar in that function's own docstring
  (*"she researched the restaurant, he said 'book it', and `_queue_job` handed
  back the research job's id and created nothing"*) pointed at a new lane.
  Shelf 2 needs its own partition, not a boolean.

**Adding a `Consequence` value without the positive law first turns the one
database-level backstop off for the new lane, and the edit that does it is one
list literal long.**

**8.6 — The undo act is itself gated.** `cancel(?:s|led|ling|ed|ing)?` is in
`brain/anticipy_core.py: _VERBS @ e5b14c3e`, so `_IRREVERSIBLE_RE` matches a
cancellation goal and `brain/anticipy_core.py: is_consequential @ e5b14c3e`
returns True on its deny-list branch — **before** the `touches` branch and
before `explicit`, because the deny-list outranks everything. **A one-tap undo
would, today, be held for a second tap.**
*Resolved by:* the tap **is** the approval. The compensating plan carries the
owner's gesture as authority bound to that exact plan version, which is the
shape the guard's `NO_APPROVAL_NEEDED` block already requires — so the undo
lane needs no gate change either, consistent with Stage 1. §7.3's seam must be
settled, in all three places, for this to be recorded honestly.

*Naming note, since it will mislead the next reader:* `_IRREVERSIBLE_RE` does
not detect irreversibility. It detects world-touching verbs in action position.
Nothing in the tree today classifies reversibility, and nothing should start by
borrowing that name.

**8.7 — The declared reach is a label, and nothing checks the steps.** New in
this revision; §5.4 is the full statement.
*Caught by:* §5.4's persisted-reach binding catches a plan whose declaration
disagrees with its admitted type. **Nothing catches** a plan that declares the
right reach and whose steps go somewhere else, and no mechanical check of steps
is proposed, because a check over URLs or step text would be the word list this
whole spec refuses.
*What contains it* is the executor constraint, and it is the only mechanical
containment available: **day one's act type runs against our own store through
our own code path.** A step list handed to a browser session is bounded by what
the session can do, not by what the plan said. This is a real limit on how far
Shelf 2 can widen without a different kind of answer, and §10.4's
capability-keyed door does not solve it — a client-minted identifier makes the
*undo* clean; it says nothing about where the *act* went.

## 9. What the effect-channel field actually does

The card says *"the effect-channel field already classifies compute/read/world."*
Checked in code rather than taken on trust, because five times tonight a card's
description of the code was wrong. This one is **true, narrower than it
sounds, and more ephemeral than the first revision realised.**

- The field is called **`touches`**, not `effect_channel`. Nothing named
  `effect_channel` exists in the tree.
- It is a **model declaration** in triage output — prompt and contract in
  `brain/orchestrator.py: TRIAGE_SYSTEM @ e5b14c3e`, parsed in
  `brain/orchestrator.py: Brain.triage @ e5b14c3e`, where a value outside
  `TOUCHES = ("compute", "read", "world")` becomes `None` (no classification,
  not a default).
- It is consumed at exactly one decision:
  `brain/anticipy_core.py: is_consequential @ e5b14c3e`. `"world"` → held.
  `"compute"`/`"read"` → runs. `None` → falls through to the registered tape
  (`_READ_ONLY_RE`, `compute_answer`).
- The deny-list `_IRREVERSIBLE_RE` outranks the field in one direction only: it
  can add a hold that the model's declaration would have released. It can never
  release. That polarity is correct and this spec preserves it.
- **It is never persisted.** Not on `Plan`, not on the row, not in `backend/`,
  `extension/` or `app/ios/` — see §5.4 for the full verification. It is a
  Python call argument with a lifetime of one decision.

**What this means for the card's HOW.** `touches` is a three-value input to a
**two-value** decision — the shelf boundary, not a shelf. It says nothing about
reversibility and was never asked to. Shelf 2 is not a matter of reading a
field that already exists; it is a third destination that does not exist, and
`brain/workflow.py: Consequence @ e5b14c3e` is where it would have to be born —
under §8.5's condition, first.

**And the non-persistence is a requirement, not trivia.** §5.4 needs a durable
declared reach for the guard to check; `touches` as it exists cannot supply
one. Whether the persisted reach reuses this field's three values or is a
separate, act-type-scoped vocabulary is an implementation choice; that it must
exist on the row before the §8.5 leg can be written is not.

The card's sentence is therefore accurate about what the field classifies and
misleading about how much of Shelf 2 it already provides. `touches: "world"` is
the **entry condition** to the reversibility question, not an answer to it.

## 10. Pre-registered criteria for widening the shelf

Written now, before anyone is invested in an answer — the discipline that made
the engine question in `2026-08-24-voice-capture-design.md` §8 answerable.
Everything in this section is a **gate on a human decision**, evaluated against
committed evidence. None of it decides at runtime whether an act is reversible;
that is §5's structural test, and these criteria cannot release anything the
structural test refused.

### 10.1 The conditions to admit a new act type

An act type joins the admitted set only when **all six** hold:

1. **The two-sided admissible test passes structurally** for every instance of
   the type (§5.4): a stored undo plan whose inputs are typed, provenance-
   tagged and all resolvable at write time, **and** a declared reach that is
   persisted, bound to the act type, and checked in the guard. Necessary,
   never sufficient — §4.1.
2. **Ten live end-to-end undos, zero failures, spread across at least ten
   distinct days, within the last 90**, each producing a verified receipt
   committed to a repo file. Live, per Law 3 — repo-green is not evidence.
3. **A silent-failure probe passes**: at least one deliberately adversarial
   run against a counterparty made to lie — a page that prints "free
   cancellation" and refuses the cancellation — where the system **refuses the
   act or catches the failure loudly**. If we cannot demonstrate the failure
   being caught, we have not defended against it. This condition is not
   waivable for being hard to build.
4. **No Shelf 3 overlap.** The act sends no money, messages no other human,
   deletes nothing of the owner's. Absolute; no quantity of evidence buys an
   exception. **This also binds the tell** (§8.2): an act whose announcement
   would reach anyone but the owner is Shelf 3.
5. **The announcement is durable** — the act cannot complete without its tell
   on the same durable path, and "durable" means the obligation record §8.3
   specifies, not a truthy return value.
6. **For any act type whose effect leaves our store: the receipt path does not
   release on page prose.** §2.1's defect is repaired first. Day one's act type
   satisfies this vacuously, which is exactly why the defect can be repaired
   behind the first admission rather than in front of it — and exactly why it
   cannot be forgotten there.

### 10.2 Why the numbers in condition 2 are not a threshold deciding meaning

Because a reader will raise it, and should. Ten-in-90-days does not decide
whether any act is reversible. It decides whether a **human review** may open a
door, and it is evaluated over recorded outcomes — the "gates and evals"
exemption in Law 1, which is the same exemption every scoreboard in
`overnight/` relies on. Measuring is not programming. The number's real job is
to be fixed *now*, so that the person who wants the shelf wider later argues
against a number they did not choose.

**The ten-distinct-days clause is new, and it is there because §3's own
objection applies to condition 2 word for word.** As first written, ten undos
in one afternoon — one page, one A/B arm, one time of day, one rate class —
satisfied it. What that proves is *that one page once cancelled ten times*,
which is precisely what §3 refused to accept from "proven host": *the same host
serves a different page tomorrow, to a different rate class, in a different
country, behind a different A/B arm.* A criterion that refuses an argument in
§3 and then accepts it in §10 is not pre-registration, it is a preference. Ten
days is the cheapest available proxy for "not one session's luck", and like the
ten, it is fixed now so that whoever wants it relaxed argues against a number
they did not choose. **Whether ten days is the right spread is an owner call
(§13.6); that there must be a spread is not.**

### 10.3 The admitted set is a floor, and how it must be stored

The admitted set can only ever **refuse**: an act type not in it is held,
whatever the model wrote. It never releases anything the structural test
failed. A list that can only hold is a seatbelt; a list that can release is the
violation, and the difference is the whole of Law 1's exemption.

Membership must be **data in the repo carrying its evidence**, with a gate leg
(`overnight/shelf2_gate.py`) that goes red if an admission is present without
its committed receipts — never a constant somebody can add to a source file in
a hurry. Mutation-test that leg in both directions, or it is a test that cannot
fail.

**Per §6.4's sequencing note, this form is required before the second
admission**, not before the first: while the set has one member, a constant a
reader can check in a single diff carries the same information. The moment a
second act type is proposed is the moment the constant stops being readable and
the evidence stops being attached to the claim.

**The set records, per act type: the permitted reach** (§5.4 condition 2),
**the executor that may run it** (§8.7), and **its evidence**. A membership
record that is only a name cannot support the checks §8.5 requires.

### 10.4 Admission is keyed on a capability we hold, never on a host we visited

The worked example, because the criterion needs teeth and this shows it has
some:

Some providers accept a **client-generated identifier** — the caller mints the
record id, or supplies an idempotency key. Where that is true, the undo recipe
is complete before the act: *delete the record whose id we minted.* It depends
on nothing the counterparty returned. That genuinely passes §5.2's test, and it
does so for a reason that has nothing to do with the domain: not "calendars are
safe" (a domain list) but "an act whose undo addresses an identifier we minted
is undoable by us alone."

So the key is the capability, and the host is recorded as evidence rather than
as the key. This is why §3 declines the "proven host" successor: a host
allowlist keys the release on the identity of the party we are defending
against.

**Two limits on this door, both from this revision.** It makes the *undo*
clean and says nothing about where the *act* went (§8.7) — so an act type
admitted through this door still needs an executor whose reach is bounded by
something other than a label. And the first act type through it is the first
whose effect leaves our store, which triggers §10.1 condition 6: §2.1's
receipt defect is repaired before that door opens, not after.

### 10.5 Withdrawal, also pre-registered — and it must tell two failures apart

**Any single undo failure in production on an admitted act type demotes it to
Shelf 3 immediately, until re-admitted through the whole of §10.1.**

Pre-registered because after the fact everybody will have a reason it was a
one-off, and they will be persuasive, and the owner will be the one paying if
they are wrong. The demotion is automatic and its reversal is expensive on
purpose.

**Two amendments, because as first written the rule is both unimplementable
and permanently destructive.**

**(a) It cannot distinguish a counterparty refusal from our own store
blinking.** "Undo failure" as written covers the case this rule exists for —
the counterparty would not let us undo — and the case it must not punish: our
database was unreachable for nine seconds, the compensating plan exhausted its
attempts, and the guard's `done` leg correctly refused a `done` with no
receipt. **One outage on a Tuesday kills the shelf permanently.** And because
the demotion is expensive to reverse *by design*, nobody will reverse it, and
Shelf 2 ceases to exist with no decision having been made by anyone.

So the demotion trigger is narrowed to: **a compensating plan that reached a
terminal `failed` state with evidence that the effect is still standing.** That
is the failure this shelf is built against. A compensating plan that never
reached the counterparty, or that exhausted its attempts against our own
infrastructure, is an **incident**: counted, reported in §11, escalated if it
recurs — and not a demotion.

The distinction must be made **from the row** — `effect_uncertain`,
`reconciliation` and the receipt are the fields that carry it — and **never
from an error string**, because reading an error string for meaning is the
thing this entire spec refuses to do.

**Where it is ambiguous, it demotes.** Floor polarity, same as §5.2: an undo
whose outcome we cannot determine is an undo that failed. An "incident"
classification requires positive evidence that our side failed; absent that,
the counterparty is presumed to have refused.

**(b) It names no executor. "Demotes it automatically" is a sentence with no
subject.** An automatic demotion needs a component that runs it, a place the
demotion is written, and a path by which the shelf finds out. §10.3 requires
the admitted set to be repo data, so a runtime demotion cannot edit it — which
means the mechanism is a **runtime denial list that the shelf reads and the
admitted set does not**: written by whatever component transitions the
compensating plan to `failed`, read at the same guard leg as §8.5, surviving a
restart, and cleared only by a §10.1 re-admission.

**Which component owns it, and whether the denial list lives in the database or
in the repo, is an owner/implementer decision and is handed back in §13.7.**
This spec states the two requirements it will not compromise on — the sentence
must have a subject, and the demotion must survive a restart — and declines to
invent the component.

### 10.6 Abandonment, also pre-registered — with a baseline, a window, and a magnitude

The condition under which the right answer is to stop rather than widen:

**If, twelve weeks after the shelf goes live, the admitted set is still a
single act type, and his taps-per-week has not fallen by at least 20% against
the four-week baseline measured before the shelf shipped, and his
messages-per-week has not fallen,** then Shelf 2 cost complexity and bought
nothing, and the answer is to remove it — not to widen it until it justifies
itself. Widening to recoup sunk cost is how the dead premise gets rebuilt with
better manners.

**Why each number is here, since the first revision had none of them:**

- **A baseline window.** "Has not fallen" against nothing is unfalsifiable, and
  an unfalsifiable abandonment test is an abandonment test that never fires.
  Four weeks before ship, recorded per §11.
- **A magnitude.** "Has not fallen" is satisfied by noise in either direction.
  20% is chosen now for exactly the reason ten-in-90-days is chosen now: so
  that the person who wants it lowered later argues against a number they did
  not pick.
- **A second metric, and this is the one the first revision was missing.** A
  shelf that **halved his taps and tripled his buzzes** passed the first
  revision's test cleanly, and it is a worse product than the one it replaced —
  taps he chose to make traded for interruptions he did not. So
  **messages-per-week is measured too, and it is a floor rather than a
  target**: if messages-per-week rose, taps-per-week falling is not a pass.
  §11 measures it, and §11 as first written did not.
- **Narration is not in this test any more** (§6.2), which is the change that
  makes the test answerable at all.

## 11. Observability, and what gets measured

- **Every refusal is recorded with its reason.** A shelf that refuses silently
  cannot be widened on evidence, because nobody can see what it refused. The
  count and the reason distribution are the input to §10.6. Reasons are the
  enumerated refusal causes of §5.2 and §8.5's a–f, not free text.
- **Every announcement is paired with its receipt** in the feed, per moment 31.
  An announcement with no receipt behind it is the defect, not a display bug.
- **Undo latency and undo outcome** are recorded per act type — the raw
  material for §10.1 condition 2 and the trigger for §10.5. Outcome
  distinguishes *counterparty refusal* from *our own failure* (§10.5a), because
  a metric that cannot tell them apart makes the demotion rule unimplementable.
- **Undo refusals for ordering** (§7.4) are counted separately. A high count
  means the LIFO law is being hit constantly, which is evidence the act type is
  wrong for this shelf rather than evidence the law is wrong.
- **Taps-per-week** is the product metric this card exists to move, **and a
  four-week pre-ship baseline is recorded, or §10.6 is unanswerable.**
- **Messages-per-week — every buzz she causes, of every kind** — is measured on
  the same baseline. It is the floor in §10.6, and it is the only metric here
  that can show the shelf making the product worse while the headline number
  improves.
- **Narration, if and when it ships as a Shelf-1 change (§6.2), is measured on
  its own line, against its own baseline.** That separation is the whole reason
  it was moved.

## 12. Law compliance

- **Law 1.** The meaning question ("what would undo this?") goes to a model
  with full context, asked alone, four-state, floor polarity. The release
  decision is a structural property of a stored artifact: the checker
  **resolves typed, provenance-tagged references** and refuses on any that does
  not resolve (§5.2) — it never inspects a field name and never parses prose,
  which is the clause that keeps it inside the seatbelt exemption rather than
  outside it. §5.4's act-side check compares a persisted declared reach against
  a persisted admitted set: two stored values, no interpretation. No word list,
  no domain list, no threshold decides reversibility. §10's numbers govern a
  human door and are evaluated over outcomes (gates-and-evals exemption);
  §10.3's set can only refuse.
  **One violation is named rather than introduced:** §2.1's
  `terminalReceiptEvidence` is page prose matched by regex deciding that an
  external effect occurred. It exists today, this spec does not rely on it, and
  §10.1 condition 6 makes its repair a precondition of the first admission that
  would reach it.
- **Law 2.** This spec introduces no tape. If an implementation needs some, it
  ships with a `TAPE:` comment naming `overnight/tape_gate.py`, a registry
  entry, and a ledger line in `HARNESS-LAWS.md` — three edits, one diff. (The
  prose fallback in `Anticipy._pending_class` is already tape and already
  carries its comment; §8.5 does not extend it.)
- **Law 3.** §10.1 condition 2 is live-only, and §8.5's guard leg is not fixed
  until its own leg is green against the live backend. The deploy-then-verify
  rule applies; `railway up` reports success while failing. Note that
  `afd4380a` being in the repo is not evidence it is in prod.
- **Law 4.** This file is the state. The dead premise (§3) is recorded here so
  it is not re-derived, and so is the trap created by a half-shipped remedy
  (§8.5). Any re-proposal of the struck auto-run design, and its outcome, gets
  written the day it is made.
- **Law 5.** Fix order respected: this is not a rule written while she is deaf
  or blind. It is structure (step 5), and it is seatbelt-shaped — it examines
  what a plan touches and what its undo depends on, never what the owner's
  words meant.
- **Law 6.** This revision is the adversarial pass §13 asked for, applied to
  the first. §13 records what it could not decide.

## 13. Decisions made without the owner, and what is handed back

The shape §13.1 established, applied to everything this revision could not
settle: **name which untrusted evidence an amendment would choose to trust, and
name who eats the cost when it is wrong.**

1. **The card's headline example does not ship on day one.** A
   free-cancellation booking fails §4's entry condition. Deciding otherwise
   means rebuilding the design three passes killed. If Omar reads the ruling as
   requiring bookings on day one, that is his call and this file gets amended
   rather than argued — but the amendment has to say which untrusted evidence
   it is choosing to trust (the page's cancellation prose, or the provider's
   flag), and name who eats the no-show fee.
2. **Shelf 2's day-one value is one act type, and it is smaller than the card's
   title.** §6.4. This is a smaller claim than "the new middle ground" and it
   is the honest one.
3. **The "proven host" successor is declined**, not deferred. §3, §10.4.
4. **No reversibility classifier, including no model-returned boolean.** §5.
   This is the substantive content of the review the card assigned to Jose, and
   it is a refusal of the card's own framing.
5. **Handed back — `terminalReceiptEvidence` (§2.1).** Two repairs are
   available and they cost different things. *(a)* Delete the fast path, so
   every `done` claim goes to the LLM verifier: costs latency and model spend
   on every external act, and trusts the verifier's judgement over a page. *(b)*
   Keep it as a **corroborator that can only refuse** — page prose may add a
   hold, never release — which matches §4's polarity exactly but leaves the
   release resting on the verifier alone. **Which untrusted evidence is being
   trusted:** in (a), the verifier's reading of the page; in (b), also the
   verifier's, with the page demoted to a refusal signal. **Who eats it when
   it is wrong:** the owner, in the form of a "done" for something that did not
   happen. This spec's own polarity argues for (b), but the cost of (a) is
   money and latency the owner pays, so it is his call.
6. **Handed back — the spread in §10.1 condition 2.** Ten distinct days is a
   number this revision chose, and it makes admission slower. **Who eats it:**
   the owner waits longer for a wider shelf. That there must be *some* spread
   is not handed back — §10.2 gives the argument, and it is §3's own.
7. **Handed back — §10.5's executor and the denial list's home.** Which
   component writes a demotion, and whether the denial list lives in the
   database (fast, and one more thing the final authority must be right about)
   or in the repo (auditable, and slower than a production failure). **Who eats
   it when it is wrong:** the owner, in the form of an act type that stays
   admitted after it has already failed him once.
8. **Handed back — §10.6's 20% and the messages-per-week floor.** Both numbers
   are this revision's, both are pre-registered on purpose, and both decide
   whether the shelf gets removed. **Who eats it:** if they are too lenient,
   the owner keeps a shelf that costs complexity and buys nothing; too strict,
   he loses one that was working.
9. **Handed back — narration's re-filing (§6.2).** This changes what the card
   delivers on day one, which is Omar's to say. The measurement argument
   (§10.6) and the Law 1 argument (§7.1's first rule) are this spec's, and both
   survive wherever narration ships. **What is not handed back:** narration
   composed at temperature 0.7 from the intention, which is a Law 1 problem
   regardless of which shelf it is filed under.

## 14. Spec self-review — what a reader should try to kill

- *"You've just moved the trust to the model that writes the undo plan."* No —
  the model's artifact is checked structurally and is a necessary condition
  inside an already-closed set (§8.4). It cannot widen the set. A perfect lie
  from the model buys nothing that the admitted set did not already permit.
- *"The admitted set is a domain list."* It can only refuse (§10.3), its
  membership is earned by committed live receipts rather than authored by
  opinion, and it is keyed on a capability we hold rather than a host we
  visited (§10.4). A list that can only hold is the seatbelt; a list that can
  release is the violation.
- *"Ten-in-90-days is a threshold."* It gates a human decision over recorded
  outcomes, not a runtime meaning judgement (§10.2).
- *"You check the label, not the act."* **Correct for the first revision, and
  it is the reason for §5.4.** The check is now two-sided: the act's declared
  reach is persisted and bound to the admitted type, so a plan labelled
  `local_draft` that declares a Gmail reach is refused before its undo plan is
  read. The residual — a plan that declares correctly and whose *steps* go
  elsewhere — is §8.7, stated rather than papered over, and contained by
  bounding the executor rather than by inspecting steps.
- *"Your headline rule is false: the tell is irreversible."* **Correct, and it
  is why §4.1 demotes it to the entry condition.** The tell is required by
  §8.3, so the residue is designed in, not overlooked. It is bounded by
  audience (§10.1.4) and it is the price of not being moment 49.
- *"§8.5 is scope creep."* It is the opposite: without it, adding a third
  `Consequence` value turns off the only database-level backstop for the new
  lane. It is the precondition, not an extra.
- *"§8.5 is stale — that guard was already inverted."* **Half of it was, and
  that is the trap, not the answer.** The inversion means Shelf 2 now fails
  *closed*, so the implementer meets a rejection first and the cheapest way out
  is a two-element array that reads as compliance with this section. The
  positive law is the requirement; the allowlist entry is only admissible as
  its consequence (§8.5).
- *"You cut narration because it was hard."* No — because it defeats §10.6,
  and because as it exists it composes from the intention at temperature 0.7,
  which §7.1's own first rule forbids and which `meeting_digest` already
  refused for the same reason. It is re-filed, not killed, and it is measured
  on its own line (§11).
- *"The undo could still fail."* Yes. It fails **loudly** (§8.1), it demotes
  the act type automatically (§10.5, now able to tell a counterparty refusal
  from our own outage), and on day one its evidence is our own row. Silence is
  the failure this spec is built against; failure is not.
- *"Nothing catches a persuasive model writing fiction for an unadmitted act."*
  Correct, and stated as the residual risk in §8.4 rather than papered over.
  What contains it is that the set is not the model's to widen.
- *"Your own citations will rot."* They are pinned to `path: symbol @ commit`
  precisely because the first revision's did — within hours, and two of them
  were wrong at the commit they shipped in. Symbols move with the code they
  name; line numbers do not.
