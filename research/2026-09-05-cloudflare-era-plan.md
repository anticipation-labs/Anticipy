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
| TestFlight pipeline | `.github/workflows/ios-testflight.yml`. **Corrected 2026-09-05 (F38, F22, F21):** it fired on push to `jose_anticipy_system` — 165 commits behind — and uploaded that tree as builds 122 and 123; the trigger is now `cloudflare-backend`. It ran `agvtool new-version` unconditionally, so every upload was labelled one or two above the tree that made it (119→121, 121→122, 121→123); it now keeps the source number unless Apple already holds it. It also runs `app/ios/Tests/run_all.sh` before the archive, which nothing did | read + `gh run list` |
| TestFlight's newest build | **123**, from `jose_anticipy_system@db43db14` (source 121), uploaded 09-05 05:00Z. Cloudflare-pointed — it is `db43db14` that moved the app to api.anticipy.ai — but it predates the 122/123/124 capture, retry, which-ear and battery work, and its `expectedExtensionVersion` is 0.11.2, so it accepts 0.14.0 with no nag. **Do not install it as "the Cloudflare build"** (F35) | `gh run view 33945943140` |
| the Twilio number's webhook | `sms_url` = `https://backend-production-61e0a.up.railway.app/sms/inbound` — **replies land on Railway, and no Railway→D1 sync exists**, so the D1 brain never sees them. Nothing on Cloudflare will repoint it: the watchdog is off (`ANTICIPY_WEBHOOK_MANAGER=0`) and the cron dispatches only the HQ sweeps (F16) | read-only Twilio GET IncomingPhoneNumbers |
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
- **Ears (iOS build 125).** Compiles clean, api-pointed, the capture fixes,
  which-ear count, battery drain, and the #90 retry citation. Reaches phones
  only through the TestFlight workflow, which has never run from this branch —
  so none of it is on any phone, and `research/2026-09-04-omi-port-coverage.md`
  row 03 is NOT LIVE until rows read `iphone-b125` (F09). The number is 125,
  not 124: the extension pin moved after 124 was set, which left the
  build-number leg red in the tree (F21), and no 124 was ever uploaded.
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
| **deaf ears on Cloudflare, root cause** | the live D1 `events` table lacks `NOT NULL DEFAULT ''`; **a client that omits `decision`** (the phone does not — `AnticipyBackend.swift:717-720` always sends `decision:""` and `goal:""`; the row that hit this was a hand-made POST) has only its sent keys inserted → NULL, invisible to the brain's `decision=""` poll. Fixed in the write path (`45422c81`); one bad cut broke creates for ~2.5 min and was rolled back (`f2a4b269`). **Attribution corrected 2026-09-05 (F23)**: the earlier "the phone never sends `decision`" is false, and believing it sends the next session to patch a phone that is not broken — or to read ears-silence on Cloudflare as a Worker bug when the cause is that no api-pointed build is installed |
| **the pendant chain on production** | `proof/e2e_cloudflare.py` run 4: ears → API → brain → hands → done, every provable hop PROVEN, exit 0 (hands-live-run.md, Proof 3) |
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
5. ~~**End-to-end, on Cloudflare, one test owner**~~ DONE — run 4 exit 0; the two mouth hops and memory wait for a real phone (design below).
6. **TestFlight** — `gh workflow run "iOS TestFlight" --ref cloudflare-backend`
   once 1–5 hold. It uploads as **125** (the tree's number; the workflow no
   longer adds one — F22), so the Law-3 proof looks for `iphone-b125` rows,
   not 124. Before it goes in front of a real owner, the mouth has to work for
   that owner: Sendblue rows 5–8 green against live, or the Twilio number
   repointed (row 2c) — otherwise she asks and cannot hear the answer (F12,
   F16). Which brain hears that owner is set in the same step, per
   `research/2026-09-05-brain-of-record.md`. Ready-to-ship verdict is given
   only after step 5's chain is green.
7. Railway: nothing more is deployed there, and the two brains do not both
   serve one owner — the rule and the cutover step are
   `research/2026-09-05-brain-of-record.md`, not restated here. What changed
   today for it (F20): `brain-state-to-r2.yml` now REFUSES to write R2 state
   for any owner named in `ANTICIPY_SERVE_OWNERS`, because for those owners the
   container is the writer (a 60 s snapshot loop) and a copy from Railway would
   silently discard everything that brain has learned. The copy direction used
   to be undefined in both directions and nothing recorded which side was
   truth. The delta re-sync (owner's tool) carries the last rows at the freeze.

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

## The texting channel moves from Twilio to Sendblue (in progress, 2026-09-05)

The owner's decision. Sendblue is an iMessage-first API (falls back to RCS,
then SMS, from the same number); its dashboard is at "Developer" with
Overview / Playground / Request Logs / Webhooks / Services, currently in
Free API Mode (10 contacts). The switch, in the order it has to happen:

