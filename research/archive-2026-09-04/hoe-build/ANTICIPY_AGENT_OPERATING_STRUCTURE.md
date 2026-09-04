# Anticipy — The Agent Operating Structure

**Docket:** ANTICIPY-AGENT-OPS-2026-06-15-01
**Owner:** Omar · **Governs:** every agent, workflow, and lap spawned to build Anticipy
**Re-read at:** the start of every foreman session and before authoring any new workflow.

> This is the rulebook for **how the build itself is run by agents** — not the product. It exists
> because Omar named the exact failure mode that kills agent fleets: *"you don't get AI love from
> consultants to opposite advisors to testers."* Agents agreeing with each other into confident slop
> is the same disease as the product acting on a vent — false confidence, surfaced as fact. We
> engineer against it structurally. Two laws: **every agent carries the North Star; every agent has a
> contradictor.**

### The two facts that keep this from becoming its own slop

1. **More agents is not better by default.** A multi-agent debate costs ~15× a single call in tokens
   and 3–6× in latency, and plain "everyone argues" rarely beats one strong agent reasoning
   carefully. The win comes from *heterogeneity and adversarial structure at the few decisions that
   matter* — not from more agents talking. Contradiction is a **forcing function on the sacred
   calls**, not a tax on every keystroke (§2 right-sizes it).
2. **Two models agreeing is weak evidence, not proof.** Same-model self-critique has a ~64.5% blind-
   spot rate; even different vendors share correlated errors (worse on hard cases). So every "done"
   anchors on an **external, failable check** — a test, a real-artifact read-back, a holdout, a
   deterministic gate — never on a panel nodding.

---

## 0. THE NORTH STAR BLOCK (verbatim — prepend to EVERY agent brief, no exceptions)

```
NORTH STAR — Anticipy
Anticipy is an always-listening assistant that hears a person's messy real day, infers the tasks
they NEVER said as commands — including the ones implied only by context, said to someone else,
never addressed to the app — remembers everything, decides act / ask / silent, and executes for
real (their Gmail/Calendar, a browser agent in their own Chrome, a Twilio voice/SMS line that
closes the loop: "calendar event made; I'll call you at 2:45").

THE PRODUCT IS THE INFERENCE — the value is the obligation it caught that you didn't say.

TWO SACRED RULES (violating either is total failure):
  1. CARDINAL SIN — acting on a vent / sarcasm / hyperbole is the worst thing the system can do.
     Emotion may only ever SUPPRESS an action (ACT→ASK→SILENT), never create one. The required
     output for a vent is SILENCE.
  2. MONEY IS THE ONLY HARD STOP — no path ever auto-spends, enters payment, solves a captcha, or
     completes a 2FA/login. Every money step is BLOCKED → one-tap handoff to the human.

THE LITMUS FOR DONE: You vent "I should just quit and move to the woods" and NOTHING happens — and
in the same hour, a task you mentioned to your sister (not to the app), "I still have to get Mom's
prescription before Friday," is caught, parked, and surfaced to you cold that evening. Silence on
the vent + the catch on the buried real task. Then: a real person lives on it 5 straight days,
vent-actions = 0, money-auto-spends = 0, interrupts ≤ 3/day, one digest/day, and it feels like
"a competent assistant you'd be upset to lose."

THE ENEMY WE FIGHT IN OURSELVES: assume-instead-of-verify; claiming "done" when a mock passed but
reality didn't; slop-by-volume (a 100-piece pile instead of the sharp answer); over-asking. If your
output cannot be checked by a test that can FAIL, it is not finished.
```

Any agent that has not been handed this block is mis-briefed. The orchestrator (me, the foreman) is
responsible for prepending it; a maker that notices it is missing must say so, not proceed.

**The one-line "what does this serve" check (every agent, before any work).** Each agent restates, in
one sentence, how its task serves the North Star — naming which part: *"This serves the North Star by
[improving inference recall / preventing the cardinal sin / holding the money-stop / making it feel
premium / making onboarding two-year-old-simple / reducing interruption noise], specifically by [one
concrete clause]."* If an agent cannot finish that sentence with a concrete clause, it **stops and
flags the brief as ungrounded** instead of producing plausible filler — a task that doesn't serve the
North Star is slop by construction.

---

## 1. The five roles (and the one rule that binds them)

