# `_CLOCK_ACTION_SOURCE_RE` — the verb list that decided whether a sentence was an errand

**Date:** 2026-08-24 · **Branch:** `jose_anticipy_system` · **Audit item:** 11, severity H
**Scope worked:** `brain/`, `tests/`, `HARNESS-LAWS.md`, `research/`
**Verdict:** REPLACED with a model judgement. Not registered as tape. The audit entry is
corrected in place.

Four waves flagged this and each correctly declined to fix it inside its own scope
(`research/2026-08-24-fence-correction.md` is the fourth). This is that fix.

---

## 1. What it actually gated, with evidence

The regex lived at `brain/anticipy_core.py:937` and had exactly **one reader**, at
`brain/anticipy_core.py:3633`, inside `Anticipy.clock_tick()`:

```python
selected = [l for l in shown if not loop_ids or l["id"] in loop_ids]
if goal and not any(_CLOCK_ACTION_SOURCE_RE.search(
        str(loop.get("source") or "")) for loop in selected):
    print(f"clock: reminder has no owner-authored task — dropping model goal {goal!r}")
    goal = None
```

`grep -rn _CLOCK_ACTION_SOURCE_RE` finds no other call site anywhere in the tree — only that
definition, that reader, and three documents talking about it.

**The path.** `brain/worker.py:3222` runs the clock every `CLOCK_EVERY_SECONDS` (30 min),
gated by quiet hours and an outreach budget. `clock_tick()` reads `Memory.open_loops()`
(`brain/memory.py:710`), drops loops with no `source` quote, caps the payload at ten, and asks
`CLOCK_SYSTEM` whether to reach out. The model replies with `initiate`, `say`, `goal`,
`loop_ids`. `source` is the **episode text** — the owner's own line, verbatim, as recorded
when the commitment node was minted (`brain/memory.py:741-747`).

**What changes on a match versus a miss.** On a miss the `goal` is set to `None` and nothing
else changes: `say` still goes out, `notify_owner` still fires, the caller
(`brain/worker.py:3236-3243`) still stamps `last_outreach_ts` and writes these `loop_ids` into
`reached_loop_ids` **permanently**. On a match the goal survives to `_queue_job` — a real
browser job, `hold=is_consequential(goal)`, a card on his phone, a `LoopRecord` in
`status_report()` and `briefing()`.

So a miss is not "nothing happens". It is: *the work is silently dropped, the reminder goes
out anyway, and the loop is marked raised forever.* A wrong miss costs that loop its one
chance, permanently.

---

## 2. Meaning or mechanism — honestly, in both directions

**It was two duties welded into one line, and only one of them was about words.**

### 2a. The meaning duty — a VIOLATION, and the audit understated it

The regex read `loop["source"]` — a human sentence — and decided whether it *meant* an
obligation. That is Law 1's canonical shape, the same shape as `_READ_ONLY_RE`, on the path
that mints goals from stored facts. There is no reading of it as a seatbelt: it does not ask
what a plan *touches*, it asks how a sentence was *worded*. Law 1 draws that line explicitly.

It is worse than "a pattern deciding meaning". It decided meaning **in direct contradiction to
the doctrine the same repo teaches its own model twelve hundred lines away.**
`brain/orchestrator.py:143-157` tells the triage model, at length, that an obligation reaches
her by more routes than a speech act:

> "AND — this is the one ambient listening exists for — an obligation he ALREADY HAD, which
> these words merely REVEALED… 'I forgot to cook for my kids this afternoon', 'the VAT return
> is due on the seventh'… **measured 2026-08-20, treating it as the only way sent half of all
> real errands to 'nobody'**, and the ones it dropped were the ones nobody would ever think to
> ask for."

The verb list was that exact mistake, re-committed downstream, after the measurement that
condemned it.

### 2b. The mechanism duty — LEGAL, undeclared, and load-bearing

`not any(pred(x) for x in xs)` is `True` when `xs` is **empty**, whatever `pred` is. So when
the model named only loop ids we do not hold, `selected` was `[]` and the goal was dropped —
**by the arity of `any()`, not by the regex.** Nothing else in the method catches that:

* the unreadable-`loop_ids` drop (`:3624`) only covers ids that are not digit strings; `[99]`
  is perfectly readable;
* the guest fence (`:3716`) has `named == []`, so it falls to the unnamed branch, whose
  `bool(selected)` is `False` and never fires.

**That duty is legal.** It reads ids against rows we hold and no English at all — mechanism,
not meaning. It was also invisible: nobody had written it down, and it is precisely the shape
`overnight/tape_gate.py` was rebuilt around this week (a check that an extract-method refactor
retires without anybody softening a predicate).

**So the violation was narrower than "the whole regex", and the legal half was in more danger
than the illegal one.**

