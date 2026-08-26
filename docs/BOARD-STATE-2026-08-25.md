# The board, measured — 2026-08-25

Supersedes `docs/BOARD-STATE-2026-08-24.md`, which was read off
anticipy.ai/internal directly and is now **stale by 112 commits**.

**The board itself could not be updated today.** `anticipy.ai/internal` does not
serve the board any more:

| Host | Path | Result |
|---|---|---|
| www.anticipy.ai | `/internal` | 404 (PocketBase body), 401 to unauthenticated curl |
| backend-production-61e0a.up.railway.app | `/internal` | 404 |

The board was never in this repo, so there is nothing here to edit either. This
file is the durable record until somebody says where the board moved.

## What changed under the site while nobody was looking

`anticipy.ai` used to be served by PocketBase out of `backend/pb_public/`. It is
now a **Next.js marketing site** (`__variable_*` classes, `/pre-orders/purchase`,
`/engine`, `/terms`, `/refund`). Consequences, measured:

| Path | anticipy.ai | railway backend |
|---|---|---|
| `/setup.html` | **404** | 200 |
| `/privacy.html` | **404** | 200 |
| `/anticipy-extension.zip` | 200 | 200 |

Nothing in `app/ios/`, `extension/` or the gates points at
`anticipy.ai/setup.html`, so **no shipped path is broken by this** — the one
`anticipy.ai` string in `extension/agent_loop.js:53` is an OpenRouter
`HTTP-Referer` header, not an API base. The new site serves its own `/privacy`
(200), so the privacy policy still resolves for the App Store.

**But note what this means for the gates.** Both LIVE legs of
`stranger_gate.py` probe `backend-production-61e0a.up.railway.app`, not the
public domain. The gate is green while the domain a stranger would actually type
serves a different application. That is not a false pass today, because the app
sends people to the backend host — but the gate cannot see the public domain at
all, and it reads as if it can.

## Card status, measured today

Gates: `done_gate` 5/6 · `stranger_gate` **9/9** · `tejas_gate` fails leg 6 ·
`tape_gate` red on purpose (Law 2 working).

| # | Card | Board says | Actually |
|---|---|---|---|
| 12 | EARS | To do | **DONE** — live rows from `iphone-b87`; `are_the_ears_live.py` watches for the 30-hour silence |
| 11 | SORTER | To do | **DONE** — `done_gate` leg 3 |
| 10 | LIBRARY | To do | **DONE** — incl. `valid_until` + `expire_stale()` |
| 6 | MOUTH | To do 0/5 | **DONE** — `done_gate` leg 4; the two-profile bug that ate replies is fixed |
| 9 | HANDS 1 | To do 0/4 | **DONE** — intent journalled before every click |
| 5 | SHELF 2 | To do | **DONE as spec** — `docs/superpowers/specs/2026-08-24-shelf-2-redesign.md`; exactly one admitted act |
| 4 | PHONE-AS-PENDANT | To do | **DONE** — board's "battery NOT STARTED" is stale (`ListenTally.swift:105`), so is "which ear" (`HeardGroup.swift:129`) |
| 8 | HANDS 2 | To do 0/5 | **ANSWERED BY DECLINING** — `research/2026-08-26-hands2-better-answer.md`. 41/50 moments need no service, 0/50 need Gmail read. Rung 0 (phone as calendar hand) building |
| 7 | HANDS 3 | To do 0/5 | **BLOCKED** on HANDS 2's ruling |
| 1 | Read the Brief | In progress 0/3 | Jose's |
| 2 | 0 · READ ME | To do | Jose's + Omar's |
| 3 | WIRE IT ALL | To do 0/5 | **OPEN** — this is `done_gate` leg 6, the only failing leg |
| — | macOS meeting recorder | new | started — `app/macos/` exists |
| — | iOS phone/FaceTime recorder | new | started — `CallPresencePolicy.swift` exists |

## The one conflict that is not a status, it is a contradiction

`tejas_gate` leg 6 demands the speaker tagger be linked:
`packageProductDependencies` is an empty list, so `speaker` stays empty on every
event while a 25 MB model ships in every build.

**Linking it is what killed builds 76-80** — those builds delivered zero rows;
the phone went deaf. So one gate demands the thing another failure recorded as
fatal. Not resolved, and not safe to simply switch on. Whoever takes it needs
the sherpa-onnx crash addressed first, not the gate silenced.

## The honest summary

Seven of twelve cards are complete in code. One is answered by deciding not to
build it. Four are open, two of those being Jose's to tick.

By the Brief's own definition none of it counts: only lived days declare done,
and no cold stranger has lived a week. That is `done_gate` leg 6 and it is the
only leg left. Everything a machine can check ahead of that week is green.

**The machine is built and every part has been proven to work. Nobody has lived
with it yet.**
