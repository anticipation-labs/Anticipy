# Isolated browser runner safety — 2026-09-11

## Scope and outcome

Approved harness-only repair to `proof/audit/run_real_browser.mjs`. No product
source, scenario wording, fixture outcome expressions, thresholds, or production
configuration changed. No real browser, model, account, provider, gateway, or
website was accessed in these tests.

The actual runner module is evaluated in a fresh Node VM per test. Filesystem,
Playwright, Chrome plumbing and the agent boundary are synthetic; real source
executes its initialization, route handler, result assertions, and cleanup. The
synthetic filesystem refuses all unrecognized reads and live-budget operations.
The synthetic native fetch refuses dispatch. OS outbound networking is denied as
an additional boundary. This is harness-boundary evidence, not a model-semantic
or real-Chrome pass.

## Red → green

Command (each output redirected to its distinct log):

```sh
PYTHON_DOTENV_DISABLED=1 CLOUDFLARE_LOAD_DEV_VARS_FROM_DOT_ENV=false \
/usr/bin/sandbox-exec -p '(version 1)(allow default)(deny network-outbound)' \
node --experimental-vm-modules --test proof/audit/run_real_browser_safety.test.mjs
```

- Before the repair: actual exit **1**, **7 passed / 28 failed**. Evidence:
  `work/ben-browser-safety-red-20260911.log`.
- After the repair, unchanged tests: actual exit **0**, **35 passed / 0 failed**,
  no skips. Evidence: `work/ben-browser-safety-green-20260911.log`.

The red failures were behavioral: acquired handles were not always closed,
known fixtures accepted unexpected methods, and a read-only case could mutate
the synthetic appointment fixture. They were not failures due to an absent
new helper or a source-text match.

## Repairs and covered paths

- A nested `finally` attempts context close and browser close after successful
  browser launch. Failure closing the context does not skip browser close.
- Setup, dynamic imports, DOM text capture, screenshots and trace-stop failures
  still reach cleanup. Agent failures remain failed results with cleanup.
- Passing artifacts and the success exit code are published only after cleanup
  succeeds. Context-close, browser-close and report-write failures cannot publish
  a passing report in these regressions.
- Known fixture pages, including owner and authored read-only pages, require
  exact GET requests. POST, PUT, DELETE, HEAD, OPTIONS and PATCH to page fixtures
  are refused and reported in `refusedNetworkAttempts`, with methods retained
  in `network`.
- Only the exact synthetic calendar endpoint accepts POST, and only for the
  explicitly writable appointment scenario. The read-only scenarios cannot
  create a record. Wrong path, query, origin or method cannot create a record.
- The authorized appointment fixture still records the expected entry once and
  satisfies the original exact title/time/count assertion.
- Reports now explicitly include `semanticReviewRequired: true`; the existing
  mechanical pass field is not represented as semantic certification.

## Remaining evidence limits

The existing content oracles intentionally remain unchanged. Compare checks
both prices and links but does not prove the answer selected the cheaper store.
The injection oracle checks the meeting date but does not alone reject an answer
claiming compliance with the malicious footer. The login oracle does not prove
untouched input fields. Capacity wording may reject a valid synonymous answer.
Independent review of answer, trace, refused requests and actual synthetic
effects remains necessary after the separately authorized real model/Chrome run.

Playwright HTTP interception is not a whole-process network sandbox. The real
run must retain its external-network denial with only the separately metered
loopback gateway allowed; no personal profile should be used. This test suite
does not certify service-worker, websocket, actual Chrome launch, or provider
behavior. No claim is made about production deployment, device audio, SMS,
connector accounts, or the unresolved legacy speech-cursor fuzz failures.

The ECC defect/pipeline workflow shaped this repair: first preserve behavioral
red evidence, then make the narrow boundary fix, then require independent review
before running the paid browser scenarios. No commit or publication was made.
