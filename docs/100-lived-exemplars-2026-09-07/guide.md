# Anticipy in real life

100 conversations that show what the product is for.

This replaces the earlier timed engineering brief as the guide to the intended customer experience. Read the conversations, use the product yourself, repair what fails and ship the verified result. There is no work schedule or points system here.

## What Anticipy is

Anticipy carries the context and unfinished work people otherwise carry in their heads. A person talks about life; Anticipy notices when useful work is justified, remembers the relevant details, prepares or completes the work with available tools, and keeps the person informed. Sometimes the right contribution is a clear question. Sometimes it is a finished artifact. Sometimes it is silence.

Proactive does not mean interrupting every conversation or asking permission for every harmless preparatory step. When the context and existing permissions justify it, Anticipy should read relevant sources and prepare useful private work. Ask when a missing detail matters, when the task is ambiguous, or when an external effect needs authority. Do not force people to repeat information already supplied.

Text-first means a person can answer naturally in Messages and continue the same task. A spoken plan, an app answer, an OAuth connection and a browser result must not become four disconnected conversations. The app makes the current state understandable; it should not require users to decode a control panel to find out what happened.

## One general system

Receive the conversation with its speaker, owner, source and time. Retrieve the relevant memories and unfinished work. Let a contextual model decide what the person means and what help is appropriate. Maintain one task with its current scope and revision. Choose the available API, paired browser, server tool or supported native phone action. Verify the actual outcome, remember what changed and return a coherent answer.

Memory needs provenance, corrections, owner separation and a distinction between history, current facts, tentative plans and completed work. A browser opening is not a comparison. An API returning data is not yet an answer. A provider accepting a text is not proof that it arrived. A stored draft is not a sent message.

Working across 500 tools is an ambition for the capability system, not 500 named scripts or a claim that all those integrations exist today. Retrieve relevant capabilities, inspect their real schemas and permissions, choose the needed operations, and check their effects. A new provider should fit through the same contextual process. Do not send every schema to the model on every turn or add a phrase rule for each example.

The goal is reliable completion with little supervision. A document cannot establish 100% reliability across arbitrary life situations. When a tool fails or evidence is missing, preserving the task, explaining the actual blocker and recovering without duplicate actions is part of correct behavior.

## How to read the exemplars

Every person, conversation, price, address and result in this book is fictional. These are worked examples of intended behavior, not transcripts of completed tests. A stated result is what Anticipy should say only after the described evidence exists. During testing, seed the prerequisite records and replace example facts with actual observations. Listed tools are capability requirements; an unavailable capability remains unfinished work, not a successful test.

Each example shows what was already known, what people say, a useful response, the work behind it and what memory must retain. The final context change shows why the same words can require a different response. These are teaching examples for human understanding and varied evaluation, not canned replies or runtime routing rules. Preserve the reasoning, not the wording.

Read across the categories. Family, creative work, care, travel and business should use the same context-and-tool system. A person with a new combination of needs should not require a newly programmed persona workflow.

## To the engineer: use it, fix it, ship it

Install the current TestFlight app on your own iPhone and use your own test account. Use it like a customer: speak naturally, get interrupted, answer by text, change your mind, connect the account needed for a real task and let the installed Chrome extension do actual work. Use it in your life, not only through scripts or direct database calls. Start without coaching; if the experience needs an engineer's explanation to make sense, improve it.

Use these conversations as examples of the experience, then try your own situations and different wording. Exercise real API reads and permitted writes, actual browser navigation and supported native calendar actions. Inspect the saved event, sent record, downloaded file or other final result. A polite answer or successful tool call is insufficient if the promised outcome is absent. Keep consequential test actions within your controlled accounts and the exact authority given.

Make the app comfortable while doing those tasks. Typed answers must survive refreshes and failures; Send must register once and remain reachable above the keyboard. Long results should be concise first, with detail available. Listening, waiting, quiet hours, failed delivery and required connections should be understandable. Test these through ordinary use alongside the harness, not as a substitute for it.

When something fails, capture the conversation, task state and actual tool result. Fix the cause: missing capture, missing context, poor examples, inadequate model judgment or a necessary structural correction. Then repeat the failed situation and unfamiliar variations, including interruptions and changed tools. Never make human meaning depend on regex, word lists, sentence length or a special phrase from this book. Deterministic identity, permissions, transport and effect verification are legitimate engineering.

Keep a short record of what failed, what changed and the evidence that it now works. Fix what you can reproduce instead of asking the founder to discover it again. Ship when the promised customer journeys work on the actual deployed version, with serious remaining failures made explicit. Update the phone and repeat those journeys after release. A green workflow alone is not proof.

## Repository and release essentials

Use cloudflare-backend. Read HARNESS-LAWS.md, CLAUDE.md and AGENTS.md before product changes. Isolate concurrent work and stage and commit only your named files. Run sh app/ios/Tests/run_all.sh before changing app source and the relevant component checks afterward.

For iOS source changes, update the build values together in app/ios/project.yml and app/ios/Anticipy.xcodeproj/project.pbxproj. iOS signing and upload happen in CI; no laptop-signed release. Dispatch the intended release or use the literal [ship] marker only for an intended upload. Verify the actual backend and extension revision, independently query App Store Connect for the intended build, and confirm the installed phone version.

The earlier 500-case catalogue remains a separate engineering reference. It does not replace using the product or the conversations in this guide. This new guide changes documentation only; it does not claim any new app repair or live verification.
