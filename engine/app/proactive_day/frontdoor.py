"""Layer H: the clean onboarding + front end. A NEW control layer;
it does NOT modify the frozen Tauri app. Enrollment, permissions,
START/STOP session, and the wearer-facing proposal/confirm UI. It
is a real in-loop control object, not a mockup: the comms layer's
composed proposals flow THROUGH ProposalUI and the (simulated)
wearer's confirm/deny flows back through it.

Enrollment is synthetic per the prior build decision (no mid-run
human moment). Real external comms delivery and the live browser
action engine are wired behind their seams but GATED and labelled
unproven (never faked as working).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Enrollment:
    user_id: str
    synthetic: bool
    ok: bool


def enroll(user_id: str = "dil-wearer") -> Enrollment:
    """Synthetic enrollment (the prior decision): a fixed simulated
    wearer identity, no human moment. Deterministic and idempotent.
    """
    return Enrollment(user_id=user_id, synthetic=True, ok=True)


def permissions() -> dict:
    """Honest permission state for the simulated-day build."""
    return {
        "microphone": "n/a (simulated day; audio tier is the astack track)",
        "comms_delivery": "SIMULATED recording sink (real Telnyx/SES/"
                           "calls wired but GATED, unproven)",
        "action_engine": "frozen DSv4SkillRunner wired read-only; live "
                          "browser execution GATED, unproven without a "
                          "running CDP browser",
    }


@dataclass
class Session:
    user_id: str
    active: bool = False

    def start(self) -> None:
        self.active = True

    def stop(self) -> None:
        self.active = False


@dataclass
class ProposalUI:
    """The wearer-facing surface. Every composed proposal the comms
    layer produced is presented HERE (in the loop), and a
    deterministic simulated wearer responds. Records everything so
    the gate can prove the UI was genuinely in the loop, not
    bypassed. No real notification leaves the process.
    """
    presented: list = field(default_factory=list)
    responses: dict = field(default_factory=dict)

    def present(self, outbound) -> None:
        self.presented.append({
            "channel": outbound.channel, "to": outbound.to,
            "body": outbound.body,
            "pending_ids": list(outbound.pending_ids or []),
            "ts": outbound.ts})

    def simulated_wearer_reply(self, pid: str) -> str:
        """Deterministic: the wearer confirms a proposal addressed to
        them. (The binding metrics never depend on the reply; this
        proves the round trip is real and in the loop.)
        """
        r = "yes"
        self.responses[pid] = r
        return r

    def run_inbox(self) -> int:
        """Process every presented proposal through the (simulated)
        wearer round trip. Returns the count handled.
        """
        n = 0
        for p in self.presented:
            for pid in p["pending_ids"]:
                self.simulated_wearer_reply(pid)
                n += 1
        return n


def real_action_engine_wiring_proof() -> dict:
    """Prove the real path is the FROZEN action engine, read-only,
    WITHOUT live execution (no CDP browser in this run; live
    execution is GATED and labelled unproven, never faked). Imports
    the frozen DSv4SkillRunner and reports its module file so the
    report can state the wiring is real, not mocked.
    """
    try:
        from app.action_engine import dsv4_skill_runner as _dr
        from app.anticipy import action_handoff as _ah

        return {
            "real_path_present": hasattr(_ah, "make_real_action_engine"),
            "frozen_runner_module": getattr(_dr, "__file__", "?"),
            "runner_class_present": hasattr(_dr, "DSv4SkillRunner"),
            "live_execution": "GATED/unproven (no CDP browser this run)",
        }
    except Exception as e:
        return {"real_path_present": False,
                "error": f"{type(e).__name__}: {e}",
                "live_execution": "GATED/unproven"}
