# Five signatures written by hand, before the planner exists

Written 2026-09-05, building the CapabilitySignature half of the two-hands
spike (`spike/two-hands/src/signature.ts`). The exercise was deliberate and the
order matters: write five real steps from the fifty moments as signatures BY
HAND, and see whether the shape survives contact, before a planner starts
emitting thousands of them. A shape flaw found here costs an afternoon. Found
after the ledger is keyed on it, it costs every rung anyone has earned.

Everything below is either measured against `docs/BRIEF.html` or is a claim I
am making with the reasoning attached. The five recipes are in
`spike/two-hands/tasks/five_recipe_signatures.json`, and every hash in that
file is recomputed by `test/signature.test.ts` from the same function the
router will use — a hand-typed hash in a fixture is a lie waiting to happen.

## The five

| moment | signature | side effect | hash |
|---|---|---|---|
| 43 "what do I have tomorrow?" | `read` / `calendar_event` / {time_min, time_max} | read | `ea27b5e3…` |
| 11 the 40-minute work call, "call moved to monday 3pm" | `update` / `calendar_event` / {event_id, start_time, end_time} | write | `3cb85bb9…` |
| 15 "fine, Thursday, the Thai place" | `create` / `calendar_event` / {title, start_time, end_time, location, attendees} | irreversible | `f0efcf03…` |
| 27 "Email the landlord that the heater's still broken." | `create` / `email_draft` / {to, subject, body} | write | `3e626fe9…` |
| 1 "I still owe Dana the insurance form" | `send` / `email` / {to, subject, body, attachments} | irreversible | `c5aac4ed…` |

Chosen to span the two axes that the router's rules actually branch on — the
verb and the effect channel — rather than to be five nice examples. Five reads
would have proved nothing about the half that can hurt: the rules only diverge
once a step writes. So: one read, two writes, two irreversibles; five distinct
hashes; a `create` that drafts and a `send` that cannot be taken back, sitting
next to each other on purpose.

## What I rejected, and why it is not a shortage of effort

I went through all fifty. **Six** are API-shaped work-and-life admin: 1, 11, 15,
27, 36 (the invite that arrives saying "wire $2,000" — a mailbox/calendar read
whose whole point is that she never acts on it) and 43. Two more, 46 and 47, are
about the CONNECTION surface rather than about a step. The other forty-two are
not browser work that we have not got to yet — most of them are not work at all.

- **No hand at all — seventeen of the fifty.** 2, 6, 7, 9, 12, 14, 17, 18,
  20–24, 40, 42, 44, 48. These are refusals, silences and manners. The product's
  personality lives here and neither hand touches it.
- **Her own memory, not an app.** 4, 16, 19, 33, 34, 35, 37, 38, 45. "What's the
  wifi at the cabin again?" is answered from what she heard in July, and the
  brief says so in as many words: the internet is never consulted for your own
  life. A notes connector would be a solution with no moment behind it — and
  that is the honest answer to why none of my five is a notes signature. **There
  is no notes moment in the fifty.** If someone connects Notion in week 3 it
  will be because Composio has a Notion connector, not because the brief asked.
- **Consumer sites with no consumer API, forever.** 5 (local trades), 8 (city
  parking permit), 25/26/28 (a restaurant, its deposit, its cancellation), 29
  (dentists), 30, 32, 41. These stay on the browser hand and the second hand
  should never be offered for them.
- **Messaging, which looks API-shaped and is not.** 39, "text Laura I'm running
  late". The owner's own SMS/iMessage identity has no third-party API; a
  connector could send *as some service*, which is a different act from the one
  he asked for. What IS API-shaped in 39 is the disambiguation sub-step — read
  the 9:00 event, see which Laura is on it — which means one moment splits
  across both hands. That is a planner problem, not a signature problem, but it
  is the first evidence that a "moment" and a "step" are not the same unit.

**Moment 47 is the sharp one and it should go to whoever writes
`onboarding.ts`.** The brief has her notice her own friction — "i keep doing
this one by hand — hook up the airline account and it's instant next time?" —
and the app in the brief's own example is an AIRLINE, which has no consumer API.
A nudge generated from friction counting alone will offer an OAuth connect link
for an app that has none. Connecting an airline means saving a login, which is a
different promise with a different risk (moment 48: she never touches a password
field herself). The nudge surface has to be able to say "there is nothing to
connect here" — and it cannot learn that from a hardcoded list of app names
either, so the answer is probably provider `search(connectedOnly: false)`
returning nothing, which is a fact rather than a guess.

## What the five taught me about the shape

**1. Key-set sensitivity is load-bearing, and it is also the biggest risk.**
Moment 15 vindicated it. `create`/`calendar_event`/{title, start, end, location}
and the same thing plus `attendees` SHOULD be different capabilities: the second
one emails three humans, the first one does not. The hash agrees, for free,
because the key set differs.

The same mechanism does something dumb one line later: {to, subject, body} and
{to, subject, body, cc} split into two rungs, and a cc is not a different
capability. One rule resolves both, and it belongs in the planner's prompt, not
in this file:

> emit the keys the step REQUIRES, not the keys you happen to have values for.

