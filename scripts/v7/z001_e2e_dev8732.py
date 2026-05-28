"""Run z001 harness against the dev engine on port 8732.

This wrapper retargets only the ENGINE URL constant. All verification
logic, all DOM evidence checks, all tab leakage accounting, all the
real-Gmail-draft assertions remain exactly as the frozen harness
defines them. Nothing about the pass/fail criteria is touched.

Usage:
    python scripts/v7/z001_e2e_dev8732.py
"""
import sys

sys.path.insert(0, "/Users/omarebrahim/Developer/Anticipy-V7/scripts/v7")

import z001_e2e_harness as h  # noqa: E402

h.ENGINE = "http://127.0.0.1:8732"

if __name__ == "__main__":
    sys.exit(h.main())
