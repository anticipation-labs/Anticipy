#!/usr/bin/env python3
"""Bridge load test: 50 concurrent CDP-shaped requests through the
Anticipy bridge on 127.0.0.1:7777.

Hypothesis (R4): the bridge uses sync WebSockets behind an asyncio
HTTP server. Each CDP call blocks the event loop, so concurrent
requests serialize. This script measures the real load profile.

For each of 50 tasks:
  1. POST /surface-command navigate with URL
     https://example.com:{port}/?lt={i}&u={uuid} so the bridge's
     host_prefix match (scheme://netloc) does NOT find the existing
     example.com:443 tab, forcing Target.createTarget.
  2. Capture per-request latency, targetId, success.
After all 50 finish:
  3. Close each NEW targetId via direct CDP Target.closeTarget on
     port 9222 (the bridge does not expose closeTarget). Tracked
     end-to-end by targetId, never by url_prefix.
  4. Poll /json/list to confirm zero leftover tabs from this run.

Outputs:
  state/v7/bridge_load_<ts>/result.json
  state/v7/bridge_load_<ts>/summary.md
  state/v7/bridge_load_<ts>/lsof_during.log
  state/v7/bridge_load_<ts>/per_request.json

Hard rules honored:
  - No bridge restart.
  - No touching tabs not created by this test (baseline snapshot).
  - 60s hard ceiling per request; if bridge hangs, STOP cleanly.
  - $0 OpenRouter (no LLM calls).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import subprocess
import sys
import time
import uuid
from pathlib import Path

try:
    import aiohttp
except Exception as exc:
    sys.stderr.write(f"aiohttp required: {exc}\n")
    sys.exit(2)

try:
    from websockets.sync.client import connect as ws_connect
except Exception as exc:
    sys.stderr.write(f"websockets required: {exc}\n")
    sys.exit(2)


BRIDGE_BASE = "http://127.0.0.1:7777"
CDP_BASE = "http://127.0.0.1:9222"
BRIDGE_SECRET = os.environ.get("ANTICIPY_TRIGGER_SECRET") or "local-dev"
N_CONCURRENT = 50
PER_REQUEST_TIMEOUT_S = 60.0  # hard ceiling per R4 rules
TEST_HOST_BASE = "example.com"  # uses unique ports to bypass prefix match
RUN_ID = uuid.uuid4().hex[:8]
PORT_BASE = 19_000  # synthetic ports, won't accept connections


def now_iso() -> str:
    return time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())


def baseline_pages() -> list[dict]:
    """Snapshot current /json/list so we can compute leak deltas."""
    try:
        import urllib.request
        r = urllib.request.urlopen(f"{CDP_BASE}/json/list", timeout=5)
        return json.loads(r.read().decode("utf-8"))
    except Exception as exc:
        sys.stderr.write(f"baseline_pages failed: {exc}\n")
        return []


def browser_ws_url() -> str:
    """Fetch the browser-level WebSocket URL for Target.closeTarget."""
    import urllib.request
    r = urllib.request.urlopen(f"{CDP_BASE}/json/version", timeout=5)
    info = json.loads(r.read().decode("utf-8"))
    return (info.get("webSocketDebuggerUrl") or "").replace("127.0.0.1", "localhost")


def close_target_via_cdp(browser_ws: str, target_id: str,
                         timeout: float = 8.0) -> dict:
    """Close one target by id via direct CDP browser session. Sync; we
    run it in a thread pool so the asyncio loop does not block.
    """
    t0 = time.perf_counter()
    try:
        ws = ws_connect(browser_ws, max_size=1 << 20,
                        open_timeout=min(5.0, timeout))
    except Exception as exc:
        return {"ok": False, "error": f"ws connect: {exc}",
                "elapsed_ms": (time.perf_counter() - t0) * 1000.0}
    try:
        rid = 1
        ws.send(json.dumps({
            "id": rid,
            "method": "Target.closeTarget",
            "params": {"targetId": target_id},
        }))
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                raw = ws.recv(timeout=max(0.5, deadline - time.time()))
            except Exception as exc:
                return {"ok": False, "error": f"ws recv: {exc}",
                        "elapsed_ms": (time.perf_counter() - t0) * 1000.0}
            try:
                msg = json.loads(raw)
            except Exception:
                continue
            if msg.get("id") == rid:
                result = (msg.get("result") or {})
                ok = bool(result.get("success", False))
                return {"ok": ok, "raw": result, "error": "" if ok else str(msg)[:300],
                        "elapsed_ms": (time.perf_counter() - t0) * 1000.0}
        return {"ok": False, "error": "timeout waiting for closeTarget response",
                "elapsed_ms": (time.perf_counter() - t0) * 1000.0}
    finally:
        try:
            ws.close()
        except Exception:
            pass


async def fire_one(session: aiohttp.ClientSession, i: int,
                   shared_state: dict) -> dict:
    """Send one navigate to bridge. Captures latency + targetId."""
    port = PORT_BASE + i
    url = f"https://{TEST_HOST_BASE}:{port}/?lt={i}&run={RUN_ID}"
    payload = {
        "secret": BRIDGE_SECRET,
        "command": "navigate",
        "url": url,
    }
    started = time.perf_counter()
    started_wall = time.time()
    out: dict = {
        "i": i,
        "url": url,
        "started_wall": started_wall,
        "elapsed_ms": None,
        "http_status": None,
        "ok": False,
        "target_id": "",
        "bridge_error": "",
        "exception": "",
    }
    timeout = aiohttp.ClientTimeout(total=PER_REQUEST_TIMEOUT_S)
    try:
        async with session.post(
            f"{BRIDGE_BASE}/surface-command",
            json=payload,
            timeout=timeout,
        ) as resp:
            out["http_status"] = resp.status
            body = await resp.text()
            elapsed = (time.perf_counter() - started) * 1000.0
            out["elapsed_ms"] = elapsed
            try:
                data = json.loads(body)
            except Exception as exc:
                out["bridge_error"] = f"non-json body: {exc}: {body[:200]}"
                return out
            out["ok"] = bool(data.get("ok"))
            out["bridge_error"] = str(data.get("error") or "")
            inner = data.get("data") or {}
            tid = str(inner.get("targetId") or "")
            out["target_id"] = tid
            if tid:
                shared_state.setdefault("created_target_ids", []).append(tid)
    except asyncio.TimeoutError:
        out["elapsed_ms"] = (time.perf_counter() - started) * 1000.0
        out["exception"] = f"timeout after {PER_REQUEST_TIMEOUT_S}s"
        shared_state["hang_detected"] = True
    except Exception as exc:
        out["elapsed_ms"] = (time.perf_counter() - started) * 1000.0
        out["exception"] = f"{type(exc).__name__}: {exc}"
    return out


async def sample_lsof(run_dir: Path, stop_evt: asyncio.Event) -> None:
    """Sample lsof -i :7777 every 1.0s until stop_evt set."""
    log = run_dir / "lsof_during.log"
    with log.open("w") as fh:
        fh.write(f"# lsof -i :7777 sampled every 1.0s from {now_iso()}\n")
        while not stop_evt.is_set():
            ts = time.strftime("%H:%M:%S")
            try:
                proc = await asyncio.create_subprocess_exec(
                    "lsof", "-nP", "-i", ":7777",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                so, _ = await asyncio.wait_for(proc.communicate(), timeout=3.0)
                text = so.decode("utf-8", "replace")
            except Exception as exc:
                text = f"lsof failed: {exc}\n"
            lines = text.splitlines()
            connections = [ln for ln in lines if "TCP" in ln]
            close_wait = sum(1 for ln in lines if "CLOSE_WAIT" in ln)
            established = sum(1 for ln in lines if "ESTABLISHED" in ln)
            listen = sum(1 for ln in lines if "LISTEN" in ln)
            fh.write(
                f"[{ts}] tcp_total={len(connections)} listen={listen} "
                f"established={established} close_wait={close_wait}\n"
            )
            fh.flush()
            try:
                await asyncio.wait_for(stop_evt.wait(), timeout=1.0)
            except asyncio.TimeoutError:
                pass


def percentile(values: list[float], p: float) -> float:
    """p in [0,100]. Nearest-rank percentile."""
    if not values:
        return 0.0
    s = sorted(values)
    k = int(round((p / 100.0) * (len(s) - 1)))
    k = max(0, min(len(s) - 1, k))
    return s[k]


async def run(run_dir: Path) -> dict:
    run_dir.mkdir(parents=True, exist_ok=True)
    # Snapshot baseline.
    base_pages = baseline_pages()
    base_ids = {p.get("id") for p in base_pages if p.get("id")}
    (run_dir / "baseline_tabs.json").write_text(json.dumps({
        "ts": now_iso(),
        "total": len(base_pages),
        "pages": [{"id": p.get("id"), "type": p.get("type"),
                   "url": p.get("url", "")[:120]} for p in base_pages],
    }, indent=2))

    # Confirm bridge alive (GET /status, no secret needed). Use generous
    # timeout because /status itself can block on cdp_alive() which probes
    # port 9222. If contended by other clients, /status may take several
    # seconds. We do NOT abort on slow pre-check; we only abort on hard
    # failure.
    status_pre_start = time.perf_counter()
    try:
        async with aiohttp.ClientSession() as s0:
            async with s0.get(
                f"{BRIDGE_BASE}/status",
                timeout=aiohttp.ClientTimeout(total=30),
            ) as r:
                status_body = await r.text()
        try:
            status_data = json.loads(status_body)
        except Exception:
            status_data = {"raw": status_body[:500]}
    except Exception as exc:
        status_data = {"error": f"bridge status pre-check failed: {exc}"}
    status_pre_elapsed_s = time.perf_counter() - status_pre_start
    status_data["_pre_check_elapsed_s"] = round(status_pre_elapsed_s, 3)
    (run_dir / "bridge_status_pre.json").write_text(json.dumps(status_data, indent=2))
    if not status_data.get("ok"):
        return {
            "verdict": "FAILED",
            "reason": "bridge /status pre-check did not return ok=true",
            "bridge_status": status_data,
        }
    print(
        f"bridge pre-check ok in {round(status_pre_elapsed_s,2)}s; "
        f"bridge_kind={status_data.get('bridge_kind')} "
        f"cdp_alive={status_data.get('cdp_alive')}",
        flush=True,
    )

    # Launch lsof sampler.
    stop_evt = asyncio.Event()
    sampler = asyncio.create_task(sample_lsof(run_dir, stop_evt))

    shared_state: dict = {"hang_detected": False, "created_target_ids": []}

    # Fire 50 concurrent.
    wall_start = time.perf_counter()
    started_iso = now_iso()
    conn = aiohttp.TCPConnector(limit=N_CONCURRENT + 10, force_close=True)
    timeout_global = aiohttp.ClientTimeout(total=PER_REQUEST_TIMEOUT_S + 5)
    async with aiohttp.ClientSession(connector=conn, timeout=timeout_global) as session:
        tasks = [fire_one(session, i, shared_state) for i in range(N_CONCURRENT)]
        per_req = await asyncio.gather(*tasks, return_exceptions=False)
    wall_total_s = time.perf_counter() - wall_start
    finished_iso = now_iso()

    stop_evt.set()
    try:
        await asyncio.wait_for(sampler, timeout=5.0)
    except Exception:
        pass

    (run_dir / "per_request.json").write_text(json.dumps(per_req, indent=2))

    # Compute stats.
    succeeded = [r for r in per_req if r["ok"]]
    latencies = [r["elapsed_ms"] for r in per_req if r["elapsed_ms"] is not None]
    success_lat = [r["elapsed_ms"] for r in succeeded if r["elapsed_ms"] is not None]
    stats = {
        "n": len(per_req),
        "success": len(succeeded),
        "wall_total_s": round(wall_total_s, 3),
        "latency_ms": {
            "all_count": len(latencies),
            "median": round(statistics.median(latencies), 1) if latencies else None,
            "mean": round(statistics.fmean(latencies), 1) if latencies else None,
            "p95": round(percentile(latencies, 95), 1) if latencies else None,
            "p99": round(percentile(latencies, 99), 1) if latencies else None,
            "min": round(min(latencies), 1) if latencies else None,
            "max": round(max(latencies), 1) if latencies else None,
        },
        "success_only_latency_ms": {
            "count": len(success_lat),
            "median": round(statistics.median(success_lat), 1) if success_lat else None,
            "p95": round(percentile(success_lat, 95), 1) if success_lat else None,
            "p99": round(percentile(success_lat, 99), 1) if success_lat else None,
        },
        "hang_detected": shared_state.get("hang_detected", False),
        "started": started_iso,
        "finished": finished_iso,
        "target_ids_received": len(shared_state.get("created_target_ids", [])),
    }

    # Cleanup phase: close every targetId we received via direct CDP.
    created_ids = list(dict.fromkeys(shared_state.get("created_target_ids", [])))
    new_ids = [tid for tid in created_ids if tid not in base_ids]

    cleanup_results: list[dict] = []
    try:
        browser_ws = browser_ws_url()
    except Exception as exc:
        browser_ws = ""
        cleanup_results.append({"error": f"could not fetch browser ws url: {exc}"})

    if browser_ws:
        # Close serially to keep cleanup deterministic; closeTarget is cheap.
        loop = asyncio.get_event_loop()
        for tid in new_ids:
            res = await loop.run_in_executor(
                None, close_target_via_cdp, browser_ws, tid
            )
            res["target_id"] = tid
            cleanup_results.append(res)

    (run_dir / "cleanup.json").write_text(json.dumps(cleanup_results, indent=2))

    # Wait briefly for Chrome to reconcile, then re-list.
    await asyncio.sleep(1.5)
    after_pages = baseline_pages()
    after_ids = {p.get("id") for p in after_pages if p.get("id")}
    # Tabs created during the run that are STILL present after cleanup.
    leftover_ids = [tid for tid in new_ids if tid in after_ids]
    # Any new tabs at all (not in baseline, also not in our created list,
    # likely just unrelated browsing). We do NOT count those as leaks.
    new_since_baseline = sorted(after_ids - base_ids)
    leaks_from_test = [tid for tid in leftover_ids]

    (run_dir / "after_tabs.json").write_text(json.dumps({
        "ts": now_iso(),
        "total": len(after_pages),
        "new_since_baseline": new_since_baseline,
        "leaks_from_this_test": leaks_from_test,
    }, indent=2))

    # Post-check bridge /status.
    try:
        async with aiohttp.ClientSession() as s2:
            async with s2.get(f"{BRIDGE_BASE}/status", timeout=aiohttp.ClientTimeout(total=5)) as r:
                post_status_body = await r.text()
        try:
            post_status = json.loads(post_status_body)
        except Exception:
            post_status = {"raw": post_status_body[:500]}
    except Exception as exc:
        post_status = {"error": f"bridge /status post-check failed: {exc}"}
    (run_dir / "bridge_status_post.json").write_text(json.dumps(post_status, indent=2))

    bridge_alive_after = bool(post_status.get("ok"))

    # Verdict.
    leak_count = len(leaks_from_test)
    success_count = stats["success"]
    if shared_state.get("hang_detected", False):
        verdict = "FAILED"
        reason = "hang detected (request timed out > 60s)"
    elif not bridge_alive_after:
        verdict = "FAILED"
        reason = "bridge /status not ok after test"
    elif success_count == N_CONCURRENT and leak_count == 0:
        verdict = "PASS"
        reason = f"all {N_CONCURRENT} ok, 0 leaks, bridge alive"
    elif success_count >= int(0.90 * N_CONCURRENT) and leak_count == 0:
        verdict = "DEGRADED"
        reason = (
            f"{N_CONCURRENT - success_count}/{N_CONCURRENT} failed, but "
            f"bridge survived and tabs cleaned up"
        )
    else:
        verdict = "FAILED"
        reason = (
            f"only {success_count}/{N_CONCURRENT} succeeded "
            f"or {leak_count} leaks"
        )

    result = {
        "run_id": RUN_ID,
        "verdict": verdict,
        "reason": reason,
        "bridge_alive_after": bridge_alive_after,
        "tab_leak_count": leak_count,
        "leaked_target_ids": leaks_from_test,
        "stats": stats,
        "cleanup": {
            "n_attempted": len(new_ids),
            "n_succeeded": sum(1 for c in cleanup_results if c.get("ok")),
            "n_failed": sum(1 for c in cleanup_results if not c.get("ok")),
        },
        "baseline_total_tabs": len(base_pages),
        "after_total_tabs": len(after_pages),
        "bridge_kind_before": status_data.get("bridge_kind", ""),
        "bridge_kind_after": post_status.get("bridge_kind", ""),
        "cdp_alive_after": post_status.get("cdp_alive"),
    }
    (run_dir / "result.json").write_text(json.dumps(result, indent=2))

    # summary.md
    lat = stats["latency_ms"]
    summary = f"""# Bridge load test {RUN_ID}

