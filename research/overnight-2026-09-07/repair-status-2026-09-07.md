# Calendar, text, discovery and browser repair

Branch: cloudflare-backend. Starting revision: a4927035. Mac source excluded.

## Implemented and checked before release

- Native iPhone calendar: real EventKit executor, owner/consent checks, atomic claims, separate approval/release, readback receipts and conservative interrupted-effect recovery. Build166 in both source declarations. See native-calendar-repair.md.
- Browser0.17.0: bounded background HTTP requests; correct coordinates after smooth scrolling; reject removed targets. All83 suites and real Chrome geometry fixtures passed. See browser-handoff-repair.md.
- Text replies: one durable feed message and outbox, shared app/SMS identity, unique provider-attempt fence, canonical phone recheck, no permanent attempt claim when provider is unconfigured, per-row recovery. A timeout is unconfirmed, never delivered and never blindly replayed. The same saved message survives restart without re-running the task.
- Connection routing: one bounded HTTP thread keeps model/catalog planning off the serial brain loop. Durable event identity remains authoritative. No word routing added. See connection-dispatch-background.md.
- API catalog query: when contextual app identification is absent, do not substitute the entire human sentence as a catalog search.
- Proactive discovery: recent owner conversation now feeds the existing app-usage evidence store through contextual model verdicts and actual catalog identity. A separate hourly schedule collects at most one completed scan per owner/day, then invokes the existing consent/nudge policy. It does not enable the retired HQ reminder schedule. Unavailable models retry; they do not become no-app judgments.

## Evidence

80 targeted Python tests passed. Worker package tests and TypeScript checks passed; focused recovery and authenticated callback checks also passed. Real local Worker/D1 outbox test passed with a non-network message recorder and fixture cleanup. Six live Claude Sonnet4.6 discovery cases passed; catalog and conversations were synthetic. Model ledger observed spend18.5500813148USD of the50USD authorized audit budget at this checkpoint.

## Limits that remain explicit

- Provider acceptance is not handset delivery. A crash after recording an attempt but before sending is conservatively unconfirmed; there is no invented exactly-once delivery guarantee. Media is not persisted by this text-only reply outbox (current inbound reply call sites do not attach media).
- Pendant callbacks are intentionally disconnected pending a local decoder and hardware proof. No pending callback queue exists. See pendant-audio-status.md.
- Legacy semantic tape remains elsewhere in the harness, including the old shard-length and anaphoric paths. These repairs add no word-list or regex interpretation, but do not certify the whole repository as free of it.
- Browser fixtures do not prove every site or the user's installed extension version. Calendar simulator proof does not prove the user's CalDAV sync.
- Deployment, live source readback and TestFlight verification are still pending at this checkpoint.

## Final release additions

- Build166 includes per-reply delivery badges. Matching requires the exact owner, reply id and transport correlation key; old job notifications cannot label a different reply as delivered. Seventeen policy checks and the final simulator build passed. The existing task quiet-hours caption remains.
- Authenticated SendBlue DELIVERED/READ callbacks update the matching reply attempt; later ERROR callbacks cannot downgrade a confirmed delivery. Unmatched/early callbacks remain unconfirmed (provider reconciliation for that race is still incomplete).
- SendBlue ingress now only persists the input; the owner brain invokes the connection dispatcher with a live HTTP request. Long model calls no longer depend on the webhook's30-second post-response lifetime.
- API CI still referenced deleted pre-migration asset scripts. Replaced these with an explicit three-alias/source-byte check.
- Discovery processes at most two owners per hourly tick, one completed scan per owner/day; task-specific access offers remain a separate immediate path. There is no claim that every unused collector is now connected. Email-domain, generic link and browser-observer collectors are still not production-fed by this repair.
