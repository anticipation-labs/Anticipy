# Unified release handoff — 2026-09-01

## Release state

- The release started from Git commit `3f3251c7`, which was identical to
  `origin/jose_anticipy_system` after a fresh fetch. Jose had not pushed a
  newer revision that needed merging.
- iPhone build 120 is `VALID` in App Store Connect and is the current
  TestFlight release. It contains the calm Home, swipeable Done deck,
  execution-hand feedback, developer diagnostics, transcript relocation,
  floating-indicator repair, and restart-safe action delivery.
- The production browser agent is package 0.11.1. Exactly one unpacked package
  is enabled in the active Chrome profile and its paired agent has a fresh
  production heartbeat. This developer-installed copy does not gain automatic
  Chrome Web Store updates until a store release replaces it.
- The brain worker remains healthy on Railway deployment
  `956af962-8e46-4302-9603-bd3be03fc4b0`. Its production ears/brain gates pass.
- The backend is healthy on Railway deployment
  `51c5ccb5-3821-41c5-8a0c-6f776fba5f86`.
- The Mac meeting recorder is version 1.1.0, build 119. Apple accepted notary
  submission `7b342b45-3166-437d-ae5d-c741b828e705`; the app is signed,
  stapled, Gatekeeper-accepted, and universal (`x86_64 arm64`). The release ZIP
  SHA-256 is
  `079aee239d2e55665490913ecfdc6a241dd020aceeca9256f8ea66034a820f36`.
  The same bytes are installed at `/Applications/AnticipyMac.app`, committed
  under `backend/pb_public/mac/`, and served from the production backend.

## Machine cleanup

The invalid legacy `/Applications/Anticipy.app`, installed Mac build 111, and
a stale executable launched from a deleted temporary build were all stopped.
The two app bundles were moved to Trash as
`Anticipy-legacy-2026-09-01.app` and `AnticipyMac-build111-2026-09-01.app`, so
the cleanup is recoverable. Only the installed build 119 process is running.

## Deployment repair

The repository-level `.railwayignore` excludes `backend/` on purpose for the
worker image. Deploying the repository root therefore risks omitting the
backend. `backend/deploy.sh` now creates a disposable isolated backend context,
checks the Dockerfile and Mac artifact, deploys that context directly to the
production backend service, and cleans the staging directory. This is the
canonical backend deploy path.

## Verification

- `pytest -q`: 2,426 passed.
- `extension/tests/run_all.mjs`: all 69 suites passed.
- Both macOS capture-core and meeting-archive suites passed.
- The installed, repository, and live-download Mac artifacts all report build
  119, pass strict code-signature, stapling, and Gatekeeper checks, and the
  repository and production ZIP checksums match exactly.
- The production backend health endpoint returns HTTP 200.

## Proof still owned by people or platforms

The software release is assembled and live, but three external proof legs are
not manufactured by automated tests: a physical long YouTube/listening run,
real SMS delivery on a verified phone number, and the cold-stranger usability
walkthrough. Speaker identification also remains deliberately unavailable
because its prior on-device binary prevented App Store processing. Those are
explicit release constraints, not silently relabelled successes.