| step | where | state |
|---|---|---|
| 1. a Sendblue arm in the brain with the Twilio arm's exact contract (`text()` → `{sid,status,delivered}`, `SendFailed` on anything that did not go out, the rig guard that keeps a laptop from texting a real phone), provider selection `ANTICIPY_SMS_PROVIDER`, the Twilio-only startup checks skipped for it, a loopback outbound proof | `brain/sendblue_arm.py`, `brain/worker.py`, `proof/sendblue_outbound_proof.py` | done `a905225a`; proof 32/32 on a loopback fake, 0 real sends |
| 2. `POST /sms/sendblue` on the Worker: `sb-signing-secret` compared in constant time, status callbacks ignored, groups ignored, sender resolved to exactly one owner as the PocketBase hook did, dedupe on `message_handle`, the same `sms_reply` row the brain already polls — and the Twilio inbound route finished with the same code. **Corrected (F12): that 503 stub was never on the live path.** Twilio's number points at Railway, so no reply has ever reached it; a signed POST to `api.anticipy.ai/sms/inbound` 503s today, which means repointing the number BEFORE this deploys would move replies from "heard by Railway" to "dropped on Cloudflare". The Sendblue webhook on api.anticipy.ai is what actually closes the gap | `migration/workers/src/routes/sendblue.ts`, `src/pb/sender.ts` | done `6b790884`; wire test 21/21 on a real workerd + D1 |
| 2c. **the Twilio number still points at Railway** and nothing on Cloudflare repoints it (F16). While that holds, every question the D1 brain texts is unanswerable by text: a reply is written to Railway PocketBase, resolved against Railway's owners (where a D1-only signup does not exist), and the D1 brain's held card waits forever. Only `app_reply` from the phone reaches `handle_inbound`. Two consequences: **step 9's "keep Twilio as the fallback for a day" is a fallback to a broken path** until the number is repointed by hand after step 2 deploys; and `migration/config/wrangler.brain.jsonc`'s `ANTICIPY_TWILIO_WEBHOOK_URL` pin is `https://www.anticipy.ai/sms/inbound`, which answers **404 live** — if the watchdog is ever enabled it would bind the number to a dead host. Change that pin to `https://api.anticipy.ai/sms/inbound` (or delete it; the URL derived from `ANTICIPY_PB` is already api.anticipy.ai) | Twilio console or the owner's `PUT`; `migration/config/wrangler.brain.jsonc:290` | OPEN — the pin edit was not made here (that file belongs to the brain cluster this evening); the repoint is the owner's, command below |
| 3. the brain container is handed the Sendblue names | `migration/workers/brain/src/index.ts` FORWARD_KEYS | done `ad759c3c` |
| 4. the local rig strips `SENDBLUE_*` as it strips `TWILIO_*` and sets `ANTICIPY_SMS_MOCK=1` | `proof/local_rig.sh` | done (this commit) |
| 2b. the API Worker's OWN two texts — the HQ reminder sweep (`src/cron.ts sendSMS`) and the password-reset code (`src/routes/password_reset.ts sendCode`) — leave through one `sendText` that chooses Sendblue when its three names are bound (or `ANTICIPY_SMS_PROVIDER=sendblue`), else the exact Twilio request they used to build; a 2xx with status ERROR/DECLINED or an error_code is a failed send | `migration/workers/src/messaging.ts`, `test/messaging.test.ts` | built, repo-green; Law-3 proof is a reset code or reminder arriving from the Sendblue number after 5 |
| 5. deploy the Worker; set on it `SENDBLUE_WEBHOOK_SECRET` (secret), `SENDBLUE_FROM_NUMBER` (var), and — for 2b — `SENDBLUE_API_KEY_ID` and `SENDBLUE_API_SECRET_KEY` (secrets); optionally `ANTICIPY_SMS_PROVIDER=sendblue` (var) to force the choice while Twilio's secrets are still bound | owner runs `wrangler secret put`; Claude deploys | after 2 |
| 6. set on the brain Worker `SENDBLUE_API_KEY_ID`, `SENDBLUE_API_SECRET_KEY`, `SENDBLUE_FROM_NUMBER`, `ANTICIPY_SMS_PROVIDER=sendblue`; dispatch the brain deploy | owner runs `wrangler secret put --config migration/config/wrangler.brain.jsonc`; Claude dispatches | after 1 |
| 7. in the Sendblue dashboard: Developer → Webhooks → URL `https://api.anticipy.ai/sms/sendblue` with the same secret; Request Logs on | Claude in Chrome once the domain is allowed; the secret is the owner's to enter | after 5 |
| 8. prove it live: the owner texts the Sendblue number from their own phone → an `sms_reply` row on D1 within seconds → the brain answers from the Sendblue number; `is_the_brain_live.py` reads the slot | owner + Claude | after 6, 7 |
| 9. Twilio: leave its secrets in place until 8 holds for a day, then remove them from both Workers | owner | last |

