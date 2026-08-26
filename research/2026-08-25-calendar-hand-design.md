# The calendar hand: what decided its shape

**Status:** being built (workflow `device-calendar-hand`). This file is the
ruling the build is working from, written the day it was made — Law 4.

## What this is

Rung 0 of `research/2026-08-26-hands2-better-answer.md`. The HANDS 2 API ladder
stays declined. Instead the phone becomes a hand for exactly one verb: calendar
write and edit. The worker queues on a device lane, the phone picks it up on the
jobs poll it already runs, `EKEventStore` executes, status goes back on the
existing channel.

Nothing is built that did not already exist. Verified 2026-08-25:

| Claim | Check | Result |
|---|---|---|
| Full calendar access already granted | `LifeContext.swift:40` `requestFullAccessToEvents` | yes |
| Nothing writes to the calendar today | `grep -rn "EKEvent(" app/ios/` | **0** |
| The promise already shipped | `Info.plist` `NSCalendarsFullAccessUsageDescription` | yes |

## The constraint that decided the design

SHELF 2 (`docs/superpowers/specs/2026-08-24-shelf-2-redesign.md`) binds:

> An act is admissible only when undoing it requires nothing the act produced.

and it excludes, by name, the shape a naive calendar write has:

> a draft created in his Gmail account is not admitted. The effect left into a
> third-party system and the undo needs a message id the provider returned — a
> hole in the recipe, filled by the counterparty, after the act.

`EKEvent.eventIdentifier` **is assigned by EventKit on save.** So "remove the
event whose identifier EventKit gave us" is precisely the excluded shape and
fails admissibility. Not by analogy — by the same mechanism.

**Ruling: mint our own id before the act and carry it on the event**, so the
undo resolves from `minted_by_us` alone and never needs anything EventKit
returned. Precedent is already in the spec: `brain/workflow.py new_plan` writes
`plan_id = plan_id or str(uuid.uuid4())` — the id exists before anything is
stored.

If that cannot be made to work, the act is **not** admissible for act-and-tell
and must be held for approval instead. A held calendar write that is correct
beats an unheld one that is clever.

## Where the id may NOT ride, and this is not a detail

The obvious home for a minted id is `EKEvent.notes`. **It is not available**, and
the reason is a promise already on the App Store in `Info.plist`:

> She never reads **the notes** or the invitees

An undo that searches `notes` for our id is reading the notes of the owner's
events. That falsifies a shipped privacy string — the same class of miss as the
Bluetooth string that still named Deepgram (`945672b2`), caught only because
`no_vendor_ears.py` was extended to read `.plist`.

So: `EKEvent.url`, or a local mint-time map from our id to the fields needed to
find the event again. Both keep the undo inside what we wrote ourselves.

## The one thing prose cannot settle

**Does an `EKEvent` written locally reach calendar.google.com when the Google
account is configured in iOS Settings, and does the field carrying our id
survive the CalDAV round trip?**

EventKit writes into whichever account the device holds. A stranger with no
Google Calendar configured gets a write that never leaves the phone. This is
**unverified** and is the single most important unknown in the card. It needs
one device test, not more argument. The phone is on build 89 and connected.

## What is deliberately NOT being built

Not mail, not reminders, not contacts, and **not a general device execution
lane** with a calendar case inside it. The research named why:

> a device execution lane that does not route through the same gate is not a new
> hand, it is a hole in the gate.

The confirmation gate and the intent journal live server-side and in
`extension/agent_loop.js`. A device lane routes through *that*, unchanged. A
second approval check written for the phone is the hole, even on the day it
agrees with the first.

## The gate fires before the lane is consulted — verified 2026-08-25

`brain/anticipy_core.py:585 is_consequential` settles the safety question
structurally, and better than the design above assumed:

```
if touches == "world":
    return True
if explicit:
    return False
```

The `world` check sits **above** the `explicit` escape. So a calendar write is
held for approval even when the owner asked for it in so many words. Held is
not a thing the device lane can opt out of, because the lane is chosen after
the gate has already decided.

Two consequences worth stating plainly:

**1. The device lane cannot be a hole in the gate by construction.** It selects
the executor *after* approval, not the requirement for one. The failure the
research warned about — a second approval check written for the phone — is
therefore not merely discouraged, it is unnecessary. Anything that looks like
one in the diff is the bug.

**2. SHELF 2 admissibility is not on the critical path.** Admissibility governs
acting *unheld*. A held write does not need it. The minted id is still worth
building for moment 11's "(undo)", but it is a convenience for the owner rather
than the thing that makes the act legal — and that ordering matters, because a
minted id built as a *permission* is one refactor away from someone deciding
the approval is redundant.

**3. `touches` is also the correct lane signal.** It is the model's declaration,
made at triage, and the comment above it records that the two previous attempts
at this question — a verb list, then a calculator-sniff — were both
"pattern-matching wearing different coats". Routing the lane on `touches` plus
the plan's declared effect is Law 1 compliant. Routing it on the word
"calendar" would not be.
