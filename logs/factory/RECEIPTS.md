# ANTICIPY — RECEIPT LEDGER (append-only · the durable record of what is PROVEN done)
Governed by CONSTITUTION.md Law 4 (the receipt is the only currency) and Law 5 (the no-slop law).
Each entry: date · slice · the RECEIPT (a real artifact a human can independently open) · skeptic verdict.
**If a capability is not listed here with a receipt, it is NOT done — no matter what any test or agent claims.**

## Slice status
- **Slice 0 — real read-back completion gate:** ✅ DONE & PROVEN (2026-06-13). See receipt below.
- **Slice 1 — inference core (catch unspoken commitments):** BLOCKED ON A PRODUCT DECISION (Omar). Two
  engineering attempts (1, 1b) both hit the cardinal-sin wall — see the finding below. Safe baseline restored
  (11/16 catch, 0 false-actions). The fork is Omar's to call.
- Slices 2–7: Slice 2 (voice transport) BUILD started in parallel (unblocked); rest NOT STARTED.

## KEY FINDING — the moat's real wall (2026-06-13)
**You cannot raise interrupt-catch (decider→ASK) on uncertain commitments without reintroducing the cardinal
sin.** Two attempts, both adversarially broken:
- Attempt 1 (cheap decider + owed-commitment carve-out): caught 16/16 but false-fired on absurd obligations
  ("unicorn delivered by Monday", "clone the codebase in my head"). Reverted.
- Attempt 1b (SMART decider + dominant reality-test veto): caught 14/16, held 22/24 adversarial killers — but a
  skeptic found 2 STABLE false ASKs on *impossible-scale-but-real-sounding* obligations ("I owe Sam a fully
  shipped product by tonight, should be quick"). Reverted.
**Why it's irreducible:** the boundary between a stressed-real commitment and sarcastic hyperbole is genuinely
fuzzy even for humans (research: agreement on "is this a task" κ≈0.36). No prompt/model can push interrupt-catch
up without some adversarial sarcasm slipping to a false interrupt. Chasing it further is whack-a-mole.
**The architectural answer (needs Omar's product call): DECOUPLE "remember" from "interrupt."**
- INTERRUPT (push ASK/ACT): stay conservative — only the clearly-real commitments (the safe baseline). An
  uncertain line is NEVER pushed (so sarcasm can't trigger the cardinal sin).
- REMEMBER (pull): capture every candidate commitment to memory and surface it only when Omar *pulls up* a
  daily review/digest — where a wrongly-remembered sarcastic line costs nothing (it's skimmed, not acted).
- ⚠️ Capturing to an open_loop with a due_ts is NOT free of cardinal-sin risk — a remembered sarcastic line
  could later TRIGGER a reminder. So "remember" must be pull-surfaced, never auto-triggered, for uncertain lines.
**THE DECISION FOR OMAR:** for a borderline "I owe Sam the deck by 4" — interrupt-ASK now (risks asking on
sarcasm too), or quietly remember it for your daily review (safe, but no live nudge)? This choice sets the whole
act/ask/remember boundary. Recommend: conservative interrupt + generous pull-surfaced memory.

## Honest negatives (reverted; kept so we never repeat them)

### ❌ Slice 1 attempt 1 — owed-commitment carve-out · 2026-06-13 · REVERTED
**Baseline measured live (OpenRouter):** 11/16 reported/indirect commitments caught, **0 vent false-actions**.
Root cause of the 5 misses: they pass triage but the **decider (Room 1.5, cheap `gemini-2.5-flash-lite`)** files
first-person commitments as "self-narration" and defaults SILENT. The attempt added an "OWED COMMITMENT"
category to the decider prompt → catch rose to 16/16. **But it reintroduced the CARDINAL SIN:** skeptic #1
found **6 deterministic false-actions** on grammatically-clean-but-absurd/sarcastic obligations ("I'll have the
unicorn delivered to Karen by Monday", "my boss wants me to clone the entire codebase in my head by Friday",
"I promised the team I'd fix everything by Friday lol") — all fired ASK 5/5 reps. The cheap model can't tell a
real obligation from a sarcastic/absurd one once the prompt says obligations "must NOT be dropped to silence."
2/3 skeptics refuted. **Reverted; suite 56/56 green.** Lesson: raising commitment catch on the cheap decider by
shape alone manufactures false-actions — the exact F34/F37/F38 trap. The fix must add a dominant
sarcasm/absurdity/hyperbole veto and/or escalate the judgment to the SMART model.

## Proven receipts

### ✅ Slice 0 — real read-back completion gate · 2026-06-13
**What changed:** the completion gate no longer trusts the actor's own word.
- `engine/anticipy_engine/hands/api_hand.py` (+169): a LIVE API write (create_event/send_email/...) now issues
  a **second, independent `client.tools.execute()` READ** of the artifact (create_event→GoogleCalendar.ListEvents,
  send_email→Gmail.ListEmails), wrapped in `confirm_stable_artifact` (reads≥2), and returns success **only** if
  the written id is re-observed. Fails closed otherwise (read-miss→failed/None; unverified read tool→needs_human).
  Proof now carries `self_attested:False, verified_by_read:<tool>, read_request_id:<distinct read id>`.
- `engine/anticipy_engine/core/orchestrator.py:_verify` (+19): rejects any proof marked `self_attested:True`
  without `verified_by_read`. Can only reject MORE, never accept more — no Law-protecting check weakened.
- `engine/scripts/test_api_readback.py` (new) + `test_api_hand.py`: fail-closed tests; wired into run_suite.sh.

**RECEIPT (independently verifiable):**
- Full suite **56 passed, 0 failed — SUITE GREEN** (foreman re-ran clean, single run, EXIT=0).
- Adversarial spy: `CALLS=[CreateEvent, ListEvents, ListEvents]`, proof `read_request_id='read-req-2'` (the
  read's id, NOT the write echo). Fail-closed: phantom written id → `status=failed, proof=None`.
- Mutation tests bite: reverting the read-back check OR the `_verify` tightening turns the new test RED.
- **3/3 adversarial skeptics returned `refuted:false`** (self-attestation, suite-green-and-test-bites,
  Law-weakening). The no-slop law also caught the builder overstating "SUITE GREEN" under port-contention —
  corrected: green only confirmed on a clean single run.

**Deferred to Slice 1 (needs Omar's live Google auth):** the genuine end-to-end live read-back (real
CreateEvent → real ListEvents re-observing it); confirming the uncertain Arcade read-tool names for Gmail
drafts/Slack (currently fail closed to needs_human rather than inventing a name).
