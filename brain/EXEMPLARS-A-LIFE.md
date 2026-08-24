# A life, and one ordinary day inside it

`EXEMPLARS.md` is the tail — thirty-one calls a competent person could get
wrong. Every one of them is rare. Put together they are maybe 1% of what she
hears, and if you only trained on them you would build something that is
brilliant at weird sentences and useless on a Tuesday.

This file is the other 99%. It is one person, written out completely, and one
whole unremarkable day of theirs, with **every memory operation shown inline**.

The thesis, and the reason this file exists:

> **Almost nothing that happens is interesting. The few things that are only
> become legible because of what she was already holding.** The work is not
> classifying a line. The work is maintaining a life well enough that a
> three-word line resolves.

Read the day (§2) with §1 open beside it. Nearly every good call down there is
paid for by a row up here.

---

# 1. What she is holding about Marcus

This is the whole state, on the morning of Tuesday 14 October, after eleven
weeks. Nobody typed any of it. Every row arrived by consolidation from things
he said out loud.

## 1.1 `profile_facts` — the distilled life

`importance` 1–5, model-judged. `confidence` starts near 0.6 and **grows every
time the fact reappears independently**. `provenance` is the episode ids it was
distilled from — so any fact can be traced back to the sentences that made it.

| # | fact | imp | conf | seen | provenance |
|---|---|---|---|---|---|
| 1 | Works at Halden Studio; it is a design studio and he is a partner, not staff | 5 | 0.96 | 41× | 12, 40, 77, … |
| 2 | Priya Shah runs Halden's books; invoices and money go through her | 4 | 0.94 | 23× | 31, 88, 194, … |
| 3 | Daughter Ines, 7, at Fielding Primary; he does the school run Mon/Wed/Fri | 5 | 0.98 | 60× | 8, 19, 55, … |
| 4 | Partner is Sofia; she works nights Tue/Thu so Tue evenings are his alone with Ines | 5 | 0.91 | 18× | 22, 63, 140 |
| 5 | Sister Nadia, in Lisbon, birthday 12 March | 3 | 0.88 | 6× | 71, 152, 233 |
| 6 | Drives a 2019 Golf; garage is Everton Autos on Mill Road | 2 | 0.79 | 5× | 96, 181 |
| 7 | Coffee is the place on Mill Road called Ostro — "the usual" means a flat white | 2 | 0.83 | 14× | 27, 44, 102, … |
| 8 | Allergic to shellfish. Mentioned once, flatly, not as a joke | 5 | 0.72 | 1× | 118 |
| 9 | Hates phone calls; will email or text anything he can | 4 | 0.86 | 9× | 35, 90, 176 |
| 10 | Runs Tue/Thu mornings before the house wakes, ~6am | 2 | 0.74 | 11× | 51, 108, 199 |
| 11 | Dentist is Cavendish Dental; last seen there in March, was told to come back in 6 months | 3 | 0.81 | 4× | 66, 121, 205 |
| 12 | Boss-adjacent: Tom Rutherford is the client he is most careful with | 4 | 0.77 | 7× | 84, 129, 210 |

**Fact 8 is the one to understand.** Importance 5, confidence 0.72, seen
**once**. High importance and low confidence at the same time. A cheap ranker
that sorts on confidence alone buries it, and one day he is handed a restaurant
with a shellfish tasting menu. **Importance gates, confidence orders. Never the
other way round.**

## 1.2 `nodes` — the graph

```
person   Priya Shah        last_seen 2d    person   Sofia            last_seen 4h
person   Ines              last_seen 2h    person   Nadia            last_seen 31d
person   Tom Rutherford    last_seen 9d
place    Fielding Primary  last_seen 2h    place    Ostro            last_seen 1d
place    Everton Autos     last_seen 46d   place    Cavendish Dental last_seen 88d
thing    the Golf          last_seen 46d   thing    the Rutherford deck  last_seen 9d
topic    the Devon invoice last_seen 2d    topic    half-term          last_seen 6d

commitment  "send Priya the Devon invoice"       OPEN       created 2d ago
commitment  "book the Golf in for its service"   OPEN       created 46d ago
commitment  "call Cavendish about a check-up"    OPEN       created 88d ago
commitment  "get back to Tom on the deck"        DONE       closed 8d ago
```

**Three open commitments, aged 2, 46 and 88 days.** That spread is the whole
design problem for the briefing. A system that reads them all out every morning
gets muted by Thursday.

## 1.3 What is deliberately *not* here

- **No transcript.** Episodes hold the raw lines and are searched by FTS on
  demand. The profile holds only what survived distillation.
