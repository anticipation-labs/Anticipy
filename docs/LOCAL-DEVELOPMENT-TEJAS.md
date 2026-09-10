# Tejas's Mac: safe development and release checks

Verified 2026-09-08. The older `LOCAL-DEVELOPMENT-MAC.md` describes Omar's
machine and historical setup, not this checkout.

## Checkout and tooling

- Product source: `/Users/tejasskaushik/Developer/anticipy/anticipy`, branch
  `cloudflare-backend`. `main` is another lineage; do not merge it into this
  branch to "sync everything."
- Website: sibling `aniticipy-web`, a separate repository and release.
- Node 24.20.0; product Python virtualenv is `.venv` (Python 3.11.16).
- Root `node_modules` is a Git-ignored symlink to the locked Worker install,
  matching CI. This lets root-level local D1 tests find Wrangler 4.129.0
  without consulting npm's registry or skipping their database assertions.
- API Worker: `migration/workers`; brain container: `brain` plus
  `migration/workers/brain`; installed browser source: `extension`; iPhone:
  `app/ios`.
- Command Line Tools/Swift are installed. **Full Xcode and an iOS Simulator
  are not installed on this Mac.** Swift logic tests are usable; they do not
  compile the complete SwiftUI application. Install Xcode through Apple for
  local simulator/device development, or require CI's simulator compilation.
- Poppler is available to inspect the replacement PDF guide. It is a
  documentation tool, not a runtime requirement.

## Credentials: deliberately not auto-loaded

The team file stays at `/Users/tejasskaushik/Developer/anticipy/.env`, **outside
both repositories**, with mode `0600`. Do not paste its contents, stage it,
copy it into frontend assets, or bulk-upload it to a Worker.

Inspect it without displaying or activating values:

```sh
.venv/bin/python proof/audit/local_env_preflight.py \
  --env-file /Users/tejasskaushik/Developer/anticipy/.env
```

Exit 0 means a private, nonempty, simple-format file was inspected. It does
**not** mean credentials are valid, an owner is authorized, or deployment is
ready. Output explicitly distinguishes these states. Unknown field names and
all values are omitted. No app module, network client, or environment loader
is invoked.

The supplied `ANTICIPY_PB` and `ANTICIPY_BACKEND_URL` both point to the **live**
`https://api.anticipy.ai`, not localhost. `ANTICIPY_OWNER_ID` and
`TWO_HANDS_OWNER` are never adopted as the customer's test account. Obtain the
fresh TestFlight account's identity from the consenting tester first.

Why not move everything into root `.env.local`? `overnight/_env.py` loads that
file automatically. Several older gates then read unscoped customer data,
send paid model requests, or create/cancel synthetic jobs on the live API.
Read the [gate safety classification](../research/2026-09-08-browser-customer-journey.md)
before running any of them. Never `source` an unreviewed dotenv file.

Local `.dev.vars*` and `.env*` are Git-ignored. If a local Worker needs private
values later, use a minimal **test-only** set next to its Wrangler config, not
the whole team file. Prefer mocked providers and local D1/R2. Do not use
`wrangler dev --remote` or `d1 execute --remote` for a local test.

