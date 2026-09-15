# Anticipy

Anticipy is a proactive assistant. A phone, a pendant, or a Mac meeting
recorder captures speech; a per-owner server brain interprets it with context
and memory; approved work reaches the owner's own browser, connected apps, or
device "hands"; and every outcome comes back to the phone as a receipt.

**Work on `cloudflare-backend`.** It is the source of record. `main` is an
older, unrelated lineage and is never pushed to; pull requests target
`cloudflare-backend`. Read [HARNESS-LAWS.md](HARNESS-LAWS.md) before changing
anything: meaning belongs to a model with context, never to a regex, word
list, or threshold.

## Components

| Component | Path | What it is |
| --- | --- | --- |
| iPhone app | `app/ios/` | SwiftUI: listening and on-device transcription, pendant BLE (`app/ios/Anticipy/BLE/`), replies, connected apps |
| Mac app | `app/macos/` | Meeting recorder; unsigned build in CI, signed release through `mac-release.yml` |
| Chrome extension | `extension/` | MV3 "hands" in the owner's own logged-in Chrome; packaged into three ZIP aliases under `migration/workers/public/` |
| API Worker | `migration/workers/` | Cloudflare Worker (TypeScript) with D1, R2 and a Durable Object; the production API |
| D1 schema and migrations | `migration/d1/` | `schema.sql` plus dated additive migrations |
| Brain Worker + Python brain | `migration/workers/brain/`, `brain/` | Containers fleet, one container per owner, running the Python brain image |
| Pendant firmware | `firmware/` | Zephyr candidate for the XIAO nRF52840 Sense; host-checked here, not built or flashed |
| Gates and proofs | `overnight/`, `proof/` | Scoreboards and live or loopback proofs with green / red / UNPROVEN semantics |
| Python tests | `tests/` | pytest suite over the brain, the gates and a local D1 |
| Contracts | `migration/spec/CONTRACT.md`, `migration/workers/ARCHITECTURE.md` | Behavioural oracle and the Worker reference |

## Data flow

```text
pendant ─BLE─► iPhone ─┐
Mac recorder ──────────┼─► events (D1) ─► brain (one process per owner) ─► jobs ─► hands ─► receipt ─► iPhone
typed / text reply ────┘                   memory.db held in R2             browser · API · device
```

[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) explains each hop and the
contracts the runtimes share.

## Run every suite

```sh
PYTHON_DOTENV_DISABLED=1 python -m pytest -q
(cd migration/workers && npm test && npx tsc --noEmit)
npm test --prefix migration/workers/brain && npm run typecheck --prefix migration/workers/brain
node extension/tests/run_all.mjs
sh app/ios/Tests/run_all.sh
sh app/macos/Tests/run_all.sh
sh firmware/source/tests/run_firmware_tests.sh
python3 proof/audit/check_extension_package.py
```

[docs/TESTING.md](docs/TESTING.md) says what each suite proves, what it does
not, how to run them offline, and how the installed-extension proof rig works.

## Read next

- [Current status](docs/EOD-READINESS-2026-09-13.md): release evidence and the
  remaining-work board.
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): runtimes, shared contracts,
  and the evidence ladder.
- [docs/RELEASE.md](docs/RELEASE.md): the ordered release runbook and
  rollback notes.
- [CONTRIBUTING.md](CONTRIBUTING.md): branch model, path-limited commits, the
  iOS build-number rule, and the review expectation.
- [SECURITY.md](SECURITY.md): how to report a vulnerability and where the
  private-data boundary sits.
- [HARNESS-LAWS.md](HARNESS-LAWS.md): the six laws that outrank everything
  else in this tree.
- [docs/README.md](docs/README.md): index of every document under `docs/`.

## License

MIT; see [LICENSE](LICENSE). Third-party code vendored in this tree is listed
in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
