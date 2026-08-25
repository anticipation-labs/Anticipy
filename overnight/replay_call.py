"""Replay a recorded call through the CURRENT brain and watch where it goes.

The 2026-08-23 Tejas call is a paired eval: we know exactly what the live
system did that evening (131 ignore / 6 act / 0 ask, four mid-call texts,
one invented human being), because it is all recorded in
research/evals/call-2026-08-23-tejas/. This script feeds the very same 137
lines, in order, on the recording's own clock, through the brain as it is
NOW — and prints every moment she would have spoken, plus the digest after
the call ends.

Honesty rules, same as overnight/evaluate.py:
  * The REAL Anticipy.hear() runs — nothing reimplemented, nothing mocked
    but the world: brain.pb is patched to an in-memory jobs list and
    notify_owner is captured, so no text, job, or card leaves this process.
  * The REAL meeting_heard() from brain/worker.py decides the posture, fed
    the recording's own timestamps — not wall clock, because density is the
    signal and the density lived in those timestamps.
  * speaker stays empty on every line, exactly as build 75 delivered them.
    Replaying with attribution she did not have would be flattery.
  * Live model only (the production one). The offline heuristic judges
    nothing like gemini-2.5-flash and a replay on it would be fiction.

Run:  OPENROUTER_API_KEY=... ANTICIPY_MODEL=google/gemini-2.5-flash \
      [ANTICIPY_STRONG_MODEL=google/gemini-2.5-pro] \
      PYTHONPATH=. python3 overnight/replay_call.py
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
# The credentials were always next to the gate; nothing loaded them, so
# legs that COULD be measured reported "cannot be tested" and the
# scoreboard named the wrong leg to work. Explicit environment still wins.
sys.path.insert(0, HERE if 'HERE' in dir() else os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402  sibling module; gates are run as scripts
_ENV_LOADED = _env.load_and_announce(ROOT)


EVAL = os.path.join(ROOT, "research", "evals", "call-2026-08-23-tejas",
                    "call_transcripts.json")


def ts(row) -> float:
    raw = (row.get("capture_started_at") or row.get("created") or "").replace(
        "Z", "+00:00").replace(" ", "T")
    try:
        return datetime.fromisoformat(raw).timestamp()
    except Exception:
        return 0.0


def main() -> int:
    if not (os.environ.get("OPENROUTER_API_KEY")
            or os.environ.get("GEMINI_API_KEY")):
        print("no model key in the environment — a heuristic replay would be "
              "fiction, refusing to pretend")
        return 2

    import brain.pb as pb
    from brain.anticipy_core import Anticipy
    from brain.llm import LLM
    from brain import worker

    rows = sorted(json.load(open(EVAL)), key=ts)
    print(f"replaying {len(rows)} lines from the recorded call "
          f"({rows[0].get('created')} .. {rows[-1].get('created')})")

    # The world, faked: jobs land in a list, patches no-op, texts append.
    jobs: list = []
    class R:
        ok = True
        status_code = 200
        def __init__(self, payload): self._p = payload
        def json(self): return self._p
        def raise_for_status(self): return None
    def fake_get(url, *a, **k):
        return R({"items": [j for j in jobs
                            if j.get("status") in ("queued", "waiting")]})
    def fake_post(url, *a, **k):
        j = dict((k.get("json") or {}), id=f"job{len(jobs)+1}")
        jobs.append(j)
        return R(j)
    pb.get, pb.post, pb.patch = fake_get, fake_post, (lambda *a, **k: R({}))

    sent_during: list = []
    a = Anticipy(llm=LLM(owner_zone="America/Vancouver"),
                 backend_url="http://replay", owner_ref="replay")
    a.notify_owner = lambda text, channel="sms": (
        sent_during.append(text) or {"replay": True})

    decisions = {"ignore": 0, "act": 0, "ask": 0}
    acts: list = []
    ctx: list = []          # rolling same-conversation context, capped like
                            # segmenter.recent_turns
    armed_at = None
    for i, row in enumerate(rows):
        line = (row.get("text") or "").strip()
        if not line:
            continue
        now = ts(row)
        worker.LAST_HEARD_AT = now
        in_meeting = worker.meeting_heard(now=now)
        if in_meeting and armed_at is None:
            armed_at = i
            print(f"  [line {i}] MEETING POSTURE ARMED")
        out = a.hear(line, context=ctx[-8:],
                     may_say=lambda *ar, **kw: True,
                     explicit=bool(row.get("explicit")),
                     in_meeting=in_meeting)
        d = out["decision"]
        decisions[d.decision] = decisions.get(d.decision, 0) + 1
        if d.decision in ("act", "ask") or out.get("anticipy_says"):
            acts.append((i, line, d.decision, d.goal,
                         out.get("anticipy_says")))
            print(f"  [line {i}] {line[:60]!r} -> {d.decision}"
                  f" goal={d.goal!r} says={out.get('anticipy_says')!r}")
        ctx.append(line)

    # The call ends: the settle window passes and the digest speaks.
    digest = a.meeting_digest()

    print()
    print("=" * 68)
    print("RECORDED that evening : 131 ignore / 6 act / 0 ask · "
          "4 mid-call texts · 0 digests · 1 invented person")
    print(f"REPLAY on this brain  : {decisions.get('ignore',0)} ignore / "
          f"{decisions.get('act',0)} act / {decisions.get('ask',0)} ask · "
          f"{len(sent_during)} mid-call texts · "
          f"digest={'yes' if digest else 'none'}")
    if armed_at is not None:
        print(f"posture armed at line {armed_at} of {len(rows)}")
    for t in sent_during:
        print(f"  mid-call text: {t!r}")
    if digest:
        print(f"  after-call digest: {digest!r}")
    print(json.dumps({"replay": "tejas-call", "decisions": decisions,
                      "mid_call_texts": len(sent_during),
                      "held_for_digest": bool(digest),
                      "digest": digest, "armed_at_line": armed_at,
                      "act_or_ask_moments": len(acts)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
