# Anticipy overnight repair — 7 September 2026

## Latest checkpoint — 2026-09-07 12:43 UTC

- iOS163 commit970f31d shipped through CI34120389837. Independent ASC34121890032
  confirms VALID, internal IN_BETA_TESTING, account ok***@icloud.com in Internal.
  Uploaded05:24Vancouver. External review remains separate; do not claim Sanket
  can install163. Simulator pairing/retry/disconnect verified, personal unpacked
  extension still0.15 because extension-settings automation was blocked.
- Local Wrangler original session46940 exited unexpectedly. Restarted same D1
  state in session89202, log overnight-local-worker-2.log, port8787. New command
  migration NOT yet applied locally. UI brain81515 is older code; restart before
  current full-flow UI tests. Simulator installed163; Browser Not connected.
- Router wire2/wire3 pass: API selected without Brave, no invented opaque ID.
- Connection repair ready for release: new durable connection_command_runs,
  shared /worker/connection-command plus carrier dispatcher, full context and
  card target, independent app reply/link creation, uncertain-effect recovery.
  Full Python3090passed2skipped; API full6+typecheck6 and real model5(11cases).
  New table is included in erasure triggers/cleanup and CI migration step.
  Must deploy API first, verify live, then brain cap100 and verify8/8 source.
- Earlier connection model1–4 found missing minter wiring/SMS dependency and
  an operation-vs-target ambiguity. Model5 actually persists links and passes.
- Remaining: proactive spoken API offers, draft-before-approval, multistep API,
  full browser queue proof/readable results, semantic legacy removal, final50
  profiles, capture/performance QA and final visual PDF. Keep working.

## Previous checkpoint — 2026-09-07 11:51 UTC

### 11:56 UTC continuation
- Readiness commit82b092968794099aad8193ec89b5b445547ee60e now LIVE, verified
  by34118717669 at11:54:39UTC:8/8 workers/current snapshots, source
  d75c3585b0bdbdd86d2e0fcdc2a93166dbfcbd1f374789213df176da5416ca87.
- UNCOMMITTED next repair: `_queue_job` always consults hand routing independent
  of Brave, with owner/backend/model explicitly supplied. A declared device act
  skips that model question. Only a positive research verdict can fall back to
  Chrome when server search is unavailable; absent verdict stays unlicensed.
  Tests added for API routing without search credentials and no-verdict refusal.
  Focused first run166passed/2skipped/1obsolete test pin; that pin was corrected
  to inspect the research-reuse question rather than unrelated router calls.
  Full run `work/audit/overnight-router-full-1.log` is underway.
- Next API work: `connections/wiring.ts::handleInboundText` is only called from
  routes/sendblue.ts and sms.ts. It requires messaging configuration and a phone,
  so calling it unchanged from app input would still fail phone-less accounts.
  `runTextCommandPlan` has a local `reply()` sending SMS; it needs channel-aware
  durable reply delivery. The current SMS waitUntil callback also races the
  brain's event claim, explicitly accepting duplicate answers in comments.
  Use the worker's already-owned event path to sequence connection handling
  before ordinary conversation; derive owner/text from the persisted event,
  make outcomes replayable/idempotent, and never execute a disconnect on quoted
  or other-speaker speech. Full conversation and measured source go to the judge.
  Do not add keyword filtering. Merely wiring explicit connect commands does
  not fix proactive API offers: those also need the existing model/catalog
  usage-signal path, currently missing a writer for ordinary speech/app input.

- Speech commit66fa7d4 verified LIVE by34116628621:8/8 workers, current snapshots,
  revision matched, runtime source c2d1def0e0368610ee16394b8d8c741b02889c85094f955af3bbd0c03e01b8d0.
- All five real Chrome fixtures passed through the live authenticated Gemini3.1
  proxy: compare, appointment(one exact write), login, capacity correction,
  injection refusal. `browser-production-results.json` records scope and limits.
  The live fixture account is DELETED; its old agent credential returns403.
- Readiness candidate:3,083 Python tests pass, two skipped;12 real-model contrasts
  pass; three actual worker replays recorded. Known contact/document no longer
  produces needless questions, calendar missing-end/correction remain correct.
  See `readiness-repair.md`. Candidate not yet deployed at this checkpoint.
