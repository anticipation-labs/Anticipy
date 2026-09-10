# Harness test candidate — September 10, 2026

## Current verdict

The reviewed candidate is deployed to the existing API and brain, and
**1.1.1 (174)** is processed and available to the approved private TestFlight
pilot group. CI and bounded synthetic checks passed. This is a testable release,
not a claim that the full live harness or public App Store release is ready.
The local real-model greeting returned HTTP 402; successful model behavior,
installation of 174 and the controlled physical-device journey remain open.

## Scope and authority

The owner approved committing/pushing the reviewed repairs on
`cloudflare-backend`, deployment for harness testing, and TestFlight delivery
through the existing private pilot group (including its notification/review
steps). This is not a public App Store submission. No main change, force push,
secret publication, unrelated account inspection or real-message retry is
authorized by this release record.

The upstream workflow-only commit `b209d8f01ec9638975f630f4d128aece6ffea58f`
was fast-forwarded without overwriting local repairs. All 55 reviewed candidate
source/test hashes matched after integration. Unrelated `.wrangler/`, `desktop/`
and `engine/` files and private account investigation notes are excluded.

## Candidate and independent verification

Source version: **1.1.1 (174)**, with all six build pins aligned. The last
user-confirmed installed phone build is **172**, not this candidate.

The repairs cover audio finalization and task ownership, account/erasure
callback fencing, visible receipt progression, durable in-app failure replies,
content-free classifier/SMS diagnostics, exact provider/phone identity and
connector authorization/retry fences. They do not introduce meaning heuristics,
blindly retry uncertain sends or enable new connector permissions.

Fresh, outbound-denied local checks completed before this release:

- Full Python: **3,389 passed, 2 intentionally skipped live-model tests**.
- Full iOS logic gate: all registered suites passed, including build identity.
- Analyzer lifecycle: **169 checks, zero failures**, plus **10 mutation controls**.
- Capture lifecycle: **68 checks, zero failures**, plus **11 mutation controls**;
  **120/120** repeated phrases across synthetic sessions.
- Actual engine source typechecked against installed Apple macOS speech APIs;
  this is not an iOS application compile.
- API Worker: all 44 configured test entrypoints and typecheck passed.
- Brain Worker: all three configured test entrypoints and typecheck passed.
- Browser extension: **84 suites passed**; actual isolated Chrome document and
  nested-scroll geometry checks **2/2 passed**.
- All three downloadable extension aliases match source **0.18.1**, SHA-256
  `430518d8eb50186f0e3d6af4caf1b8754cd231e21899a997dc65984af7f97afc`.

Actual exit codes were checked. Independent reviewers checked audio lifecycle,
app integration and metadata privacy. The final manifest digest is
`96cc446910a2c52bc9cc95c5a8b174020e838fc4910d78b334b218ea3fa22fff`.
It identifies local candidate files, not a deployment or a Git commit.

## Release sequence and current status

1. Commit explicit reviewed paths and push without a ship marker. This runs
   full iOS simulator compilation and system CI without Apple upload.
2. Require successful CI for that exact commit. No full Xcode/iOS SDK is
   installed locally, so the actual committed-app compile is a required gate.
3. After green CI, use one deliberate TestFlight dispatch on the verified
   branch tip. Record the actual upload build (Apple collision handling can
   change it), processing verdict and private-pilot outcome separately.
4. Deploy only reviewed backend components to their verified existing targets;
   preserve configured secrets/provider variables and record live identity.
   Do not run broad customer-data checks merely because a workflow bundles them.
5. Follow [the device acceptance sequence](../docs/HARNESS-ACCEPTANCE-TEJAS.md).

At creation of this record, Git/CI publication and deployments were pending.
Later evidence is appended below. Local green is not live or device proof.

### Publication and deployment preflight

- Published candidate `7968926eaf2e3aae2c57b291e278335ae02d53d1` on
  `cloudflare-backend`; the remote tip was read back and matched. Exactly 59
  reviewed paths were committed; all earlier private research remains local.
