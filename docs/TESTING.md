# Testing

Every suite in the tree, the command that runs it verbatim, what a green run
proves, and what it does not. Nothing in the suites touches production; the
gates that can are named in the last section so nobody runs one by accident.

## Ground rules

- **Offline.** Suites run with dotenv loading disabled and, where practical,
  with outbound network refused by the OS (prefix below). A suite that fails
  because the network is blocked is investigated, never relabelled as a
  product regression or quietly handed production access.
- **Read the exit code of the command, not of the pipeline's last stage.**
  `out=$(sh run.sh 2>&1); rc=$?` — a trailing `| tail` reports `tail`'s
  status, which is how a red gate has been reported as green before.
- **Three states.** Green is exit 0. Red is non-zero. **UNPROVEN is exit 2**:
  the instrument could not measure (no toolchain, no live control, no
  credential) and says so. UNPROVEN is never read as green, and a predicate
  is never softened to reach green (HARNESS-LAWS.md Laws 2 and 3;
  CLAUDE.md).
- **Stage by path.** `git status --short --branch` before you start; another
  session may be mid-task in the same tree (AGENTS.md).

### The offline prefix (macOS)

```sh
CLOUDFLARE_LOAD_DEV_VARS_FROM_DOT_ENV=false WRANGLER_SEND_METRICS=false \
npm_config_offline=true \
/usr/bin/sandbox-exec -p '(version 1)(allow default)(deny network-outbound)(allow network-outbound (remote ip "localhost:*"))' \
  <command>
```

Loopback stays open because the extension's HTTP-deadline test and the local
Worker need it; everything outbound is refused by the OS, a separate boundary
from `npm_config_offline`.

## The suites

### Python: brain, gates, local D1

```sh
PYTHON_DOTENV_DISABLED=1 python -m pytest -q
```

Python 3.11 in a virtualenv. CI installs `pytest requests httpx tzdata boto3
playwright numpy` (`.github/workflows/system-invariants.yml`); there is no
requirements file. The local-D1 tests drive the real Worker under
`wrangler dev --local`, so run `npm ci --prefix migration/workers` first and
give the repository root a `node_modules` symlink to that install, exactly as
CI does (`ln -s migration/workers/node_modules node_modules`; the symlink is
git-ignored). `pytest.ini` limits collection to `tests/`; `proof/` scripts
are run directly (`PYTHONPATH=. python3 proof/<script>.py`) and exit at
import, which is why they are kept out of pytest.

Proves: brain and storage invariants, workflow law, the gates' own logic, the
migration applier (`tests/test_d1_additive.py`), and the Worker's D1 behaviour
over a fresh local database. Does not prove: anything live, any real
provider, comparative model quality.

### API Worker

```sh
cd migration/workers && npm test && npx tsc --noEmit
```

Node 24 (the suites run under `node --experimental-strip-types`). `npm test`
is the `&&`-chain in `package.json`; a red file stops the chain, and `npm ci`
refuses a drifted lockfile. Optional wire suites — `npm run test:llm-wire`,
`test:sms-wire`, `test:service-wire` — run `scripts/*_local.sh`, which prove
the model proxy, the SMS routes and the account routes on a real local
`workerd` with no vendor key, no carrier and nothing deployed.

Proves: every route and policy against `migration/spec/CONTRACT.md`, and the
types. Does not prove: the deployed bytes, D1 on Cloudflare, provider
behaviour.

### Brain Worker (the Containers fleet)

```sh
npm test --prefix migration/workers/brain && npm run typecheck --prefix migration/workers/brain
```

Proves: fleet planning, erasure and status logic, types. Does not prove: a
container runtime, R2, or the Python image; those are proved only by the brain
release job (`proof/audit/live_brain_release.py`, run from
`brain-deploy.yml`).

### Chrome extension

```sh
node extension/tests/run_all.mjs
```

Offline: an in-memory `chrome` (`extension/tests/chrome_mock.mjs`), a
hand-built DOM for `page_map.js` (`fake_page.mjs`), and a service-worker
lifecycle rig (`rig_lifecycle.mjs`). Proves: never-foreground, pairing
lifecycle races, crash reconciliation, model-verdict shapes, transport
deadlines. Does not prove: a real Chrome, the served ZIP, a real site, a real
model.

