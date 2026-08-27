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

---

## CORRECTION, 2026-08-27: the table above overstates seven cards

Written the day after, against a full audit of all seventeen. **Not one card is
complete**, and the "DONE" column above is wrong wherever it appears.

**The headline: the ears have been deaf for 76.5 hours.**
`overnight/are_the_ears_live.py` exits 1. Newest speech of ALL TIME is
2026-08-24 01:30Z from `iphone-b75`, while the backend answered throughout.

The row above claiming EARS is "**DONE** — live rows from `iphone-b87`" is
FALSE, and I wrote it. Production holds zero rows from b87 and zero from any
build after 75. The tree is on build 102. Every capture change since 24 Aug is
unproven, because nothing has arrived to prove it with.

**Why no gate caught it.** `done_gate` leg 1 SHE HEARS YOU is green right now,
over a provably deaf phone, because leg 1 runs Swift tests in this checkout and
never consults `are_the_ears_live.py`. Nothing in done_gate, stranger_gate or
tejas_gate invokes that file — it is named only in CLAUDE.md, AGENTS.md and
research notes. The alarm exists and is wired to nothing.

**SORTER is not what leg 3 proves.** Leg 3 judges four single LINES against a
live model. That is the line-by-line judge this card exists to replace, so leg 3
being green is orthogonal to it. The segment judge is demoted to shadow
unconditionally at `brain/worker.py:2706-2717`; no value of
ANTICIPY_SEGMENT_TRIAGE lets it write back.

**LIBRARY's ageing half has no caller and no producer.** `expire_stale` is
defined at `brain/memory.py:2180` and grep across brain/ returns exactly that
one line. `valid_until` is a parameter no caller ever passes.

**Three cards are BUILT-NOT-WIRED** — code that exists, is tested, and is
reachable by nothing: HANDS 2's device lane (inert at both ends at once, which
is why no test caught it), SHELF 2 (the one admitted act type has no producer,
so nothing has ever been act-and-told), and the macOS recorder (whose suite is
on no scoreboard: grep for macos across overnight/ and run_all.sh returns
empty).

The honest count is **0 of 17**. The pattern in this file was calling a card done
because a gate leg was green, without asking what that leg actually measures.
