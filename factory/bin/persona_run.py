#!/usr/bin/env python
"""Run persona days through ISOLATED engine instances and dump raw results.

For each persona:
  1. fresh ANTICIPY_DATA_DIR under the run dir, seeded from seed_memory.jsonl
  2. boot an isolated engine (stub/mock env regardless of .env.local — explicit env wins
     because core/env.py uses load_dotenv(override=False))
  3. feed each days/dayNN.txt through scripts/realday.sh (the same pipe the product uses)
  4. dump /glassbox, /pending, /scorecard and every persisted goal JSON
  5. kill the engine, leave the run dir for persona_score.py

Usage:
  persona_run.py --bank factory/personas/dev --lap LAP [--personas a,b] [--tier stub|live]
                 [--out logs/factory/runs/LAP]
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PY = REPO / "engine" / ".venv" / "bin" / "python"


def http_json(url: str, timeout: float = 10.0) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as r:
        raw = r.read().decode("utf-8")
    return json.loads(raw) if raw else {}


def port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def engine_env(data_dir: Path, tier: str) -> dict:
    env = dict(os.environ)
    env.update({
        "ANTICIPY_DATA_DIR": str(data_dir),
        "ANTICIPY_HANDS_MODE": "mock",        # persona runs NEVER touch real apps
        "ANTICIPY_CHANNELS_MODE": "mock",
        "TWILIO_MOCK": "true",
        "ANTICIPY_NATIVE_BRIDGE_FALLBACK": "0",  # no Chrome/bridge in eval runs
        "ANTICIPY_NATIVE_BRIDGE_AUTOSTART": "0",
    })
    if tier == "live":
        env["ANTICIPY_MODEL_PROVIDER"] = "openrouter"   # cheap-tier model decisions
        env["ANTICIPY_MEMORY_MODE"] = "live"
    else:
        env["ANTICIPY_MODEL_PROVIDER"] = "stub"
        env["ANTICIPY_MEMORY_MODE"] = "stub"
    return env


def boot_engine(port: int, env: dict, log_path: Path, timeout_s: float) -> subprocess.Popen:
    cmd = [str(PY), "-m", "uvicorn", "--app-dir", "engine",
           "anticipy_engine.main:app", "--port", str(port), "--log-level", "warning"]
    log = log_path.open("w")
    proc = subprocess.Popen(cmd, cwd=str(REPO), env=env, stdout=log, stderr=subprocess.STDOUT,
                            start_new_session=True)
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"engine died at boot; see {log_path}")
        try:
            http_json(f"http://127.0.0.1:{port}/health", timeout=2)
            return proc
        except Exception:
            time.sleep(0.5)
    proc.terminate()
    raise RuntimeError(f"engine did not become healthy on :{port} within {timeout_s}s")


def kill_engine(proc: subprocess.Popen) -> None:
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except Exception:
        proc.terminate()
    try:
        proc.wait(timeout=10)
    except Exception:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except Exception:
            proc.kill()


def collect_goals(data_dir: Path) -> list[dict]:
    goals = []
    for p in sorted(data_dir.rglob("*.json")):
        try:
            obj = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(obj, dict) and "intent" in obj and "steps" in obj and "state" in obj:
            goals.append(obj)
    return goals


def run_persona(persona_dir: Path, lap: str, port: int, out_root: Path, tier: str,
                boot_timeout: float) -> dict:
    pid = persona_dir.name
    run_dir = out_root / pid
    if run_dir.exists():
        shutil.rmtree(run_dir)
    data_dir = run_dir / "data"
    run_dir.mkdir(parents=True)

    # seeds MUST be embedded with the same embedder the engine will query with,
    # or cosine similarity is garbage in live tier (ledger C1)
    seed_env = dict(os.environ)
    seed_env["ANTICIPY_MEMORY_MODE"] = "live" if tier == "live" else "stub"
    seed = subprocess.run([str(PY), str(REPO / "factory/bin/seed_memory.py"),
                           "--persona", str(persona_dir), "--data", str(data_dir)],
                          capture_output=True, text=True, env=seed_env)
    (run_dir / "seed.out").write_text(seed.stdout + seed.stderr, encoding="utf-8")
    if seed.returncode != 0:
        return {"persona": pid, "error": f"seed failed: {seed.stderr[:300]}"}

    env = engine_env(data_dir, tier)
    base = f"http://127.0.0.1:{port}"
    proc = boot_engine(port, env, run_dir / "engine.log", boot_timeout)
    days_out = []
    try:
        day_files = sorted((persona_dir / "days").glob("day*.txt"))
        for day in day_files:
            day_lap = f"{lap}-{pid}-{day.stem}"
            renv = dict(os.environ)
            renv.update({"ANTICIPY_ENGINE_BASE": base, "AUTOPILOT_LAP": day_lap,
                         "ANTICIPY_REALDAY_TIMEZONE": renv.get("ANTICIPY_REALDAY_TIMEZONE",
                                                               "America/Los_Angeles")})
            r = subprocess.run(["bash", str(REPO / "scripts/realday.sh"), str(day)],
                               cwd=str(REPO), env=renv, capture_output=True, text=True, timeout=1800)
            (run_dir / f"{day.stem}.harness.txt").write_text(r.stderr, encoding="utf-8")
            summary = None
            if r.returncode == 0:
                try:
                    summary = json.loads(r.stdout)
                except Exception:
                    pass
            if summary is None:
                days_out.append({"day": day.stem, "error": f"realday rc={r.returncode}",
                                 "stdout_tail": r.stdout[-500:]})
                continue
            (run_dir / f"{day.stem}.summary.json").write_text(
                json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
            days_out.append({"day": day.stem, "ok": True,
                             "decisions": summary.get("decisions", {})})

        dumps = {}
        for name, path in (("glassbox", "/glassbox?limit=1000"), ("pending", "/pending"),
                           ("scorecard", "/scorecard")):
            try:
                dumps[name] = http_json(base + path, timeout=15)
            except Exception as e:
                dumps[name] = {"error": str(e)}
        (run_dir / "dumps.json").write_text(json.dumps(dumps, indent=2, sort_keys=True),
                                            encoding="utf-8")
    finally:
        kill_engine(proc)

    goals = collect_goals(data_dir)
    (run_dir / "goals.json").write_text(json.dumps(goals, indent=2, sort_keys=True),
                                        encoding="utf-8")
    # a failed day must fail the persona loudly — silently dropping a day from scoring
    # makes the lap look better than reality (ledger C4)
    day_errors = [d for d in days_out if d.get("error")]
    result = {"persona": pid, "days": days_out, "goals": len(goals), "port": port, "tier": tier}
    if day_errors:
        result["error"] = f"{len(day_errors)} day(s) failed: " + "; ".join(
            str(d.get("error"))[:80] for d in day_errors)
    (run_dir / "run.json").write_text(json.dumps(result, indent=2, sort_keys=True),
                                      encoding="utf-8")
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bank", default="factory/personas/dev")
    ap.add_argument("--personas", default="", help="comma list; default = all in bank")
    ap.add_argument("--lap", required=True)
    ap.add_argument("--tier", default="stub", choices=["stub", "live"])
    ap.add_argument("--out", default="")
    ap.add_argument("--port-base", type=int, default=int(os.environ.get("PERSONA_PORT_BASE", "8801")))
    ap.add_argument("--boot-timeout", type=float,
                    default=float(os.environ.get("ENGINE_BOOT_TIMEOUT_SECONDS", "45")))
    args = ap.parse_args()

    bank = (REPO / args.bank).resolve()
    out_root = Path(args.out) if args.out else REPO / "logs/factory/runs" / args.lap
    out_root.mkdir(parents=True, exist_ok=True)

    if args.personas:
        persona_dirs = [bank / p.strip() for p in args.personas.split(",") if p.strip()]
    else:
        persona_dirs = sorted(d for d in bank.iterdir() if d.is_dir())
    missing = [str(d) for d in persona_dirs if not (d / "persona.json").exists()]
    if missing:
        print(f"persona_run: missing persona.json in {missing}", file=sys.stderr)
        return 2

    results, port = [], args.port_base
    for d in persona_dirs:
        while not port_free(port):
            port += 1
        try:
            results.append(run_persona(d, args.lap, port, out_root, args.tier, args.boot_timeout))
        except Exception as e:
            results.append({"persona": d.name, "error": f"{type(e).__name__}: {e}"})
        port += 1

    manifest = {"lap": args.lap, "bank": str(bank.relative_to(REPO)), "tier": args.tier,
                "results": results}
    (out_root / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True),
                                            encoding="utf-8")
    print(json.dumps(manifest, indent=2, sort_keys=True))
    errors = [r for r in results if r.get("error")]
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
