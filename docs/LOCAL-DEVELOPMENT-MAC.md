# Anticipy development on Omar's Mac

Prepared 2026-09-06 from `cloudflare-backend` at
`d93682f80b14c40d5d4ba445ea6333e4a5a58e33`. The governing files are
`HARNESS-LAWS.md`, `CLAUDE.md`, and `AGENTS.md`.

## The workspace

Use **`/Users/omarebrahim/Anticipy`**. This is a fresh checkout from
`https://github.com/anticipation-labs/Anticipy`, tracking only
`origin/cloudflare-backend`. It has full branch history, with older blobs fetched
on demand (`--filter=blob:none`); it is not shallow. That history is required by
the build-number gate. Local pulls are configured to fast-forward only.

The older checkouts are in `/Users/omarebrahim/Anticipy-Cleanup-2026-09-06/`.
Their archive/upload operation is separate and was still in progress at setup.
Its `START-HERE.md` and `STATE.md` describe recovery. Do not run old relocation
scripts against this newly created checkout.

## Where the parts belong

| Path | Role |
|---|---|
| `app/ios/Anticipy/` | SwiftUI app, capture, account state, feed, settings, backend client, and device hands |
| `app/ios/Anticipy.xcodeproj` | Committed Xcode project; includes the iOS app, widget, Mac target, and UI tests |
| `app/ios/project.yml` | Project specification and build/version settings; maintain alongside the Xcode project |
| `app/ios/Tests/` | 63 shell-invoked gate legs at this baseline, mostly direct Swift compilation |
| `app/macos/` | Companion capture sources and Mac checks |
| `migration/workers/src/` | Cloudflare API: records/auth, account boundaries, model proxy, connections, messaging, API hands, and cron handlers |
| `migration/d1/` | D1 schema and explicit migrations |
| `brain/` | Python interpretation, orchestration, memory, owner workers, and container entry point |
| `migration/workers/brain/`, `migration/config/` | Cloudflare Container/DO control and brain deployment configuration |
| `extension/` | Chrome execution, pairing, effect/confirmation boundaries, and offline tests |
| `backend/pb_public/` | Static pages and download ZIPs staged into the API Worker |
| `backend/pb_hooks/`, `backend/pb_migrations/` | PocketBase compatibility/history; not the current local server |
| `firmware/` | Pendant source, artifacts, build receipts, and host checks; hardware proof is separate |
| `spike/two-hands/` | Hand routing and connections contracts imported by production code and tests |
| `tests/`, `proof/`, `overnight/` | Python invariants, explicit proof harnesses, and readiness/live gates |
| `docs/`, `design/`, `research/` | Product specifications, decisions, audits, and dated evidence |
| `website/` | A static artifact; this branch is not the unrelated website lineage on `main` |
| `.github/workflows/` | CI checks, release, ASC queries, and explicit migration/deployment jobs |

The basic flow is speech or typed input → API event → brain with context and
memory → work/confirmation state → the appropriate hand → evidence back to the
app. A passing local check proves only the portion it exercises.

## Tools and generated files

| Item | Prepared location or version |
|---|---|
| macOS / architecture | 26.3 / Apple Silicon, 16 GiB RAM |
| Xcode / Swift | Xcode 26.6 at `/Applications/Xcode.app`; Swift 6.3.3 |
| Simulator SDK / runtime | iOS 26.5 |
| Node | 24.20.0, installed under `~/.nvm/versions/node/` to match CI's Node 24 major |
| Python | 3.11.12 in this checkout's `.venv`, matching CI's Python 3.11 major |
| Worker dependencies | `migration/workers/node_modules`, installed with `npm ci` from the lockfile |
| Root `node_modules` | Local symlink to the Worker install, so repo-root `npx --no-install wrangler` gates can resolve it |
| Local configuration and launchers | `work/mac-dev/`, ignored by Git |
| Local D1/R2/DO state | `work/mac-dev/state/`, separate from wire-test state and all remote databases |
| Xcode build products | `~/Library/Developer/Xcode/DerivedData/Anticipy-Local/` |
| Setup logs and screenshot | `~/Library/Logs/Anticipy/setup-2026-09-06/` |

The normal shell resolves Node through a Hermes-managed binary and npm through
an older NVM installation. The existing npm prefix also conflicts with `nvm use`.
The project environment below selects matching executables by PATH, without
rewriting global shell files or npm settings. XcodeGen is installed on this Mac,
but this workflow does not run it: maintain the two committed project files by
hand as instructed. No signing credentials were imported.

## Start a development session

```sh
cd /Users/omarebrahim/Anticipy
. work/mac-dev/env.sh
git status --short --branch
```

Run the local API in a terminal and leave that terminal running:

```sh
./work/mac-dev/start-worker.sh
```

