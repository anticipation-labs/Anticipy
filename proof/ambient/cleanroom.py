"""The same corpus, one FRESH BRAIN PER LINE, no rig, no accumulated state.

    ~/.anticipy-rig/venv/bin/python proof/ambient/cleanroom.py --work 80
    ~/.anticipy-rig/venv/bin/python proof/ambient/cleanroom.py --ids amb-0002,amb-0140
    ~/.anticipy-rig/venv/bin/python proof/ambient/cleanroom.py --compare

WHY THIS EXISTS. The live rig run has ONE worker holding ONE long-lived
Anticipy instance for ONE owner (brain/worker.py:2499 scopes every poll to
`anticipy.owner_ref`, and the instance is built once, outside the loop). So
across 320 utterances the brain accumulates memory, loops and a job queue, and
three real mechanisms can turn a correct catch into something that LOOKS like
a miss:

  * dedupe — `_same_pending` / `_refines_pending` correctly decline to queue an
    errand already on the desk (anticipy_core.py:1718-1734);
  * `_told_him_before` — she does not raise a card she has already raised;
  * memory injection — related recalled lines change what triage is shown.

All three are correct behaviour, and all three are indistinguishable from
outside from "she stopped noticing". The only way to separate them from a
genuine property of the words is to run the words with none of that state.

So: a new Memory on a private in-process database and a new Anticipy for every
single line, with PocketBase stubbed the way overnight/evaluate.py:31-69 stubs
it, so the jobs she queues are captured in-process instead of reaching the rig.
Nothing is written to the rig. Nothing under brain/ is touched.

WHAT IT ANSWERS. The live run's miss rate rose with corpus position. Either the
later block is harder, or she degrades as state piles up. Replay an early
sample and a late sample here: if the gap survives with no state at all, the
corpus explains it; if the gap disappears, accumulation does.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, REPO)

import score  # noqa: E402

JOBS: list[dict] = []


class _R:
    def __init__(self, payload, ok=True):
        self._p, self.ok = payload, ok

    def json(self):
        return self._p

    def raise_for_status(self):
        if not self.ok:
            raise RuntimeError("http")


def _install_pb_stub():
    """Capture jobs in memory. A live PocketBase here would pollute the rig's
    queue with replay rows AND let dedupe leak back in through the database —
    the exact state this file exists to exclude."""
    from brain import pb

    def _get(url, params=None, timeout=None, **kw):
        if "/jobs/" not in url:
            return _R({"items": []})
        want = ("queued", "awaiting_confirm", "running")
        return _R({"items": list(reversed([j for j in JOBS
                                           if j["status"] in want]))})

    def _post(url, json=None, timeout=None, **kw):
        if "/jobs/" not in url:
            return _R({})
        rec = dict(json or {})
        rec.setdefault("status", "queued")
        rec["id"] = f"cr{len(JOBS)}"
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


def rate(sample) -> str:
    n = sum(1 for r in sample if r.get("decision") in score.DECISIONS)
    m = sum(1 for r in sample if r.get("decision") in score.DECISIONS
            and score.lane_of(r) == "silent")
    return f"{score.pct(m, n):5}% ({m}/{n})"


def compare(results_path, cleanroom_path) -> int:
    """Live (one accumulating brain) versus clean room (a brain per line)."""
    if not os.path.exists(cleanroom_path):
        print("no cleanroom results yet")
        return 0
    live = {}
    if os.path.exists(results_path):
        with open(results_path) as fh:
            for line in fh:
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                if r.get("id"):
                    live[r["id"]] = r
    rows = []
    with open(cleanroom_path) as fh:
        for line in fh:
            try:
                rows.append(json.loads(line))
            except Exception:
                pass
    rows.sort(key=lambda r: r["id"])

    cut = len(rows) // 2
    early, late = rows[:cut], rows[cut:]
    live_rows = [live[r["id"]] for r in rows if r["id"] in live]
    live_early = [live[r["id"]] for r in early if r["id"] in live]
    live_late = [live[r["id"]] for r in late if r["id"] in live]

    print("\n" + "=" * 70)
    print("CLEAN ROOM vs LIVE RIG — same lines, same code, no shared state")
    print("=" * 70)
    print(f"  miss rate  clean room, all sampled : {rate(rows)}")
    print(f"  miss rate  live rig,   same lines  : {rate(live_rows)}")
    print("")
    print(f"  clean room  early half : {rate(early)}")
    print(f"  clean room  late  half : {rate(late)}")
    print(f"  live rig    early half : {rate(live_early)}")
    print(f"  live rig    late  half : {rate(live_late)}")
    print("\n  Read it this way: if the clean room shows the SAME early/late"
          "\n  gap as the rig, the later block is simply harder. If the clean"
          "\n  room is flat and only the rig widens, she degrades as state"
          "\n  piles up — and that is a product bug, not a corpus property.")

    flipped = [r for r in rows
               if r["id"] in live and r.get("decision") in score.DECISIONS
               and score.lane_of(live[r["id"]]) == "silent"
               and score.lane_of(r) != "silent"]
    if flipped:
        print(f"\n  {len(flipped)} lines the RIG missed that a FRESH brain "
              "caught — state, not words:")
        for r in flipped[:12]:
            print(f"    {r['id']} {r['text'][:56]!r}")
            print(f"        clean room: {score.lane_of(r)} / "
                  f"{(r.get('goal') or '')[:60]}")
            print(f"        reason    : {(r.get('reason') or '')[:80]}")
    stuck = [r for r in rows
             if r["id"] in live and r.get("decision") in score.DECISIONS
             and score.lane_of(r) == "silent"
             and score.lane_of(live[r["id"]]) == "silent"
             and r["gold"] != "ignore"]
    if stuck:
        print(f"\n  {len(stuck)} errands missed in BOTH — the words alone are "
              "not enough for her:")
        for r in stuck[:12]:
            print(f"    {r['id']} {r['text'][:56]!r}")
            print(f"        reason    : {(r.get('reason') or '')[:80]}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default=os.path.join(HERE, "corpus.json"))
    ap.add_argument("--results", default=os.path.join(HERE, "results.jsonl"))
    ap.add_argument("--out", default=os.path.join(HERE, "cleanroom.jsonl"))
    ap.add_argument("--ids", default="")
    ap.add_argument("--work", type=int, default=0,
                    help="sample N errand lines, half from the earliest block "
                         "and half from the latest, for the drift experiment")
    ap.add_argument("--compare", action="store_true",
                    help="only compare an existing cleanroom.jsonl with the "
                         "live results; runs no model calls")
    args = ap.parse_args()

    corpus = json.load(open(args.corpus))
    by_id = {c["id"]: c for c in corpus}

    if args.compare:
        return compare(args.results, args.out)

    if args.ids:
        wanted = [s.strip() for s in args.ids.split(",") if s.strip()]
        chosen = [by_id[i] for i in wanted if i in by_id]
    elif args.work:
        work = [c for c in corpus if c["gold"] in ("act", "ask")]
        half = max(1, args.work // 2)
        chosen = work[:half] + work[-half:]
    else:
        chosen = corpus

    done = set()
    if os.path.exists(args.out):
        with open(args.out) as fh:
            for line in fh:
                try:
                    done.add(json.loads(line)["id"])
                except Exception:
                    pass
    chosen = [c for c in chosen if c["id"] not in done]
    if not chosen:
        print("nothing to replay")
        return compare(args.results, args.out)

    _install_pb_stub()
    from brain.anticipy_core import Anticipy  # noqa: E402
    from brain.llm import LLM  # noqa: E402
    from brain.memory import Memory  # noqa: E402

    llm = LLM()
    if not llm.live:
        raise SystemExit("need OPENROUTER_API_KEY in the environment")

    print(f"replaying {len(chosen)} lines, one fresh brain each")
    t0 = time.time()
    for n, item in enumerate(chosen, 1):
        JOBS.clear()
        said: list[str] = []
        # Memory() defaults to ":memory:" (brain/memory.py:146), so each line
        # gets a private database that dies with the loop iteration. Nothing
        # carries over: not a fact, not a card, not a loop.
        a = Anticipy(memory=Memory(llm=llm), llm=llm, owner_id="cleanroom")
        a.notify_owner = lambda m, channel="sms": said.append(m) or {"ok": True}
        rec = {"id": item["id"], "text": item["text"], "gold": item["gold"]}
        try:
            out = a.hear(item["text"], context=[])
            d = out["decision"]
            spoke = list(said)
            if out.get("anticipy_says"):
                spoke.append(out["anticipy_says"])
            rec.update({
                "decision": d.decision, "goal": d.goal or "",
                "reason": getattr(d, "reason", "") or "",
                "addressee": getattr(d, "addressee", "") or "",
                "owes": getattr(d, "owes", "") or "",
                "missing": list(getattr(d, "missing", []) or []),
                # Same shape as run.py records, so score.own_said grades both
                # files by one rule. Here every message is hers by
                # construction — nothing else shares this process — but the
                # goal is carried anyway so the shapes cannot drift apart.
                "said": [{"text": s[:200], "goal": d.goal or "",
                          "decision": d.decision} for s in spoke],
                "jobs": [{"id": j["id"], "status": j.get("status"),
                          "lane": j.get("lane"), "goal": j.get("goal")}
                         for j in JOBS],
            })
        except Exception as e:
            rec.update({"decision": "error", "error": str(e)[:200]})
        with open(args.out, "a") as fh:
            fh.write(json.dumps(rec) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        lane = score.lane_of(rec)
        ok = "  " if lane in score.ACCEPTABLE[item["gold"]] else "!!"
        print(f"[{n}/{len(chosen)}] {ok} {item['id']} want={item['gold']:6} "
              f"lane={lane:6} {item['text'][:50]!r}")
    print(f"done in {(time.time() - t0) / 60:.1f} min")
    return compare(args.results, args.out)


if __name__ == "__main__":
    raise SystemExit(main())
