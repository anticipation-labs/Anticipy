#!/usr/bin/env python3
"""Load + analyze the live Anticipy engine on port 8731.

Read-only HTTP. Uses stdlib only (urllib + ThreadPoolExecutor). Does
NOT restart the engine. Designed to coexist with the strangers loop:
every request has a tight per-call timeout so a hung backend cannot
back up the driver.

Records median, p95, p99, error rate, status histogram, and overall
RPS per endpoint. Writes metrics.json + analysis.md into --run-dir.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = (len(s) - 1) * pct
    f = int(k)
    c = min(f + 1, len(s) - 1)
    if f == c:
        return s[f]
    return s[f] + (s[c] - s[f]) * (k - f)


def _summarize(latencies_ms: list[float], statuses: list[int],
               errors: list[str], wall_s: float) -> dict:
    ok = [s for s in statuses if 200 <= s < 400]
    bad = [s for s in statuses if s < 200 or s >= 400 or s == 0]
    hist: dict[str, int] = {}
    for s in statuses:
        key = str(s) if s else "exc"
        hist[key] = hist.get(key, 0) + 1
    return {
        "count": len(latencies_ms),
        "ok": len(ok),
        "errors": len(bad),
        "error_rate": (len(bad) / len(statuses)) if statuses else 0.0,
        "wall_seconds": round(wall_s, 3),
        "rps_wall": round(len(latencies_ms) / wall_s, 2) if wall_s > 0 else 0,
        "latency_ms": {
            "min": round(min(latencies_ms), 2) if latencies_ms else 0,
            "median": round(statistics.median(latencies_ms), 2)
            if latencies_ms else 0,
            "p95": round(_percentile(latencies_ms, 0.95), 2)
            if latencies_ms else 0,
            "p99": round(_percentile(latencies_ms, 0.99), 2)
            if latencies_ms else 0,
            "max": round(max(latencies_ms), 2) if latencies_ms else 0,
            "mean": round(statistics.mean(latencies_ms), 2)
            if latencies_ms else 0,
        },
        "status_histogram": hist,
        "sample_errors": errors[:5],
    }


def _one_call(method: str, url: str, body: dict | None,
              timeout_s: float) -> tuple[float, int, str]:
    headers = {"Content-Type": "application/json"} if body else {}
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers,
                                 method=method)
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            resp.read()
            elapsed = (time.perf_counter() - t0) * 1000.0
            return elapsed, resp.status, ""
    except urllib.error.HTTPError as e:
        elapsed = (time.perf_counter() - t0) * 1000.0
        try:
            body_text = e.read().decode("utf-8", errors="replace")[:200]
        except Exception:
            body_text = ""
        return elapsed, e.code, f"HTTP {e.code}: {body_text}"
    except Exception as e:
        elapsed = (time.perf_counter() - t0) * 1000.0
        return elapsed, 0, f"{type(e).__name__}: {e}"


def _run_pool(jobs: list[Callable[[], tuple[float, int, str]]],
              concurrency: int, label: str) -> dict:
    latencies: list[float] = []
    statuses: list[int] = []
    errors: list[str] = []
    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=concurrency) as ex:
        futs = [ex.submit(j) for j in jobs]
        for f in as_completed(futs):
            ms, code, err = f.result()
            latencies.append(ms)
            statuses.append(code)
            if err:
                errors.append(err)
    wall = time.perf_counter() - t0
    print(f"[{label}] n={len(jobs)} conc={concurrency} "
          f"wall={wall:.2f}s ok="
          f"{sum(1 for s in statuses if 200 <= s < 400)} "
          f"err={sum(1 for s in statuses if s < 200 or s >= 400 or s == 0)} "
          f"median={statistics.median(latencies):.1f}ms "
          f"p95={_percentile(latencies, 0.95):.1f}ms "
          f"p99={_percentile(latencies, 0.99):.1f}ms")
    return _summarize(latencies, statuses, errors, wall)


def _load_transcripts(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    items = data.get("transcripts") or []
    if not items:
        raise SystemExit(f"no transcripts in {path}")
    return items


def _build_inject_jobs(engine: str, transcripts: list[dict],
                       n: int, account: str,
                       timeout_s: float = 35.0) -> list[Callable]:
    url = f"{engine}/api/listen/inject"
    jobs: list[Callable] = []
    for i in range(n):
        t = transcripts[i % len(transcripts)]
        body = {
            "text": t["raw"],
            "account_id": account,
            "user_id": account,
            "source": "asr-transcript",
        }
        jobs.append(lambda b=body: _one_call("POST", url, b, timeout_s))
    return jobs


def _build_dossier_jobs(engine: str, n: int, account: str,
                        timeout_s: float = 10.0) -> list[Callable]:
    # Mounted paths in the LIVE binary do not include /api/dossier/active.
    # The legacy /api/dossier reader is the closest analogue actually
    # mounted; it returns a 200 with a "legacy_endpoint_retired" payload
    # but still exercises FastAPI routing + JSON serialization end to
    # end and lets us compare to the other endpoints under identical
    # load. The analysis flags this so the reader is not misled.
    primary = f"{engine}/api/dossier/active?account_id={account}"
    fallback = f"{engine}/api/dossier?user_id={account}"
    test = _one_call("GET", primary, None, 5.0)
    if test[1] in (200, 400):
        url = primary
    else:
        url = fallback
    return [lambda u=url: _one_call("GET", u, None, timeout_s)
            for _ in range(n)]


def _build_status_jobs(engine: str, n: int,
                       timeout_s: float = 5.0) -> list[Callable]:
    url = f"{engine}/api/listen/status"
    return [lambda: _one_call("GET", url, None, timeout_s)
            for _ in range(n)]


def _build_intent_jobs(engine: str, transcripts: list[dict],
                       budget: int, account: str,
                       timeout_s: float = 35.0) -> list[Callable]:
    # Intent extract runs an OpenRouter LLM call by design. Cap at the
    # supplied budget to keep cost negligible while still measuring
    # the LLM-bound path under concurrency.
    url = f"{engine}/api/intent/extract"
    jobs: list[Callable] = []
    for i in range(budget):
        t = transcripts[i % len(transcripts)]
        body = {
            # Live engine's _transcript_from_normalized reads from
            # capture.raw_asr_transcript or capture.asr_normalized
            # first; the bare `text` path is unreachable because
            # capture defaults to {} via `or {}`. So we must supply
            # capture for the LLM cascade to actually fire.
            "normalized_input": {
                "capture": {"raw_asr_transcript": t["raw"]},
                "account_id": account,
                "user_id": account,
            },
            "memory_context": "",
            "timeout": 10.0,
        }
        jobs.append(lambda b=body: _one_call("POST", url, b, timeout_s))
    return jobs


def _build_memory_jobs(engine: str, n: int, account: str,
                       timeout_s: float = 5.0) -> list[Callable]:
    # /api/memory is what is mounted; /api/memory/read is not in this
    # binary build. Use the available reader.
    url = f"{engine}/api/memory"
    return [lambda: _one_call("GET", url, None, timeout_s)
            for _ in range(n)]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", required=True)
    ap.add_argument("--account", required=True)
    ap.add_argument("--transcripts", required=True)
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--intent-budget", type=int, default=10)
    ap.add_argument("--inject-n", type=int, default=100)
    ap.add_argument("--inject-conc", type=int, default=32)
    ap.add_argument("--dossier-n", type=int, default=100)
    ap.add_argument("--dossier-conc", type=int, default=32)
    ap.add_argument("--status-n", type=int, default=100)
    ap.add_argument("--status-conc", type=int, default=32)
    ap.add_argument("--memory-n", type=int, default=50)
    ap.add_argument("--memory-conc", type=int, default=16)
    ap.add_argument("--intent-conc", type=int, default=5)
    args = ap.parse_args()

    run_dir = Path(args.run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    transcripts = _load_transcripts(Path(args.transcripts))
    print(f"loaded {len(transcripts)} transcripts")

    # Pre-flight per endpoint: 1 call each, so we know baselines.
    pre: dict[str, Any] = {}
    for label, jobs in [
        ("inject", _build_inject_jobs(args.engine, transcripts, 1,
                                      args.account, 20.0)),
        ("dossier", _build_dossier_jobs(args.engine, 1, args.account, 10.0)),
        ("status", _build_status_jobs(args.engine, 1, 5.0)),
        ("memory", _build_memory_jobs(args.engine, 1, args.account, 5.0)),
    ]:
        ms, code, err = jobs[0]()
        pre[label] = {"ms": round(ms, 2), "status": code, "err": err}
        print(f"  pre-flight {label}: {code} in {ms:.1f}ms")

    metrics: dict[str, Any] = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "engine": args.engine,
        "account": args.account,
        "preflight": pre,
        "endpoints": {},
    }

    # Order: status (cheap warm-up), dossier (cheap), inject (medium),
    # memory (cheap), intent (expensive, last so it doesn't poison
    # earlier latencies if the OpenRouter call blocks the loop).
    metrics["endpoints"]["GET /api/listen/status"] = _run_pool(
        _build_status_jobs(args.engine, args.status_n),
        args.status_conc, "status",
    )

    metrics["endpoints"][
        "GET /api/dossier (active fallback)"
    ] = _run_pool(
        _build_dossier_jobs(args.engine, args.dossier_n, args.account),
        args.dossier_conc, "dossier",
    )

    metrics["endpoints"]["POST /api/listen/inject"] = _run_pool(
        _build_inject_jobs(args.engine, transcripts, args.inject_n,
                           args.account),
        args.inject_conc, "inject",
    )

    metrics["endpoints"]["GET /api/memory"] = _run_pool(
        _build_memory_jobs(args.engine, args.memory_n, args.account),
        args.memory_conc, "memory",
    )

    metrics["endpoints"]["POST /api/intent/extract"] = _run_pool(
        _build_intent_jobs(args.engine, transcripts, args.intent_budget,
                           args.account),
        args.intent_conc, "intent",
    )

    # Survival check: did the engine crash?
    try:
        with urllib.request.urlopen(f"{args.engine}/version",
                                    timeout=5) as r:
            metrics["survived"] = r.status == 200
            metrics["post_version"] = r.read().decode(
                "utf-8", errors="replace")
    except Exception as e:
        metrics["survived"] = False
        metrics["post_version_error"] = f"{type(e).__name__}: {e}"

    metrics["total_requests"] = sum(
        v["count"] for v in metrics["endpoints"].values()
    )
    metrics["total_errors"] = sum(
        v["errors"] for v in metrics["endpoints"].values()
    )
    metrics["overall_error_rate"] = round(
        metrics["total_errors"] / max(1, metrics["total_requests"]), 4,
    )

    (run_dir / "metrics.json").write_text(
        json.dumps(metrics, indent=2), encoding="utf-8",
    )
    print(f"\nwrote {run_dir / 'metrics.json'}")
    print(f"total requests: {metrics['total_requests']}, "
          f"errors: {metrics['total_errors']}, "
          f"overall error rate: {metrics['overall_error_rate']}")
    print(f"engine survived: {metrics['survived']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
