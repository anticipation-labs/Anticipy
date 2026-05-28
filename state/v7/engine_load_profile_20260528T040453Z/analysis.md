# Engine Load Profile Analysis

- Run: `state/v7/engine_load_profile_20260528T040453Z/`
- Engine: `http://127.0.0.1:8731` (packaged binary, PID 37580, `product-3`)
- Account under test: `e2e_rich_test_2026_05_28`
- Method: 100 concurrent injects (cycling 20 hard transcripts), 100 concurrent dossier reads, 100 concurrent `/api/listen/status`, 50 concurrent `/api/memory`, 10 concurrent `/api/intent/extract` (LLM budget cap).
- Engine sample: `sample 37580 30s` (`sample.txt`, 7.1 MB).
- Engine log: `~/.anticipy/product-engine.log` tail since pre-flight = 0 bytes (uvicorn access-log goes to stdout, not the file).

## Survival

Engine survived 360 total HTTP requests across 5 endpoints. Post-load `/version` returned `200`. No 5xx anywhere. No tracebacks in the log tail. `survived: true` in `metrics.json`. PID 37580 is still the engine after the run. The strangers loop on PID 69265 continued without disruption.

## Latency under load (cold/warm mix)

| Endpoint | n | median | p95 | p99 | error rate | notes |
|---|---:|---:|---:|---:|---:|---|
| GET `/api/listen/status` | 100 | 16.3 ms | 23.2 ms | 23.5 ms | 0.0% | cheap snapshot under `_LISTEN["lock"]` |
| GET `/api/dossier (active fallback)` | 100 | 10.8 ms | 12.3 ms | 12.6 ms | 100% (410) | endpoint is retired; routing layer is fast |
| POST `/api/listen/inject` | 100 | 19,066 ms | 30,023 ms | 30,176 ms | 0.0% (HTTP) | mean 18.1 s, max 30.2 s |
| GET `/api/memory` | 50 | 17.8 ms | 30.0 ms | 31.0 ms | 0.0% | small in-memory map serialization |
| POST `/api/intent/extract` | 10 | 6,776 ms | 10,008 ms | 10,008 ms | 0.0% | LLM cascade, capped at `timeout=10s` |

Pre-flight (sequential, before any load): inject 6,206 ms, dossier 1.9 ms, status 1.3 ms, memory 1.4 ms. Sequential inject already costs 6 s; concurrency multiplies it to 19 s median / 30 s p95.

## Mounted-paths note

`/api/dossier/active` and `/api/memory/read` (the endpoints the brief named) are NOT present in this packaged binary (`product-3`). Confirmed in `mounted_paths.json`. The current binary still exposes the legacy `/api/dossier` reader, which always returns 410 with `legacy_endpoint_retired`. I substituted the legacy reader (still exercises FastAPI routing + JSON serialization) and `/api/memory` for the memory bench so the load test could complete with the live binary, and flagged it here.

## Top 3 bottlenecks

### 1. `/api/listen/inject` is sync and runs blocking LLM calls behind a thread-spawning timeout wrapper

- File:line. `engine/app/product/server.py:4229` (`def listen_inject`, NOT `async def`), wrapping `_with_timeout(...)` at line 4251, which spawns a fresh `threading.Thread` (line 835) for every call. The blocking work is `_process_utterance -> _run_pipeline -> _compose_task_from_memory`, where `_compose_task_from_memory` at `engine/app/product/server.py:4956-4971` retries an OpenRouter `model_call` up to 4 times with `_t.sleep(1.5 + attempt * 2)` between attempts.
- Latency impact. Sequential pre-flight 6.2 s. Under 32-way concurrency median jumps to 19.1 s; p95 / p99 / max all clamp at the 30 s upstream `ANTICIPY_INJECT_TIMEOUT_SECONDS` cap. So under any realistic burst (multiple browser tabs, the listening loop firing alongside, the verifier pinging) every inject hits the timeout ceiling and degrades to a 30 s call. The `sample.txt` shows ~744 `take_gil` / `PyThread_acquire_lock_timed` frames across 212 unique threads. Pure GIL contention.
- Blast radius. This is the single most important user-facing endpoint (every utterance and every E2E test injects through it). The strangers loop, the e2e_hard_transcripts harness, the live mic ASR loop, and `/api/act` all funnel through this path. A 30 s inject means the "Now / Next / Past" popover lags 30 s behind speech, the strangers loop times out per persona, and the proactive day pipeline starves. This is the difference between "ambient AI" and "broken demo".
- Concrete fix (do not apply here, another agent does).
  1. Make `listen_inject` `async def`, and offload the CPU/IO work via `await asyncio.to_thread(...)` instead of a per-call `_with_timeout` thread spawn. This removes the double-thread (FastAPI threadpool + `_with_timeout` Thread) and lets Starlette's anyio threadpool size cap concurrency cleanly.
  2. Bound `_compose_task_from_memory`'s retry budget: the current 4-attempt loop with `1.5 + 2n` second backoff sleeps 1.5 + 3.5 + 5.5 = 10.5 s of pure wall-clock per inject when the LLM is slow. Cut to 1 retry + 1 s backoff, and short-circuit when `outcome` is `ACTED`/`CONFIRMED` (the LLM call only matters in the `elif _is_actionish(text)` clarify branch at server.py:3866-3880, not for the common LIFE_LOG/IGNORED outcomes).
  3. Cache `_compose_task_from_memory` results by `(instruction, profile_hash, recent_window_hash)` for at least 60 s. The same hard transcript called twice in a row hits the cascade twice today.

