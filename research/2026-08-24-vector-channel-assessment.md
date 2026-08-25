# The vector channel (LIBRARY gap 5): what it would actually cost

Assessment only. **Nothing was built, no dependency was added, no external
embedding API was called.** Written to `research/` rather than left in a chat
because a conclusion that lives only in a conversation gets re-derived — wrong
— by the next session (HARNESS-LAW 4).

The card asks for a third recall channel so that "the tooth guy" reaches
`dentist is Cavendish Dental` with zero shared words. Today it cannot: recall
is FTS5 keyword matching plus a two-hop graph walk plus the distilled profile
ranking, and three places in the tree state the absence as a deliberate design
fact (`brain/memory.py:9` "not embedding soup", `design/day-zero.md:144` "**The
memory store has no embeddings.**", `brain/worker.py:405-411`).

---

## 1. The blocker the card does not mention, and it is not the dependency

The prior research named the dependency as the hard blocker:
`brain/Dockerfile:12` installs exactly `requests httpx tzdata`, so cosine
similarity would be pure Python. That is true and it is the smaller half.

**The real blocker is that the read path stops being free.** The research
concluded that "embedding at write time and caching the vector in the row keeps
read cost at zero". *That is wrong, and it is the load-bearing sentence.* A
cosine comparison needs BOTH vectors. The stored one can be cached in the row;
the QUERY vector cannot, because the query is a sentence nobody has ever said
before. So a vector channel wired into `recall()` costs **one embedding call
per query**, on a path that today advertises itself as free:

```
brain/anticipy_core.py:3372
    # Pure SQLite (profile layer then graph walk), so this costs no model
    # call and works with no key.
```

`recall()` is called from five places, and one of them is per-line:

| call site | when | frequency |
|---|---|---|
| `anticipy_core.py:2458` — triage context | **every ambient line** | ~131/day (`orchestrator.py:398`, the measured figure) |
| `anticipy_core.py:2624` — `_answer_from_memory` | owner asks a question | already pays for a model call |
| `anticipy_core.py:3386` — `_queue_job` memory block | a job is minted | ~6/day; today free |
| `orchestrator.py:1209` — `fill_gaps_from_memory` | a plan has a gap | already pays for an aux call |
| `conversation.py:1238` — SMS classifier | every inbound text | already pays for a model call |

So the honest cost statement is: **~131 extra network round-trips a day for the
triage channel alone**, on the hot path, in front of a judgement that already
costs 4-6 model calls per utterance (`brain/llm.py:24-38`). It is not free and
it is not nothing.

## 2. No embedding provider is wired, and the alternate one may not be paid for

`brain/llm.py:21-22` speaks two protocols: OpenRouter chat-completions and
Gemini `:generateContent`. Neither is an embeddings endpoint.

- **Gemini** has `:embedContent` on the same host, reachable with the same key
  over the `httpx` already installed. **No new dependency.** This is the
  research's suggestion and it is sound as far as it goes.
- **But production runs OpenRouter, not Gemini.** `live` is
  `bool(gemini_api_key or api_key)` (`llm.py:223`), `DEFAULT_MODEL` is
  `deepseek/deepseek-v3.2`, `done_gate` leg 3 asks for `OPENROUTER_API_KEY`,
  and the deployed env list in `HANDOFF.md:332` carries `OPENROUTER_API_KEY`
  and no Gemini key. OpenRouter is a chat-completions router and does not
  serve a general embeddings endpoint.

**So the "no new dependency" claim is true and the "no new credential" claim is
not.** Shipping the Gemini embed path means provisioning `GEMINI_API_KEY` on
the deploy — at which point `llm.py:223` makes Gemini the *primary chat
provider too*, because the gemini key is checked first (`llm.py:276-282`). A
credential added for embeddings would silently move every judgement in the
product onto a different model. That is a deployment trap worth writing down
before anybody sets the variable.

## 3. Pure-Python cosine: measured, not guessed

Measured on this machine (Python 3.14, Apple silicon). A Railway
`python:3.11-slim` container is slower — assume 1.5-3x.

```
  dim=  384 facts=   100       1.9 ms/query
  dim=  384 facts=   500      10.0 ms/query
  dim=  384 facts=  2000      38.4 ms/query
  dim=  384 facts= 20000     386.6 ms/query

  dim=  768 facts=   100       3.8 ms/query
  dim=  768 facts=   500      19.0 ms/query
  dim=  768 facts=  2000      75.6 ms/query
  dim=  768 facts= 20000     762.7 ms/query

  dim= 1536 facts=   100       7.4 ms/query
  dim= 1536 facts=   500      37.7 ms/query
  dim= 1536 facts=  2000     154.2 ms/query
  dim= 1536 facts= 20000    1575.1 ms/query

  dim= 3072 facts=   100      15.1 ms/query
  dim= 3072 facts=  2000     312.5 ms/query
  dim= 3072 facts= 20000    4071.5 ms/query
```

Storage: a 768-dim `float32` BLOB is 3 KB per row; 500 profile facts is 1.5 MB
of per-owner SQLite. At 3072 dims it is 6 MB. Both are fine on disk.

**The conclusion the numbers support: `profile_facts` only, never `episodes`.**
A few hundred profile facts at 768 dims is 20-60 ms of CPU per query — tolerable
next to a network round-trip that already dominates it. The episode table is
tens of thousands of rows within weeks and lands at 0.8-4 seconds per ambient
line in pure Python, which is not a feature, it is an outage. numpy would fix
the arithmetic (roughly two orders of magnitude) at the cost of the first
numeric dependency in a deliberately bare image.

## 4. Does the local-first law permit it?

`design/LOCAL-FIRST.md` rule 2, verbatim:

> Voiceprints, embeddings, biometrics: computed on device, stored on
> device, never synced, never in git, never in PocketBase.

**The word "embeddings" is in the law.** Two readings, and I am not the one who
gets to pick:

- **Narrow.** The list is one list of BIOMETRIC things — voiceprints and the
  embeddings that are voiceprints. A 768-float summary of "dentist is Cavendish
  Dental" is not a biometric, and the sentence it summarises is already sent to
  a cloud model on every ambient line (the scoreboard's own row for Triage says
  "CLOUD TODAY — the biggest open gap"). On this reading a cloud embedding adds
  no new CLASS of data leaving the device.
- **Plain.** The law says embeddings are computed on device, full stop. Sending
  every profile fact and every ambient line to a second vendor to be vectorised
  is a new outbound flow of the most compressed possible description of who he
  is, and the law's one-sentence form — "Understanding happens on the device;
  only CONCLUSIONS and OUTWARD ACTIONS travel" — reads against it. A vector is
  not a conclusion; it is understanding, exported.

The scoreboard row for Memory already says "CLOUD TODAY — second biggest gap".
Adding a cloud embedding channel does not merely fail to close that gap; it
deepens it, because a vector index is much harder to move on-device later than
a SQLite table is.

**Rule 5 binds this decision either way:** "Any new feature PR/brief states its
local-first posture explicitly. 'We'll localize it later' requires naming the
later." A cloud-embedding vector channel therefore cannot ship without naming
the later, and nobody has.

## 5. What it would actually take

Ordered smallest-first. Each row is what the option costs and what it buys.

| # | Option | New dependency | New credential | Read cost/line | Local-first |
|---|---|---|---|---|---|
| 0 | **Do nothing.** Keep keyword + graph + the importance-ordered padding block (`memory.py` `_profile_recall`, which fakes this today: "'go-to restaurant' answers 'usual dinner spot' yet shares no word with it") | none | none | 0 | compliant |
| 1 | **Vectors only where a model call is already paid for** — `_answer_from_memory`, `fill_gaps_from_memory`, and nothing else | none (httpx) | `GEMINI_API_KEY` | 0 on the ambient path | same question as 2 |
| 2 | Cloud embeddings on every `recall()` | none (httpx) | `GEMINI_API_KEY` | 1 round-trip | **rule 2 conflict, unresolved** |
| 3 | Local embedder in the container (`sentence-transformers`) | torch, ~2 GB image | none | ~50-200 ms CPU | compliant |
| 4 | **Embed on the phone** (`NLEmbedding` / `NLContextualEmbedding`) and ship the vector with the line | none server-side | none | 0 server-side | **compliant by construction** |

Option 4 is the one that matches the law rather than arguing with it, and it is
the same shape the product already uses for speaker tags: the device computes,
and only the conclusion travels. It needs `app/ios/**` work (out of this wave's
scope, and another agent holds it), it needs the query embedded on-device too —
which is free there, since the phone has the line before anyone else does — and
it needs the model identity pinned so a phone on an older iOS does not silently
produce vectors in a different space. **It has not been verified that the
iOS-side API produces a stable, comparable sentence embedding across OS
versions; that is the first thing to check before committing to it.**

Option 1 is the honest cheap experiment: it buys the card's own example (the
`_answer_from_memory` path is where "what's my dentist called" is answered)
without touching the per-line budget, and it is reversible.

