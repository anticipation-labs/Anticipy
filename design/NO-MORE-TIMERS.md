# No more timers: conversations as links, not cuts

**2026-08-05. Written after Omar's ruling ("better it overreacts than underreacts")
and a research pass into how this problem has actually been solved elsewhere.**

---

## 1. The thing we got wrong, and the paper that proves it

Every version of Anticipy's segmenter has asked the same question:

> *has enough time passed that this conversation is over?*

That question was studied and answered eighteen years ago, and the answer is that
it cannot be answered.

**Jones & Klinkner, CIKM 2008, "Beyond the session timeout: automatic hierarchical
segmentation of search topics in query logs."** They hand-labelled real user
sessions into tasks, then swept timeout length across its whole range:

> "Timeouts, whatever their length, are of limited utility in identifying task
> boundaries, achieving a maximum precision of only **70%**."

Not "45 s is the wrong number." *No number exists.* They also measured **17% of
tasks interleaved** and **20% hierarchically nested** — which is Omar's "two people
back to back" and his "a quadrillion other scenarios," quantified.

They then discarded the timer and trained a pairwise classifier instead —
**92%** on fine-grained boundaries, **89–97%** on "are these two from the same task,"
*including* when tasks were interleaved.

**Everything this project has done to `CONTINUE_S` / `APPEND_GAP_S` / `QUIET_CLOSE_S`
has been tuning a constant that is provably capped at 70%.**

## 2. What everyone who solved it actually did

Three fields, three decades, one answer. Nobody draws a boundary.

**JWZ email threading (Zawinski, 1997)** — shipped in every mail client alive.
No timer anywhere. Each message carries a pointer to its parent (`In-Reply-To`,
`References`). Build the graph; **a thread is a connected component.** Missing
pointer → fall back to subject match. A link that would make a message its own
ancestor is dropped.

**Kummerfeld et al., ACL 2019** — the same idea for chat. 77,563 IRC messages hand
annotated with **reply-structure graphs**; each connected component is a
conversation. Re-checking the field's standard corpus with it, they found **89% of
its conversations were wrong** (missing or extra messages) — the whole field had
been benchmarking against bad data. Their model is a feedforward net over GloVe
embeddings with features including **lexical overlap and turn distance**, reaching
**F1 73.5**. Dataset, model and 496,469 auto-disentangled conversations are public.

**Online Conversation Disentanglement with Pointer Networks, EMNLP 2020** — the
streaming form, and the closest to us. Each utterance is embedded as
**timestamp + speaker + text together**; a pointer-attention mechanism selects which
*earlier* utterance it replies to. Explicitly online: decides on arrival, never
needs the future. Its stated contribution is avoiding "time-consuming
domain-specific feature engineering" — i.e. exactly Omar's objection to scenario lists.

**Zero-Shot Dialogue Disentanglement (2021)** gives us the mechanism detail that
makes this implementable, and a calibration on how much labelling we need:

- **A line that starts a new conversation points at *itself*.** The self-link.
  There is no null, no special case, no separate "is this new?" classifier.
- Zero-shot, with no labelled disentanglement data at all: **Link F1 42.2**.
- With **10% labelled data**: **Link F1 69.3** — about **92% of full-data performance**.
  Labels are the highest-leverage thing we can produce.

**LLM-based (Takada & Mori, 2026 — DD-GEPA)**: naive LLM prompting *underperforms*
classical methods, but with the prompt decomposed into task instruction, utterance
representation and output instruction and then optimised, LLM methods now
**surpass** prior work. This matters because we already make an LLM call per line.

## 3. Everyone who kept the timer has our bug

**Omi issue #6551**, open: Limitless Pendant reconnects, backlog audio batch-syncs
in 1–3 minute chunks, **each chunk becomes its own conversation even when seconds
apart**, ignoring the configured Conversation Timeout. Omi runs Silero VAD plus a
timeout constant. Same pendant architecture, same constant, same bug, shipped.

No published work applies disentanglement to **ambient spoken audio** — it is all
text chat (IRC, Reddit). Searched specifically. That is the genuine gap, and it is
the part worth being first at.

## 4. The design

**Delete the segment.** No open row, no closed row, no timer anywhere.

Every heard line answers exactly one question:

> **Which earlier line, if any, am I a continuation of?**

