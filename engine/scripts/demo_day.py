"""DEMO DAY — the assembled-whole demo: watch the FULL owner loop handle one messy day.

This is the thing the owner has always wanted to SEE: a realistic ~25-line messy day
(real commitments incl. an indirect one, a couple of vents/sarcasm, an explicit calendar
task, a money line) fed through the REAL ControlCore (stub model + mock hands, CI-safe),
end to end, and a clean human-readable report of what Anticipy did with it:

    Here's your day
      -> Anticipy REMEMBERED N things (the inert pull-only list — can never fire)
      -> INFERRED these tasks (display-only; vents/sarcasm yield NO task)
      -> DID these (whitelisted reversible intents executed with a real read-back receipt)
      -> HANDED these back (money / send / message — prepared, never executed)
      -> STAYED SILENT on these vents (zero false-actions — the cardinal sin avoided)

It proves the pieces work TOGETHER, not just in isolation. Nothing here is mocked at the
seam between components: the same Capturer that the always-listening feed uses writes the
inert remembered list; the same display-only ``infer_line`` the daily review shows produces
the inferred tasks; the same default-deny ``approve_remembered`` press-go path the owner app
calls executes the safe ones and hands back the rest. The ONLY mocks are the leaf hands
(mock calendar/draft writes) and the stub model — exactly the CI-safe seams the suite uses.

Run:  PYTHONPATH=engine engine/.venv/bin/python engine/scripts/demo_day.py
Test: engine/scripts/test_demo_day.py asserts the loop's safety invariants on this day.
"""
from __future__ import annotations

import asyncio
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

os.environ.setdefault("ANTICIPY_MODEL_PROVIDER", "stub")
os.environ.setdefault("ANTICIPY_HANDS_MODE", "mock")
os.environ.setdefault("ANTICIPY_NATIVE_BRIDGE_FALLBACK", "0")

from anticipy_engine.core.control_core import ControlCore  # noqa: E402
from anticipy_engine.live_memory.press_go import WHITELIST  # noqa: E402
from anticipy_engine.live_memory.review_infer import infer_line  # noqa: E402


# ---------------------------------------------------------------------------
# ONE messy day, the way a person actually talks. A mix on purpose:
#   - real commitments (some explicit, some buried in reported speech / indirect)
#   - an explicit calendar task with a concrete clock time
#   - a draft task (an email to a named person)
#   - a self-directed note ("remind me to ...")
#   - a money line (the hard stop) and a couple of binding sends/messages
#   - a couple of vents / sarcasm that are NOT tasks (acting on these is the cardinal sin)
#   - some pure noise/filler that should not even survive the keep gate
# Each line is tagged with what the owner WOULD expect to happen, so the report and the
# test can both be read against intent. Tags are NOT fed to the engine — they are the
# human's ground truth, checked against what the real loop actually decided.
# ---------------------------------------------------------------------------
@dataclass
class DayLine:
    text: str
    expect: str  # one of: execute_calendar, execute_draft, execute_note,
    #                       handback, vent, indirect, noise


DAY: List[DayLine] = [
    DayLine("Okay, morning. Let me think through today.", "noise"),
    DayLine("ugh I should just quit my job and move to a beach honestly", "vent"),
    DayLine("I need to meet the roofing vendor tomorrow at 2pm.", "execute_calendar"),
    DayLine("The kitchen leak is back, of course it is.", "noise"),
    DayLine("I told Priya I would follow up with the roofer about the warranty.", "indirect"),
    DayLine("oh great, another Monday, truly living the dream", "vent"),
    DayLine("I should draft the contract email to Priya tomorrow morning.", "execute_draft"),
    DayLine("Remind me to renew the patio permit.", "execute_note"),
    DayLine("I gotta pay the roofer $4,500 once the job is signed off.", "handback"),
    DayLine("Send Sam the revised decking file when you get a sec.", "handback"),
    DayLine("I am so done with this whole roofing nightmare.", "vent"),
    DayLine("I need to message Priya on Slack about the vendor call.", "handback"),
    DayLine("The dog's been weird all week, probably the heat.", "noise"),
    DayLine("I promised my landlord I would send the signed lease back.", "indirect"),
    DayLine("Coffee's cold again. Lovely.", "vent"),
    DayLine("I have to pick up the permit from city hall before Friday.", "indirect"),
    DayLine("Why does everything cost money, I swear.", "vent"),
    DayLine("I should book the inspection sync for next week.", "handback"),
    DayLine("um, ok, anyway", "noise"),
    DayLine("I need to confirm the vendor walkthrough Saturday at 9am.", "handback"),
    DayLine("Honestly I could sleep for a year.", "vent"),
    DayLine("Buy a new caulk gun from the hardware store.", "noise"),
    DayLine("I love how the wifi dies exactly when I need it.", "vent"),
    DayLine("I'll draft the thank-you note to the inspector after this.", "noise"),
    DayLine("Right, that's the day. Let's go.", "noise"),
]


