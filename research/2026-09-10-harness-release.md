# Harness test candidate — September 10, 2026

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

At creation of this record, Git/CI publication and deployments are pending.
Later evidence is appended below. Local green is not live or device proof.

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