- **No inferred facts.** Nothing says "probably likes Italian food." Every row
  traces to sentences he actually said.
- **No emotional model.** No "seemed stressed on Tuesday." It is not
  measurable from a microphone and it would be used to justify things.

---

# 2. Tuesday 14 October

A day of his, in shape. **Three lines out of twenty-eight produce an action.**
The rest is the job too — the job is knowing they are not.

Notation: `↳` is a memory write. `⟳` is a recall. `→` is the decision.

---

### 05:58 — 07:40 · the run and the school run

```
05:58  (silence, movement)
06:31  "morning"                                          → ignore
       ↳ episode. node person:Sofia last_seen ↑
       ↳ fact 10 (runs Tue/Thu ~6am) confidence 0.74 → 0.76, seen 11 → 12
```

Nothing happened, and something happened. **A day where she takes no action is
still a day where the profile gets sharper.** Fact 10 is now a little more true
because a Tuesday morning went the way Tuesday mornings go.

```
07:02  "Ines — shoes. Shoes!"                             → ignore
       ↳ node person:Ines last_seen ↑
07:03  Ines: "I can't find them"                          → ignore
```

**Not his voice.** Third-party speech is remembered as an episode and never
produces a commitment. The commonest false-positive class in the whole product
is acting on something a child said.

```
07:19  "right, in the car"                                → ignore
07:33  "see you at pickup"                                → ignore
       ↳ node place:Fielding Primary last_seen ↑
       ↳ fact 3 (school run Mon/Wed/Fri) confidence 0.98 → 0.98, seen 60 → 61
```

Fact 3 is saturated. **Confidence must not run away with repetition** — past
~0.95 a re-sighting refreshes `last_seen` and nothing else, or the top of the
profile becomes whatever he says most often rather than what matters most.

---

### 08:10 — 08:14 · Ostro

```
08:11  "morning — just the usual, ta"                     → ignore
       ⟳ recall("the usual") → fact 7, relevance 2, conf 0.83
       ↳ node place:Ostro last_seen ↑; fact 7 seen 14 → 15
```

**This is the most instructive nothing in the file.** She resolves "the usual"
to a flat white at Ostro, correctly, from an eleven-week-old pattern — and then
does *not act on it*. He is ordering coffee from a person standing in front of
him. There is no work here.

Resolving is not acting. A model that thinks retrieval implies action orders
him a second coffee.

```
08:13  "cheers"                                           → ignore
```

---

### 09:05 — 11:20 · the studio

```
09:07  "did the Rutherford stuff land?"                   → ignore
       ⟳ recall("Rutherford") → node thing:the Rutherford deck (9d),
                                 commitment DONE 8d ago, fact 12 (imp 4)
```

He is asking a person in the room. She retrieves, resolves, stays quiet. **The
retrieval still mattered** — it is what lets her know, two lines later, what
"it" means.

```
09:08  (other voice) "yeah Friday, he's happy"            → ignore
       ↳ episode. node person:Tom Rutherford last_seen ↑
```

```
09:31  "I still haven't sent Priya that invoice"          → ???
       ⟳ recall("Priya invoice") → commitment "send Priya the Devon invoice"
                                    OPEN, created 2d ago
       →  ignore
```

**The single highest-value `ignore` in this file.**

The line is a textbook commitment: named person, named object, stated
obligation, unaddressed. In `EXEMPLARS.md` §1 that is an unambiguous `act`.

It is `ignore` here **only because an open commitment for exactly this already
exists.** Without that recall she opens a second job and texts him a second
time about one invoice — the duplicate-job bug, arriving not through a weird
sentence but through the most ordinary thing a person does: **repeating
themselves because it is on their mind.**

```
       ↳ commitment last_seen ↑, mention_count 1 → 2
```

The mention count is the useful part. **Twice in two days is the signal that it
is bothering him**, and that is a far better trigger for a nudge than the age
of the row.

```
10:02  "can you send me that link"                        → ignore
10:44  "I'm going to grab a sandwich, want anything?"     → ignore
11:02  "no, the other one — the one with the grid"        → ignore
11:19  "yeah that's fine"                                 → ignore
```

Four lines, nothing to do. **This is what most of a day is**, and the correct
behaviour is complete silence.

---

### 12:40 · the one that needs the graph

```
12:40  "oh — Sofia's on nights, so I've got Ines tonight"  → ignore
       ⟳ fact 4 (Sofia nights Tue/Thu) conf 0.91
       ↳ fact 4 seen 18 → 19, conf 0.91 → 0.92
       ↳ node person:Sofia last_seen ↑, person:Ines last_seen ↑
```