Answer is a line id, or **itself** (= I start something new).

Store it as `parent_line` on the event row. **A conversation is a connected
component.** Compute with union-find on read; it is cheap and it is always current.

### Why this dissolves the bugs rather than patching them

| Today's bug | Under links |
|---|---|
| Late audio splits a call into chunks (Omi #6551, ours) | A late line just adds an edge. Nothing is re-cut. `dirty`, `BACKFILL_SETTLE_S`, `supersedes` all become unnecessary |
| Arrival order changes the answer | Order-independent by construction — components are a set, not a sequence |
| 45 s pause hard-ends a conversation | No timer exists to end it |
| Two people back-to-back merged with no gap | Their lines self-link; two components, no gap needed |
| A boundary error destroys understanding | A wrong edge costs one line of context, not a whole conversation |

### Why it is nearly free

**The triage call already happens on every heard line, and it already sees recent
context.** The link is **one extra field in the JSON it already returns**. No new
call, no new model, no added latency.

```
{"decision": ..., "owes": ..., "continues": "<line id>" | "self"}
```

### Honesty wall

`continues` missing, unparseable, or naming an unknown id → **fall through to the
existing segmenter unchanged.** A confused model can never be worse than today.
Enforced by a test that deletes the field and asserts byte-identical behaviour.

## 5. Plan

**Phase 0 — Labels, before any code.** Label ~300 of Omar's real lines with their
true parent. We have never had ground truth for this and every previous claim was
therefore a guess. The zero-shot paper's 10%→92% result says this is the single
highest-leverage work available. Deliverable: `overnight/gold_links.json`.

**Phase 1 — The link, free.** Add `continues` to the triage JSON. Candidate set =
last **40** lines (the window the masked-hierarchical-transformer work uses).
Self-link means new. Nothing consumes the field yet; it is only logged and scored.

**Phase 2 — The graph.** `parent_line` on the event row. Union-find on read.
Conversations become a derived view, not stored state.

**Phase 3 — Shadow.** Links and timer run side by side on Omar's real day. Log both.
Score Link F1 and Cluster F1 against phase 0's labels. **Bar: beat 70%** — Jones &
Klinkner's proven ceiling for any timer.

**Phase 4 — Switch and delete.** Only if phase 3 clears the bar. Then
`APPEND_GAP_S`, `QUIET_CLOSE_S`, open/closed segments and the escalation path all
get deleted rather than tuned.

**Phase 5 — The card.** Feed groups by connected component. One call, one card.

**Phase 6 — Free signals as tie-breakers.** Speaker-set change (already on-device
via sherpa-onnx). If diarization needs to be stronger: **FluidAudio**, Apache-2.0,
Swift + CoreML, iOS 17+, **DER 17.7%, 141× realtime on an M1**.

### Metrics

Link F1 and Cluster F1 against the labelled set — the field's standard metrics, so
our numbers are comparable to published ones rather than invented. Plus the
existing laws (order independence, silence-never-merges, capture-time-only
membership), which become **true by construction** under a link graph rather than
things to defend with tests.

### Reference points

| | Link F1 |
|---|---|
| Any timer, proven ceiling (Jones & Klinkner 2008) | ~70% precision |
| Zero-shot, no labels | 42.2 |
| 10% labelled | 69.3 |
| Fully supervised (Kummerfeld 2019) | 73.5 |

---

## Sources

- Jones & Klinkner, *Beyond the session timeout*, CIKM 2008
- Kummerfeld et al., *A Large-Scale Corpus for Conversation Disentanglement*, ACL 2019 — https://aclanthology.org/P19-1374/ · https://github.com/jkkummerfeld/irc-disentanglement
- *Online Conversation Disentanglement with Pointer Networks*, EMNLP 2020 — https://aclanthology.org/2020.emnlp-main.512.pdf
- *Zero-Shot Dialogue Disentanglement by Self-Supervised Entangled Response Selection* — https://arxiv.org/abs/2110.12646
- Takada & Mori, *DD-GEPA*, 2026 — https://arxiv.org/abs/2606.07894
- Zawinski, message threading (1997)
- Omi issue #6551 — https://github.com/BasedHardware/omi/issues/6551
- FluidAudio (Apache-2.0) — https://github.com/FluidInference/FluidAudio
