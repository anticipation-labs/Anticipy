# Layer audit and live status — 8 September 2026

Written from Tejas's Mac against `cloudflare-backend` at `eac3aba1`. Everything
marked VERIFIED was run or read here. Method: eight layers traced by agents,
then every candidate defect handed to a second agent told to refute it. Of 42
candidates, **24 survived and 18 were refuted** — so nothing below is an
unchecked claim, and the 43% refutation rate is why the raw list is not
published.

## What this pass could and could not do

**Could not**: use the product. This machine has Command Line Tools and no
Xcode, no iPhone, no pendant, no TestFlight, and no credentials — no
`ANTICIPY_SERVICE_TOKEN`, `OPENROUTER_API_KEY`, `ANTICIPY_BACKEND_URL`,
SendBlue or Composio. Nothing here is a claim about lived use, and no scenario
from the 500-case catalogue was executed.

**Could**: verify the live release by its bytes, run every gate and suite, and
trace the layers through source. That is what follows.

## Live state, VERIFIED

| Thing | Result |
|---|---|
| Repo sync | local == `origin`, tree clean |
| API health | 200, `x-anticipy-revision: d52eaf38` |
| Mac zip live | 200, 1,148,615 bytes, `application/zip` |
| Mac zip sha256 | `c27dd01e…8186e1cbb` — matches committed build and the handoff's expected hash |
| Deploy run 34180318042 | completed, success |
| Extension 0.18.0 | source, committed zip, live URL all agree |
| Python | 3033 passed, 2 skipped |
| Worker | tsc clean, all suites |
| Extension | 83 of 83 suites |
| Mac | 7 suites, 140 checks |
| iOS | all suites, build 171 |

The previous handoff asked the next operator to read the Mac bytes back. **Done
and matching.** The repo is green everywhere.

Gates: `stranger_gate` 10 of 11 pass; `tejas_gate` 7 pass with leg 6 red by
design; `tape_gate` 5 pass with leg 2 red by design; `no_vendor_ears` passes.
`done_gate` legs 3 and 4 and both live-memory gates fail **only for want of
credentials on this machine** — they are honest refusals to pass an untestable
leg, not product defects.

## The headline: what the product actually does

Traced call chains only, never a README. Condensed from the full inventory.

| Capability | Verdict |
|---|---|
| Speech capture, phone | LIVE, proven on production |
| **Speech capture, pendant** | **ABSENT** |
| Speaker attribution | UNWIRED — measured 0% across 221 production events |
| Task creation | LIVE, proven |
| Native iPhone calendar write | PARTIAL — executor real, not proven live |
| Calendar read | PARTIAL, native only |
| SMS outbound / inbound | PARTIAL — wired and credentialled, **never proven live** |
| Calendar/email/doc write via connected API | **UNWIRED** |
| Email read | PARTIAL — supervised browser only, owner must watch |
| Email send | PARTIAL — browser only, no live receipt ever |
| Browser read / click | PARTIAL — arm alive, receives nothing |
| Research | PARTIAL — needs Brave/Tavily keys |
| Proactive surfacing | PARTIAL — notifications only while listening is on |
| Memory recall | LIVE in process, durability UNPROVEN |

**Omar asked me to use it as a pendant user. The pendant audio path is not
implemented.** `AnticipyApp.swift:2153` `startPendantTranscription` sets
`pendant.onOpusFrame = nil` — there is no Opus decoder in the target and pendant
audio is discarded at the source. No amount of device access would have made
that journey work.

What a new owner really gets in hour one: speech capture on the phone, a
transcript feed, model triage, task cards, in-app answers, memory, native
calendar writes and server-composed text. Everything touching the outside world
needs a Chrome extension on a computer.

## Defect 1 — the public download still hands over the old product

`stranger_gate` leg 11, and measured here: `www.anticipy.ai/download` redirects
to `Anticipy_1.0.0_aarch64.dmg` and delivers **2,516,712,351 bytes** of the May
2026 product. The notarized 1.1 MB build 171 is live and correct at
`api.anticipy.ai`; the website does not point at it.

The repair is written, reviewed, merged to `aniticipy-web` branch `cloudflare`
(the branch the live Worker builds from) and built in that checkout,
smoke-tested under `wrangler dev`. It has never been deployed:

```sh
cd <aniticipy-web checkout>
CLOUDFLARE_ACCOUNT_ID=114587b715e702461766369b01d42fc7 npx wrangler deploy
```

This is the last red leg. The site is **not** on Vercel; merging to `main`
deploys nothing that reaches the domain.

## Defect 2 — the connected-API hand can never fire