No action — he is stating a thing he already knows. But she now holds, for
today specifically, **that his evening is not free**, and that is what makes
the 17:52 line answerable.

---

### 13:15 — 16:30 · afternoon

```
13:15  "ugh, my back"                                     → ignore
14:07  "what time's the thing on Thursday"                → ???
       ⟳ recall("Thursday") → topic:half-term (6d), no calendar node
       →  ask
       ASK  "Which thing on Thursday?"
```

**Genuinely ambiguous, and she says so.** Memory has a half-term topic from last
week and nothing scheduled. She could guess. Guessing here produces a confident
answer about the wrong thing, which is worse than a question — a wrong answer
teaches him not to trust the right ones.

```
14:09  "the school thing"                                 → act
       GOAL "find the start time for the Fielding Primary event on Thursday"
       ⟳ place:Fielding Primary, fact 3
       ↳ episode; edge (question → about → Fielding Primary)
```

**One question, one answer, then work.** Note the goal carries the resolved
school name, not the words "the school thing" — a goal containing an unresolved
pronoun is a goal nobody can execute.

```
15:22  "did we ever hear back on that?"                   → ignore
16:04  "I'll look at it after"                            → ignore
```

`16:04` is a commitment by the letter of the rules. It is `ignore` because
there is no object — "it" resolves to nothing in the last six lines. **A
commitment with no resolvable object is not actionable**, and inventing one is
how you get a job about the wrong thing.

---

### 17:52 · the line the whole file exists for

```
17:52  "yeah go on then, Thursday, book us a table"       → act
```

Nine words. Here is what has to be true for that to become a correct action:

```
⟳ recall pass:
   AROUND  17:50 (other voice) "we should do that dinner thing this week"
           17:51 (other voice) "Thursday? that place on the corner"
   MEMORY  fact 4   Sofia nights Tue/Thu     imp 5  conf 0.92   ← Thursday is NOT free
           fact 8   shellfish allergy        imp 5  conf 0.72   ← imp gates it in
           fact 3   Ines, school run         imp 5  conf 0.98
           fact 7   Ostro / Mill Road        imp 2  conf 0.83   ← "the corner", maybe
```

```
→   ask
ASK "Thursday — isn't Sofia on nights? Want me to look at Wednesday instead?"
```

**She does not book it.** Everything needed to book it is present: a day, a
place, an instruction, an explicit "go on then". A system optimising for
helpfulness books the table.

The right answer is a question, because **the memory contradicts the
instruction.** He has forgotten his own Thursday. A great assistant standing in
the room says exactly that sentence.

Then:

```
17:53  "oh — good call. Wednesday."                       → act
GOAL  "book a table for two on Wednesday evening at the place on Mill Road —
       NO SHELLFISH, he is allergic"
↳ commitment "book Wednesday dinner" OPEN
↳ fact 4 conf 0.92 → 0.94  (it was just proved useful — a fact that CHANGES an
                            outcome earns more than one that merely recurs)
↳ fact 8 provenance += this episode  (surfaced, still seen only once, but now
                                      it has been acted on rather than stored)
```

Three things in that one write:

1. **The allergy rides along into the goal** without him mentioning it. Recalled
   on importance, not on relevance — "book a table" does not textually match
   "shellfish". A pure keyword ranker never surfaces it. This is the single
   clearest argument in the whole system for importance-gated recall.
2. **A fact that changed an outcome is worth more than a fact that recurred.**
   Fact 4 earns a bigger confidence bump from being *load-bearing once* than
   from being *mentioned twenty times*.
3. **The place is still fuzzy** — "the place on the corner" against a Mill Road
   coffee shop. The goal says "the place on Mill Road" rather than guessing
   "Ostro", because Ostro is a café at importance 2 and this is dinner.
   **Carry the uncertainty into the goal instead of resolving it wrongly.**

---

### 19:30 — 22:10 · evening

```
19:31  "right — bath, then one chapter"                   → ignore
20:15  Ines: "can we do two"                              → ignore
20:16  "one"                                              → ignore
21:40  "I'm so done with today"                           → ignore
22:08  "oh, I need to book the car in at some point"      → ignore
       ⟳ commitment "book the Golf in for its service" OPEN, 46d
       ↳ mention_count 3 → 4, last_seen ↑
```

The car commitment is **46 days old and has now been mentioned four times.** No
action — it already exists, and "at some point" carries no anchor.

But this is the row the morning briefing should lead with tomorrow, and **not
because it is the oldest.** The dentist one is 88 days old and has been
mentioned once since. Age says dentist. **Mention count says car, and mention
count is what "this is bothering him" actually looks like in data.**

