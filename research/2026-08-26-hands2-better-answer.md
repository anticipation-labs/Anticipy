# HANDS 2, re-decided — the ruling stands, its central sentence does not

**Date:** 2026-08-26 · **Tree:** `/Users/josegaelcruzlopez/Desktop/anticipy-omize`
· **Branch:** `jose_anticipy_system` · **Method:** read-only. No product code
touched, no ruling edited, no account created with any vendor.

**What this settles:** `docs/DECISIONS-2026-08-24.md` RULING 3 declined HANDS 2.
Four lenses were pointed at it with instructions to beat it, and every
decision-changing claim they produced was attacked by a separate agent. This is
the write-up of what survived.

**Provenance rule used throughout:** every external claim carries a URL, fetched
today unless dated otherwise. Where I am relying on my own knowledge rather than
a source, the sentence says so in those words.

---

## 1. The answer, in three sentences

**The ruling stands: nothing in the API ladder beats the browser for the errands
the fifty moments actually contain, and the four lenses did not find one.** But
one thing beats *both* the browser and the API for exactly one verb, and it is
not an API — it is the phone: `EventKit` already holds full calendar access in
the shipped app, writes nothing, and sits on a job channel the device polls every
three seconds. And the ruling's load-bearing sentence — *"no Gmail scope is
narrower than the whole mailbox"* — is **false as written and true as meant**, so
it must be struck and replaced the day it was refuted, or Law 4 guarantees the
next session re-derives it as fact.

---

## 2. The demand tally — what the product actually needs

Nobody had established this before arguing about scopes. It is the number that
should govern the rest, so it goes first. Method: all fifty moments read verbatim
out of `docs/BRIEF.html` (`div.ex50`, scene + "what she does"), each assigned one
primary bucket, cross-listed where a moment spans two. Status column from
`docs/FIFTY-MOMENTS-STATUS.md` (2026-08-24).

| Bucket | Count | Moments |
|---|---:|---|
| **No third-party service at all** (ears, judgment, memory, silence, SMS) | **29** | 2, 3, 4, 6, 7, 9, 10, 12, 13, 14, 15, 16, 17, 18, 20, 21, 22, 23, 24, 31, 34, 35, 38, 40, 42, 44, 45, 49, 50 |
| **Browser on a target with no usable third-party API** | **12** | 8, 19, 25, 26, 28, 30, 32, 33, 37, 41, 47, 48 |
| **Calendar READ — already served on-device by `EventKit`** | **3** | 36, 39, 43 (plus the read half of 11) |
| **Public-web research, no owner account** | **2** | 5, 29 |
| **The connect offer itself** | **1** | 46 |
| **API-shaped: a Google OAuth scope could serve it** | **3** | 1, 11, 27 (+ 31 implied) |

**The three numbers that decide the card:**

