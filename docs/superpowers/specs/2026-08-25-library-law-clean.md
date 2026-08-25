# LIBRARY — the two gaps at the door

**Card:** LIBRARY — VECTOR (fuzzy finder) → GRAPH (family tree) → RANK (the
librarian). `docs/BOARD-STATE-2026-08-24.md:128`.

Every item that card lists is about what happens to a fact once it is IN the
store: supersession, aging, confidence, provenance gating action, a vector
channel. Four of the five have landed. This spec is about the two things
nobody has a card for, and they are both at the DOOR:

1. **The only extractor that decides what a heard line contains, when the
   model does not answer, is a regex** — `_rule_extract`
   (`brain/memory.py:2523`). It decides who a person is (a capitalised word),
   what a commitment is (`I'll …`), and **who it was promised to** (`people[0]`,
   `:2535`). That is Law 1's forbidden question, answered by a pattern, on a
   path that runs in production. The 2026-08-24 audit recorded it as item **43,
   VIOLATION / TAPE-UNDECLARED, severity H**
   (`research/2026-08-24-law1-audit.md:177`).
2. **Nothing outside the deploy host can tell a degraded librarian from a
   quiet day.** The code says so in its own comment
   (`brain/memory.py:2437-2440`: *"a degraded brain looked exactly like a quiet
   day"*), and the one gate that can answer it — `overnight/consolidation_gate.py`
   — is unrunnable anywhere but the host, by design.

Neither appears in the Brief's section 9 open-problems list. Nothing else is
going to find them.

**Law 3, up front:** none of this is verified live and none of it can be
today. The ears are dead — zero transcript rows in ~31 hours, b82 compiled and
not installed on a phone. Section 8 says exactly which claims wait on a working
build and which I ran here.

---

## 1. `_extract` has four paths, not two, and the silent one is the worst

The docstring-level story is "live model, else rules". That is wrong. I ran
all four against the shipped code.

| # | Condition | What happens | Reports itself? |
|---|---|---|---|
| a | `self.llm is None` | `_rule_extract` — the regex — for every line, forever | **no. Silent.** |
| b | live model, JSON parses | the model's verdict | n/a |
| c | live model **raises** | one `print()` then `_rule_extract` (`:2436-2443`) | a log line, on the host |
| d | LLM object present, **not live** | `Extraction()`, empty, **no fallback and no print** | **no. Silent.** |

Path (d) is the one nobody wrote down, and it is the one the comment at
`:2437-2440` blames the regex for. Measured, keyless:

```
LLM().live -> False
chat(EXTRACT_SYSTEM, "I'll send Sarah the pitch deck tomorrow.", aux=True)
  mode='heuristic'  text='{"decision": "ignore", "goal": null, "reason": "..."}'
Memory(":memory:", llm=LLM()).ingest(...)
  -> {'entities': [], 'commitment': None, 'commitment_id': None, 'closed': []}
```

`LLM.chat` with no key does not raise — it returns the **triage heuristic's**
reply (`brain/llm.py:285`). That is valid JSON from a different prompt, so
`json.loads` succeeds, every key `_extract` wants is missing, and the empty
`Extraction` is returned as though the model had read the line and found
nothing in it. No exception, no print, no fallback.

The same thing happens with a **live key** whenever the provider returns prose
instead of JSON: `_extract_json` (`:2497`) returns the literal `"{}"` when the
reply contains no braces, which parses, so a refusal or an outage page reads as
"nothing in this line". Verified:

```
llm.chat -> "I'm sorry, I can't help with that."   (mode='openrouter')
ingest(...) -> {'entities': [], 'commitment': None, ...}   # silent
llm.chat -> raise RuntimeError("503 upstream")
ingest(...) -> {'entities': ['Sarah','deck','pitch deck'],
                'commitment': 'send Sarah the pitch deck tomorrow', ...}
              # the regex, with one print
```

**Path (a) is not a test rig, it is the deployed default when the key is
missing.** `brain/worker.py:3500`:

```python
memory = Memory(path=mem_db, llm=llm if llm.live else None)
```

`llm.live` is read **once**, at process start, from the environment. A worker
that boots without a key hands memory `llm=None` and then runs the regex on
every line for the life of the process, with nothing printed even once. A
worker whose key starts erroring later takes path (c) — the regex plus one log
line per line, into the log `is_the_brain_live.py:27` was written because
nobody queries.

`brain/anticipy_core.py:1024` does `Memory(llm=llm)` unconditionally, so any
directly-constructed `Anticipy` with a non-live LLM sits on path (d).

## 2. FIX, not REGISTER

**Recommendation: FIX. Delete `_rule_extract` and its three patterns; return
no verdict instead.**

### Why not REGISTER — the registration I wrote and threw away

For completeness, here is the entry that would have gone into
`overnight/tape_gate.py`. It is well-formed and it satisfies the letter of the
requirement: leg 2 reads every `KNOWN_TAPE` entry and is red for any that is
not `GONE`, so the predicate is genuinely impossible to pass while the text
lives.

```python
    Tape(
        tid="_rule_extract",
        rel="brain/memory.py",
        find="def _rule_extract(",
        what="a capitalisation regex and an `I'll ...` clause decide who a "
             "person is, what a commitment is, and WHO IT WAS PROMISED TO "
             "(people[0]) on every line, whenever the extraction model is "
             "absent or unusable",
        marker_home="_rule_extract",
        real_fix="the extractor returns NO VERDICT when no model answered, "
                 "the way _horizon and _fact_kind already do, and the test "
                 "double that needs a deterministic extractor lives in "
                 "tests/. Then _rule_extract, _COMMIT_RE, _NAME_RE and "
                 "_NOT_NAMES are DELETED.",
        ledger_needle="[tape:rule_extract]",
    ),
