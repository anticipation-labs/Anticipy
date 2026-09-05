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

## The sequence from here

1. **Worker parity** — port `/agent/llm` (building), copy the 0.13.0 zips into
   `migration/workers/public/`, add a gate leg that says the Worker's public
   folder equals `backend/pb_public`; `tsc`, dry-run, contract tests; then
   `wrangler deploy` from `migration/workers/`. Verify: `/agent/llm` answers a
   paired agent; `is_it_live.py` with `ANTICIPY_BACKEND_URL=https://api.anticipy.ai`.
2. **Hands on Cloudflare, proven** — `extension_smoke.mjs --base=https://api.anticipy.ai`
   with a test owner (creates one probe agent row and one read-only job on D1;
   the smoke tidies the agent and leaves the job as evidence). Then the same
   battery shape against the Worker if the rig can be pointed at it.
3. **Extension 0.14.0** — `DEFAULT_BASE` → `https://api.anticipy.ai` so a fresh
   install pairs with a phone that is itself api-pointed (pairing needs both
   halves on one backend). Rebuild into BOTH public folders; deploy the Worker.
   Railway keeps 0.13.0 for old installs.
4. **Brain deploy** — merge 06 and 10b, `gh workflow run brain-deploy.yml --ref cloudflare-backend`,
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
