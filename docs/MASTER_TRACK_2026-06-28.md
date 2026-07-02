# Anticipy — Master Track & Documentation (2026-06-28)

One place that answers: where the work lives, what the owner asked for (verbatim track), what was built, what the plans are, and the honest open-issues list.

## 1. Where the work is
- **Repo:** `github.com/omize10/Anticipy-executor-working`, branch `devin/full-frontend-ui`, working copy on the Devin VM at `/home/ubuntu/Anticipy`.
- **Pieces (one repo):**
  - `engine/` — FastAPI engine on `localhost:8787` (memory ContextPack spine, proactive gateway, browser agent loop, onboarding scan endpoints). Run: `engine/.venv/bin/python -m uvicorn --app-dir engine anticipy_engine.main:app --port 8787`.
  - `app/` — Next.js app on `localhost:3000` (welcome/sign/setup/onboarding/great/done/board/go-to/memory/settings/mp3, all under `app/phase-zero/PhaseZeroApp.js` + per-route pages, API proxies under `app/api/*`).
  - `extension/` — MV3 Chrome extension ("the hands": trusted CDP observe/click/type, onboarding scans, screenshot proof).
- **IMPORTANT:** Everything runs on the **Devin VM's own Chrome**, not the owner's computer. There is **no SSH access to the owner's machine** from this session. Getting Anticipy onto the owner's real Chrome/machine is an open item (see issues).

## 2. Owner prompt track (chronological, condensed but faithful)
1. "Best browser agent in the world" push → WebVoyager public benchmark runs (28% → vision-first fixes → 43% stable, $0.19/task; Browser-Use ~50% same box). Verdict recorded honestly: product-done, not #1.
2. "Get a 60 in 30 seconds, then grind toward 90 — from the Chrome extension, go back to the roots" → vision-first SoM grounding, iframe/consent fixes in our own loop.
3. "Is it fine to pack into Anticipy / cross browser agent off baby steps?" → yes: browser = product-done component.
4. "Place proactive + browser in codebase with clear documentation; tell all agents: always test before done, always plan all the way through, make pieces work together" → rules encoded in `CLAUDE.md`/`AGENTS.md`, `docs/agent_os/SYSTEM_SPINE.md`.
5. "Research memory & context engineering deeply, produce a detailed plan with micro-plans, loops, sub-agents" → `docs/agent_os/MEMORY_AND_CONTEXT_PLAN.md`.
6. "Go" → M0–M7 executed: one ContextPack builder feeding decide/act/speak, capture reconciliation, bi-temporal validity, salience gate + tiering, privacy layer, rerank/reflection contradictors, day1→day3 flywheel proof. Report: `docs/agent_os/MEMCTX_M0_M7_TEST_REPORT.md`.
7. "According to plan baby steps where are we / how do we finish" → status read: engine ahead, unified UI behind.
8. "Design all the UI around the system… onboarding with the browser scrape… keep what exists but renovate, make all the buttons work… the proper proper proper MVP" → this session: wired onboarding scrape (consent gates + real Chrome scan), Great screen with real learned memory, board typed intake + approvals, live memory page + ContextPack inspector + gated forget-me. Demo recorded; committed `2cfd9de`.
9. **Latest feedback (2026-06-28), verbatim points:**
   - "That onboarding pass can't just open a website. It needs to actually scroll around, click around, and understand what's going on."
   - "I didn't see anything proactive. You told it 'remind me to handle something' — that has nothing to do with proactive. That's a joke."
   - "You should have access to my computer by SSH."
   - "The UI is not good. Really ugly, bloated, technical developer UI — not a clean, good-looking, well-working UI."
   - "Tell me what codebase you're working in and where; push all changes to GitHub; document everything including every prompt and the whole track; document all plans; make everything clean and put all work in one area — this is just the very surface of all your issues."

## 3. What is actually built and proven (with proof locations)
- **Browser agent:** general vision-first agent in owner Chrome via extension; WebVoyager 30-task sample 43% cold / $0.19; hard-task suite 97.9% warm. Proof: `docs/build/proof/*`, `docs/build/BROWSER_Y0_STEP56_REPORT.md`.
- **Memory + context:** M0–M7 spine, suite-gated (107 green at time of report). Proof: `docs/agent_os/MEMCTX_M0_M7_TEST_REPORT.md`.
- **Proactive gateway:** event → memory → decide (act/ask/silent) → hold-for-approval on money/send-to-person → circuit records with proof. Code: `engine/anticipy_engine/proactive/*`, `core/gateway.py`.
- **MVP UI walkthrough (2026-06-28):** live setup readiness, consent-gated onboarding scan that drives real Chrome tabs and writes discoveries into memory, Great screen with real drawers, typed intake → held cards → approve → working record, memory page with ContextPack inspector and default-deny forget-me. Report: `/home/ubuntu/mvp-test-report.md` (session artifact); commit `2cfd9de`.

## 4. Open issues (owner's list first — this is the priority order)
1. **Onboarding scrape is shallow.** Today: opens each service, detects logged-in state, records app connections. Needed: actually scroll, click, and read content (inbox subjects, calendar events, contacts, LinkedIn profile) to build the real "tools and systems inventory" and seed memory with substance. Plan: extend the extension deep-scan to per-service content readers reusing the browser agent's observe/act loop with consent gates and redaction.
2. **Nothing proactive was demonstrated.** The demo was reactive (typed request → card). Proactive means: Anticipy hears/reads the day, infers unspoken tasks, and surfaces/acts WITHOUT being asked. Plan: run the proactive tick against live memory (open loops + routines) and surface engine-initiated cards on the board ("You said Friday dinner — want me to book?"), with a real proactive demo on a messy transcript, not a direct command.
3. **No SSH to the owner's computer.** All work so far runs on the Devin VM. Options: (a) owner provisions SSH access (needs credentials/keys from owner), (b) owner installs the extension + engine locally with a packaged setup. Blocked on owner input.
4. **UI quality.** Current UI is bloated developer-styled. Needed: real design pass — clean visual language, fewer debug-ish panels (source tags, circuit internals collapsed by default), consumer-grade layout/typography/spacing.
5. Calls (Call 1/2/Final) are `coming_soon`; mic listening untested on the VM (no audio device).

## 5. Plans index (all in-repo)
- `docs/agent_os/` — Memory Dock: CONSTITUTION, DEFINITION_OF_DONE, CURRENT_TRUTH, MEMORY_AND_CONTEXT_PLAN, SYSTEM_SPINE, M0–M7 report.
- `docs/build/` — browser agent design, 5-year plan, phase-1 frontend plan, proof artifacts, competitive research (Browser-Use, Vy/Vercept, vision-first plan).
- `plan-baby-steps/` — the phased UI operating plan (Phases 1–10), screen inventory, traceability.
- `factory/`, `autopilot/`, `logs/` — the forcing system, laws, state ledgers.
- `THE_MISSION.md`, `CLAUDE.md`, `AGENTS.md` — standing mission + agent rules.

## 6. Working rules in force (encoded, non-negotiable)
- Always test before saying done (a check that could fail and didn't, read back).
- Always plan the whole chain before touching code.
- One spine — memory, proactive, hands, voice work together, never plumbed separately.
- Never act on a vent; money is the only hard stop; never fake done.
