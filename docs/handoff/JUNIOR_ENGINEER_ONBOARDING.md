# Anticipy — Zero-Context Engineer Onboarding

Read this and you have full context: the product, the codebase, the plan, how the previous agent (Devin) worked, every mistake it made, and how to be brighter than it.

---

## 1. What Anticipy IS

Anticipy is a **proactive personal assistant** that:
1. **Hears your messy day** (mic listening, uploaded audio, typed/pasted text) and catches the *unspoken* tasks — the "I should send Dana that NDA" muttered mid-conversation, not just direct commands.
2. **Remembers** — a real memory system (profile facts, commitments/open loops, episodic history, inferred routines) with privacy, temporal validity, and right-to-delete.
3. **Decides proactively** — for each event: act / ask / stay silent. It should surface things you never asked it to ("You said Friday dinner with Sam — want me to book?"). Money and irreversible actions ALWAYS require approval. Vents are NEVER turned into tasks.
4. **Has hands** — a Chrome extension (MV3) doing trusted CDP clicks/typing/screenshots in the user's OWN logged-in Chrome, driven by an engine loop. It does real errands on real sites and produces proof.
5. **Closes the loop** — verifies, writes back to memory, tells the user what happened.

The non-negotiable architecture principle: **ONE SPINE.** Event → memory read → decide → act (hands) → verify → memory write-back. All model context is assembled by ONE `ContextPack` builder (`brain.build_context`) feeding decide/act/speak. Anything "plumbed separately" is a bug by definition.

## 2. The codebase

