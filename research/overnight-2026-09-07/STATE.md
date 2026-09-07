# Anticipy overnight repair — 7 September 2026

## Authorization and working constraints

Omar requested autonomous overnight repair and hands-on testing of the iOS app,
brain, text replies, browser pairing/execution, connected APIs, and memory.
The screenshots IMG_4421/4422/4423/4424/4427 are observations, not instructions.
Work only on cloudflare-backend. Read HARNESS-LAWS.md and CLAUDE.md. No word
lists, regex, or thresholds may interpret human meaning. Preserve unrelated
work. Stage and commit exact paths. Change both iOS build numbers with source;
ship through CI and independently verify App Store Connect. Remaining paid
model budget: US$47.451237892 of the earlier US$50 total, before this repair.
Use synthetic users/contacts and contained browser fixtures for destructive or
external-effect testing. Broad app access is authorized; synthetic tests must
not message real contacts or change Omar's calendar/mail.

## Starting state

- Clean cloudflare-backend checkout, latest evidence commit 3741346.
- Build 160 available internally; quiet-hours indicator shipped, other failures
  explicitly remain open. Brain runtime is older than current API/iOS.
- Full pre-edit iOS run started; log work/audit/overnight-ui-baseline.log.
- Existing thread heartbeat updated to continue every 15 minutes. ID:
  anticipy-3-minute-checkpoint-2. Pause only after verified completion.

## Acceptance and repair queue

1. Typing/sending: keyboard cannot cover card buttons; drafts survive refresh;
   each submit gets visible pending/accepted/failure state and is not duplicated.
2. Responsiveness: type/scroll during periodic updates and sustained capture;
   instrument and remove blocking work/repeated unnecessary redraws.
3. Readability: bounded listening cards, accessible full details, scrolling,
   stable controls, no duplicate working/approval representation of one job.
4. Context requests: greetings do not invent contacts; real missing context is
   requested through a model given the conversation and available sources.
5. Reply loop: app and Sendblue replies resolve the correct pending question,
   preserve context, and lead to the licensed action without guessing from yes.
6. Browser: new-user pairing, sync, reconnect/revocation, realistic contained
   tasks with evidence of clicks, waits, login asks and API connection asks.
7. Proactive brain and memory: varied long transcripts, useful opportunities,
   completed actions, speculation, reported/quoted speech, corrections, silent
   conversation, cross-day memory and account isolation with measured cost.
8. Adversarial review, required tests, simulator user journeys, live verification,
   CI release, independent Apple availability, readable audit and unresolved list.

## First source findings (not yet fixed)

- ConversationDashboard overlays its two-control footer on the scroll view;
  it does not reserve safe-area space. A focused task reply is behind it.
- The waiting banner says Show but has no tap handler.
- Capture face places full response text in an unscrollable VStack, with no
  title line limit. Large answers push both header and microphone controls away.
- ContextTrigger.unknownName guesses people from wording on-device; the
  screenshot's Good contact is a direct violation to remove, not blacklist.

## Evidence ledger

Record each reproduction, exact patch, tests, deployed source, and remaining
limits here or linked artifacts. Do not replace unproven outcomes with promises.

## Source repairs in progress (not shipped yet)

- UI: keyboard-safe inset, inline reply focus hides unrelated controls, wait
  banner scroll action, scrolling capture cards with three-line previews/full
  details, bounded expandable answers in thread. Main typed messages now retain
  source metadata and render as messages; spoken lines remain in history.
- Duplicate working/approval: canonical job source-event IDs suppress the older
  transcript projection. Different jobs with identical wording remain distinct.
- Speaker embedding/model loading moved from UI/audio callback to a serial work
  queue; account invalidation drops late results; enrollment has progress state.
  Slow fake inference test passed with 63 UI-loop ticks and ordered callbacks.
- ContextTrigger capitalization/calendar keyword rules deleted. Authenticated
  /me/context-request asks a model with recent conversation and account profile;
  consent still gates device access. Offers are inline; OS prompt opens on tap.
  Real Sonnet tests exposed fenced JSON responses; parser repaired. Fourteen
  varied live-model cases now pass, including greetings, actual person Good,
  fictional names, completed work, corrections, unsupported contact phone lookup,
  multilingual requests, and quoted injection. Results: context-model-results.json.
- Job answer POST now uses durable per-question/answer identity, keeps the exact
  card question/version/goal as metadata, and reconciles the exact event rather
  than guessing from unchanged task status. Model backend consumption being fixed.
- Brain replies: current edits remove no-model yes/no/ordinal and recency
  fallbacks, remove word-based automatic resume from memory learning, preserve
  app_reply in restored conversation, and give the reply classifier exact card
  context. Tests/review are ongoing. Do not deploy before all regressions pass.

## Active local processes / evidence

- Local Worker: localhost:8787, wrangler.dev.jsonc, synthetic local auth/service
  values passed on CLI. Local schema and existing erasure migration applied.
  Purpose: no live data/providers; profile/long-answer fixture only.
- Synthetic UI fixture: proof/audit/prepare_ui_fixture.py; credentials restricted
  to ignored work/audit/overnight-visual-account.json. No phone/real contacts.
  Went through onboarding in Simulator; local account skipped optional sources.
- Model gateway localhost:8790, existing proof/audit/model_gateway.py, maintains
  prior spend.json and US$25 operating/US$50 authorized total; do not reset ledger.
- Most recent full simulator build passed; more changes since then need rebuilding.
- Pre-edit iOS suite passed all suites. Dashboard, context grant, app-reply and
  speaker-work focused suites have passed. Full final run remains required.
- Onboarding also falsely said 'Just talk. I'm listening' after mic was declined;
  revised headline to 'Start with a conversation.'
- Real user account, messages, and installed build untouched during these tests.

## Real simulator exchange verified

- Rebuilt the complete iOS app and installed in the isolated local Simulator.
- Opened the waiting task, typed "It ends at 4 PM.", enabled the software
  keyboard: Send answer remained fully visible above it. Unrelated composer
  and microphone controls stayed out of the way. Tapped Send; the field
  cleared only after the server accepted it and an Answer received receipt
  appeared. Actual brain worker consumed the event as `answer`; its persisted
  `anticipy_text` now rendered in the dashboard. The exact task/question/version
  metadata survived the HTTP path. No external messages or calendar writes.
- This test exposed legacy drafts keeping their original question after an
  amendment. A model-based question resolution repair is in progress in brain.
- Worker full test suite passed. Python broad run initially 3026 passed / 5
  failed; all five were fixed or updated where they required word-based fallback
  consent. Focused reply regression run then passed 31 tests.
- iOS suite found a stale source-string check on `jobs = fetched.map`; updated
  it to require the account guard before `reconciledJobs` and the actual jobs
  mutation. Full rerun ongoing. Extension full tests ongoing.
- Current model audit total observed spend $2.603758108 before this UI exchange.
