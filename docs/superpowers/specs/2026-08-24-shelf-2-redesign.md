# SHELF 2 — act-and-tell with one-tap undo — redesign

> Status: SPEC. Not a plan, not a sequence, no code. Somebody else sequences it.
> Supersedes the struck Stage 2 of `docs/superpowers/plans/2026-08-25-shelf-2-undo.md`.
> Stage 1 of that plan (undo as a compensating plan, moment #28) survives
> untouched and this spec assumes it.
>
> Card: SHELF 2, Omar's ruling of 2026-08-24, three shelves.
> Brief: `docs/BRIEF.html` moments 25, 26, 27, 28, 30, 31, 48, 49.
> Laws: `HARNESS-LAWS.md` (1, 2, 3, 4, 6 all bind here).
> Jose's assigned part: review the reversibility classifier. §5 is that review,
> and its finding is that the classifier is the wrong object.

---

## 1. Goal

Give the owner a middle shelf: work that runs **without waiting for a tap**,
and is **reported afterwards with a real undo**. Shelf 1 (math, lookups) runs
silently. Shelf 3 (money, messages to other humans, deletes) taps first,
forever. Shelf 2 is the register in between, and today there is nothing in it —
`Consequence` has exactly two values (`brain/workflow.py:38-41`).

The card's own safety claim is the thing to preserve, verbatim: **the plan
carries its own undo recipe *before* acting.** Everything below is an attempt
to make that sentence literally true rather than decoratively true.

## 2. Non-goals

- **No change to Shelf 3.** Money, messages to other humans, deletes: tap
  first. No reversibility finding, no receipt, no host history, no owner
  impatience overrides this. It is not a default, it is a wall.
- **No new verification vocabulary.** `terminalReceiptEvidence`
  (`extension/agent_loop.js:1721-1726`) already accepts "successfully
  cancelled" plus a reference as terminal first-party proof. If this spec
  needs a new word for success it has gone wrong.
- **No modification of `is_consequential()`** for the hold/run split of
  existing work. This spec adds a third destination; it does not move anything
  that is held today into a lane that runs.
- **No reversibility classifier.** See §5. This is a non-goal on purpose.
- **Not a plan.** No tasks, no ordering, no estimates.

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
`Plan.assert_valid` (`brain/workflow.py:242`). That function runs via `from_dict`/`from_params`,
which is called unguarded at `brain/worker.py:1171` and `:1244` and at
`brain/anticipy_core.py:1172`, `:2946` and `:3974` — verified against the tree
today; the struck plan cited `anticipy_core.py:3572`, which has since moved,
and the hazard is unchanged by the drift. It also runs inside a bare
`except Exception: return None` on the Send path. A stored
SUCCEEDED row that lost its undo evidence would become permanently
unparseable, and `brain/workflow.py:50-62` is a twelve-line scar block about
exactly that — one malformed row threw out of `hear()`, the event was marked
error and never retried, *"and nothing was ever said to him about any of it."*

**Rule that survives and binds this spec:** `assert_valid` must never grow a
rule that can be false for a legitimately stored row. A law of this kind
belongs in a TRANSITION guard, mirrored in `backend/pb_hooks/workflow_guard.pb.js`,
or it uses the cautious-coercion shape of `_state_after_unreadable`
(`brain/workflow.py:78-98`) — never a raise.

**The successor idea in that plan's postscript is also declined.** It proposed
"proven host": a per-HOST allowlist, a host admitted after one live end-to-end
undo. That is a domain list wearing a receipt. A host is not a stable identity
— the same host serves a different page tomorrow, to a different rate class, in
a different country, behind a different A/B arm — and the thing we would have
proven is that one page once cancelled once. §10 replaces it with admission
keyed on a **capability we hold**, never on a host we visited.

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

The three directions the card offered, weighed:

| Direction | Verdict |
|---|---|
| **Provider-side confirmation** instead of page-scraped handles | Better, and still testimony. A provider flag is authored by the counterparty under a contract rather than by an arbitrary page, which raises the cost of lying without changing what kind of thing it is. It also drags in a second problem: verifying against the owner's inbox means reading the owner's mail, and tonight's audit already found a word list deciding consent to do that. **Not a day-one release.** Admissible later only as corroboration inside §10's door, never as the release itself. |
| **Prove the undo by doing it** (scratch run) | Converts a claim into evidence, and cannot be a per-act release. For most act types the scratch run *is* the harm — two bookings, two emails, a rate limit, a blacklist — and where it is harmless it proves the wrong thing: that *that* booking was cancellable, not that *this* one will be. Sites vary by rate class, by attempt number, by time of day. **Kept as an admission instrument in §10, never as a runtime check.** |
| **Shelf 2 starts tiny and grows one act-type at a time** | Correct, and this spec takes it. |

**The rule that falls out, and it is the whole spec:**

> **An act is admissible to Shelf 2 only when undoing it requires nothing the
> act produced.**

If the undo needs a handle, a URL, a reference number, a deadline, a session,
or a record id that the act itself created and the counterparty controls, then
the undo recipe cannot be complete before the act — it contains a hole to be
filled by the party we are defending against. The card asked for a recipe that
is known-good **before** acting. This rule is what that sentence means when
taken literally, and taking it literally is the redesign.

Two consequences worth stating out loud, because they are the load-bearing
half:

1. **The same property makes the undo's receipt trustworthy.** An undo that
   depends on nothing the counterparty authored produces a receipt the
   counterparty did not author either. On day one, where the effect never
   leaves our own store, the undo's evidence is our own row — first-party by
   construction. We are not trusting a stranger's "cancelled successfully"; we
   are reading our own database. The safety of the release and the safety of
   the proof have the same root, which is why this shelf is small: it is small
   exactly where trust runs out.

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

**Polarity: this is a FLOOR.** No verdict, no undo plan, an unparseable undo
plan, a dead model call, a timeout, an empty response — every one of those is
the same answer as "there is money here." Refuse; the work goes to Shelf 3 and
waits for a tap. A floor that lifts on silence lifts itself.

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

## 6. What Shelf 2 admits on day one

Applying §4's rule honestly. This list is short. Saying so plainly is the point;
a small shelf that is honestly safe beats a wide one that is not.

### 6.1 ADMITTED — acts whose entire effect is a row in our own store

Drafting, held locally. A drafted email, message, or document that lives in our
storage and is shown only to the owner. Nothing left his world. The undo is
"discard our row", written in full before the draft exists, needing nothing but
an id we minted.

This is the whole of the admitted *acting* set on day one. One item.

Note what it excludes, and why the line is where it is: **a draft created in
his Gmail account is not admitted.** The effect left into a third-party system
and the undo needs a message id the provider returned — a hole in the recipe,
filled by the counterparty, after the act. Same act in English, opposite side
of the line. That the same word lands on both sides is the clearest evidence
available that a word list could never have drawn this boundary.

### 6.2 ADMITTED — the announcement of Shelf 1 work that was already permitted

The card's own flagship example is *"I'm on the restaurant's site now — I'll
text you the times."* **That is a read.** Under `touches` it is `"read"`
(`brain/orchestrator.py:208-219`), it is not consequential
(`brain/anticipy_core.py:591`), and it already runs unattended today. The card
files "checking a site" under Shelf 2 while Omar's ruling files "lookups" under
Shelf 1, and both are right about permission — the difference between them was
never permission at all. **It is whether he hears about it.**

So a real part of what Shelf 2 delivers on day one is **not a new permission
but a new voice**: narrating work that was already allowed to run silently.
This has a genuine product cost today — `say_handling`
(`brain/anticipy_core.py:2693-2701`) says "On it: …" only where work was never
held, so much of what she does she does in silence — and it carries **zero new
risk surface**, because the permission boundary does not move by one inch.

### 6.3 NOT ADMITTED on day one — and each for a stated reason

| Act | Why not |
|---|---|
| A free-cancellation booking | Fails the pre-written undo test outright: the cancel URL and reference come from the act. This is the card's headline example and it does not ship on day one. |
| Anything touching money, another human, or a delete | Shelf 3. Not a reversibility question. |
| A calendar event, a form submission, an account change | Fails the test today for the same reason as the booking. §10.4 describes the specific door one of these could come through, and it is narrower than it sounds. |
| Reading the owner's mail to corroborate a cancellation | Separate consent question, currently decided by a word list per tonight's audit. Not fixed here and not leaned on here. |

### 6.4 The honest summary

**Day one Shelf 2 is: local drafts, plus a voice.** The mechanism — the
pre-written undo plan, the announcement carrying the tap, the compensating
plan, the receipt — is built and proven end to end on that one act type, so
that widening later is a matter of admitting an act type through a stated door
(§10) rather than rebuilding the shelf. Building the machinery is the work;
the admitted set is deliberately the smallest thing that exercises all of it.

If that reads as a disappointing answer to a card titled "the new middle
ground": it is the answer the evidence supports, and the alternative on offer
is the design that three passes already killed.

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
cancel path, not an undo.

**Act-and-tell — with a tap.** Past tense, names the exact thing done, offers
the undo in the same breath:

> *"drafted the email to your landlord about the boiler — [undo] if you'd
> rather i hadn't."*

Rules the wording must hold to:

- **Composed from the receipt, never from the intention.** The announcement
  says what the receipt says happened. An announcement generated from the plan
  is a confident lie waiting for the first failure, and moment 30 is already
  the repo's standard here: an honest report beats a claim.
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
   anything; `workflow_guard.pb.js:150` already refuses an executor rewriting
   or approving its plan, and the tap must not become a hole in that.
2. **The finished plan is not touched.** `SUCCEEDED` stays terminal, and
   `cancel()` keeps raising on completed work, because retracting the record of
   something that really happened destroys the only evidence that it did. Undo
   is a **compensating plan in the same lineage**. This is Stage 1's
   architecture and it survived every pass; it is reused, not redesigned.
3. **The compensating plan cannot claim success without proof.**
   `workflow_guard.pb.js:202-210` already refuses a `done` without a verified
   receipt whose `effect_key` matches. This is the existing mechanism the card
   under-uses, and it is most of the answer to "the undo can fail silently":
   **the database will not let the undo be marked done on a claim.** On day
   one the evidence is our own deleted row.
4. **The owner gets a second message either way.** "undone — here it is gone",
   or "couldn't undo it. here's what i tried and what's still standing." The
   second message is the one that matters and it must be as easy to send as the
   first, or the failure path silently rots.

### 7.3 The tap has no words, and one existing field expects words

`Approval.owner_words` (`brain/workflow.py:147-153`) is required non-empty by
the database (`workflow_guard.pb.js:167-175`), and `authority_text`
(`brain/workflow.py:185-188`) is documented as *"exact owner-authored wording
… never model-owned"* and is bound into the effect digest. A tap is a gesture,
not wording. Stuffing a synthetic string into `owner_words` to satisfy the
check would put a sentence the owner never said into the field whose entire
purpose is that he did say it.

This spec does not resolve it; it names it as a seam that must be resolved
before the undo lane ships, and states the constraint: **an owner gesture must
be recorded as a gesture** — authenticated, bound to plan id, version and scope
digest, and distinguishable at a glance from speech. A typed reply of "undo"
*is* words and can use the existing field honestly. A tap is not, and the two
must not be stored as the same thing.

## 8. The one dangerous edge, explicitly

The classifier is wrong in the unsafe direction. Enumerated, each with what
catches it, and where nothing does, said so.

**8.1 — The undo recipe is complete but the undo fails at run time.** Session
expired, endpoint gone, record already changed. A complete recipe is not a
guaranteed effect.
*Caught by:* the compensating plan cannot reach `done` without a verified
receipt (`workflow_guard.pb.js:202-210`). It fails loudly, into `failed`, and
§7.2.4's second message goes out. **And it triggers automatic demotion** —
§10.5. A failed undo is never a one-off to be absorbed; it is the act type
losing its admission until it is re-earned.

**8.2 — The act did more than we recorded.** The undo undoes the effect we
know about; an unrecorded side effect stands. A booking that also charged a
card; a submission that also subscribed.
*Caught by:* on day one, structurally impossible — nothing left our store, so
there is no unrecorded elsewhere. This is the strongest argument for the tiny
day-one shelf, and the hazard that returns the instant it widens, which is why
§10.3's adversarial probe is a hard requirement and not a nicety.

**8.3 — The phone dies between the act and the announcement (moment 49).** He
never learns an act happened, so he never undoes it. Silence is
indistinguishable from nothing having happened.
*Caught by:* `effect_key` plus `effect_uncertain` plus the reconciliation
requirement (`workflow_guard.pb.js:177-191`) already refuse a retry of an
uncertain effect without evidence it was not applied — that is moment 49's "no
re-texts, no ghost cards" and it is already built. **The new requirement this
spec adds:** an act may not run unattended unless its announcement is on the
same durable path as the act. *Act-and-tell* means the tell is part of the
work, not a best-effort text afterwards. An act that ran and was not announced
is an open obligation, not a completed job.

**8.4 — The model writes a plausible undo plan for an act that has no undo.**
The recipe parses, binds, and is fiction.
*Caught by:* nothing, at the level of a single act — and this is the honest
residual risk. What contains it is that the admitted set (§6) is not the
model's to widen. A well-formed undo plan for an unadmitted act type is
refused whatever it says. The model's artifact is a **necessary condition
inside an already-closed set**, never a way into the set. This is why §10's
door is human, evidence-bearing, and pre-registered: it is the only thing
standing between a persuasive model and a wide shelf.

**8.5 — The middle shelf disables the gate by existing.** The most likely way
this card ships a disaster, and it is a live defect in the tree today rather
than a hypothetical.

`workflow_guard.pb.js:167` reads:

```js
if (nextStatus === "queued" && consequence === "consequential") { /* approval required */ }
```

The approval requirement fires on **one exact string**. Anything else — a new
third value, a typo, a truncation, a legacy blank — reaches `queued` with no
approval and no objection from the database. `_pending_class`
(`brain/anticipy_core.py:3837-3840`) has the same polarity: `return stored ==
"consequential"`.

The Python side is already correct: `_consequence_or_safe`
(`brain/workflow.py:64-69`) defaults an unreadable consequence to
CONSEQUENTIAL, and `_state_after_unreadable` parks it. The database — *"the
final authority for workflow transitions"*, by its own header comment — does
not.

*Required before any third value exists:* invert the guard to **deny by
default**. Approval is required unless `consequence` is a member of an explicit
allowlist of unattended values, so an unknown, new, or corrupted consequence
**holds** rather than runs. And the middle shelf needs its own positive law in
the same file, because a release enforced only in Python is not enforced: for
`queued` with the middle-shelf consequence, require a parseable undo plan in
the embedded `_workflow`, complete, zero unbound fields, act type present in
the admitted set. `workflow_guard.pb.js:102` already refuses a `queued` whose
required facts are missing from the approved plan — the shape exists; the
middle shelf needs its own instance of it.

**Adding a `Consequence` value without doing this first turns the one
database-level backstop off for the new lane. That is the single highest-risk
line item in this card.**

**8.6 — The undo act is itself gated.** `cancel(?:s|led|ling|ed|ing)?` is in
`_VERBS` (`brain/anticipy_core.py:95-112`), so `_IRREVERSIBLE_RE` matches a
cancellation goal and `is_consequential` returns True at line 587 before
anything else runs. **A one-tap undo would, today, be held for a second tap.**
*Resolved by:* the tap **is** the approval. The compensating plan carries the
owner's gesture as authority bound to that exact plan version, which is the
shape `workflow_guard.pb.js:167-175` already requires — so the undo lane needs
no gate change either, consistent with Stage 1. §7.3's seam must be settled for
this to be recorded honestly.

*Naming note, since it will mislead the next reader:* `_IRREVERSIBLE_RE` does
not detect irreversibility. It detects world-touching verbs. Nothing in the
tree today classifies reversibility, and nothing should start by borrowing that
name.

## 9. What the effect-channel field actually does

The card says *"the effect-channel field already classifies compute/read/world."*
Checked in code rather than taken on trust, because five times tonight a card's
description of the code was wrong. This one is **true, and narrower than it
sounds.**

- The field is called **`touches`**, not `effect_channel`. Nothing named
  `effect_channel` exists in the tree.
- It is a **model declaration** in triage output — prompt at
  `brain/orchestrator.py:208-219`, contract at `:293`, parsed at `:548-550`,
  where an invalid channel becomes `None` (no classification, not a default).
- It is consumed at exactly one decision:
  `is_consequential(goal, touches=...)` (`brain/anticipy_core.py:561-599`).
  `"world"` → held. `"compute"`/`"read"` → runs. `None` → falls through to the
  registered tape (`_READ_ONLY_RE`, `compute_answer`).
- The deny-list `_IRREVERSIBLE_RE` outranks the field in one direction only: it
  can add a hold that the model's declaration would have released. It can never
  release. That polarity is correct and this spec preserves it.

**What this means for the card's HOW.** `touches` is a three-value input to a
**two-value** decision — the shelf boundary, not a shelf. It says nothing about
reversibility and was never asked to. Shelf 2 is not a matter of reading a
field that already exists; it is a third destination that does not exist, and
`Consequence` (`brain/workflow.py:38-41`) is where it would have to be born —
under §8.5's condition, first.

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

### 10.1 The five conditions to admit a new act type

An act type joins the admitted set only when **all five** hold:

1. **The pre-written undo test passes structurally** for every instance of the
   type — a stored undo plan with zero fields bound from the act's response.
   Necessary, never sufficient.
2. **Ten consecutive live end-to-end undos, zero failures, within the last 90
   days**, each producing a verified receipt committed to a repo file. Live,
   per Law 3 — repo-green is not evidence.
3. **A silent-failure probe passes**: at least one deliberately adversarial
   run against a counterparty made to lie — a page that prints "free
   cancellation" and refuses the cancellation — where the system **refuses the
   act or catches the failure loudly**. If we cannot demonstrate the failure
   being caught, we have not defended against it. This condition is not
   waivable for being hard to build.
4. **No Shelf 3 overlap.** The act sends no money, messages no other human,
   deletes nothing of the owner's. Absolute; no quantity of evidence buys an
   exception.
5. **The announcement is durable** — the act cannot complete without its tell
   on the same durable path (§8.3).

### 10.2 Why the numbers in condition 2 are not a threshold deciding meaning

Because a reader will raise it, and should. Ten-in-90-days does not decide
whether any act is reversible. It decides whether a **human review** may open a
door, and it is evaluated over recorded outcomes — the "gates and evals"
exemption in Law 1, which is the same exemption every scoreboard in
`overnight/` relies on. Measuring is not programming. The number's real job is
to be fixed *now*, so that the person who wants the shelf wider later argues
against a number they did not choose.

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

### 10.4 Admission is keyed on a capability we hold, never on a host we visited

The worked example, because the criterion needs teeth and this shows it has
some:

Some providers accept a **client-generated identifier** — the caller mints the
record id, or supplies an idempotency key. Where that is true, the undo recipe
is complete before the act: *delete the record whose id we minted.* It depends
on nothing the counterparty returned. That genuinely passes §5's test, and it
does so for a reason that has nothing to do with the domain: not "calendars are
safe" (a domain list) but "an act whose undo addresses an identifier we minted
is undoable by us alone."

So the key is the capability, and the host is recorded as evidence rather than
as the key. This is why §3 declines the "proven host" successor: a host
allowlist keys the release on the identity of the party we are defending
against.

### 10.5 Withdrawal, also pre-registered

**Any single undo failure in production on an admitted act type demotes it to
Shelf 3 immediately, until re-admitted through the whole of §10.1.**

Pre-registered because after the fact everybody will have a reason it was a
one-off, and they will be persuasive, and the owner will be the one paying if
they are wrong. The demotion is automatic and its reversal is expensive on
purpose.

### 10.6 Abandonment, also pre-registered

The condition under which the right answer is to stop rather than widen:

**If, after eight weeks of the shelf being live, the admitted set is still only
local drafts and narration, and his measured taps-per-week has not fallen,**
then Shelf 2 cost complexity and bought nothing, and the answer is to remove it
— not to widen it until it justifies itself. Widening to recoup sunk cost is
how the dead premise gets rebuilt with better manners.

## 11. Observability, and what gets measured

- **Every refusal is recorded with its reason.** A shelf that refuses silently
  cannot be widened on evidence, because nobody can see what it refused. The
  count and the reason distribution are the input to §10.6.
- **Every announcement is paired with its receipt** in the feed, per moment 31.
  An announcement with no receipt behind it is the defect, not a display bug.
- **Undo latency and undo outcome** are recorded per act type — the raw
  material for §10.1 condition 2 and the trigger for §10.5.
- **Taps-per-week** is the product metric this card exists to move. It is
  measured before the shelf ships, or §10.6 is unanswerable.

## 12. Law compliance

- **Law 1.** The meaning question ("what would undo this?") goes to a model
  with full context, asked alone, four-state, floor polarity. The release
  decision is a structural property of a stored artifact — a seatbelt check on
  what a plan depends on, not on how a sentence was worded. No word list, no
  domain list, no threshold decides reversibility. §10's numbers govern a human
  door and are evaluated over outcomes (gates-and-evals exemption); §10.3's set
  can only refuse.
- **Law 2.** This spec introduces no tape. If an implementation needs some, it
  ships with a `TAPE:` comment naming `overnight/tape_gate.py`, a registry
  entry, and a ledger line in `HARNESS-LAWS.md` — three edits, one diff.
- **Law 3.** §10.1 condition 2 is live-only, and §8.5's guard change is not
  fixed until its leg is green against the live backend. The deploy-then-verify
  rule applies; `railway up` reports success while failing.
- **Law 4.** This file is the state. The dead premise (§3) is recorded here so
  it is not re-derived. Any re-proposal of the struck auto-run design, and its
  outcome, gets written the day it is made.
- **Law 5.** Fix order respected: this is not a rule written while she is deaf
  or blind. It is structure (step 5), and it is seatbelt-shaped — it examines
  what a plan touches and what its undo depends on, never what the owner's
  words meant.
- **Law 6.** §13.

## 13. Decisions made without the owner, and why

1. **The card's headline example does not ship on day one.** A
   free-cancellation booking fails §4's rule. Deciding otherwise means
   rebuilding the design three passes killed. If Omar reads the ruling as
   requiring bookings on day one, that is his call and this file gets amended
   rather than argued — but the amendment has to say which untrusted evidence
   it is choosing to trust, and name who eats the no-show fee.
2. **Shelf 2's day-one value is mostly voice, not permission.** §6.2. This is a
   smaller claim than the card's title and it is the honest one.
3. **The "proven host" successor is declined**, not deferred. §3, §10.4.
4. **No reversibility classifier, including no model-returned boolean.** §5.
   This is the substantive content of the review the card assigned to Jose, and
   it is a refusal of the card's own framing.

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
- *"Day one admits almost nothing, so why build it."* Because the machinery —
  pre-written undo plan, durable announcement, compensating plan, receipt —
  is the expensive part and it is proven on the one act type where the receipt
  is first-party by construction. And because §10.6 pre-registers the
  conditions under which "almost nothing" is the verdict rather than the
  starting point.
- *"§8.5 is scope creep."* It is the opposite: without it, the act of adding a
  third `Consequence` value turns off the only database-level backstop for the
  new lane. It is the precondition, not an extra.
- *"The undo could still fail."* Yes. It fails **loudly** (§8.1), it demotes
  the act type automatically (§10.5), and on day one its evidence is our own
  row. Silence is the failure this spec is built against; failure is not.
- *"Nothing catches a persuasive model writing fiction for an unadmitted act."*
  Correct, and stated as the residual risk in §8.4 rather than papered over.
  What contains it is that the set is not the model's to widen.
