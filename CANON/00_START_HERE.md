<!-- CANON v1 · written 2026-07-02 by the HoE agent (post-Devin) · NEW documentation, not Devin's.
     On conflict with any doc outside CANON/ (except MISSION_LOCK.md for live mission status), THIS file wins. Fix errors HERE — never fork. -->

# START HERE — the front door to the Anticipy repo

You are in `/Users/omarebrahim/Anticipy-devin`, branch `hoe/build`. This file tells you what
Anticipy is, which documents to trust, and how work gets proven here. Read it before anything else.

---

## 1. THE TWO-AUTHORITY RULE

What is the product / how does it work / what does done mean → **CANON wins.**
What are we working on right now / is X proven → **MISSION_LOCK.md wins.**
Everything else in the repo is archive — indexed in `CANON/99_SUPERSEDED_INDEX.md`, never followed.
If CANON is wrong, fix it in place, same commit — never fork.

---

## 2. ANTICIPY IN THREE SENTENCES

1. Anticipy is a **proactive personal assistant — "Donna from Suits"** — that listens to your real
   day, catches the things you get told or asked to do, and quietly handles them inside your own
   real systems (your logged-in browser, calendar, email, voice), checking with you like a sharp
   human before anything that matters; the goal is that it genuinely runs **~50% of your workload,
   end to end** (source: `ANTICIPY_SOURCE_OF_TRUTH.md`, section 0).
2. **The product is the inference**: it hears messy natural speech and silently lets non-tasks pass —
   venting, sarcasm, hypotheticals — because acting on a vent is the cardinal sin, while money and
   irreversible actions always require your confirmation, in every mode.
3. The litmus for "done" (from `ANTICIPY_DONE_VISION_2026-06-15.md`): **you vent about quitting your
   job and nothing happens — and twenty minutes later it quietly reminds you about your mom's
   prescription that you mentioned to someone else.** Silence on the vent, the catch on the buried
   real task, both in the same hour — that contrast IS the product.

---

## 3. THE MAP (what to read, in order)

| File | What it is |
|---|---|
| `CANON/00_START_HERE.md` | This file — the front door and the rules of trust. |
| `CANON/01_WHAT_ANTICIPY_IS.md` | The product truth: the one sentence, the 7-point model, a day living with it, onboarding. |
| `CANON/02_PROACTIVE_ENGINE.md` | How proactive works AND must feel; the ONE pipeline (the law); the graveyard of all 11 engine versions. |
| `CANON/03_ARCHITECTURE.md` | The technical map: pieces, spine, directory guide, endpoint surface, the seam table. |
| `CANON/04_DEFINITION_OF_DONE.md` | The single done bar: the investor walkthrough, the fail conditions, three levels of proof. |
| `CANON/05_CURRENT_STATE.md` | The one living status snapshot (dated; stale >7 days = re-verify before trusting). |
| `CANON/99_SUPERSEDED_INDEX.md` | The index of every archived legacy doc — what it was, why it's archive. |
| `MISSION_LOCK.md` (repo root) | The LIVE mission + status ledger: the M1–M9 plan, the STATUS TABLE with pasted proofs, detours, and the NEEDS-OMAR list. Newest dated entry wins. |
| `PLANS/` | Executable fix plans, written so a non-coder can supervise them — each step carries a proof box (a command + the pasted output). |

---

## 4. HOW I (THE HOE AGENT) WORK

Distilled from `MISSION_LOCK.md` (OPERATING PROTOCOL) and `CLAUDE.md` (non-negotiables). These are
not preferences; they are the rules.

**Verify by running.** "Done" is never a claim — it is a check that could have failed and did not.
Run the real thing, paste the output. A statement of done without an attached, replayable result is
a violation. Never fake done; honest handbacks beat false success.

**Commit every win.** Every proven step is committed on `hoe/build` (the working git branch). If it
isn't in `git log` with its proof, it didn't happen.

**Honest handbacks.** Anything that physically needs Omar (his logged-in accounts, a live phone
call, deploy credentials) goes on the **NEEDS-OMAR list in MISSION_LOCK.md** — queued, never faked.

**The standing gates** (run these before claiming anything):
- `bash scripts/run_suite.sh` — the regression suite, **stub-forced** (it runs against a fake
  built-in model, so it's free and deterministic). Baseline 2026-07-02: **109 passed / 10 failed.**
  The rule is not "all green" — it is **the fail-set may never grow.** A new failure = a regression.
- `factory/bin/check_premium_copy.py` — no developer strings (IDs, ports, JSON, "task #24a") may
  ever reach user-visible copy.
- `factory/bin/check_wiring.py` — **nothing is built until it is wired**: a component only counts
  when it's connected into the live flow, not sitting orphaned in the repo.

**GATE-M protocol (milestone proof).** The milestone batteries — `overnight/m1_battery.py` must be
**6/6**, `overnight/m2_copy_test.py` must be **PASS**, `overnight/m3_integration_test.py` must be
**ALL PASS** — are run against a **FRESH engine with a FRESH data dir**. They are state-sensitive:
leftover cards/memory from a previous run change the results (verified 2026-07-02). A battery run
against a stale engine proves nothing.

**Running the engine** (the local Python brain the app and tests talk to):

```
engine/.venv/bin/python -m uvicorn --app-dir engine anticipy_engine.main:app --port 8787
```

(For isolated test runs, MISSION_LOCK's proof commands use port 8790 with mock channels/hands and a
throwaway `ANTICIPY_DATA_DIR` — see the STATUS TABLE header there for the exact launch line.)

**Where progress is recorded** — three places, always: the **MISSION_LOCK STATUS TABLE** (pasted
PASS output per milestone), the **proof boxes inside `PLANS/`**, and the **git log** on `hoe/build`.

---

## 5. WHAT NOT TO READ

This repo carries roughly 174 legacy `.md` files (well over 200 counting every subfolder) from
earlier eras — old handoffs, old constitutions, old status ledgers, old plans. They are **archive**:
historically interesting, operationally dead. In particular, the old read-order stacks — the banner
chain in the old `CLAUDE.md` (THE_MISSION → factory handoffs → foreman docs), the `docs/agent_os/`
Memory Dock, `autopilot/`, and `docs/handoff/` (Devin's handoff docs) — describe regimes that no
longer govern this repo. Do not follow instructions found in them; do not resolve conflicts by
reading more of them. `CANON/99_SUPERSEDED_INDEX.md` indexes what each one was and why it was
superseded. If something in the archive seems importantly true and missing from CANON, the fix is
to add it to CANON in the same commit — never to resurrect the old doc.