1. **3 of 50 (6%)** of the definition of done is API-shaped at all. Two verbs:
   *send an email as him* (moments 1, 11 item 1, 27) and *write or move a
   calendar event* (moment 11 item 2; moment 31 implies one — *"the confirmation
   screenshot, the receipt, **the calendar entry**"*).
2. **0 of 50** need Gmail READ. Not one moment asks her to read the inbox.
   Moment 12 is an explicit *refusal* to write from what she overheard; moment 36
   is a calendar invite she may quote and never obey. The nearest thing to a mail
   read in the fifty is moment 46's *offer*, and `design/day-zero.md` §2 already
   answers that with the supervised read, shipped in
   `extension/supervised_read.js` and `app/ios/Anticipy/Views/SupervisedReadView.swift`.
3. **12 of 50 (24%)** — four times the API-shaped surface — are browser-forever
   by the ladder's own rung 4: a city permit form (8), flowers (19), restaurant
   booking (25, 26, 28, 30), retail reorder (33), a salon (37), a receipt (41),
   an airline (47).

**Why this reframes everything.** RULING 3 spends its central paragraph proving
that `supervised_read.js`'s thirty-second lease beats the narrowest API **read**
scope. The product has **no read demand**. The paragraph wins an argument nobody
needed to have, and the sentence it wins it with is the one that is wrong.

**Two sub-findings that fall out of the tally and change what the card is:**

- **Moment 1 is not blocked on email.** `FIFTY-MOMENTS-STATUS.md` records it as a
  GAP because *"NO photo/image organ exists anywhere"* — the insurance-form photo,
  not the send. Building a mail adapter moves moment 1 zero distance.
- **Two of HANDS 2's five steps need no API whatsoever.** The card
  (`docs/BOARD-STATE-2026-08-24.md` §8) lists *"onboarding connect flow"* =
  moment 46, and *"repeated-chore detector → the suggestion text"* = moment 47.
  Moment 46's two organs are already written — `LifeContext.requestCalendar()`
  (`app/ios/Anticipy/LifeContext.swift:40`) and the supervised mail read — and the
  only thing missing is that `OnboardingView`'s `Step` enum is four beats
  (`welcome, howItWorks, mic, phone`, `OnboardingView.swift:73-79`) and neither
  offer is one of them. Moment 47's *"hook up the airline account"* is servable as
  a saved login the browser hand replays; airlines have no consumer API, so the
  API reading of that sentence is unbuildable. **Declining the API half of HANDS 2
  does not strand either moment.**

---

## 3. What RULING 3 got right, and what it got wrong

### Right, and unmoved by anything four lenses threw at it

- **Composio, Arcade Cloud and Pipedream Connect fail LOCAL-FIRST on custody and
  transit.** Nobody attacked this and it is not attackable: it is the product
  those companies sell.
  ([Composio managed auth](https://docs.composio.dev/docs/managed-authentication),
  [Arcade hosting](https://docs.arcade.dev/en/home/hosting-overview),
  [Pipedream Connect](https://pipedream.com/docs/connect/))
- **The 2026-05-21 Composio breach is the right kind of evidence** — the initial
  vector was one Gmail OAuth token, which is the exact asset rung 1 proposed to
  hand over.
- **A platform does not save the expensive half.** Bring-your-own OAuth app is
  required in production by all three, so Google verification stays ours either
  way.
- **"An API is always faster, cheaper and safer" is false**, and §2's tally makes
  the "no API at all" leg *four times* more load-bearing than the API-shaped one.
- **Restricted scopes stay refused.** `gmail.readonly` is Restricted on Google's
  own page, confirmed independently today. `extension/side_trip.js:581` — the
  verification-code lane that opens
  `mail.google.com/mail/u/0/#search/in%3Aanywhere+newer_than%3A1h` on a message
  the owner has *not* opened — is the one genuine mail read in the tree, and only
  a Restricted scope would serve it. The browser stays the only hand there.

### Wrong, plainly, and it is the sentence the ruling leans on

> *"no Gmail scope is narrower than the whole mailbox"*

**This is false.** Google's own scopes page — the same URL
`research/2026-08-24-api-ladder.md` §4(a) already cited — partitions Gmail scopes
under three headings the research reported only one third of. I fetched it today
with a "reproduce the tables verbatim" prompt and got:

- **Non-sensitive** (*"only require basic OAuth App Verification"*):
  `gmail.addons.current.action.compose`, `gmail.addons.current.message.action`,
  `gmail.labels`.
- **Sensitive** (*"require additional OAuth App Verification"*):
  `gmail.addons.current.message.metadata`, `gmail.addons.current.message.readonly`
  (*"View your email messages when the add-on is running"*), `gmail.send`.
- **Restricted** (*"provide wide access… require restricted scope OAuth App
  Verification"*): `mail.google.com`, `gmail.readonly`, `gmail.compose`,
  `gmail.insert`, `gmail.modify`, `gmail.metadata`, `gmail.settings.basic`,
  `gmail.settings.sharing`.

([developers.google.com/workspace/gmail/api/auth/scopes](https://developers.google.com/workspace/gmail/api/auth/scopes))

Google itself encodes the narrowing the ruling denies: the *same data* is
**Restricted** at mailbox width (`gmail.metadata`) and **Sensitive** at
one-open-message width (`gmail.addons.current.message.metadata`).

### And why the verdict survives it anyway — the refutation of the refutation

The narrow scopes do not reach the REST API. I checked the reference page for the
one method that matters to this product:

> `users.messages.send` — authorization scopes: `https://mail.google.com/`,
> `gmail.modify`, `gmail.compose`, `gmail.send`. **`gmail.addons.current.action.compose`
> is not among them.**
> ([users.messages.send](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/send))

A parallel agent confirmed the same shape on `users.messages.get`,
`users.messages.list` and `users.threads.get`: all four accept only
`mail.google.com`, `gmail.modify`, `gmail.readonly`, `gmail.metadata` — every one
of them Restricted, every one of them whole-mailbox. The `addons.current.*`
scopes function only inside a Workspace Add-on invocation, against a per-message
token Google mints and pushes to the add-on
([event objects](https://developers.google.com/workspace/add-ons/concepts/event-objects)),
and that trigger fires only *"when the user opens a Gmail message (with the
add-on open)"*
([extending the message UI](https://developers.google.com/workspace/add-ons/gmail/extending-message-ui)).
An ambient assistant that needs the owner to be sitting in Gmail with a panel
open is not an ambient assistant.

**So the accurate sentence, which the owner should paste over the false one:**

> *No Gmail scope reachable by a server-side REST client is narrower than the
> whole mailbox. Google does publish six narrower scopes — three Non-sensitive,
> three Sensitive — but the three that read a message work only inside a
> Workspace Add-on, invoked while the owner has that message open, and no Gmail
> REST method accepts them. `supervised_read.js`'s thirty-second lease is
> therefore narrower than any read scope this architecture can use.*

Same correction owed to `research/2026-08-24-api-ladder.md` §4(a)'s *"Gmail has
no scope for 'the subject lines of this one thread'"*.

**Three code sites need no change.** `extension/supervised_read.js:47-52`,
`app/ios/Anticipy/ContextGrant.swift:32-45` and `design/day-zero.md:122-124, :340`
each assert only that `gmail.readonly` is Restricted, which is true and was
re-verified today. The false generalisation lives in exactly two prose files.

### Missed, and it changes the forward prescription

**"If this is ever revisited it is native OAuth, `calendar.events` first" is the
wrong first rung.** The calendar half of moment 11 needs no OAuth at all:

- `app/ios/Anticipy/LifeContext.swift:41-47` already calls
  `requestFullAccessToEvents()` (iOS 17+) / `requestAccess(to: .event)` — the app
  **holds write permission today** and the only reader, `upcomingEvents()` at
  `:62-77`, never writes. Apple's own docs: write-only access *"lets your app
  create new events but doesn't let it read any events"*, and *"your app can't
  request read-only access"* — full access is what reading costs, and it includes
  the write ([accessing the event store](https://developer.apple.com/documentation/eventkit/accessing-the-event-store)).
- The shipped permission string already promises the write:
  `NSCalendarsFullAccessUsageDescription` — *"never puts anything in your calendar
  **unless you ask her to**"* (`app/ios/Anticipy/Info.plist`). The consent the
  owner has already given anticipates exactly this errand.
- **And the transport exists.** `AnticipyApp.swift:486-494` polls the server every
  three seconds; `:521-523` records why that survives a locked screen — *"the app
  keeps running while it listens (background audio), so a local notification from
  here reaches a locked screen without a push server."* The phone already reads
  job rows (`fetchJobs`) and writes job status back (`setJobFields`,
  `AnticipyApp.swift:945, 967, 1827-1907`) with in-flight and read-after-write
  guards already hardened.

The ladder's own rung 2 says calendar *reads* already have a better hand than any
API. Nobody noticed the same is true of calendar *writes*, on a permission that is
already granted, over a channel that already runs.

---

## 4. The recommended shape, and the trade

**Keep the verdict. Do not build the API half of HANDS 2. Build one device-lane
hand instead, and name it something other than HANDS 2 so the card's four other
steps are not smuggled in with it.**

### Rung 0 — new, and it beats both incumbents: the phone as a hand

Scope: **calendar write and calendar edit only** (moments 11, 31). Shape: the
worker queues a job with a device lane; the phone picks it up on the poll it
already runs; `EKEventStore.save` / `remove` executes it; the phone writes status
back on the channel it already writes status back on. Undo is an
`EKEvent` removal by identifier, which is what moment 11's *"(undo)"* literally
asks for.

What it costs against `design/LOCAL-FIRST.md`: **nothing — it improves the
posture.** No refresh token exists to hold, so §3's custody bill (*"the larger half
of this card"*) is zero. No Google verification, no CASA, no vendor in the trust
path, and the only thing that travels is the conclusion — *"put dinner Thursday
7pm"* — which is rule 3 exactly. The law's own scoreboard line for browser hands,
*"already the most local-first part of the system"*, applies here more strongly:
the browser hand is local to the Mac; this one is local to the device that holds
the calendar.

**The trade, named honestly — three costs, none of them zero:**

1. **Availability for custody.** The hand exists only while the phone is alive and
   the app resident. That is the same failure shape as the Chrome hand, which the
   product already models and shows in the status strip (*"Waiting for your
   browser"*), so the vocabulary exists — but a second such hand doubles the
   surface where an errand can sit waiting on a device.
2. **It reaches Google only if Google is on the phone.** `EventKit` writes into
   whichever account the device holds. A cold stranger whose Google Calendar is
   not configured in iOS Settings gets a write that never reaches
   calendar.google.com. **Unverified — this needs one device test, not more
   prose.**
3. **The gate must move with the hand, and this is the real risk.** The
   confirmation gate and the effect-journal-before-every-click discipline live
   server-side and in `extension/agent_loop.js`. A device execution lane that does
   not route through the same gate is not a new hand, it is a hole in the gate.
   Moments 25/26 (*"money always waits"*) and 48 (*"physically off-limits"*) are
   gate properties, and duplicating a safety mechanism is how a second one drifts.
   **This is the reason rung 0 is scoped to calendar writes and nothing else** —
   a calendar event is reversible, unpriced, and sends nothing to another human.

### Rung 1 — `gmail.send`, and still not now

If the mail half is ever built it is `gmail.send`: **Sensitive**, *"Send email on
your behalf"*, no read privilege of any kind, verification *"typically 3-5
business days"*, brand verification required first, demo video required, and the
page says nothing about CASA
([sensitive scope verification](https://developers.google.com/identity/protocols/oauth2/production-readiness/sensitive-scope-verification),
last updated 2026-08-19). That is the honest price and it is bounded.

It is still declined today, for a reason that is not about scopes: §3's custody
bill is unpaid. A `gmail.send` refresh token is durable, and the five gaps stand —
no encryption at rest, seven unencrypted backups on the same volume, one
server-wide `ANTICIPY_SERVICE_TOKEN` as the whole wall, a volume that has already
taken production down, and `agent_key.pb.js` already shipping owner PII to a
paired browser. Three of 50 moments do not buy that.

**Alternatives to `gmail.send` tried and rejected, so nobody re-tries them:**

- **SMTP with a Google app password.** Still available in 2026 — *"you need
  2-Step Verification"*, *"a 16-digit passcode that gives a less secure app or
  device permission to access your Google Account"*, and Google's own page says
  *"app passwords aren't recommended and are unnecessary in most cases"*
  ([support.google.com/accounts/answer/185833](https://support.google.com/accounts/answer/185833)).
  It is **strictly worse than `gmail.send`**: a bearer credential to the account
  rather than a send-only scope, revoked whenever the owner changes their
  password, and unavailable on Advanced Protection or many org accounts.
- **Send on his behalf from Anticipy's own domain** (a transactional sender with
  `Reply-To:` him). Zero owner-credential custody, and it breaks moment 27's
  actual promise — the landlord must receive it *from him*, in his voice — and
  buys a DMARC/deliverability problem instead.
- **`MFMailComposeViewController` on the phone.** Zero custody, and Apple is
  explicit that the app cannot send: *"The composition interface doesn't guarantee
  the delivery of your email message; it only lets you construct the initial
  message and present it for user approval"*
  ([MFMailComposeViewController](https://developer.apple.com/documentation/messageui/mfmailcomposeviewcontroller)).
  That *matches* moment 27's contract but **moves the yes** from an SMS reply to a
  tap inside the app with Apple Mail configured (`canSendMail()`), which a Gmail-app
  user does not have. A real option for the tap-the-card path; not a replacement
  for "reply *send it*".
- **`chrome.identity` in the extension.** Forbidden by the card's own last step
  (*"tokens live server-side, never in the app or the extension"*) and by
  `day-zero.md` §2.
- **Nango, self-hosted.** Unchanged from api-ladder §5: the re-open candidate, not
  today's answer.

### Rungs 2-4, unchanged

Calendar/contacts reads stay on-device. Restricted scopes stay refused. Airlines,
OpenTable, utilities, government forms and Slack history stay browser-forever —
and per §2 that is 24% of the definition of done, four times the API-shaped
surface.

---

## 5. What would change this decision later

Checkable triggers, each one a fact somebody can go and get. Not vibes.

1. **A Gmail REST read method starts accepting a sub-mailbox scope.** The precise
   check: re-fetch
   `developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/get`
   and look for any scope not in {`mail.google.com`, `gmail.modify`,
   `gmail.readonly`, `gmail.metadata`}. Until that list changes, the corrected
   sentence in §3 holds. **This is the only trigger that would reopen the read
   half at all.**
2. **The custody bill gets paid for another reason.** If envelope encryption, an
   off-volume backup path and a per-provider revoke endpoint ship because
   something else needed them, `gmail.send` becomes a 3-5 day verification and
   ~300 lines. Re-price the card that day, not before.
3. **The demand tally changes.** Re-run §2 against `docs/BRIEF.html` after any
   Brief edit. If API-shaped moments pass **10 of 50**, or if a mailbox *read*
   moment ever appears, this document is stale and the card reopens.
4. **`done_gate` leg 6 goes green with a real stranger.** A credential custodian
   with an unfinished stranger path is the wrong order — api-ladder §6's own kill
   criterion. Nothing in HANDS 2 should ship before leg 6.
5. **Rung 0 fails its device test.** If `EventKit` writes cannot reach a cold
   stranger's Google Calendar on an unmodified phone, rung 0 collapses and
   `calendar.events` (or `calendar.app.created`) comes back as the only hand for
   moment 11 — at which point §6's question 1 must be answered first.
6. **The service count passes ~15 and they are all API-having.** Re-open Nango
   (api-ladder §5). Nothing in the fifty moments points that way today.

---

## 6. Handed back

**For the owner, and only the owner:**

1. **Amend RULING 3** — strike *"no Gmail scope is narrower than the whole
   mailbox"*, paste the corrected sentence from §3. Keep the verdict. Under Law 4
   an uncorrected false premise in a decision file is re-derived as fact; this one
   is already two documents deep.
2. **Same correction to `research/2026-08-24-api-ladder.md` §4(a).**
3. **Strike "`calendar.events` first" from RULING 3's closing paragraph**, per §3
   and §4. If a first rung is named at all it is `gmail.send`, and rung 0 comes
   before it.
4. **Decide whether rung 0 is HANDS 2 or a new card.** My recommendation is a new
   card: HANDS 2's five steps include two that need no API (moments 46, 47) and
   three that do, and leaving them bundled is how the API half gets built by
   accident.

**Open questions, with who can close them and what it costs:**

| Question | Who | Cost |
|---|---|---|
| Do `EventKit` writes reach a stranger's Google Calendar on an unmodified phone? | whoever holds the test device | one write, five minutes |
| Are `calendar.app.created` / `calendar.events.owned` / `calendar.events` sensitive or restricted? Still open since api-ladder §7 opened it on 2026-08-24 | anyone with the Cloud console | one page visit — the Data Access page labels them automatically ([support.google.com/cloud/answer/9110914](https://support.google.com/cloud/answer/9110914)); Google's Calendar auth page publishes no classification, confirmed today ([calendar/api/auth](https://developers.google.com/workspace/calendar/api/auth)) |
| Current CASA assessor pricing — the repo's `~$540-$4,500+/yr` is of unknown vintage | someone willing to request a quote | unknown; nobody has one |
| Does moment 31's *"the calendar entry"* mean she writes one, or attaches one? | Omar | one sentence |
| Should a device execution lane exist at all, given the gate lives server-side? | Omar | this is the architecture question rung 0 turns on |

**What I could not determine, stated rather than smoothed over:**

- Whether any 2026 change to Google's verification or CASA regime has landed. The
  WebSearch budget for this session was exhausted before I could look, so the
  policy claims here come from primary Google pages fetched directly (the
  sensitive-scope page carries *"Last updated 2026-08-19"*), not from news.
- Apple's `EKEventStore.save(_:span:commit:)` reference page would not render for
  a fetcher (JS-only); the write/full-access facts above come from Apple's
  "Accessing the event store" article, which did render, plus the repo's own code.
  **My own knowledge, flagged as such:** that a saved `EKEvent` syncs to whichever
  account owns its calendar — that is exactly what the device test in §5 checks.
- I did not re-verify the Composio breach numbers against Composio's primary
  disclosure; api-ladder §7 already flags that gap and it is unchanged.

**One thing worth carrying forward regardless of this card.** api-ladder §3 says
*"becoming a credential custodian is the larger half of this card."* That is true
of native per-service OAuth and false as a general law: a Workspace Add-on gets
short-lived per-invocation tokens pushed to it and stores no refresh token
([alternate runtimes](https://developers.google.com/workspace/add-ons/guides/alternate-runtimes)),
and rung 0 stores no token at all. **"An API route requires custody" is not a law;
"native per-service OAuth requires custody" is.** Whoever prices the next
integration should start from the narrower sentence.
