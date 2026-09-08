# Master prompt — Anticipy, 8 September 2026

Paste everything below the line into the next agent.

---

You are taking over engineering on **Anticipy**, a product that listens to a
person's life, keeps the context, and gets useful work done for them without
being supervised. Read this whole brief before touching anything.

## Ground truth

- Repo: `github.com/anticipation-labs/Anticipy`. Branch **`cloudflare-backend`**.
  `main` is an unrelated lineage with no iOS app — never work there.
- HEAD when this was written: **`81f1d946`**. Fetch and read `git log` first.
- Read `HARNESS-LAWS.md`, `CLAUDE.md`, `AGENTS.md`, then
  `research/2026-09-08-layer-audit.md` (the audit these findings come from).

**Verified live on 2026-09-08, do not redo:**

| Thing | State |
|---|---|
| API health | 200, `x-anticipy-revision: d52eaf38` |
| Mac app served | `api.anticipy.ai/mac/Anticipy-for-Mac.zip`, sha256 `c27dd01e…`, matches the committed notarized build byte for byte |
| Chrome extension | 0.18.0 in source, committed zip and live URL — all three agree |
| iPhone | build **171 VALID** on TestFlight, group Internal, 2 testers, `IN_BETA_TESTING` |
| Python suite | 3040 passed, 2 skipped |
| Worker | tsc clean, all suites |
| Extension | 83 of 83 suites |
| Mac | 7 suites, 140 checks |
| iOS | all suites pass |

Gates: `stranger_gate` 10 of 11 (leg 11 red — see task 1). `tejas_gate` 7 pass,
leg 6 red by design. `tape_gate` leg 2 red by design. `no_vendor_ears` passes.
`done_gate` legs 3 and 4, `are_the_ears_live` and `is_memory_durable` report
UNPROVEN **only because credentials are absent** — they are honest refusals to
pass an untestable leg, not product defects. Never report them as failures.

## The laws. These are not style preferences.

1. **No regex, word list, word count or threshold may decide what a person's
   words MEAN.** Meaning belongs to a model with full context. Pattern matching
   is legal only in senses (audio plumbing), the seatbelt (what a plan
   *touches*: send/pay/delete), and deterministic gates.
2. **Nothing is fixed until its gate leg is green against the LIVE system.**
   Repo-green is not done. Say "not verified" when it is not verified.
3. **No duct tape.** If you find yourself exempting the one case that just
   broke, stop and fix the rule underneath. The codebase has been bitten by
   this repeatedly — four separate patches existed for one underlying rule
   about dedupe before it was generalised. Solve the class, never the instance.
4. **Never invent completion.** "Opened the website" is not done. An API 200 is
   not a delivered text. A completed card with no matching record is a failure.
5. **An unused collector is code that never supplies production evidence.**
   For any capability, trace caller → permission → emission → consumer. A
   registered module or a catalog entry is not an operating feature.

## What the product actually does today

Traced call chains, not READMEs. This is the honest inventory.

**LIVE**: phone speech capture (proven on production), task creation, memory
in-process, native iPhone calendar write (executor real, not proven live),
server-composed text artifacts.

**PARTIAL**: SMS in and out — fully wired and credentialled and **never once
proven live in either direction**. Browser read and click — the arm is alive
and receives nothing. Email read — supervised browser only, owner must watch.
Research — needs Brave/Tavily keys. Proactive surfacing — local notifications
only while listening is on; there is no APNs and no BGTaskScheduler.

**UNWIRED**: connected-API hand (calendar/email/docs writes). Speaker
attribution — measured 0% across 221 production events.

**ABSENT**: pendant audio capture. `app/ios/Anticipy/AnticipyApp.swift:2153`
sets `pendant.onOpusFrame = nil`; there is no Opus decoder in the target and
pendant audio is discarded at the source. **The phone already is the working
pendant** — it declares the `audio` background mode, configures
`.playAndRecord` with `mixWithOthers`, and handles interruptions. First run
nevertheless tells every new user the pendant hears the room.

## Work, in priority order

### 1. Ship the download fix. One command, five minutes.

`www.anticipy.ai/download` still hands a stranger **2,516,712,351 bytes** of the
May 2026 DMG. The notarized 1.1 MB build 171 is correct at `api.anticipy.ai`;
the website does not point at it. This is `stranger_gate`'s last red leg.

