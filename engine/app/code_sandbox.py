"""
Multi-tenant code sandbox for the Anticipy engine.

The browser agent (and future planner) calls `run_python` to execute Python
that the LLM wrote — for things the browser cannot do alone: text munging,
arithmetic, table parsing, regex extraction, date math, JSON manipulation.

Three layers of isolation, in this order:

  1. Process: a fresh `python3` subprocess (no shared memory with the engine).
  2. Kernel: `bwrap` (bubblewrap) wraps the subprocess in a user namespace
     with mountns + pidns + netns + utsns. Filesystem is read-only outside
     the per-tenant workdir; network is unshared (loopback only); the
     subprocess runs as uid 65534 (`nobody`) with all capabilities dropped.
  3. Resource: `setrlimit` caps CPU seconds, address space, FDs, NPROC.
     Wall-clock kill switch via `asyncio.wait_for`. Output truncated.

When `bwrap` is not available (developer laptop, container without userns)
the sandbox falls back to layer 1 + 3 only, and `CodeRunResult.degraded_isolation`
is set to True. Production deployments must run with bwrap.

Per-tenant: the optional `tenant_id` is included in the workdir prefix so
two simultaneous calls from different tenants get distinct mountns roots.
The mountns is destroyed at process exit; cross-tenant filesystem leakage
is structurally impossible under bwrap.

What it returns:
  CodeRunResult(stdout, stderr, exit_code, timed_out, duration_s,
                degraded_isolation, rejected_reason)

Hardware-transfer note (wearable companion / aarch64): bwrap is in
archlinuxarm, ubuntu/jammy/arm64, and alpine. Build needs only Linux ≥3.8
with CONFIG_USER_NS=y — every modern aarch64 kernel. No KVM, no daemon,
no Go runtime. Static-link is achievable (~50 KB binary).
"""

from __future__ import annotations

import asyncio
import logging
import os
import resource
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass

logger = logging.getLogger("engine.code_sandbox")


DEFAULT_CPU_SECONDS = 5
DEFAULT_WALL_TIMEOUT_S = 8.0
DEFAULT_MEMORY_MB = 256
DEFAULT_MAX_OUTPUT_BYTES = 64 * 1024  # 64 KB cap on combined stdout+stderr
DEFAULT_MAX_PROCS = 32  # RLIMIT_NPROC: cap fork bombs without choking thread pools
MAX_CODE_LENGTH = 16 * 1024


@dataclass
class CodeRunResult:
    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool
    duration_s: float
    degraded_isolation: bool = False
    rejected_reason: str | None = None


# Resolve once at import time. If bwrap is missing we degrade gracefully and
# log a single warning — caller can still see `degraded_isolation` per result.
_BWRAP_PATH: str | None = shutil.which("bwrap")
if _BWRAP_PATH is None:
    logger.warning(
        "code_sandbox_bwrap_missing",
        extra={"hint": "install `bubblewrap` for full multi-tenant isolation"},
    )


def _set_resource_limits(
    cpu_seconds: int,
    memory_mb: int,
    max_procs: int = DEFAULT_MAX_PROCS,
    *,
    set_nproc: bool = True,
) -> None:
    """Called inside the child process before exec to cap resources.

    `set_nproc=False` when running under bwrap: the rlimit is inherited by
    bwrap *before* it clones the sandboxed namespaces, and our engine user
    may already be at ~30 procs — a tight NPROC cap on the parent would
    refuse bwrap's own clone() call. Under bwrap we apply NPROC inside the
    sandboxed Python instead via a code prefix (`_NPROC_PREFIX`), where
    uid 65534 starts at 0 procs.

    Without bwrap, NPROC must be set here on the subprocess so the
    engine's user gets a per-uid cap that includes the new sandbox proc.
    """
    # CPU seconds — SIGXCPU at soft, SIGKILL at hard
    resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
    # Virtual memory
    mem_bytes = memory_mb * 1024 * 1024
    try:
        resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))
    except (ValueError, OSError):
        pass
    # File descriptors
    try:
        resource.setrlimit(resource.RLIMIT_NOFILE, (256, 256))
    except (ValueError, OSError):
        pass
    # No core dumps (don't write secrets to disk on crash)
    try:
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    except (ValueError, OSError):
        pass
    if set_nproc:
        try:
            resource.setrlimit(resource.RLIMIT_NPROC, (max_procs, max_procs))
        except (ValueError, OSError):
            pass
    # File size cap — anything written to /tmp inside the workdir
    try:
        resource.setrlimit(resource.RLIMIT_FSIZE, (16 * 1024 * 1024, 16 * 1024 * 1024))
    except (ValueError, OSError):
        pass