- started: {started_iso}
- finished: {finished_iso}
- concurrency: {N_CONCURRENT}
- bridge: {BRIDGE_BASE}
- cdp: {CDP_BASE}

## verdict: {verdict}

reason: {reason}

## throughput

| metric | value |
| --- | --- |
| total requests | {stats['n']} |
| succeeded | {stats['success']} / {N_CONCURRENT} |
| wall time (s) | {stats['wall_total_s']} |
| effective rps | {round(stats['n'] / max(stats['wall_total_s'], 0.001), 2)} |
| hang detected | {stats['hang_detected']} |

## latency (ms, all requests)

| pct | value |
| --- | --- |
| min | {lat['min']} |
| median (p50) | {lat['median']} |
| mean | {lat['mean']} |
| p95 | {lat['p95']} |
| p99 | {lat['p99']} |
| max | {lat['max']} |

## tabs

- baseline pages total: {len(base_pages)}
- after pages total: {len(after_pages)}
- target ids received from bridge: {stats['target_ids_received']}
- new tab leaks attributable to this test: {leak_count}
- cleanup attempted: {result['cleanup']['n_attempted']}
- cleanup succeeded: {result['cleanup']['n_succeeded']}

## bridge state

- bridge_kind before: {result['bridge_kind_before']}
- bridge_kind after: {result['bridge_kind_after']}
- cdp_alive after: {result['cdp_alive_after']}
- bridge alive after: {bridge_alive_after}

See `result.json`, `per_request.json`, `cleanup.json`,
`baseline_tabs.json`, `after_tabs.json`, `lsof_during.log`.
"""
    (run_dir / "summary.md").write_text(summary)
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", default="")
    args = ap.parse_args()
    ts = now_iso()
    repo = Path("/Users/omarebrahim/Developer/Anticipy-V7")
    run_dir = Path(args.run_dir) if args.run_dir else (
        repo / "state" / "v7" / f"bridge_load_{ts}"
    )
    print(f"bridge load test starting: run_dir={run_dir}", flush=True)
    try:
        result = asyncio.run(run(run_dir))
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130
    print(json.dumps({
        "verdict": result.get("verdict"),
        "reason": result.get("reason"),
        "stats": result.get("stats"),
        "tab_leak_count": result.get("tab_leak_count"),
        "run_dir": str(run_dir),
    }, indent=2))
    return 0 if result.get("verdict") in ("PASS", "DEGRADED") else 1


if __name__ == "__main__":
    sys.exit(main())