---

## 3. Failure scenarios — reproduced, not argued

Driving the real `_CLOCK_ACTION_SOURCE_RE`:

| sentence | verb list | truth |
|---|---|---|
| `the VAT return is due on the seventh` | **no match** | a real errand |
| `we're completely out of the good coffee` | **no match** | a real errand |
| `that filling has been aching for a week` | **no match** | a real errand |
| `I forgot to cook for my kids this afternoon` | **no match** | a real errand |
| `Book Earls for Friday at 7` | **no match** | a direct instruction |
| `Tell Priya the invoice is still outstanding` | **no match** | a direct instruction |
| `Can you believe Tejas said that?` | match `Can you` | chatter |
| `Please, that is ridiculous` | match `Please` | chatter |
| `I'll be honest, that movie was terrible` | match `I'll` | chatter |
| `I have to say, the coffee here is amazing` | match `I have to` | chatter |
| `I promised to never watch that again, ha` | match `I promised to` | chatter |

The first four are the four sentences `orchestrator.py`'s own prompt names as the reason
ambient listening exists. **The verb list dropped every one of them.**

### The concrete product failure, end to end through `clock_tick()`

**A — the wrong-drop.** Store holds one open loop, `what="file the VAT return"`,
`source="the VAT return is due on the seventh"`. The clock wakes, the model says
`initiate:true`, `goal:"prepare the VAT return filing"`, `loop_ids:[1]`. Observed:

```
clock: reminder has no owner-authored task — dropping model goal 'prepare the VAT return filing'
goal = None | queued = []
```

He gets a text about the VAT return. Nothing is prepared. The loop is written into
`reached_loop_ids` and **is never raised again**. The one errand ambient listening exists to
catch is the one shape the fence cannot see.

**B — the wrong-fire.** Store holds one loop whose source is `"Can you believe Tejas said
that?"`. The model proposes `goal:"book tickets for the movie"`. Observed:

```
goal = book tickets for the movie | queued = [('book tickets for the movie', True)]
```

A consequential card, held for approval, buzzing his phone, minted off a rhetorical question.
This is the "invented human being" family from the Tejas call, reached through the clock.

**C — the load-bearing case.** One-loop store, model names `loop_ids:[99]`. The goal is
dropped — and with the regex mutated to match everything it is *still* dropped, because
`selected` is empty. Confirms §2b: the arity was doing the work.

---

## 4. The option taken, and why not the other two

### Not "show it is legal"

Half of it was, half of it was not, and the illegal half is wrong in both directions with
receipts. The audit's row is corrected rather than retracted: it said "decides whether the
owner's own words expressed an obligation", which is right, and it missed that the same line
was also carrying a mechanism check nothing else could carry.

### Not "register it as tape"

Law 2 buys **time** for a fix that is genuinely a larger piece of work. This one is not.
`brain/orchestrator.py` already holds three worked examples of exactly the needed shape —
`party_verdict`, `ends_in_the_world`, `check_sufficiency` — each a single question put to a
model at the point of use, each replacing a pattern that was getting a meaning question wrong.
Copying the fourth cost ~110 lines in one file plus one call site. Registering tape would have
cost three coordinated edits, a permanently red leg, and a census two agents were editing in
the same hour — **more process than the fix.** Choosing tape here would have been choosing the
middle option because it was easiest, which is the thing the brief forbids.

### Taken: replace it with a model judgement