Whatever ships, three properties are non-negotiable and come free from the
existing shape of this store:

1. **`embedder=None` degrades to today, exactly.** Consolidation already
   no-ops with no model (`memory.py consolidate`), extraction already falls
   back to `_rule_extract`. Every offline test and the whole deterministic gate
   suite depend on it.
2. **A write must never fail because a vector could not be computed.** The
   profile row lands; the vector is an optimisation.
3. **The vector table stores the model identity.** A provider or model change
   invalidates every vector in the store and the row has to be able to say so.
   `CREATE TABLE IF NOT EXISTS fact_vectors(...)` is a NEW table, so it reaches
   existing owner databases with no ALTER — the `vetoed_facts` precedent — but
   the column migration machinery (`_ADDED_COLUMNS` / `_retrofit_columns`) now
   exists either way.

## 6. Recommendation

**Do not build it this week, and do not build option 2 at all without an owner
ruling on rule 2.** The card ranks this fifth of five and it is the only one of
the five that is a new subsystem rather than a column and a filter. Three
things should be known first, and none of them is code:

1. **Does nightly consolidation even run in production?** Everything the
   profile layer does rides on it and nobody has shown it firing against LIVE.
   `overnight/consolidation_gate.py` now measures exactly that, and it is red
   until somebody runs it on the deploy host. A vector index over a profile
   that is not being written is an index over nothing.
2. **How many profile facts does a real owner actually have?** The whole
   cost table above is a function of that number and it is unknown from here —
   per-owner files under `ANTICIPY_STATE_ROOT` on the deploy host, not in the
   repo. At 100 facts the pure-Python arithmetic is free; at 20,000 it is an
   outage. One `SELECT COUNT(*)` on the host answers it.
3. **The owner's reading of rule 2.** That is one sentence from one person and
   it decides between options 2 and 4, which differ by weeks of work.