- Build-only [iOS CI](https://github.com/anticipation-labs/Anticipy/actions/runs/34484415662)
  and [system CI](https://github.com/anticipation-labs/Anticipy/actions/runs/34484415661)
  completed successfully for that exact commit. Final evidence follows below.
- API package dry run passed with outbound networking denied. The existing
  API target is `anticipy-api` / `api.anticipy.ai`; the brain is `anticipy-brain`
  in the same verified team account. No new environment was provisioned.
- Actual pre-release API version: `3a11055c-1c77-4ed0-a0a9-0ecf84cd5f62`,
  revision `24af7506a3c73cb13af1628fe73938629607ea2a`.
- Actual pre-release brain version: `77a02e72-2625-4876-aec5-a9111a5ee7ff`,
  revision `cb2010957877eec0a8c67138b57060dc1bef3110`. Runtime source is
  `8d54551681dcd736b2744de07f5763575812a78f257a8205f5324207e20978d8`.
- Cached operational baseline: ten running workers, ten current snapshots,
  zero failed cleanups; all ten match the existing strong-model release check.
  No owner identities, sender values, conversations or memory contents were
  emitted. Health reads did not start work.
- Deployed discovery capacity is **100**. An eventual brain dispatch must
  explicitly preserve 100; the workflow's default 1 is not appropriate.
  Deployed and committed allowlists match the single existing synthetic e2e
  fixture, so the preflight's database GET does not fetch customer memory.
- Independent deployment review checked additive/idempotent API migrations,
  synthetic fixture exclusion, cached health semantics and unchanged capacity.
  The API proof creates/removes its own `.invalid` accounts, including one
  fictional-phone erasure fixture; it makes no provider send. If it fails after
  signup but before cleanup registration, inspect for that fixture before retry.
- The brain rollout mode is explicitly `immediate`, with ordinary platform
  process drainage; it is not gradual despite an old workflow comment. Preserve
  secrets/configuration and verify the running source, not just deploy exit 0.
- The full brain delta from its deployed revision includes earlier reviewed
  recovery/memory fixes as well as this candidate. It adds a durable deferred
  consolidation queue. Old code cannot drain that new queue even though SQLite
  retains the rows, so a rollback needs a data-aware plan, not just promotion of
  the old version. No rollback or database rewrite was performed here.

### API release — verified

[API run 34485031942](https://github.com/anticipation-labs/Anticipy/actions/runs/34485031942)
completed successfully at 13:50:24 UTC for the candidate. Both migrations,
deployment and all **37 live synthetic checks** passed. The proof removed its
own disposable accounts; no real account was erased and no provider send ran.
Active API version: `81e4ad35-24f4-444a-bba6-8ba81dfe394d`. A separate public
health read returned HTTP 200 and candidate revision
`7968926eaf2e3aae2c57b291e278335ae02d53d1`.

System CI completed successfully: Python **3,389 passed, two skipped** in
139.88 seconds; browser **84 suites passed**; API/brain Worker checks and
unsigned universal Mac build all passed. The only Python warning is a test
docstring escape deprecation, not a provider/audio runtime failure.

The iOS CI logic gate passed and the actual committed simulator compile passed
at 13:52:19 UTC. The workflow completed successfully; all signing, upload,
processing and private-pilot steps were skipped in this build-only run.

### Brain release — verified

[Brain run 34485285291](https://github.com/anticipation-labs/Anticipy/actions/runs/34485285291)
was dispatched on the exact candidate after system CI and API live verification.
Explicit capacity: **100**. All 21 checked-in brain variables compared equal to
the deployed plaintext values before dispatch; separately configured bindings
and secrets are retained with `--keep-vars`. Expected new running source:
`81d6697a859c56041489c206f96794443e5ade02a4f281574dc415180aa621f5`.
The workflow subsequently completed successfully. Active brain version:
`e01c3f59-fc9a-404e-a970-d7fe102adef0`. During startup all ten processes reached
the new source before their first snapshots were current; the verifier correctly
remained red until all **10/10** workers passed running-source/model/snapshot
checks, with zero failed cleanups and the exact candidate revision. Only then
did the release finish green. No stale-code or partly-warm result was accepted.
Post-deployment version readback separately confirmed all 21 configured
variables unchanged, capacity 100, the same secret binding names, and the
intended expected-runtime source hash. Secret values were not read or emitted.

### TestFlight release — available to the private pilot

Both exact-commit CI runs completed successfully. Root verified their final
conclusions and rechecked the branch tip before the single approved
[TestFlight dispatch 34485412047](https://github.com/anticipation-labs/Anticipy/actions/runs/34485412047).
The run completed successfully on the exact candidate. Apple accepted upload
**1.1.1 (174)** at 14:02:13 UTC and returned **VALID** at 14:05:15 UTC.
The existing private external pilot group and tester were assigned. After an
initial review-submission state, final exact-build readback was
**IN_BETA_TESTING**, with `ready_to_install=true` and auto-notification enabled.
No second upload or workflow retry was needed. The API's tester-level
`INSTALLED` state is not evidence that this particular build is installed.
The owner was asked to update from 172 and confirm 174 on the physical phone.
No public App Store submission was performed.

The owner subsequently reported **172** with only an **Open** button. The
release workflow's dedicated private pilot assignment does not establish this
owner's tester/build association. That exact association was initially unknown:
the development Mac has no usable ASC signing key, and the scoped browser
check reached Apple's sign-in page. The owner was asked to sign in for the
targeted access check. No new upload, broad tester-directory query, invitation,
account permission change or device uninstall was performed to force access.

After the owner signed in, the scoped App Store Connect UI check established
the cause: the owner's existing private external group contained the exact
intended tester but only builds **169 and 172**. Build 174 was already in
**Testing** and selectable, but had not been attached to this group.

Under the existing harness/TestFlight release approval, the already-approved
**1.1.1 (174)** was added to that exact group. Apple's saved-state readback
showed **one tester, three builds**, including **174 — Testing**. No new tester,
public link, account role, binary upload or additional app review was created.
The owner reopened TestFlight and reported **174 visible and updating**. This
confirms access and an update in progress, not completed installation or a
passed physical-phone harness test. The release workflow itself
was not changed: future releases must verify every intended private group,
not infer this owner's access from a different pilot group's success.

### Browser distribution — verified; installed execution remains open

Independent live GETs of all three public extension ZIP aliases returned HTTP
200, 353,502 bytes each, and the same source-matching 0.18.1 SHA-256 recorded
above. These checks cover the deployed assets, not the user's installed copy.
The browser tool blocked `chrome://extensions` under its URL security policy;
no alternate surface or workaround was attempted. Installed version/enabled
state and authenticated read-only execution still need a permitted observation.

### Live-test utility limitation

Independent source review found that `live_reply_probe.py` does not guarantee
zero provider sends: blank phone suppresses immediate delivery but preserves a
pending reply outbox, and the script restores the number afterward. The existing
`tests/test_reply_delivery.py` blank-phone-then-sweep test proves the delayed
send. Its fixed `real_messages_sent=0` field is not observed evidence. This
script was NOT run, no fixture phone was changed, and no outbox was fabricated
or deleted. The acceptance guide records this restriction.

### Real-model greeting — blocked, not passed

An isolated smoke invoked the actual Conversation and LLM with synthetic local
context and the approved local model credential. Outbound access was restricted
to OpenRouter; backend/task/message-provider operations were blocked. One
judgment-model request returned **HTTP 402**, and the conversation returned
`unavailable` with the existing fallback. No task or memory change, backend
request, external send or retry occurred. This is not proof that the deployed
credential has the same issue. The source/readiness gate remains unproven for
successful live-model answers until the credential/account issue is resolved.

A separate read-only current-key request returned HTTP 200, confirming that the
local key authenticates and has no reported per-key limit. This does not reveal
the account's available credit or prove equality with the deployed key. The
owner/team must check the provider account before another bounded model test;
no guess about which deployed secret to replace is justified by this result.

Private local smoke evidence is kept under ignored `work/`; no credentials or
account billing data are included in this record. The owner was asked to check
the provider account and confirm whether local and deployed keys correspond.
No credits were purchased and no keys or spending limits were changed.

## Remaining acceptance boundaries

Physical iPhone recognition/pause/resume/Stop, a live model answer, matching
visible answer, handset SMS receipt, authenticated installed-extension
execution and each required live connector still require bounded observations.
The historical unavailable answer and handleless SMS attempt do not acquire a
root cause retroactively; new structural diagnostics support a controlled
reproduction. Never blind-retry an unconfirmed SMS attempt.

Pendant decoding remains disabled. Missed negative SMS callbacks can still
leave status unknown; bounded older receipt history is unchanged. Legacy tape
gates remain intentionally red, not waived. No claim of zero flaws or public
release readiness follows from the local checks.