```

```python
# TAPE (HARNESS-LAWS.md Law 2). A regex decides who a promise was made to —
# `people[0]`, the first capitalised word — whenever no model answered. The
# real fix is an honest no-verdict, the way _horizon and _fact_kind already
# refuse to guess. Tracked by overnight/tape_gate.py; that leg stays RED
# until this function is deleted, not until it is improved.
```

Three reasons that is the wrong answer, and the third is the decisive one.

**(i) Law 2 is for emergencies.** *"If a string-level patch must ship in an
emergency"* (HARNESS-LAWS.md Law 2). There is no emergency. The real fix is
smaller than the registration: registration is three coordinated edits in three
files, forever; the fix is a deletion and a stub moved into `tests/`.

**(ii) This tape is worse than nothing, so "better than nothing" cannot
justify it.** Tape is supposed to hold something up. `commitment_to =
people[0]` does not degrade the graph, it **fabricates** in it — a promise
attributed to whichever capitalised word came first. The recorded failure this
whole laws file exists for is *"one invented human being"*
(HARNESS-LAWS.md, the Tejas call). A guard whose failure mode is the product's
signature failure is not a stopgap.

**(iii) The gate cannot make a sixth registration visible.** This is
structural, and I checked it against the gate rather than assuming:

- `leg_3_audited_five` (`tape_gate.py:989`) is the only leg that requires a
  `TAPE:` comment to exist, and it iterates `t.audit_item in census_ids` where
  `census_ids = AUDIT_UNDECLARED = (19, 20, 21, 22, 50)`. `_rule_extract` is
  audit item **43**. It can never be in that tuple: `AUDIT_UNDECLARED` is a copy
  of a dated measurement and the gate's own header forbids editing it
  (`tape_gate.py:753-757`).
- `leg_1_markers_are_registered` builds `claimed` **only from entries that
  already have a marker** (`tape_gate.py:846-850`) and then reports markers
  with no entry. **An entry with no marker contributes nothing and is never
  checked.** Leg 1 catches tape without a registration; nothing catches a
  registration without tape-marking. (Leg 5 implements exactly that missing
  direction for the ledger and says so; leg 1 does not.)
- Which leaves leg 2 — and **leg 2 is red by design and always red.** The
  gate's own header names this failure: *"a real failure arriving inside a
  permanent red is the I4 hole"* (`tape_gate.py:935-940`), which is why
  resurrection was deliberately moved out of leg 2 into leg 6. A sixth entry
  in leg 2 adds a line to a twenty-line block that is red every single day for
  reasons unrelated to it.

So registering buys a permanent red nobody reads, a marker no leg requires,
and the regex still running. That is the shape of audit item #21 — *a
declaration that reads compliant and enforces nothing* — one file over.

**This spec therefore adds NO entry to `KNOWN_TAPE` and moves nothing into
`CLOSED_TAPE`.** `tape_gate.py` stays exit 2 with leg 3 red for the five in
`anticipy_core.py` and `asking.py`. Nobody may report this work as moving that
gate.

## 3. The fix, exactly

### 3.1 The verdict function

The house pattern is already in this file three times: `_speaker_verdict`
(`:2481`), `_fact_kind` (`:483`), `_horizon` (`:466`). Each normalises an
untrusted answer into a value or `None`, and each says out loud that `None` is
a distinct third state. `_horizon`'s docstring is the template:

> *"NO VERDICT IS NOT AN EXPIRY. … Expiring on a guessed date deletes a true
> fact; leaving it permanent costs a stale row the ranker already sinks."*

The fourth one:

```python
_EXTRACTORS = ("model",)