- Still open: draft preparation held before useful work; hand router wrongly
  gated by Brave key; API connection commands wired only to SMS. These are next.
  Also full browser queue/lease proof, readable structured results, remaining
  semantic shortcuts, final50-person evaluation and visual PDF audit remain.
- Apple readback34118333933 at11:46UTC:162 VALID/internal IN_BETA_TESTING;
  attached to Sanket pilot but externally READY_FOR_BETA_SUBMISSION.159 review
  blocks162 submission. Do not equate attachment with external installation.
- Budget at11:45UTC:gateway observed$9.0962540792; native-browser conservative
  reservation$1.757278. Keep original ledgers; caps25+10 remain below total50.
- Existing personal extension still0.15. Published0.16 archives do not replace
  an unpacked installation automatically. Browser security policy rejected
  extension-settings access; do not bypass that via other tools.

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

## Release and deeper test status (09:15 UTC)

- UI/context release committed and pushed: a50f3ca4e6d49d194bdb3a1e99328c28eed738c6,
  build161. iOS CI 34104369111 is archiving; NOT yet verified in TestFlight.
- API CI 34104384706 deployed a50f3ca and verified the live URL's source/version
  plus34 ownership/auth/deletion checks. Local log overnight-api-deploy.log.
- System invariants found a date-expiring test fixture: quiet26h had become48h
  as the date changed. No production monitoring threshold changed. Replaced
  fixed date with26h-relative data, tested7cases, committed a52c859 and pushed.
- Brain changes are UNCOMMITTED. Live reply wire tests found partial-answer
  premature resume, quoted-consent cancellation, and legacy draft question
  persistence. First two cheap-model runs still failed. Upgrading these
  authority judgments to the already-configured strong tier; current live
  proof hit unavailable models under concurrent budget reservation. Do not
  count unavailable as a semantic pass; that evaluator has been corrected.
- 40 development people are running through actual local worker processes
  (overnight-50-development);10 held-out people remain closed. Credentials and
  models are restricted to localhost/API gateway. Actual cost roughly$3 sofar;
  conservative reservations share the originalUS$50 cap (operating$25).
- Memory real-model checks found planned completion being retired as done,
  and an ambiguous unnamed-person identity case needing adjudication. Unfixed.
- Chrome metadata found one dead Anticipy path and one current0.15.0 install
  matching repository hashes. Browser security policy REFUSED chrome://extensions
  and explicitly prohibited alternate routes to that management page. Do not
  work around it or modify these entries. Continue isolated browser fixtures.

## Verified progress and next release (10:12 UTC)

- Apple independently reports build161 VALID and IN_BETA_TESTING for the internal
  group. Query34105899086; evidence work/audit/overnight-asc-161.log. This is
  availability, not proof anyone installed161. External161 still READY_FOR_BETA_SUBMISSION.
- Live brain is still1682d69d,8 owner workers, current snapshots, no cleanup failures.
  Recent worker-status rows identify Sendblue. Brain repairs below are NOT deployed.
- Real HTTP/model reply proof overnight-replies-final-2 passed14/14, including
  quoted consent (must not mutate), partial answers, exact-card ambiguity, typed
  schema answers, queued cancellation and multiple task approval. Strong tier is
  needed for these authority judgments. The cheap-tier failures remain recorded.
- Real memory relation proof using the production strong tier passed16/16, including
  future promises not being treated as completed, different recipients/people and
  revoked facts. Earlier14/16 result was the wrong cheaper tier, not production.
-40 development people finished through isolated actual worker processes; outcomes
  require semantic review, not automatically PASS.10 held-out remain unopened.
-12 ambient boundary diagnostics completed; eight non-action cases stayed quiet,
  firm owner plans created held/quiet work. These transcripts include explanatory
  hints, so natural raw-speech variants are still required before final evaluation.
-Real isolated Chrome agent: compare, capacity discrepancy, quoted injection,
  login wall and appointment passed. Appointment first FAILED with five incomplete
  submissions: page_map omitted wrapping-label names, so the temporal judge removed
  the end time; the duplicate fence checked before that removal. Repaired accessible
  labels and final-payload recheck on BOTH click and Enter. Appointment then made
  exactly one correct POST. Two new injected-error regressions also pass.
-Extension now0.16.0, iOS version pin updated, three zip aliases rebuilt. These are
  NOT yet published or installed in Omar's personal Chrome. No extension management
  workaround is allowed after the browser security rejection.
