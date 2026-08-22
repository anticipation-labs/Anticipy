"""Score proof/ambient/results.jsonl against proof/ambient/corpus.json.

    ~/.anticipy-rig/venv/bin/python proof/ambient/score.py
    ~/.anticipy-rig/venv/bin/python proof/ambient/score.py --json proof/ambient/scorecard.json

GRADE ON BEHAVIOUR, NOT ON THE VERDICT. This is the single most important
thing in this file, and getting it wrong understated the brain by a factor of
four on the first pass.

`decision == "ignore"` does not mean she did nothing. It means she SAID
nothing. brain/anticipy_core.py:1358-1372: when a line yields a goal that is
not consequential, she queues the job UNHELD and then deliberately overwrites
the verdict with "ignore", reason "<addressee>-directed: quiet research, saying
nothing". worker.py:1971-1984 says the same thing from the other side. The goal
and the job both survive. So the discriminator is the goal and the job, and the
verdict is only the volume knob.

THE FOUR LANES, named for what the OWNER experiences, loudest last:

  silent  nothing. No goal, no job, no message. The only true miss.
  quiet   she is doing it and has not said so. A goal, usually a queued job.
  desk    a card he has to look at (decision="act").
  spoke   she interrupted him: an anticipy_says row, or decision="ask".

This is overnight/label_corpus.py:45-68's four-way vocabulary, re-derived from
what is observable on the wire rather than asserted by a label, so the two
corpora stay comparable.

THE TWO NUMBERS, and why they are not one number.

  FALSE PING RATE — a silent line that reached him: lane desk or spoke.
      Denominator: the ignore lines only. This is the wearability number. The
      MVP target is two or fewer false pings PER WEEK; a worn week is order a
      thousand overheard lines, so the budget is roughly 0.2%. 147 ignores
      cannot resolve 0.2% — what they can do is say whether the rate is in the
      right order of magnitude. One false ping here is already ~0.7%.

  MISS RATE — an errand that produced lane `silent`.
      Denominator: the act/ask lines only. This is the usefulness number.

  They are NOT symmetric, and averaging them into one accuracy figure hides the
  product. A false ping costs trust — he takes the pendant off, and there is no
  second chance. A miss costs one errand: annoying, invisible, recoverable, and
  he can always say it again. So the report weights a false ping as five misses
  (FALSE_PING_WEIGHT). That is a judgement, not a measurement, which is why it
  is a named constant instead of being buried in a formula.

BOTH CONFUSION MATRICES ARE PRINTED. The decision-level one because that is
what the database says and what any future run will diff against; the
behaviour-level one because that is what is true.
"""
from __future__ import annotations

import argparse
import json
import os
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))

# A false ping costs trust; a miss costs one errand. Five is a judgement.
FALSE_PING_WEIGHT = 5
DECISIONS = ("ignore", "ask", "act")
LANES = ("silent", "quiet", "desk", "spoke")
# What the gold label demands, expressed in lanes.
ACCEPTABLE = {
    "ignore": {"silent", "quiet"},   # quiet costs money, never trust
    "act": {"quiet", "desk", "spoke"},
    "ask": {"spoke"},                # the whole point of `ask` is that he hears
}


def pct(a: int, b: int) -> float:
    return round(100.0 * a / b, 1) if b else 0.0


def own_said(r) -> list:
    """The messages THIS line caused, with another lane's output removed.

    The rig is shared. A browser job finishing for a different agent posts an
    `anticipy_says` row of its own, and crediting it to whichever utterance
    was in flight manufactured two false pings out of "The heading on
    example.com is Example Domain" — on lines stamped ignore with no goal,
    which per brain/worker.py:2607-2611 cannot produce speech at all.

    A message belongs to this utterance when the utterance itself produced
    words: worker.py only posts one when hear() returned anticipy_says, which
    is exactly the act/ask paths. Otherwise the goals have to match.
    """
    said = r.get("said") or []
    # Older result files stored bare strings; accept both shapes.
    said = [{"text": s} if isinstance(s, str) else s for s in said]
    if (r.get("decision") or "") in ("act", "ask"):
        return said
    goal = (r.get("goal") or "").strip().lower()
    if not goal:
        return []
    return [s for s in said if (s.get("goal") or "").strip().lower() == goal]


def lane_of(r) -> str:
    """What the owner would have experienced. See the module docstring."""
    decision = r.get("decision") or ""
    goal = (r.get("goal") or "").strip()
    jobs = r.get("jobs") or []
    if own_said(r) or decision == "ask":
        return "spoke"
    if decision == "act":
        return "desk"
    if goal or jobs:
        return "quiet"
    return "silent"


