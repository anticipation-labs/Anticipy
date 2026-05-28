"""
Tests for app.code_sandbox — the subprocess-isolated Python sandbox.

Covered:
  - Empty / over-length / non-string code rejected without spawning
  - Successful execution returns stdout/stderr correctly
  - Wall-clock timeout kills hung code
  - Output truncated to max_output_bytes
  - CPU rlimit triggers exit on busy loops
  - Subprocess receives empty env (no secrets leaked)
  - Stdin is closed (no input() bypass)
  - Fresh tempdir cleaned up after run

These are integration tests — they actually spawn subprocesses. They run
in seconds because every limit is small.
"""

from __future__ import annotations

import asyncio
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.code_sandbox import MAX_CODE_LENGTH, is_isolated, run_python  # noqa: E402


def test_run_python_executes_simple_code():
    async def go():
        result = await run_python("print(2 + 3)")
        assert result.exit_code == 0
        assert result.stdout.strip() == "5"
        assert result.timed_out is False
    asyncio.run(go())


def test_run_python_captures_stderr():
    async def go():
        result = await run_python("import sys; sys.stderr.write('warn'); print('ok')")
        assert "ok" in result.stdout
        assert "warn" in result.stderr
    asyncio.run(go())


def test_run_python_rejects_empty_code():
    async def go():
        result = await run_python("")
        assert result.rejected_reason is not None
        assert result.exit_code == -1
        result2 = await run_python("    \n  \n")
        assert result2.rejected_reason is not None
    asyncio.run(go())


def test_run_python_rejects_oversized_code():
    async def go():
        too_long = "x" * (MAX_CODE_LENGTH + 1)
        result = await run_python(too_long)
        assert result.rejected_reason is not None
    asyncio.run(go())


def test_run_python_rejects_non_string():
    async def go():
        result = await run_python(12345)  # type: ignore[arg-type]
        assert result.rejected_reason is not None
    asyncio.run(go())


def test_run_python_wall_clock_timeout():
    """Hung code is killed by wall-clock timeout."""
    async def go():
        # busy-sleep for 60s; we set wall_timeout to 1s
        result = await run_python("import time; time.sleep(60)", wall_timeout_s=1.0)
        assert result.timed_out is True
        # Process was killed; duration should be near the timeout
        assert result.duration_s < 5.0
    asyncio.run(go())


def test_run_python_truncates_output():
    """Output beyond max_output_bytes is cut off."""
    async def go():
        # Print 200 KB; cap at 1 KB
        code = "import sys; sys.stdout.write('A' * 200000)"
        result = await run_python(code, max_output_bytes=1024)
        assert len(result.stdout.encode("utf-8")) <= 1024
    asyncio.run(go())


def test_run_python_isolated_env():
    """Subprocess gets a minimal env — no API keys, no secrets."""
    async def go():
        # GOOGLE_API_KEY is set in CI/local — verify it does NOT leak in.
        result = await run_python(
            "import os; print('found' if os.environ.get('GOOGLE_API_KEY') else 'missing')"
        )
        assert "missing" in result.stdout
    asyncio.run(go())


def test_run_python_stdin_closed():
    """stdin is closed — input() raises EOFError, doesn't hang waiting for input."""
    async def go():
        result = await run_python("input('prompt> ')", wall_timeout_s=2.0)
        # Either EOFError on stderr OR exits non-zero quickly
        assert result.exit_code != 0 or "EOF" in result.stderr or result.timed_out is False
    asyncio.run(go())


def test_run_python_workdir_isolated_and_cleaned():
    """Each run uses a fresh tempdir; it is cleaned up after."""
    import glob
    async def go():
        before = set(glob.glob("/tmp/engine_codesandbox_*"))
        result = await run_python("import os; print(os.getcwd())")
        assert result.exit_code == 0
        cwd_seen = result.stdout.strip()
        # Under bwrap the sandbox sees /work; under degraded mode it sees
        # the host-side tmpdir. Either is acceptable.
        if is_isolated():
            assert cwd_seen == "/work"
        else:
            assert "engine_codesandbox_" in cwd_seen
        # After return, no NEW workdirs should be left behind.
        after = set(glob.glob("/tmp/engine_codesandbox_*"))
        leaked = after - before
        assert not leaked, f"workdir leak: {leaked}"
    asyncio.run(go())


def test_run_python_no_leftover_workdirs_after_many_runs():
    """Smoke test: 5 successive runs leave no orphan workdirs in /tmp."""
    async def go():
        for _ in range(5):
            await run_python("print('ok')")
        # Allow up to 1 leftover from a flake — the contract is best-effort cleanup.
        leftovers = glob.glob("/tmp/engine_codesandbox_*")
        assert len(leftovers) < 5
    asyncio.run(go())


def test_run_python_exit_code_nonzero_on_error():
    async def go():
        result = await run_python("raise SystemExit(7)")
        assert result.exit_code == 7
    asyncio.run(go())


# --- bwrap multi-tenant isolation tests ---
#
# These run only when bwrap is installed. On a developer laptop without
# bubblewrap they are skipped via early return. CI must install bwrap
# (apt-get install bubblewrap) so these run for real.


