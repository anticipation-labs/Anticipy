# ANTICIPY V6 - canonical contract

This is the controlling document for the V6 loop. Every dispatcher prompt must
read this file from disk at the start of every cycle. If any inherited V4 or V5
contract conflicts with this file, this file wins.

## PART 0 - THE PRINCIPLE

Anticipy is software that, running on a stranger's Mac, acts as a second
version of that stranger: executing whatever a competent person would do in
response to their environment, ambiently, using only the stranger's existing
tools and accounts, with no setup beyond installing the app and signing into
whatever services they want the assistant to help with the way they normally
would.

The load-bearing words are:

- Stranger. The user is a real person on a real Mac, not Omar, not a developer,
  not a fixed test account, and not a fixture.
- Second version. Anticipy executes. It is not a suggester.
- Ambiently. The user should not have to frame a prompt, click a special button,
  or speak a wake word for every useful action.

The load-bearing absences are:

- No test credential backdoors. The verifier reads what the user reads on the
  same surface. No IMAP, Google Calendar API, Slack API, Notion API, service
  role keys, or app passwords for verification.
- No closed verb list. Real people use Gmail, Calendar, Slack, Canva, Figma,
  Notion, Salesforce, Amazon, native Mac apps, terminals, PDFs, and surfaces not
  named here. The engine must handle what appears or decline competently.
- No setup beyond install and normal sign-in. The user installs the app and
  signs into services in Chrome or native apps the way they normally would.

Runtime economics are part of the product:

- The hard ceiling is $200 per year per heavy user at 100,000 complex tasks.
- The runtime ceiling is $0.002 of LLM spend per complex task.
- Build-time verifier, judge, planner, and worker calls are exempt from this
  runtime ceiling. The shipped engine is not exempt.

## PART 1 - DERIVATIONS

### D1. Verifier surface equals user surface

DOM web apps are verified through the user's real Chrome on remote debugging
port 9222. Canvas and rasterized surfaces are verified by screenshot plus a
vision-model question when deterministic reads are not available. Native Mac
apps are verified through the accessibility tree. Terminal output is verified
through the terminal text buffer. Bot-protected sites are approached through the
user's normal signed-in Chrome and trusted browser state. If a surface blocks
automation, the engine must decline competently and leave no broken state.

### D2. Engine surface equals user surface

The engine drives the user's real Chrome on port 9222, the user's native apps,
and the user's visible surfaces. It must not run a cloned Chrome profile, a
hidden Chrome, or a parallel native app. If Chrome is not running with port 9222,
Anticipy launches or relaunches it with session preservation. Tabs opened by
Anticipy are visually marked with a cream border, color `#F5F0EB`.

### D3. Open verb set with hard breadth

There is no fixed verifier fixture library that defines allowed verbs. The
stranger generator produces real work moments. Across evaluation, at least five
hard categories must be exercised:

1. Canvas-based design tools.
2. CRM and enterprise SaaS.
3. E-commerce with bot protection.
4. Native Mac apps.
5. Ambient-only intents with no explicit utterance.

The engine uses its action engine, dossier, reference resolution, DOM path,
AX path, keyboard shortcuts, screenshot and vision fallback, and competent
decline path to handle new surfaces.

### D4. Judge standard

The judge asks one question: would a competent person, given the stranger's
context, have done what Anticipy did, the way Anticipy did it? If the answer is
ambiguous, the interaction fails. Ambiguous-fails-not-passes is the bias.

### D5. Generated strangers, not fixtures

Each cycle generates a fresh persona and script with high variety. Personas and
scripts are written under `state/strangers/<uuid>/`. Personas are not reused.
Across every rolling 20 strangers, at least five must be from the hard
categories in D3. Persona and script similarity is audited by embeddings.

### D6. Held-out MP3 anchor

`~/Downloads/2026-05-21_08_11_04.mp3` is Omar's held-out full-day audio. It is
never trained on. Every ten generated-stranger cycles, or every six hours,
whichever comes first, the engine processes it and an evaluator judges the
result under PART 0.

### D7. Done is statistical and mechanical

The orchestrator writes `state/COMPLETE.md` only when all of these hold at the
same time:

