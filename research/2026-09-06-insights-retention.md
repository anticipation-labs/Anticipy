# Insights — what Anticipy may truthfully say about itself

2026-09-06. Written before the code, because every number on this screen is a
claim and the wrong ones are lies (law 4).

The ask was Wispr Flow's insights screen, aimed at Anticipy: hours recorded,
things caught, a streak, recurring-meeting recaps, a peek card on Home that
opens into a full page. Four readers inventoried what the codebase can actually
count, three designers proposed metric sets from different angles, and three
critics — honesty, manipulation, laws — went at all of it.

**Three of the asked-for metrics did not survive. That is the useful part of
this document.**

---

## 1. What was killed, and why

### Recurring-meeting recaps — killed on law 1

Clustering conversations into "your Tuesday standup" needs the client to decide
two conversations are the same meeting. The only available signal is
`brain/segmenter.py`'s `proper_nouns()`, which is a bare
`/\b[A-Z][a-zA-Z]{2,}\b/` — a capitalisation regex. Deciding what a
conversation *is* from overlapping capitalised words is precisely the thing law
1 forbids, and it would be wrong the first time somebody's colleague is called
Mark.

### A consecutive-day streak — killed on honesty, not on taste

All three designers independently refused it. The reason is specific to this
product: **the ears went deaf for 30 hours and nothing noticed**, which is why
`overnight/are_the_ears_live.py` exists. A streak breaks on that outage and
bills it to the person, who did nothing wrong. A number that falls for the
app's own failure has no place on a screen whose whole proposition is trust.

Days used — monotone, never falls — is kept instead.

### "Hours recorded" — killed as written, kept in an honest form

There is no listening-duration column anywhere in `migration/d1/schema.sql`. The
only microphone-on clock is `ListenTally.listeningSeconds`, folded from a
256 KB two-file journal that dies on reinstall and is device-local. Worse, the
fold carries an uncovered defect: `ListenTally.swift:249-268` sets `openedAt` on
`.sessionStarted` **without closing an open span**, so a session killed without a
stop silently discards its whole duration.

And the server-side substitute is empty today: all 137 stored production rows
carry the same postmark in all three capture columns, so a sum over
`capture_ended_at − capture_started_at` is zero.

So: no hours on this screen until `GET /me/insights` exists with a live leg.
Never labelled "hours recorded".

### A weekday-shape chart — killed on creep

Every other tile counts what Anticipy **did**. A chart of which weekdays you
talk profiles what you **are**. An always-on microphone reporting your weekly
rhythm back to you is the sentence that makes somebody turn it off.

### An unlock countdown — killed as an invented number

Wispr's "472 more to unlock your stats" is a good mechanic and it is not
available to us honestly: nobody has measured where a real owner's first
finished errand lands, so any number in that sentence is a guess dressed as a
milestone. The cold start gates on **the set being empty**, never on a threshold
being crossed.

---

## 2. The fact that decides the whole design

**The brain is capped to one owner.** `migration/workers/brain/src/index.ts`
serves `ANTICIPY_MAX_OWNER_WORKERS` plus an allowlist, and the 2026-09-05 audit
records cap = 1 with only the e2e probe allowlisted.

So on every real phone that exists today, every transcript row carries
`decision = ""` and `goal = ""`. Any headline derived from the brain's verdicts
renders as its cold-start apology — "None judged yet" — for every real owner.

That is why the headline is **days**, which reads timestamps the phone itself
wrote and is immune to the cap.

---

## 3. What ships

### The peek card

Replaces `sectionHeader("Done")` in `ContentView.swift`, with `DoneDeck`
unchanged beneath it, inheriting the `if !finishedShown.isEmpty` guard so the
card is absent rather than empty.

    You've talked to Anticipy on 43 days.
    312 of 12,431 lines turned into something.

Non-negotiable, from the manipulation critique: no count-up animation, no badge,
no notification, no milestone, and no number that can fall.

### The page

| Metric | Basis | Note |
|---|---|---|
| Days you've talked | distinct local days over capture stamps | monotone; the headline |
| Things picked up | `goal != ""` | **not** `decision="act"` — quiet work is stamped ignore+goal |
| Not yet judged | `decision = ""` | mandatory companion; today this is most rows |
| Errands finished | jobs `status="done"` | needs a jobs pager with totals |
| Asked before acting | events `kind="anticipy_says" && decision="ask"` | monotone |
| Conversations | segments | same cap caveat as the catch metrics |
| How it reached me | `events.source` | omit the pendant lane rather than print 0% |

### Two rules that are not negotiable

1. **Never print 0. Name the empty set instead.** An absent card says "not yet";
   a card reading 0 says "it doesn't work".
2. **A count over the newest page is never presented as a lifetime.** This is
   the likeliest way this feature ships a lie. Lifetime counts come from
   `totalItems` on a filtered count request, never from `items.count`.

### The cold start: a closed set of four

Nothing heard → heard but nothing judged → judged but nothing finished →
steady. Four cases rather than "show whatever is non-empty", because a closed
enum is the shape a suite can walk exhaustively.

State two is where **every real owner lives today**. It is simultaneously the
genuinely new owner and the owner the capped fleet is not serving, the phone
cannot tell them apart, and the honest sentence is the same for both.

---

## 4. Defects this research found in shipped code

Three, none of them in the new feature:

1. `ListenTally.swift:249-268` — `.sessionStarted` does not close an open span,
   so an unstopped session's duration is discarded.
2. `AnticipyApp.swift:2827-2831` — `requestFreshRetry` calls `heard(…)`, posting
   a row the person never spoke or typed. Every Retry tap over-counts "typed".
3. `AnticipyBackend.swift:921-941` — `fetchEventPage` never sends `fields=`,
   though the Worker honours it, so a day-walk drags every transcript's full
   text across the wire.

## 5. Law 3

Every number here is a `totalItems` claim about a live server, and the iOS
suites compile pure Foundation with no network. So this needs two seams:
`InsightsPolicy` (pure, walked by `run_insights_tests.sh`) and, before any of it
can be called proven, a live leg that recounts each printed figure by an
independent page-walk and diffs it against the count endpoint.

Until that leg exits 0, this screen is repo-green and law-3 unproven — and it is
a screen whose entire proposition is that its numbers are true.