def _extractor_verdict(mode) -> Optional[str]:
    """WHO filled this Extraction — "model", or None for no verdict.

    NO VERDICT IS NOT AN EMPTY LINE. A model that read the sentence and found
    no promise in it returns an empty Extraction and the verdict "model";
    a transport that answered with the triage heuristic, a refusal, or an
    exception returns an empty Extraction and NO VERDICT. Those are different
    facts about the same row and the store has to keep both, because one of
    them means "nothing here" and the other means "nobody looked".

    `mode` is the transport's own report (brain/llm.py:149), set by which
    endpoint answered. It is never read off the owner's words.
    """
    return "model" if mode in ("gemini", "openrouter") else None
```

`"heuristic"` — llm.py's keyless engine — maps to `None`. That single line
closes path (d).

### 3.2 `_extract`

Returns `tuple[Extraction, Optional[str]]`. Four paths collapse to two
outcomes:

- `self.llm is None` → `(Extraction(), None)`.
- `res.mode` is not a live mode → `(Extraction(), None)`. **Do not parse a
  heuristic reply.** Return before `json.loads`.
- `json.loads`/`_extract_json` raises → `(Extraction(), None)`, keeping the
  existing `print`, and changing its words: it no longer says "falling back to
  rules", because there are no rules to fall back to.
- parsed under a live mode → `(Extraction(...), "model")`, including when
  every field comes back null.

Deleted in the same diff: `_rule_extract` (`:2523-2542`), `_COMMIT_RE`
(`:2516`), `_NAME_RE` (`:2518`), `_NOT_NAMES` (`:2519`).

### 3.3 What `ingest()` returns when extraction fails

Unchanged shape plus one key. Nothing is removed, so no caller breaks on a
missing key:

```python
{
  "episode_id": episode_id,   # ALWAYS. The words land before _extract runs.
  "entities": [],             # empty
  "commitment": None,
  "commitment_id": None,
  "closed": closed,           # see 4.2 — still non-empty, and that is a problem
  "extracted_by": None,       # NEW. "model" | None. None is no verdict.
}
```

**The episode is never lost.** `INSERT INTO episodes` runs at
`brain/memory.py:694`, before `ex = self._extract(text)` at `:696`. The
FTS trigger fires on that insert (`:201-203`), so `recall`'s full-text path
over what was actually said keeps working through a total extraction outage.
What is lost is the derived graph — nodes, edges, the commitment — and that
loss is the point: a graph edge is a claim, and a claim with no verdict behind
it is the thing Law 1 forbids.

**Why the floor points this way.** Law 1: *"a FLOOR (does anything authorize
this?) must refuse without a verdict or it lifts itself."* Minting a commitment
is what authorises the clock to raise an errand at the owner. It is a floor.
No verdict must therefore write nothing.

## 4. What breaks — measured, not estimated

### 4.1 Tests: 39 of 2169, all of them fixtures

Baseline: `python3 -m pytest tests/ --ignore=tests/test_day_zero_oracle.py`
→ **2169 passed in 14.61s**. (`test_day_zero_oracle.py` needs `playwright`,
which is not installed here; it collects, it does not run.)

With `_rule_extract` stubbed to return `Extraction()` — the exact behaviour of
the fix — **39 failed, 2130 passed**:

| File | n | Shape |
|---|---|---|
| `tests/test_memory_knows_who_spoke.py` | 35 | `Memory(":memory:")`, no llm, then `m.open_loops()[0]` → `IndexError` |
| `tests/test_memory_consolidation.py` | 2 | `:164`, `:231` — same shape |
| `tests/test_lane_routing.py` | 2 | `:95`, `:122` — ride the offline `_decide` arm |

**Every one of the 39 uses the regex as an implicit test double. None tests
it.** `grep -rn "_rule_extract" tests/` returns nothing: the function has
zero tests of its own and 39 tests that depend on it by accident.
`tests/test_lane_routing.py:115` says so in a comment: *"# No LLM: the
deterministic path acts on a fresh commitment."*

The repair is a stub extractor in `tests/`, next to `FakeLLM`
(`tests/llm_fakes.py:19`) — a fake that returns the `Extraction` a test wants,
injected the way `FakeLLM` already is. **It must live in `tests/` and `brain/`
must never import it.** A "shared" deterministic extractor imported back into
`brain/` for convenience is the same decision under a different name, which
`tape_gate.py:197-200` names as the thing no gate can catch.

### 4.2 Three things in `brain/` that the fix leaves broken, and what to do

**(a) `brain/anticipy_core.py:2689-2692` — the offline `act` arm becomes dead
code.**

```python
        # Deterministic offline path: a fresh commitment means act.
        if mem.get("commitment"):
            return Decision(decision="act", goal="agent_goal",
                            reason="heard a commitment", needs_confirmation=True)