### iOS

```sh
sh app/ios/Tests/run_all.sh
```

Every suite compiles the real pure-Foundation sources with `swiftc`; no
simulator, no signing, no Xcode project. `set -eu`: the runner stops at the
first red suite. The last leg is the build-number gate
(`run_build_number_tests.sh`): red while iOS source has moved since
`CURRENT_PROJECT_VERSION` last did, which means "bump it before you commit",
not "the code is wrong".

On a Mac with only the Command Line Tools, point the compiler at an installed
macOS SDK that carries the SwiftUI macro plugin:

```sh
SDKROOT=/Library/Developer/CommandLineTools/SDKs/MacOSX<version>.sdk sh app/ios/Tests/run_all.sh
```

`ls /Library/Developer/CommandLineTools/SDKs/` lists what is installed. This
does not change `xcode-select` and does not provide an iOS SDK.

Proves: policies, cursors, receipts, copy contracts. Does not prove: that the
app compiles or runs; that is `ios-candidate.yml` (a simulator build on every
pull request into `cloudflare-backend`) and `ios-testflight.yml`.

### Mac

```sh
sh app/macos/Tests/run_all.sh
```

Same shape as iOS: `swiftc` over the real sources against the macOS 26 SDK.
Proves: no audio leaves the Mac, the archive and library policies, the
transcript wire, offline delivery, the app shell type-checks. Does not prove:
the app builds; the `mac` job in `system-invariants.yml` runs an unsigned
`xcodebuild` for that.

### Firmware (host-compiled halves)

```sh
sh firmware/source/tests/run_firmware_tests.sh
```

Compiles the pure halves (`recovery_touch.c`, `transport_safety.c`) with the
host `clang` against `firmware/source/tests/hoststub/`. Its own last line says
it: **NOT a build, NOT hardware.** There is no Zephyr, `west`, or ARM
toolchain in this tree, and `overnight/firmware_gate.py` reports UNPROVEN
until a build and a flash exist.

### Extension package parity

```sh
python3 proof/audit/check_extension_package.py
```

Reads the three ZIP aliases under `migration/workers/public/`, checks every
packaged file byte-for-byte against `extension/`, checks the manifest version
equals `ENGINE_BUILD` in `background.js`, and refuses if the aliases differ.
Prints the shared SHA-256. The API deploy job runs it before deploying.

### Real-Chrome geometry gate

```sh
ANTICIPY_PLAYWRIGHT_MODULE=<path to a playwright index.mjs> \
  node proof/audit/check_browser_frame_clicks.mjs
```

Drives the shipped `agent_loop.js` and `page_map.js` in a headless branded
Chrome over synthetic fixture pages with a scripted step model. Proves trusted
clicks into nested frames and refusal when a control is covered. Not a real
site, not a real model.

### The installed-extension rig

A real unpacked extension in a real Chrome, against a loopback Worker, a
scripted provider and a fixture site, with the production host blackholed:
install, task, restart, outage, owner separation, and the two phone-side
release shapes. See
[proof/audit/installed_extension/README.md](../proof/audit/installed_extension/README.md).

### Isolated task flow

`proof/audit/run_isolated_task_flow.py`: input → real task formation → local
Worker/D1 claim → server result → feed, on fresh phone-less local accounts,
under the OS network denial. Read the docstring for its two modes before
running it.

## Gates that can touch live systems

`overnight/*.py` are scoreboards, not unit tests. They load a root
`.env.local` if one exists (`overnight/_env.py`) and announce which names they
found; several read customer rows, send paid model requests, or create and
cancel synthetic jobs on the production API. Read the
[gate safety classification](../research/2026-09-08-browser-customer-journey.md)
before running any of them, and never `source` an unreviewed dotenv file.
`overnight/tape_gate.py` is red on purpose (Law 2): green means the tape is
gone, not written down.

Live verification after a deploy is a release step, not a test; see
[RELEASE.md](RELEASE.md).

## Last check before a commit

```sh
git diff --check
```
