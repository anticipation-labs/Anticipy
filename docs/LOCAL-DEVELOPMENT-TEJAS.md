# Development-Mac deltas: Command Line Tools only

Machine-specific notes for a Mac that has the Command Line Tools and no
Xcode. The general commands live in [TESTING.md](TESTING.md) and
[RELEASE.md](RELEASE.md); this file records only what differs on such a
machine. The older [LOCAL-DEVELOPMENT-MAC.md](LOCAL-DEVELOPMENT-MAC.md)
describes a different, historical setup.

## Checkout and tooling

- Branch `cloudflare-backend`; `main` is another lineage and is never merged
  in to "sync everything".
- The website is a separate repository and release.
- Node 24; a Python 3.11 virtualenv at `.venv` inside the checkout. Use
  `.venv/bin/python`, never an unrelated global interpreter.
- The repository root `node_modules` is a git-ignored symlink to the locked
  Worker install (`migration/workers/node_modules`), matching CI, so the
  local-D1 tests find Wrangler without consulting the registry.
- Command Line Tools and Swift are installed; **full Xcode and an iOS
  Simulator are not.** The `swiftc` logic suites run; the complete SwiftUI
  app does not compile here. Simulator and device builds come from Xcode on
  another machine or from CI (`ios-candidate.yml`).
- Poppler is available for inspecting the PDF guides under `output/pdf/`. It
  is a documentation tool, not a runtime requirement.

## The SDK selection that keeps the iOS suites green

A Command Line Tools update can move the default `MacOSX.sdk` to a release
whose SwiftUI typecheck needs a compiler plugin the tools do not ship. Select
an installed SDK explicitly for the process:

```sh
SDKROOT=/Library/Developer/CommandLineTools/SDKs/MacOSX<version>.sdk \
CLOUDFLARE_LOAD_DEV_VARS_FROM_DOT_ENV=false WRANGLER_SEND_METRICS=false \
npm_config_offline=true \
/usr/bin/sandbox-exec -p '(version 1)(allow default)(deny network-outbound)(allow network-outbound (remote ip "localhost:*"))' \
  sh app/ios/Tests/run_all.sh
```

This does not change `xcode-select`, install a compiler, or provide an iOS
SDK. Use it only while that SDK directory exists on the machine; do not
suppress a new compiler failure with it or assume the path exists elsewhere.

## Credentials are not auto-loaded

The team environment file lives **outside** the repository with mode `0600`.
Do not paste its contents, stage it, copy it into frontend assets, or
bulk-upload it to a Worker. Inspect it without displaying or activating
values:

```sh
.venv/bin/python proof/audit/local_env_preflight.py --env-file <path to the file>
```

Exit 0 means a private, nonempty, simple-format file was inspected — not that
any credential is valid, that an owner is authorized, or that deployment is
ready. Values and unknown field names are never printed, and no app module,
network client, or environment loader is invoked.

Why not move it into the root `.env.local`: `overnight/_env.py` loads that
file automatically, and several older gates then read unscoped customer data,
send paid model requests, or create and cancel synthetic jobs on the live API.
Read the [gate safety classification](../research/2026-09-08-browser-customer-journey.md)
before running any of them. Never `source` an unreviewed dotenv file.

If a local Worker ever needs private values, use a minimal test-only set next
to its Wrangler config, never the whole team file; prefer mocked providers and
local D1/R2; never `wrangler dev --remote` or `d1 execute --remote` for a
local test. `wrangler secret put` creates and deploys a new Worker version
immediately, so it is not a harmless way to "check" a credential.

Presence of the CI and Worker secrets was confirmed by name in early
September; that is a presence check, not a provider authentication test. The
inventory of names and locations is `migration/runbooks/SECRETS.md`.

## Playwright for the real-Chrome proofs

`proof/audit/check_browser_frame_clicks.mjs` and the installed-extension rig
take an existing Playwright runtime through `ANTICIPY_PLAYWRIGHT_MODULE` (the
path to a `playwright/index.mjs`) and a Python interpreter through
`ANTICIPY_PYTHON`. Set both explicitly; do not assume an old cache survives.

## Release from this machine

Releases go through the workflows in [RELEASE.md](RELEASE.md); this machine
contributes reviewed, path-limited commits and offline evidence. Local green
is not live verified. The remaining consented device and provider gates are
tracked in [HARNESS-ACCEPTANCE-TEJAS.md](HARNESS-ACCEPTANCE-TEJAS.md).
