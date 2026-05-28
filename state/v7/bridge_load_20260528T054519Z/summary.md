# Bridge load test 6eeccf3a

- started: 20260528T054519Z
- finished: 20260528T054524Z
- concurrency: 50
- bridge: http://127.0.0.1:7777
- cdp: http://127.0.0.1:9222

## verdict: PASS

reason: all 50 ok, 0 leaks, bridge alive

## throughput

| metric | value |
| --- | --- |
| total requests | 50 |
| succeeded | 50 / 50 |
| wall time (s) | 5.449 |
| effective rps | 9.18 |
| hang detected | False |

## latency (ms, all requests)

| pct | value |
| --- | --- |
| min | 2455.9 |
| median (p50) | 3493.9 |
| mean | 3872.6 |
| p95 | 5432.6 |
| p99 | 5435.7 |
| max | 5435.7 |

## tabs

- baseline pages total: 74
- after pages total: 72
- target ids received from bridge: 50
- new tab leaks attributable to this test: 0
- cleanup attempted: 50
- cleanup succeeded: 50

## bridge state

- bridge_kind before: cdp_primary
- bridge_kind after: cdp_primary
- cdp_alive after: True
- bridge alive after: True

See `result.json`, `per_request.json`, `cleanup.json`,
`baseline_tabs.json`, `after_tabs.json`, `lsof_during.log`.
