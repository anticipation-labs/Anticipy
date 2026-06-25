# THE FORGE — the system that forces Anticipy genuinely done

> The forcing mechanism. Reads with `ANTICIPY_SOURCE_OF_TRUTH.md` (the bar = §4) and `PLAN_TO_DONE.md`
> (the path). This file answers the two questions that decide everything: **why every prior loop/factory
> failed, and how this one is engineered to actually converge** — over a goal that is NOT binary.

---

## Why every prior loop/factory FAILED (named, so we never repeat them)

1. **No un-fakeable grader.** "Done" meant an agent *said* done → it faked → the number snapped back.
   This is the #1 killer. Every other failure compounds it.
2. **The goal is non-binary.** A loop chasing the word "done" over an asymptotic goal never converges,
   so it wanders — it digresses instead of finishing.
3. **Context died at compaction.** The agent forgot the real definition, re-derived a smaller/wrong
   goal, and drifted. "By 20% you forget what 0% said."
4. **Manager-mode.** The orchestrator spawned agents and stopped doing the meticulous per-piece work,
   so the output was wonky — assembled, not built.
5. **Environment chaos.** It built on the wrong engine tree / extension copy, and the work evaporated.
6. **Grinding for its own sake.** Motion got logged as progress; nothing actually closed.

## The five locks that make THIS one converge

1. **Binary GATES over a non-binary goal.** We never chase "done." We chase gates. Each gate is a
   script that drives the REAL product and exits **RED unless it genuinely works**, emitting a receipt
   (a curl result / a glassbox trail / a replay) that **cannot be faked by talking**. The non-binary
   whole becomes a finite set of binary, un-fakeable checks. *(kills #1, #2)*
2. **The RATCHET — green never regresses.** Every passed gate joins a suite re-run **every cycle**.
   Any gate going red **reverts that cycle**. Green only grows. This is the "40% junk → 90%, never
   digress" mechanism: the gates ARE the memory — they fail loudly the instant anything backslides.
   *(kills #2-digression, #3)*
3. **Adversarial verification — the builder never grades itself.** Every gate I claim green is handed
   to independent skeptic agents whose ONLY job is to prove the receipt is faked or the fix is shallow.
   A gate is green **only if it survives**. Builder and grader are separated. *(kills #1, #4-faking)*
4. **The builder BUILDS; agents only verify.** The main loop does the meticulous, per-piece code
   itself — bit by bit, big plant and small plant. Agents are used ONLY for grounded discovery and
   adversarial verification, **never** to do the core work. The moment I'm "just routing," I've
   already failed. *(kills #4)*
5. **Durable memory + one trunk.** The bar (§4), the plan, the gates (`forge/`), and the live
   `LEDGER.md` live in files on ONE trunk (`factory/build`, one engine, one extension). A fresh /
   compacted agent reads them and is instantly the last agent — with the gates as un-fakeable memory.
   *(kills #3, #5)*

## The non-binary tail (the parts that genuinely aren't binary)

Browser reliability on arbitrary real sites, and the multi-day owner test, are **not** binary. Their
"gate" is a **measured number with a defined floor** that the ratchet forces to never drop:
real-task success rate ≥ floor across N sites; days-survived; vent-actions == 0; money-confirmed ==
100%. Done for these = **the number holds at/above floor across real runs**, not a checkbox. This is
how a non-binary finish is made loop-able without self-deception.

## The operating loop (one cycle — what "running it" means)

1. Pick the **lowest RED gate** in `PLAN_TO_DONE.md` order.
2. The **builder (me)** does the meticulous code to make it genuinely green — read the real code, edit
   surgically, restart/reload, test against the live product.
3. Re-run **that gate + the FULL ratchet** (`forge/gates.py` + `scripts/run_suite.sh`). Anything red →
   fix or `git revert`. **No green movement for K=3 cycles → STOP, write the wall to `ESCALATION.md`,
   don't grind.**
4. **Adversarial-verify** the new green (skeptic agents try to break it). Survives → lock into the
   ratchet + `LEDGER.md` + commit on `factory/build`. Doesn't → back to step 2.
5. If a gate needs Omar (a login / Twilio / a Railway decision), mark it **BLOCKED-ON-OMAR** in the
   ledger with the exact one-step unblock, and move to the next **unblocked** gate. Never fake it,
   never stall the whole loop on it.

## What "genuinely done" means here (no self-deception)

All buildable gates GREEN + held by the ratchet + adversarially verified; the Omar-blocked gates
**wired and mock-verified**, waiting only on his one-time unblock; and the non-binary tail's numbers
at/above floor across real runs. That is §4. Anything short of it is reported as **exactly** what it
is — green count, blocked count, and the floors — never as "done."

## The honest limit (stated up front, because pretending is the original sin)

Some gates **cannot** go green without Omar (he must be logged into his accounts for a real-Chrome
act; Twilio + a tunnel for voice; a Railway volume + tenancy call for cloud per-user). The loop drives
**everything that doesn't need him** to real green, wires the rest to one-step-from-green, and leaves
an honest ledger. "Everything done" without his unblocks is not physically possible — and claiming it
would be the exact failure this whole system exists to prevent.