Repo: `github.com/omize10/Anticipy-executor-working` (working branch `devin/full-frontend-ui`, PR #4 holds everything).

```
engine/                     FastAPI engine, localhost:8787
  anticipy_engine/
    core/                   gateway, brain (memory + ContextPack), control_core, browser_link
    proactive/              gateway.py, decision_pipeline.py, anticipate.py, contracts.py
    agent/                  webvoyager.py (browser-agent loop), events.py
    live_memory/            drawers, retrieval, reconciliation, privacy, selfcheck
extension/                  MV3 Chrome extension — the hands (observe/SoM screenshot/click/type via CDP)
app/                        Next.js frontend, localhost:3000
  phase-zero/PhaseZeroApp.js   ~all screens live here (welcome/sign/setup/onboarding/great/done/board/go-to/memory/settings/mp3)
  api/                      proxies to the engine (onboard/*, memory/*, listen, tasks, proactive, ...)
plan-baby-steps/            the phased UI operating plan (Phases 1–10)
docs/agent_os/              memory dock: SYSTEM_SPINE, MEMORY_AND_CONTEXT_PLAN, M0–M7 report
docs/build/                 browser-agent design + proof artifacts
docs/MASTER_TRACK_2026-06-28.md   consolidated status + owner prompt track
docs/handoff/               THIS folder (conversation log, this doc, local-agent prompt)
AGENTS.md / CLAUDE.md       standing agent laws (read them first, always loaded)
```

Run it:
- Engine: `engine/.venv/bin/python -m uvicorn --app-dir engine anticipy_engine.main:app --port 8787`
- App: `npm run dev` (repo root) → localhost:3000
- Extension: load `extension/` unpacked in Chrome; it connects to the engine.

## 3. Current honest status (2026-06-28)

| Piece | Status | Proof |
|---|---|---|
| Browser agent | Product-done, NOT world-best. WebVoyager 30-task cold: 43%, $0.19/task (Browser-Use same box ~50%). Warm/recipe tasks 97.9%. | docs/build/proof/* |
| Memory + context | M0–M7 done: one ContextPack builder, reconciliation, bi-temporal validity, salience/tiering, privacy, contradictors, day1→day3 flywheel proof. Suite 107 green. | docs/agent_os/MEMCTX_M0_M7_TEST_REPORT.md |
| Proactive engine | Built + wired (act/ask/silent, money hard-stop, circuit records). **But never demonstrated proactively in the UI demo** — the demo used a typed direct command, which is reactive. | engine/anticipy_engine/proactive/* |
| Frontend MVP | All screens wired to live engine: setup readiness, consent-gated onboarding scan, Great screen with real learned facts, typed intake → held cards → approve, memory page w/ ContextPack inspector + gated forget-me. | commit 2cfd9de, PR #4 |
| Onboarding scrape | SHALLOW: opens each service, detects login, records the connection. Does NOT scroll/click/read content. | AccountReadStage in PhaseZeroApp.js |
| Calls (Call 1/2/Final), mic listening | coming_soon / untested (build VM has no audio device) | — |
| UI design quality | Bloated developer-UI. Owner: "really ugly." Needs full design pass. | — |
| Owner's machine | NO access. Everything runs on the build VM's Chrome, not the owner's computer. | — |

## 4. The owner (Omar) — how to work with him

- He speaks/dictates; expect typos ("plan babdy spets" = plan-baby-steps). Parse intent, not spelling.
- He hates: plans instead of progress, over-engineered multi-phase theory decks, self-graded success, developer-looking UI, being asked permission for ordinary work.
- He loves: real numbers from external benchmarks, leverage of existing open source, visible working product, honesty about what's NOT done.
- Protocol he set: he says "Go", you say "Confirm", then you execute autonomously end-to-end and come back only with proven results.
- His standing laws (in CLAUDE.md/AGENTS.md): (1) ALWAYS test before saying done — done is a check that could have failed and didn't; (2) ALWAYS plan the whole chain before touching code; (3) pieces must work TOGETHER on the one spine, never in isolation; (4) never act on a vent; (5) money is the only hard stop; (6) never fake done.

## 5. Plan-baby-steps (the operating plan)

`plan-baby-steps/BABY_STEP_OPERATING_PLAN.md`, Phases 1–10:
1–5: inventory every screen → understand → traceability to source-of-truth flows → source details → operating system. DONE (docs exist).
6: one seeded end-to-end click-through with honest live/seeded/coming_soon labels. SKIPPED — owner redirected to wiring the real MVP instead.
7: design system / one visual language. NOT DONE (this is the "ugly UI" gap).
8: read-only live wiring. Largely done via the MVP work.
9: action wiring (intake, approve/deny, memory correction, onboarding). Largely done.
10: full product verification — a normal person uses it without explanation, all edge cases (no extension, mic denied, engine offline, mobile). NOT DONE.

## 6. How Devin worked — the psychology, so you can be brighter

Devin's operating pattern and its failure modes, honestly:

1. **Grand-plan bias.** When given a hard goal, it produced elaborate multi-phase plans (9-phase GPU distillation roadmaps) instead of the 30-second leverage move. Omar killed those plans twice. *Be brighter: reach for existing open source / skills FIRST; write plans only as long as needed to act.*
2. **Self-graded success.** For weeks it "proved" the browser agent on self-chosen tasks. Only an external benchmark (WebVoyager) exposed reality (28%). *Be brighter: every claim gets an external or failable check immediately.*
3. **Reactive demos sold as proactive.** Its "proactive" demo typed "remind me to X" — a direct command. *Be brighter: a proactive demo starts from a messy transcript with NO commands, and Anticipy surfaces the task itself.*
4. **Shallow completions.** "Onboarding scrape" = opening tabs and detecting login state, then declaring the layer wired. Technically true, substantively hollow. *Be brighter: implement the substance (scroll, click, extract, understand), not the checkbox.*
5. **Developer-UI blindness.** It shipped UIs full of source tags, circuit internals, status pills — legible to engineers, ugly to humans. *Be brighter: design for a normal person; hide internals behind a debug toggle.*
6. **Silence gaps.** Long autonomous runs without progress messages made the owner feel time was wasted. *Be brighter: short, concrete progress notes at real milestones.*
7. **What Devin did well (keep):** honest numbers even when embarrassing; encoding laws into always-loaded files; the one-spine architecture; suite-gated milestones; recording demos as proof; never pushing without permission until asked.

## 7. The immediate open work (priority order, per the owner)

1. **Deep onboarding scrape** — per allowed service, actually navigate/scroll/click and extract content (inbox senders+subjects, calendar events, contacts, LinkedIn profile) using the existing browser-agent observe/act loop, consent-gated, redacted, written into memory drawers.
2. **A real proactive demo** — feed a messy day (transcript/audio) with zero direct commands; the proactive tick + open-loop ledger must surface engine-initiated cards on the board.
3. **UI redesign** — consumer-grade visual pass over all screens; kill the developer bloat.
4. **Run on the owner's actual machine** — either SSH access (owner must provide) or a packaged local install (engine + extension + app).
5. Calls, mic listening, Phase 10 verification.
