"""P0 durability gate: a real start, journal, hard kill, resume, verify
cycle across two separate OS processes.

phase1: start a workflow that journals two steps then suspends on an
external event, then hard exit with os._exit (no cleanup, simulating a
crash or the laptop sleeping and the process dying).

phase2: a fresh process. resume_all replays the journal (the two steps
must NOT re execute, proven by a side effect counter file that only the
real step body increments), then the external event is delivered and the
workflow runs its final step and completes.

Pass means: the side effect counter is exactly 3 (two steps ran once in
phase1, the final step ran once in phase2, replay re ran nothing), the
workflow status is completed, and the result is exactly correct.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent.parent
if str(ENGINE) not in sys.path:
    sys.path.insert(0, str(ENGINE))
PYBIN = str(ENGINE / ".venv" / "bin" / "python")
SELF = str(Path(__file__).resolve())


def _counter_path() -> Path:
    from app.anticipy import platform_adapter

    return platform_adapter.data_dir() / "side_effects.txt"


def _bump_counter() -> None:
    p = _counter_path()
    n = int(p.read_text()) if p.exists() else 0
    p.write_text(str(n + 1))


def _register():
    from app.anticipy import durable

    async def wf(ctx):
        a = await ctx.journal_step("s1", lambda: (_bump_counter(), "A")[1])
        b = await ctx.journal_step("s2", lambda: (_bump_counter(), "B")[1])
        payload = await ctx.await_external("go", timeout_s=None)
        c = await ctx.journal_step("s3", lambda: (_bump_counter(), "C")[1])
        return [a, b, c, payload]

    durable.register_workflow("p0_durable_probe", wf)
    return durable


def phase1() -> None:
    durable = _register()
    durable.start_workflow("p0_durable_probe", "wf-p0", {})
    cp = _counter_path()
    print(f"phase1 counter={cp.read_text() if cp.exists() else '0'} (expect 2)")
    info = durable.get_workflow("wf-p0")
    print(f"phase1 status={info['status']} (expect suspended)")
    sys.stdout.flush()
    os._exit(137)  # hard kill, no cleanup


def phase2() -> int:
    durable = _register()
    resumed = durable.resume_all()
    print(f"phase2 resume_all -> {resumed}")
    cp = _counter_path()
    after_resume = cp.read_text() if cp.exists() else "0"
    print(f"phase2 counter after replay={after_resume} (expect 2: replay re ran nothing)")
    out = durable.deliver_event("wf-p0", "go", {"v": 1})
    print(f"phase2 deliver_event -> {out}")
    info = durable.get_workflow("wf-p0")
    final_counter = cp.read_text() if cp.exists() else "0"
    print(f"phase2 final counter={final_counter} (expect 3)")
    print(f"phase2 status={info['status']} result={info['result']}")
    ok = (
        final_counter == "3"
        and info["status"] == "completed"
        and info["result"] == ["A", "B", "C", {"v": 1}]
        and after_resume == "2"
    )
    print("DURABLE_GATE_PASS" if ok else "DURABLE_GATE_FAIL")
    return 0 if ok else 1


def orchestrate() -> int:
    tmp = tempfile.mkdtemp(prefix="anticipy_durable_")
    env = dict(os.environ)
    env["ANTICIPY_DATA_DIR"] = tmp
    env["PYTHONPATH"] = str(ENGINE)
    p1 = subprocess.run([PYBIN, SELF, "phase1"], cwd=str(ENGINE), env=env, capture_output=True, text=True)
    print(p1.stdout.strip())
    if p1.stderr.strip():
        print("phase1 stderr:", p1.stderr.strip()[:400])
    # phase1 hard exits 137 by design
    p2 = subprocess.run([PYBIN, SELF, "phase2"], cwd=str(ENGINE), env=env, capture_output=True, text=True)
    print(p2.stdout.strip())
    if p2.stderr.strip():
        print("phase2 stderr:", p2.stderr.strip()[:400])
    return p2.returncode


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else "orchestrate"
    if arg == "phase1":
        phase1()
    elif arg == "phase2":
        sys.exit(phase2())
    else:
        sys.exit(orchestrate())
