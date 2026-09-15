# The installed-extension proof rig

A real unpacked extension in a real branded Chrome, paired to a stand-in
phone, working against a loopback Worker, a scripted model provider and a
fixture site — with the production host blackholed for the life of the
browser. It records what an INSTALLED extension does across install, task,
restart, backend outage and owner separation. Loopback only: nothing here
deploys, and no production account, secret, database or provider is
reachable.

## Files

| File | Role |
| --- | --- |
| `chrome.mjs` | Launches Chrome (Playwright's `chrome` channel, 137 or newer) as a persistent context with `--enable-unsafe-extension-debugging`, loads `extension/` through CDP `Extensions.loadUnpacked`, maps the production host to NOTFOUND with `--host-resolver-rules`, and proves the blackhole from inside the extension before anything else. Every storage read or write runs inside one of the extension's own pages. |
| `local_worker.py` | `up` / `down` for the real `migration/workers/src/index.ts` under `wrangler dev --local` over a fresh local D1 built from `migration/d1/schema.sql`, with the model proxy pointed at the fake provider through the test-only `LLM_PROVIDER_BASE`. The environment is rebuilt from `PATH`, `HOME` and `TMPDIR` only. |
| `fake_provider.mjs` | An OpenRouter-shaped provider on loopback: verifies audit prompts, answers a page map naming the fixture button with one click, then `done`. Logs request shapes only. `POST /__reset` clears its click ledger. |
| `fixture_site.mjs` | The venue pages (`/widget`, `/wrapper`, `/scroll`, `/two-hop`, `/plain`). A click on the widget button is recorded by the SITE (`POST /__clicked`); `GET /__clicks` reads the ledger and `POST /__reset` clears it. |
| `phone.py` | The stand-in phone: `owner` (create and sign in through the public owners endpoints), `pair` (look up and claim a pair code with the account token), `unpair` (release the way the app does; `--legacy` leaves `owner_ref` on the row), `mint` (a read-only browser job through the real `brain.workflow` engine), `job` (read a row). Refuses any non-loopback base. |
| `run.mjs` | The scenarios, in order, each writing a row to `work/installed-extension/results.json`. |
| `__init__.py` | Makes the directory importable as `proof.audit.installed_extension`. |

## Prerequisites

- A branded Chrome, version 137 or newer, installed on the machine (no
  Chrome for Testing download is needed).
- A Playwright runtime. This repository does not vendor one, so `chrome.mjs`
  looks at `ANTICIPY_PLAYWRIGHT_MODULE` first and then at
  `node_modules/playwright/index.mjs` under the repository root; with neither,
  it refuses and says so. Nothing is guessed from a home directory.
- A Python interpreter. `run.mjs` uses `ANTICIPY_PYTHON`, then a `.venv` at
  the repository root, then whatever `python3` resolves to. The stand-in phone
  and the Worker controller are standard-library only, so any Python 3.11 or
  newer will do; set the variable if the repository's own virtualenv is
  somewhere else.
- `npm ci --prefix migration/workers` done, so `wrangler` is available under
  `migration/workers/node_modules` (that is where `local_worker.py` invokes
  it from).
- Run from the repository root; `run.mjs` sets `PYTHONPATH` and
  `PYTHON_DOTENV_DISABLED=1` for the Python calls it makes.

## The three loopback servers

| Server | Address | Start |
| --- | --- | --- |
| API Worker | `http://127.0.0.1:8791` (inspector on `8792`) | `python3 -m proof.audit.installed_extension.local_worker up` |
| Fake model provider | `http://127.0.0.1:8796` | `node proof/audit/installed_extension/fake_provider.mjs` |
| Fixture site | `http://127.0.0.1:8797` | `node proof/audit/installed_extension/fixture_site.mjs` |

Start each in its own terminal so its log survives. The Worker writes its
config, pid file, `workerd.log` and persisted D1 under
`work/installed-extension/worker/` (git-ignored) and refuses to start while a
pid file is present. `local_worker.py down` stops it, ends any leftover
`workerd` that names the state directory, and waits for the ports to free.
Options: `--port`, `--provider-port` and `--state DIR` on the Worker;
`--port`, `--log FILE` and `--label` on the provider; `--port` on the site.

## Running

```sh
ANTICIPY_PYTHON=<interpreter> ANTICIPY_PLAYWRIGHT_MODULE=<playwright index.mjs> \
  node proof/audit/installed_extension/run.mjs [--headed] [--scenario NAME,...]
```

`--headed` shows the browser. `--scenario` limits the run to the named
scenarios; the launch and install rows always run because everything after
them needs a paired browser. The process exits 1 if any row records
`ok: false` or an error.

## Rotating the rig between passes

The Worker's D1 persists across `down` / `up` — the `outage` scenario relies
on that — so a fresh pass needs a fresh state directory:

1. `python3 -m proof.audit.installed_extension.local_worker down`
2. Move `work/installed-extension/worker/` aside (or delete it).
3. `python3 -m proof.audit.installed_extension.local_worker up`
4. `curl -X POST http://127.0.0.1:8797/__reset` and
   `curl -X POST http://127.0.0.1:8796/__reset` (`run.mjs` also resets both
   before every task).

The Chrome profile is a fresh temporary directory per launch unless a
scenario reuses one (`restart` does, deliberately).

## Scenario rows

| Row | What it records |
| --- | --- |
| `launch` | Extension id, the proven blackhole result, the Chrome version, the profile path. |
| `launch:targets` | The CDP targets present after load, the service worker among them. |
| `install:register` | The extension registered itself against the loopback Worker: a record id, a pair code and a token in storage; exactly one `agents` row for this browser. |
| `install:pair` | The stand-in phone claimed the code; the heartbeat taught the extension its owner and model. |
| `task` | A read-only browser job minted through the real brain engine was claimed, run against the two-hop iframe page, and landed `done` with a verified receipt; the site saw exactly one click on the widget button. |
| `restart` | Chrome closed and relaunched on the same profile: same identity, still one `agents` row, still paired, a second task done. |
| `outage` | The Worker stopped for about 100 seconds and restarted: identity and token not rotated, the popup reported the queue unreachable, then a third task done. |
| `separation` | The phone unpaired; the owner pressed "New code"; a second owner claimed the new code; the popup shows none of owner A's task text; a job minted for owner A stays queued and unclaimed. |
| `phone-repair` | Owner B released the browser from the app; owner A re-claimed the SAME code without pressing New code; B's profile, key and task text did not reach A; a task ran for A on the same credential. |
| `phone-release-legacy` | The same release in the older shape (`paired:false` with `owner_ref` left on the row): the extension still wipes profile and key and reads "Not linked"; A re-pairs with the same code; a task runs. |

**Eight of these ten rows carry a verdict.** `launch` and `launch:targets`
record what the browser looked like and have no pass/fail field, so they
cannot go red and must not be counted as passes: a run that is entirely green
is "8/8 verdict rows", not "10/10". Two further rows appear only on a
condition: `restart:extId` if the extension id changed across the relaunch,
and `error` if a scenario threw.

## Where results land

`work/installed-extension/results.json` — one JSON array, rewritten after
every row, with an `at` timestamp per row. The owner stand-ins are written to
`work/installed-extension/owner-a.json` and `owner-b.json` (mode 0600) and
hold loopback-only tokens. The directory is git-ignored; copy reviewed,
redacted findings under `research/`, never the raw files.

## What it does not prove

- **A scripted model.** The provider answers a fixture with a fixture; nothing
  about model judgement is measured.
- **No real customer site or account.** The fixture site is the only origin
  the job visits; the owners are synthetic local accounts.
- **Not the served ZIP.** The rig loads `extension/` unpacked. Parity of the
  download with the source is `proof/audit/check_extension_package.py`; the
  live download is verified in [docs/RELEASE.md](../../../docs/RELEASE.md).
- **Not the owner's real Chrome profile.** Fresh profiles only: nothing about
  an existing install, its stored credential state, or its update path.
- **Not production.** The production host cannot resolve for the life of the
  browser, by construction and by check.
