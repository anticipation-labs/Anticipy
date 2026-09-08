# Browser and demo readiness — 8 September 2026

Baseline: `cloudflare-backend` at `7f319726`. The user supplied the engineering
handoff and requested browser readiness for a VC presentation. Governing laws,
current README, and the layer audit were read before task work.

## Scope and evidence

- Trace the brain-to-browser queue; repair demonstrated execution defects.
- Exercise production browser mapping/clicking in isolated Chrome on synthetic
  pages. A scripted model or Chrome API adapter is transport evidence, not proof
  of model judgment or the installed extension in an owner's session.
- Repair the connected-API read boundary with explicit owner isolation.
- Repair the two reproduced memory reliability defects named in the handoff.
- Deploy the already-reviewed website download repair if current build and
  Cloudflare authorization permit it, then verify the public download gate.
- Keep live judgment, SMS, phone, and owner-data gates UNPROVEN when the required
  credentials or devices are unavailable. Previously verified release facts in
  the handoff are not being re-audited without a change that requires it.

## Baseline observations

- Main checkout is on `cloudflare-backend`; website is on `cloudflare`.
- Untracked `.wrangler/`, `desktop/`, and `engine/` predate this task and are
  preserved. Those engine/desktop directories belong to the earlier lineage.
- Shell has no `ANTICIPY_SERVICE_TOKEN`, `OPENROUTER_API_KEY`, or
  `ANTICIPY_BACKEND_URL`. Asked for the approved env-file path, never key values.
- Cloudflare CLI is authenticated and lists the account named by the handoff.
- Current extension already includes the previous geometry/request-deadline
  repairs and the 0.18 alarm repair; fresh failures must be demonstrated.

## Release verdict

**Not yet certified for a live autonomous VC demo.** The public download repair
is live and verified. The browser/brain/API repairs below are tested local
source changes, not a new production release. No commit or push was made and
`main` was not touched. The supplied live-model and device gates remain
UNPROVEN; local test counts do not replace those gates.

## Live website repair

- Deployed the already-built `aniticipy-web` / `cloudflare` download repair to
  the account and Worker specified in the handoff. Website source stayed clean.
- Cloudflare version: `28dd265c-ce18-4463-a4c3-9aa8ad838bde`.
- Stranger gate leg 11 now **PASS LIVE**: `https://www.anticipy.ai/download`
  redirects to `https://api.anticipy.ai/mac/Anticipy-for-Mac.zip` and serves the
  committed Mac 1.1.1 (171) archive byte-for-byte, 1,148,615 bytes.
- The full stranger gate at this working-tree state is **9/11**, not 11/11:
  legs 1 and 2 detect the newly edited `extension/background.js` differing from
  the existing packaged/live 0.18.0 extension. That is pending release work,
  not evidence that the website download failed. All other legs passed.

## Local repairs and evidence

| Area | What changed | Evidence / boundary |
| --- | --- | --- |
| Browser queue | Exclude phone/calendar and supervised-read lanes; show picking-up state only after verified lease ownership | Five SQLite-backed queue scenarios; full extension suite 84/84 |
| Direct task honesty | No-op queue results create no active loop/action claim; failed writes clear the goal and return a retry message only for explicit requests | Four regressions red before the patch; six direct-path tests green, including real-card controls |
| Connected API hand | Service-only, owner-scoped connection read; bind planned arguments to goal/source/owner/revision; recheck before vendor execution and protect writeback | Connections route 29, execution route 51, API hand 74 checks; separate test owners; no live API hand proof |
| Memory | Rank before the 300-row cap; durable per-candidate deferral preserves successful facts and original provenance | Long-history/long-query, rollback, restart and veto regressions; independent adversarial review |
| Container state | Refuse a missing memory snapshot when clock state proves previous use | Offline checkpoint tests; both objects absent is still unresolved |
| Inbound SMS | Unknown current phone authority preserves the event for retry; absent sender cannot borrow cached owner identity | Fresh-read, outage/recovery, wrong-owner and app-channel tests; real delivery not proven |
| Nudge phone safety | Existing profile wins over sign-up phone, including removal; recheck immediately before sending; release cannot resurrect deleted/revised rows | Wiring 66, nudge 71, ask 42 checks over local fixtures/SQLite |
| Model usage | Normalize reported Gemini usage, including refused/empty responses; retain unknown cost and missing counters as unknown | 83 focused LLM/gateway/budget tests; no price or performance improvement invented |

Independent agents reviewed the changes. Review found and repaired two memory
edge cases, a correction during an API catalog await, and nudge-release
resurrection after deletion. A request already dispatched to a vendor cannot
be retracted by these checks; that temporal limitation remains explicit.

Detailed reports:

- [Browser queue / release preparation](2026-09-08-browser-queue-ownership.md)
- [API hand and ownership](2026-09-08-api-connection-route.md)
- [Memory reliability](2026-09-08-memory-reliability.md)
- [Inbound authority and retry](2026-09-08-inbound-authority-retry.md)
- [Usage ledger](2026-09-08-llm-usage-ledger.md)