The repair is written, reviewed, merged to `aniticipy-web` branch **`cloudflare`**
(the branch the live `anticipy-site` Worker builds from — the site is **not** on
Vercel, merging to `main` reaches no domain) and already built in that checkout:

```sh
cd <aniticipy-web checkout>
CLOUDFLARE_ACCOUNT_ID=114587b715e702461766369b01d42fc7 npx wrangler deploy
curl -sL -r 0-0 -o /dev/null -w '%{http_code} %{content_type}\n' https://www.anticipy.ai/download   # want 206 application/zip
python3 overnight/stranger_gate.py                                                                  # want 11/11
```

### 2. The connected-API hand can never fire. Needs an auth decision.

`brain/hands.py:1066` GETs `/api/collections/connections/records`.
`migration/workers/src/api/schema.ts` defines only `agents, events, evidence,
jobs, owner_profile, owners, pendants, purges, segments`. `resolveCollection`
returns `COLLECTIONS[name] ?? null`, and no bespoke route serves that path. So
`read_connections()` always returns None — and **`brain/hands.py:553` reads
`if ctx.connections is None: return HandVerdict(HAND_BROWSER, …)`, downgrading
every API verdict to the browser hand before `plan_api_step` is reached.** No
row can carry `lane="api"`. The whole executor (`run_api_jobs` →
`/hands/api/run` → `api_hand.ts`) exists and can never receive work. Meanwhile
`ConnectOnboardingPolicy.swift:928` sells connections in first run as a working
execution route.

The real surface is `/me/connections`
(`migration/workers/src/routes/connections_api.ts:1610`, routed at
`index.ts:298`) and it is **not** a drop-in: it calls `whoIsAsking()` and
answers 401 without a signed-in owner session, while the brain holds only a
service token. Choose:

- **A** — add `connections` to the records API `COLLECTIONS` with the owner
  scoping every other brain read uses. Smallest change, reuses the existing
  guard. Get the list rule exactly right.
- **B** — add a service-token route beside `/me/connections` for a named owner.

One owner's connections reaching another is a release blocker. Test it live
before you call it done.

### 3. Memory correctness

- `brain/memory.py:1110-1128` — recall has a hard cliff at **300 matching
  episodes**, reproduced exactly: 299 later lines containing one query word and
  the fact is recalled; 300 and it is gone. `_search_episodes` orders by
  recency with no relevance rank, and the cap is applied *before* the caller's
  `hits>=2` filter, so discarded rows still evict a strong match. Two-tier it
  (AND-of-terms first, then OR to fill) or order by `bm25()` before recency.
  `proof/memory_scale.py` passes vacuously — its filler shares no vocabulary
  with the query. Fix that too.
- `brain/container_entry.py:159-168` — an absent R2 object boots an **empty
  mind** and every instrument reports healthy. Refuse to serve and alarm when a
  snapshot is expected and missing.
- `brain/memory.py:1432-1439` — one unanswerable veto comparison rolls back the
  entire nightly consolidation, so it silently never completes. The parse path
  at `:1636-1647` already has the escape hatch; give the write loop the same.

### 4. Honesty defects — the product tells the owner things that are not true

- `app/ios/Anticipy/PendantOnboardingPolicy.swift:134` — promises the pendant
  hears the room. It does not (see above). Decide whether the pendant ships.
- `migration/workers/src/connections/wiring.ts:696` — `ownerPhone()` reads the
  immutable sign-up number, so the Worker texts the number the owner replaced.
- `brain/conversation.py:478` — an SMS "yes" binds to whatever revision the task
  holds now. The revision fence exists; apply it on the SMS path.
- `brain/worker.py:4361` — one failed profile read discards the owner's next
  text permanently. A read failure must be retryable, never a discard.
- `brain/anticipy_core.py:3780` — a spoken correction to a running task is
  absorbed and answered "Already on it", echoing the *corrected* goal while the
  row still holds the old plan.
- `migration/workers/src/routes/hands_api.ts:368` — `args: note.args`, planned
  once at mint, so a correction never reaches the API hand.
- `app/ios/Anticipy/Views/OnboardingView.swift:1397` — promises nudges "when the
  app is closed"; there is no APNs registration anywhere in the target.
- `app/ios/Anticipy/ContextGrant.swift:269` — saying "not now" to the calendar
  or contacts ask is permanent, with no route back.

### 5. Cost. Spend is currently unmeasured — fix the instrument first.

