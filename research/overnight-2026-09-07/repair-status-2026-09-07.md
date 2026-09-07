# Calendar, text, discovery and browser repair

**Latest verified state:** iOS build 167 is installable by the owner in TestFlight; API and all eight brain processes are live on the repaired source. The live text test is delivered and reconciled. Chrome still runs extension 0.15.0 and needs the published 0.17.0 update. The global removal of legacy meaning rules remains unfinished.

Branch: cloudflare-backend. Starting revision: a4927035. Mac source excluded.

## Implemented and checked before release

- Native iPhone calendar: real EventKit executor, owner/consent checks, atomic claims, separate approval/release, readback receipts and conservative interrupted-effect recovery. Build 166 in both source declarations. See native-calendar-repair.md.
- Browser 0.17.0: bounded background HTTP requests; correct coordinates after smooth scrolling; reject removed targets. All83 suites and real Chrome geometry fixtures passed. See browser-handoff-repair.md.
- Text replies: one durable feed message and outbox, shared app/SMS identity, unique provider-attempt fence, canonical phone recheck, no permanent attempt claim when provider is unconfigured, per-row recovery. A timeout is unconfirmed, never delivered and never blindly replayed. The same saved message survives restart without re-running the task.
- Connection routing: one bounded HTTP thread keeps model/catalog planning off the serial brain loop. Durable event identity remains authoritative. No word routing added. See connection-dispatch-background.md.
- API catalog query: when contextual app identification is absent, do not substitute the entire human sentence as a catalog search.
- Proactive discovery: recent owner conversation now feeds the existing app-usage evidence store through contextual model verdicts and actual catalog identity. A separate hourly schedule collects at most one completed scan per owner/day, then invokes the existing consent/nudge policy. It does not enable the retired HQ reminder schedule. Unavailable models retry; they do not become no-app judgments.

## Evidence

80 targeted Python tests passed. Worker package tests and TypeScript checks passed; focused recovery and authenticated callback checks also passed. Real local Worker/D1 outbox test passed with a non-network message recorder and fixture cleanup. Six live Claude Sonnet 4.6 discovery cases passed; catalog and conversations were synthetic. Model ledger observed spend 18.5500813148 USD of the 50 USD authorized audit budget at this checkpoint.

## Limits that remain explicit

- Provider acceptance is not handset delivery. A crash after recording an attempt but before sending is conservatively unconfirmed; there is no invented exactly-once delivery guarantee. Media is not persisted by this text-only reply outbox (current inbound reply call sites do not attach media).
- Pendant callbacks are intentionally disconnected pending a local decoder and hardware proof. No pending callback queue exists. See pendant-audio-status.md.
- Legacy semantic tape remains elsewhere in the harness, including the old shard-length and anaphoric paths. These repairs add no word-list or regex interpretation, but do not certify the whole repository as free of it.
- Browser fixtures do not prove every site or the user's installed extension version. Calendar simulator proof does not prove the user's CalDAV sync.
- Deployment, live source readback and TestFlight verification are still pending at this checkpoint.

## Final release additions

- Build 166 includes per-reply delivery badges. Matching requires the exact owner, reply id and transport correlation key; old job notifications cannot label a different reply as delivered. Seventeen policy checks and the final simulator build passed. The existing task quiet-hours caption remains.
- Authenticated SendBlue DELIVERED/READ callbacks update the matching reply attempt; later ERROR callbacks cannot downgrade a confirmed delivery. Unmatched/early callbacks remain unconfirmed (provider reconciliation for that race is still incomplete).
- SendBlue ingress now only persists the input; the owner brain invokes the connection dispatcher with a live HTTP request. Long model calls no longer depend on the webhook's30-second post-response lifetime.
- API CI still referenced deleted pre-migration asset scripts. Replaced these with an explicit three-alias/source-byte check.
- Discovery processes at most two owners per hourly tick, one completed scan per owner/day; task-specific access offers remain a separate immediate path. There is no claim that every unused collector is now connected. Email-domain, generic link and browser-observer collectors are still not production-fed by this repair.


## Release corrections and live observations

The initial release commit is `03f0c7f4`. Build 167 follows in `1f2d8f67`: it
updates the iPhone's required browser version to0.17.0 and removes an obsolete
test that required phone-side word/regex contact parsing. The answer writer now
preserves each complete owner answer in a versioned field for contextual brain
interpretation. The build number moved in both source files in that commit.

The full CI run on that revision passed 2,979 Python checks, 83 browser suites,
Worker package checks/type checks and the existing Mac check (no Mac source was
changed by this repair). App Store Connect separately confirmed build 166 as
VALID and available to the owner's Internal tester group. Final build 167 and
backend receipt readback are recorded in `repair-live-release.json`.

