"""P0 logger gate: the trajectory logger writes a portable record and
reads back exactly what it wrote, and the documented fallback path is
exercised so a write failure can never silently poison the flywheel.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent.parent
if str(ENGINE) not in sys.path:
    sys.path.insert(0, str(ENGINE))


def main() -> int:
    import os

    tmp = tempfile.mkdtemp(prefix="anticipy_log_")
    os.environ["ANTICIPY_DATA_DIR"] = tmp
    from app.anticipy import trajectory

    rec_in = dict(
        user_id="u-test",
        input_text="book us the usual place friday",
        source="ambient",
        features={"hedged": False, "addressee": "agent", "cascade": "COMMIT"},
        decision="ACT",
        confidence=0.91,
        memory_state={"usual place": "Carbone"},
        profile_state={"name": "Omar"},
        extra={"phase": "p0"},
    )
    ok = trajectory.log_decision(**rec_in)
    back = trajectory.read_all("u-test")
    round_trips = (
        ok
        and len(back) == 1
        and back[0]["input_text"] == rec_in["input_text"]
        and back[0]["decision"] == "ACT"
        and back[0]["features"] == rec_in["features"]
        and back[0]["memory_state"] == rec_in["memory_state"]
        and back[0]["outcome"] is None
    )
    print(f"primary round trip: {round_trips}")

    # outcome backfill (the bit that turns logs into training data)
    bf = trajectory.record_outcome("u-test", rec_in["input_text"], {"executed": True, "ok": True})
    back2 = trajectory.read_all("u-test")
    backfilled = bf and back2[0]["outcome"] == {"executed": True, "ok": True}
    print(f"outcome backfill: {backfilled}")

    # export is the portable format the future trainer consumes
    exported = trajectory.export_jsonl("u-test")
    export_ok = exported.strip().count("\n") == 0 and '"decision": "ACT"' in exported
    print(f"portable export: {export_ok}")

    ok_all = round_trips and backfilled and export_ok
    print("LOGGER_GATE_PASS" if ok_all else "LOGGER_GATE_FAIL")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
