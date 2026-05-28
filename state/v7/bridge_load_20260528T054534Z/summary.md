# Bridge load test 8f60b4f7

- started: 20260528T054534Z
- finished: 20260528T054550Z
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
| wall time (s) | 15.755 |
| effective rps | 3.17 |
| hang detected | False |

## latency (ms, all requests)

| pct | value |
| --- | --- |
| min | 2274.0 |
| median (p50) | 10380.5 |
| mean | 9619.2 |
| p95 | 10935.0 |
| p99 | 15720.3 |
| max | 15720.3 |

## tabs

- baseline pages total: 72
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