A live, authorized owner app-to-text check reached the production brain and
created exactly one reply and one SendBlue attempt. The reply appeared in 16.6 s:
“Got it, your delivery check came through.” A direct authenticated SendBlue status
query for that saved handle confirmed DELIVERED. The test input was created with
the app's API event shape; it was not a physical-phone keyboard test.

That live check exposed a real remaining bug: the app's saved delivery attempt
stayed `sms_accepted` for 180 seconds despite confirmed delivery. Commit
`b9a388b2` adds a read-only status reconciliation for saved provider handles. It
can recover delayed/lost callbacks without sending again. 97 focused tests passed.
One lookup per sweep, a 30-second owner scan interval and persisted 60-second
per-handle throttling bound transport work. The lookup considers the most recent
100 candidate attempts from 7 days. Only verified DELIVERED/READ advances delivery;
failed lookups and negative observations cannot downgrade a delivered callback.
An attempt with no saved provider handle still requires manual reconciliation.
These are resource and identity checks, not judgments about human meaning.

All three live extension downloads were independently read and matched 0.17.0
source, SHA256 `2e36a5de26fd89dd02336b6e3faa4f6b2523625b4fd9ec9f50ed8a0d22caaae7`.
The owner's fresh backend heartbeat at 20:15:53 UTC still reported
`Chrome/152.0.0.0 ext/0.15.0`, paired=true. A live heartbeat is not proof of
successful task authorization, and publishing a zip does not reload that
installed copy. Install/reload verification remains open.

The status API contract is documented by
[SendBlue](https://docs.sendblue.com/api/python/resources/messages/methods/get_status).
The live response used the nested `{"status":{"status":"DELIVERED"}}` envelope;
this exact shape is included in the regression tests.

## What remains outside the completed repair

The code that collects conversation app-use evidence now has a production caller
and hourly schedule. Email-domain, generic-link, browser-host and answer-to-ask
collectors still lack production inputs. A collector's existence is not evidence
that it is running. Likewise, model-led discovery records evidence; it does not
connect an account or grant authority for an external action.

No new heuristic interprets human words in these repairs. The global
zero-hardcoded-meaning goal remains unfinished: legacy shard-length suppression,
anaphoric handling and other registered semantic tape still exist elsewhere.
The earlier harness map is retained explicitly as a pre-repair snapshot.

Provider terminal failures without a callback are not promoted by the positive
receipt reconciler. Unknown acceptance with no provider id is never blindly
replayed. Arbitrary websites, every possible Composio action, actual iCloud
calendar synchronization and physical pendant transcription are not established
by these tests. The Mac app is excluded from this work.

Budget note: the gateway ledger records 18.5500813148 USD observed/committed cost;
the separate native API ledger reserves 17.131602 USD against its 19 USD ceiling.
The gateway runtime ceiling was 30 USD; combined ceilings 49 USD stay inside the
user's 50 USD authorization. Reservations are not a provider billing invoice.


## Final verified state, 20:25 UTC

- App Store Connect query 34159127874 confirms build 167 VALID, Internal group
  installable, with the owner's iCloud tester already in that group. This is
  separate from the successful upload workflow 34158318108. External testing was subsequently enabled for the existing private tester group, as recorded below.
- API health returns HTTP 200 and revision 03f0c7f4; all three extension packages
  match the repaired 0.17.0 source. No later API source change was needed for the
  Python-only receipt correction.
- Brain status returns HTTP 200, 8 served owners, 0 failures, all 8 running
  b9a388b2 source with current memory snapshots. Source SHA256 is
  `5066e3a3a7e5d4246d28546b8d4283728bb33e70f166278536b564e29332993b`.
- The original live test reply's attempt and outbox now both read
  `sms_delivered`. The production reconciler recovered the missing receipt; no
  replacement test input or manual status patch was used.
- System invariants 34159096498 passed on the final backend revision: 3,001 Python checks, 2 skipped, 83 browser suites and the Worker checks.

Machine-readable proof: `repair-live-release.json` and `repair-live-text.json`.
The three-page PDF is generated by `proof/audit/repair_report.py`; its content
uses the committed, sanitized release evidence rather than private credentials.


### External tester readback, 20:28 UTC

Authorized workflow 34159516762 attached build 167 to the existing private Sanket
pilot group. Apple accepted review and the subsequent reads reported
IN_BETA_TESTING, tester INVITED, automatic notification enabled, public link off.
Both the helper's post-write readback and the separate Who can install step
confirmed the exact build/group association. This is available for installation;
physical installation by the external tester was not observed.