1. At least 100 successful generated-stranger interactions.
2. At least 20 verb categories hit.
3. At least five hard categories hit: canvas, CRM, e-commerce, native, ambient.
4. No failed interaction in the most recent 20 interactions.
5. Three consecutive MP3 evaluations pass.
6. Local main, origin/main, and live `/api/app/state` report the same commit.
7. The public DMG SHA matches `state/builds/manifest.json`.
8. Last-20 cost projection is under $200 per user per year.
9. Last-20 audio transcript WER is under 5 percent.

No model or role may short-circuit this done check.

### D8. Production is the product

A correct local engine is not the product. The product is what is served at
`https://www.anticipy.ai/app` and what installs from the public DMG URL. Every
accepted bundled-code change must ship through `scripts/ship.sh`.

### D9. The setup the stranger does, the verifier does

The verifier uses the same setup as a real user: sign into Chrome on port 9222,
grant Accessibility when native apps need it, and grant Screen Recording when
canvas or screenshot verification needs it. If a service is not signed in, the
loop writes a specific decision-queue item and continues with a default skip for
that service.

### D10. Runtime cost ceiling

Runtime code must stay under $0.002 per complex task. Banned in runtime code:
GPT-4o, GPT-5 and GPT-5.x, Claude Opus, Claude Sonnet, Gemini Pro, and any
model priced above $1 per million output tokens. Allowed runtime model families
include DeepSeek flash, Kimi instruct or vision, Gemini Flash, small embeddings,
and local Mac models. Build-time judge, planner, worker, evaluator, stranger
generator, and verifier calls may use expensive models.

### D11. Competent decline

When the engine cannot reliably handle a surface, reference, CAPTCHA, permission
state, or canvas action, it must not fail visibly. It either stays silent and
logs a declined action or surfaces a small opt-in card. It must not leave
half-filled forms, wrong drafts, wrong posts, or tab storms.

### D12. Transcript fidelity

Natural speech transcript WER target is under 5 percent, including names and
jargon. Live mic, MP3 upload, and transcript paste all feed the same post-ASR
pipeline. Transcript paste has perfect input fidelity by definition.

### D13. The principle wins

If any rule in this document conflicts with PART 0, PART 0 wins.

### D14. Bounded everything

Every operation has a limit. Engine retries per intent are capped at 3. Reference
resolution depth is capped at 5. Page waits are capped at 30 seconds. Total
action wall time is capped at 90 seconds. Worker loops, cycle loops, ship loops,
Codex subprocesses, decision queues, and recurring failures all have explicit
fallthroughs to competent decline, next cycle, decision queue, `STUCK.md`, or
`SETUP_BROKEN.md`.

### D15. Research before asking

For any non-obvious error, capture the exact error, search the web for the exact
error, search the symptom in plain English, search the tool plus 2026, then try
a fix. After three researched angles fail, write the decision queue.

### D16. Trace receipts

No claim counts without a surface-readable proof. Email drafts are proved from
Gmail UI. Calendar events are proved from Calendar UI. Canva edits are proved
from screenshots plus vision or deterministic canvas-adjacent reads. Slack
messages are proved from Slack UI. Competent decline is proved by a decline log
plus absence of broken visible state.

### D17. State hygiene

Before every stranger, close prior Anticipy tabs, clear working state, snapshot
baseline surface state, and kill orphan engine subprocesses. After the stranger,
diff the visible surfaces against baseline. Only the diff counts.

### D18. Persona diversity

Each persona and script is embedded and compared with the last 20. Similarity
above 0.8 causes regeneration with a different occupation, age, geography, and
primary surface category.

## PART 2 - ARCHITECTURE

The loop is Planner, Worker, Judge, Stranger Generator, Stranger Driver,
Multi-Modal Trace Reader, Evaluator, Cost Auditor, Transcript Quality Auditor,
Breadth Auditor, and Done Checker.

Planner reads this file and state, then writes `state/cycle-N/tasks.json`.
Worker runs exactly one task in `.worktrees/cycle-N-task-K/`, edits only scope,
runs success test, commits, and exits. Judge reads diff plus success-test output
and returns merge, reject, or escalate. Stranger Generator writes one persona
and script. Stranger Driver uses computer use to enact the script. Trace Reader
reads CDP, AX, screenshots, terminal text, tabs, menu-bar state, and engine logs.
Evaluator decides whether the interaction passed under PART 0. Auditors enforce
cost, transcript fidelity, breadth, and deploy parity.