def _nproc_prefix(max_procs: int) -> str:
    """Code prefix that caps NPROC inside the sandboxed Python.

    Used under bwrap. The prefix runs as the first statement of the
    sandboxed program, so a fork bomb in the user code hits the cap
    immediately. The prefix is one line and doesn't change line numbers
    of later code if the user's traceback hits the prefix-vs-user
    boundary unusually."""
    return (
        f"import resource as _r;"
        f"_r.setrlimit(_r.RLIMIT_NPROC,({max_procs},{max_procs}));"
        f"del _r;"
    )


def _validate_code(code: str) -> str | None:
    """Cheap pre-flight check. NOT a sandbox; just bounces obvious foot-guns."""
    if not isinstance(code, str):
        return "code must be a string"
    if not code.strip():
        return "code is empty"
    if len(code) > MAX_CODE_LENGTH:
        return f"code exceeds {MAX_CODE_LENGTH} bytes"
    return None


def _bwrap_argv(workdir: str) -> list[str]:
    """Build the bwrap argv that wraps the python invocation.

    Mount layout the sandbox sees:
      /usr, /lib, /lib64, /etc/alternatives -> read-only host bind
      /proc -> fresh procfs (no host PIDs visible)
      /dev  -> minimal /dev (null, zero, urandom, full, tty)
      /tmp  -> tmpfs (per-call, freshly allocated)
      /work -> bind-mount of `workdir` from the host (RW), set as cwd
      everything else: not mounted

    Process attributes:
      uid/gid 65534 (nobody/nogroup), all caps dropped
      new pid namespace, new net namespace (no internet), new uts/mount/cgroup ns
      die with parent (sandbox dies if engine dies)
      new session (no TIOCSTI escape)
    """
    assert _BWRAP_PATH is not None
    return [
        _BWRAP_PATH,
        "--die-with-parent",
        "--new-session",
        "--unshare-all",
        "--uid", "65534",
        "--gid", "65534",
        # Read-only host filesystem — only the bare minimum to run python3
        "--ro-bind", "/usr", "/usr",
        "--ro-bind", "/lib", "/lib",
        # /lib64 only exists on x86_64; tolerate its absence on aarch64
        "--ro-bind-try", "/lib64", "/lib64",
        "--ro-bind-try", "/etc/alternatives", "/etc/alternatives",
        # Fresh procfs and /dev
        "--proc", "/proc",
        "--dev", "/dev",
        "--tmpfs", "/tmp",
        # Per-call tenant workdir, RW
        "--bind", workdir, "/work",
        "--chdir", "/work",
        # Clear the env, then add only the keys we want
        "--clearenv",
        "--setenv", "PATH", "/usr/bin:/bin",
        "--setenv", "LANG", "C.UTF-8",
        "--setenv", "PYTHONDONTWRITEBYTECODE", "1",
        # Drop all capabilities; the sandboxed code is uid=nobody anyway,
        # but defense in depth.
        "--cap-drop", "ALL",
        "--",
        "/usr/bin/python3", "-I", "-S", "-c",  # code goes after this in argv
    ]


