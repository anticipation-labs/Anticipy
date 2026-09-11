# Isolated model gateway: actual HTTP boundary review

September 11, 2026. Independent, bounded test-only review by Ben.

## Result

**20 tests passed, actual exit 0, 1.15 seconds.** This includes the previous
18 gateway tests and two new actual-loopback HTTP regressions. No blocker was
found within the requested cases. This is not a provider, production backend,
or billing-system certification.

The new matrix sent 13 rejected requests through the production nested HTTP
handler, not directly into `handle()`: missing/wrong authentication; wrong
route; unknown, duplicate and invalid audit query; malformed JSON; non-object
JSON; invalid, zero and oversized Content-Length; Transfer-Encoding; and a
truncated body terminated at the client socket. Each returned its expected
non-success status, left the ledger byte-for-byte unchanged, and dispatched
zero provider calls. Responses did not expose the synthetic provider key.

A fourteenth, valid synthetic HTTP request succeeded, reserved before provider
dispatch, recorded its audit label, and reconciled exactly $0.001. This was one
mocked completion and **zero actual model calls or charges**.

The other new test ran the production lifetime timer: the server thread exited,
its listening socket closed, and a subsequent connection to that port failed.
Both tests use newly allocated ephemeral ports and private temporary state.
No connection was made to the separately running funded gateway on port 8794.

## Isolation and changes

Read README, AGENTS, CLAUDE, HARNESS-LAWS and the regression-testing skill.
`ecc:ai-regression-testing` guided the actual-boundary tests. Only
`tests/test_isolated_model_gateway.py` was changed; production gateway and app
source were not modified. The test intercepts server construction solely to
learn the OS-assigned port, preserving the real handler and HTTP server. Only
`post_model` is replaced at the provider boundary. No real dotenv, key, owner,
microphone, browser or production data is accessed.

Baseline before additions: 18/18, exit 0. Final command:

```sh
PYTHON_DOTENV_DISABLED=1 \
/usr/bin/sandbox-exec -p '(version 1)(allow default)(deny network-outbound)(allow network-outbound (remote ip "localhost:*"))' \
  .venv/bin/python -m pytest tests/test_isolated_model_gateway.py -q
```

Captured the pytest process exit separately from the displayed log tail.
Evidence: `work/ben-actual-http-gateway-20260911.log`.

Frozen SHA-256:

```text
0d010604a405bb9cc86f52ef5663f6ddc6bdd634ec4f1b99ce4244f0db3d2bcb  tests/test_isolated_model_gateway.py
917795ed5330795f56d4ef601e134a1fd2c054e74c7330926ef8f8495c42bd25  proof/audit/isolated_model_gateway.py
```

Root review requested before handoff. No commit, push or deployment.
