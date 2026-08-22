---
name: testing-anticipy
description: How to run hands-off end-to-end tests of the Anticipy pendant assistant (PocketBase backend, brain, Chrome extension agent loop) at volume on this Mac.
---

# Testing Anticipy end-to-end

Three surfaces, three harnesses. Everything below runs on THIS machine
(`~/Desktop/anticipy-omize`, rig state in `~/.anticipy-rig`). The older
`/home/ubuntu/anticipy_app` paths in this file's history were a different box;
nothing here uses them.

## Stand the rig up

```sh
sh proof/local_rig.sh up            # PocketBase :8090 + the brain, seeded
node proof/fixtures/server.mjs &    # the deterministic web, :8899
node proof/chrome_arm.mjs up        # a paired Chrome, fully automatic
```

- **Never background a service from a tool-call shell.** It is killed with the
  process group when the call returns. Use a supervised process, `setsid`, or
  `nohup` from a shell that outlives the call.
- **`ANTICIPY_SERVICE_TOKEN` and `ANTICIPY_PB` live in `.env.local` and leak
  into every child process.** With the token set, `guard.pb.js` answers every
  collection read `{"error":"forbidden"}` and the rig looks broken. With
  `ANTICIPY_PB` set, `proof/ambient/run.py` correctly REFUSES to run because it
  points at production. Start PocketBase with the token cleared and pass
  `--pb http://127.0.0.1:8090` explicitly. `proof/ambient/fanout.py` already does.
- Model key: `OPENROUTER_API_KEY` in `.env.local`. Check the balance BEFORE a
  long run — `curl -H "Authorization: Bearer $KEY" https://openrouter.ai/api/v1/credits`.
  A 402 mid-run does not stop anything: the worker stamps `decision="error"`
  and falls back to rules, so the results file keeps filling with rows that
  look like judgements and are not. Truncate every lane at its first `error`.

## The Chrome arm — `proof/chrome_arm.mjs`

One command from cold to a paired, model-armed browser (~7s).

```sh
node proof/chrome_arm.mjs up --port=29401 --owner-ref=<ref>
node proof/chrome_arm.mjs status --port=29401
node proof/chrome_arm.mjs down --port=29401
```

Four things it exists to get right, each of which cost a debugging round:

1. **`extension/config.js` defaults to PRODUCTION.** A fresh profile registers
   against the owner's real backend from `onInstalled`, before any script can
   write `chrome.storage`. `up` launches with
   `--host-resolver-rules=MAP <prod host> ~NOTFOUND` so the race lands on a DNS
   failure, and it VERIFIES the blackhole before pairing anything.
2. **An unpacked extension's id is `sha256(absolute path)`, first 128 bits,
   nibbles mapped to a..p.** Derive it; never take "the first service worker"
   off `/json/list` — Chrome's own component extensions have workers too, and
   evaluating against one dies on `chrome.storage` being undefined.
3. **MV3 workers are mortal.** Killed at ~30s idle, respawned with a NEW target
   id; a socket held across that goes silent forever. Re-resolve the target on
   every call. To wake a stopped worker, open one of the extension's own pages
   (`onboarding.html`) — `about:blank` belongs to no extension — then close it.
4. **`import()` is banned in a service worker**, so `background.js` exports are
   unreachable over CDP. Trigger registration the way a person does: open the
   setup page, whose `anticipy-ping` re-asserts alarms and polls on the spot
   (194ms vs the 30s alarm floor), then poll storage for `recordId`.

Pairing is still just: `POST /agent/register`, then PATCH the agents record
with `{owner, owner_ref, paired:true}`.

## Voice / ambient — `proof/ambient/`

```sh
python proof/lanes.py provision voice 8
python proof/ambient/fanout.py --corpus proof/ambient/corpus.big.json --label round1
python proof/ambient/score.py --corpus proof/ambient/corpus.big.json \
       --results proof/ambient/rounds/round1/results.jsonl
```

- `corpus.big.json` is 1000 authored utterances, 164 walks of life, 47
  conversations, 278 hard cases. `corpus.json` (320) is the original.