Verified four ways here, then re-confirmed independently with the mechanism:

1. `brain/hands.py:1066` GETs `/api/collections/connections/records`.
2. `migration/workers/src/api/schema.ts` defines only `agents, events,
   evidence, jobs, owner_profile, owners, pendants, purges, segments`.
3. `resolveCollection()` returns `COLLECTIONS[name] ?? null`.
4. No Worker route serves that path.

So `read_connections()` always returns None, and — the part that matters —
**`brain/hands.py:553` reads `if ctx.connections is None: return
HandVerdict(HAND_BROWSER, …)`, downgrading EVERY api verdict to the browser
hand before `plan_api_step` is ever reached.** No row can carry `lane="api"`.
The whole API executor (`run_api_jobs` → `/hands/api/run` → `api_hand.ts`)
exists and can never receive work.

Meanwhile first run and Settings sell connections as a working execution route
(`ConnectOnboardingPolicy.swift:928`) — rated a blocker on its own.

Not patched. `/me/connections` requires a signed-in owner session while the
brain holds a service token, so this moves an authorization boundary on
production data where one owner's connections reaching another is a release
blocker, and it cannot be tested from here. Two options:

- **A** — add `connections` to the records API `COLLECTIONS` with the owner
  scoping every other brain read uses. Smallest change.
- **B** — add a service-token route beside `/me/connections` for a named owner.

## Defect 3 — a spoken errand can be silently cancelled

`brain/worker.py:3293` → `anticipy_core.py:2736,2754,2780`. A **0.6 word-overlap
dedup** can misfire and cancel a newly spoken errand. Rated blocker, live.

This is one of a family. Proactive suppression is decided by word-overlap
ratios: a 0.34 overlap mutes the clock about a subject for 14 days
(`worker.py:3404`); the clock sees only the ten oldest open commitments
(`anticipy_core.py:4363`); `status_report()` can answer "Nothing's open — all
loops are closed" when loops are open (`anticipy_core.py:3165`).

Word-overlap ratios deciding what an owner meant is precisely what Law 1
forbids. This is the most systemic finding in the audit.

## The rest of the confirmed defects

Eight high, eight medium, eight low. The high ones:

| Defect | File |
|---|---|
| A correction never reaches the API hand; args planned once at mint | `hands_api.ts:368` |
| A spoken correction to a running task is answered "Already handled" | `anticipy_core.py:3780` |
| Recall has a hard cliff at 300 matching episodes — reproduced exactly | `memory.py:1110` |
| One unanswerable veto rolls back the whole nightly consolidation | `memory.py:1432` |
| The Worker texts the number the owner replaced | `wiring.ts:696` |
| An SMS "yes" binds to whatever revision the task holds now | `conversation.py:478` |
| A failed profile read discards the owner's next text permanently | `worker.py:4361` |

The memory cliff was reproduced by the verifier: 299 later lines containing one
query word and the fact is recalled; 300 and it is gone. The repo's own
`proof/memory_scale.py` passes vacuously because its filler shares no
vocabulary with the query.

## Cost

An idle owner costs approximately zero model spend — verified by driving the
real loop with a counting stand-in at the transport boundary. The problems are
elsewhere, and the first one is that **spend is currently unmeasured**:
`brain/llm.py:882` records nulls for every call on the default transport.

Ranked, with the auditor's estimates:

1. **Turn the instrument on.** Map Gemini's token counts into the keys `_record`
   reads and give the ledger a durable sink. No saving; every number below is an
   estimate until it lands.
2. **Profile-relation judge off the frontier tier, widen the batch** 25 → ~100.
   120 stored facts cost 345 frontier calls today. 70–90% of nightly memory
   spend. Gate it on `proof/audit/run_memory_relations.py` at both tiers.
3. **Bound the briefing window.** 2,000 episodes → 38,011 tokens in one prompt,
   unbounded in the container shape.
4. **Split the poll cadence.** 13–14 backend GETs per idle turn, ~650k
   requests/owner/day; ~80% reduction with no latency change.
5. Fix an escalation condition that buys frontier calls out of failures,
   stop re-asking a question already answered, slim the verify prompt.

## What to do next, in order

1. Run the one deploy command above. It clears the last red gate leg.
2. Decide option A or B for connections, implement, and test live. Until then
   the API hand is dead and first run is selling it.
3. Fix the 0.6 word-overlap cancellation before it eats somebody's errand.
4. Turn on the cost ledger, then take the memory-judge tier and batch.
5. Prove SMS end to end once, in both directions. It has never been done.
6. Decide whether the pendant ships. Today the app promises a device whose
   audio it discards.
