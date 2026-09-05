# The Cloudflare era — where the system actually is, and the plan from here

Written 2026-09-05 after the owner said "everything is on Cloudflare, forget
Railway". Every line under "measured" was checked against a live origin this
session; the rest is plan. The two screenshots the owner sent (another
session's summary) are the newest statement of the topology and outrank the
older files in migration/, which lag by a day and say so themselves.

## Measured

| piece | where it runs | measured how |
|---|---|---|
| API (`api.anticipy.ai`) | Cloudflare Worker `anticipy-api` + D1 `anticipy-backend` | `/api/health` 200, `/setup.html` 200, collections answer with the service token |
| D1 data | 36 tables; `agents` 472 rows (healthy), `jobs` 232 (newest 09-04 23:43Z), `events` 717 (**newest 09-02 04:58Z**), `segments` 14 (newest 09-01) | service-token reads |
| the Worker's model proxy | **`POST /agent/llm` → 503 "llm proxy not yet ported"** | `migration/workers/src/routes/agent.ts:148` |
| the Worker's extension download | **stale 0.12.0** (291,907 B copy in `migration/workers/public/`) | size + date; the committed 0.13.0 zip is 338,430 B |
| brain | Cloudflare Containers (`anticipy-brain`), writes `device_id: anticipy-brain` events to D1 | D1 rows; `brain-deploy.yml` is `workflow_dispatch` only |
| brain's HTTP client vs the firewall | httpx and requests get 200; only Python urllib's fingerprint gets 1010 | probed with the real libraries |
| iOS in this tree | points at `https://api.anticipy.ai`, migrates old installs off Railway (`AnticipyApp.swift:592, :798`) | grep |
| TestFlight pipeline | `.github/workflows/ios-testflight.yml` fires on push to **`jose_anticipy_system`** (a branch ~100 commits behind) or `workflow_dispatch`; xcodegen from `project.yml`; bumps the build above Apple's latest | read |
| Railway PocketBase | still receiving the phone's speech (**newest 09-05 00:02Z**); `agents` and `pendants` tables malformed; served 0.13.0 after today's deploys | reads + deploys |
| the phone in the field (iphone-b122, build 122) | posts to **Railway** — the api-pointed build is not on it | Railway events newest vs D1 events newest |
| wrangler on this machine | logged in as omar@anticipy.ai | `wrangler whoami` |

So today: the ears still land on Railway, the brain reads D1, and the hands
cannot think on Cloudflare. That is the state to move from, and the
screenshot's "forget Railway" is the destination, not yet the map.

## Measured on the Cloudflare dashboard (Claude in Chrome, 2026-09-05 ~12:20Z)

| surface | what the dashboard shows |
|---|---|
| Workers & Pages | 5 Workers: `anticipy-api` (api.anticipy.ai + 1 route, 64.5k requests, 6 errors), `anticipy-site` (www.anticipy.ai, 6.3k), `anticipy-brain` (no routes, 337), `anticipy-internal` (www.anticipy.ai/internal + 2), `anticipy-fellowships` (anticipyfellowship.com + 2) |
| `anticipy-api` deployments | 63 versions, all "Manually deployed / Wrangler / by omar"; active `f909fc2f`, 7 h old, 100% traffic, 2.3 req/s, **0% error rate**, 0.6 ms median CPU |
| Containers | `anticipy-brain-owner` **Active, 1 live instance** (0.25 vCPU, 1 GiB, 4 GB disk); usage this period 1.2k CPU-s |
| D1 | `anticipy-backend` **17.01 MB**; also `anticipy-backend-staging` (12 kB), `canopy`, `anticipy-fellowship` |
| R2 | `anticipy-downloads`, `anticipy-evidence`, `anticipy-owner-state`, `anticipy-pocketbase-backups-production` |
| DNS zone `anticipy.ai` | **active on Cloudflare** (13 records): `api` → Worker `anticipy-api` (proxied), `www` → Worker `anticipy-site` (proxied), apex A 76.76.21.21 proxied (redirects to www), MX Google, SendGrid CNAMEs, SPF/DKIM/DMARC |

The one number that looked like a question: **one live brain container**.
Answered from the code and the API: the supervisor (`migration/workers/brain/src/index.ts:176`)
runs one container per D1 owner whose email is real — it filters `.invalid`,
`.local` and `@example.` signups, which is most of the 33 rows
`/worker/owners` returns. One instance is one real owner. The R2 `owners`
object is not the source of truth for scheduling; D1 is.

## What today's work reaches, per organ

- **Hands (extension 0.13.0).** All seventeen audit items, the intent journal
  in both halves, the 512 reply floor: in the repo, in the Railway zip, NOT in
  the Worker's zip, and unable to run on Cloudflare until `/agent/llm` is
  ported. Proven live on the local rig (PocketBase hooks): install path 10/10
  twice, battery 7/8 with the 8th being the law working
  (`research/2026-09-05-hands-live-run.md`).
- **Brain.** 09b gateway fallback and 10a no-verdict floor merged; 06 bounds
  and 10b reserved budget building. Reach production only through
  `brain-deploy.yml` (manual dispatch) — nothing merged to brain/ is live
  until that runs.
- **Ears (iOS build 124).** Compiles clean, api-pointed, the capture fixes,
  which-ear count, battery drain, and the #90 retry citation. Reaches phones
  only through the TestFlight workflow.
- **Memory.** Lives in the brain container (per-owner SQLite pulled from R2 at
  boot). Moves with the brain deploy.
- **Pendant hardware.** Firmware fixed in source, unbuilt, unflashed; the
  pendant lane has never delivered a row anywhere. Out of reach here.

## Done since the plan was written (same day)

| step | result |
|---|---|
| Worker parity | `fields=` projection and the unique-collision 400 (`557e1227`); `heard_ms`/`heard_calls` in schema.sql + the map (`69eac667`); the live D1 ALTER waits for the owner |
| `/agent/llm` ported | `47c6f8d5`: 22 contract cases on a real workerd with a fake provider; floor 512, ceiling text, key-echo mutations red |
| Worker vars | `ANTICIPY_BROWSER_MODEL`/`ANTICIPY_VISION_MODEL` = gemini-3.1-pro-preview |
| **Worker deployed** | version `02aa186d`, `npm run deploy` (assets staged from `backend/pb_public`): `/agent/llm` → 400 credentials (was 503 "not yet ported"); `/agent/key` → 400 credentials (was 503 no model); served zip **338,456 B = 0.13.0**; `fields=id` → 200 |
| brain ports merged | 09b `8230819d`, 10a `3c36d2f7`, 10b `41ab8015`, 06 `6b7b9e16` — all four Omi ports the ledger ranked open |
| **brain deployed** | run 33966119164, `confirm=DEPLOY cap=1`, Worker version `b0b2f230`, image `sha256:cf5f8235…` built remotely; application version 1 → 2 by gradual rollout at 12:31Z; the supervisor logs "1 served, 4 unserved (cap 1)" every minute after; the Durable Object reset at 12:29 is the deploy landing |
| register returned no `id` | found by the smoke's leg 3 on Cloudflare; a 0.13.0 install minted a junk agents row per poll and never paired; fixed `640e8bc8`, deployed `f3d9da08`, contract pinned |
| **hands proven on Cloudflare** | `extension_smoke.mjs` unmodified, 10/10 against api.anticipy.ai with a disposable owner; two proxy audit rows on OpenRouter, claim in 4 s, done with a verified receipt |
| the instruments | fifteen defaults moved to api.anticipy.ai; `_env.py` sends a gate User-Agent because the firewall blocks `Python-urllib` (`9e53051c`); is_it_live and stranger 1/9 green against Cloudflare |
| **extension 0.14.0** | `5f4ccec6`: DEFAULT_BASE → api.anticipy.ai, four pins bumped, zip rebuilt; Worker `3b62abf2` serves it byte-identical; the served zip's own config.js reads `DEFAULT_BASE = "https://api.anticipy.ai"`; stranger legs 1 and 2 PASS |
| the ears on Cloudflare, measured | `are_the_ears_live.py` against api.anticipy.ai now RUNS (it needed `fields=`) and says **DEAF**: newest speech 2026-09-01 05:02Z (iphone-b113), newest server row 2026-09-02 04:58Z. Not a defect of the ears — no phone posts to Cloudflare until the api-pointed build is on one |

**Which owner the one brain serves — read from D1, masked.** The supervisor
serves real-email owners in id order up to the cap; with cap 1 that is
`43dl3t9oz7q34qc`, an `oma***@gmail.com` account created 2026-08-14. The
account whose phone actually carries speech today (`capture_day.py`'s
"whose day": `4i2vafx1g01nlia`, also `oma***@gmail.com`, created 2026-09-01)
is **second by id and therefore unserved**. The owner's own account
(`sxkotd1h02qb6gw`, `jos***@gmail.com`) is fourth. So even once the
api-pointed build is on the phone, the Cloudflare brain would be listening
for the wrong Omar until the cap is raised to at least 2 (and 4 for the
owner's) — or the supervisor learns an explicit list instead of "first N by
id". That is a product decision for the owner; the end-to-end run below
needs it settled first.

**Answered at 13:50Z.** After the allowlist deploy (run 33969999772, Worker
version `24041939`, `ANTICIPY_SERVE_OWNERS=qeuy6sv1raof9rw`, cap still 1)
`wrangler containers instances` lists TWO RUNNING instances on image
version 2: `43dl3t9oz7q34qc` (the first real owner, unchanged) and
`qeuy6sv1raof9rw` (the probe). The earlier "both inactive" listing was the
gradual rollout in flight, not a dead fleet. The brain is running the code
merged today, and the probe owner has a brain to hear it.

Earlier open question, kept for the record: `wrangler containers instances` listed only two INACTIVE instances (stale ids; `ssh` says not found) while the supervisor reports one owner served every minute and the DO keeps logging. Whether a container is actually running the new image is proven only functionally — by speech for the served owner reaching D1 and a decision coming back with `heard_ms` stamped. That is the end-to-end run's first hop.

## The sequence from here

1. ~~**Worker parity**~~ DONE (`557e1227`, `47c6f8d5`, `640e8bc8`; deployed `f3d9da08`). Was: port `/agent/llm` (building), copy the 0.13.0 zips into
   `migration/workers/public/`, add a gate leg that says the Worker's public
   folder equals `backend/pb_public`; `tsc`, dry-run, contract tests; then
   `wrangler deploy` from `migration/workers/`. Verify: `/agent/llm` answers a
   paired agent; `is_it_live.py` with `ANTICIPY_BACKEND_URL=https://api.anticipy.ai`.
2. ~~**Hands on Cloudflare, proven**~~ DONE 10/10 (hands-live-run.md). Was: `extension_smoke.mjs --base=https://api.anticipy.ai`
   with a test owner (creates one probe agent row and one read-only job on D1;
   the smoke tidies the agent and leaves the job as evidence). Then the same
   battery shape against the Worker if the rig can be pointed at it.
3. ~~**Extension 0.14.0**~~ DONE `5f4ccec6` / Worker `3b62abf2`.
4. ~~**Brain deploy**~~ DONE (run 33966119164, cap 1) — but see the served-owner finding: the cap serves the wrong Omar; the live legs wait for speech. Was: merge 06 and 10b, `gh workflow run brain-deploy.yml --ref cloudflare-backend`,
   then the live legs adapted to `wrangler tail`: gateway tally, decision
   bounds, unattributed lane, reserved budget.
5. **End-to-end, on Cloudflare, one test owner** (design below).
6. **TestFlight** — `gh workflow run ios-testflight.yml --ref cloudflare-backend`
   once 1–5 hold; the workflow bumps the build itself. Ready-to-ship verdict
   is given only after step 5's chain is green.
7. Railway: nothing more is deployed there. The repair switch is moot; the
   delta re-sync (owner's tool) carries the last rows when the freeze comes.

## End-to-end test design — the pendant system on Cloudflare

One test owner on production D1 (signup is open), phone number = the owner's
own, so every text lands with a person who can read it.

| hop | how it is driven | what proves it |
|---|---|---|
| ears → API | the api-pointed app on a real phone or the simulator (`proof/local_rig.sh phone` builds it; sign in to `api.anticipy.ai` instead of the rig), speaking three of the fifty moments; fallback: POST speech rows the way the app does (`proof/live_day.py` shape) | D1 `events` newest moves; `capture_day.py` against `api.anticipy.ai` reports the lines |
| API → brain | the brain container's poll | `anticipy-brain` rows in D1 within one poll; `wrangler tail anticipy-brain` shows the decision with its bounds and lane |
| brain → mouth | an ambient line that earns a text | the owner's phone receives it; the reserved-budget row exists in D1 |
| brain → hands | a spoken errand the brain turns into a job | a job row with workflow metadata on D1 |
| hands | a paired Chrome (0.14.0) on this machine | claim ≤ 30 s, model calls through `/agent/llm` (audit rows), done with evidence |
| hands → mouth | the done-text | the owner's phone receives the receipt |
| memory | the next morning's recall | the brain's `memory_notes` carries yesterday's fact |

Pass = every row filled with a live artefact id. Anything mocked is a fail.

## What only the owner can do

- rotate the tokens the other session pasted (their note, not mine)
- run the delta re-sync and the retire-readiness monitor at the freeze
- install the TestFlight build on the phone that wears the pendant
- decide the test owner's phone number for the end-to-end run