It serves `http://127.0.0.1:8787`, using the current Worker source with local
D1, R2, and Durable Objects. Its config is `work/mac-dev/wrangler.json`: no
production routes, cron schedule, provider keys, or remote bindings. It carries
development-only auth values and uses `--local` explicitly. It serves assets
directly from `backend/pb_public/`. Stop it with Ctrl-C. If port 8787 is already
serving this checkout, use that process rather than starting another.

```sh
curl --fail http://127.0.0.1:8787/api/health
```

The schema was initialized with:

```sh
wrangler d1 execute DB --local --config work/mac-dev/wrangler.json \
  --persist-to work/mac-dev/state --file migration/d1/schema.sql
```

No production data was copied. This gives the app and API a development surface;
it does not start a model-backed brain or connect messaging/provider accounts.
Production credentials remain in their existing stores and the preserved local
vault at `/Users/omarebrahim/Anticipy-Env-Vault-2026-09-06/`. Do not copy old
environment files wholesale into this new checkout.

## Build and open iOS

Run the gate before code changes:

```sh
sh app/ios/Tests/run_all.sh
```

Build the committed project for the simulator:

```sh
xcodebuild -project app/ios/Anticipy.xcodeproj -scheme Anticipy \
  -configuration Debug -destination 'generic/platform=iOS Simulator' \
  -derivedDataPath "$HOME/Library/Developer/Xcode/DerivedData/Anticipy-Local" \
  build CODE_SIGNING_ALLOWED=NO
```

Launch the installed build against the local Worker:

```sh
./work/mac-dev/open-ios.sh
open -a Xcode app/ios/Anticipy.xcodeproj
```

The dedicated device is **Anticipy Development**, iPhone 17 Pro, UDID
`4CC99375-02A4-47F6-9CA7-25805CDBD06D`. The launcher supplies the existing
`backendURL` preference as a launch argument (`http://127.0.0.1:8787`). The
machine-local **Anticipy Local** Xcode scheme supplies the same arguments;
select that scheme and this simulator for local debugging. The shared
**Anticipy** scheme retains the production default. User schemes live under
ignored `xcuserdata/`; no shipping source was changed to redirect traffic.

The simulator reached the signed-out onboarding screen. Microphone behavior,
Bluetooth, background capture, and a real person's week need their own device
proofs; a successful simulator compile does not establish those.

## Other checks

After sourcing `work/mac-dev/env.sh`, from the repo root:

```sh
python -m pytest -q -rs
node extension/tests/run_all.mjs
npm test --prefix migration/workers
npm run typecheck --prefix migration/workers
npm run test:llm-wire --prefix migration/workers
```

The wire harness starts its own local Worker and fake provider and cleans them
up. It exercises the real runtime without provider keys. Its database is
separate from the development server's custom `work/mac-dev/state` directory.

To stage the static download assets used by the standard Worker config:

```sh
npm run stage:assets --prefix migration/workers
npm run check:assets --prefix migration/workers
```

`python overnight/tape_gate.py` exits **1 by design** at this baseline: five
registered legacy meaning rules remain. Its other legs pass. Do not weaken the
gate to make it green; replacements follow HARNESS-LAWS Law 5. Production gates
in `overnight/` and scripts in `proof/` need individual review before use: some
write rows, invoke models, or exercise real hands.

## Commits and releases

`CURRENT_PROJECT_VERSION` is **158** and `MARKETING_VERSION` is **1.1.1** at the
baseline. An iOS source change must raise the build number in both
`app/ios/project.yml` and `app/ios/Anticipy.xcodeproj/project.pbxproj`, in the same
commit as the source. Update every relevant occurrence. The final iOS gate leg
detects source changes since the last bump; an increased, synchronized working
tree number can make it green before commit.

Stage by exact path. Check the shared index, then use
`git commit ... -- <your exact paths>`; never sweep another agent's staged work
into a bare commit. Do not use `git checkout --` to discard work.

Releases use `.github/workflows/ios-testflight.yml` on `cloudflare-backend`.
Uploads require a manual dispatch or the literal `[ship]` in the **commit
subject**. A push is not a release. This setup did not dispatch that workflow.

One current CI gap is recorded in the setup baseline: an ordinary qualifying
push runs the logic gate and XcodeGen, but all `xcodebuild` steps are ship-only.
Its final “Built and tested” message therefore does not prove an app compile.
The local build above provides a real compile baseline for this source.

Ask Apple about a specific build without inviting anyone:

```sh
gh workflow run asc-query.yml --ref cloudflare-backend -f build=158
```

Leave invitation inputs blank. Inspect the returned run's Apple verdict and
tester availability, not just GitHub's conclusion. The setup query confirmed
158 valid/internal testing and also listed 159 valid. Re-query at release time.

Older files, notably `CLAUDE-ONBOARDING.md`, `migration/CUTOVER-STATE.md`, and
parts of `app/ios/README.md`, describe earlier branch/deployment arrangements.
They are historical evidence, not instructions to restore PocketBase, switch
branches, regenerate this project, or upload from this laptop.
