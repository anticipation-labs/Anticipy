# Anticipy: make it earn trust

Engineer field brief | September 7, 2026 | 500 proposed acceptance scenarios

## Your assignment

Install Anticipy on your own iPhone. Use it for real, ordinary work tonight. Talk naturally, answer in Messages, switch apps, get interrupted, return later and expect the original task to still make sense. Follow every failed outcome from the screen back through the harness. Fix the cause, repeat the original case, then try different people, wording, tools and circumstances.

The product promise is simple: I can say what is happening in my life, let Anticipy carry the context, and get a useful, verified outcome without supervising a second job. The founder's desired "OpenClaw moment" means unmistakable usefulness: a person feels the burden leave their head and chooses to keep using the product. Treat the references to unlimited cost or giving up privacy as emphasis on value, not product requirements. Trust, permission and understandable cost are part of the experience.

"Perfect" is an ambition. The release decision must be based on observed behavior: no known critical failures in the promised experience, no hidden unsupported capability, no invented completion, and a clear recovery path. Do not promise that one night proves every future situation or twenty actual days of use.

## The current starting point

Repository: https://github.com/anticipation-labs/Anticipy . Use cloudflare-backend; main is an unrelated lineage without the iOS app. Remote HEAD was read as 9039b83a for this brief. Production source was independently verified at cb2010957877eec0a8c67138b57060dc1bef3110. These are different because the later commit records evidence rather than changing runtime code.

Build 170 is VALID and available to the owner's Internal TestFlight group, confirmed independently at 01:29:13 UTC on September 8 (6:29 PM September 7 Vancouver). That does not establish access for a new engineer: obtain a tester invitation for his own Apple ID and confirm it on his phone. No engineer identity or invitation has been created by this brief.

Extension 0.18.0 is published. The last observed owner's installed version was 0.15.0, an earlier observation, not a new device inspection. The engineer must install the current extension in his own Chrome profile, pair his own test account and verify its fresh heartbeat. Updating TestFlight does not update Chrome.

The previous lab used 15 fictional people, separate SQLite memories, 5,072 transcript words and 25 typed follow-ups. It included seven isolated Chrome cases, five connection-dispatch cases and 24 API fault checks. It was not a complete real-account OAuth, real texting or twenty-day phone trial. Five repairs and the later reply-priority/context repair are deployed. Latest follow-up checks: 3,033 Python passes, two skips, 83 browser suites passed, eight live workers on matching source with current memory snapshots. These counts do not prove the whole product.

The 500 scenarios accompanying this brief are NEW and NOT RUN. Expected outcomes are acceptance contracts, not historical results or claims that every capability already exists.

## How the harness works

The harness is the system around the model that gives it context, chooses tools, remembers progress and checks whether work really happened. The model is one part of that system.

1. Receive a spoken transcript, app input or SendBlue message; preserve account, event identity, speaker and time.
2. Retrieve the relevant conversation, earlier quoted speech, current task, permissions and owner memory.
3. Ask the model what the person means and what useful work is justified. Silence, clarification and action are all valid outcomes.
4. Keep one durable task with its current revision, dependencies and exact approval scope.
5. Choose an actually available hand: server research/composition, connected API, paired Chrome or the narrow native iPhone calendar hand.
6. Get a needed detail, account connection or permission; resume the same task when it arrives.
7. Execute, read back the result, verify the requested outcome and save a receipt.
8. Show coherent state in the app and text conversation; update memory and close completed commitments.

Cloudflare's API Worker owns the route/data boundary and D1-backed records. The Python brain runs per owner in Cloudflare Containers, coordinated by Worker/Durable Object infrastructure. Owner memory is SQLite inside the container, restored and snapshotted through R2. PocketBase-shaped collection URLs and old comments remain; they do not establish that a PocketBase server is the production database. Verify runtime state, not historical names.

Example: earlier speech names two lamp URLs. Later the owner texts "compare those two; don't buy anything." The classifier and brain must see the URLs, the queued task must retain them as quoted evidence, the selected hand must read them, and the result must contain both observed prices. The no-purchase boundary survives every hop. "Opened the websites" is not completion.

## The text-first contract

A person should be able to continue an existing task in Messages without opening a task dashboard to decipher it. Text-first is a conversation and task-continuity contract, not a claim that every update always becomes a text.