---

## 2.1 The day, counted

Counted from what is actually written above, not estimated — every number here
can be grepped out of this file.

| | |
|---|---|
| lines shown | 28 |
| `ignore` | 23 |
| `ask` | 2 |
| `act` | 3 |
| memory writes shown | 16 |
| recalls shown | 9 |
| facts whose confidence moved | 5 |
| **actions that were only correct because of memory** | **3** |

The three: the 09:31 non-duplicate, the 17:52 refusal, and the allergy riding
into the 17:53 goal.

**Eighty-two percent of the day is `ignore`, and that is the product working.**

A real Tuesday is closer to two hundred lines — the run, the school gate, the
studio, an entire evening. This is the shape of one, not a transcript of one.
The ratio is what to take from it, and on a full day the ratio gets *more*
extreme, not less.

---

# 3. How the life got there

Same person, backwards. This is the part `EXEMPLARS.md` had no way to show,
because it happens over weeks and not in a line.

## Day 1 — everything is a stranger

```
"I'll get that over to Priya by Friday"
→ act    GOAL "prepare what he owes Priya by Friday"
↳ node person:Priya (new)  ·  commitment (new)  ·  NO profile fact yet
```

**One sighting is not a fact.** She acts on the sentence — it is a clear
commitment — but writes nothing durable about who Priya is. Consolidation has
not run and there is nothing to distill from a single mention.

Day 1 behaviour is correctly worse than day 60. **A system that seems to know
you on day one is guessing**, and it will be confidently wrong in front of a
stranger. This is also why the pendant has to be worth wearing before it is
smart — see the fellowship course, unit 0.

## Day 3 — the first distillation

```
consolidate() reads episodes 28–61
model returns: {"fact": "Priya Shah handles invoices at his work",
                "importance": 4, "episodes": [31, 44]}
↳ INSERT profile_fact #2, confidence 0.60
```

Two independent mentions, three days apart, become one fact. Confidence starts
low on purpose.

## Day 11 — a fact gets corrected

```
"no, Priya's not my boss — she does the books"
↳ _find_same_fact() matches #2
↳ MERGE, not insert: text updated, confidence 0.71 → 0.78
```

**Correction is a merge, not a second row.** Two contradictory facts about one
person is how a profile starts lying. `_find_same_fact` exists precisely so a
correction lands on the thing it corrects.

## Day 24 — the allergy

```
"no shellfish for me — I'm allergic"
↳ INSERT profile_fact #8, importance 5, confidence 0.60, seen 1×
```

Said once, flatly, in passing, and never repeated in eleven weeks. **Its
confidence will never grow, because it will never come up again.** If ranking
ran on confidence it would be at the bottom of the profile forever, and it is
the one fact in this file that could actually hurt him.

Importance is a separate axis for exactly this reason.

## Day 30 — a commitment closes itself

```
"sent it — Priya's got the invoice"
↳ close_from_speech() → commitment "send Priya the Devon invoice" → DONE
```

**She learns it is finished from him saying so**, not from watching an outbox.
An open loop nobody ever closes is the fastest route to a nagging assistant.

## Day 46 — the poison batch

```
consolidate() → model returns unparseable output
↳ cursor does NOT advance. Same episodes re-read tomorrow.
```

Correct — a flaky model must not eat a day. **But this is also the bug that was
found here:** a batch the model could *never* parse was re-read every night
forever, nothing after it was ever consolidated, and **the profile silently
stopped learning** with one print line as the only sign. After three
consecutive failures on the same cursor the batch is skipped.

**A memory system that stops learning must be loud about it.** Silence here
looks identical to nothing happening.

---

# 4. What this means for whoever builds recall

Six rules, all earned above:

1. **Importance gates, confidence orders.** Confidence-first ranking buries the
   shellfish allergy under the coffee order.
2. **Confidence saturates.** Past ~0.95 a re-sighting refreshes `last_seen` and
   nothing else, or the profile becomes whatever he says most, not what matters
   most.
3. **A fact that changed an outcome earns more than a fact that recurred.**
   Load-bearing once beats mentioned twenty times.
4. **Check open commitments before creating one.** The most ordinary human
   behaviour — repeating yourself — is the most common route to a duplicate job.
5. **Mention count, not age, is what "this is bothering him" looks like.**
   46 days and four mentions outranks 88 days and one.
6. **Resolving is not acting.** She should know what "the usual" means and order
   nothing.

And one that outranks all six:

> **When memory contradicts the instruction, ask.** Every other rule is about
> being useful. This one is about being trusted, and it is the reason he keeps
> wearing it.
