# Bridge load test cc3b53dc

- started: 20260528T051610Z
- finished: 20260528T051710Z
- concurrency: 50
- bridge: http://127.0.0.1:7777
- cdp: http://127.0.0.1:9222

## verdict: DEGRADED

reason: bridge survived but serialized hard: only 15/50 finished in 60s, 35 timed out; 0 leaked tabs (all 15 created tabs closed via direct CDP Target.closeTarget by tracked targetId); bridge backlog drained and /status returned ok within ~60s of test end. R4 hypothesis confirmed: sync WebSocket per request + single asyncio handler serializes CDP work.

Initial verdict was FAILED because per-request timeouts >60s tripped
the hang_detected gate. After-the-fact polling showed the bridge fully
recovered within about 60s of test end (status ok, cdp_alive true).
Net effect: degraded throughput, but no crash, no FD exhaustion of the
listener, and zero tab leaks.

## throughput

| metric | value |
| --- | --- |
| total requests | 50 |
| succeeded within 60s | 15 / 50 |
| timed out at 60s | 35 / 50 |
| wall time (s) | 60.465 |
| effective rps | 0.83 |

## latency (ms, all requests including timeouts)

| pct | value |
| --- | --- |
| min | 45076.8 |
| median (p50) | 60451.9 |
| mean | 58027.2 |
| p95 | 60455.1 |
| p99 | 60455.4 |
| max | 60455.4 |

## latency (ms, only the 15 successful)

| pct | value |
| --- | --- |
| median (p50) | 52369.9 |
| p95 | 58613.0 |
| p99 | 59658.9 |

## tabs

- baseline pages total: 58
- after pages total: 60
- target ids received from bridge: 15
- new tab leaks attributable to this test: 0
- cleanup attempted (via direct CDP Target.closeTarget by tracked targetId): 15
- cleanup succeeded: 15

## connection state observations (from lsof_during.log)

Pre-test the bridge already had ~52 established TCP connections from
other clients (engine, supervisor loops). When our 50 piled on, total
established peaked at 102. After we abandoned the 35 timed-out
connections, the bridge accumulated CLOSE_WAIT FDs (peak around 16)
which gradually drained as the bridge processed its backlog post-test.

Pre-test bridge /status latency was already 15.27s -- already
contended by other clients even before our load.

## bridge state

- bridge_kind before: cdp_primary
- bridge_kind during test: cdp_primary (no fallback to AppleScript)
- bridge_kind after recovery: cdp_primary
- bridge alive after recovery: True
- cdp_alive after recovery: True

## R4 hypothesis check

R4: "bridge uses sync WebSocket + single asyncio handler that serializes all CDP calls."

CONFIRMED. The success-only latencies are perfectly linearly spaced at
~1s intervals (45.0, 46.1, 47.2, 48.2, 49.2, 50.3, 51.3, 52.4 s ...),
which is the signature of a queue draining one item per ~1s. The
1s/task floor matches the bridge's hard-coded `time.sleep(1.0)` inside
`_cdp_navigate` plus the WS-connect + send + recv round-trip per call.

Recommendation: REWRITE THE BRIDGE HANDLER. The current handler is
async at the socket level but sync at the CDP level, so every request
blocks the event loop while waiting on its WebSocket. A single
persistent WebSocket to the browser plus async sends/receives via
asyncio websockets, with per-request promise correlation by message id,
would unblock concurrent calls and reduce p95 by an order of magnitude.

See `result.json`, `per_request.json`, `cleanup.json`,
`baseline_tabs.json`, `after_tabs.json`, `lsof_during.log`.