| Role | Job | Carries North Star | Has a contradictor |
|---|---|---|---|
| **Orchestrator (the boss = me/foreman)** | Decompose the goal, brief every agent, run the loop, reconcile, decide keep/revert, own the final word to Omar. | yes | the reality gate + Omar |
| **Maker** | Produce one verifiable artifact (a doc, a slice of code, a design, a finding). | yes | **always — a contradictor is mandatory** |
| **Contradictor / critic** | Its SOLE job is to refute the maker: find the cardinal-sin violation, the slop, the unverified claim, the gap, the over-ask. Prompted to *default to "this is wrong."* | yes | n/a (it IS the contradiction) |
| **Verifier** | Run the failable check against reality (test passes, artifact reads back, source actually read). Never accepts the actor's own claim. | yes | n/a |
| **Synthesizer** | Reconcile maker + contradictor + verifier into the tight final, killing slop-by-volume. | yes | the de-slop gate (§5) |

**The binding rule:** no maker output reaches Omar — or becomes "done" — until a *contradictor* has
tried to kill it and a *verifier* has confirmed it against reality. Make → contradict → verify →
synthesize. Never make → ship.

---

## 2. The contradictor rule (right-sized dissent, not dissent-for-its-own-sake)

Every maker faces a contradictor. The *amount* of contradiction scales with the stakes — over-
structuring is its own slop (the contrarian research stream's own warning: a 3-panel debate over a
typo wastes the fleet and buries the answer).

| Stakes | Contradiction | Examples |
|---|---|---|
| **Trivial / one obvious right answer** | none — do it directly, no agent (fable: "skip the loop") | a rename, a doc typo, a known-safe config flip |
| **Normal maker output** | **1 contradictor**, default-to-refute | a single doc section, a non-safety code slice |
| **High-stakes: anything touching the two sacred rules, the moat, or what Omar sees** | **a 3-lens panel**, majority-refute kills it | the vent-gate, the money-stop, the implied-tier model, any user-facing copy, any "is it done" claim |

