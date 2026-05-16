"""P0 / P10 resource envelope gate.

Runs the suite under a 2 GB home base class cap, deliberately below Mac
class, so Mac class resource assumptions cannot be silently baked in.

Two layers, honestly reported:
  1. A best effort hard cap via RLIMIT_AS. On macOS lowering the address
     space limit for a CPython process with large shared mappings is not
     reliably enforceable; this is stated, not hidden.
  2. The binding check: measured peak resident set (ru_maxrss, normalized
     per platform) must stay under 2 GB.

P0 runs the harness empty (zero categories), which proves the harness
and the whole spine execute within the envelope before any model work.
"""

from __future__ import annotations

import resource
import sys
import tempfile
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent.parent
if str(ENGINE) not in sys.path:
    sys.path.insert(0, str(ENGINE))

CAP_BYTES = 2 * 1024 ** 3  # 2 GB


def _maxrss_bytes() -> int:
    ru = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    ruc = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    # Linux reports kilobytes, macOS/BSD reports bytes.
    unit = 1 if sys.platform == "darwin" else 1024
    return max(ru, ruc) * unit


def main(categories: list[str] | None = None) -> int:
    import os

    os.environ["ANTICIPY_DATA_DIR"] = tempfile.mkdtemp(prefix="anticipy_res_")

    enforced = False
    try:
        soft, hard = resource.getrlimit(resource.RLIMIT_AS)
        resource.setrlimit(resource.RLIMIT_AS, (CAP_BYTES, hard if hard != resource.RLIM_INFINITY else CAP_BYTES))
        new_soft, _ = resource.getrlimit(resource.RLIMIT_AS)
        enforced = new_soft == CAP_BYTES
    except (ValueError, OSError) as e:
        print(f"RLIMIT_AS not enforceable on this platform ({e}); relying on measured RSS")

    from app.anticipy import harness

    cats = categories or []
    sb = harness.run_suite(cats, None, "p0-resource-empty")
    peak = _maxrss_bytes()
    peak_mb = peak / (1024 ** 2)
    within = peak < CAP_BYTES
    print(f"RLIMIT_AS hard enforced: {enforced}")
    print(f"empty_run: {sb.get('empty_run')} elapsed={sb.get('elapsed_s')}s")
    print(f"peak RSS: {peak_mb:.1f} MB  cap: {CAP_BYTES / (1024 ** 2):.0f} MB  within={within}")
    print("RESOURCE_GATE_PASS" if within else "RESOURCE_GATE_FAIL")
    return 0 if within else 1


if __name__ == "__main__":
    sys.exit(main())