`brain/orchestrator.work_is_licensed(llm, quotes, goal)` — new, sitting beside its three
siblings. `LICENCE_SYSTEM` asks one question and nothing else: *do these quoted words put the
OWNER on the hook for the work described?* It carries the doctrine the verb list contradicted
(revealed obligations count; a fact stored for recall does not; wording is not the test) and
the failure this fence exists for (*"FALSE ALSO when the words do carry a real obligation but
the described work does not serve it — that work was invented rather than heard"*).

Four states, not a bool, for the reason `party_verdict` gives at length: `LICENCE_YES`,
`LICENCE_NO`, `LICENCE_UNASKED`, `LICENCE_UNANSWERED`. One call for the whole set, mirroring
the `any()` the verb list stood in for — one quote licensing the work is enough.

`clock_tick()` now reads:

```python
if goal and not selected:                      # MECHANISM, and asked first
    print("clock: the loops it named are not loops I hold ...")
    goal = None
if goal:                                       # MEANING, put to a model
    licence = work_is_licensed(self.llm, [l.get("source") for l in selected], goal)
    if licence != LICENCE_YES:
        print(f"clock: nothing he said licenses preparing this ({licence}) ...")
        goal = None
```

**Why a call at the point of use rather than a label stored at mint.** The brief's preferred
shape is "a model decides, you store the label, later code compares labels", and I checked
whether that was reachable here. It is not, today, without a store change:

* `owes` is the right label and triage already produces it — but **it is only ever persisted
  when it equals `"other"`** (`brain/anticipy_core.py:1671` is the sole write). There is no
  stored positive verdict to compare against.
* Writing the positive one through `attribute_commitment` would **clobber the `"other"` mark**
  (`brain/memory.py:795` assigns unconditionally), which is exactly the fence-destroying bug
  the wave before this one spent a night removing.
* Several `hear()` paths mint a commitment and return before the attribution block ever runs
  (`:1349`, `:1380`, `:1401`), so a label written there would be absent for a whole class of
  loops.
* And decisively: **every loop already in every owner's database has no label.** A stored-label
  floor either refuses all of them (the clock stops preparing work) or waves them through (the
  fence is gone). Asking at the point of use works on legacy rows and new ones alike, because
  the quote is right there — the same argument this repo already made for preferring `owes`
  over `speaker` ("0% of live lines carry a voice verdict").

A stored label is still the better end state and it is a real piece of work: give the
commitment node its own additive authority key, written at every minting path, never able to
overwrite `owes`. That is a memory-schema wave, not this one.

**Why not just add the question to `CLOCK_SYSTEM`.** Because the clock model is the one that
*invented* the goal, and asking it to certify its own invention is not a fence. The repo has
measured the bundling failure twice: `party_verdict` exists because triage "answers it wrong
when both are bundled" (6/6 on a live conversation), and `check_sufficiency` exists because
"the field is one of eight in a JSON object and it loses" (7 cases, zero moved; the same model
asked alone got 8/8).

**Polarity, stated because it is the whole design.** This is a **floor** — it asks whether
anything licenses preparing work at all. A floor with no verdict has no authority, so
`UNASKED` and `UNANSWERED` both refuse. That differs from `party_verdict`'s house rule ("no
live model behaves exactly as before"), deliberately: the guest fence one block down is a
**ceiling** and must not fence without a verdict or it never lifts. Getting the two confused is
how a fence becomes a wall. `LICENCE_UNASKED` is unreachable in production — a keyless `LLM`
answers `CLOCK_SYSTEM` with heuristic triage JSON (`brain/llm.py:285`, `:396`) whose `initiate`
is falsy, so `clock_tick` returns long before this point — and refusing rather than waving
through means the fence has no branch that can fail open at all.

**Cost.** One extra call, only when the clock proposes a goal, at most once per 30-minute
window, and rarely then ("most reviews should conclude stay quiet"). Not `aux` — this is a
judgement that becomes an action. Law 5 sanctions exactly this: "frontier model on the few
decisions that become actions — cents per day."

---

## 5. Mutation testing

Eight mutations, each applied to the shipped code and run against the suite.

| # | mutation | caught by |
|---|---|---|
| 1 | delete the mechanism check entirely | **initially SURVIVED** — see below |
| 2 | floor becomes `if licence == "no"` (unasked/unanswered wave through) | 7 legs |
| 3 | send only `selected[0]`'s quote to the model | `test_every_quote_reaches_the_model_not_just_the_first` |
| 4 | a raised exception returns `LICENCE_NO` instead of `UNANSWERED` | `test_a_licence_call_that_raises_is_unanswered_not_a_no` |
| 5 | `answer is not False` — an unreadable reply reads as a licence | 5 legs |
| 6 | no live model returns `LICENCE_YES` | 2 legs |
| 7 | a wording shortcut around the model (the relapse) | 10 legs |
| 8 | the module-level regex comes back | `test_the_verb_list_is_gone_from_the_tree` |

**Mutation 1 is the finding.** Deleting the explicit `if goal and not selected` guard left
**every test in the tree green**, because `work_is_licensed` also refuses an empty quote list
(`LICENCE_UNASKED`) and does so *without calling the model* — so even the "no model was asked"
assertion still passed. A check I had just written to make a hidden duty visible was itself
unobservable. That is the same disease as the original: two agents found their own checks
fail-open tonight, and this would have been the third.

Fixed by asserting **which refusal fired**, via the operator-facing log line. Re-run: mutation
1 now goes red with a message naming the guard to restore. The redundancy is kept on purpose
and documented in the test — but it is now redundancy that can be told apart, not redundancy
that hides a deletion.

---

## 6. What changed, file by file

| file | change |
|---|---|
| `brain/orchestrator.py` | **+** `LICENCE_SYSTEM`, the four `LICENCE_*` states, `work_is_licensed()` |
| `brain/anticipy_core.py` | **−** `_CLOCK_ACTION_SOURCE_RE`; **+** the split call site; two stale comment clauses in the guest fence corrected |
| `tests/test_clock_authority.py` | rewritten: 32 legs incl. both error directions, the four states at the root, the mechanism guard, and the relapse guards |
| `tests/llm_fakes.py` | **+** `licence_reply()` — the shared prompt-router every clock double now uses |
| `tests/test_memory_knows_who_spoke.py` | 3 clock doubles made live and prompt-routing; `_clock_over` gained `licence_needs=` so the payload-cap scope test stays a scope test; **+** a control leg it was missing |
| `tests/test_goal_needs_a_card.py` | 1 clock double made prompt-routing |
| `research/2026-08-24-law1-audit.md` | row 11 marked **FIXED**; the override table's `:3419` row corrected; new "Fixed since this audit" section |
| `research/2026-08-24-fence-correction.md` | its standing flag marked closed, with the mechanism finding it could not have known |
| `HARNESS-LAWS.md` | under Law 1: the four worked examples of the legal replacement shape, and the floor/ceiling rule for the missing state |

### The tape census — what I changed about it: **nothing**

Stated plainly because the brief asked for it, and because
`overnight/tape_gate.py` was being edited by another agent in the same hour (their work landed
as `1d48dcc0` mid-session).

* **No tape was registered.** No `TAPE:` comment added, no `Tape(...)` entry, no ledger bullet.
* `AUDIT_UNDECLARED = (19, 20, 21, 22, 50)`, `AUDIT_UNDECLARED_COUNT = 5`,
  `AUDIT_DECLARED_COUNT = 0` — **unchanged, untouched.** Item 11 was never one of the five; it
  is a `VIOLATION` row, not a `TAPE, UNDECLARED` row.
* The audit-doc edit deliberately avoided the two rows `CENSUS_ROWS` matches. Leg 4 verified
  green afterwards: *"census intact (5 audited items, 5 registered); …agrees: 5 undeclared,
  0 properly declared"*.
* `TAPE:` marker counts in the two files I touched: `anticipy_core.py` 2 → 2,
  `orchestrator.py` 0 → 0.
* `overnight/tape_gate.py` exit code **2 before my change and 2 after**, verified by running
  `HEAD`'s copy of the gate against the tree with my `brain/` changes stashed and unstashed.
  The exit-2 state (leg 3 red: the audited five are still undeclared) is the other agent's
  baseline, not mine.

---

## 7. Scoreboards

* `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q --ignore=tests/test_day_zero_oracle.py -p no:cacheprovider`
  → **1469 passed, 2 failed**. Baseline at session start was 1440 passed / 1 failed. Net +29
  legs. Both failures are `tests/test_earls_live_failures.py` against `extension/*.js`, which
  is another agent's in-flight scope (`git status` shows four modified extension files); the
  second one appeared mid-session while I changed nothing in that directory.
* `python3 overnight/tejas_gate.py` → **8/8 PASS**, exit 0.
* `python3 overnight/tape_gate.py` → exit 2, legs 1/4/5 PASS, leg 2 RED by design, leg 3 FAIL.
  Identical to baseline. **Left red.**
* `python3 overnight/done_gate.py` → NOT DONE, first failing leg 3 (no model key). Unchanged.

---

## 8. Law 3 — what waits on LIVE

Repo-green is not done. Every test here scripts the licence answer; not one has asked a real
model the real question.

1. **Whether the model answers `LICENCE_SYSTEM` correctly on real quotes.** This is the whole
   fix. The prompt is written from measured doctrine, but a prompt is a hypothesis until a
   model has answered it on real lines. The cheap measurement: run the eleven sentences in §3
   through `work_is_licensed` against the live model and confirm the first six come back
   `true` and the last five `false`. **Until that runs, the claim "this is right in both
   directions" is a claim about the prompt, not about the product.**
2. **Whether the model emits parseable `{"licenses_work": …}` reliably.** An unreadable reply
   refuses, so a badly-behaved model degrades to a clock that never prepares work — silently,
   because the only symptom is a log line. Worth one live check and worth watching the
   `licence: unreadable reply` line after deploy.
3. **The latency and cost of a second serial call inside the clock tick.** Measured nowhere.
   Bounded by one call per 30-minute window, but unmeasured is unmeasured.
4. **Inherited, unchanged:** whether the model actually emits `loop_ids` when it sets a goal
   (`60ebd20f`'s residual). My mechanism check makes the *hallucinated*-id case explicit, but
   the *absent*-`loop_ids` case still falls into the permissive unnamed branch of the guest
   fence exactly as before.
5. **Deploy verification.** `railway up` reports success while failing, and prod has served
   stale code twice. Nothing here is fixed until an `is_it_live.py`-style check confirms the
   deployed brain has no `_CLOCK_ACTION_SOURCE_RE` in it.
