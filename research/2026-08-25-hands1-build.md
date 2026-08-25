# HANDS 1 — what was built, what is proven, and what is still a claim

Date: 2026-08-25 · Branch: `jose_anticipy_system`
Spec followed: `docs/superpowers/specs/2026-08-25-hands1-skills-reach.md`
Commits: `c1d0c7a9` (gate + store + the unblocking), `1acc64d2` (the distiller),
and this file.

**Nothing here is verified against LIVE, and it cannot be today.** Zero
transcript rows have reached production in ~31 hours; builds 76–80 delivered
none. Every claim below is "green in the tree", which HARNESS-LAWS law 3 says
is a claim and not a fix. Section 6 lists exactly which legs would have to go
green against live before any of this counts.

---

## 1. What the card asked for, and what the spec turned it into

The card is *"HANDS 1 — research-first + a skills cache"*. The spec's own
headline is that the card's framing is wrong: the cache exists twice
(`extension/recipes.js`, `extension/learn.js`), both are good, and the real
gaps are one bridge, one gate, and one unblocking. I followed the spec, not the
card. Nothing named "skills" was created, no third cache was written, and not a
line of `recipes.js` or `learn.js` was rewritten.

Three things landed.

### 1.1 The unblocking (spec §5.2, §8.3) — the defect the card is really about