SendBlue is the current messaging provider. Outbound submission uses its API; inbound messages and delivery callbacks enter /sms/sendblue. App answers and texts converge on the brain's conversation handling, with transport identity preserved. A text saying "yes" has no universal meaning: the model must interpret it against the actual question, task revision, previous conversation and authority.

A question must say what is needed, refer to the actual task and accept a natural answer. A missing account must produce a relevant connection flow; after OAuth, resume the original task with its details intact. A vague "account or device action required" is a defect when the system knows the specific action. If the action is unknown, admit that rather than fabricating a precise instruction.

The app must distinguish queued, provider-accepted, delivered, failed and unconfirmed states according to available evidence. Quiet hours and outreach limits need a visible reason and next step. Never claim delivery from API acceptance alone. Direct answers now run before and between speech records, but an in-flight model call or another serial operation may still delay them; measure real phone latency.

## What good feels like

The owner recognizes the situation without rereading the full transcript. A short headline states the useful outcome; one clear question asks for the missing choice. Detail, quotes and sources remain available without dominating the screen. This applies the usability principles of visible status, familiar language and recognition instead of forced recall [U1].

The owner can correct, cancel and return later. Make capability limits understandable before they turn into a confusing failure. When wrong, preserve context and offer a concrete repair. Human-AI interaction guidance treats first use, regular use, failure and change over time as distinct design situations [U2].

Touch feedback must be immediate and truthful. Use concise status, accessible visuals and appropriate haptics or sound; a routine update should not become an unnecessary interruption. These are design requirements for this product, informed by Apple's feedback guidance [U3]. Do not play a success cue before the underlying action is verified.

Measure relief: how many times did the owner repeat a fact, reopen a source, ask for status, recover lost text or verify something the app should have verified? Count unnecessary questions and misleading notifications separately from model latency. A fast answer that creates more work is a failure.

## First hour: use the actual product

Before coding, record branch, commit, installed iPhone build, iOS version, Chrome version, extension heartbeat, account identity, timezone and enabled notification settings. Use a fresh test owner and controlled connected accounts. Do not reset the founder or other users to obtain a clean test.

Complete these journeys from the phone: signup; speak a harmless task; answer its missing detail by text; prepare a private draft; connect a supported calendar or workspace through the conversational flow; retrieve an actual known record; pair Chrome; obtain a two-page comparison; cancel an unfinished task; restart and recover the context. Verify one native-calendar write in a disposable calendar. Record an unavailable capability as a gap, not a pass.

Then live with it: use it during a real work interruption, plan one ordinary errand, retrieve something you genuinely forgot, and ask at the end what still needs your decision. Use only your own or consenting participants' accounts. Send test messages to controlled recipients. Browser writes, bookings and payments use sandboxes unless the exact real action has been deliberately authorized.

Start with the first two cases in each catalogue category: 50 smoke cases. These are only a minimum exploration set, not the full release requirement. Read the scenario before injecting its prerequisite; no hidden manual task creation or direct database fix may stand in for the app journey.

## Diagnose causes, not sentences

For each failure, inspect capture first, then missing context, then the prompt/examples, then model capability, and only then structure. A phrase matcher that knows this example is not a fix. No regex, word list, word count or threshold may decide what a person's words mean. Structural authorization, identity, transport and test assertions remain legitimate; performance targets below are not semantic rules.

Preserve exact quotes, speaker/source/time, competing identities, corrections, and the difference between someone else's promise and the owner's instruction. Do not turn fiction into contacts or completed events into open promises. Keep quoted context separate from permission. Store useful sources without recursively embedding whole task histories.

Memory tests need owner isolation, current-versus-historical facts, provenance, expiry, correction, forgetting, crash recovery and return-after-interruption. Test ten projects and fifty live tasks before claiming large-scale coherence. Use 1,000 and 10,000 historical-event fixtures to measure retrieval and growth. Do not interpret the founder's "150 million things" as an already-supported capacity target.

Proactive discovery must have actual callers and actual observations. An unused collector is code that never supplies production evidence. Trace the caller, permissions, event emission and consumer for every claimed signal. Either connect and verify it, explicitly defer it, or remove the claim. Never treat a registered module or a catalog entry as an operating feature.

## Real tool completion

