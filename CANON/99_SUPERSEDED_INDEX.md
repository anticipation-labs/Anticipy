<!-- CANON v1 · written 2026-07-02 by the HoE agent (post-Devin) · NEW documentation, not Devin's.
     On conflict with any doc outside CANON/ (except MISSION_LOCK.md for live mission status), THIS file wins. Fix errors HERE — never fork. -->

# 99 · THE ARCHIVE INDEX — every old doc, what it was, what replaced it

This repo accumulated ~174 legacy `.md` files across five agent regimes. **None of them is the truth
anymore.** The truth lives in exactly three places: `CANON/` (timeless facts), `MISSION_LOCK.md`
(the live mission + status table), and `PLANS/` (active build plans). Everything below is history —
listed so nobody ever has to guess again which "source of truth" wins. Every path was verified to
exist on disk on 2026-07-02 (`ls <path>` replays the proof).

"Era" gloss (the regime that wrote the doc):
- **FACTORY** — early-to-mid June: the autopilot/factory build-loop regime (foreman + Codex workers + judges).
- **AGENT-OS** — ~06-16→06-20: the `docs/agent_os/` "Memory Dock" regime.
- **OVERNIGHT** — ~06-19→06-23: local Claude overnight runs ("investor-ready by morning").
- **WHITEBOARD** — 06-24: Omar's whiteboard session, captured as `ANTICIPY_SOURCE_OF_TRUTH.md`.
- **DEVIN** — ~06-27→07-01: the remote Devin agent (branch `devin/full-frontend-ui`), replaced by the local HoE agent.

---

## 1. Former "sources of truth" — the war this table settles

Five different files each claimed to be "the single source of truth." Here is the verdict on all of them.

| path | era | what it was | still worth reading for | superseded by |
|---|---|---|---|---|
| `MISSION_LOCK.md` | **LIVE** (locked 2026-07-01 by Omar) | The live mission: milestones, PASS tests, STATUS TABLE, NEEDS-OMAR | **NOT superseded — this is the live authority.** Read it every session. | — (it and CANON/ are the two authorities) |
| `ANTICIPY_SOURCE_OF_TRUTH.md` | WHITEBOARD (06-24) | 227 KB capture of Omar's whiteboards: the one-sentence, how it works, onboarding, 120 use cases, the "fully finished" bar | **KEPT as the deep reference.** §3 (line 218: 100+ use cases across professions) is irreplaceable; §2 onboarding flow is the richest spec of it anywhere | `CANON/01` + `CANON/02` + `CANON/04` (authority); §3 has no replacement — read it there |
| `SOURCE_OF_TRUTH.md` | OVERNIGHT (snapshot 06-23) | Status truth doc; self-labeled "HISTORICAL … superseded 2026-06-24" in its own title | Honest 06-23 status snapshot | `CANON/00_START_HERE.md` + `MISSION_LOCK.md` |
| `CURRENT_STATE.md` | WHITEBOARD (06-24) | "The single authoritative status doc" of its day; declared the other ~30 .md files stale | The 06-24 state of cloud/Railway/Supabase/extension — good history of what worked then | `CANON/05_CURRENT_STATE.md` + `MISSION_LOCK.md` STATUS TABLE |
| `THE_MISSION.md` | OVERNIGHT (06-19) | "Read this FIRST every session" — build to investor-ready overnight while Omar sleeps | The never-fake-done rules (its "you falsely claimed done hundreds of times" is still true) | `MISSION_LOCK.md` (mission) + `CANON/00` (read order) |
| `docs/agent_os/CURRENT_TRUTH.md` | AGENT-OS | "Mutable truth, verified by live command each run — do NOT trust old docs" | The verify-live-before-claiming habit it preached | `MISSION_LOCK.md` STATUS TABLE |
| `README.md` (its "👉 Start here" section, line 7) | WHITEBOARD (06-24) | Pointed newcomers at `CURRENT_STATE.md` as the single dated truth | The one-paragraph product summary at its top is still accurate | `CLAUDE.md` reading order → `CANON/00_START_HERE.md` |

---

