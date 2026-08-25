# HANDS 1 — where the learned knowledge lives, and what makes research a gate

> Status: SPEC. Not a plan, not a sequence, no code, no task list.
> Card: HANDS 1 — "research-first + a skills cache", PART 4 of 5.
> Roadmap: `docs/superpowers/plans/2026-08-24-five-organs-roadmap.md:138-148`
> (which is already more accurate than the card, and says "do not rebuild").
> Survey this checks rather than inherits: `research/2026-08-24-mouth-and-hands1.md`.
> Laws that bind: `HARNESS-LAWS.md` 1, 2, 4, 6. `design/LOCAL-FIRST.md` decides §4.
>
> **The card's framing is wrong and the honest answer is smaller than a redesign.**
> The cache exists twice, it is good, and nothing in it should be replaced. The
> gaps are: one of the two caches is unreachable except through a model's
> self-report; the server half of the product cannot see either; and "the
> research gate" as written cannot be built at all, because the thing it would
> gate on is not a question anybody should be asking.

---

## 1. What the card claims, checked against the code

Every row verified by reading the file this session, not inherited from the
survey. Two of the survey's own claims needed correcting; they are marked.

| The card says | The code says | Verdict |
|---|---|---|
| "SKILLS CACHE — a new collection" | Two caches exist. `extension/recipes.js` (621 lines) and `extension/learn.js` (387 lines). Nothing named "skills" anywhere. | **Wrong.** Building a third would be the fourth copy of one idea. |
| "after every successful run, write the recipe down" | Already done, and only on a *verified* done, never on a done-claim: `recordCleanRun` at `agent_loop.js:5144` and `:5494`, defined `:3958-3965`. | **Already built.** |
| "recalled BEFORE planning the next similar goal" | True for recipes — `recallRecipe` at `agent_loop.js:4016`, before `planRun` at `:4029-4031`. **False for procedures** — `recallProcedure` at `:4052` sits inside `if (plan && plan.unfamiliar)` at `:4050`, i.e. after planning *and* behind a model's opinion. | **Half built, and the unbuilt half is the expensive one.** See §5.2. |
| "site, steps, selectors, gotchas, last-verified date" | `recipes.js`: `steps`, `expect{url,index,field,role,label}`, `checkpoint`, `sources`, `compiledAt`, `runs`. `learn.js`: `startUrl`, `needs`, `steps`, `caveats`, `sources`, `learnedAt`. | **Present.** "last-verified" is `compiledAt`/`learnedAt` and is a *refresh* stamp, not a verification stamp — §6. |
| "SKILL AGING — stale recipes get re-verified, not trusted" | Expiry, not re-verification: `recall` returns `null` past 14 days (`recipes.js:166`), `recallProcedure` past 30 (`learn.js:354`). | **Not built — and should not be built as written.** §6. |
| "DEEP-RESEARCH GATE — any plan that will touch the world gets a research pass first, server-side, before the browser opens" | Implemented as none of *any*, *first*, or *server-side*. `learnProcedure` fires only on `plan.unfamiliar` (`agent_loop.js:4050`), a planner self-report (`:2660-2664`) from a prompt that says "Researching a restaurant booking is a waste of the owner's money" (`:2594-2595`). `plan` is `null` entirely when the caller gave a `startUrl` or the run is a resume (`:4029`). | **Genuinely missing.** §5. |
| "wire skills into both the server research lane and the browser agent's context" | Browser half done (`agent_loop.js:4016`, `:4052`, and `procedure` rides every step at `:5005`). Server half impossible today: both caches live in `chrome.storage.local` (`:4016`, `:4052`, `:4057`; `recipes.js:160,201`; `learn.js:351,362,371`). No `storage.sync` anywhere in `extension/`. | **The load-bearing gap.** §4. |
| "no column-migration machinery at all until tonight" | Was true, is now false. SQLite: `_ADDED_COLUMNS` + retrofit, `brain/memory.py:124-148`. PocketBase: the directory has grown from 45 to **48** files during this session — `1700000045_evidence.js` is present in the working tree (uncommitted at the time of writing, another agent's) and is a complete worked example of adding a collection. | **Stale within the hour, exactly as the card warned.** §4.4. |

**Correction to the survey, 1.** `research/2026-08-24-mouth-and-hands1.md`
closes with "a server-side skills cache does not need new capture — it needs a
distiller over rows that are already being written." **That is false and it
matters**, because it is the cheapest-looking path in the document. `jobs.trace`
is the joined `history` array of prose strings, each carrying the decision JSON
truncated to 160 chars and the URL to 100 (`background.js:1361-1363`, written
from `agent_loop.js:5024`). `params._execution_journal` holds at most 18
entries, one per *distinct page fingerprint* rather than per step
(`agent_loop.js:4714-4724`), with `elements` sliced to 1000 chars on the way to
the row (`background.js:1370`). Neither carries `state.fields` at all — which
exists in the page map (`page_map.js:363`) and is what `fieldAt`/`stepFrom`
read to build a typing step's checkpoint (`recipes.js:385-401`, `:542-546`).
`compile()`'s own docstring says a run recorded without its state "cannot
compile" (`recipes.js:140-141`). **A server-side distiller over today's rows
could not produce a single checkpointed typing step, and steps without
checkpoints are precisely what rule 2 exists to forbid.** Server-side recipe
compilation is new capture, not a distiller.

**Correction to the survey, 2.** It reports "no file field in PocketBase, zero
hits" as a live fact. `1700000045_evidence.js` now exists in the working tree
(uncommitted at the time of writing) with a `type: "file"` field, a hook
(`backend/pb_hooks/evidence.pb.js`) and a retention sweep. It does not change this card's
conclusions; it does supply the precedent used in §4.4.

---

## 2. Non-goals

- **Do not replace `recipes.js` or `learn.js`.** §3 says what they get right.
  Nothing in this spec asks for a line of either to be rewritten. Both take an
  injected `storage` object with `.get()`/`.set()` and are pure by contract —
  no chrome, no DOM, no network (`recipes.js:71-76`, `learn.js:340-343`) — so
  every change contemplated here is at a call site, not inside a cache.
- **No third cache, and nothing called "skills".** The repo calls them recipes
  and procedures. A new vocabulary is how a fourth copy gets written.
- **No re-verification job.** §6 argues it is worse than what already runs.
- **No keyword, host-list or threshold test for "is this unfamiliar".** §5.3.
- **No change to what runs unattended.** This card is about knowledge, not
  authority. `is_consequential()` is untouched; SHELF 2 owns that question and
  its spec (`2026-08-24-shelf-2-redesign.md`) already fixed the shape of it.
- **Not a plan.** No tasks, no ordering, no estimates.

---

## 3. What the two caches already get right, so nobody trades it away

Read both in full. The rules below are load-bearing and a fresh design would
have to rediscover every one of them.

**`recipes.js` — four rules, each written against a specific disaster.**

1. **Two clean runs, never one** (`CLEAN_RUNS_REQUIRED = 2`, `:65`; enforced in
   `compileSteps` at `:282-292`, at the read door in `recall` at `:165`, and
   again in `nextStep` at `:220`). And the count is of *consecutive trailing*
   agreeing runs (`:290-291`) — runs 1 and 3 matching around a different run 2
   is a flaky page, not a route. One gate, three enforcement points, no second
   copy of the predicate.
2. **Every step carries a checkpoint**, and abandonment is total
   (`checkpointFailed`, `:232-273`; `agent_loop.js:4964-4971`). The checkpoint
   is not "is there a control at slot 12" but "is slot 12 still the control I
   recorded" (`:250-254`) — which is exactly the silent mis-click a shifted
   banner causes. There is no partial replay and the comment says there never
   will be (`:28-29`).
3. **A recipe may never carry a value the owner did not give this time.**
   Structurally, not carefully: `stepFrom` builds every action key by key and
   contains no spread (`:347-352`); a typing step has `needsValue: true` and no
   `text` key (`:392-397`); query strings are dropped from stored routes
   (`navTarget`, `:596-602`); dated routes refuse to compile (`DATED_ROUTE`,
   `:85`, `:357`); and `unfitToReplay` re-checks all of it at the *read* door
   so a hand-edited or downgraded cache entry dies rather than replays
   (`:508-515`, called at `:170` and `:223`). Even the stored `goal` string is
   the shape's own tokens, never the owner's sentence (`:293-303`), and even
   the checkpoint prose is cut before `[contains "…"]` so a field's current
   value cannot ride into storage (`cleanLabel`, `:548-562`).
4. **The commit is never replayed** (`:329-332`, `:223`, and `isCommit` at
   `:424-434`). Replay reaches the ready-to-commit state for almost nothing and
   stops; the last click goes back through the live gates.

And one structural decision worth more than the four rules: **replay is an
alternative source of one decision, not a parallel fast path**
(`agent_loop.js:4951-4960`). Every downstream guard — the external-effect gate,
at-most-once, the form auditor, `protectedInput` — runs on a replayed action
exactly as on a reasoned one. A fast path that skipped them is the copy without
the gates, and it is the one that books twice.

**`learn.js` — three rules plus the key everything hangs on.**

1. **What comes back is background, never instructions** (`:17-24`). Pages are
   fenced with per-reading `BEGIN/END UNTRUSTED PAGE` markers (`:294-298`), the
   system prompt names the injection case explicitly (`:66-68`), and the
   distilled procedure is excluded from the approved-scope set, so a value
   tracing only to a web page can never be typed and submitted.
2. **Read-only**, and stricter than the main loop: `NEVER_RESEARCH` refuses to
   even *read* a bank (`:35-36`), and `isResearchable` refuses every private,
   loopback and link-local host (`:137-163`) — because research runs *before*
   the loop's `taskAllowsLoopback` guard exists and would otherwise have opened
   the owner's own machine on a sentence a web page wrote.
3. **Paid for once**, keyed by `taskShape` (`:94-116`), which strips digits,
   months and weekdays so "the March bill" and "the April bill" are one entry —
   and which `recipes.js` *imports* rather than copies, on purpose, so the two
   caches can never key differently (`recipes.js:53-57`).

Plus two things a fresh design would not have: sources ranked by **authority
shape** rather than by vendor name (`AUTHORITATIVE`/`LOW_VALUE`, `:42-55`,
`rankSources` at `:170-192`) so it generalises to errands nobody anticipated;
and an **honest blank** — an empty steps list is treated as "learned nothing"
and deliberately *not* cached, so a hollow procedure cannot stop this shape ever
being researched again (`:305-314`).

**None of this is what is wrong.** Everything in §4 and §5 is about call sites
and reach.

---

## 4. Where the knowledge lives

### 4.1 There are two objects here, and the card treats them as one

| | Procedure (`learn.js`) | Recipe (`recipes.js`) |
|---|---|---|
| Derived from | the open web | the owner's own logged-in session |
| Contents | `startUrl`, `needs`, `steps`, `caveats`, `sources` (`:323-333`) | slot indexes, control labels, field names, page routes (`:352-414`) |
| Owner values inside | none, by construction — `needs` names a *category* ("an account number"), never a value (`:73`, `:325-326`) | none, by construction — rules 3 and its read-door twin |
| Ages in | years for the steps, weeks for the `startUrl` | days — it is bolted to one vendor's current DOM (`:59-63`) |
| Who can execute it | anyone, including the server | only a browser holding that session |
| What it reveals if read | that somebody researched a task shape | which sites this owner operates, and how his accounts are laid out |

They are the same idea at two altitudes, and **the altitude is exactly what
LOCAL-FIRST draws its line on.**

### 4.2 The recommendation

**Procedures travel. Recipes stay.** Stated as a rule in the repo's own words:
*the shape of a task travels; the route through a page does not.*

**Procedures go server-side.** `design/LOCAL-FIRST.md`'s own scoreboard already
rules on this object: *"Research arm — fine in the cloud FOREVER: it reads the
public web, not him. Only the QUESTION travels, phrased as a goal, not his
transcript."* A procedure is literally the distilled output of reading the
public web, and what travels to produce one is `plan.learn` — a search question,
capped at 200 chars (`agent_loop.js:2665`), which is a goal and not a
transcript. It is the same object the law already blesses, with the same
provenance. It also cannot be produced anywhere else: `brain/research.py` has
Brave + fetch + a cited-summary prompt, and its lane *fails the plan* when the
answer carries no citable URL (`worker.py:1283-1296`) — an evidence discipline
`learn.js` does not have. The cheap lane is the right lane, which is the card's
own argument, correctly applied to the half of the knowledge it fits.

**Recipes stay in `chrome.storage.local`.** Four reasons, in descending weight:

1. **The server cannot use one.** A recipe is slot indexes and control labels
   against a session that exists on one machine. `run_research_jobs`
   (`worker.py:1198-1320`) has no browser, no DOM and no way to act on a
   selector. "Wire skills into the server research lane" is satisfiable for
   procedures and is a category error for recipes.
2. **LOCAL-FIRST's scoreboard has exactly one row marked "already the most
   local-first part of the system": "Browser hands — his own Chrome on his own
   Mac".** Moving the recipe store server-side is the only change proposed in
   this card that would take a law-abiding row and demote it. Rule 5 of that
   file — "any new feature states its local-first posture explicitly, and 'we'll
   localize it later' requires naming the later" — has no answer here, because
   there is no later: a browsing-habit index has no on-device successor planned.
3. **The privacy object is different in kind, not degree.** A recipe store is a
   per-owner, deduplicated, long-lived index of *which sites he operates and how
   his account pages are laid out*, with the hosts already extracted into a
   `sources` list (`recipes.js:307-308`). A transcript is a record of a moment;
   this is a standing map of a life's logistics, and it is durable across the
   purge horizon of the rows it was derived from. The `jobs` row that produced
   it is one errand; the recipe is the pattern behind forty of them.
4. **What it costs is bounded and self-healing.** Recipes die with the profile
   and do not cross machines. Price that honestly: `MAX_RECIPES = 40`
   (`:69`), `RECIPE_TTL_MS = 14 days` (`:64`), and a recipe needs two clean runs
   of one shape to exist at all. A reinstall costs at most forty shapes' worth
   of second-run savings, and ordinary use rebuilds it inside a fortnight. That
   is a small recoverable loss. A server-side index of every site he uses is not
   recoverable, and it is not the sort of thing that gets un-collected.

**What each half buys, and what it costs.**

| | Buys | Costs |
|---|---|---|
| Procedures server-side | the card's "never pay for the same learning twice" becomes true on run 2 instead of never (§5.2); the research lane can produce them at a fraction of a browser run; they survive a reinstall and a second machine; they can be produced *before* the browser opens, which is the whole gate | one collection and its three registration points (§4.4); a shared poisoning surface if it is un-owned (§4.3) |
| Recipes local | the LOCAL-FIRST row stays green; no browsing-habit index exists to leak, subpoena or forget to delete; no new write surface on the browser credential (§4.4) | a reinstall or a second machine pays first-run price again, bounded at 40 shapes / 14 days |

### 4.3 The one genuinely open question: is the procedure store owner-scoped?

A procedure contains nothing about the owner. Its *key* — `taskShape` — is a
fact about him ("dispute-hydro-bill"), but that same string is derived from
`jobs.goal`, which is already a server-side owner-scoped column. So an
owner-scoped procedure store adds no new *kind* of fact, only a longer-lived
copy of one the product already keeps.

An **un-owned, shared** procedure store is strictly better on privacy and
strictly better on the card's own economics: it holds only public-web knowledge,
it has nothing personal to delete so it never touches `account_delete.pb.js` at
all, and the second owner to dispute a Hydro bill pays nothing. The compounding
the card calls the moat is real only in this form.

**And it is a cross-owner poisoning surface, which the per-profile version is
not.** Today a hostile page that gets itself distilled into a bad procedure
misleads one browser profile. Shared, it misleads everybody. What survives that
is already in place — the fence (`learn.js:291-298`), the exclusion from
approved scope (`:17-24`), `isResearchable` re-checked on the model's own
`start_url` by the caller (`agent_loop.js:4059-4076`), and `sources` retained on
every record so provenance is inspectable — so the blast radius is *misdirection
about where to open*, never authorization of a value or a commit. That is a
containable failure, but "containable for one owner" and "containable for all of
them" are different sentences and the second is unproven.

**Recommendation: owner-scoped first, shared later or never.** Un-owned is the
better object and the worse risk, and there is no measurement yet that says the
compounding across owners is worth anything — the product has one owner. Ship
the reach; earn the sharing. Whoever revisits it should have to name what
changed, not merely that it would be cheaper.

### 4.4 What "a new collection" actually costs here, checked tonight

Mechanically it is cheap and cheaper than the card assumed. The real price is
registration, and `1700000045_evidence.js` — which landed during this session —
is the complete worked example of paying it (uncommitted in the tree as this is written, so re-check it before relying on the line numbers):

- the migration itself (`backend/pb_migrations/`, now 48 files);
- **`guard.pb.js:416`** — the account-auth branch matches a hard-coded
  collection list by regex; a collection absent from it is 403 to the phone,
  and a collection added to it inherits that branch's owner-scoping rules;
- **`account_delete.pb.js:58-80`** — `OWNER_TABLES`. This file's own header
  records that a table missed here left personal residue surviving a delete
  (`:20-38`), and the `evidence` entry (`:77`) carries a comment explaining why
  nothing else would ever remove those rows;
- a retention sweep, because "a cap that is only written in a design note is a
  cap that does not exist" (`1700000045_evidence.js`, header) — the volume is
  5 GB, it has filled once and taken production down, and daily backups keep
  seven zips of `pb_data` on that same volume, so every stored byte is charged
  roughly eight times.

For the per-owner SQLite the picture is simpler: a new **table** has always been
free (`CREATE TABLE IF NOT EXISTS` in `SCHEMA`, `memory.py:33-118`, and the
`vetoed_facts` comment at `:107-110` says so), and a new **column** now has
`_ADDED_COLUMNS` + `_retrofit_columns()` (`:124-148`, `:459-478`) with a
shape-parity test guarding the two declarations against drift.

**Three of those four costs disappear if the procedure store is un-owned**, and
the fourth (retention) is already answered by the existing 30-day TTL.

### 4.5 The bridge already exists, in both directions

Neither half of the wiring needs a new surface on the browser credential — and
that credential is deliberately narrow: three fields on its own agent row, a
jobs *list* for its owner, GET/PATCH on one job record with four forbidden
evidence keys, and `events` POST only for supervised-read narration
(`guard.pb.js:196-300`). The comment at `:246-260` explains why that narrowness
matters: a claimant may describe its own progress and nothing else, because
client-authored values trusted as proof about the world is the shape of every
hole that file has closed. **A general read/write collection for the browser
credential is a widening of the browser's authority and this card does not need
one.**

- **Server → extension (recall):** `/agent/key` already returns owner-scoped,
  server-authored context on every key fetch, including `owner_profile.facts` as
  a JSON blob (`agent_key.pb.js:37-49`), cached into the extension at
  `background.js:228-243` and read by `planRun` at `agent_loop.js:2619`. A
  recalled procedure is the same shape of payload on the same downlink. Nothing
  new is opened.
- **Extension → server (write-back):** the extension can already PATCH its own
  job row's non-evidence fields — that is how `trace` and `params` are written
  every four seconds (`background.js:1388-1391`). A procedure learned during a
  run can ride into `params` and be harvested by the worker, on a surface that
  already exists.

The recall/write-back points on the browser side are one line each and already
shaped to receive: `planRun`'s payload takes fenced background blocks
(`agent_loop.js:2623-2634`), and `procedureBlock()` already renders exactly that
kind of block (`learn.js:200-221`).

On the server side there is currently **no** recall point at all: `job_lane` is
called at `anticipy_core.py:3406`, before the job row is written, and nothing
sits between it and the queue. That is what §5.4 is for.

---

## 5. The research gate

### 5.1 What decides that a plan touches the world: `touches`, and it already exists

The field is `touches` (the SHELF 2 spec corrected the card on the name and was
right). It is declared by the triage model with the full context in front of it,
under prose that names the stakes — *"This field decides what runs unattended
and what waits for the owner's word, so a wrong 'compute' or 'read' on a goal
that leaves a mark is the worst mistake this format allows"*
(`orchestrator.py:208-221`), with eleven worked examples at `:226-287`. It is
parsed at `orchestrator.py:548`, validated against a closed three-value set
(`TOUCHES`, `:333`) with anything else collapsing to `None` (`:549-550`), and
carried on the decision at `:384`/`:598`.

It is already the release condition for the analogous question: `is_consequential`
consults the deny-list first, then `touches == "world"`, then `explicit`, then
`touches in ("compute","read")` (`anticipy_core.py:586-612`) — a comment there
records that the first two attempts at this were a verb list and then a
calculator sniff, "both pattern-matching wearing different coats", and that the
model's declaration replaced them.

**And the lane router does not receive it.** `_queue_job` takes `touches` as a
parameter (`anticipy_core.py:3200-3202`) and uses it for `_same_pending`
(`:3371-3372`) and `_refines_pending` (`:3394-3395`) — and then calls
`lane = job_lane(goal, params)` at `:3406` without it. `job_lane`
(`:857-874`) therefore decides routing entirely from `_IRREVERSIBLE_RE`,
`_BROWSER_TARGET_RE`, `compute_answer` and `_READ_ONLY_RE` — the last of which
is **registered standing tape** (`[tape:read_only_re]`, `HARNESS-LAWS.md:126-136`),
whose ledger entry notes that the gate leg naming itself as tracker is green
while the regex still decides.

So the gate's key is not something to invent. **It is a model declaration that
already exists, is already validated, and is already sitting unused in the scope
of the line that would consume it.**

### 5.2 The recall/gate conflation is the actual defect, and it is worse than "opt-in"

The survey calls `plan.unfamiliar` opt-in research. It is that, and it is also
something more damaging: **one condition controls both whether to spend money
researching and whether to read the cache at all** (`agent_loop.js:4050-4058`).

Recall is a storage read. It costs nothing. It is behind the single most
expensive-to-get-wrong judgement in the file, and the prompt that produces that
judgement is written to bias toward "no" (`:2594-2595`), and the parse requires
*both* `unfamiliar: true` and a non-null `learn` (`:2660-2664`), and `plan` is
`null` outright on a caller-supplied `startUrl` or a resume (`:4029`).

The consequence is precise: **a cached procedure is silently discarded whenever
the second run's planner happens to feel familiar** — which is more likely on
the second run than the first, because that is what having done it once feels
like. "Never pay for the same learning twice" fails in exactly the case it
exists for, and it fails invisibly.

Note that the other cache does not have this defect: `recallRecipe` at `:4016`
is unconditional on shape alone, gated only by "is this a resume". That is the
correct discipline, already in the file, two dozen lines above.

**So the first thing the gate must do is separate the two questions:**

- **Recall is unconditional and keyed on shape.** No model in the loop, ever.
- **Only the decision to *spend* on research is gated**, and it is gated on a
  fact: *is there a live cached answer for this shape?*

### 5.3 What the gate must not key on

**HARNESS-LAW 1 forbids a pattern deciding meaning**, and "is this goal
unfamiliar" is a meaning question. Explicitly out of bounds:

- a keyword or verb list for unfamiliarity;
- a host allowlist ("we know Booking.com") — the SHELF 2 spec already declined
  a host allowlist for keying a release on the identity of the party being
  defended against, and the same objection lands here;
- goal length, token counts, or a similarity threshold against past goals;
- **a cheap filter in front of the model call.** This repo has shipped that
  shape and reverted it: the tape ledger records that "an early fix that ADDED
  compute verbs to the regex was itself a Law-1 violation and was reverted"
  (`HARNESS-LAWS.md:~130-133`). `plan.unfamiliar` is the same shape wearing a
  model's clothes — a cheap gate in front of an expensive capability, tuned by a
  prompt sentence to exclude the case the capability was built for.
- **and it must not key on a *new* model self-report either.** Replacing
  `unfamiliar` with a second, better-prompted `unfamiliar` is the same design.
  The fix is that nobody is asked.

### 5.4 What the gate is

Three inputs, none of them an opinion about familiarity:

1. **Recall by shape.** A live procedure exists → the gate is satisfied at zero
   cost, no model call, no research. *This is the card's "second time =
   instant", and it is the case that is broken today.*
2. **`touches != "world"` →** there is no gate. A read *is* the research lane's
   own job; routing it there is what `job_lane` already does.
3. **`touches == "world"`, or no declaration at all →** the research pass runs,
   server-side, before the browser may claim. Paid once per shape per TTL.

**On the undeclared case.** For the *hold* gate, an undeclared goal defaults to
held, because the cost of guessing wrong is something leaving the owner's world.
For the *research* gate the polarity is opposite: the cost of researching
unnecessarily is money and latency; the cost of not researching is a run that
spends eighteen steps on a marketing page and parks (`learn.js:5-9` records
exactly that failure, live). **So an undeclared goal researches** — and that is
the specific reason this gate never has to consult `_READ_ONLY_RE`, and never
inherits its tape.

**Why this answers the cost objection the current prompt is right about.** The
prompt's claim — researching a restaurant booking wastes the owner's money — is
*true per errand* and false per shape. Under this gate a restaurant booking
costs one research pass, once, for the life of the cached procedure; every
subsequent booking of that shape reads the cache. The card's "research, ALWAYS"
becomes affordable precisely because recall stopped being gated. The two halves
of this card only work as one change.

**And the judgement disappears.** "Is this unfamiliar" is replaced by "is there
a cached answer", which is a fact anyone can check, from either side of the
wire, without a model.

### 5.5 What "before the browser opens" costs structurally

Stated as shape, not as tasks. A world-touching job must not be claimable by a
browser until a research answer is attached or the pass has honestly returned
nothing. The machinery for lane-scoped claiming exists and has two enforcement
points that any third lane value must be added to, or it is a hole rather than a
gate:

- `research_lane.pb.js:101` rewrites any queued jobs poll that does not name a
  lane, appending exclusions for `research` and `supervised_read`. A third lane
  absent from that line is claimable by every extension in the wild.
- `background.js:76` — `BROWSER_LANE = 'workflow_id!="" && lane!="research"'`,
  the current extension's own filter, plus `supervisedReadFilter` at `:90-91`.

Both are named in this spec because the survey's "swap the storage adapter" path
does not touch them and would look complete while the gate stood open.

Two honest costs of gating: a research pass adds latency before the browser
opens on a *first* run of a shape (bounded — Brave + at most 3 fetches + one
model call, `research.py:28-30`), and a research lane that is down or keyless
must not deadlock the browser lane. The existing keyless fallback is the right
precedent: `run_research_jobs` hands a research job back to the browser lane
with `{"lane": ""}` rather than letting it sit forever
(`worker.py:1229-1240`). A gate that cannot run must open, not hold, and say so
in the trace.

---

## 6. Aging

**The 14-day recipe TTL is right, and the cliff is wrong.** The number has a
stated reason — a recipe is bolted to one vendor's current DOM and vendors ship
redesigns, "long enough to compound across a fortnight of daily errands, short
enough that a dead route cannot become folklore" (`recipes.js:59-63`). Do not
lengthen it. But `recall` returns `null` past the TTL (`:166`) and `prune`
deletes the record (`:483-487`), so a **monthly** chore never accumulates: two
clean runs, a 14-day clock, and it is gone before the third. It pays full price
forever and nothing anywhere records that this is happening.

**Degrade, do not delete.** A recipe has two halves with different half-lives.
The slot indexes and control labels rot in weeks. *Which site, which page, which
controls exist there* does not. Past TTL, stop replaying and start hinting: feed
the stale steps to the planner as fenced background — which is exactly the shape
`procedureBlock()` already renders (`learn.js:200-221`) and exactly the channel
`planRun` already accepts (`agent_loop.js:2623-2634`). The route stops being
executed and starts being knowledge, which is what it has decayed into.

**"Re-verified, not trusted" — the card's phrase — is already implemented, and
better than a re-verification pass would be.** When a site quietly changes one
selector, `checkpointFailed` (`recipes.js:232-273`) catches it at the moment the
step would fire, against the live page, and the run abandons the whole replay
and reasons live from there (`agent_loop.js:4964-4971`); two clean runs of the
new route re-compile it (`mergeRecord`, `:465-480`). That is continuous
verification at zero marginal cost, on the only page state that matters — the
one in front of the agent now.

**A periodic re-verification job would be worse on three counts** and should be
declined: it opens the owner's browser with no errand behind it (unattended,
visible, and for no benefit he asked for); it verifies against a page state that
may differ from the one the real run meets; and it would need its own lane,
approval posture and failure semantics for a signal the live path already
produces for free.