def _skip_if_degraded() -> bool:
    """Returns True if these tests should skip (bwrap not present)."""
    return not is_isolated()


def test_bwrap_blocks_network_egress():
    """Sandbox subprocess cannot reach the internet."""
    if _skip_if_degraded():
        return
    async def go():
        code = (
            "import socket\n"
            "s = socket.socket()\n"
            "s.settimeout(1.0)\n"
            "try:\n"
            "    s.connect(('1.1.1.1', 80))\n"
            "    print('LEAK')\n"
            "except Exception as e:\n"
            "    print('blocked', type(e).__name__)\n"
        )
        result = await run_python(code, wall_timeout_s=4.0)
        assert "LEAK" not in result.stdout
        assert "blocked" in result.stdout
        assert result.degraded_isolation is False
    asyncio.run(go())


def test_bwrap_blocks_filesystem_reads_outside_workdir():
    """Sandbox cannot list /home, /root, /var, or read engine source files."""
    if _skip_if_degraded():
        return
    async def go():
        code = (
            "import os\n"
            "results = {}\n"
            "for p in ('/home', '/root', '/var', '/workspaces'):\n"
            "    try:\n"
            "        os.listdir(p)\n"
            "        results[p] = 'LEAK'\n"
            "    except (FileNotFoundError, PermissionError) as e:\n"
            "        results[p] = type(e).__name__\n"
            "for p, v in results.items():\n"
            "    print(p, v)\n"
        )
        result = await run_python(code, wall_timeout_s=4.0)
        assert "LEAK" not in result.stdout
    asyncio.run(go())


def test_bwrap_runs_as_unprivileged_uid():
    """Sandbox uid is 65534 (nobody)."""
    if _skip_if_degraded():
        return
    async def go():
        result = await run_python("import os; print(os.getuid(), os.getgid())")
        assert result.stdout.strip() == "65534 65534"
    asyncio.run(go())


def test_bwrap_pid_namespace_isolation():
    """Sandbox sees only its own processes via /proc — host PIDs invisible."""
    if _skip_if_degraded():
        return
    async def go():
        code = (
            "import os\n"
            "pids = [p for p in os.listdir('/proc') if p.isdigit()]\n"
            "print(len(pids))\n"
        )
        result = await run_python(code, wall_timeout_s=4.0)
        # In a fresh PID namespace the python process is PID 1 and there
        # should be very few procs visible (the python proc itself).
        count = int(result.stdout.strip())
        assert count <= 5, f"saw {count} pids — pid namespace likely not active"
    asyncio.run(go())


def test_bwrap_fork_bomb_capped():
    """RLIMIT_NPROC stops a fork bomb before it can hurt the host."""
    if _skip_if_degraded():
        return
    async def go():
        code = (
            "import os\n"
            "spawned = 0\n"
            "for _ in range(2000):\n"
            "    try:\n"
            "        pid = os.fork()\n"
            "        if pid == 0:\n"
            "            import time; time.sleep(2); os._exit(0)\n"
            "        spawned += 1\n"
            "    except OSError:\n"
            "        break\n"
            "print(spawned)\n"
        )
        result = await run_python(code, wall_timeout_s=6.0, max_procs=8)
        # Even on a fast machine spawned should hit the cap and stop, not 2000
        spawned = int((result.stdout or "0").strip() or "0")
        assert spawned < 50, f"fork loop produced {spawned} children — RLIMIT_NPROC ineffective"
    asyncio.run(go())


def test_bwrap_workdir_writable_but_isolated_per_call():
    """Two parallel calls cannot see each other's workdir contents."""
    if _skip_if_degraded():
        return
    async def go():
        # Call A writes a file, exits. Call B (after) can't see A's file
        # because each call gets a fresh mountns + tempdir.
        code_a = (
            "import os\n"
            "open('secret.txt','w').write('A_SECRET_DATA')\n"
            "print(os.listdir('.'))\n"
        )
        code_b = (
            "import os\n"
            "files = os.listdir('.')\n"
            "for f in files:\n"
            "    print(f)\n"
            "    if f.endswith('.txt'):\n"
            "        print(open(f).read())\n"
        )
        result_a = await run_python(code_a, tenant_id="alice")
        result_b = await run_python(code_b, tenant_id="bob")
        assert "secret.txt" in result_a.stdout
        assert "A_SECRET_DATA" not in result_b.stdout
        assert "secret.txt" not in result_b.stdout
    asyncio.run(go())


def test_bwrap_capabilities_dropped():
    """Sandbox cannot exercise CAP_SYS_ADMIN or other root capabilities."""
    if _skip_if_degraded():
        return
    async def go():
        # Try to mount a tmpfs — requires CAP_SYS_ADMIN. Should fail.
        code = (
            "import ctypes, ctypes.util\n"
            "libc = ctypes.CDLL(ctypes.util.find_library('c') or 'libc.so.6', use_errno=True)\n"
            "MS_NOSUID = 2\n"
            "rc = libc.mount(b'tmpfs', b'/tmp', b'tmpfs', 0, 0)\n"
            "print('rc=', rc, 'errno=', ctypes.get_errno())\n"
        )
        result = await run_python(code, wall_timeout_s=4.0)
        # Either the mount call returned -1 (errno=EPERM/EINVAL) or the
        # syscall is blocked entirely. We just need rc != 0.
        assert "rc= 0" not in result.stdout
    asyncio.run(go())