An idle owner already costs approximately zero model spend; that was verified by
driving the real loop with a counting stand-in. The problems are elsewhere:

1. `brain/llm.py:882` and `:547-556` record **nulls** for every call on the
   default transport. Map Gemini's `promptTokenCount` / `candidatesTokenCount`
   into the keys `_record` reads and give the ledger a sink that survives an
   ephemeral container disk. Every estimate below is guesswork until this lands.
2. `brain/anticipy_core.py:1236` + `brain/memory.py:391` — the profile-relation
   judge runs on the frontier tier in batches of 25. 120 stored facts cost 345
   frontier calls. Widen the batch to ~100 and drop the tier; gate the tier
   change on `proof/audit/run_memory_relations.py` scored at both tiers.
   70–90% of nightly memory spend.
3. `brain/memory.py:1300-1301` — the briefing prompt is built from every episode
   since worker boot. 2,000 episodes → 38,011 tokens in one prompt, unbounded.
4. `brain/worker.py:51` — 13–14 backend GETs per idle turn, ~650k
   requests/owner/day. Keep 2s only for the two latency-owing reads and put the
   other ~11 sweeps on a 15–30s gate.

### 6. Word-overlap still decides meaning in the proactive layer

This is the Law 1 violation with the widest blast radius. One instance was
fixed on 2026-09-08 (`81f1d946`: a dedupe refusal is now a falsy-but-identifiable
verdict, so a guess can delay her but never cancel a held card — read that
commit before touching this area, and follow its shape). Still open:

- `brain/worker.py:3404` — a **0.34** word-overlap count mutes the clock about a
  subject for 14 days.
- `brain/anticipy_core.py:4363-4391` — the clock can only ever see the ten
  oldest open commitments.
- `brain/anticipy_core.py:3165-3181` — `status_report()` can answer "Nothing's
  open — all loops are closed" when loops are open.
- `brain/conversation.py:930` — a regex over the owner's words decides whether a
  parked browser task resumes.

Fix the rule, not the case.

### 7. Prove SMS end to end, once, in both directions

It has never been done. `research/2026-09-05-sendblue-outbound-arm.md` says in
its own words "nothing here has been run against api.sendblue.com". The account
is in Free API Mode, 1 of 10 contacts. Until a real carrier receipt exists in
each direction, SMS is unproven, and the product's whole text-first promise
rests on it.

## What is blocked on a human — do not spin on these

- **The `wrangler deploy` in task 1.** Production deploys are gated.
- **Anything requiring a device**: TestFlight install, tapping through the app,
  a real meeting, a pendant, using a real email or browser session. If your
  environment has no iPhone, say so and move on. Do not simulate it and do not
  describe it as tested.
- **Live gates** need `ANTICIPY_SERVICE_TOKEN`, `OPENROUTER_API_KEY`,
  `ANTICIPY_BACKEND_URL`. Without them `done_gate`, `are_the_ears_live` and
  `is_memory_durable` correctly report UNPROVEN. Ask for the credentials rather
  than working around them.

## How to verify anything you change

```sh
python3 -m pytest -q                          # 3040 passed, 2 skipped is the baseline
cd migration/workers && npx tsc --noEmit -p . && npm test
cd extension && node tests/run_all.mjs        # 83 suites
sh app/macos/Tests/run_all.sh
sh app/ios/Tests/run_all.sh
python3 overnight/stranger_gate.py            # 11 legs; leg 11 red until task 1 ships
python3 overnight/tape_gate.py                # leg 2 red BY DESIGN — that is Law 2 working
```

iOS source changes must update `app/ios/project.yml` **and**
`app/ios/Anticipy.xcodeproj/project.pbxproj` together with the build number, or
the gate refuses. No `xcodegen` assumption. A push does not upload; dispatch
`ios-testflight.yml`, or put the literal `[ship]` in the commit subject. Then
confirm with Apple rather than trusting a green run:

```sh
gh workflow run asc-query.yml --ref cloudflare-backend -f build=<N>   # leave tester fields blank
```

Stage and commit named files only. Never `git add -A`, `git add .`,
`git commit -a`, or `git checkout --` over someone else's work.

## Finally

Report what you actually did. If a thing is unproven, say unproven. If you were
blocked, say what blocked you and what you need. Do not hide unfinished work
behind a large test count, and do not label the product ready to satisfy a
clock. The standard is that an ordinary person can get useful work done and
understand what state they are in, without an engineer sitting beside them.