For API work, prove: natural request -> relevant connection question -> provider authorization -> correct account -> actual record read -> original task resumed -> useful result verified. Exercise revoked credentials, empty results, pagination, scope errors, malformed payloads and uncertain writes. The API returning 200 does not mean the user's task is done.

For browser work, prove: phone/text request -> persisted job -> intended paired extension claims it -> fresh page observations -> actual clicks or reads -> task-level evidence -> result returns. Use login handoffs, stale layouts, blocked controls, new tabs, interrupted sessions and owner tab changes. A direct agent-loop fixture is useful diagnostic evidence, but not a pass for the installed extension's whole queue.

For native calendar work, inspect the actual EventKit record and identifier in Apple's Calendar app. Test permission changes, task revision and crash-after-save reconciliation. A completed card without a matching event is a failure.

For mixed work, preserve one parent outcome with independently tracked dependencies. API success must not hide browser failure; cancellation must identify effects already completed. When an external result is uncertain, reconcile before retrying an action that could duplicate or spend something.

## Tonight's work order

00:00-00:30: establish versions, clean test identity, baseline tests and a shared issue ledger. Confirm TestFlight access before counting phone work as started.

00:30-01:30: complete the phone/text/connection/browser journeys. Reproduce the visible failures before choosing repairs. Fix anything that loses input, acts under the wrong owner, invents completion or repeats an external effect first.

01:30-04:30: repair the highest-impact causes. For each: retain the failing trace, add a regression, repeat the original case through its real surface, then try an unseen paraphrase and a different owner/source. Keep useful independent work moving when one provider is blocked.

04:30-06:30: work through the broader catalogue with real-device checks plus controlled replay/fault injection. Run mixed-task, interruption, memory and recovery cases. Track each surface separately; a backend replay cannot replace a phone or carrier result.

06:30-08:00: run regression suites, review the final diff adversarially, ship through CI, check the actual production bytes and independently check Apple. Reinstall or update the shipped build and repeat the critical journeys. Leave a concise morning report with evidence and gaps.

This is a proposed eight-hour allocation, not a promise that all 500 real-world journeys fit into one night. Record NOT RUN or BLOCKED honestly. If the release criteria are unmet, finish the repair work that can be completed safely and report the exact remaining dependency. Do not label the product investor-ready to satisfy the clock.

## Acceptance and release decision

All 500 cases have individual status, observations and evidence. PASS means the stated outcome occurred on the required surface. FAIL means it did not. BLOCKED means a named dependency prevented execution. NOT RUN means no evidence. A capability that is missing from the promised journey is a gap, even if its error message is polite. The catalogue itself is not an automated test runner.

Release blockers: lost submitted input; wrong-owner access; unapproved external action; duplicate effects; invented completion; unrecoverable task or memory loss; broken signup; unusable primary controls; no coherent path through the promised text/API/browser experience. Zero observed release blockers are permitted in the release-critical journeys. Publish both numerator and denominator for tested outcomes; do not bury skipped cases.

Proposed product targets to measure, not claims already achieved: visible tap acknowledgement within 200 ms; retained input or explicit submission state within 2 s; typing remains responsive during refresh; ordinary direct replies reach an answer or accurate progress update within 10 s at p95 under the stated load; stalled work shows a useful status by 30 s. Report carrier acceptance and delivery time separately. If the target is infeasible, measure the cause and agree a revised promise rather than faking a fast completion.

Repeat each corrected failure at least three times, including a restart or injected fault when relevant, and try a new wording/source before acceptance. Keep a reserved subset of 100 cases (the last four in each category) out of prompt-tuning examples until first evaluation. Once a failure informs a repair, it becomes regression evidence; write new held-out variants. The human reviewer judges meaning and usefulness. Exact-text matches are not a semantic quality score.

Record actual model calls, retries, provider failures, p50/p95 latency, notification count, owner interventions, and task outcome. Do not inherit the prior agent's remaining US$50 allowance as a new engineer's budget; obtain and record the engineer's authorized test spend before paid bulk replay.

## Work safely in this repository

Read HARNESS-LAWS.md, CLAUDE.md and AGENTS.md first. Work from cloudflare-backend. Prefer an isolated worktree based on that branch for concurrent repairs; record its base commit and integrate deliberately. Fetch and compare before merging. Do not reset or clean a shared checkout to make it look tidy.

