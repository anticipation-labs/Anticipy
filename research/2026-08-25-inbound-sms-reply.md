# Can a real user reply to an Anticipy text and have it do something?

2026-08-25. Read-only investigation. No message was sent to produce it.

## 1. The answer

**Partly — and for one of the two real people the system texts, no.** Replies
from the owner's number `+16047245161` work end to end: five of five inbound
texts since 2026-08-19 became `sms_reply` events and were acted on, the most
recent `SM919b49ae107bb1f292a7d52314e75cd9` at 2026-08-24T01:26:39Z landing as
event `0zh0kchlwtr45lx` in the same second. Replies from the other live human,
`+16282721282`, are 100% discarded — all five of his texts since 2026-08-20,
four of them cancellations, were answered with HTTP 200 and thrown away at
`backend/pb_hooks/sms.pb.js:206-208`, because two accounts claim his number and
the hook fails closed rather than pick one.

The single place it breaks is `backend/pb_hooks/sms.pb.js:206-208`, fed by the
owner lookup at `backend/pb_hooks/sms.pb.js:166-167`.

A third number, `+17868735256`, never receives anything to reply to: fifteen
outbound messages since 2026-08-19, zero delivered, all Twilio error 30034.

## 2. What is proven vs what is assumed

### Proven — I ran these myself against LIVE

- **The two-account condition exists right now.** `GET
  /api/collections/owner_profile/records?perPage=200&sort=-updated` returns two
  rows for `+16282721282`: `0v0wois0lzfoofr` ref `2ut6yd1xb9aahdj` (created
  2026-08-20 00:24:56.744Z) and `ryinspqbukimoex` ref `bkandbths3d8n4b`
  (created 2026-08-19 05:22:46.268Z, updated 2026-08-20 00:16:25.313Z). Two
  distinct non-empty refs.
