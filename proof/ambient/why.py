"""For every wrong verdict, say WHY — with evidence from two sources.

    ~/.anticipy-rig/venv/bin/python proof/ambient/why.py
    ~/.anticipy-rig/venv/bin/python proof/ambient/why.py --replay   # slower, richer

SOURCE 1, always: the live rig's own log, ~/.anticipy-rig/brain.log. Every
heard line prints as

    heard: '<the words>' -> <decision> (<goal or "no goal">)

plus, since segments were switched on, the `segment:` line above it. That is
what ACTUALLY happened to that utterance, and it is quoted verbatim. What the
log does NOT carry is the brain's reason — worker.py:2612 prints the decision
and the goal and throws `decision.reason` away, which is the single cheapest
observability fix available and is written up in the report.

SOURCE 2, with --replay: the same line put back through the REAL brain
offline, with PocketBase stubbed exactly the way overnight/evaluate.py:31-69
stubs it, so `Decision.reason`, `.addressee` and `.owes` can be read directly.
This is a SECOND OBSERVATION, not the live verdict: it runs on a fresh mind
with no memory of the day and no conversation context, so it can disagree with
the rig. Where it disagrees, that disagreement is itself the finding — it means
the verdict depended on accumulated state rather than on the words.

Nothing here writes to the rig and nothing here touches brain/.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
RIG = os.environ.get("ANTICIPY_RIG_DIR", os.path.expanduser("~/.anticipy-rig"))

# ONE definition of a lane, imported rather than restated. Two copies of
# "what counts as wrong" is how a scorer and its diagnosis start disagreeing.
sys.path.insert(0, HERE)
import score  # noqa: E402

DECISIONS = ("ignore", "ask", "act")
_HEARD = re.compile(r"^heard: (?P<q>['\"])(?P<text>.*)(?P=q) -> (?P<decision>\S+)"
                    r"(?: \((?P<goal>.*)\))?$")


def log_index(path: str) -> dict:
    """text -> list of (decision, goal, preceding segment line).

    Keyed by the words because the log carries no event id. A line said twice
    gets both verdicts, in order, which is exactly what is wanted when the
    same utterance was pushed more than once.
    """
    out: dict[str, list] = defaultdict(list)
    if not os.path.exists(path):
        return out
    prev_segment = ""
    with open(path, errors="replace") as fh:
        for raw in fh:
            raw = raw.rstrip("\n")
            if raw.startswith("segment:"):
                prev_segment = raw
                continue
            m = _HEARD.match(raw)
            if not m:
                continue
            goal = m.group("goal") or ""
            out[m.group("text")].append({
                "decision": m.group("decision"),
                "goal": "" if goal == "no goal" else goal,
                "segment": prev_segment,
                "raw": raw,
            })
            prev_segment = ""
    return out


def _escape(text: str) -> str:
    """The log writes Python repr, so the corpus text must be repr'd to match."""
    return repr(text)[1:-1]


def load_wrong(corpus_path, results_path):
    corpus = {c["id"]: c for c in json.load(open(corpus_path))}
    wrong = []
    with open(results_path) as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            c = corpus.get(r.get("id"))
            if not c:
                continue
            got = (r.get("decision") or "").strip()
            if got not in DECISIONS:
                continue
            row = {**c, "expected_goal": c.get("goal", ""),
                   "decision": got, "goal": r.get("goal", ""),
                   "produced_goal": r.get("goal", ""),
                   "addressee": r.get("addressee", ""),
                   "segment": r.get("segment", ""),
                   "said": r.get("said", []), "jobs": r.get("jobs", [])}
            # WRONG IS DECIDED BY LANE, NOT BY VERDICT. decision="ignore"
            # carrying a goal is her working silently, which is a pass — see
            # score.py's module docstring. Diagnosing those as failures sent
            # the first analysis chasing twenty-five errands she had already
            # queued.
            row["lane"] = score.lane_of(row)
            if row["lane"] in score.ACCEPTABLE[c["gold"]]:
                continue
            wrong.append(row)
    return corpus, wrong


def kind_of(row) -> str:
    """The theme a wrong verdict belongs to. Deliberately decided by what the
    LABEL said the line was, not by guessing at the model's intent."""
    if row["gold"] == "ignore":
        return f"false ping / {row.get('hard_kind') or row.get('register')}"
    if row["lane"] == "silent":
        if row.get("convo"):
            return "miss / inside a conversation"
        return f"miss / {row.get('hard_kind') or row.get('register')}"
    return f"went ahead / wanted {row['gold']}, lane {row['lane']}"