### 2. `_with_timeout` spawns a new daemon thread per request and joins on it

- File:line. `engine/app/product/server.py:826-843`. Every call creates `threading.Thread(target=runner, daemon=True)`, starts it, and `th.join(timeout_s)`. There is no pool, no bound.
- Latency impact. With 32-way inject + the strangers loop already in flight, the sample shows 212 unique threads in flight inside the engine process at peak (`grep "Thread_" sample.txt | sort -u | wc -l = 212`). Pthread create + GIL acquisition for each new thread amplifies tail latency: the 30 s p95 on inject is partly because once 64+ threads are competing for the GIL, each Python op is starved. The double-thread (Starlette anyio pool runs `def` handlers on its own pool, and `_with_timeout` then spawns a second thread) doubles thread count for the inject path.
- Blast radius. `_with_timeout` is used in 6+ places in `server.py`. Every one of them creates the same pattern. This is a process-wide multiplier. Fixing it improves every code path that uses it.
- Concrete fix. Replace `_with_timeout` with a single module-level `ThreadPoolExecutor(max_workers=8)` and use `future.result(timeout=...)`. Or, since most callers already run inside Starlette's threadpool, switch the wrapped handlers to `async def` and use `asyncio.wait_for(asyncio.to_thread(fn), timeout=...)`. The current implementation cannot be made faster without changing this primitive.

### 3. ASR executor is hard-coded to `max_workers=1`

- File:line. `engine/app/audiostack/audio.py:142-150` (`_get_asr_executor`). Constructed with `max_workers=1`, `thread_name_prefix="anticipy-asr-mlx"`.
- Latency impact. Not visible in this run because the load test exercises the transcript-boundary inject path (`source="asr-transcript"`), which bypasses the executor. But every audio upload (`/api/listen/upload`, `/api/onboarding/from_audio`, the MP3-of-the-day path) and every continuous-listening window pipes through `_get_asr_executor`. With one worker, two concurrent uploads serialize fully: 12 s audio -> 12 s ASR -> second upload waits 12 s before starting. The serialized wait is invisible to a single-mic install but fatal for the verifier loop (which uploads N fixture MP3s in parallel) and for any future "drop a folder of recordings" UX. Confirmed: this is the only `max_workers=1` executor in the engine. No other file matches `max_workers=1` in a `ThreadPoolExecutor` constructor. R4 was right.
- Blast radius. Any path that touches `_get_asr_executor`. Today that is upload + onboarding-from-audio + the audio capture loop's window-flush.
- Concrete fix. Raise `max_workers` to 2 on Apple Silicon (the MLX parakeet model uses GPU streams that can multiplex), with a guard env var (`ANTICIPY_ASR_WORKERS`, default 2). The thread initializer at line 128-139 already calls `mx.new_thread_local_stream(mx.gpu)`, which is the right primitive. It was already written to support multi-thread, but only one worker was ever created. The fix is a one-line change plus a smoke test that two `/api/listen/upload` calls in parallel finish in `~max(t1, t2)`, not `t1+t2`.

## Honorable mentions (not in top 3, but visible)

- GIL pressure on cheap endpoints. `/api/listen/status` median 16 ms is high for what is a dict read under a `threading.Lock`. The `_LISTEN["lock"]` is held during the response build at server.py:4726-4742. Under contention with 32 inject workers in flight, even a cheap GET pays GIL tax. Mitigation: snapshot under the lock, release, then build the JSON outside the lock.
- `_transcript_from_normalized` bug in `intent_extractor.py:170-184`. `capture = normalized_input.get("capture") or {}; if isinstance(capture, dict): return str(capture.get("asr_normalized") or capture.get("raw_asr_transcript") or "")` always evaluates true (empty dict is still a dict), so the `text` field fallback at line 184 is unreachable. Every caller that uses `{"normalized_input": {"text": "..."}}` gets `empty_transcript` instead of an extracted intent. The load test had to send `capture.raw_asr_transcript` to actually fire the cascade. This is not a latency bottleneck but it is a real correctness bug worth surfacing.
- `/api/dossier/active` and `/api/memory/read` are not mounted in the packaged binary. The router-wire blocks at `server.py:6679-6696` and `scoped_memory_router_wire` are wrapped in `try/except: pass`, so if their dependency module raises at import the router is silently dropped. The live `product-3` binary advertises `/api/dossier` and `/api/memory` only. Either the wire blocks are failing silently in the packaged Python or the bundler did not include `dossier_endpoints.py` / `scoped_memory_endpoints.py`. Worth investigating separately (`PyInstaller` hidden-imports).

## Survival verdict

Engine survived 250+ concurrent requests (360 total) without crashing. Zero 5xx, zero log errors, zero tracebacks. Post-load `/version` returned `200`. The strangers loop on PID 69265 was unaffected. The "did the engine crash?" answer is no, but the "is the engine usable under load?" answer is no, inject latency is 19 s median / 30 s p95 which is unacceptable for an ambient assistant.