def load(corpus_path: str, results_path: str):
    corpus = {c["id"]: c for c in json.load(open(corpus_path))}
    rows = []
    if not os.path.exists(results_path):
        raise SystemExit(f"no results at {results_path} — run run.py first")
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
            # `goal` exists on BOTH sides and means opposite things: the
            # corpus's is what she SHOULD have gone after, the result's is
            # what she DID. Merging them blind would score her against her
            # own answer, so the expected one is renamed here.
            merged = {**c, **r}
            merged["expected_goal"] = c.get("goal", "")
            merged["goal"] = r.get("goal", "")
            merged["decision"] = (r.get("decision") or "").strip()
            merged["lane"] = lane_of(merged)
            rows.append(merged)
    return corpus, rows


def bucket(rows, key):
    """Correctness per value of `key`, ignoring rows that never got an answer."""
    out = {}
    groups = defaultdict(list)
    for r in rows:
        groups[r.get(key) or "(none)"].append(r)
    for name, rs in sorted(groups.items()):
        scored = [r for r in rs if r["decision"] in DECISIONS]
        right = sum(1 for r in scored if r["lane"] in ACCEPTABLE[r["gold"]])
        out[name] = {"n": len(rs), "scored": len(scored), "right": right,
                     "accuracy": pct(right, len(scored))}
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default=os.path.join(HERE, "corpus.json"))
    ap.add_argument("--results", default=os.path.join(HERE, "results.jsonl"))
    ap.add_argument("--json", default="")
    ap.add_argument("--examples", type=int, default=12)
    args = ap.parse_args()

    corpus, rows = load(args.corpus, args.results)

    # Anything the worker never answered is an ERROR, never a verdict.
    # overnight/evaluate.py:163-168 learned this the expensive way: counting
    # API failures as false fires invented a 57-false-fire regression that did
    # not exist. Unanswered rows get their own bin and are out of every rate.
    unanswered = [r for r in rows if r["decision"] not in DECISIONS]
    scored = [r for r in rows if r["decision"] in DECISIONS]

    right = [r for r in scored if r["lane"] in ACCEPTABLE[r["gold"]]]
    d_confusion = Counter((r["gold"], r["decision"]) for r in scored)
    l_confusion = Counter((r["gold"], r["lane"]) for r in scored)

    gold_ignore = [r for r in scored if r["gold"] == "ignore"]
    gold_work = [r for r in scored if r["gold"] in ("act", "ask")]

    false_pings = [r for r in gold_ignore if r["lane"] in ("desk", "spoke")]
    quiet_drift = [r for r in gold_ignore if r["lane"] == "quiet"]
    misses = [r for r in gold_work if r["lane"] == "silent"]
    caught_quietly = [r for r in gold_work if r["lane"] == "quiet"]
    caught_loudly = [r for r in gold_work if r["lane"] in ("desk", "spoke")]
    # Gold `ask` means she was supposed to come back with a question because
    # something she needed was missing. Going ahead anyway is not a miss and
    # not a false ping; it is an assumption she was not entitled to make.
    assumed = [r for r in scored if r["gold"] == "ask"
               and r["lane"] in ("quiet", "desk")]

    hard = [r for r in scored if r.get("hard")]
    easy = [r for r in scored if not r.get("hard")]

    # Conversation-level truth, the same idea as overnight/evaluate.py:132-136:
    # a plan that only exists across three turns needs catching ONCE. Counting
    # a miss on every turn that stayed quiet would punish exactly the restraint
    # the product wants.
    convos = defaultdict(list)
    for r in scored:
        if r.get("convo"):
            convos[r["convo"]].append(r)
    need_work, dropped = [], []
    for cid, rs in convos.items():
        if any(x["gold"] in ("act", "ask") for x in rs):
            need_work.append(cid)
            if all(x["lane"] == "silent" for x in rs):
                dropped.append(cid)

    weighted_cost = FALSE_PING_WEIGHT * len(false_pings) + len(misses)

    report = {
        "utterances_in_corpus": len(corpus),
        "answered": len(scored),
        "unanswered": len(unanswered),
        "behaviour_accuracy": pct(len(right), len(scored)),
        "decision_accuracy": pct(
            sum(1 for r in scored if r["decision"] == r["gold"]), len(scored)),
        "false_pings": len(false_pings),
        "false_ping_rate_of_ignores": pct(len(false_pings), len(gold_ignore)),
        "misses": len(misses),
        "miss_rate_of_work": pct(len(misses), len(gold_work)),
        "caught_quietly": len(caught_quietly),
        "caught_loudly": len(caught_loudly),
        "quiet_drift": len(quiet_drift),
        "asked_when_told_to_ask": len(gold_work and
                                      [r for r in scored if r["gold"] == "ask"
                                       and r["lane"] == "spoke"]),
        "assumed_instead_of_asking": len(assumed),
        "weighted_cost": weighted_cost,
        "weighted_cost_note": f"one false ping counted as {FALSE_PING_WEIGHT} misses",
        "hard_accuracy": pct(sum(1 for r in hard
                                 if r["lane"] in ACCEPTABLE[r["gold"]]), len(hard)),
        "easy_accuracy": pct(sum(1 for r in easy
                                 if r["lane"] in ACCEPTABLE[r["gold"]]), len(easy)),
        "conversations_needing_work": len(need_work),
        "conversations_dropped": len(dropped),
        "dropped_conversation_ids": sorted(dropped),
        "by_field": bucket(scored, "field"),
        "by_family": bucket([r for r in scored if r["gold"] != "ignore"], "family"),
        "by_hard_kind": bucket(hard, "hard_kind"),
        "by_register": bucket(scored, "register"),
        "decision_confusion": {f"{g}->{d}": v
                               for (g, d), v in sorted(d_confusion.items())},
        "lane_confusion": {f"{g}->{lane}": v
                           for (g, lane), v in sorted(l_confusion.items())},
        "false_ping_examples": [
            {"id": r["id"], "text": r["text"], "lane": r["lane"],
             "decision": r["decision"], "goal": r.get("goal", ""),
             "said": [s.get("text", "") for s in own_said(r)],
             "hard_kind": r.get("hard_kind", "")}
            for r in false_pings],
        "miss_examples": [
            {"id": r["id"], "text": r["text"], "wanted": r["gold"],
             "expected_goal": r.get("expected_goal", "")}
            for r in misses[:args.examples]],
        "unanswered_examples": [
            {"id": r["id"], "error": r.get("error", ""), "text": r["text"][:70]}
            for r in unanswered[:args.examples]],
    }

    w = print
    w("=" * 74)
    w(f"AMBIENT SCORECARD — {len(scored)} answered of {len(corpus)} written"
      f"   ({len(unanswered)} unanswered, excluded from every rate)")
    w("=" * 74)
    w("")
    w("  THE TWO THAT MATTER")
    w(f"    FALSE PINGS : {len(false_pings):3} of {len(gold_ignore):3} silent lines"
      f"   = {report['false_ping_rate_of_ignores']:5}%"
      "   <- reached him over nothing")
    w(f"    MISSES      : {len(misses):3} of {len(gold_work):3} errands "
      f"      = {report['miss_rate_of_work']:5}%"
      "   <- real need, nothing happened")
    w(f"    weighted cost {weighted_cost}   (a false ping counted as "
      f"{FALSE_PING_WEIGHT} misses: trust does not come back, an errand does)")
    w("")
    w("  WHAT SHE DID WITH THE ERRANDS SHE CAUGHT")
    w(f"    quietly, saying nothing : {len(caught_quietly):3}"
      "   <- the product's whole personality")
    w(f"    put a card on his desk  : {len(caught_loudly):3}")
    w(f"    asked when told to ask  : {report['asked_when_told_to_ask']:3}"
      f" of {sum(1 for r in scored if r['gold'] == 'ask')} `ask` lines")
    w(f"    assumed instead of ask  : {len(assumed):3}"
      "   <- went ahead on facts she did not have")
    w("")
    w(f"  behaviour accuracy : {report['behaviour_accuracy']}%"
      f"  ({len(right)}/{len(scored)})   <- what actually happened")
    w(f"  decision accuracy  : {report['decision_accuracy']}%"
      "   <- the raw stamp; understates her, kept for diffing runs")
    w(f"  hard cases         : {report['hard_accuracy']}%"
      f"  ({len(hard)} lines)  vs {report['easy_accuracy']}% on the rest")
    w(f"  quiet drift        : {len(quiet_drift)}"
      "   <- research on noise; costs money, not trust")
    w(f"  conversations dropped : {len(dropped)} of {len(need_work)}"
      f"  {sorted(dropped) if dropped else ''}")
    w("")

    def matrix(title, conf, cols):
        w(f"  {title}   (rows = gold)")
        w("               " + "".join(f"{c:>9}" for c in cols))
        for g in DECISIONS:
            body = "".join(f"{conf.get((g, c), 0):>9}" for c in cols)
            w(f"    {g:<9}" + body)
        w("")

    matrix("BEHAVIOUR MATRIX — what he would have experienced", l_confusion, LANES)
    matrix("DECISION MATRIX — the raw stamp on the event row", d_confusion,
           DECISIONS)

    def table(title, data, note=""):
        w(f"  {title}{note}")
        for name, s in sorted(data.items(), key=lambda kv: kv[1]["accuracy"]):
            if not s["scored"]:
                continue
            bar = "#" * int(s["accuracy"] / 5)
            w(f"    {name:<24} {s['accuracy']:5.1f}%  "
              f"{s['right']:>3}/{s['scored']:<3} {bar}")
        w("")

    # DRIFT OR COMPOSITION? The miss rate rose from 42% at 100 answered to
    # 52% at 214, and there are only two explanations: the brain got worse as
    # the run went on (accumulated memory, dedupe, a leaking instance), or the
    # later part of the corpus is simply harder. This corpus is written in
    # blocks, not interleaved, so the second is the prior — but a prior is not
    # a measurement. The decisive test is WITHIN FIELD: the same walk of life
    # appears in both the early block and the late one, so if position were
    # the cause, a field's late lines would miss more than its own early ones.
    work = [r for r in scored if r["gold"] in ("act", "ask")]
    work.sort(key=lambda r: r["id"])
    w("  DRIFT CHECK — did she get worse, or did the corpus?")
    if len(work) >= 8:
        quarter = max(1, len(work) // 4)
        for q in range(4):
            chunk = work[q * quarter:(q + 1) * quarter] if q < 3 \
                else work[3 * quarter:]
            if not chunk:
                continue
            m = sum(1 for r in chunk if r["lane"] == "silent")
            fams = Counter(r["family"] for r in chunk).most_common(3)
            w(f"    errands {q * quarter + 1:>3}-{q * quarter + len(chunk):<3} "
              f"miss {pct(m, len(chunk)):5}%   top families: "
              + ", ".join(f"{k}x{v}" for k, v in fams))
        halves = defaultdict(lambda: [[0, 0], [0, 0]])   # field -> [[m,n],[m,n]]
        midpoint = len(work) // 2
        for i, r in enumerate(work):
            half = 0 if i < midpoint else 1
            halves[r["field"]][half][1] += 1
            if r["lane"] == "silent":
                halves[r["field"]][half][0] += 1
        both = {f: v for f, v in halves.items() if v[0][1] and v[1][1]}
        early_m = sum(v[0][0] for v in both.values())
        early_n = sum(v[0][1] for v in both.values())
        late_m = sum(v[1][0] for v in both.values())
        late_n = sum(v[1][1] for v in both.values())
        w(f"    within the {len(both)} walks of life present in BOTH halves: "
          f"early miss {pct(early_m, early_n)}% ({early_m}/{early_n})"
          f"   late miss {pct(late_m, late_n)}% ({late_m}/{late_n})")
        w("    a gap here is degradation with position; no gap means the "
          "later block is simply harder.")
    w("")

    # IS THE `ask` LANE ALIVE AT ALL? `ask` is the only outcome that asks him
    # a question before doing something on a fact she does not have, and it
    # has two gates in series: anticipy_core.py:1679-1684 only produces it
    # when decision.missing is non-empty, and worker.py:1981-1984 then demotes
    # it back to "ignore" unless she actually generated words to say. Either
    # gate closing makes the lane invisible, and the two failures are not the
    # same bug.
    ask_stamps = [r for r in scored if r["decision"] == "ask"]
    gold_ask = [r for r in scored if r["gold"] == "ask"]
    w("  THE ASK LANE")
    w(f"    times she stamped `ask` on ANY line : {len(ask_stamps)}"
      f" of {len(scored)}")
    w(f"    of the {len(gold_ask)} lines that needed a question, she asked "
      f"{sum(1 for r in gold_ask if r['lane'] == 'spoke')}")
    if gold_ask:
        spread = Counter(r["lane"] for r in gold_ask)
        w("    what she did instead: "
          + ", ".join(f"{k} x{v}" for k, v in spread.most_common()))
    w("")

    table("BY HARD KIND", report["by_hard_kind"],
          "   (worst first — 'hard' averages nine unrelated failure modes)")
    table("BY REGISTER", report["by_register"],
          "   (the product claim: no imperative needed)")
    table("BY TASK FAMILY (act/ask only)", report["by_family"])
    table("BY WALK OF LIFE", report["by_field"])

    if false_pings:
        w("  EVERY FALSE PING — the number the MVP is judged on")
        for r in false_pings:
            w(f"    [{r['lane']}] {r['id']} {r['text'][:62]!r}")
            w(f"        goal she invented : {r.get('goal') or '(none)'}")
            mine = own_said(r)
            if mine:
                w(f"        SAID TO HIM       : {mine[0].get('text', '')[:120]}")
        w("")
    if misses:
        w(f"  MISSES — nothing happened at all (first {args.examples})")
        for r in misses[:args.examples]:
            w(f"    [want {r['gold']}] {r['id']} {r['text'][:60]!r}")
            w(f"        should have been: {r.get('expected_goal', '')}")
        w("")
    if unanswered:
        w(f"  UNANSWERED ({len(unanswered)}) — not scored either way")
        for r in unanswered[:args.examples]:
            w(f"    {r['id']} {r.get('error', '?')}  {r['text'][:50]!r}")
        w("")

    if args.json:
        with open(args.json, "w") as fh:
            json.dump(report, fh, indent=1)
        w(f"written to {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
