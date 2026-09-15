# Contributing

## Branch model

- `cloudflare-backend` is the source of record and the only branch pull
  requests target. `main` is an older, unrelated lineage: never push to it,
  never merge it in.
- Topic branches come off `cloudflare-backend`. Firmware hardware work may
  live on its own branches; agree on packet, header and codec changes in both
  directions before changing either endpoint
  ([docs/FIRMWARE-COLLABORATION.md](docs/FIRMWARE-COLLABORATION.md)).

## Read first

[HARNESS-LAWS.md](HARNESS-LAWS.md) outranks everything else, then
[CLAUDE.md](CLAUDE.md) and [AGENTS.md](AGENTS.md). The law that catches people
first: no regex, word list, or threshold may decide what a human's words
mean. If a change you are about to make does that, stop and say so.

## Path-limited commits

More than one person or agent works in a tree at once, and the index is
shared.

```sh
git status --short --branch        # anything staged that is not yours means someone is mid-task
git add <new files>                # by name; never -A, never .
git commit -- <paths>              # commits those paths and nothing else
```

`git commit -- <path>` only commits tracked paths, so a new file is
`git add`ed first. Never `git checkout -- <file>` to undo uncommitted work;
back new files up with `cp` first. Read the exit code of each command, not of
a pipeline's last stage.

## The iOS build-number rule

Any change under `app/ios/` moves `CURRENT_PROJECT_VERSION` in **both**
`app/ios/project.yml` and `app/ios/Anticipy.xcodeproj/project.pbxproj` (four
occurrences), in the **same commit** as the source. The last leg of
`sh app/ios/Tests/run_all.sh` is red until you do. The Mac target shares the
project, so `app/macos/` changes move it too.

Extension changes move four values together: `version` in
`extension/manifest.json`, `ENGINE_BUILD` in `extension/background.js`,
`expectedExtensionVersion` in `app/ios/Anticipy/AnticipyApp.swift`, and
`expected` in `app/ios/Tests/StaleExtensionTests.swift` — then rebuild the
ZIP aliases (`sh extension/build-zip.sh`) and commit all three.

## Which suite runs for which directory

| You changed | Run locally | CI |
| --- | --- | --- |
| `brain/`, `tests/`, `overnight/` | `PYTHON_DOTENV_DISABLED=1 python -m pytest -q` | `system-invariants.yml`, `test` job |
| `extension/` | `node extension/tests/run_all.mjs`; `sh extension/build-zip.sh`; `python3 proof/audit/check_extension_package.py` | `system-invariants.yml`, `test` job |
| `migration/workers/`, `migration/d1/` | `cd migration/workers && npm test && npx tsc --noEmit` | `system-invariants.yml`, `worker` job |
| `migration/workers/brain/` | `npm test --prefix migration/workers/brain && npm run typecheck --prefix migration/workers/brain` | `system-invariants.yml`, `worker` job |
| `app/ios/` | `sh app/ios/Tests/run_all.sh` | `ios-candidate.yml` on a PR; `ios-testflight.yml` on push (build only unless `[ship]`) |
| `app/macos/` | `sh app/macos/Tests/run_all.sh` | `system-invariants.yml`, `mac` job |
| `firmware/` | `sh firmware/source/tests/run_firmware_tests.sh` | none; `overnight/firmware_gate.py` is UNPROVEN until a build and a flash exist |
| `.github/workflows/` | `ruby -ryaml -e 'YAML.load_file("<file>")'` | the workflow itself |

Full commands, the offline prefix, and what each suite proves and does not:
[docs/TESTING.md](docs/TESTING.md).

## The review expectation (Law 6)

The owner is not the review loop. Before a PR is opened, an adversarial pass
— yours or a fleet's — has tried to kill the change against the laws, the
tests, and the recorded failures under `research/`, and the PR says what that
pass tried. A violation the owner catches that you could have caught is a
process failure and is logged as one. Self-review to convergence, then ship.

## Documentation

Public-safe, always: no absolute personal paths, no e-mail addresses or phone
numbers, no owner record ids, no provider budgets or credential dates, no invite links, no
secret values. Refer to paths relative to the repository root. Docs are
additive: dated notes are not rewritten, and a new state gets a new dated
file ([docs/README.md](docs/README.md) indexes them).

## Pull requests

Use the template (`.github/pull_request_template.md`). Its checklist is the
definition of "ready": gates run and named, versions aligned, ZIPs rebuilt and
committed, docs public-safe, and no `[ship]` in the title unless a TestFlight
upload is intended — a squash-merge takes its commit subject from the title,
and a push to `cloudflare-backend` whose subject carries `[ship]` uploads.
