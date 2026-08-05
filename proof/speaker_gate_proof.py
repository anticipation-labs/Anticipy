"""The proof that speaker recognition changes the answer — Omar's own miss.

Live on 2026-08-05 the pendant heard:
    "Yo can you look into the flights for me yeah I bet where let's go to
     Paris tomorrow for sure I'll get into it"
and she could not know WHO said "I'll get into it" — Omar promising, or his
friend. Wording alone cannot decide it; that is why the line came back
"Noted — nothing needed" and Omar (rightly) called speaker recognition the
keystone.

This proof replays that EXACT line through the live model twice:
  tagged  speaker="other"  (the friend's voice said it)
  tagged  speaker="owner"  (Omar's own voice said it)
and demands the behaviour DIFFER in the one way that matters: when the
friend commits, no job may wait on Omar; when Omar commits, the work must
actually start (research queued, or prepared and held).

Run: OPENROUTER_API_KEY=... PYTHONPATH=. python3 proof/speaker_gate_proof.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain import pb  # noqa: E402

JOBS: list[dict] = []


class _R:
    def __init__(self, payload, ok=True):
        self._p, self.ok = payload, ok

    def json(self):
        return self._p

    def raise_for_status(self):
        if not self.ok:
            raise RuntimeError("http error")


pb.get = lambda url, params=None, timeout=None, **kw: _R(
    {"items": [j for j in JOBS if j["status"] in
               ((params or {}).get("filter", "") or "")]}) \
    if "/jobs/" in url else _R({"items": []})


def _post(url, json=None, timeout=None, **kw):
    if "/jobs/" not in url:
        return _R({"id": "x"})
    rec = dict(json or {})
    rec["id"] = f"job{len(JOBS) + 1}"
    JOBS.append(rec)
    return _R(rec)


pb.post = _post
pb.patch = lambda url, json=None, timeout=None, **kw: _R({})

from brain.anticipy_core import Anticipy  # noqa: E402
from brain.llm import LLM  # noqa: E402
from brain.memory import Memory  # noqa: E402

LINE = ("Yo can you look into the flights for me yeah I bet where let's go "
        "to Paris tomorrow for sure I'll get into it")


def run(speaker: str):
    JOBS.clear()
    llm = LLM()
    a = Anticipy(memory=Memory(llm=llm), llm=llm, owner_id="speaker-proof")
    texts: list[str] = []
    a.notify_owner = lambda m, channel="sms": texts.append(m) or {"ok": True}
    out = a.hear(LINE, speaker=speaker)
    d = out["decision"]
    print(f"  speaker={speaker!r}: decision={d.decision} addressee={d.addressee}")
    print(f"      goal={d.goal}")
    print(f"      jobs={[(j['goal'][:60], j['status']) for j in JOBS]}")
    return d, list(JOBS), texts


def main() -> int:
    llm = LLM()
    if not llm.live:
        print("SKIP speaker gate — needs the live model")
        return 0

    failures = []

    print("the friend's voice says it:")
    d_o, jobs_o, _ = run("other")
    held_o = [j for j in jobs_o if j["status"] == "awaiting_confirm"]
    if held_o:
        failures.append(
            f"friend's promise put work on OMAR's desk to approve: {held_o}")

    print("Omar's own voice says it:")
    d_own, jobs_own, _ = run("owner")
    if not jobs_own:
        failures.append("Omar's own commitment produced no work at all")

    print()
    if failures:
        for f in failures:
            print(f"FAIL {f}")
        print("\nSPEAKER GATE: NOT READY")
        return 1
    print("PASS the friend's 'I'll get into it' never waits on Omar's OK")
    print("PASS Omar's own words start real work")
    print("\nSPEAKER GATE: READY — same sentence, different mouth, "
          "different (correct) behaviour")
    return 0


if __name__ == "__main__":
    sys.exit(main())