def replay(rows):
    """Put each wrong line back through the real brain to read its reason."""
    sys.path.insert(0, REPO)
    from brain import pb  # noqa: E402

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
        want = ("queued", "awaiting_confirm", "running")
        return _R({"items": list(reversed([j for j in JOBS
                                           if j["status"] in want]))})

    def _post(url, json=None, timeout=None, **kw):
        if "/jobs/" not in url:
            return _R({})
        rec = dict(json or {})
        rec.setdefault("status", "queued")
        rec["id"] = f"replay{len(JOBS)}"
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

    llm = LLM()
    if not llm.live:
        print("  (replay skipped: no OPENROUTER_API_KEY in this shell)")
        return

    for row in rows:
        JOBS.clear()
        # A FRESH MIND PER LINE. The point of the replay is to read the reason
        # the words alone produce; carrying state between them would reproduce
        # the rig's confound instead of isolating it.
        a = Anticipy(memory=Memory(llm=llm), llm=llm, owner_id="why")
        a.notify_owner = lambda m, channel="sms": {"ok": True}
        try:
            out = a.hear(row["text"], context=[])
            d = out["decision"]
            row["replay"] = {
                "decision": d.decision, "goal": d.goal or "",
                "reason": getattr(d, "reason", ""),
                "addressee": getattr(d, "addressee", ""),
                "owes": getattr(d, "owes", ""),
                "missing": list(getattr(d, "missing", []) or []),
            }
        except Exception as e:
            row["replay"] = {"error": str(e)[:160]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default=os.path.join(HERE, "corpus.json"))
    ap.add_argument("--results", default=os.path.join(HERE, "results.jsonl"))
    ap.add_argument("--log", default=os.path.join(RIG, "brain.log"))
    ap.add_argument("--replay", action="store_true")
    ap.add_argument("--replay-limit", type=int, default=0,
                    help="replay only the first N wrong lines (each costs a "
                         "live model call)")
    ap.add_argument("--json", default="")
    args = ap.parse_args()

    _corpus, wrong = load_wrong(args.corpus, args.results)
    if not wrong:
        print("no wrong verdicts in the results file")
        return 0
    index = log_index(args.log)
    for row in wrong:
        hits = index.get(_escape(row["text"])) or index.get(row["text"]) or []
        row["log"] = hits[-1] if hits else None

    if args.replay:
        subset = wrong[:args.replay_limit] if args.replay_limit else wrong
        print(f"replaying {len(subset)} wrong lines through the real brain...")
        replay(subset)

    themes = defaultdict(list)
    for row in wrong:
        themes[kind_of(row)].append(row)

    print("=" * 72)
    print(f"WHY IT WENT WRONG — {len(wrong)} wrong verdicts, "
          f"{len(themes)} themes")
    print("=" * 72)
    for theme, rows in sorted(themes.items(), key=lambda kv: -len(kv[1])):
        print(f"\n### {theme}  ({len(rows)})")
        for row in rows:
            print(f"  {row['id']}  want={row['gold']} got={row['decision']}")
            print(f"    said : {row['text']}")
            if row["log"]:
                print(f"    log  : {row['log']['raw']}")
                if row["log"]["segment"]:
                    print(f"           {row['log']['segment']}")
            else:
                print("    log  : (not found in brain.log)")
            if row["gold"] != "ignore":
                print(f"    wanted goal   : {row['expected_goal']}")
            if row["produced_goal"]:
                print(f"    produced goal : {row['produced_goal']}")
            if row.get("addressee"):
                print(f"    addressee     : {row['addressee']}")
            if row.get("said"):
                print(f"    SAID TO HIM   : {row['said']}")
            rp = row.get("replay")
            if rp:
                if rp.get("error"):
                    print(f"    replay        : error {rp['error']}")
                else:
                    print(f"    replay        : {rp['decision']} "
                          f"addressee={rp['addressee']} owes={rp['owes']}")
                    print(f"    REASON        : {rp['reason']}")
                    if rp["missing"]:
                        print(f"    missing       : {rp['missing']}")

    print("\n" + "=" * 72)
    print("THEME COUNTS")
    for theme, rows in sorted(themes.items(), key=lambda kv: -len(kv[1])):
        print(f"  {len(rows):3}  {theme}")
    if any(r.get("replay") for r in wrong):
        agree = sum(1 for r in wrong
                    if (r.get("replay") or {}).get("decision") == r["decision"])
        print(f"\n  offline replay reproduced the rig's verdict on "
              f"{agree}/{len(wrong)} lines")
        print("  (a disagreement means the verdict depended on accumulated "
              "state, not on the words)")
        reasons = Counter((r.get("replay") or {}).get("reason", "")
                          for r in wrong)
        print("\n  REASONS THE BRAIN GAVE, most common first")
        for reason, count in reasons.most_common(15):
            if reason:
                print(f"    {count:3}  {reason[:96]}")

    if args.json:
        with open(args.json, "w") as fh:
            json.dump({"wrong": wrong,
                       "themes": {k: [r["id"] for r in v]
                                  for k, v in themes.items()}}, fh, indent=1)
        print(f"\nwritten to {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