### The owner's command sheet for the switch (run from the repo root; nothing here is printed back)

    # 1. the API Worker: the webhook secret you also enter in the Sendblue dashboard
    cd migration/workers
    npx wrangler secret put SENDBLUE_WEBHOOK_SECRET --config wrangler.jsonc
    npx wrangler secret put SENDBLUE_API_KEY_ID    --config wrangler.jsonc    # for the Worker's own texts (reset codes, HQ reminders)
    npx wrangler secret put SENDBLUE_API_SECRET_KEY --config wrangler.jsonc
    npx wrangler secret put SENDBLUE_FROM_NUMBER   --config wrangler.jsonc    # your Sendblue number, E.164

    # 2. the brain Worker (the container reads these; FORWARD_KEYS carries them in)
    npx wrangler secret put SENDBLUE_API_KEY_ID     --config ../config/wrangler.brain.jsonc
    npx wrangler secret put SENDBLUE_API_SECRET_KEY --config ../config/wrangler.brain.jsonc
    npx wrangler secret put SENDBLUE_FROM_NUMBER    --config ../config/wrangler.brain.jsonc
    npx wrangler secret put ANTICIPY_SMS_PROVIDER   --config ../config/wrangler.brain.jsonc   # value: sendblue

    # 3. the Sendblue dashboard, Developer -> Webhooks: URL https://api.anticipy.ai/sms/sendblue, secret = the value from step 1;
    #    Developer -> Overview: enable Request Logs. (Claude in Chrome can set the URL and the toggle once the domain is allowed; the secret is yours to type.)

    # 4. after Claude has deployed the Worker and dispatched the brain: text your Sendblue number from your own phone.
    #    Within seconds an sms_reply row lands on D1 and she answers from that number. That is the live proof of the mouth.

    # 5. TestFlight, when the audit is clean (uploads as 125, not 124):
    gh workflow run "iOS TestFlight" --ref cloudflare-backend

Nothing in the phone app names the sending number (the welcome text
introduces her from whatever number sends it), so a new number is not a
client change.

## What the pre-TestFlight audit changed here (2026-09-05, CI / iOS / ledger cluster)

The findings this section answers are F09, F12, F16, F18, F20, F21, F22, F23,
F26, F31, F35, F37, F38, F41, F44 and F47. The cap and brain-of-record verdicts
(F45, F48, F49) and the brain deploy's pre-flight (F46) are elsewhere:
`research/2026-09-05-brain-of-record.md` and `.github/workflows/brain-deploy.yml`.