-Actual simulator paired the extension registration/heartbeat client through local
  Worker/D1. Registration singleflight and owner identity passed; hardware Chrome
  plumbing was adapted, not an installed-extension end-to-end claim. Revocation
  and reconnect still need the final pass.
-iOS162 code improves fresh-first-line context offers, typed reply follow/quiet
  counts, and truthful extension update instructions. Full logic suite passed and
  simulator build passed. Hands-on NEW REPLY tap exposed a NEW layout freeze in
  LazyVStack (100% CPU; sample in overnight-ui-freeze.sample.txt). Replaced current
  thread's lazy estimates with measured bounded rows and deferred the scroll until
  the banner change settles. Retest completed the jump; typing remained responsive.
-Actual simulator main composer answer then Yes resumed the SAME legacy draft.
  Another natural cancellation is being sent now. No real user data/calendar/SMS
  was touched.
-Persisted question sweep now also sees awaiting_confirm cards with a question,
  paginates, checks owner and status, defers proposals at night/during conversation,
  and uses the shared outreach budget. Authorized executor questions still reply
  immediately. Truthful voice context no longer pretends every task reached a
  browser.6 new delivery tests +57 existing delivery tests pass. Older wording
  deduplication/semantic tape elsewhere remains to audit; no claim of full removal.
-Full Python3033 passed/2 skipped before latest delivery tests. Extension94 suites
  passed before the two new final-payload regressions. Re-run required appropriate
  focused/full checks after final edits.
-Observed total model spend was aboutUS$6.66 before these last ambient/browser runs;
  original50-dollar ledger intact, no budget reset.

Next: finish UI responsiveness/capture/reply/pair revoke checks; exact-source
review and162 source commit/CI. Commit/deploy brain through brain-deploy.yml with
component=brain confirm=DEPLOY cap=100 (preserve fleet cap), verify live process and
snapshot hashes. Publish extension zip through API CI. Complete natural speech
and held-out/API-connection tests, clean synthetic accounts, update visual PDF.

## Release162 and reply deployment preparation (10:33 UTC)

-iOS/browser source committed81dafd1393bb79d982f087fe2279aff84240a89c.
 CI34110939670 passed; ASC query34112233057 passed (see overnight-asc-162.log).
 API deploy34110987507 passed. All three live zip aliases are0.16.0 and exactly
 match source SHA25693c3a2d8c29e97031c7c81707a2fb086c01564b3d201b546e2ec1b18aa0a9ba9.
-Browser re-pair and UI disconnect verified. Correctly formed /agent/key was
 rejected403 after disconnect. Before disconnect the local rig authenticated
 but returned503 because browser model configuration is absent; this limits the
 local pairing proof. It does NOT prove the full installed-extension/API loop.
-14 final real-model reply cases passed again after truthful human-readable
 receipts: a queued job is ready to start, not falsely already executing; a
 cancellation no longer mechanically concatenates a malformed task title.
-Question coverage now belongs to a model with complete task/question/history.
 Word overlap and number-token guesses were removed from that follow-up path,
 as was the paraphrase token guard.8 real-model coverage cases pass.
-Questions use an exclusive durable pre-send fence keyed to exact job/question/
 workflow version. Lost provider responses remain unconfirmed and do not resend
 after restart. Database outage creates no unrecordable SMS; restoration allows
 delivery. New question identity remains sendable.68 focused delivery tests pass.
-Full Python run3051 passed/2 skipped with one obsolete source-string test failing
 because it required the deleted token guard. Replaced it with real delivery-path
 behavior; focused41 passed. No production failure was hidden by that change.
-tape_gate exits1 for its five declared legacy pieces, all other registry legs
 pass. These are STILL OPEN, not an all-clear: undeclared effect-channel fallback,
 compute fallback, shard word-count filter, degraded third-person filter, and
 anaphoric segment word matching. Other legacy semantic shortcuts also remain.
-Natural speech corpus (no explanatory rubric in the spoken text), including the
 original greeting and calendar/accounting quotes, is running as overnight-natural-1
 with2 workers.10 held-out people still not opened. Do not claim corpus completion.
-Next: commit these reply/delivery changes; deploy brain via CI with cap100; check
 live process/source/snapshot identities. Then finish natural speech/50-person/API
 connection proof and remove remaining semantic shortcuts on active paths.

