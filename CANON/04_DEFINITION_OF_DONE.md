<!-- CANON v1 · written 2026-07-02 by the HoE agent (post-Devin) · NEW documentation, not Devin's.
     On conflict with any doc outside CANON/ (except MISSION_LOCK.md for live mission status), THIS file wins. Fix errors HERE — never fork. -->

# 04 · THE DEFINITION OF DONE — the one bar

There have been at least six "definitions of done" written into this repo over the months. This file
replaces all of them (see SUPERSESSION at the bottom). There is ONE bar. It never shrinks.

---

## 1. THE ONE-LINE BAR

> **Omar hands a laptop to an investor, walks out of the room, and it just works — beautifully,
> blissfully, no rough edges, nothing fake.**

That phrasing is from `THE_BAR.md` (the "1,000,000% Bar", now superseded by this file). Everything
below just makes that sentence checkable — able to PASS or FAIL, never a vibe.

---

## 2. THE INVESTOR WALKTHROUGH (the literal pass/fail test)

A **stranger** — not Omar, not an agent, nobody helping — does ALL of this, and it feels premium
the whole way:

1. Opens the **URL** → a premium site that explains Anticipy in 10 seconds.
2. Clicks **Get Anticipy** → downloads and runs the engine in **one clean step** (no terminal).
3. The app opens → **onboarding**: it scrapes what they allow, **calls them** (a voice you can't
   tell is AI) to fill the gaps, they confirm → a real profile of them now exists.
4. They **speak or paste a messy day** → real, correct cards appear (tasks inferred, vents ignored).
5. They **swipe** the cards — confirm / deny / allow / feedback — and each swipe changes real
   engine state, not just the screen.
6. They give it a **browser errand** ("return that plant") → it does it on a real browser,
   **stops at money or login**, and hands back to them.
7. At no point does it: spend money without a yes, act on a vent, fake a "done", sound robotic,
   or break.

**PASS = a stranger completes 1–7 unassisted and it feels investor-grade. Anything less is not done.**

---

## 3. THE FAIL CONDITIONS (any ONE = NOT done, no matter how good the rest is)

Compressed from `ANTICIPY_SOURCE_OF_TRUTH.md` §4.7. The product is NOT done if:

- It feels like **separate demos stitched together** anywhere in the loop.
- A stranger needs hand-holding, or an **operator behind the curtain** keeps it useful.
- It **acts on a vent**, sarcasm, or hypothetical — even once. (The cardinal sin.)
- It takes a **money or irreversible action without a confirming ask** — even once, in any mode.
- It **fakes "done"** — claims an outcome it didn't achieve — even once.
- The browser agent **screenshots/surfaces instead of actually operating** the real system.
- Any message is **identifiably AI**: reads like a system, a template, or an error code.
- **Memory doesn't compound** — it re-asks what it already learned, or forgets across days.
- It handles **less than ~half the real workload**, or only on a single good day rather than
  sustained over many real days.
- Any component needs **per-service API/OAuth** instead of working browser-only as designed.
- It only works on **rehearsed scenarios** and breaks on novel tasks, sites, or users.

Two invariants sit above every mode and feature: **money / send-to-a-person / delete / binding
commitment always CONFIRMS**, and **a vent is never a task**.

---

## 4. THREE LEVELS OF DONE — and the proof each one demands

"Done" is never a claim; it is a check that could have failed and did not. Reports are lies;
running is truth. Three levels, three proofs:

| Level | What it means | The proof it demands |
|---|---|---|
| **Step done** | One increment of work inside a plan is finished. | A **wiring-proof** (real command output showing the piece works INSIDE the live flow, not in isolation) pasted into that plan's box in `PLANS/`, **and** the regression gates are not worse (gate = the test suite's fail-set is identical or better vs. baseline, and `safety_mega_eval` still passes). |
| **Milestone done** | A whole milestone (M1…M9) of the locked mission is finished. | The milestone's **PASS output pasted into the STATUS TABLE in `MISSION_LOCK.md`**, with a replayable proof command. No pasted output = still OPEN, whatever anyone says. |
| **Product done** | Anticipy is finished. | **The investor walkthrough (section 2), run by a stranger, unassisted, end to end.** Nothing else counts — not a green suite, not a demo Omar drives, not an agent's word. |

A green checkmark with no runnable proof does not count at any level. Where the live scoreboard
stands today is in `MISSION_LOCK.md`, not here (that file owns live status; this file owns the bar).

---

## 5. SUPERSESSION

This file supersedes THE_BAR.md, DONE_DEFINITION.md, docs/agent_os/DEFINITION_OF_DONE.md,
THE_MISSION.md's done section, ANTICIPY_SOURCE_OF_TRUTH.md §4, ANTICIPY_DONE_VISION's done section.
If they disagree with this file, this file is right; if this file is wrong, fix it here.