```

With no llm, `mem["commitment"]` is now always `None`, so `_decide` always
returns `ignore`. The audit calls this arm *"the deepest one"*
(`research/2026-08-24-law1-audit.md:738-739`). **Delete it in the same diff.**
Leaving a dead branch that mints `act` from a regex commitment is an invitation
to re-feed it.

**(b) `close_from_speech` still fires on a verb list.** `brain/memory.py:761`:

```python
        if not completed and not _DONE_RE.search(text or ""):
            return []
```

With no verdict, `ex.completed` is `None`, and `_DONE_RE` (`:361`) gets its
vote anyway. So after this fix, on a degraded brain, **a promise can be closed
by a regex but never opened by one.** That is a strictly safer asymmetry than
today's — closing suppresses an action, opening authorises one — but it is not
clean, and it must not be described as clean. It is audit item **41**, a
separate site with a separate polarity. Out of scope here on purpose: fixing
both in one diff makes the 39-test blast radius unmeasurable. Section 9.

**(c) A degraded window leaves a permanent hole in the graph.** Nothing in the
tree re-runs `_extract` over stored episodes; there is no backfill. So the
words survive and the graph does not, forever, for that window. This is the
honest cost of the fix and it is the reason PART TWO is not optional: **without
the stamp, nobody can even find the window to backfill.** Section 9 hands the
backfill question on.

---

## 5. The stamp — telling a degraded brain from a quiet day

### 5.1 The instrument already exists in this repo

`overnight/are_the_ears_live.py:32` states the whole method in one line:

> *"A silent night is silent on BOTH halves. Deaf ears are silent on ONE."*

No threshold, no expected-words-per-hour, no calendar. Two counts, one of them
a control the fault cannot move, and the fault is the **asymmetry**. That is
what LIBRARY needs, and it is why the design below has no tuned number in it.

### 5.2 The column

**`events.extractor`** — one text field, three values:

| value | means |
|---|---|
| `"model"` | a live model answered for this line |
| `"none"` | she heard this line and nothing read it |
| `""` (absent) | **no verdict about the extractor**: an old core, or a row `hear()` never touched |

Text, not bool, for `_speaker_verdict`'s reason: a bool has two states and this
question has three. Empty must never count as healthy on either side of the
comparison.

**Why on `events` and not in the SQLite store.** The store is the thing that is
unreachable off-host — that is the entire gap. `events` is *"the durable record
the brain itself writes"*, which is `is_the_brain_live.py:30`'s doctrine for
why it checks behaviour instead of a hash.

### 5.3 On which rows

Transcript rows that went through `hear()`, and only those. Explicitly not:

- `anticipy_says` rows (`brain/worker.py:3785`) — she wrote them, she did not
  hear them;
- `sms_reply` / `app_reply` — `handle_inbound` (`worker.py:2991`), a different
  path that does not ingest;
- the profile-import paths, which say in their own comments that they
  deliberately bypass `hear()` (`worker.py:429-437`, `:543-546`).

Naming the population is what stops the ratio in 5.5 being computed over a
denominator that was never eligible — the empty-for-loop green that
`consolidation_gate.py:160-166` was built to refuse.

### 5.4 Written by whom

**`mark_processed()` (`brain/worker.py:2955`)**, which is already the single
writer of per-row verdicts and already PATCHes `decision` / `addressee` /
`goal` in one call from `worker.py:3769`. One new kwarg, one new key in `body`,
one new argument at the call site, read from `out["memory"]["extracted_by"]`.
No new request and no new failure mode; `mark_processed` already returns
whether the PATCH landed, which the replay guard depends on.

The `except TypeError` retry at `worker.py:3746` needs no special case: it
calls the same core with fewer kwargs, so `out["memory"]` is still there. A
core old enough not to return the key yields `.get("extracted_by") → None →
""`, which is the correct degradation — an old core produces **no verdict about
itself**, which is neither healthy nor broken.

Migration: `backend/pb_migrations/1700000046_event_extractor.js`, additive,
byte-for-byte the shape of `1700000029_event_intent.js`.

### 5.5 Read by which gate leg

**A new leg in `overnight/is_the_brain_live.py`, not a new gate file.** That
file already reads production, already loads credentials through `_env`,
already exits non-zero as its verdict, and is already run. A new gate nobody
runs is how `overnight/fellowship_gate.py` came to be cited in two files and
never exist — HARNESS-LAWS.md's own closing complaint.

Over the window, on the population in 5.3:

- `heard` = transcript rows carrying a `decision` (i.e. `hear()` finished them)
- `read` = of those, rows stamped `extractor="model"`
- `blind` = of those, rows stamped `extractor="none"`
- `mute` = of those, rows with `extractor=""`

The verdict, **with no threshold anywhere in it**:

1. `heard == 0` → this leg says nothing, out loud, and is not a PASS. The ears
   own that question and `are_the_ears_live.py` is the leg that asks it. A leg
   that reports health from zero rows is `leg_4`'s old disease
   (`tape_gate.py:1096-1102`: a message asserting what it did not check).
2. `blind > 0` **and** the main tier is demonstrably alive in the same window
   → **RED**, naming the count and the first row id. That asymmetry is
   `are_the_ears_live`'s instrument exactly: the control is the brain's own
   main-tier work — rows carrying a non-empty `goal`, or `anticipy_says` rows
   — and the owner's sleep cannot move it.
3. `blind > 0` and the main tier is silent too → not this leg's business. Both
   halves silent is the brain being down, and the other legs of
   `is_the_brain_live.py` own it.
4. `mute > 0` while other rows in the same window carry a verdict → **RED** as
   version skew, not as a brain fault: two writers are disagreeing about
   whether to stamp. Report which build, do not guess a cause.
5. `read == heard` → PASS, and the message prints the number, because a
   message that asserts more than it counted is the disease above.

**This catches a fault this codebase can actually produce today.**
`_gemini_model_for` (`brain/llm.py:287-300`) sends `ANTICIPY_AUX_MODEL`'s bare
id to the Gemini endpoint and its own docstring notes that a slug naming a
non-Google vendor *"404s a real decision"*. Extraction is the aux tier
(`memory.py:2402`, `aux=True`); triage is not. So one wrong environment
variable takes the librarian's door off its hinges while every visible symptom
of the brain stays perfectly healthy — and today nothing anywhere would say so.

**Why no threshold.** A ratio line ("red under 90%") is a number somebody tunes
down the first week it cries wolf, and it would be the gate deciding how much
blindness is acceptable. The asymmetry needs no number. A partial failure
(`0 < blind`, main tier alive) is already red by rule 2; a partial failure with
the main tier down is already somebody else's leg by rule 3.

---

## 6. `consolidation_gate` off-host: an exported stamp, and only the number

### 6.1 What it is not

**Not a remote leg.** Running the gate on the deploy host puts its answer in a
log, and *"prints it to a log nobody queries"* (`is_the_brain_live.py:27`) is
the specific failure that cost eighteen texts on 2026-08-18. On top of that,
`railway up` reports success while failing (CLAUDE.md), so "we ran it on the
host" is itself an unverifiable claim from off-host.

**Not an exported verdict.** A row saying `consolidation: healthy` is the
registry-satisfied-by-declaration attack `tape_gate` already defeats for live
tape (`tape_gate.py:60-66`). The brain does not get to grade itself. Every
green in this repo that came from a self-report has been wrong.

### 6.2 What it is

**The brain exports the numbers it cannot be trusted to interpret, and the leg
does the comparing off-host against a denominator the brain does not control.**

Three values, all of them things that happened, none of them claims:

| field | source | already computed at |
|---|---|---|
| `consolidated_at` | `Memory.last_consolidation_ts()` — stamped by `consolidate()` and nothing else | `memory.py:1659` |
| `consolidated_facts` | profile rows with `source="consolidation"` and a non-null `kind` — the exact predicate the on-host leg 4 runs | `consolidation_gate.py:330` |
| `consolidated_episodes` | `totals["episodes"]` from the nightly loop | `worker.py:165-176` |

`run_nightly_consolidation` already computes all three and prints them
(`worker.py:176-177`). The export is that print, written to a row instead of a
log.

**Nothing else travels.** No fact, no name, no text. `design/LOCAL-FIRST.md:32-34`
— *"What travels is the smallest conclusion that works"*. A count and a clock
are metadata about the librarian, not about the life. This is what makes the
export legal under the law that the memory graph is a cloud gap already; it
does not widen that gap by one word.

**Where:** the owner's `owner_profile` row — one per owner, already fetched by
the brain at `worker.py:128-141`, already scoped by `owner_ref`. Written by
`run_nightly_consolidation`, best-effort, inside the existing `try` whose whole
purpose is that consolidation can never take hearing down (`worker.py:178-180`),
with the same posture as `record_link` (`worker.py:2912-2920`).

**One thing I could not verify and that must be checked before the field
ships.** `1700000003_owner_profile.js:18` declares `listRule: ""`, which in
PocketBase means public, and the collection carries the owner's phone number.
It appears to be fenced by `backend/pb_hooks/guard.pb.js:416`, but I did not
determine what that hook actually permits for an unauthenticated list. If the
fence is weaker than assumed, a consolidation stamp there is activity metadata
on a public collection. Check it, or put the three fields on a collection whose
rules you have read.

### 6.3 The off-host leg

Sibling of 5.5, same file. **The denominator is already off-host and the brain
does not own it:** transcript rows in `events`.

- transcript rows exist since `consolidated_at`, spanning more than one
  quiet-hours window, and `consolidated_at` has not moved → **RED**. Reuse
  `STALE_AFTER_SECONDS = 48 * 3600` (`consolidation_gate.py:103`) by importing
  it, not by re-deriving it, so the two gates cannot drift apart.
- `consolidated_at` moved but `consolidated_facts` did not, across a window in
  which transcript rows existed → **RED**. That is on-host leg 4's *"a pass
  that runs and achieves nothing"*, off-host.
- the export fields are absent entirely → **RED, not skip.** *"A leg that
  cannot be tested does not pass"* — done_gate's doctrine, quoted at
  `consolidation_gate.py:38-40`.

**The declared weakness, stated so the green is never over-read:** this leg
cannot tell a dead consolidator from a dead exporter. Collapsing them into one
red is correct — either way the librarian's health is unknown from outside, and
unknown is not green. `overnight/consolidation_gate.py` remains the authority
on the host; this is a mirror, and its message must say it is a mirror.

---

## 7. The honesty wall, all three sites

Three verdicts, one rule each. All three are **floors** — each authorises
something — so all three refuse without a verdict, per Law 1's floor/ceiling
test:

| verdict | authorises | absent means |
|---|---|---|
| `_extractor_verdict` | writing a node, an edge, or a commitment | nothing is written |
| `events.extractor` | the leg saying she understood the day | the leg reports skew, never health |
| the consolidation export | the leg saying the profile is learning | red |

None of the three is a bool, for `_speaker_verdict`'s stated reason. None of
the three is inferred from the owner's words.

## 8. Law compliance, and what waits on a working build

**Law 1.** This deletes a pattern-match that decides meaning and adds counts, a
clock, and one transport-reported mode string. `_extractor_verdict` reads
`LLMResult.mode` (`llm.py:149`), which is set by which endpoint answered
(`llm.py:280-285`) and never by reading the owner's words. The new legs are
gates — exempt — and they carry no threshold regardless.

**Law 2.** No entry is added to `KNOWN_TAPE` and nothing moves into
`CLOSED_TAPE`. This retires none of the audited five. `tape_gate.py` stays
exit 2 with leg 3 red for the five in `anticipy_core.py` and `asking.py`, and
nobody may report this work as having moved that gate.

**Law 3 — what can be verified today, without a phone.** I ran these:
- the four `_extract` paths, against the shipped code (section 1);
- the 39-test blast radius, both directions (section 4.1);
- that `brain/memory.py` contains zero `TAPE:` markers and that `tape_gate.py`
  exits 2 with leg 3 red for all five;
- `_rule_extract` has no test of its own anywhere in the tree.

**What waits on a working build**, i.e. a phone delivering transcript rows
again:
- that `events.extractor` appears on a real row at all;
- the 5.5 comparison, which needs a non-zero `heard`;
- whether PocketBase accepts a PATCH carrying an unknown field or rejects it
  (section 10);
- the consolidation export, which needs a redeploy **and** one quiet-hours
  night with a live model.

The ears are dead — zero transcript rows in ~31 hours; b82 is compiled and not
installed. Nothing in this spec can be called fixed until those rows exist.

**Law 5.** Fix order is senses → context → examples → tier → structure. This is
not structure over meaning: it **deletes** a structure that was doing meaning,
and everything else here is instrumentation. It is nonetheless genuinely below
capture in priority — the Brief lists capture first and EARS caps everything
downstream. It costs nothing to land while the phone is being fixed, because it
touches no capture code and no iOS file.

**LOCAL-FIRST.** Section 6.2. Counts and a clock; zero facts and zero words
leave the host that were not already leaving it.

## 9. What would kill this

- **PocketBase rejecting an unknown PATCH field.** If a brain-first deploy
  starts sending `extractor` before the migration lands and PocketBase 400s
  rather than ignoring it, `mark_processed` stops marking rows processed, the
  2s poll replays every row, and you get a duplicate job and a duplicate text
  per cycle — the exact failure that function's own docstring records
  (`worker.py:2957-2959`). **Backend-first deploy order is mandatory, and it is
  free.** I did not verify PocketBase's behaviour on unknown fields; verify it
  before the first deploy, not after.
- **The 39 tests being "fixed" by re-adding a rule extractor that `brain/`
  then imports.** Same decision, different name — the blind spot
  `tape_gate.py:197-200` names as one no gate can catch. The stub lives in
  `tests/`; `brain/` must not import it.
- **`_DONE_RE` being left alone forever** (4.2b). After this fix it is the last
  pattern-match that can move the commitment graph, and it moves it in one
  direction only.
- **`owner_profile`'s list rule** being weaker than 6.2 assumes.

## 10. Decisions made without the owner

1. That a promise the model did not verify is not written at all, rather than
   written and flagged. Follows Law 1's floor rule and `_horizon`'s docstring.
2. That `_DONE_RE` stays out of this diff. Different polarity, different audit
   item; combining them makes the blast radius unmeasurable.
3. That both new legs go into `overnight/is_the_brain_live.py` rather than a
   new gate file.
4. That the consolidation export lands on `owner_profile` rather than in a new
   collection — reversible, and contingent on 6.2's unresolved rules question.

## 11. Handed back

- **Re-extraction/backfill.** 4.2c leaves a permanent graph hole for any
  degraded window. The stamp makes the window findable; nothing rebuilds it.
  Is a backfill pass wanted, and does it belong to the nightly consolidation
  lane or to its own? This crosses out of `memory.py`.
- **`_DONE_RE` (audit item 41).** After this fix it is the only pattern left
  that can move the commitment graph. It needs its own decision — model verdict,
  or an honest no-verdict that leaves loops open — and the second option means
  the clock nags about finished work, which is the failure `close_from_speech`
  was built to stop. That is an owner call about which harm is worse.
- **`brain/worker.py:3500`.** `llm if llm.live else None` reads `live` once, at
  boot. Should a worker that boots without a key refuse to start rather than
  run a memory that can never learn? That is a supervisor decision, not a
  memory one.
- **`guard.pb.js:416`** — what it actually permits for `owner_profile` (6.2).
- **Whether PocketBase ignores or rejects unknown PATCH fields** (section 9).
  One curl against the live backend answers it and nobody has run it.