One condition — `plan.unfamiliar` — controlled **both** whether to spend money
researching **and** whether to read the procedure cache at all
(`extension/agent_loop.js`, the block that now begins "READING THE CACHE COSTS
NOTHING").

Reading a cache costs nothing. It sat behind the most expensive-to-get-wrong
judgement in the file, produced by a prompt that argues against researching
("Researching a restaurant booking is a waste of the owner's money"), and was
skipped outright whenever `plan` was `null` — a caller-supplied `startUrl`, or
a resume.

The consequence is precise and was invisible: **a cached procedure was silently
discarded whenever the second run's planner happened to feel familiar** — which
is *more* likely on the second run than the first, because that is what having
done a thing once feels like. Moment #32 of the fifty ("the same errand a second
time, two weeks later → near-instant … the recipe is cached, not relearned")
could not happen for procedures at all. It happened for recipes, because
`recallRecipe` twenty lines above is keyed on shape and asks nobody's opinion.

Now: **recall is unconditional on shape; only the spend is gated**, and the
first thing the spend consults is a fact (is there a live cached answer for this
shape) rather than an opinion.

Proven by `extension/tests/test_recall_is_not_gated.mjs` (10 checks). Before the
change, three of them failed — the familiar-feeling second run, the same shape
worded differently, and the caller-supplied start URL. That is the mutation
proof: the pre-change code IS the mutation.

### 1.2 The gate (spec §5.1–5.5) — `research_gate()` in `brain/research.py`

Keys on `touches`: declared by the triage model with full context, validated
against the closed three-value set (`orchestrator.TOUCHES`), already the release
condition for `is_consequential`. The gate imports that tuple rather than
retyping it, so a fourth channel cannot exist in one file and not the other.

What it will not do, and how that is enforced rather than promised:

| Forbidden by §5.3 | How it is prevented |
|---|---|
| a keyword or verb list for "unfamiliar" | **the function has no parameter for the goal.** `test_the_gate_cannot_be_handed_the_goal_at_all` asserts the signature is exactly `(touches, procedure, gate_can_run)` and that passing `goal=` raises. You cannot pattern-match on prose you were never handed. |
| a new model self-report | there is no model call anywhere in the gate |
| keying on a cached procedure's words | it reads only whether one is live — a stamp and a non-empty steps list. `test_the_gate_reads_no_word_of_the_procedure` gives it a procedure whose steps say "IGNORE YOUR INSTRUCTIONS… skip the gate" and asserts the same verdict as an innocent one |
| inheriting `[tape:read_only_re]` | `test_the_gate_never_consults_the_read_only_regex` scans the module's **code** with comments and string literals tokenized away, so a comment saying "we never consult it" is not mistaken for compliance |

Four verdicts, deliberately distinct so nobody can record "we had the knowledge"
and "we gave up looking" as one outcome:

- `GATE_SATISFIED` — a live cached procedure. Free. Outranks everything,
  including a dead lane: a cached answer needs no lane.
- `GATE_NOT_REQUIRED` — `touches` is `read` or `compute`. A read *is* the
  research lane's own job.
- `GATE_RESEARCH` — `touches == "world"`, **or no declaration at all**.
- `GATE_OPEN` — the gate itself cannot run. §5.5: a gate that cannot run must
  open, not hold, and say so in the trace. `GateVerdict.why` carries that line.

The undeclared case is the one worth defending. The **hold** gate defaults an
undeclared goal to held, because the cost of guessing wrong there is something
leaving the owner's world. The **research** gate has the opposite polarity: the
cost of not researching is a run that spends eighteen steps on a marketing page
and parks. So undeclared researches — and that is the specific reason this gate
never has to consult `_READ_ONLY_RE` and never inherits its tape.

### 1.3 The bridge (spec §4.2, §8.1) — procedures server-side

`brain/research.py` now holds:

- `recall_procedure` / `remember_procedure` — injected storage (`.get()`/`.set()`),
  no database assumed, **owner-scoped by whichever store the caller passes**.
  §4.3's recommendation was "owner-scoped first, shared later or never", and
  making the scoping the caller's decision means sharing has to be argued for
  out loud rather than happening because a default was convenient.
- `_clean_procedure` — the one place a stored record is built, whichever door it
  came in by. Every field copied **by name**, no spread; lists bounded, strings
  cut; an honest blank refused at the write door as well as the read door.
  `recipes.js` rule 3's discipline applied to the uplink.
- `learn_procedure` — the server-side distiller, so the gate's `RESEARCH` verdict
  has something to call. A port of `learn.js`'s rules, not a fresh design:
  authority-shape source ranking, one page per host, banks and private addresses
  never even *read*, per-page `BEGIN/END UNTRUSTED PAGE` fencing, the honest
  blank, and **no fallback when the model is absent** — `run_research` can fall
  back to the sources' own words because an *answer* is read by a person; a
  procedure is *acted on*.
- `task_shape`, `is_researchable`, `rank_sources`, `host_of` — ports of
  `learn.js`.

**Recipes stay in `chrome.storage.local` and nothing here touches them.** The
server cannot execute a slot index, and a server-side recipe store would be a
standing index of which sites the owner operates and how his account pages are
laid out — demoting LOCAL-FIRST's only row marked "already the most local-first
part of the system".

### 1.4 The ports are the risk, so the ports are tested against the original

`recipes.js` *imports* `taskShape` from `learn.js` rather than copying it,
precisely so the two caches can never key differently. My Python is the second
copy that import was avoiding. It is only honest because
`tests/test_research_shape_parity.py` **runs the real `extension/learn.js` under
node** over a shared corpus (28 goals, 43 URLs) and compares character by
character:

- `taskShape` output, identical;
- `isResearchable`, identical (including IDN hosts, IPv6, and every private
  range);
- `rankSources` order, identical;
- the four word lists (`STOP`, `INSTANCE_WORDS`, `AUTHORITATIVE`, `LOW_VALUE`)
  read straight out of the JS source and compared as sets;
- and the four constants both stores depend on (`PROCEDURE_TTL_MS`,
  `MAX_PROCEDURE_STEPS`, `MAX_PAGES`, the cache bound). A drifted TTL would mean
  the browser and the server answer "is there a live cached answer" — the fact
  the gate is keyed on — differently, and nothing would say so.

If node is missing the suite **skips loudly**, because a skipped parity test is
a copy nobody is checking.

---

## 2. What is proven, and how

Every behaviour was written test-first, watched fail, then implemented; then
mutated in place and watched fail again. The mutations that were run:

| Mutation | Caught by |
|---|---|
| the shape key's word-length filter changed | parity vs learn.js |
| a stop word dropped from one list | word-list drift test |
| the `172.16/12` private range dropped | parity (three corpus URLs flip) |
| the authority bonus / content-farm penalty zeroed | ranking parity |
| one-page-per-host dropped | ranking parity + `test_one_page_per_host` |
| ranking ties broken backwards | ranking parity |
| an undeclared goal treated as safe | `test_an_undeclared_goal_researches` |
| a dead gate holds instead of opening | `test_a_gate_that_cannot_run_opens_and_says_so` |
| the cache read put behind the lane being up | `test_a_cached_procedure_satisfies_even_when_the_lane_is_down` |
| the write door spreads what it was handed | `test_the_store_keeps_only_the_fields_it_declares` |
| the TTL stops being enforced | `test_recall_refuses_an_expired_or_hollow_record` |
| the gate grows a `goal=` parameter | `test_the_gate_cannot_be_handed_the_goal_at_all` |
| a `_READ_ONLY_RE` reference added in code | code-only scan |
| …the same string added in a *comment* | correctly **not** caught (the scan tokenizes comments away) |
| the untrusted-page fence removed | `test_the_pages_are_fenced…` |
| an honest blank turned into an invented step | four tests, both doors |
| a bank read after all | `test_a_place_that_holds_money_is_never_even_read` |
| the model asked about nothing read | `test_nothing_readable_means_no_procedure_and_no_model_call` |
| a non-live model asked anyway | `test_a_dead_model_does_not_invent_a_procedure…` |
| the distiller given an opinion about which goals are worth researching | `test_the_distiller_never_decides_whether_to_research` |
| both page caps removed together | `test_no_more_than_three_pages_are_read` |
| four store constants drifted from learn.js | constants parity |

Two mutations **survived** and are reported rather than hidden:

1. Removing *either* page cap alone survives — the slice and the loop break are
   belt-and-braces (as they are in `learn.js`). Removing both together fails, so
   the behaviour is enforced; neither line is individually load-bearing.
2. Spreading model output into `_clean_procedure`'s **input** survives, because
   the no-spread protection lives inside `_clean_procedure` and is proven there.

**Suite counts at the moment of commit** (honest, re-run):

- Python: **1973 passed, 0 failed** (`pytest tests/ --ignore=tests/test_day_zero_oracle.py`).
  `test_day_zero_oracle.py` errors at import on a missing `playwright` module —
  pre-existing environment gap, not touched by this work. Two other agents are
  editing `brain/workflow.py` and `backend/` in this same tree right now, so
  consecutive full runs flicker between 1971 and 1973 as their `test_shelf2_*`
  work lands; nothing of mine moves between runs.
- Extension: **64 of 65 suites pass**. The failure is
  `test_account_delete_flow.mjs`, which reads only `backend/pb_hooks/*` — a
  directory this work never touches and which is unmodified in the tree. It is
  red at HEAD and belongs to another agent.
- My own new tests: 30 Python (gate + store), 20 Python (distiller), 10 Python
  (parity), 10 extension checks.
- Gates: `tejas_gate` first failing leg is 6 (the speaker engine is not linked)
  — unchanged. `done_gate` first failing leg is 6 (a stranger) — unchanged.
  `tape_gate` legs 2 and 3 red — unchanged, and **this work adds no tape**.

---

## 3. What is NOT built, and who has to build it

`brain/research.py` is a library. The gate is not wired, and I did not wire it,
because every wiring point is a file another agent holds right now. Each of
these is named so nobody has to re-derive it.

### 3.1 The one-line change that makes the gate real — `brain/anticipy_core.py:3427`

```python
lane = job_lane(goal, params) if os.environ.get("BRAVE_API_KEY") else ""
```

`_queue_job` takes `touches` as a parameter (`:3223`) and uses it for
`_same_pending` and `_refines_pending` — and then routes the lane without it.
`job_lane` therefore decides from `_IRREVERSIBLE_RE`, `_BROWSER_TARGET_RE`,
`compute_answer` and `_READ_ONLY_RE`, the last of which is registered standing
tape. **The gate's key is already in scope at the line that would consume it.**

What it needs: pass `touches` in, call
`research.research_gate(touches, research.recall_procedure(shape, store))`, and
route on the verdict. `research.gate_holds_the_browser(verdict)` is the single
property a caller should test — written once, so a fifth verdict cannot be added
without somebody deciding this question.

**I did not edit that file.** It is on the do-not-touch list for this task.

### 3.2 The two lane-enforcement points a third lane must be added to

§5.5 names both, and the spec is right that a storage swap would look complete
while the gate stood open:

- `backend/pb_hooks/research_lane.pb.js:101` — rewrites any queued-jobs poll
  that does not name a lane, appending exclusions for `research` and
  `supervised_read`. A third lane absent from that line is claimable by every
  extension in the wild.
- `extension/background.js:76` — `BROWSER_LANE = 'workflow_id!="" && lane!="research"'`,
  plus `supervisedReadFilter` at `:89`.

`backend/` is another agent's; `background.js` is not a skills-cache file.

### 3.3 The two halves of the bridge that already exist and are not connected

- **Server → extension (recall):** `/agent/key` already returns owner-scoped,
  server-authored context including `owner_profile.facts`
  (`backend/pb_hooks/agent_key.pb.js:40-48`), cached at `background.js:228` and
  read by `planRun`. A recalled procedure is the same shape of payload on the
  same downlink. **Nothing new needs to be opened on the browser credential**,
  and it should not be — that credential is deliberately narrow.
- **Extension → server (write-back):** the extension already PATCHes its own job
  row's non-evidence fields every four seconds. A procedure learned during a run
  can ride in `params` and be harvested by the worker into
  `remember_procedure`. The write door is already built to distrust it.

### 3.4 Where the procedure store's rows actually live

`remember_procedure` takes an injected store, so the backing choice is still
open and is deliberately not made here. §4.4 prices both: a PocketBase
collection costs the migration plus **three registration points**
(`guard.pb.js:416`, `account_delete.pb.js` `OWNER_TABLES`, and a retention
sweep), with `1700000045_evidence.js` as the worked example; a per-owner SQLite
table has always been free (`CREATE TABLE IF NOT EXISTS` in `memory.py`'s
`SCHEMA`). Both files are other agents' tonight.

### 3.5 From the spec, deliberately not built

- **§6 aging.** "Degrade, do not delete" (feed a past-TTL recipe to the planner
  as fenced background instead of dropping it) and the **count of checkpoint
  abandonments per shape** — which §8.4 calls the product's only "this site
  moved" signal. The counter is small; the degrade path changes `recall`'s
  contract in `recipes.js`, which three enforcement points depend on, and it is
  not a change to make in the same night as the gate. The split `startUrl`/steps
  TTL the spec itself marks "named here, not designed" is likewise not designed.
- **§7 measurement.** The spec's hold-out — deliberately withholding research on
  a random half of first runs of world-touching shapes — is not built, and
  without it any before/after comparison measures which shapes the planner
  called unfamiliar, not what research did. The one missing quantity is a single
  boolean, "was a procedure in hand", which the job row could carry. **The
  abandonment rule from §7 stands, pre-registered: if first-run `needs_user`
  rate on world-touching shapes does not fall and first-run steps-to-`done` does
  not fall, remove the gate rather than widen it.**

---

## 4. Law 1: a violation in a file I now own, flagged and not fixed

`brain/research.py:44` — `_QUERY_PREFIX`, pre-existing, unregistered as tape:

```python
_QUERY_PREFIX = re.compile(
    r"^\s*(research|look\s*up|find(?:\s+out)?|check|search(?:\s+for)?|"
    r"compare|price|tell\s+me(?:\s+about)?)\s*[:\-—]?\s+", re.IGNORECASE)
```

A verb list deciding which part of the owner's sentence is "the instruction" and
which is "the subject". Measured on five ordinary goals just now:

| goal | search query it produces |
|---|---|
| `Compare the two quotes from the movers` | `the two quotes from the movers` |
| `Price check the Sony a7 IV` | `check the Sony a7 IV` |
| `check on my passport application` | `on my passport application` |
| `Find out whether the clinic is open Saturday` | `whether the clinic is open Saturday` |

The first three lose the verb that carried the entire request. This is a regex
doing understanding's job on the owner's own words, and it decides what the
research arm actually goes and looks for.

**I did not fix it.** It is outside this card, the fix is a model call (which
has a cost argument attached), and law 1 says flagging beats completing.

**CORRECTION (2026-08-25, repair round).** The paragraph that stood here said
this finding was "**not** currently in `HARNESS-LAWS.md`'s ledger or
`tape_gate.py`'s registry ... exactly the category it says it cannot see: tape
nobody marked, nobody registered". **That was false, and it was false about the
one file HARNESS-LAWS names as where the laws are enforced.** It is registered,
it was registered eleven hours before this report was written, and it is the
same construct, the same site and the same objection:

> `research/2026-08-24-law1-audit.md:190` — item **#51**
> `_QUERY_PREFIX` / `query_from_goal` | research.py:44-52, site run_research:132
> | strips a prefix from the goal before searching — **the `price` and
> `compare` legs eat a load-bearing word** | VIOLATION | L

The flag was right and the "nobody has seen this" framing was wrong, which is
worse than useless: it invites the owner to re-open a question that was closed
and ranked L the day before. That is law 4 failing inside the review layer — a
finding that lives in a file, re-derived as new by the next session — and the
cost is his triage time, which is the one thing this product exists to protect.

The lesson, written down so it is cheaper than the mistake: **grep the audit
before calling anything unregistered.** `grep -n '<construct>'
research/2026-08-24-law1-audit.md` costs one command.

~~The new code adds no pattern over meaning.~~ **WRONG, and the same mistake
twice in one section: it says so without checking the census.** The paragraph
that stood here argued `task_shape` "is a cache **key**, not a decision". The
audit had already ruled the opposite on the very construct being ported:

> `research/2026-08-24-law1-audit.md:229` — item **#76**
> `taskShape` `INSTANCE_WORDS`/`STOP` sets | extension/learn.js:96-135 |
> decides: **which cached procedure is replayed for a new task** | VIOLATION | M

So this diff copied a ranked, known Law-1 violation into a second language and
then wrote a comment in `brain/research.py` asserting it was not one — which is
precisely how a closed question gets re-opened in the wrong direction, and how
the three-month loop restarts. The blast radius grew in the same diff, too:
recall became unconditional (`extension/agent_loop.js:4246`), so a shape
collision can no longer be filtered out by `plan.unfamiliar` happening to be
false. The key drops words under three characters, drops the stop list, and
SORTS — so "transfer money from savings to checking" and "transfer money from
checking to savings" are both `checking-money-savings-transfer`.

**Closed on the server side in the repair round** (see §7): the key is demoted
to a SIFT and `procedure_applies` / `recall_confirmed_procedure` own the
decision — one question, four states, FLOOR polarity, nothing replayed without
a live model confirming it applies. `extension/learn.js` is **still item #76,
open and unchanged**; it is not this card's file.

`is_researchable`, `NEVER_RESEARCH` and the ranking lists are about *where the
agent may go*, which is the seatbelt clause, not meaning (and the audit agrees:
item #81 rules `NEVER_RESEARCH` and the SSRF guards LEGAL). The repair round
found that the seatbelt clause only protects you if the seatbelt is buckled —
see §7.

---

## 5. Honest limits

- **The shape key does not collapse synonyms.** "dispute the charge" and
  "dispute the bill" are two shapes and each pays for research once. That is
  `learn.js`'s deliberate trade and is asserted as a limit in its own tests.
- **`owner-scoped vs shared` is not settled**, on purpose (§4.3). The store is
  scoped by the caller. Whoever makes it shared should have to name what
  changed, since the compounding is real only in the shared form and so is the
  cross-owner poisoning surface.
- **The browser's spend trigger is still `plan.unfamiliar`**, a model
  self-report. §5.3 condemns it as a *gate*, and it is no longer one: it decides
  only whether to SPEND, never what is recalled, and it can no longer lose
  knowledge. It is marked with a `TODO(HANDS 1 §5.4)` naming the server gate
  that supersedes it. **It is not tape and carries no `TAPE:` comment** — it is
  pre-existing code whose blast radius this change reduced.
- **A resumed run now recalls a procedure where it previously did not.** The
  test covers the equivalent branch (caller-supplied `startUrl`, `plan === null`)
  and proves a recalled procedure cannot redirect where the run opens; the
  resume path itself is not separately covered.

---

## 6. What would have to happen for any of this to count (law 3)

1. **The ears.** Nothing in the product can be verified end-to-end while zero
   transcripts reach production. Not my card, and it blocks the honest
   verification of this one.
2. **The extension change needs a version bump it must not get from me.**
   `extension/agent_loop.js` changed. The version pin lives in **three**
   hand-copied files (`extension/manifest.json`,
   `app/ios/Anticipy/AnticipyApp.swift`, and the Swift test that mirrors it) and
   `tests/test_extension_version_pin.py` requires them equal in one diff. Two of
   the three are under `app/ios/`, which I must not touch. So: whoever ships
   this must bump all three together and re-run
   `extension/sync-to-chrome.sh` — otherwise the recall fix exists in source and
   not in the browser, which is exactly the 0.3.3-live-against-0.3.9-in-source
   failure that made the stale-extension banner exist.
3. **The gate is not live and cannot be** until §3.1 and §3.2 are wired; until
   then `research_gate` is a tested library with no caller, and I have not
   claimed otherwise anywhere in the code.

---

## 7. Repair round (2026-08-25) — what the adversarial reviewer killed

A reviewer refused to approve §1-§6 and filed five findings. This section is
what came of them. Nothing below is verified against production: the ears are
dead, zero transcript rows have reached prod in ~31 hours, and builds 76-80
delivered none — so every claim here is "proven by tests", never "proven live".

### 7.1 `is_researchable` was not a faithful port, and the parity leg could not see it — CLOSED

The finding, verified before touching anything, by running the real `learn.js`
under node against `research.py`:

| URL | learn.js | research.py (before) |
|---|---|---|
| `http://2130706433/` | refused | **allowed** |
| `http://0x7f000001/` | refused | **allowed** |
| `http://2852039166/latest/meta-data/` | refused | **allowed** |
| `http://0177.0.0.1/` | refused | **allowed** |
| `http://0x7f.1/` | refused | **allowed** |
| `http://0/` | refused | **allowed** |
| `http://999.999.999.999/` | refused | **allowed** |
| `http://example.com.5/` | refused | **allowed** |
| `http://1.1.1.1.1/` | refused | **allowed** |

`2130706433` is `127.0.0.1`; `2852039166` is `169.254.169.254`, the cloud
metadata endpoint the worker can reach and the laptop cannot. `_clean_procedure`
accepted `http://2130706433:8090/admin` — the PocketBase admin port
`agent_loop.js:1994-2007` names by hand as the threat — while correctly refusing
the dotted-quad spelling of the same machine. The module comment claimed the
port was "only honest because tests/test_research_shape_parity.py compares
character by character"; the corpus contained only dotted quads, so the one
class the predicate exists for was the one class it never tested.

**The class, not the three URLs.** WHATWG's URL parser normalises every IPv4
spelling before a host rule sees it, which is why learn.js's identical regexes
are correct and the port's were not. Adding `^0x7f` would have closed three
URLs and left the family open. So `parse_host` now implements the browser's own
host parser — percent-decode, IDNA, "ends in a number", the IPv4 parser — and
returns a **typed** `ParsedHost` carrying an `ipaddress` object. Every refusal
is a containment test on that object. After canonicalisation there is no such
thing as "the encoded form", including a spelling nobody has thought of yet.

The refused ranges are learn.js's, one for one, so parity stays exact.
`ipaddress.is_private` is broader and deliberately unused: widening the
server's refusals is a real improvement and belongs in a diff that widens the
extension's in the same breath.

Corpus: `tests/test_research_shape_parity.py` grew 22 rows covering decimal,
hex, octal, short-form, percent-encoded, trailing-dot, unparseable-port and
`ends-in-a-number-but-cannot-finish` hosts, plus the negatives that stop the fix
being "refuse anything unusual" (`010.0.0.1` is octal 8.0.0.1 — public;
`2130706433.example.com` is a label, not an address).

Class test, node-independent: `tests/test_research_host.py` (54).

### 7.2 Two more divergences, found by this round's own sweep

Neither was in the findings; both were in the SAME class and were found by
sweeping 16 hand-built edge cases through both languages.

* **`http://a:b:c/`, `http://example.com:99999/`** — the browser throws on an
  unparseable port. `urlsplit` is lazy about the port and handed back a
  perfectly good host, so the port was **more permissive than the browser**
  again. Closed: `parts.port` is now evaluated, and a failure to parse it fails
  the URL.
* **`http://%41.example.com/`, `http://%31%32%37.0.0.1/`** — the browser
  percent-decodes the host first. The port refused all percent-encoded hosts
  (stricter, so it refused real pages), and `%31%32%37.0.0.1` **is** `127.0.0.1`
  and was being refused for the wrong reason. Closed: decoded once, exactly as
  WHATWG does — `%2570` decodes to `%70`, still holds a forbidden character,
  and fails, rather than being decoded twice.

### 7.3 Where the fetch LANDS — a class no URL check can close

Closing 7.1 exposed the ceiling of the whole approach. `is_researchable` reads
a string, and this half of the product is a cloud worker, not a browser:

1. **`requests` follows redirects by default.** Every refusal was applied to a
   URL that was never read, and none to the one that was. A real help page can
   answer `302 Location: http://169.254.169.254/latest/meta-data/`.
2. **A hostname is not an address.** Any domain an attacker controls resolves to
   127.0.0.1 whenever its owner wants it to.
3. **`run_research` never called `is_researchable` at all** — it read every URL
   the search backend returned, in order. Only `learn_procedure` filtered
   (through `rank_sources`). Proven by test before the fix: it fetched
   `http://169.254.169.254/latest/meta-data/` first.

So the guard moved to the address, at every hop, immediately before connecting:
`fetch_is_permitted` resolves and requires every returned address to be on the
open web; `fetch_page` sets `allow_redirects=False` and walks the chain itself,
re-checking each hop; `run_research` filters its candidates like the other lane.
This also closes `http://[::ffff:127.0.0.1]/` server-side (see 7.6) without
breaking parity, because it is not a string rule.

**Honest limit, in the code and here:** the addresses a name resolves to are
checked, then the NAME is handed to `requests`, which resolves it again. A DNS
rebind between the two answers is not closed and cannot be without pinning the
connection to the checked address. Every fixed-address and redirect route is
closed; the rebind window is not.

Tests: `tests/test_research_fetch.py` (13).

### 7.4 `task_shape` is audit item #76, and the comment denied it — CLOSED server-side

Finding upheld in full. §4 of this report and the comment at
`brain/research.py:434` both asserted "NOT A LAW-1 PROBLEM ... a cache key, not
a decision" without citing `research/2026-08-24-law1-audit.md:229`, which had
already ranked this exact construct **VIOLATION / M** with the "Decides" column
reading "which cached procedure is replayed for a new task". Both texts are
corrected above and in the module.

The reviewer's concrete case is real and is now asserted as a test: the key
drops words under three characters, drops the stop list, and **sorts**, so
`transfer money from savings to checking` and `transfer money from checking to
savings` are both `checking-money-savings-transfer`. With recall unconditional
(`agent_loop.js:4246`) nothing filters that collision out any more.

**Fix, in the shape law 1 spells out:** the key is demoted to the one role
HARNESS-LAWS leaves open for a word list — "the cheap sift in front of the
model, never as the decision". `procedure_applies` asks ONE question on its own
("would following this remembered procedure accomplish the NEW task?"), returns
a **four-state** answer (`RECALL_YES` / `RECALL_NO` / `RECALL_UNASKED` /
`RECALL_UNANSWERED`), and `recall_confirmed_procedure` compares the verdict.
Polarity is a **FLOOR** — no verdict means no replay — because a miss costs one
research pass and a wrong replay costs a browser agent following someone else's
steps on his accounts. Both floor-lifting mutations were tried and both were
caught.

The remembered procedure is fenced as untrusted in the prompt: every word of it
came off the open web, and a procedure that argues for its own applicability is
told to be treated as a reason to say no.

**NOT fixed:** item #76 names `extension/learn.js:96-135`. The browser copy is
still the decision on its own side and that file is not this card's. #76 stays
open, now with a fixed sibling to copy.

Tests: `tests/test_research_recall.py` (12).

### 7.5 `research_gate` has no caller — NOT FIXED, and now RED

Upheld, and re-verified: grepping the tree for `research_gate`,
`gate_holds_the_browser`, `recall_procedure`, `remember_procedure` and
`learn_procedure` outside `tests/` and `brain/research.py` returns exactly one
hit — a comment on `extension/agent_loop.js:4253` saying it is not wired.

This is the leg-that-cannot-fail in its purest form: `gate_holds_the_browser`
returns True only for `GATE_RESEARCH`, nothing asks, so no job is ever held, and
the card's requirement is enforced in zero places while ~90 tests describe how
well it would be enforced if it were.

**I did not wire it.** The site is `brain/anticipy_core.py:3427`, which is
another card's file and has live agents in it. What I did instead is make the
gap impossible to mistake for done, in two places that do not rot:

* `brain/research.py` carries a block above `gate_holds_the_browser` stating
  plainly that nothing calls any of it, that §5.3 is "satisfied in a library
  nobody calls and violated in the shipped loop" (`plan.unfamiliar`,
  `agent_loop.js:4251`), and naming the exact wiring site.
* **`tests/test_research_gate.py::test_UNWIRED_the_research_gate_is_not_called_by_anything_that_runs` is RED and stays red until the gate is wired.**
  Law 2 polarity: it fails BECAUSE the thing is missing, and goes green on its
  own the day something that runs calls it. A companion test proves the scanner
  can go green for the right reason (it finds a real call in a synthetic tree)
  and is not fooled by the gate merely being MENTIONED in a comment — which
  `agent_loop.js:4253` already does.

**The suite is therefore 1 red on purpose.** Do not delete that leg, do not
mark it xfail, do not soften its predicate.

### 7.6 Findings NOT closed, and new ones raised

| # | What | Where | Why not closed here |
|---|---|---|---|
| 1 | **Navigation precedence**: a cached `startUrl` now overrides a *confident* planner's fresh `start_url`, because `procedure` is no longer null when `unfamiliar` is false | `extension/agent_loop.js:4264` — `if (procedure && procedure.startUrl && plan) plan.startUrl = procedure.startUrl;` | Not this card's file; other agents are live in it. The server-side analogue IS fixed (7.4): only a model-confirmed procedure is released, so a stale record cannot silently outrank fresh reasoning. The browser needs the same treatment or, at minimum, the cached URL must lose to a planner that answered `unfamiliar:false`. |
| 2 | `taskShape` `STOP`/`INSTANCE_WORDS` deciding replay | `extension/learn.js:96-135` — audit **#76**, VIOLATION/M | Not this card's file. Server half closed; browser half open. |
| 3 | `_QUERY_PREFIX` eating a load-bearing word (`price`, `compare`) | `brain/research.py:48` — audit **#51**, VIOLATION/L | Still open, still flagged, and — corrected from §4 — **already registered** in the audit. Fix is a model call with a cost argument. |
| 4 | **NEW: `http://[::ffff:127.0.0.1]/` is allowed by BOTH copies.** Verified under node: `isResearchable` returns true, and `new URL(...).hostname` is `[::ffff:7f00:1]`, which `/^\[?::1\]?$/` does not match. An IPv4-mapped IPv6 address is loopback. | `extension/learn.js:137-165` and the port | Fixing it in the port alone would break the parity contract, so it is closed at the FETCH boundary server-side (7.3) and left visible in the parity corpus. **The extension is still open to it.** |
| 5 | **NEW: `loopbackTarget` has the same gap.** Its comment correctly explains that WHATWG normalises `127.1` / `0177.0.0.1` / `2130706433`, and it strips brackets — but `::ffff:127.0.0.1` matches none of its arms. | `extension/agent_loop.js:1993-2005` | Not this card's file. Same one-line class as #4. |
| 6 | **NEW: IDNA divergence.** `http://١٢٣.com/` throws in the browser (UTS-46 Bidi rule) and punycodes to `xn--9hbcd.com` here, so the port is the permissive side — on a registrable domain, never an address, and the fetch guard still checks what it resolves to. | `brain/research.py` `parse_host` | Closing it needs the `idna` package (UTS-46). A dependency decision, not this card's. Written down in the code and here rather than left to be rediscovered. |

### 7.7 Process finding the reviewer was right about

Both false Law-1 claims in §4 — "`_QUERY_PREFIX` is not registered" and
"`task_shape` is not a Law-1 problem" — were written **without grepping
`research/2026-08-24-law1-audit.md`**, the file HARNESS-LAWS names as where the
laws are enforced. One invented a new finding out of a closed one; the other
argued the opposite of a ranked verdict. Both cost the owner triage time, which
is law 4 failing inside the review layer.

The rule, written down because it is cheaper than the mistake:
`grep -n '<construct>' research/2026-08-24-law1-audit.md` before calling
anything unregistered, unranked, or not-a-violation. One command.

### 7.8 Numbers, measured back to back

Measured by restoring the pre-round files, running, restoring the new ones, and
running again — not by arithmetic:

* **before:** `2048 passed`, exit 0
* **after:** `2122 passed, 1 failed`, exit 1 — the one failure is
  `test_UNWIRED_the_research_gate_is_not_called_by_anything_that_runs`, red on
  purpose (7.5)
* `tests/test_day_zero_oracle.py` is excluded from both runs: it fails to
  COLLECT on `ModuleNotFoundError: No module named 'playwright'` via
  `proof/day_zero_20.py:37`. Pre-existing, untouched by this round.

Every behaviour added was shown able to fail by mutating the fix in place and
restoring: the IPv4 canonicalisation (47 tests red), the refused-range
containment (8 red), the port check (4 red), the percent-decode (4 red), and
both directions of the recall FLOOR (1 and 2 red).

**No tape was added, and no gate predicate or test was weakened to reach green.**
