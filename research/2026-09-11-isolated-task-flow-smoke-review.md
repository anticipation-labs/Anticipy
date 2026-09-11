# Isolated task-flow runner review and smoke — Tom, 2026-09-11

Scope: only `proof/audit/run_isolated_task_flow.py` and the new focused
`tests/test_isolated_task_flow.py`. Root authored the initial runner; Tom reviewed
and repaired the local launch/cleanup boundary. No product source was changed.
The runner still requires independent/root review of these authored repairs.

## Repairs

- Captures PATH/HOME/TMPDIR before clearing the environment, so the selected Node
  and virtualenv tools remain available without inheriting provider credentials,
  backend defaults, proxies, or customer identity.
- Explicitly disables Wrangler process-env inclusion and supplies an empty
  `/dev/null` env file to the local Worker; dotenv and package fetching remain off.
- Covers every context-manager entry failure with cleanup. Schema creation now
  uses a tracked, dedicated process group too, so schema timeout/spawn/readiness
  failures close this runner's group and log. Shutdown targets only the process
  group this runner created, with bounded wait then SIGKILL escalation if needed.
- Preserves the unique private run directory, config, database state, log, and
  result evidence. It does not remove or touch preexisting local state.

## Actual evidence

- Regression first: 4 failed / 5 controls passed, actual exit 1:
  `work/tom-isolated-flow-red-20260911.log`.
- Final focused runner plus independently reviewed harness tests: 43 passed,
  actual exit 0 (13 runner controls + 30 harness controls):
  `work/tom-isolated-flow-green-20260911.log`.
- Actual `--smoke` with real local workerd/D1: all three selected cases passed,
  every created phone-less fixture reported `fixture_deleted=true`, actual exit 0:
  `work/tom-isolated-flow-smoke-20260911.log`.
- Canonical result:
  `work/isolated-task-flow-tjr52k3h/result.json`.
- Ports 18555 and 18556 had no listener after shutdown. The startup log is retained
  beside the result. Scoped whitespace checks were clean.

All tests used a scrubbed environment and OS external-network denial with only
loopback allowed. No gateway key was read, model invoked, provider contacted,
installed browser driven, production service used, commit made, or deployment run.

Smoke uses the actual ReplyDelivery publisher with an explicitly fixed fixture
answer. It proves local API/auth/persistence and durable duplicate suppression;
it does **not** exercise input reasoning, task generation, server research,
verification, browser tasks, device capture, or live SMS. The result correctly
sets `full_product_verified=false`. The `api_requests` list records the runner's
explicit API calls, not every internal brain/backend call.

The real-model path was read, not executed. Its intended boundary is actual
`Anticipy.hear` task formation followed by `run_research_jobs` and
`report_finished_jobs`, with no pre-seeded jobs, browser pairing, or connectors.
It requires a separately approved, budgeted loopback gateway and later semantic
review of the result. Local green does not prove that future path works.

Frozen hashes:

```text
0395290d16d614d51ff4d1ae35646ae8809cda7a3721fc3f59f60a887f3e9edb  proof/audit/run_isolated_task_flow.py
138863c7e0e392e7ba4b18bba58b1603ecdad926320c19b71efadff803c04a2c  tests/test_isolated_task_flow.py
```

## Final oracle review addendum

The hashes above are the earlier launch/cleanup freeze, not the final runner.
Root subsequently corrected the real-mode oracle to read Plan's actual plural
`source_event_ids` and require a verified receipt with evidence. Independent
review reproduced a false-positive on scalar/substring lineage and scalar
evidence. Root then required nonempty lists of nonempty strings, exact input-ID
membership, and `verified is True`, adding five malformed-shape regressions.

**That finding is closed.** Tom independently reran the final runner suite:
19 passed, actual exit 0, with OS external-network denial and no model calls.
Evidence: `work/tom-isolated-flow-oracle-final-20260911.log`.
Root separately reports its fresh smoke 3/3, all local owners/events/jobs removed,
and both local ports closed; those later database checks are root's evidence,
not an additional live/provider check by Tom. Real-model acceptance remains
separate from these smoke and structural-oracle results.

Final reviewed hashes:

```text
c6c2eaf590d87b97ed3d014c76cd6d0b0df11821cb8a34a2bcc187fd11ce44b8  proof/audit/run_isolated_task_flow.py
128572b7646a95f1b0d373204c63ad1bf10ddfaeac2fc46a7c5f4cd59f292c9b  tests/test_isolated_task_flow.py
```