async def run_python(
    code: str,
    *,
    tenant_id: str | None = None,
    cpu_seconds: int = DEFAULT_CPU_SECONDS,
    wall_timeout_s: float = DEFAULT_WALL_TIMEOUT_S,
    memory_mb: int = DEFAULT_MEMORY_MB,
    max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES,
    max_procs: int = DEFAULT_MAX_PROCS,
) -> CodeRunResult:
    """Run a Python snippet in a sandboxed subprocess. Async-friendly.

    `tenant_id` is included in the workdir prefix for traceability and so
    parallel calls from different tenants don't share a workdir name. The
    mountns isolation already prevents cross-tenant fs visibility.
    """
    rejected = _validate_code(code)
    if rejected:
        return CodeRunResult(
            stdout="", stderr="", exit_code=-1, timed_out=False, duration_s=0.0,
            rejected_reason=rejected,
        )

    # Workdir name: include tenant if provided, plus a uuid to avoid collisions.
    safe_tenant = "".join(c for c in (tenant_id or "anon") if c.isalnum() or c in "_-")[:32] or "anon"
    workdir = tempfile.mkdtemp(prefix=f"engine_codesandbox_{safe_tenant}_{uuid.uuid4().hex[:8]}_")
    # Ensure bwrap (running as uid 65534) can write into the workdir.
    try:
        os.chmod(workdir, 0o1777)
    except OSError:
        pass

    started = time.time()
    proc: asyncio.subprocess.Process | None = None
    timed_out = False
    degraded = _BWRAP_PATH is None

    try:
        if _BWRAP_PATH is not None:
            # Inject NPROC cap inside the sandbox itself (not on bwrap parent —
            # that would refuse bwrap's own clone() if the engine user is
            # already near its NPROC limit).
            sandboxed_code = _nproc_prefix(max_procs) + code
            argv = _bwrap_argv(workdir) + [sandboxed_code]
            proc = await asyncio.create_subprocess_exec(
                *argv,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"},
                preexec_fn=lambda: _set_resource_limits(
                    cpu_seconds, memory_mb, max_procs, set_nproc=False,
                ),
            )
        else:
            # Degraded path: subprocess + rlimit + tmpdir but no kernel sandbox.
            proc = await asyncio.create_subprocess_exec(
                sys.executable, "-I", "-S", "-c", code,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=workdir,
                env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"},
                preexec_fn=lambda: _set_resource_limits(
                    cpu_seconds, memory_mb, max_procs, set_nproc=True,
                ),
            )

        try:
            stdout_b, stderr_b = await asyncio.wait_for(
                proc.communicate(), timeout=wall_timeout_s,
            )
        except asyncio.TimeoutError:
            timed_out = True
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            try:
                stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=2.0)
            except (asyncio.TimeoutError, ProcessLookupError):
                stdout_b, stderr_b = b"", b""

        stdout_b = stdout_b[:max_output_bytes]
        stderr_b = stderr_b[:max_output_bytes]

        exit_code = proc.returncode if proc.returncode is not None else -1
        return CodeRunResult(
            stdout=stdout_b.decode("utf-8", errors="replace"),
            stderr=stderr_b.decode("utf-8", errors="replace"),
            exit_code=exit_code,
            timed_out=timed_out,
            duration_s=round(time.time() - started, 3),
            degraded_isolation=degraded,
        )
    except Exception as exc:
        logger.exception("code_sandbox_spawn_error")
        return CodeRunResult(
            stdout="", stderr=f"sandbox spawn error: {type(exc).__name__}",
            exit_code=-1, timed_out=False,
            duration_s=round(time.time() - started, 3),
            degraded_isolation=degraded,
            rejected_reason="spawn_error",
        )
    finally:
        try:
            shutil.rmtree(workdir, ignore_errors=True)
        except Exception:
            pass


def is_isolated() -> bool:
    """True if the strong (bwrap) sandbox is active. False if we are degraded."""
    return _BWRAP_PATH is not None


# ---------------------------------------------------------------------------
# Porting to the wearable companion (aarch64 Linux)
# ---------------------------------------------------------------------------
#
# The sandbox is intentionally portable. To run it on the on-device companion:
#
# 1. Install bubblewrap. Available on:
#       Alpine:      apk add bubblewrap
#       Debian/Ubuntu: apt-get install bubblewrap
#       Arch ARM:    pacman -S bubblewrap
#       Yocto:       meta-oe / meta-security recipe
#
# 2. Kernel requirements: Linux ≥ 3.8 with CONFIG_USER_NS=y and
#    CONFIG_USER_NS_UNPRIVILEGED=y. Every modern aarch64 kernel ships
#    with these. Verify with `unshare -U true` returning exit 0.
#
# 3. Drop the `--ro-bind /lib64` line if /lib64 doesn't exist (the
#    `--ro-bind-try` flag in `_bwrap_argv` already handles this — the
#    sandbox starts cleanly on aarch64 where /lib64 is absent).
#
# 4. Confirm uid 65534 ("nobody") exists in /etc/passwd. If not, edit
#    `_bwrap_argv` to use a uid that does — any non-root unprivileged
#    uid works; the namespace gives it 0 procs/files/caps inside.
#
# 5. CPython binary size: aarch64 builds add ~10–20% over x86_64. The
#    256 MB AS rlimit is comfortable headroom on a 1 GB-class wearable.
#
# 6. Cold-start latency: bwrap fork+pivot_root+exec adds ~10–25 ms;
#    CPython init with `-I -S` is ~30–60 ms on x86, ~60–120 ms on
#    Cortex-A. Total per call: ~50–80 ms (x86), ~100–180 ms (ARM).
#
# 7. If the wearable kernel ever drops user-ns support, swap bwrap for
#    `wasmtime + WASI` (single static binary, no kernel features needed,
#    stdlib-only Python via Pyodide-WASI). The interface in this file
#    (run_python -> CodeRunResult) stays unchanged — only `_bwrap_argv`
#    and the spawn block need rewriting.