## 2. Definition-of-done forks — five bars, now ONE

Five docs each defined "done" differently. All five now defer to **`CANON/04_DEFINITION_OF_DONE.md`**.

| path | era | what it was | still worth reading for | superseded by |
|---|---|---|---|---|
| `THE_BAR.md` | OVERNIGHT (06-19) | "The 1,000,000% Bar": hand the laptop to an investor, walk out, it just works | The checkable, can-fail framing of every line item | `CANON/04` |
| `DONE_DEFINITION.md` | OVERNIGHT ("Omar's guiding star, 2026-06-19") | "THE definition of done. Every other 'what done means' defers to this" (it said — then got forked anyway) | Omar's own phrasing of the star | `CANON/04` |
| `docs/agent_os/DEFINITION_OF_DONE.md` | AGENT-OS | "The finish line (never shrink it)" — the agent-OS regime's bar | Its "never shrink the bar" rule, which survives in CANON/04 | `CANON/04` |
| `THE_MISSION.md` § "WHAT 'DONE' GENUINELY MEANS" (line 19) | OVERNIGHT (06-19) | The done-bar embedded inside the mission doc | "Code exists ≠ done, a test passed ≠ done" — verbatim still the law | `CANON/04` |
| `ANTICIPY_DONE_VISION_2026-06-15.md` | pre-FACTORY synthesis (06-15) | Four research streams synthesized: what "done" FEELS like, how to build that feel, and the path | **KEPT as the feel reference** — the richest description of the product's emotional bar; CANON/04 sets the line, this describes the texture | `CANON/04` (authority); kept for feel |

---

## 3. Devin's docs — era DEVIN, kept separate on purpose

Per Omar's explicit requirement these stay quarantined: they describe the **previous** agent (Devin,
on a remote VM) — its plans, its context anchors, its conversation record. They were never part of
the current read order and never will be. Nothing here is followed; it is evidence and history.