Before product edits: sh app/ios/Tests/run_all.sh. Run relevant Python, Worker and browser suites for changed components. Use the repository's Node 24 requirement for Worker tests. Stage and commit named files only. Never git add -A, git add ., git commit -a or git checkout -- on someone else's work.

For iOS source changes, update app/ios/project.yml and app/ios/Anticipy.xcodeproj/project.pbxproj together, including consistent product build values. No xcodegen assumption. Local simulator builds are allowed; signed iOS releases come only from CI. A normal push does not upload: dispatch ios-testflight.yml intentionally, or use the literal [ship] marker in the intended release commit subject. Avoid duplicate uploads and Apple throttling.

After deployment, compare the active API revision, brain source hash/process health/current R2 snapshots, and public extension ZIP bytes with the intended commit. A green workflow alone is insufficient. After iOS upload, run gh workflow run asc-query.yml --ref cloudflare-backend -f build=<N> with invitation fields blank to read Apple state. Verify VALID, the correct tester group and tester access, then update the engineer's actual phone.

The earlier scheduled follow-ups and temporary lab services are paused/stopped. Do not restart broad automations to substitute for an explicit finish. This assignment is for the engineer; this brief has not sent invitations, changed app source or run the new 500-case catalogue.

## What you hand back in the morning

1. A short video from a clean phone showing signup, natural speech, a text reply, a contextual API connection, a real record retrieval, a Chrome task, a correction, a cancellation and a verified result. Keep secrets and unrelated personal content out of recordings.
2. The completed 500-row result ledger. Every claimed pass links to evidence; blocked and unrun cases remain visible. Separate actual-life, phone, text/carrier, provider, browser and simulated results.
3. A before/after issue list: exact input, expected outcome, observed failure, root cause, changed files/commit, regression, new variant, and live retest.
4. A release receipt: commit, actual live backend revision, memory/source checks, extension version/hash, Apple build/group, installed phone build and known limitations.
5. A plain verdict: what reliably saves effort, what still requires supervision, what prevents an investor demonstration, and the exact next owner or action for each blocker.

Do not ask the founder to discover problems you could reproduce yourself. Do not conceal unfinished work behind an enormous test count. The standard is that an ordinary person can get useful work done and understand the state without needing the engineer beside them.

## Repository evidence and starting files

[R1] HARNESS-LAWS.md and CLAUDE.md: reasoning, review and live-proof requirements.
[R2] docs/CURRENT-APP-STATUS.md: dated release baseline and unresolved boundaries.
[R3] research/overnight-2026-09-07/persona-lab-status.md: previous fifteen-person observations and exact limitations.
[R4] research/overnight-2026-09-07/reply-priority-repair.md and reply-priority-release.json: latest repair and independent release receipts.
[R5] brain/worker.py, brain/conversation.py, brain/anticipy_core.py: input scheduling, conversation interpretation and task creation.
[R6] brain/source_context.py, brain/memory.py, brain/workflow.py: quoted evidence, memory and revision/approval state.
[R7] brain/hands.py, brain/server_work.py and migration/workers/src/routes/hands_api.ts: routing, execution evidence and verified API-read synthesis.
[R8] migration/workers/src/messaging.ts, routes/sendblue.ts and connections/dispatch.ts: real provider and connection paths.
[R9] extension/background.js, extension/agent_loop.js and extension/source_context.js: paired browser execution and context handoff.
[R10] app/ios/Anticipy/Backend/NativeCalendarHand.swift and Views/ContentView.swift: device execution and actual app entry surfaces.
[R11] proof/audit/persona_lab/README.md: existing synthetic harness boundaries and reproduction.
[R12] migration/workers/brain/src/index.ts and brain/container_entry.py: per-owner runtime and memory snapshots.

Use commit-pinned repository links in the PDF. Treat old documents as dated evidence, not current truth when they conflict with runtime checks.

## Design references

[U1] Nielsen Norman Group, 10 Usability Heuristics for User Interface Design: https://www.nngroup.com/articles/ten-usability-heuristics/
[U2] Microsoft Research, Guidelines for Human-AI Interaction: https://www.microsoft.com/en-us/research/project/guidelines-for-human-ai-interaction/
[U3] Apple, Human Interface Guidelines: Feedback: https://developer.apple.com/design/human-interface-guidelines/feedback

These sources inform design principles. The scenario expectations, performance targets and overnight schedule are proposed Anticipy acceptance criteria, not measured claims from these publications.