- **One owner_ref per lane, one brain worker per lane.** `worker.py:45` binds
  `ACTIVE_OWNER_REF` at process start. 8 lanes ran ~2.5s/utterance against ~31s
  serial.
- **Never pair a Chrome to a voice lane.** The corpus mints real jobs; a paired
  browser claims them and drives the live web, and the run then measures the
  browser's luck instead of the brain's judgement.
- Conversations must stay CONTIGUOUS and in turn order in the corpus file —
  `run.py` walks it in order and only applies the 10s turn gap while `convo` is
  unchanged. `fanout.py` shards whole conversations for the same reason.
- **`consequences()` normalises its own filter timestamps now.** PocketBase
  silently matches nothing against a `T`-separated operand, so the live path
  used to record `said=[]`/`jobs=[]` for every row and the scorer graded every
  errand as `silent`. That single bug fabricated 88 misses in the 2026-08-20
  scorecard. If you add a caller, pass either shape; do not re-add a `.replace`
  at the call site.

## Browser agent — `proof/battery/`

```sh
node proof/battery/selfcheck.mjs                     # 4s, no LLM. Always first.
node proof/battery/run.mjs --owner-ref=<ref> --owner=arm-1 \
     --fixture=http://127.0.0.1:8901 --ids=<ids> --label=r1 --out=...
node proof/battery/score.mjs proof/battery/results/r1*.jsonl
```

- 102 tasks in `tasks.json`. `score.mjs` reads that file unconditionally and
  joins by `task_id`, so NEW TASKS MUST LAND THERE, not in a side file.
- **The lane owns the fixture origin.** `--fixture` now rewrites each fixture
  task's `start_url` at mint time (`localise()`), because the agent reads
  `start_url` off the job row: without the rewrite the harness resets lane N's
  server while the browser browsed 8899, and the isolation was imaginary.
- Isolation unit is one server process per port; `/__fixture/reset` swaps a
  single module-global wholesale.
- `params` must be a JSON-encoded STRING. A nested object is stored as `""`
  (or refused 409 on a workflow row) and the agent wakes at `about:blank`.
- Every `public` task is read_only; every consequential task points at the
  local fixture.

## Extension — offline and under duress

```sh
node extension/tests/run_all.mjs        # 42 suites, ~60s, no browser, no LLM
node proof/extension_smoke.mjs          # 10 checks; exit 1 = backend, 2 = Chrome arm
node proof/extension_stress.mjs --owner-ref=<ref> --port=29401 --fixture=...
```

`extension_stress.mjs` covers what a mock cannot: a banking goal refused
pre-LLM, a read-only task at a live submit control, a browser killed
mid-commit, two browsers on one owner, a stale row, and tab-per-errand.

Two rules it enforces on itself, both learned the hard way:

- **An infrastructure ending is not evidence.** "permits stayed 0" is also true
  when the model 402'd before the run reached a button. Scenarios whose
  assertion is "nothing bad happened" first establish that anything happened;
  otherwise they return SKIP, never PASS.
- **Count only what this errand did.** A long-lived browser accumulates a tab
  per finished job, so counting every tab on the fixture origin reported
  `peak_tabs=10` for a single claim. Snapshot before queueing and diff.

## Facts worth keeping

- Poll filter, character for character (`background.js:73-75`, mirrored in
  `extension_smoke.mjs` and `battery/job.mjs`):
  `status="queued" && owner_ref="<REF>" && workflow_id!="" && lane!="research"`.
- `BLOCKED_DOMAINS` and the financial pre-flight return **`needs_user`**, not
  `awaiting_confirm`. Both alarms fire every **30s**, not 10s.
- The extension holds no vendor key: it stores the marker `"backend-proxy"` and
  calls `POST /agent/llm`. A missing key on the BACKEND looks exactly like a
  broken extension.
- A fresh `--user-data-dir` per code change is mandatory: the service worker's
  module graph is cached in the profile.
- `proof/test_extension.py`, `test_full_chain.py`, `test_pairing_live.py` and
  `browser_battery.py` predate owner_ref scoping and hardcode Linux paths.
  Shape references only; do not run them.
- `pytest tests/ --ignore=tests/test_day_zero_oracle.py` is 833 tests in ~9s
  (the ignored one needs playwright, which is not installed here).