Every dispatcher prompt starts with: read `ANTICIPY_V6.md` from disk and restate
PART 0 in your own words.

The orchestrator is `scripts/orchestrate_v6.sh`. It exits only on
`state/COMPLETE.md`, `state/STUCK.md`, or `state/SETUP_BROKEN.md`.

## PART 3 - STRANGER GATE

Each stranger has a UUID, demographics, occupation, location, primary surfaces,
hard-category focus, accounts, life context, verbal style, and communication
preferences. Each script is a sequence of moments: speaks aloud, pastes a
transcript, uploads audio, uses a surface, or stays silent while context changes.

For each moment the trace reader collects DOM reads, screenshots and vision
answers, AX trees, terminal text, open tabs, Anticipy UI state, and engine logs.
The evaluator scores whether Anticipy acted, whether the action was correct,
whether the risk UX was correct, and whether a competent person would have done
it.

Only full pass counts toward the D7 successful-interaction total. Partial and
fail reset the most-recent-20 streak.

## PART 4 - ONE-TIME SETUP

Omar may sign into services once in the Chrome launched on port 9222 and grant
Accessibility and Screen Recording once. If a service is missing, the loop
writes a decision-queue item with a default skip and continues.

## PART 5 - RUNTIME RULES

R1. No LLM declares done alone.
R2. No smoke tests.
R3. Verifier surface equals user surface.
R4. Ship every accepted bundled-code change.
R5. Engine logs are not proof.
R6. Frozen paths require verifier-first changes.
R7. Brand discipline: DM Serif Display, IBM Plex Sans, IBM Plex Mono,
`#0C0C0C`, `#F5F0EB`, `#6B635B`, no forbidden launch copy.
R8. Decision queue is for human-only decisions and has a default.
R9. Stop only on COMPLETE, STUCK, or SETUP_BROKEN.
R10. Runtime cost ceiling is enforced.
R11. Competent decline, never visible failure.
R12. Transcript quality is product quality.
R13. Bounded everything.
R14. Research before asking.
R15. Trace receipts mandatory.
R16. State hygiene per stranger.
R17. Diversity audit per persona.
R18. Re-read this document at every cycle boundary.
R19. PART 0 wins.

## PART 6 - TRAPS AND ESCAPES

The orchestrator implements escape paths for repeated judge rejection, build
environment failure, disk pressure, Chrome port failure, R2 or Vercel failure,
Codex rate limits, bad vision answers, stranger-driver failures, tests that do
not prove product behavior, engine loops, decision-queue overflow, context
compaction, build-cost runaway, test pollution, persona diversity collapse,
date sensitivity, corrupted build caches, false "looks done" signals,
frozen-path drift, loss of focus, first-launch onboarding, ambient-only intents,
missing service sign-ins, vision false positives, and concurrent worker
conflicts.

The meta-pattern for any unlisted trap is: research, try a fix, try a different
angle, after three angles write a decision-queue item with the default skip or
fallback, and continue unless the stop condition requires STUCK or SETUP_BROKEN.

## PART 7 - WHAT CODEX DOES NOW

1. Verify PART 0 in three sentences.
2. Audit git log, live `/api/app/state`, state directories, and old fixtures.
3. Delete closed fixture libraries and verifier API backdoors. Remove or replace
   tests that do not touch real surfaces. Remove banned runtime model paths.
4. Commit those deletions as:
   `v6: remove fixture library, API-credential tests, and banned-model runtime calls per principle in ANTICIPY_V6.md`
5. Write the V6 orchestrator and helpers:
   `scripts/orchestrate_v6.sh`, dispatchers under `scripts/v6/`,
   `verifier/v6/trace_reader.py`, cost audit, transcript audit, breadth audit,
   done check, and ship guard.
6. Commit and ship the V6 framework.
7. Start `bash scripts/orchestrate_v6.sh`.
8. Continue until D7 holds or a specific Omar-only blocker is written.