- **Five real texts were lost.** Twilio `Messages.json?From=%2B16282721282`
  returns exactly five, all `direction=inbound`, all `to=+16196584447` (this
  deployment's `TWILIO_PHONE_NUMBER`), all `status=received`:
  `SM1d5d9893…` 2026-08-20T00:42:11Z "Yes"; `SMbf57bbc7…` 2026-08-20T05:03:31Z
  "It's going, cancel that request"; `SMe84b2547…` 2026-08-21T05:38:39Z "Forget
  about this request"; `SM102e12ff…` 2026-08-22T18:26:58Z "Yeah of course";
  `SM391a4268…` 2026-08-22T20:00:41Z "Forget the request".
- **Nothing was written for any of them.** Filtering `events` on those five
  `external_event_id` values with no `kind` restriction returns
  `totalItems = 0`. Filtering `events` on `goal="+16282721282"` also returns 0.
  Reconciling every inbound message since 2026-08-19 against `sms_reply` rows:
  `landed {+16047245161: 5}`, `missing {+16282721282: 5}`.
- **It was not a signature failure.** The two 2026-08-22 losses are bracketed by
  successful validations from the other number: 15:01:06Z landed, 18:26:58Z
  lost, 19:42:56Z landed, 20:00:41Z lost, 2026-08-23T21:21:16Z landed. Signature
  checking demonstrably worked in that window. Independently, every Twilio 11200
  alert on the account is dated 2026-08-15 and carries the historical stale
  `?token=61bffc5f` URL; there are none after that date. The number's binding is
  clean today: `sms_url = https://backend-production-61e0a.up.railway.app/sms/inbound`,
  POST, no application SID, no fallback URL.
- **The deployed build contains the fail-closed gate.** A POST to
  `/sms/inbound` with `Content-Type: application/json` returns 415, so the
  deployed code is at least commit `c5b3ab0f`, which is newer than `e6e93319`
  (2026-08-12) where the `matches.length === 1` predicate first appears. The
  probe sends no SMS and writes nothing.
- **The webhook is the only inbound path.** `brain/voice_arm.py:447-452` is an
  outbound POST to `Messages.json`; there is no inbound poll anywhere in
  `brain/worker.py`. A dropped event reaches nobody — `brain/worker.py:3671`
  consumes `sms_reply` rows already scoped by `owner_ref`.
- **The owner's own number is one claim away from the same fate.** `+16047245161`
  has four `owner_profile` rows, only one ref-bearing. Orphan row
  `1r7vce8u1vmff7w` carries `owner_id=45CE4E52-B83B-4F1B-8E71-389D9F39966D`, and
  live `/worker/owners` shows account `l5wygrhnb067lbs` holds exactly that
  `legacy_uuid`. `backend/pb_hooks/claim_legacy.pb.js:76-80` stamps
  `owner_ref = auth.id` on any row matching `owner_id = {:u} && owner_ref = ''`.
  One sign-in by that account makes the owner's number ambiguous.
- **Outbound to a third number has never worked.** 1200 outbound messages since
  2026-08-01, grouped by recipient: `+16047245161` 755 delivered / 4 failed;
  `+16282721282` 410 delivered / 1 undelivered; `+17868735256` **15 undelivered,
  0 delivered, all error 30034**, from 2026-08-19 through 2026-08-25T03:15Z.

### Assumed — reasoned, not observed

- **I never read a "DROPPED (ambiguous)" log line.** I have no verified Railway
  stdout access. The drop is deduced, and the deduction is tight: row
  `ryinspqbukimoex` was ref-bearing and last touched 2026-08-20 00:16:25Z, which
  is 26 minutes before the first lost text and never since (PocketBase bumps
  `updated` on every save), so `matches.length >= 1` at all five moments; no
  event exists for any of them, so `matches.length != 1`; therefore
  `matches.length >= 2` and `sms.pb.js:206` is the only branch that can have run.
  The residual assumption is that no event was created and later deleted. The
  only deletion path is `account_delete.pb.js`, and both accounts still hold
  their rows, so I regard this as very unlikely but not disproven.
- **I could not confirm the exact deployed commit.** I bounded it to
  `>= c5b3ab0f` via the 415 probe. Law 3 says repo-green is not done; the same
  caution applies to this report's claim about which code is running.
- **I could not read the `owners` collection's `phone` field.** `/worker/owners`
  returns only `id` and `legacy_uuid`. So the fallback lookup at
  `sms.pb.js:174-179` is unverified: I cannot say whether `owners.phone` is
  populated or whether it is ambiguous in its own right.
- **I could not identify who the two accounts behind `+16282721282` are.** Every
  `owner_profile.name` came back empty through the service token, and I could
  not read owner emails.
- **I did not verify that `+17868735256` belongs to a real person** rather than
  being a test entry, only that the system keeps texting it and Twilio keeps
  rejecting it.

### What a real end-to-end test would require

Nothing here was proven by sending a message, and it cannot be without spending
money and reaching a real phone. A genuine test would need: a consenting handset
whose number sits on exactly one `owner_profile` row; an outbound question sent
from `+16196584447` to it; a human reply; then confirmation of a `sms_reply`
event row with a matching `external_event_id`, a `processed` transition, and a
delivered outbound answer. Steps 2 and 3 are exactly what this investigation was
forbidden to do, so the loop's last inch is inferred from historical traffic
rather than demonstrated.

## 3. The findings, ranked by whether they stop a real person's reply

### Finding 1 — Two accounts on one number silently discard every text. LIVE.

**Stops a reply: yes. Happening now.**

What breaks: `sms.pb.js:164-180` resolves a sender phone to a set of
`owner_ref`s. `sms.pb.js:206-208` drops the message when that set has more than
one member, returning empty TwiML behind HTTP 200 and logging only to stdout.
`+16282721282` has two ref-bearing `owner_profile` rows, so every text from it
hits that branch.

Evidence: the live rows, the five Twilio SIDs, and the zero matching events, all
listed in section 2. The counterpart number resolves and works, which isolates
the fault to routing rather than transport, signature, or the brain.

This is deliberate, not an oversight. `sms.pb.js:160-163` states the policy —
"Shared/recycled/ambiguous numbers fail closed; an SMS must never choose which
person's browser to control" — and
`tests/test_inbound_sms_and_calls.py:287-292` pins the behaviour. Any fix
changes a currently-passing test on purpose.

Two pieces of the folklore around this are wrong and should not be carried
forward. First, `backend/pb_migrations/1700000016_share_phone_across_accounts.js:3-11`
is not the cause: it dropped a unique index on `owners.phone` only, and
`owner_profile.phone` was never unique. Its prose ("Texting still routes by
owner_profile") simply went stale when the fail-closed predicate arrived eight
days later in `e6e93319`. Second, the drop is older than its log line: the log
at `:206-208` arrived in `cf4b5e3f` (2026-08-22T04:35Z), but the identical
`matches.length === 1` predicate has gated event creation since `e6e93319`
(2026-08-12). The three earliest losses left no trace anywhere at all.

Fix: **do not fan out one event per claiming ref.** That idea looks safe because
`brain/worker.py:2897` re-checks `same_phone()`, but it is not:
`anticipy.owner_phone` comes from `fetch_owner_phone` (`brain/worker.py:183-194`)
via `_latest_profile` (`brain/worker.py:128-141`), which reads *that owner's own*
profile row — and both rows carry `+16282721282`. `same_phone`
(`brain/worker.py:665-672`) compares the last ten digits, so it would pass for
both workers and one "Yes" would release held jobs in two accounts. It excludes
strangers; it cannot separate two accounts sharing a number, which is precisely
this case.

Instead, tiebreak deterministically inside the hook — the account with a pending
question, else the most recently active — and make the drop visible (finding 4)
rather than leaving it in stdout. Separately, reconcile the duplicate rows: this
number should be on one account.

### Finding 2 — A third number receives nothing, so its user can never reply. LIVE.

**Stops a reply: yes, one step earlier.**

What breaks: outbound to `+17868735256` has failed 15 times out of 15 with
Twilio error 30034 (unregistered A2P 10DLC), first 2026-08-19T05:24:21Z, most
recent 2026-08-25T03:15:00Z. Zero delivered. There is no reply loop to test
because the question never arrives.

Evidence: per-recipient status counts over 1200 outbound messages, section 2.
Twilio Monitor alerts corroborate: 16 alerts with code 30034, the newest
2026-08-25T03:15:00Z.

Note this is not a code defect and no code change fixes it. It is a Twilio
messaging-compliance registration for the sending number. I did not investigate
whether `+16047245161` and `+16282721282` deliver only because they are older
established destinations, so I cannot say whether this failure will spread to
them.

Fix: register the A2P 10DLC brand and campaign for `+16196584447`. Until then,
the system is silently talking to a number that cannot hear it, and the outbound
send path treats these as sent.

### Finding 3 — The owner's own number is one sign-in away from finding 1.

**Stops a reply: not yet. It is armed.**

What breaks: `sms.pb.js:166-167` asks for at most three `owner_profile` rows
sorted `-updated`, filtered on `phone` alone. `+16047245161` has four rows.
Empty-ref rows are skipped at `:169-171` but still consume the window. Today the
one ref-bearing row `i9qras8aboe5ygc` (ref `3tjzbdptx85mpsp`, updated
2026-08-24 16:37:02.693Z) is the most recently updated, so it resolves.

Two ways it breaks with no alarm. First, orphan `1r7vce8u1vmff7w` is claimable
by account `l5wygrhnb067lbs` via `claim_legacy.pb.js:76-80`, which makes the
owner's number carry two distinct refs — finding 1 applied to the primary user.
I verified this pairing live and it is the only dangerous one of the three
orphans: `22migkbm7xsflin` is claimable only by `3tjzbdptx85mpsp`, which is the
owner's own ref and therefore harmless, and no account holds the `legacy_uuid`
for `elimhifbtspjy6j`. Second, if all three empty-ref rows are touched after the
ref-bearing one, the three-row window contains no ref at all and the lookup falls
through to the `owners` collection, whose behaviour here I could not verify.

Fix: filter the lookup to rows that can resolve — `phone = {:phone} && owner_ref
!= ''` — so empty-ref rows cannot consume the window, and raise the limit above
three. The limit exists only to bound the query; more than one distinct ref is
the signal, and three rows is not enough to see it reliably. Then reconcile or
delete the three orphan rows on `+16047245161`.

### Finding 4 — The drop is invisible to everything except stdout.

**Stops a reply: no. It is why the other three went unnoticed for five days.**

What breaks: both silent-drop branches (`sms.pb.js:202-205` for zero matches,
`:206-208` for ambiguity) `console.log` and return healthy TwiML. From Twilio's
console the webhook looks perfect — 200, no alert, no retry. Nothing polls,
counts, or compares.

Evidence: no file under `overnight/` mentions `sms_reply` or `sms/inbound`; the
only references are in `tests/`, which are unit tests against a mocked
`findRecordsByFilter`. `tests/test_inbound_sms_and_calls.py:120-123` mocks that
call as `(collection) => collection === 'owner_profile' ? profiles : []`,
discarding sort, limit and params, so the suite structurally cannot observe
truncation or ordering. No gate anywhere checks phone-to-ref ambiguity.

Fix: see section 5.

## 4. The order to fix them in

Law 3 applies throughout: repo-green is not done, and this backend has served
stale code before. Every leg below is verified against LIVE or it is not
verified. Note that `railway up` reports success while failing, so each deploy
needs an `overnight/is_it_live.py`-style confirmation.

1. **Reconcile the duplicate rows on `+16282721282`.** Data change only, no
   deploy, no code. This is the one action that restores a live user's replies
   today. Decide which account is his, clear the other row's claim, then confirm
   the lookup returns one ref. Everything else is prevention.
2. **Ship the gate leg in section 5, red.** Code change plus deploy of the gate
   itself only — it reads production, it does not change it. Doing this second
   means step 1's result is measured rather than asserted, and the same leg then
   guards steps 3 and 4.
3. **Fix the lookup: `owner_ref != ''` in the filter, limit above 3.** Code
   change in `backend/pb_hooks/sms.pb.js:166-167`, requires a backend deploy.
   Low risk, closes finding 3's second path. Verify with a live 415-style probe
   plus the new gate leg, not with the unit suite, which cannot see it.
4. **Clean up the three orphan `owner_profile` rows on `+16047245161`.** Data
   change, no deploy. Closes finding 3's first path. Do this after step 3 so the
   window fix is already in place if a claim races the cleanup.
5. **Decide the ambiguity policy and implement the deterministic tiebreak.**
   Code change plus deploy, and it must knowingly rewrite
   `tests/test_inbound_sms_and_calls.py:287-292`. This is the real design
   decision and it should not be rushed ahead of steps 1-4, all of which are
   safe without it. Do not implement the per-owner fan-out; the reasoning that
   makes it look safe is wrong, as shown in finding 1.
6. **Register A2P 10DLC for `+16196584447`.** No code, no deploy — a Twilio
   console and compliance task. Independent of everything above and can run in
   parallel from the start.

## 5. The gate leg that should exist

There is none today, which is why five lost replies sat unnoticed. The leg has
to compare two systems, because each looks healthy alone: Twilio shows a 200 and
PocketBase shows a well-formed absence.

Proposed, as a new leg reading LIVE:

- **Leg A — every inbound text became an event.** For each Twilio inbound
  message to `TWILIO_PHONE_NUMBER` in the last 72 hours, assert an `events` row
  exists with a matching `external_event_id`. Report each miss with its SID,
  timestamp, sender and body. This leg would have gone red on 2026-08-20 at
  00:42Z. It is the leg that answers the owner's actual question, and it must
  fail loudly rather than skip when the Twilio credentials are absent —
  otherwise it measures nothing, which is the failure mode `triage_eval` already
  has without `--live`.
- **Leg B — no phone resolves to more than one owner_ref.** Group live
  `owner_profile` by `phone` and assert at most one distinct non-empty
  `owner_ref` per number, ignoring the empty-phone group. Red today on
  `+16282721282`. This is the leg that turns finding 3 from invisible to
  one-line, and it goes red the moment a claim ambiguates the owner's number.
- **Leg C — the resolvable rows fit inside the query window.** Assert that for
  every phone, the count of `owner_profile` rows is below the hook's limit, or
  that the ref-bearing row is within the top N by `updated`. This is the leg
  that would have caught finding 3 before it was one sign-in away.
- **Leg D — outbound is actually arriving.** Assert no recipient has a 100%
  undelivered rate over the last 7 days. Red today on `+17868735256` with 15 of
  15 at error 30034.

Legs A and D need Twilio read credentials; B and C need only
`ANTICIPY_SERVICE_TOKEN` and the backend URL. All four are read-only.

A note on Law 1: none of these predicates decide what words mean. They count
rows and compare identifiers, which is exactly the deterministic-gate use the
laws permit. No fix proposed in this document adds a pattern match over message
text.

## Appendix — one refuted claim, recorded so it is not re-raised

An earlier pass reported that `brain/conversation.py:1494-1502` (`_references`,
a four-letter-word set intersection) vetoes a correct model `pending_id` and
re-asks the menu, and filed it as a Law 1 violation breaking user replies. The
primitive is real and the line numbers are right, but the failure does not
reproduce on the live path: `brain/conversation.py:444-449` sets
`text_for_guard = None` when her last line in the thread ended in a question
mark, so the intersection never runs on an answer to her own question. The
reported failure state only appears with an empty thread, which production does
not have — replies are written back as `anticipy_text` (`brain/worker.py:2943`)
and proactive asks as `anticipy_says` (`brain/worker.py:2454-2455`). `_references` is
already recorded as item 31 in `research/2026-08-24-law1-audit.md:160` (which cites it under that
file's own older line numbering, `:1459-1468`). It is
worth revisiting on its own merits; it is not why anyone's reply failed.