If the planner writes `cc: null` because its JSON template has a cc field, every
optional field it owns doubles the number of rungs and shadow mode never closes.
This is the single highest-risk thing the exercise found, it is invisible until
the ledger stops promoting, and there is no test in this module that can catch
it — the shape is right, the planner is what has to be disciplined.

**2. `object` is a free string, so the hash is only as stable as the planner's
word for the thing.** `calendar_event`, `event` and `meeting` are three rungs.
I normalise ORTHOGRAPHY (case, spacing, `_` vs `-` vs space) because that is
plumbing — nobody claims `Calendar Event` and `calendar_event` mean different
things. I did NOT add a synonym table, and the absence is pinned by a test:
`event` and `calendar_event` stay different. A table mapping one planner word to
another is a word list deciding that two things MEAN the same capability, which
is precisely what law 1 keeps out of this repo.

The cost is real: a planner that renames its own object between releases
silently orphans every rung it earned. The cheap instrument for it is a counting
gate, not a rule — distinct `object` values per (app, verb) over a week. If that
number climbs, the planner is drifting, and a human decides what to do. Counting
is measuring, and measuring is legal.

**3. `side_effect` is not in the hash, and that has a consequence the router
must handle.** Two steps can share a rung and differ in reversibility. Moment
11's `update`/`calendar_event`/{event_id, start_time, end_time} is reversible —
the brief offers undo, and undo is one more update with the old times. The
identical hash also covers moving an event that mails eight attendees a change
notice. **So the router must gate on `sig.side_effect` at decision time as well
as on the rung, never on the rung alone.** A promoted rung says "this tool has
worked here 27 times"; it does not say "this instance is safe to do unattended".
Putting `side_effect` in the key would fix it and break something worse — see
(4).

**4. Leaving `expected_effect` out of the key is right, and it is what makes the
ledger possible at all.** "Move the 2pm to 3pm" and "shorten the 2pm" are one
tool call with one argument shape. If the sentence were in the key, every
distinct sentence would be its own rung and `n` would never leave 1: nothing
would ever promote, and shadow mode would be permanent. The sentence is a
per-RUN judgement, and it is the only thing the verifier reads.

Which is why writing five of them by hand mattered. Moment 43's `expected_effect`
had to end up as *"every event on the calendars he has connected … and nothing
is created, changed or marked read"*, because the failure mode of an API read is
not an error — it is returning three events when he has four, from the one
calendar the connector could see, and reading like a complete answer. "The call
returned 200" is not a verifier. Every one of the five expected effects is a
sentence about the WORLD; none of them mentions a tool.

**5. The `SideEffect` enum cannot express moment 15, and I floored rather than
extended it.** Creating an event with attendees is a reversible RECORD and an
irreversible INVITATION in one call. I marked it `irreversible`, in the strict
direction, consistent with the rest of the repo. The price is that "dinner with
three friends" can never ride the unattended path however many clean runs it
accumulates. I do not think a fourth enum member is the answer — `expected_effect`
already carries the distinction for the verifier, and the router's job here is
to hold, which it now will.

**6. `app_hint` out of the hash does not mean the app is out of the ledger.**
`CapabilityStats` carries `app` as its own column. The hash names the
CAPABILITY; the stats row names the capability-on-this-app-with-this-hand. That
split is right: it is why the same "draft an email" record does not silently
carry over when the owner moves from Gmail to Fastmail, while the api_candidates
and the shadow-mode history keyed on the hash do.

**7. Types are stripped, not checked, so every guard is a runtime guard.**
`node --experimental-strip-types` deletes the annotations. A planner emitting
`{"verb": "purchase"}` would otherwise hash into a rung of its own and route as
though it were understood. `makeSignature` and `signatureHash` both check
membership in the contract's enums at run time, and reject a missing or blank
`expected_effect` — because a vacuous verifier collapses parity back to "did
both hands return the same bytes", which is exactly how a wrong browser run
certifies a wrong API run.

**8. Signatures come back frozen. Other agents should know.** `sig.inputs.cc =
"x"` throws a TypeError. Without the freeze it would change which capability the
step is while leaving `signature_hash` describing the old one, and the router
would read a rung earned by a step that never had the field. `withInputs(sig,
inputs)` is the legal path and re-hashes. `verifySignatureHash(sig)` exists for
anything that crossed a process boundary — a step reloaded from D1, a plan
handed back by a model — because a swapped hash is how an irreversible step
inherits a read step's track record.

## Where meaning is decided in this module

Nowhere. That is the claim, stated plainly so it can be attacked.

`signature.ts` decides two things. **Identity** — which two steps share a track
record — from a verb and an object the *planner* chose and a set of key names
the *planner* wrote. It compares them for equality after case-folding. It never
reads a human's sentence and it has no vocabulary of its own.