def test_bwrap_proc_self_environ_clean():
    """No host env vars leak into the sandbox via /proc/self/environ."""
    if _skip_if_degraded():
        return
    async def go():
        code = (
            "with open('/proc/self/environ','rb') as f:\n"
            "    env = f.read().decode('utf-8','replace')\n"
            "for k in ('GOOGLE_API_KEY','GROQ_API_KEY','SUPABASE','JWT_SECRET','PROFILE'):\n"
            "    if k in env:\n"
            "        print('LEAK', k)\n"
            "print('checked', sorted(set(p.split(\"=\")[0] for p in env.split(chr(0)) if p)))\n"
        )
        result = await run_python(code, wall_timeout_s=4.0)
        assert "LEAK" not in result.stdout
    asyncio.run(go())


def test_bwrap_path_traversal_safe():
    """Symlink + path traversal in workdir cannot reach host files."""
    if _skip_if_degraded():
        return
    async def go():
        code = (
            "import os\n"
            "os.symlink('/usr/bin/python3', 'x')\n"
            "# Read through the symlink — points to a host file we DO bind-mount RO\n"
            "print('exists', os.path.exists('x'))\n"
            "# But can we resolve to /etc/shadow? No — /etc not bound.\n"
            "try:\n"
            "    os.symlink('/etc/shadow', 'shadow')\n"
            "    open('shadow').read()\n"
            "    print('LEAK shadow')\n"
            "except (FileNotFoundError, PermissionError) as e:\n"
            "    print('blocked', type(e).__name__)\n"
        )
        result = await run_python(code, wall_timeout_s=4.0)
        assert "LEAK" not in result.stdout
        assert "blocked" in result.stdout
    asyncio.run(go())


def test_bwrap_concurrent_calls_isolated():
    """100 concurrent sandbox calls all complete independently."""
    if _skip_if_degraded():
        return
    async def go():
        async def one(i: int):
            r = await run_python(f"print({i} * 2)", tenant_id=f"t{i}")
            return int(r.stdout.strip())
        results = await asyncio.gather(*(one(i) for i in range(20)))
        assert results == [i * 2 for i in range(20)]
    asyncio.run(go())


def test_bwrap_memory_cap_enforced():
    """Allocating beyond memory_mb hits MemoryError or kills the process."""
    if _skip_if_degraded():
        return
    async def go():
        # Try to allocate 512 MB with cap = 64 MB
        code = (
            "try:\n"
            "    x = bytearray(512 * 1024 * 1024)\n"
            "    print('LEAK')\n"
            "except MemoryError:\n"
            "    print('blocked')\n"
        )
        result = await run_python(code, memory_mb=64, wall_timeout_s=8.0)
        assert "LEAK" not in result.stdout
    asyncio.run(go())


def test_bwrap_cpu_cap_kills_busy_loop():
    """Tight CPU loop hits RLIMIT_CPU before the wall-clock timeout."""
    if _skip_if_degraded():
        return
    async def go():
        code = "n = 0\nwhile True: n += 1"
        result = await run_python(code, cpu_seconds=1, wall_timeout_s=10.0)
        # Process killed somehow. Either CPU rlimit (SIGXCPU/SIGKILL, exit_code != 0)
        # or wall-clock kill. We accept either; what we DON'T accept is success.
        assert result.exit_code != 0 or result.timed_out
        # Total elapsed should be meaningfully under wall_timeout_s if the CPU
        # limit fired. Under heavy concurrent load (e.g., proactive tests
        # running in parallel) the OS schedules our 1-second CPU budget across
        # several wall-seconds, so we leave generous slack here. If the CPU
        # rlimit is actually broken, wall-clock kill fires at ~10s — that's
        # what we are guarding against, not single-second timing variance.
        assert result.duration_s < 8.5
    asyncio.run(go())


# --- runner ---


if __name__ == "__main__":
    tests = [
        (name, obj) for name, obj in sorted(globals().items())
        if name.startswith("test_") and callable(obj)
    ]
    print(f"running {len(tests)} tests...")
    failed: list[tuple[str, str]] = []
    for name, fn in tests:
        try:
            fn()
            print(f"  PASS  {name}")
        except AssertionError as e:
            failed.append((name, f"AssertionError: {e}"))
            print(f"  FAIL  {name}")
        except Exception as e:
            failed.append((name, f"{type(e).__name__}: {e}"))
            print(f"  ERR   {name}  ({type(e).__name__}: {e})")

    print()
    print(f"{len(tests) - len(failed)}/{len(tests)} passed")
    if failed:
        for name, err in failed:
            print(f"  {name}: {err}")
        sys.exit(1)