Cloudflare separates local dotenv files from deployed Worker secrets.
`secret put` immediately creates/deploys a new Worker version, so it is not a
harmless way to "check" a credential. See the
[official secrets documentation](https://developers.cloudflare.com/workers/configuration/secrets/).

## What is already configured

Names-only checks on 2026-09-08 confirmed:

- GitHub CI has Cloudflare account/token, ASC key ID/issuer/private key,
  internal diagnostic key, and the SendBlue webhook secret.
- `anticipy-api` has its service/auth/internal/vault secrets, Composio
  API/webhook secrets, OpenRouter, and SendBlue credentials/sender/webhook.
- `anticipy-brain` has the service token, backup storage secrets, OpenRouter,
  SendBlue credentials/sender, and search credentials.

These are **presence checks, not provider authentication/effect tests**.
SendBlue/ASC/Cloudflare keys absent from the local team file are therefore not
automatically missing from production. No production secrets were replaced.
The brain secret-list command needs the explicit team account ID because the
CLI can access two accounts; the API config and CI identify the intended
account as `114587b715e702461766369b01d42fc7`.

## Offline verification

First read `HARNESS-LAWS.md`, `CLAUDE.md`, and `AGENTS.md`. Preserve existing
work; stage/commit named files only. Before product edits:

```sh
git status --short --branch
sh app/ios/Tests/run_all.sh
```

Use the virtualenv, not an unrelated global Python installation. Component
commands (from the product root unless indicated):

```sh
.venv/bin/python -m pytest -q
npm --prefix migration/workers test
npm --prefix migration/workers run typecheck
npm --prefix migration/workers/brain test
npm --prefix migration/workers/brain run typecheck
node extension/tests/run_all.mjs
sh app/ios/Tests/run_all.sh
.venv/bin/python proof/audit/check_extension_package.py
git diff --check
```

Keep live credentials out of these processes. On this Mac, outbound network
can additionally be refused by running an offline command beneath:

```sh
CLOUDFLARE_LOAD_DEV_VARS_FROM_DOT_ENV=false WRANGLER_SEND_METRICS=false \
npm_config_offline=true \
/usr/bin/sandbox-exec -p '(version 1)(allow default)(deny network-outbound)(allow network-outbound (remote ip "localhost:*"))' \
  node extension/tests/run_all.mjs
```

Use the same prefix with `.venv/bin/python -m pytest -q -rs` for the combined
Python/local-D1 run. `npm_config_offline=true` keeps npm resolution local;
the OS policy is the separate boundary that refuses external requests.

Only loopback clients are allowed by that policy; external outbound calls are
refused. Without the loopback exception the extension's real local HTTP
deadline test fails with EPERM before it can measure a timeout. A blocked-network failure
must be investigated, never relabelled as a product regression or bypassed by
quietly giving the suite production access.

## Release is deliberate

### September 9 toolchain update

On this Mac the Command Line Tools update changed `MacOSX.sdk` to SDK 27.0,
whose SwiftUI typecheck requires the missing `SwiftUIMacros` compiler plugin.
The same unchanged onboarding check, and the complete pre-edit iOS suite,
passed with the already-installed SDK 26.5 selected for the process:

```sh
SDKROOT=/Library/Developer/CommandLineTools/SDKs/MacOSX26.5.sdk \
CLOUDFLARE_LOAD_DEV_VARS_FROM_DOT_ENV=false WRANGLER_SEND_METRICS=false \
npm_config_offline=true \
/usr/bin/sandbox-exec -p '(version 1)(allow default)(deny network-outbound)(allow network-outbound (remote ip "localhost:*"))' \
  sh app/ios/Tests/run_all.sh
```

This does not change `xcode-select`, install a compiler, or provide the missing
iOS SDK. Full iOS application compilation remains a separate Xcode/CI gate.
Use the explicit SDK only while that directory exists on this machine; do not
suppress a new compiler failure or assume this path exists on another Mac.

For the isolated Chrome geometry gate, an existing bundled Playwright runtime
can be supplied through `ANTICIPY_PLAYWRIGHT_MODULE`. Obtain its path from the
Codex workspace-dependency tool instead of assuming an old npm cache survives.

### Release boundaries

Keep backend, website, extension and iOS evidence separate. No `deploy.sh`,
blanket pushes/merges, account resets, or restored production reminder cron
are part of local setup.

1. Finish the reviewed patch and relevant offline checks. For SwiftUI
   changes, require actual simulator compilation in Xcode/CI as well.
2. Browser source changes need manifest, `ENGINE_BUILD`, iPhone expected
   version and stale-version tests in agreement. `sh extension/build-zip.sh`
   regenerates all three tracked ZIP aliases; check package bytes afterward.
   A new ZIP does not update an already-installed unpacked extension.
3. iOS changes need matching build values in `project.yml` and the committed
   `Anticipy.xcodeproj/project.pbxproj` in the same commit. CI checks for Apple
   build collisions; don't guess the installed build from the source number.
4. A qualifying push builds/tests iOS. Only intentional workflow dispatch or
   `[ship]` in the commit **subject** uploads. Signed builds come from CI.
   Successful upload/processing does not prove tester access or installation.
5. Backend `brain-deploy.yml` is manual. API mode also runs remote migrations
   and synthetic-account release probes. Brain mode can replace active owner
   containers. Review and authorize that blast radius separately from the
   no-injected-jobs customer journey; do not dispatch as a "check."
6. Verify the live API revision, served extension bytes, App Store Connect
   processing/tester access, and installed build/extension. Then repeat the
   actual customer journeys on the controlled account.

The acceptance map and remaining gaps are tracked in
[current readiness](../research/2026-09-08-customer-readiness.md), with linked
iOS, browser, and service path inventories. Local green is not live verified.

The September 10 follow-up is recorded in [the harness release ledger](../research/2026-09-10-harness-release.md).
Use [the remaining acceptance sequence](HARNESS-ACCEPTANCE-TEJAS.md) for the
separate CI, release and consented device/provider gates.
