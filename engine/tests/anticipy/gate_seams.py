"""P0 seam gate: every typed seam interface imports, instantiates, and
structurally type checks. The core (P2 onward) consumes these from day
one, so they must be real and stable before anything uses them.
"""

from __future__ import annotations

import sys
import tempfile
from dataclasses import fields, is_dataclass
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent.parent
if str(ENGINE) not in sys.path:
    sys.path.insert(0, str(ENGINE))


def main() -> int:
    import os

    os.environ["ANTICIPY_DATA_DIR"] = tempfile.mkdtemp(prefix="anticipy_seam_")
    from app.anticipy import platform_adapter
    from app.anticipy.seams import (
        EngineDecision,
        InboundMessage,
        OutboundMessage,
        TranscriptLine,
        UserContext,
        UserProfile,
    )

    checks: list[tuple[str, bool]] = []

    prof = UserProfile(user_id="u1", name="Omar", role_title="Founder", mandate="run my ops", people={"the boss": "investor Dana"})
    checks.append(("UserProfile dataclass", is_dataclass(prof)))
    checks.append(("UserProfile.is_populated", prof.is_populated() is True))

    cold = UserContext.cold_start("u1")
    checks.append(("UserContext.cold_start conservative", cold.autonomy_level == 0.97 and cold.profile is None))
    fromp = UserContext.from_profile(prof)
    checks.append(("UserContext.from_profile binds", fromp.user_id == "u1" and fromp.profile is prof))

    inb = InboundMessage(source="direct", text="book the dinner", user_id="u1")
    checks.append(("InboundMessage.source literal", inb.source == "direct"))
    rep = InboundMessage(source="reply", text="7pm is fine", user_id="u1", in_reply_to="task-9")
    checks.append(("InboundMessage reply carries task", rep.in_reply_to == "task-9"))

    out = OutboundMessage(task_id="t1", user_id="u1", channel="text", body="party size?")
    checks.append(("OutboundMessage.to_dict", out.to_dict()["channel"] == "text"))

    line = TranscriptLine(speaker_id="WEARER", text="email Sarah", ts=1.0)
    checks.append(("TranscriptLine WEARER label", line.speaker_id == "WEARER"))

    dec = EngineDecision(decision="ASK", confidence=0.4, evidence="ambiguous", unit_text="x", user_id="u1")
    checks.append(("EngineDecision.to_dict", dec.to_dict()["decision"] == "ASK"))

    # all seam dataclasses expose stable named fields (the contract later
    # phases fill in without touching core logic)
    for cls in (UserProfile, UserContext, InboundMessage, OutboundMessage, TranscriptLine, EngineDecision):
        checks.append((f"{cls.__name__} has fields", len(fields(cls)) > 0))

    # the adapter exposes every promised seam symbol
    for sym in ("model_call", "adversarial_model_call", "data_dir", "user_data_dir",
                "transcript_source", "direct_command_source", "comms_send",
                "comms_receive", "action_engine_invoke", "supabase_client",
                "service_role_client"):
        checks.append((f"adapter.{sym}", hasattr(platform_adapter, sym)))

    ok_all = all(v for _, v in checks)
    for name, v in checks:
        print(f"  [{'ok' if v else 'FAIL'}] {name}")
    print("SEAMS_GATE_PASS" if ok_all else "SEAMS_GATE_FAIL")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