**The real aging gap is a missing signal, not missing verification.** A
checkpoint failure today writes one prose line into `history` (`:4969`) which
lands in `jobs.trace` and is counted by nothing. Nobody — not the owner, not a
gate — can answer "which sites changed under us this month". `lastVerified` is
the wrong field to add, because a stamp says only when someone looked. The
useful durable object is a **count of checkpoint abandonments per shape**: it is
the product's only available "this site moved" signal, it is derivable from what
the run already writes, and it is what would tell you a recipe should be dropped
early rather than waiting out its clock.

**The 30-day procedure TTL is one number doing two jobs.** `startUrl` is the
field that rots — help centres move, vendors reorganise — while `steps`,
`needs` and `caveats` ("you need the serial number", "there is a 30-day
deadline") age in years. One clock set for the fastest-rotting field throws away
the slowest-rotting knowledge with it. Split the expiry by field: let the
`startUrl` expire early and be re-derived, keep the rest. Named here, not
designed.

---

## 7. Does the deep-research gate pay for itself?

**Unmeasured, and the card's argument is not the strongest one available.**

**The counter-evidence is real and should be stated first.** For repeated
chores — the exact case "never pay for the same learning twice" is about —
the expensive part is already solved without any server involvement. From run 3
on, `recipes.js` replays with **no model in the loop at all**: the replay branch
at `agent_loop.js:4963-4993` produces `decision` and sets `replayed = true`, and
the entire `llmStep` call at `:5005` is skipped under `if (!replayed)` at
`:4995`. The research gate does nothing for those runs. Any claim that this card
makes repeated errands cheap is already false — they are already cheap, locally.

**Where research can actually pay is the opposite case: the first run of a shape
nobody knows.** That is also the run that produces the recipe, so the two
mechanisms are complementary rather than redundant — research is what makes run
1 *succeed*, and succeeding is the precondition for the two clean runs that make
run 3 free. `learn.js:5-9` records the failure it was built for: the planner
guessing a `start_url`, landing on a marketing page, eighteen steps of hunting,
then parking. The gate's whole value is in that tail.

**What would measure it.** The unit is a **shape**, never a run — a per-run cost
comparison will make the gate look bad forever, because it strictly adds a call
to every first run. Four quantities, three of which are already written:

| Quantity | Where it already is |
|---|---|
| steps to terminal | `jobs.trace` — the `history` lines, `background.js:1361-1363` |
| terminal status (`done` / `needs_user` / `failed`) | the `jobs.status` column |
| whether a recipe replayed, and for how many steps | derivable from the trace: the replay lines at `agent_loop.js:4990` and the abandonment line at `:4969` are distinct strings |
| whether a procedure was in hand | **the one thing missing** — one boolean, on the job row or in `params` |

**And none of it measures anything without a hold-out.** Comparing shapes that
were researched against shapes that were not measures which shapes the planner
called unfamiliar, not what research did — the current selection is exactly the
confound. A real measurement requires deliberately withholding research on a
random half of first runs of world-touching shapes for a fixed period. Say that
plainly, because the alternative is a plausible story that survives forever.

**The honest metric is cost per completed errand, not cost per run** — including
the runs that park at `needs_user` and are then done by hand, which are the ones
this feature exists to remove and are invisible to any per-run accounting.

**Pre-register the abandonment rule now, before anyone is invested** (the
convention `2026-08-24-shelf-2-redesign.md` established): if first-run
`needs_user` rate on world-touching shapes does not fall, and first-run steps to
`done` does not fall, **remove the gate rather than widen it to justify itself.**
Widening a gate that did not pay is how a cost becomes permanent.

---

## 8. What this spec concludes

**The cache is fine. The gaps are one bridge, one gate, and one unblocking of a
cache that is already built.**

1. **The bridge.** Procedures move server-side, where the research lane can
   produce and read them. Recipes stay in the browser, because the server cannot
   use one and because LOCAL-FIRST's only law-abiding row is the one that would
   be demoted. The split is: the shape of a task travels; the route through a
   page does not. Both directions of wiring already exist (§4.5) — a downlink at
   `/agent/key`, an uplink through the job row — and neither requires widening
   the browser credential.
2. **The gate.** It keys on `touches`, a model declaration that already exists,
   is already validated against a closed set, and is already in scope at the one
   line that routes the lane and is not passed it (`anticipy_core.py:3406`). It
   never keys on a self-report about familiarity, and it never consults a
   pattern. `touches == "world"` or undeclared, and no cached answer → research
   runs server-side before the browser may claim.
3. **The unblocking.** Recall is separated from spend. `recallProcedure` stops
   living behind `plan.unfamiliar` and becomes unconditional on shape, the way
   `recallRecipe` already is twenty-four lines earlier. This is the smallest
   change in the card and the one that makes "second time = instant" true.
4. **Aging degrades instead of deleting**, and "re-verified, not trusted" is
   declined as a job because `checkpointFailed` already does it continuously and
   better. What is missing is a durable count of checkpoint abandonment per
   shape — the product's only "this site moved" signal.

**Open, and deliberately not settled here:** whether the procedure store is
owner-scoped or shared (§4.3 — recommendation: owner-scoped first, and whoever
revisits it must name what changed); and whether the split TTL for a procedure's
`startUrl` versus its steps is worth the field (§6).

**Not answered by this spec, on purpose:** sequencing, any code, and how much of
HANDS 3's "library + skills in the browser context" this covers. HANDS 3
consumes this cache (`roadmap:59`); it does not change where it lives.