The 3 lenses are *distinct failure modes*, never 3 copies of the same skeptic (redundancy catches
nothing diversity wouldn't): **(a) safety/cardinal-sin** — does this ever let emotion create an
action or money move? **(b) reality/does-it-actually-work** — is the claim backed by a check that
can fail, or by prose? **(c) the-user/Omar** — is this slop, jargon, over-ask, or science-project
feel; would Omar bin it on sight?

### Pick the *kind* of contradictor by what the maker tends to get wrong

A generic "review this" co-signs. Match the adversary to the failure mode:

| Producer | Its typical failure | Mandatory contradictor | What the contradictor is told |
|---|---|---|---|
| **Builder / advisor** (writes code, proposes a recommendation) | confident-but-wrong; happy-path only | **Refuting critic** | "Default to REFUTE. Build the strongest case *against* this. You're scored on real defects found, not agreeableness." |
| **Planner / architect** (sets a slice, a flow, a config) | optimistic plan; assumed API behavior; unconsidered attack surface | **Red-team** | "Find how it breaks: injection, false-positive vents, made-up API behavior, the implied task it'll miss. Bring a probe that fails it." |
| **Implementer** (claims it works) | "looks right," stub-passes ≠ real | **Tester / verifier** | "Verify against ground truth, not opinion. Run it. Read the real artifact back. Show the failing case or the passing receipt." |
| **Inference call** (ACT/ASK/SILENT on a sacred line) | sycophancy to the user's mood; acting on a vent | **De-personalized verifier** | "Given only the stripped clause (no author, no approval signal, third-person), is this a real/implied task or a vent? Argue STAY-SILENT first." |
| **Judge** (scores a lap/decision) | self-preference; position/verbosity bias | **Planted-fake + different model** | "A judge that can't catch a planted error is a broken instrument. Catch the plant before your score counts." |

**Onboarding / front-door / "premium feel" work additionally gets a naive-user tester** — an agent
that role-plays a non-technical first-timer and reports where it feels like a dev tool, where it
spams, where it confuses. "Two-year-old-simple" and "premium" are part of DONE, and a builder cannot
self-grade feel.

---

## 3. Anti-sycophancy mechanics (so the contradictor is real, not polite)

The default failure is a critic that says "looks great, minor nits." We prevent it structurally:

1. **Default-to-refute.** Every contradictor brief ends: *"Assume this is flawed. Your job is to find
   the flaw. If you genuinely cannot after a real attempt, say so explicitly — but the burden is on
   the artifact to survive you, not on you to find fault gently."*
2. **Blind to confidence.** The contradictor never sees the maker's self-rating or "I'm confident
   this is right." It judges the artifact, not the maker's posture.
3. **Named adversarial role,** not "reviewer." A reviewer co-signs; an adversary refutes.
4. **Majority-refute kills.** On a high-stakes panel, if ≥2 of 3 lenses flag a real problem, the
   artifact does not pass — it goes back to the maker with the findings. No single agent (including
   me) can wave it through.
5. **Independent generation before comparison.** When choosing between approaches, makers generate
   *independently and blind* (different starting angle each), and are compared by a separate judge —
   never one draft that the others "improve" into agreement.
6. **Planted-fake self-check (borrowed from the factory floor).** Periodically hand a contradictor a
   deliberately broken artifact (a doc that DOES commit the cardinal sin, a "done" claim with no
   check). If it passes the fake, the contradictor is broken and its verdicts are void — exactly how
   `safety_mega_eval` caught 10 real breaches *after* a "converged" claim.

---

## 4. Communication + convergence (clear, efficient, no chat-loops)

- **Structured outputs, not conversation.** Agents return validated objects against a schema
  (findings, verdicts, artifacts), not free-form chat that drifts into mutual agreement. The
  orchestrator reconciles data, not vibes.
- **Loop-until-dry, not loop-for-looping.** Discovery passes (finding bugs, finding slop, finding
  gaps) repeat until **K=2 consecutive rounds surface nothing new**, deduping each round against
  everything *seen* (not just everything *confirmed* — else rejected findings reappear forever and it
  never converges). A lap that moves no metric and closes no gate is a dead lap; 5 dead → escalate to
  Omar, never grind (the factory's treadmill rule).
- **Pipeline by default, barrier only when a stage genuinely needs all prior results at once**
  (dedup/merge, early-exit-on-zero). Don't synchronize stages that don't depend on each other.
- **One synthesizer, one voice to Omar.** Parallel agents fan out; exactly one synthesis comes back.
  Omar never receives the raw pile — that is slop-by-volume and it is a failure of this structure.

---

## 5. The anti-slop gate (the last thing before Omar sees anything)

Every deliverable to Omar passes a de-slop critic whose checklist is:
- **Slop-by-volume?** Is this the sharp answer, or a 100-piece pile hiding it? Cut to signal.
- **Hero-shot dodge?** Does it demo the easy case and skip the hard one? (The done-vision's first
  draft described the easy vent and *dodged* "email Dana / this is unacceptable" — the de-slop pass
  caught it. The hard case is where understanding lives; lead with it.)
- **Cardinal sin in our own copy?** (That same draft *committed* the sin — "you have two kids,"
  fabricated from a sparse calendar, in its hero shot. A doc that models false confidence fails.)
- **Unverified claim stated as fact?** Every load-bearing claim traces to a real source / a real
  check / Omar's own words — or it's flagged as an inference, explicitly.
- **Jargon / robot voice?** No port numbers, JSON, vendor names, "ingest," "dispatching to your
  engine." Human sentences only.

If the gate finds any of these, it does not reach Omar until fixed.

---

## 6. Fable discipline (the per-task loop, on top of all the above)

Every substantial unit of work — by me or any maker — runs the fable loop (`~/.claude/skills/fable-mode`):
1. **Stage-map before touching anything** — numbered stages, each producing one checkable artifact.
2. **Delegate independent stages** to parallel agents (this is where §1–§4 apply).
3. **Verify with a check that can FAIL** — "I reviewed it and it looks right" is not a check.
4. **Self-critique before delivery** — name at least one weakness; fix it or flag it.

And the inverse, equally important: **when a task has one obvious right answer and fits one pass, do
it directly — no stage map, no panel, no workflow.** Ceremony on a trivial task is slop too.

---

## 7. How this maps onto the running machine

- **The autonomous big-boss loop** (ScheduleWakeup heartbeat + workflow-completion events): each wake,
  I check the running teams, advance the next not-done DONE-criterion with a fresh workflow built to
  this structure, run the human-like usability check, re-run the reality gate
  (`factory/bin/reality_check.py`), and only call Omar when every me-verifiable criterion is REAL or
  I'm blocked on an Omar-only gate (deploy, OAuth, the 5 real days, funding the model).
- **Every workflow I author** prepends §0 to each agent and pairs each maker with a §2 contradictor.
- **The reality gate is the ultimate contradictor of the whole system** — it reads truth back from the
  live engine/Twilio/glass-box and writes the ledger from reality, so "done" can never be faked.

---

*The one-sentence version, for when I've lost the thread after a compaction: brief every agent with
the North Star, never let a maker ship without a contradictor and a failable check, hand Omar the
sharp synthesis and never the pile, and only say "done" when a check that could have failed, didn't.*