## 2026-09-07 11:00 UTC — natural speech failures reproduced and under repair
- Brain96e7ef4 deployed by CI34112544081. Live verification observed8/8 running
  workers with source93b08f99bb48a15302f9b3eb7d4a2994e1d5078b2adf28dcc4bf3a1c5a98e100,
  current snapshots, correct revision and zero archive cleanup failures.
- Natural1 completed10 actual worker runs. It reproduced the exact unwanted
  calendar/accounting task: memory extraction knew the work was complete, but
  both triage tiers invented unfinished work (strong model explicitly guessed
  an ASR repair from got into gotta). Another completed conversation triggered
  an irrelevant memory answer through _RECALL_RE. The direct calendar request
  was lost when notify_owner could not text, because queue creation depended
  on successful delivery. These are observed failures, not hypothetical risks.
- Prompt repair preserves recorded tense/completion; a separate contextual
  information-request model now replaces the question-mark/briefing early route.
  Natural2 reproduced the original completed utterance and ordinary completed
  dialogue with no task and no unsolicited answer (2/2).
- Natural2 direct calendar request now persisted, but exposed a second defect:
  unsupported_names considered September an invented person, and reconstruction
  of Decision dropped touches=world. This produced an absurd which-September
  question and lost the phone-calendar route. Replacing that active token check
  with model grounding; transitions preserve all Decision fields via replace.
- A saved question is now independent of optional SMS. Worker avoids writing
  an unsent app question into outbound-message history (which otherwise suppresses
  the first SMS). Its persisted job owns the app card; the durable question
  outbox owns texting. Tests cover absent phone and failed persistence.
- Memory rendering no longer drops every JSON/contact fact merely for braces,
  nor drops a contradictory fact because it contains the utterance's word set.
  Exact record identity handles self-echo; imported facts remain nonce-fenced.
- Current work UNCOMMITTED/NOT LIVE. Natural3 is replaying direct calendar and
  draft requests. Full tests running; old assumptions about inline SMS and word
  filtering are being replaced with observable delivery/grounding tests.
- Speech-request audit1 has no unwanted answers, but strict verdict labels
  exposed ambiguous cases and a Spanish request missed by the cheap tier.
  Escalate unclear/unavailable to the existing strong tier, then rerun. A safe
  unclear negative is not a false positive, but provider unavailable never passes.

## 2026-09-07 11:25 UTC — speech release candidate verified
- Full Python checks:3072 passed,2 skipped (overnight-core-full-6.log).
  Targeted last changes also passed. No iOS source changed in this release.
-12 real grounding cases and16 contextual information-request cases pass.
-10 natural worker transcripts completed (natural-speech-results.json). Nine
  behave as expected at ingestion/planning; case9 still asks for a known email
  and for source contents before retrieval. This is an OPEN memory/API issue.
-Calendar-delivery1 specifically proves the final shared path: one draft
  device_calendar task, missing-end question, invited=true, source event marked
  ask, no false outbound event. Invited questions may text at night; proactive
  proposals defer. Durability/failure/duplicate tests cover this distinction.
-Live browser fixture prepared on api.anticipy.ai. Signup, registration, exact
  code lookup, pairing readback and model access passed. The live browser and
  vision model is Gemini3.1Pro, not the Sonnet used by the earlier local proofs.
  Through that ACTUAL live proxy, compare passed3 calls/21.8s and appointment
  passed11 calls/45.1s, exactly one synthetic APPT-1 with correct start/end.
  Chrome pages are isolated fixtures; extension plumbing is adapted, not an
  installed-extension claim. Live account MUST be cleaned up after next probes:
  PYTHONPATH=. python3 proof/audit/prepare_browser_fixture.py cleanup --label overnight-live-browser-1
-Actual proxy testing reserves a conservative independent $10 ceiling in
  work/audit/overnight-live-browser-budget.json. Gateway operating cap remains
  $25, so combined controlled audit spending remains below authorized$50.
-Sanket:162 attached to private group by34115188213, but Apple refused review:
  another build in the same train (159) is already in beta review. Do not call
  this installable externally. Keep checking existing review; no duplicate invites.
-Next commit/deploy the speech fix; verify8/8 live source/snapshots again.
  Then memory/source retrieval before questions, remaining active semantic
  shortcuts, browser response formatting, full queue/API execution and UI QA.