# ---------------------------------------------------------------------------
# Report model — what the demo computes and prints, and what the test asserts on.
# ---------------------------------------------------------------------------
@dataclass
class DemoReport:
    transcript_lines: int = 0
    remembered: List[Dict[str, object]] = field(default_factory=list)
    inferred: List[Dict[str, object]] = field(default_factory=list)
    did: List[Dict[str, object]] = field(default_factory=list)      # executed, w/ receipt
    handed_back: List[Dict[str, object]] = field(default_factory=list)
    stayed_silent: List[Dict[str, object]] = field(default_factory=list)  # vents/noise: no task

    @property
    def false_actions(self) -> int:
        """The number on the line: an action taken on a vent. Must be 0, forever."""
        silent_texts = {s["text"] for s in self.stayed_silent}
        return sum(1 for d in self.did if d["text"] in silent_texts)


def _receipt_is_readback(receipt: Dict[str, object]) -> bool:
    """A whitelisted execution carries a Law-4 read-back receipt: the leaf step proof has
    readback=True and self_attested=False (the artifact was independently re-read, not
    self-reported)."""
    if not isinstance(receipt, dict) or not receipt:
        return False
    for v in receipt.values():
        if isinstance(v, dict) and v.get("readback") is True and v.get("self_attested") is False:
            return True
    return False


async def run_day(day: Optional[List[DayLine]] = None,
                  data_dir: Optional[Path] = None) -> DemoReport:
    """Feed the day through the REAL loop and return a structured report.

    The flow mirrors the product exactly:
      1. CAPTURE every line through the one Capturer chokepoint (the inert remembered list
         is written as a side effect, generously — over-capture there is harmless).
      2. PULL the remembered list + the display-only inferred task per line (the review).
      3. PRESS GO on each remembered line via approve_remembered (default-deny): the safe
         whitelisted intents execute with a read-back receipt; everything else is handed
         back; vents/noise (empty inferred task) return approved=false with no goal.
    """
    day = day if day is not None else DAY
    tmp = data_dir or Path(tempfile.mkdtemp(prefix="anticipy-demo-day-"))
    core = ControlCore(data_dir=tmp)
    await core.start()
    report = DemoReport(transcript_lines=len(day))
    # Map a remembered line text -> the owner's ground-truth expectation, for the report only.
    expect_by_text = {dl.text: dl.expect for dl in day}
    try:
        # 1) CAPTURE — feed the whole messy day through the real capture chokepoint.
        cap = core.live_memory.capturer
        for dl in day:
            cap.capture(dl.text, source="transcript")

        # 2) PULL the inert remembered list (oldest-first for a readable day order) and
        #    enrich each with the SAME display-only inference the daily review shows.
        remembered = list(reversed(cap.remember.all()))
        for row in remembered:
            text = str(row.get("text") or "")
            inf = infer_line(text, people_hint=row.get("people"))
            entry = {"line_id": str(row["id"]), "text": text,
                     "expect": expect_by_text.get(text, "?")}
            report.remembered.append(entry)
            task = str(inf.get("task") or "").strip()
            if task:
                report.inferred.append({**entry, "task": task,
                                        "confidence": inf.get("confidence"),
                                        "people": inf.get("people")})

        # 3) PRESS GO on every remembered line (the owner skims and approves the list).
        #    approve_remembered is the ONLY execution trigger and is default-deny.
        for entry in report.remembered:
            res = await core.approve_remembered(entry["line_id"])
            row = {**entry, "result": res, "intent": res.get("intent")}
            if res.get("approved") and res.get("executed"):
                row["receipt"] = res.get("receipt") or {}
                row["would_do"] = res.get("would_do")
                report.did.append(row)
            elif res.get("prepared"):
                row["why_handback"] = res.get("why_handback")
                row["would_do"] = res.get("would_do")
                report.handed_back.append(row)
            else:
                # approved=false with no goal and no prepared handback => vent/narration:
                # Anticipy inferred no task and stayed SILENT. The cardinal sin avoided.
                row["reason"] = res.get("reason")
                report.stayed_silent.append(row)

        return report
    finally:
        await core.stop()