And **an effect-channel floor**, which is the one place that reads WHICH verb it
got: `read` floors at read, `pay` floors at irreversible, everything else floors
at write, applied through the contract's own `tightenSideEffect` so it can only
ever tighten. I am flagging it here rather than letting a reviewer find it,
because it is the thing in this file that looks most like the forbidden shape.
The case for it: it is a total function over a seven-member closed enum declared
in `contract.ts`, not over natural language; it is the seatbelt law 1 permits by
name (what does the plan TOUCH — does it send, pay, delete?); and it can only
make a step stricter. The failure it prevents is concrete: a planner emits
`{verb: "pay", side_effect: "read"}` — a real class of mistake, since the model
filling a JSON field is not the model that will be gated by it — and the
router's read path, which may run unattended with the laptop shut, executes a
payment. Moment 26 is one sentence about this: money always waits for your word.

`send` is deliberately floored at `write` and not at `irreversible`, and that is
the boundary I would not cross: whether a sent thing can be unsent is a property
of the APP, not of the verb, and deciding it here would be this module inventing
meaning it has no context for.

The only regexes in the module are `[\s_\-]+ → _` (orthography) and, in the
test, `^[0-9a-f]{40}$`.

## What is not done

- Nothing here is measured against a live vendor. Five signatures written by
  hand say the shape holds; they do not say Composio has a tool for any of them.
  That is the ten-read harness's job and it needs a key. Law 3 applies: this is
  repo-green, and repo-green is not done.
- `eventId` and `event_id` still hash apart. I stopped at case and separators
  because splitting camelCase needs a rule about mid-word capitals that I cannot
  justify from first principles ("URLTemplate"), and the real defence is one
  planner with one prompt. Written down so it is a known cost rather than a
  surprise.
- The planner-discipline rule in (1) — emit required keys, not populated ones —
  has no enforcement anywhere. It is the thing most likely to quietly stop the
  ledger from ever promoting, and when the planner exists it needs either a
  prompt line and an eval, or a gate leg counting rungs per (app, verb).

---

## Composio account, project and key (2026-09-05 evening)

Set up through the dashboard in the owner's own browser. **No credential in this
record**; the key went from the dashboard's copy button to `.env.local` (which
`.gitignore` covers at `.env.*`) without passing through a transcript.

| what | value |
|---|---|
| organization | `omar_workspace` (Omar Ebrahim), **Pro plan** — confirmed on Billing, "Current Plan" |
| project | **`anticipy_two_hands`** — created for this work, so the spike never shares a key with `omar_workspace_first_project` |
| API key | `COMPOSIO_API_KEY` in `.env.local`, shown once and stored |
| user_id | **`omar`**, in `.env.local` as `TWO_HANDS_OWNER` |

**A trap worth writing down: there were two Composio logins on this machine.**
Browser 1 was signed in as **Jose Lopez / `jose.colorstack_workspace`**, on the
Hobby plan, with no access to Omar's org — its org switcher offered only Jose's.
Creating the project there would have put Anticipy's integration in a personal
ColorStack workspace on the wrong plan, with a key nobody else could rotate.
Check the account chip at the bottom-left before creating anything.

That Hobby badge belongs to JOSE's org and to nothing else. It was briefly
reported here as the plan for this work, which was wrong: `omar_workspace` is on
**Pro**, and Pro is what the spike runs against — 100k tool calls plus the $29
usage credit, so a week-1 spike cannot stall on a free-tier cap.

**The key is live, verified against the real API rather than assumed:**
`POST /api/v3.1/tool_router/session` with `{"user_id":"omar"}` answered
**HTTP 201**, and the session's `tool_router_tools` are exactly the meta tools
the plan was chosen for — `COMPOSIO_SEARCH_TOOLS`,
`COMPOSIO_MANAGE_CONNECTIONS`, `COMPOSIO_MULTI_EXECUTE_TOOL`, plus
`COMPOSIO_GET_TOOL_SCHEMAS`, `COMPOSIO_REMOTE_WORKBENCH` and
`COMPOSIO_REMOTE_BASH_TOOL`.

**user_id is ours to choose, not something the dashboard issues.** The Users
page says so in as many words — "users appear here when your app creates
sessions" — and the three shown (`sarah_user`, `james_user`, `priya_user`) are
Composio's own illustration, not real accounts. It is `omar`, and every connect
link below was minted under it; a link minted under a different id produces an
empty connection list, which reads exactly like "he connected nothing".

**Connect links, generated under `user_id=omar`** (they are the owner's to
click — granting OAuth consent is not something Claude does):

    gmail           https://connect.composio.dev/link/lk_OSCPVWOiKvmc
    googlecalendar  https://connect.composio.dev/link/lk_B3-qQoTUaotK
    notion          https://connect.composio.dev/link/lk_ugrj2ErY407L
    slack           https://connect.composio.dev/link/lk_wqCrhtGjsF_2

Measured after generating them: **0 connected accounts** for `omar`.

**Gate state.** `tasks/run_ten.ts` now finds both keys and the owner id, and
refuses for exactly one remaining reason — six unfilled placeholders in
`tasks/ten_read_tasks.local.json` (`PERSON_A`, `PERSON_B`, `SENDER_INVOICE`,
`NOTION_TOPIC`, `SLACK_CHANNEL`, `SLACK_SEARCH`). It prints no table and no
numbers, which is the behaviour law 3 asks for: a run that could not happen is
not a pass.