| path | era | what it was | still worth reading for | superseded by |
|---|---|---|---|---|
| `docs/handoff/SENIOR_AGENT_PROMPT.md` | DEVIN (handoff, ~07-01) | The "paste this into the local agent" senior/HoE prompt Devin wrote for its successor | How Devin framed the handoff; what it admitted was broken | `CANON/00` + `MISSION_LOCK.md` (the HoE agent's real charter) |
| `docs/handoff/JUNIOR_ENGINEER_ONBOARDING.md` | DEVIN | Zero-context engineer onboarding incl. "every mistake Devin made" | The candid catalogue of Devin's mistakes | `CANON/00` |
| `docs/handoff/FULL_CONVERSATION_LOG.md` | DEVIN | Every Omar↔Devin exchange with intent/subcontext annotated (later turns verbatim) | **The primary record of what Omar actually asked for, in his own words** | nothing replaces a transcript — kept as evidence |
| `docs/handoff/LOCAL_AGENT_PROMPT.md` | DEVIN | Earlier local-agent prompt variant ("Omar is mad, and he is right to be") | The failure inventory it opens with | `CANON/00` + `MISSION_LOCK.md` |
| `docs/MASTER_TRACK_2026-06-28.md` | DEVIN (06-28) | "Where the work lives, what the owner asked (verbatim), what was built, honest open issues" | The verbatim owner-track and its honest open-issues list | `MISSION_LOCK.md` STATUS TABLE |
| `docs/build/` (MASTER_PLAN, BROWSER_AGENT_DESIGN, BROWSER_AGENT_5YR_PLAN, PHASE_1_FRONTEND_UI, PROGRESS_JOURNAL, reports) | DEVIN | Devin's durable context anchor + browser-agent ("hands") design and phase plans | Browser-hand design rationale; PROGRESS_JOURNAL as its work diary | `PLANS/` (active plans) |
| `docs/build/proof/` (screenshots, scorecards, reports) | DEVIN | Real screenshots and scorecards from Devin's browser-agent test runs | Actual pixel evidence of what the hands could do by late June | superseded only by newer proofs in `MISSION_LOCK.md` |
| `plan-baby-steps/` (OPERATING_PLAN, SCREEN_INVENTORY, REUSE_MAP, TRACEABILITY, plans) | DEVIN | Devin's incremental "build map for the next UI pass" | `SCREEN_INVENTORY.md` + `REUSE_MAP.md` — the best maps of screens and reusable engine capability | `PLANS/` |
| `docs/agent_os/SYSTEM_SPINE.md` | AGENT-OS→DEVIN (Devin adopted it) | "One system, not separate plumbing" — the Event→memory→decide→act→verify spine | The spine idea itself — it survives as a CANON non-negotiable | `CANON/02` (architecture) |
| `docs/agent_os/MEMCTX_BASELINE.md` | DEVIN (06-28) | Measured suite baseline before the memory/context M-steps | Which suite failures pre-dated the MEMCTX work | `MISSION_LOCK.md` (current baseline: 109/10, 2026-07-02) |
| `docs/agent_os/MEMCTX_M0_M7_TEST_REPORT.md` | DEVIN (06-28) | M0→M7 memory+context test report ("ALL GREEN" — on Devin's VM, that day) | The ContextPack design: one builder feeding memory/proactive/browser | `MISSION_LOCK.md` for what is green NOW |

---

## 4. Factory-era control plane — the old build-loop machinery's docs

The FACTORY regime ran build/judge laps with personas and gates. Its **docs** are archive.
**Exception, still LIVE tooling (2026-07-02): `factory/bin/` gate scripts (e.g. `check_wiring.py`,
`verify_gate.sh`) and `scripts/run_suite.sh` (GATE-S) are used by the current regime — the regime
docs died, the tools didn't.**

| path | era | what it was | still worth reading for | superseded by |
|---|---|---|---|---|
| `autopilot/00_START_HERE.md` … `09_REPO_FACTS.md` | FACTORY | The 10-file autopilot operating system (mission, laws, loop, judge, logging, milestones, human gates, repo facts) | `02_LAWS.md` and `08_HUMAN_GATES.md` — early versions of rules that survive in CANON | `CANON/00` + `CANON/04` |
| `autopilot/LESSONS.md` | FACTORY (from 06-06) | Append-only log of repeated mistakes + the fix | **Genuinely worth reading** — hard-won failure patterns (mutating proofs, judged-vs-plumbing) | folded into CANON lessons; original kept |
| `factory/prompts/` (BUILD, FOREMAN, JUDGE, JUDGE_SELFCHECK) | FACTORY | Role prompts for the foreman/builder/judge lap loop | How the judge was made hard to game | `CANON/00` (how the HoE agent operates) |
| `factory/TARGET.md` | FACTORY (v10, 06-13) | The north-star + phase + metric file the foreman steered by | Its guards: `false_action_count==0`, `silent_harm_count==0` — still the law | `MISSION_LOCK.md` milestones |
| `logs/factory/` (CONSTITUTION, FINISH_LINE, FAILURE_MODES, handoffs, morning reports, laps) | FACTORY (06-13→06-15) | The factory's working state, receipts, and morning reports | `FAILURE_MODES.md` — catalogued ways laps went wrong | `MISSION_LOCK.md` STATUS TABLE |
| `AGENTS.md` | FACTORY | Standing instructions for the autonomous build agent | historical only | `CLAUDE.md` + `CANON/00` |
| `CODEX.md` | FACTORY | Rules for Codex workers ("worker army, not the foreman") | The foreman/worker division of labor idea | `CANON/00` |
| `CODEX_BRIEF.md` | FACTORY | Read-only situation brief with REAL/UNVERIFIED labels per claim | Its evidence discipline (claim → file + real test, or say UNVERIFIED) | `CANON/05` + `MISSION_LOCK.md` |
| `00_AMENDMENT_NEVER_STALL.md` | FACTORY/OVERNIGHT | "Never stall, never fake, always move the real task forward" amendment | The anti-stall doctrine — survives in CANON non-negotiables | `CANON/00` |
| `docs/agent_os/` (most: CONSTITUTION, DECISIONS, FAILURES, RECEIPTS, DONE_LEDGER, NEXT_GATE, HANDOFF_NOW, RABBIT_HOLE_EXIT, MEMORY_AND_CONTEXT_PLAN, README, …21 files) | AGENT-OS | The "Memory Dock": per-run memory, decisions, receipts, failure ledgers | `FAILURES.md` + `DECISIONS.md` — real decisions with reasons | `CANON/` + `MISSION_LOCK.md` (SYSTEM_SPINE and MEMCTX rows: see §3) |

---

## 5. Root status/plan litter — the pile of "read me first" files

Every overnight run left a status/plan file at repo root. All verified present 2026-07-02; all archived.

| path | era | what it was | still worth reading for | superseded by |
|---|---|---|---|---|
| `STATUS.md` | OVERNIGHT | Technical log of the `overnight/real-progress` run, artifact ids as they happened | example of receipts-as-you-go logging | `MISSION_LOCK.md` STATUS TABLE |
| `PRODUCT_STATUS.md` | FACTORY (06-13) | Product status snapshot of the factory era | 06-13 state of the world | `CANON/05_CURRENT_STATE.md` |
| `WAKEUP.md` | OVERNIGHT | Morning report of an overnight run ("nothing green unless a checker confirmed it") | its honest PROVEN/NOT-PROVEN labeling style | `MISSION_LOCK.md` |
| `WAKEUP_REPORT.md` | OVERNIGHT (06-23) | Harness-generated report (`overnight/harness.py` against live :8787 + CDP :9222) | the harness pattern: reports generated FROM reality, not typed | `MISSION_LOCK.md` (harness itself still exists at `overnight/harness.py`) |
| `WHEN_OMAR_RETURNS.md` | OVERNIGHT | "Where it actually is (no spin)" — honest handback after an away period | 2-minute see-it-yourself framing | `MISSION_LOCK.md` NEEDS-OMAR |
| `PENDING_FOR_OMAR.md` | post-WHITEBOARD (06-25→26) | The batch of items only Omar could unblock + a morning handoff (suite 112→113 that night) | which asks were open on 06-26 | `MISSION_LOCK.md` NEEDS-OMAR |
| `PLAN_TO_DONE.md` | WHITEBOARD (06-24) | 10-subsystem audit of live code + engine, each finding with file:line or a live probe; paired with ANTICIPY_SOURCE_OF_TRUTH | the audit method (findings must carry file:line evidence) | `PLANS/00_OVERARCHING.md` |
| `ANTICIPY_EXECUTION_PLAN.md` | mid-June (grounded in the 06-15 vision + the two spam failures) | Ordered milestones to the "Owner Test", each with a falsifiable exit check | falsifiable-exit-check discipline; the spam-failure record | `PLANS/00_OVERARCHING.md` |
| `THE_PLAN_TO_FLUSH.md` | post-WHITEBOARD (~06-25) | Omar's demand verbatim: stop testing pieces — the WHOLE product through the front end is the unit of success | Omar's whole-product rule, in his words | `PLANS/` + `CANON/04` |

Not individually tabled but same verdict (root, archive): `ANTICIPY_PLAN.md`, `ANTICIPY_PRD.md`,
`ANTICIPY_ARCHITECTURE.md`, `ANTICIPY_UX_SPEC.md`, `ANTICIPY_ENGINE_AUDIT_2026-06-15.md`,
`LEDGER.md`, `THE_FORGE.md`, `AUTONOMY_LINE.md`, the two 06-22 ledgers, `AMAZON_RETURN_HANDOFF.md`,
`ANTICIPY_AGENT_OPERATING_STRUCTURE.md`. History → this index; truth → CANON/ + MISSION_LOCK.md.

---

## 6. The going-forward rule (never litter again)

- **New truth lands ONLY in `CANON/` (timeless), `MISSION_LOCK.md` (live mission + status), or `PLANS/` (active plans).**
- **No new root-level `.md` file, ever, without an entry in THIS index** saying what it is and why it had to exist.
- If a CANON file is wrong, **fix it in place** — never write a rival doc. Forking the truth is how the war in §1 happened.
- When a doc dies, it does not get deleted — it gets a superseded banner and a row here.