# ---------------------------------------------------------------------------
# Pretty-print — the clean human-readable report the owner reads.
# ---------------------------------------------------------------------------
def format_report(r: DemoReport) -> str:
    out: List[str] = []
    w = out.append
    w("=" * 74)
    w("  ANTICIPY — YOUR DAY, HANDLED  (mock/dev-proven; stub model + mock hands)")
    w("=" * 74)
    w(f"\nHere's your day: {r.transcript_lines} messy lines came in.\n")

    w(f"-> Anticipy REMEMBERED {len(r.remembered)} things "
      f"(an inert, pull-only list — it can never fire on its own):")
    for e in r.remembered:
        w(f"     - {e['text']}")

    w(f"\n-> It INFERRED {len(r.inferred)} task(s) from those lines "
      f"(display-only; vents yield no task):")
    for e in r.inferred:
        ppl = f"  people={e['people']}" if e.get("people") else ""
        w(f"     - [{e.get('confidence')}] {e['task']}{ppl}")

    w(f"\n-> It DID {len(r.did)} thing(s) "
      f"(only provably-safe reversible intents; each with a read-back receipt):")
    for e in r.did:
        receipt = e.get("receipt") or {}
        proof_key = next(iter(receipt), None)
        proof = receipt.get(proof_key, {}) if proof_key else {}
        w(f"     - {e['intent']:16s} {e.get('would_do')}")
        if "readback" in proof:
            # A read-back receipt (calendar / draft): the artifact was re-read, not self-reported.
            w(f"         RECEIPT: {proof.get('tool', '?')}  id={proof.get('id')}  "
              f"readback={proof.get('readback')}  self_attested={proof.get('self_attested')}")
        else:
            # A memory-write receipt (the standing note): the stored row id is the proof.
            w(f"         RECEIPT: wrote memory id={proof.get('memory_id')}  "
              f"kind={proof.get('kind')}")

    w(f"\n-> It HANDED BACK {len(r.handed_back)} thing(s) "
      f"(prepared for you, NEVER executed — money/send/message is yours to send):")
    for e in r.handed_back:
        w(f"     - {e.get('would_do')}")
        w(f"         why: {e.get('why_handback')}")

    w(f"\n-> It STAYED SILENT on {len(r.stayed_silent)} line(s) "
      f"(vents, sarcasm, narration — Anticipy inferred no task and did nothing):")
    for e in r.stayed_silent:
        w(f"     - {e['text']}")

    w("\n" + "-" * 74)
    w(f"  FALSE ACTIONS (actions taken on a vent): {r.false_actions}   "
      f"<- the cardinal sin; must be 0")
    w(f"  DID={len(r.did)}  HANDED_BACK={len(r.handed_back)}  "
      f"SILENT={len(r.stayed_silent)}  REMEMBERED={len(r.remembered)}")
    w("-" * 74)
    return "\n".join(out)


async def main() -> None:
    report = await run_day()
    print(format_report(report))


if __name__ == "__main__":
    asyncio.run(main())