| # | what was wrong | what changed |
|---|---|---|
| F09 | the Omi ledger read build 122's 68 lines as proof the relay fixes work; b122 predates them by two days and came off another branch | `research/2026-09-04-omi-port-coverage.md` row 03 is DONE-in-repo/NOT-LIVE, flipped only by `iphone-b125` rows |
| F12, F16 | the mouth's inbound path: the number points at Railway, the D1 brain polls D1, nothing syncs them, and the brain's webhook pin is a live 404 | Sendblue rows 2 and 2c above; the repoint is the owner's command below, and it must come AFTER row 2 deploys |
| F18 | `brain-state-to-r2.yml` was invalid YAML — heredoc bodies at column 1 closed the block scalar — so a dispatch-only workflow fired on every push and failed 50 times in a day | rewritten with every `run:` line inside its block scalar (the heredocs are gone; `python3 -c` does both jobs). Prove it: `ruby -ryaml -e 'YAML.load_file(".github/workflows/brain-state-to-r2.yml")'` |
| F20 | Railway and Cloudflare both ran a brain for the same owner, and the R2 copy direction was undefined in both directions | the rule is `research/2026-09-05-brain-of-record.md`; the workflow now refuses to write R2 state for an allowlisted owner, and takes an explicit `owners:` input |
| F21, F35 | the build number said 124 while the source had moved past it, and the ledgers described bytes nobody could build | build **125** at all six sites, with the reason in `project.yml`'s comment; `run_all.sh` now runs inside the TestFlight workflow, so the leg gates the upload instead of waiting for someone to remember |
| F22 | every CI upload was numbered one or two above its own tree (119→121, 121→122, 121→123), so no TestFlight build matched a commit | `next_build_number` keeps the source unless Apple holds it; `live_next_build` no longer adds one when there is no pre-release version; `agvtool` runs only on a collision. Pinned in `tests/test_app_store_connect_release.py` |
| F23 | three files blamed the phone for the NULL-`decision` rows; the phone always sends `decision:""` | corrected in the "deaf ears" row above (the Worker comment and the hands ledger are the write-path cluster's) |
| F26 | the Omi ledger's ranked list asked for four ports that were built, one of them deployed | rewritten; the triage fence is relabelled 10c and recorded as deployed with no eval leg |
| F31, F38 | no test workflow had ever run on `cloudflare-backend`, and the TestFlight trigger still armed a 165-commit-behind branch | `system-invariants.yml` runs on both branches; `ios-testflight.yml` fires on `cloudflare-backend` only |
| F37, F44, F47 | `is_the_decision_bounded.py` is UNPROVEN, and the ledger blamed the deploy | it is the missing D1 columns; the deployed brain stamps decisions and drops the measurement on the Worker's 400. The ALTER is the owner's, below |
| F41 | three Worker routes are 503/401 stubs and no ledger said so | recorded below |

**Stubs still OPEN on the Worker (F41), none of which a build-125 owner hits.**
`/agent/solve-captcha` — 503 even when configured, and `CAPSOLVER_API_KEY` is
not bound as a secret; the extension degrades to "solving unavailable — handing
it to the owner", which is what an unconfigured hook always did.
`/agent/upgrade-credential` — 503 behind the service-token check; the
extension's only caller treats any non-OK as null and has been getting 403
since the master token left the browser. `/transcription/token` — answers 401
"Sign in first." to everyone, and has no caller at all (the phone's fetch was
removed). Server-side CAPTCHA solving was an owner instruction on 2026-08-16
and is the one real loss; porting it means the hook's CapSolver create/poll
into `agentCaptcha` plus the secret. The other two are not worth porting.

### The owner's commands from the audit (nothing here is printed back)

    # A. The D1 columns the bounded-decision leg reads (F37, F44, F47). The brain
    #    already stamps decisions; it drops heard_ms/heard_calls on the Worker's 400
    #    and latches that off per process, so restart the containers afterwards.
    npx wrangler d1 execute anticipy-backend --remote \
      --command "ALTER TABLE events ADD COLUMN heard_ms REAL NOT NULL DEFAULT 0;"
    npx wrangler d1 execute anticipy-backend --remote \
      --command "ALTER TABLE events ADD COLUMN heard_calls REAL NOT NULL DEFAULT 0;"
    # then re-dispatch the brain deploy (restarts the containers) and:
    ANTICIPY_BACKEND_URL=https://api.anticipy.ai python3 overnight/is_the_decision_bounded.py

    # A2. Optional, same session (F47): live D1 is missing six indexes that
    #     migration/d1/schema.sql declares. Nothing at today's row counts depends
    #     on them; they are full scans over ~700 rows until then.
    #     idx_events_owner_ref_created, idx_events_segment, idx_jobs_owner_ref_status,
    #     idx_jobs_lane_status, idx_agents_pair_code, idx_agents_owner_ref

    # B. Point the Twilio number at Cloudflare (F16) — ONLY after the Worker
    #    carrying the finished /sms/inbound route is deployed, or replies go from
    #    "heard by the wrong brain" to "dropped with a 503".
    #    Twilio console -> Phone Numbers -> the number -> Messaging -> A message comes in:
    #      https://api.anticipy.ai/sms/inbound   (POST)
    #    Equivalently: PUT /2010-04-01/Accounts/{sid}/IncomingPhoneNumbers/{numberSid}.json
    #      SmsUrl=https://api.anticipy.ai/sms/inbound
    #    Nothing on Cloudflare does this for you: the watchdog is off and the cron
    #    dispatches only the HQ sweeps.

    # C. Carry an owner's brain memory to R2 before they move (F18, F20). The job
    #    parses again, and refuses any owner already on ANTICIPY_SERVE_OWNERS.
    gh workflow run "Brain state → R2 (Railway volume migration)" \
      --ref cloudflare-backend -f confirm=MIGRATE -f owners=<owner id>

## What only the owner can do

- rotate the tokens the other session pasted (their note, not mine)
- run the delta re-sync and the retire-readiness monitor at the freeze
- install the TestFlight build on the phone that wears the pendant
- decide the test owner's phone number for the end-to-end run
- the two ALTERs on live D1, and the Twilio repoint (commands above)
