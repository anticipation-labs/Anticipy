# Independent harness-only review — Tom, 2026-09-11

Reviewed the six frozen files/hashes in
`research/2026-09-11-harness-honesty-repair.md`; all hashes matched the author's
freeze. No author files were changed by this review.

**Verdict: no blocking defect found in the scoped changes.**

- Reply selectors now reject explicit empty, unknown, duplicate, and malformed
  selection before reading the gateway token or creating accounts. Omitted
  selection means the complete named matrix, not zero work. The summary cannot
  pass empty/partial/duplicate or non-boolean-success results. The gateway is an
  explicit loopback HTTP URL; error output drops original exception/provider text.
- The legacy queue overrides preserve `touches`, hold `world`, and reject
  unsupported non-null `act` before POST. They are explicitly historical and
  unsafe to treat as current acceptance drivers. Their bootstrap/main paths were
  not imported or run; old auth/effect/cleanup behavior is not certified.
- The actual API route returns the retired carrier's 410 before parsing or
  persistence. The rewritten contract matches this and checks absent rows with
  local D1. The SendBlue comparison retains its full canonical row oracle;
  existing active-carrier cases remain present.
- The shell runner now owns unique scratch states for both Workers, passes the
  configured state to the D1 oracle, disables dotenv/process env/package fetches,
  and explicitly supplies `/dev/null` as the Worker env file. Cleanup targets
  only these fresh directories, preserves the log, and no longer erases the old
  default/fixed local state. No remote D1 flag or live provider send is introduced.

Independent execution: `tests/test_harness_honesty.py` — **30 passed, actual exit
0**, under a scrubbed environment, dotenv/metrics disabled, npm offline, and OS
external-network denial (loopback permitted). Evidence:
`work/tom-harness-honesty-review-20260911.log`. Shell syntax and scoped diff
whitespace checks also exited 0. I did not independently rerun the author's
21-case real-workerd wire result or access a provider/device/live account.

These checks verify harness selection, plumbing, historical compatibility, and
retirement assertions. They do not prove model accuracy, browser/device success,
live SMS delivery, or every connector. Root's fresh combined/release gates remain
separate.