## Final combined checks

- `.venv/bin/python -m pytest -q`: **3107 passed, 2 skipped** (33.17 seconds).
  The two skipped tests require the live model. An earlier run overlapped
  source editing and its introspection test failed; the isolated test and the
  complete frozen-source rerun passed. Earlier red TDD runs are not final gates.
- `migration/workers`: complete `npm test` and `npm run typecheck` **passed**.
- `migration/workers/brain`: all fleet/erasure/status tests **passed**;
  typecheck **passed** after installing its missing locked local dependency.
- `extension`: all **84 suites passed** (74.28 seconds).
- `sh app/macos/Tests/run_all.sh`: all **7 suites passed**, including real Mac
  source typechecking against the macOS 26 SDK.
- `sh app/ios/Tests/run_all.sh`: **all suites passed**; build 171 source pin
  unchanged. This is a logic gate, not a new TestFlight upload or device test.
- `git diff --check`: **passed**.

## Browser observation, not simulated completion

The browser-verification skills were used to open the existing compiled
Cloudflare website locally in an isolated Chrome session. `/app` rendered the
account entry UI and its controls; the JavaScript-error inspection was empty.
No account was created and no authenticated state was exercised. Local logs
also showed two existing 404s for Vercel analytics/speed-insight scripts on
Cloudflare; this telemetry mismatch remains cleanup work, not a proven healthy
authenticated web app. Screenshot: `output/playwright/vc-app-0908.png`.

`proof/audit/check_browser_click_geometry.mjs` ran the production page map and
real Chrome CDP clicks on isolated synthetic pages. Document and nested smooth
scroll cases each clicked the intended target exactly once; detached targets
were refused. Evidence: `output/playwright/browser-click-geometry/results.json`
and screenshots. This proves DOM geometry, not model judgment, extension
installation/pairing, or an owner request reaching a real browser task.

The temporary website server on port 8891 and the isolated browser session were
closed after verification. Personal browser profiles were not used.

## Local environment changes

- Created ignored `.venv` using Python 3.11 and installed the test dependencies
  named by `system-invariants.yml` (pytest, requests, httpx, tzdata, boto3,
  playwright, numpy).
- Installed the missing locked `@cloudflare/containers` dependency in
  `migration/workers/brain` with `npm ci --ignore-scripts --no-audit --no-fund`.
  No package versions or lockfiles were changed.
- Used cached agent-browser tooling and the Mac's Chrome for the isolated
  browser checks. The empty browser config is at
  `../browser-verification.json`, outside the repositories.

## Test-harness incident

The first placement of four new nudge tests was after the existing test file's
fetch-mock restoration. Those four synthetic requests reached SendBlue with
fixture credentials/numbers and all were rejected HTTP 401. No successful
delivery was reported; no real credential or owner data was used. The tests
were moved inside the mock's lifetime before further execution. The corrected
tests then demonstrated four local failures before the patch and passed after
it. Independent review verified their mock lifetime. This incident was
disclosed to the user during the work; the run is not described as zero
external test requests.

## Remaining gates and next authorized work

1. Supply only the path to the team's approved test env file containing
   `ANTICIPY_SERVICE_TOKEN`, `OPENROUTER_API_KEY`, and `ANTICIPY_BACKEND_URL`.
   Do not paste values. The shell has none of these, and no private token
   stores were searched to work around their absence.
2. Run real-model, isolated-owner browser request → saved job → claim → DOM
   action → verified receipt → user-visible result. The historical no-job
   event's exact cause is not established without its live trace. A scripted
   decision cannot close this gate.
3. Prepare a coordinated extension release: four version pins, all archive
   aliases, source/archive equality, API asset release, actual installation and
   reload; rerun stranger gate. No artifact or iOS version was changed here.
4. Release and live-gate the tested backend/brain changes with two authorized
   test owners. Do not silently deploy them merely because local tests pass.
5. Prove SMS inbound/outbound with a real team test phone and provider receipts;
   SMS yes-to-presented-revision binding is still unfinished. No real iPhone,
   email session, meeting or pendant was exercised this turn.
6. Missing-both-R2-objects recovery needs authoritative initialization/history,
   not a guess that absence means signup. Long-lived deferred judgments need
   operational visibility; the source now reports their count, not a live
   durability proof.
7. The handoff's legacy word-overlap/regex meaning controls, expensive profile
   judge, briefing window, poll cadence, onboarding APNs/pendant promises, and
   measured speaker attribution remain unfinished. Usage instrumentation alone
   does not prove lower cost or a complete product.

For a presentation before those gates close, demonstrate only the specifically
verified capabilities and disclose the limitations. Do not present autonomous
browser completion, SMS delivery, persistent memory recovery, or pendant
capture as proven by these local suites.
