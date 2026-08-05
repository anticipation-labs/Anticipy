"""Score the brain against Omar's real night. Two numbers that matter.

  FALSE FIRES — she did something about a line that deserved silence.
                (his complaint: dictating a list to his laptop became
                 three jobs)
  MISSES      — she stayed silent on a line that deserved work.
                (the failure that killed the product before: a whole
                 dinner agreed out loud, "Noted — nothing needed")

Any change that fixes one by breaking the other FAILS. That is the entire
point of scoring both at once, every time.

Run:  OPENROUTER_API_KEY=... PYTHONPATH=. python3 overnight/evaluate.py dev
      (add --limit N while iterating; the held-out set is scored ONCE)
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain import pb  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
JOBS: list[dict] = []


class _R:
    def __init__(self, payload, ok=True):
        self._p, self.ok = payload, ok

    def json(self):
        return self._p

    def raise_for_status(self):
        if not self.ok:
            raise RuntimeError("http")


def _get(url, params=None, timeout=None, **kw):
    if "/jobs/" not in url:
        return _R({"items": []})
    filt = (params or {}).get("filter", "")
    want = [s for s in ("awaiting_confirm", "queued") if s in filt]
    return _R({"items": list(reversed([j for j in JOBS if j["status"] in want]))})


def _post(url, json=None, timeout=None, **kw):
    if "/jobs/" not in url:
        return _R({"id": "x"})
    rec = dict(json or {})
    rec["id"] = f"job{len(JOBS)+1}"
    JOBS.append(rec)
    return _R(rec)


def _patch(url, json=None, timeout=None, **kw):
    jid = url.rstrip("/").rsplit("/", 1)[-1]
    for j in JOBS:
        if j["id"] == jid:
            j.update(json or {})
            return _R(j)
    return _R({}, ok=False)


pb.get, pb.post, pb.patch = _get, _post, _patch

from brain.anticipy_core import Anticipy  # noqa: E402
from brain.llm import LLM  # noqa: E402
from brain.memory import Memory  # noqa: E402

LOUDNESS = {"silent": 0, "quiet": 1, "desk": 2, "text": 3}


def run_line(a: Anticipy, text: str, texts: list) -> str:
    """One line through the real brain; return the loudest thing she did."""
    before_jobs, before_texts = len(JOBS), len(texts)
    out = a.hear(text)
    lane = "silent"
    for j in JOBS[before_jobs:]:
        lane = max(lane, "desk" if j.get("status") == "awaiting_confirm"
                   else "quiet", key=LOUDNESS.get)
    if len(texts) > before_texts or out.get("anticipy_says"):
        lane = max(lane, "text", key=LOUDNESS.get)
    return lane


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("which", nargs="?", default="dev")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    gold = json.load(open(os.path.join(HERE, f"gold_{args.which}.json")))
    gold = [g for g in gold if g.get("gold")]
    if args.limit:
        gold = gold[:args.limit]

    llm = LLM()
    if not llm.live:
        print("need OPENROUTER_API_KEY")
        return 1

    # Replay CONVERSATIONALLY, the way the worker actually runs: lines in the
    # order he said them, sharing one mind and a rolling context within a
    # conversation, with a fresh mind when the day moves on. Scoring each
    # line in isolation was unfair in both directions — it hid the open-plan
    # merge (so early turns each looked like a separate text) and it stripped
    # the context that makes "tomorrow 7 PM" part of a dinner rather than
    # three meaningless words.
    gold.sort(key=lambda g: g.get("created") or "")

    def gap_minutes(a_, b_):
        from datetime import datetime
        try:
            fmt = "%Y-%m-%d %H:%M:%S"
            ta = datetime.strptime((a_ or "")[:19], fmt)
            tb = datetime.strptime((b_ or "")[:19], fmt)
            return abs((tb - ta).total_seconds()) / 60
        except Exception:
            return 999

    false_fires, misses, errors, right = [], [], [], 0
    a = None
    convo: list = []
    texts: list = []
    prev_created = None
    # Conversation-level truth. A dinner agreed over six turns needs ONE
    # card, not six — so counting a "miss" on every turn that stayed quiet
    # punishes exactly the behaviour we want. What matters is whether the
    # plan was caught AT ALL before the conversation ended.
    sessions: list = []
    cur: dict = {}
    for i, g in enumerate(gold):
        JOBS.clear()
        if a is None or gap_minutes(prev_created, g.get("created")) > 10:
            a = Anticipy(memory=Memory(llm=llm), llm=llm, owner_id="eval")
            a.notify_owner = lambda m, channel="sms": texts.append(m) or {"ok": True}
            convo = []
            cur = {"wanted_work": False, "did_work": False, "lines": 0}
            sessions.append(cur)
        cur["lines"] += 1
        if g["gold"] in ("quiet", "desk", "text"):
            cur["wanted_work"] = True
        prev_created = g.get("created")
        before_texts = len(texts)
        try:
            before_jobs = len(JOBS)
            out = a.hear(g["text"], context=list(convo[-8:]))
            got = "silent"
            for j in JOBS[before_jobs:]:
                got = max(got, "desk" if j.get("status") == "awaiting_confirm"
                          else "quiet", key=LOUDNESS.get)
            if len(texts) > before_texts or out.get("anticipy_says"):
                got = max(got, "text", key=LOUDNESS.get)
            convo.append(g["text"])
        except Exception as e:
            got = f"error:{e}"
        # An LLM error is NOT a false fire. Counting it as one turned API
        # rate-limiting into a fake 57-false-fire result and nearly sent me
        # chasing a regression that did not exist. Errors get their own bin.
        if got.startswith("error"):
            errors.append({"text": g["text"], "err": got[:120]})
            continue
        if got != "silent":
            cur["did_work"] = True
        want = g["gold"]
        if want == "silent" and got != "silent":
            false_fires.append({"text": g["text"], "did": got, "why": g.get("why")})
        elif want != "silent" and got == "silent":
            misses.append({"text": g["text"], "wanted": want, "why": g.get("why")})
        else:
            right += 1
        if (i + 1) % 25 == 0:
            print(f"  scored {i+1}/{len(gold)}  "
                  f"(false fires {len(false_fires)}, misses {len(misses)})")

    n = len(gold)
    need = [s for s in sessions if s["wanted_work"]]
    dropped = [s for s in need if not s["did_work"]]
    report = {
        "set": args.which, "lines": n,
        "false_fires": len(false_fires),
        "misses": len(misses),
        "agreed": right,
        "errors": len(errors),
        "conversations_needing_work": len(need),
        "conversations_dropped": len(dropped),
        "false_fire_rate": round(100 * len(false_fires) / max(1, n), 1),
        "miss_rate": round(100 * len(misses) / max(1, n), 1),
        "false_fire_examples": false_fires[:12],
        "miss_examples": misses[:12],
    }
    print(f"\n=== {args.which.upper()} — {n} of Omar's real lines ===")
    print(f"  FALSE FIRES : {len(false_fires):3}  ({report['false_fire_rate']}%)"
          f"   <- acted when she should have stayed quiet")
    print(f"  MISSES      : {len(misses):3}  ({report['miss_rate']}%)"
          f"   <- stayed quiet when she should have acted")
    print(f"  agreed      : {right:3}")
    if errors:
        print(f"  errors      : {len(errors):3}  (model/API failures — NOT counted "
              f"as either; rerun if this is more than a couple)")
    print(f"  DROPPED CONVERSATIONS: {len(dropped)} of {len(need)} that needed "
          f"work got none at all  <- the one that actually matters")
    if false_fires:
        print("\n  worst false fires:")
        for f in false_fires[:6]:
            print(f"    [{f['did']:5}] {f['text'][:70]}")
    if misses:
        print("\n  worst misses:")
        for m in misses[:6]:
            print(f"    [want {m['wanted']:5}] {m['text'][:66]}")
    if args.out:
        json.dump(report, open(args.out, "w"), indent=1)
        print(f"\nwritten to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
