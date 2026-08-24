"""Score the REAL Brain.triage against the Tejas-call labeled regression set.

  Set:    research/evals/call-2026-08-23-tejas/labeled_set.json
          25 rows — real lines from the 2026-08-23 call with CORRECTED labels
          (the live system got 5 of its 6 acts wrong), plus held-out entries
          from brain/EXEMPLARS.md that must never appear in a teaching prompt.

  Run:    python3 overnight/triage_eval.py            # offline heuristic
          python3 overnight/triage_eval.py --live     # real model via env keys

This is a MEASURING STICK, not a gate: offline mode always exits 0. The
offline heuristic (brain/llm.py _heuristic — what LLM() becomes with no key)
is a keyword engine, so its score here is expected to be bad; what matters is
that the number exists, is deterministic, and moves when the brain moves.

WHAT IS BEING CALLED — and what is deliberately NOT reimplemented:
  Brain.triage(transcript_line, candidates=0, explicit=False) -> Decision,
  the genuine article from brain/orchestrator.py, second look, inherited-
  errand guard and all. Every row's `text` goes in as the line; `around`
  rides along the way the production caller (Anticipy._decide) would send
  it: appended as "(Earlier in this conversation: a | b)". Reimplementing
  triage here would score a copy that drifts; the whole point is to score
  the thing that ships.

POSTURE (in_two_way_call): Brain.triage takes NO mid_conversation kwarg.
  That decoration lives one layer up, in Anticipy._decide's "(Pre-check:
  he is mid-conversation ...)" block — and that block asserts the other
  side is INAUDIBLE, which is false for the Tejas call (both sides are in
  the transcript). Faking it would test a sentence production never sends
  for this posture, so the 15 in_two_way_call rows are triaged WITHOUT
  posture context, and the report header says so. Same for the one row
  with timing="after_call_digest": triage decides WHAT, the digest lane
  decides WHEN, so timing and digest_worthy are out of scope here.

MEMORY: rows carry a plain `memory` list (mostly empty; one row real).
  There IS a clean bare-triage injection route — the "(Related memory:
  ...)" suffix that TRIAGE_SYSTEM itself documents as context, exactly
  how anticipy_core.memory_notes delivers recalled facts ("; "-joined).
  Non-empty memory rows get that suffix; the Memory class is untouched.

THE 'answer' MAPPING (the set has a label triage does not):
  Decision.decision is only ignore|ask|act. TRIAGE_SYSTEM folds a spoken
  factual question into "act" with a research goal ("a factual question
  the owner says out loud that you could answer by looking it up ...
  Make the goal a research goal"). So the fair mapping is:
    label 'answer' PASSES when the prediction is "act" WITH a non-null
    goal (the brain's answering shape), or when the prediction is in the
    row's also_ok. An "ignore" or a goalless verdict FAILS the row.
  answer_must_contain is the CONTENT of the answer ("3", "Central"),
  and a triage Decision contains no answer text to check it against —
  the number 3 lives in the downstream compute/say step, not in a goal
  like "convert 5 PM CST to PST". It is therefore checked against the
  goal INFORMATIONALLY only (reported per row, never a pass/fail input),
  and the report says out loud that content was not verified. Nothing is
  silently marked passed: the decision-shape check is real and failable.

SCORING (per the set's _readme, which is law here):
  a row passes when the predicted decision equals `label` or is in
  `also_ok` — AND, for label=act rows predicted "act", the emitted goal
  contains EVERY goal_must_contain substring case-insensitively and NONE
  of goal_must_not_contain (a null goal fails any must-contain).
  Per-label accuracy is mandatory and the mean is never reported alone:
  the set is balanced so that a brain that answers "ignore" to everything
  maxes ignore and zeroes the other three — silence cannot max the score.

DETERMINISM: rows are sorted by id; offline mode strips the API keys from
  this process's environment before LLM() is built, so `python3
  overnight/triage_eval.py` is offline even on a machine with keys
  exported, touches no network, and gives the same answer every run
  (the heuristic is pure regex and triage pins temperature 0).
"""
from __future__ import annotations

import argparse
import json
import os
import sys

# Run from anywhere: the repo root is one level up from this file, and the
# brain package is imported from it, never from an installed copy.
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

LABELED_SET = os.path.join(
    ROOT, "research", "evals", "call-2026-08-23-tejas", "labeled_set.json")

# The keys llm.py looks for. Popped (process-locally) in offline mode so the
# default invocation cannot silently become a live — and billable — run.
_KEY_VARS = ("GEMINI_API_KEY", "OPENROUTER_API_KEY")

# Every label the set may use. 'answer' is the one triage cannot emit; its
# mapping is defined in decision_matches() below and documented above.
LABELS = ("ignore", "ask", "act", "answer")


def decorate(row: dict) -> str:
    """Build the prompt the way Anticipy._decide would for a bare line.

    Two suffixes only, in the order production appends them:
      1. `around` -> "(Earlier in this conversation: a | b)" — the exact
         " | " join anticipy_core uses for convo context;
      2. `memory` -> "(Related memory: f1; f2)" — the "; " join
         memory_notes produces for trusted facts.
    Nothing else is fabricated: no voice check, no pre-check, no numbered
    link candidates, because the set supplies no evidence for any of them.
    """
    prompt = row["text"]
    around = [a for a in (row.get("around") or []) if a and a.strip()]
    if around:
        prompt = f"{prompt}\n(Earlier in this conversation: {' | '.join(around)})"
    memory = [m for m in (row.get("memory") or []) if m and m.strip()]
    if memory:
        prompt = f"{prompt}\n(Related memory: {'; '.join(memory)})"
    return prompt


def decision_matches(row: dict, predicted: str, goal) -> bool:
    """Did the predicted DECISION satisfy the row's label (or also_ok)?

    Goal-content constraints are checked separately in score_row — this
    answers only the label question, including the 'answer' mapping.
    """
    acceptable = [row["label"]] + list(row.get("also_ok") or [])
    for want in acceptable:
        if want == "answer":
            # The brain's answering shape: act, with a real research goal.
            # A bare "act" with no goal is a contradiction, not an answer.
            if predicted == "act" and goal:
                return True
        elif predicted == want:
            return True
    return False


def goal_ok(row: dict, goal) -> tuple[bool, list[str]]:
    """The act-goal contract: every must-contain present, no invention.

    Case-insensitive substring checks per the _readme. A null goal fails
    every must-contain (a detail that never made it into a goal is a
    detail lost — orchestrator's own words) and trivially passes
    must-not-contain (nothing invented in nothing).
    """
    problems: list[str] = []
    hay = (goal or "").lower()
    for need in row.get("goal_must_contain") or []:
        if need.lower() not in hay:
            problems.append(f"goal missing {need!r}")
    for banned in row.get("goal_must_not_contain") or []:
        if banned.lower() in hay:
            problems.append(f"goal contains forbidden {banned!r}")
    return (not problems, problems)


def score_row(row: dict, predicted: str, goal) -> tuple[bool, list[str]]:
    """One verdict per row: pass/fail plus the reasons a human can read."""
    problems: list[str] = []
    if not decision_matches(row, predicted, goal):
        also = row.get("also_ok") or []
        want = row["label"] + (f" (also_ok: {', '.join(also)})" if also else "")
        problems.append(f"decision: wanted {want}, got {predicted}")
    # Goal content is enforced only where the set defines it: label=act rows,
    # and only when the brain actually answered "act" — a wrong decision is
    # already a failure and double-charging it as a goal failure too would
    # make the table read worse than the behaviour is.
    if row["label"] == "act" and predicted == "act":
        ok, goal_problems = goal_ok(row, goal)
        if not ok:
            problems.extend(goal_problems)
    return (not problems, problems)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Score Brain.triage against the Tejas labeled set.")
    ap.add_argument("--live", action="store_true",
                    help="use GEMINI_API_KEY/OPENROUTER_API_KEY from the "
                         "environment instead of the offline heuristic")
    args = ap.parse_args()

    if not args.live:
        # OFFLINE MEANS OFFLINE. Keys exported in the shell must not turn
        # the deterministic mode into a network run behind the operator's
        # back — the default invocation is the one CI and tired humans use.
        for var in _KEY_VARS:
            os.environ.pop(var, None)

    # Imported AFTER the key scrub so LLM() is constructed in the intended
    # mode (llm.py reads the environment at __init__ time).
    from brain.llm import LLM            # noqa: E402
    from brain.orchestrator import Brain  # noqa: E402

    llm = LLM()
    if args.live and not llm.live:
        # Asked for live, no credentials. Not an error — say how, then run
        # the offline stick anyway so the invocation still produces a number.
        print("--live requested but no API key found in the environment.")
        print("To run live:  OPENROUTER_API_KEY=... python3 "
              "overnight/triage_eval.py --live")
        print("        (or:  GEMINI_API_KEY=... — Gemini wins when both set)")
        print("Falling back to the offline heuristic for this run.\n")
    mode = "live" if llm.live else "heuristic"
    brain = Brain(llm=llm)

    data = json.load(open(LABELED_SET))
    # Sorted by id: the file's order is editorial, the report's order is a
    # contract — the same set must produce the same lines in the same place.
    rows = sorted(data["rows"], key=lambda r: r["id"])

    # ---------------------------------------------------------------- header
    # The caveats a reader needs BEFORE the numbers, per the _readme's own
    # rule that reporting shape must not be able to hide behaviour.
    print(f"=== triage_eval — {len(rows)} labeled rows, mode: {mode} ===")
    print("NOTE  Brain.triage has NO mid_conversation/in-conversation kwarg")
    print("      (signature: triage(transcript_line, candidates=0, "
          "explicit=False));")
    n_call = sum(1 for r in rows if r.get("in_two_way_call"))
    print(f"      the {n_call} in_two_way_call rows were triaged WITHOUT "
          "posture context —")
    print("      that decoration lives in Anticipy._decide, above this seam.")
    print("NOTE  'answer' mapping: Decision has no 'answer' value; per "
          "TRIAGE_SYSTEM a")
    print("      spoken factual question is 'act' with a research goal, so "
          "answer rows")
    print("      pass on decision=='act' with a non-null goal (or also_ok). ")
    print("      answer_must_contain is CONTENT the downstream answer step "
          "produces,")
    print("      not the goal — reported per row below, never pass/fail "
          "here.")
    print("NOTE  non-empty `memory` rows were injected via the documented "
          "'(Related")
    print("      memory: ...)' suffix — none scored memory-blind. "
          "digest_worthy and")
    print("      timing are digest-lane concerns, out of triage's scope, "
          "unscored.")
    print()

    per_label = {lab: {"pass": 0, "total": 0} for lab in LABELS}
    failures: list[dict] = []
    answer_notes: list[str] = []
    for row in rows:
        decision = brain.triage(decorate(row))
        predicted, goal = decision.decision, decision.goal
        passed, problems = score_row(row, predicted, goal)
        bucket = per_label[row["label"]]
        bucket["total"] += 1
        if passed:
            bucket["pass"] += 1
        else:
            failures.append({
                "id": row["id"], "expected": row["label"],
                "also_ok": row.get("also_ok") or [],
                "got": predicted, "goal": goal, "problems": problems,
            })
        # The informational content check for answer rows — visible either
        # way, so a passing table cannot quietly imply content was verified.
        if row["label"] == "answer":
            hits = [s for s in (row.get("answer_must_contain") or [])
                    if s.lower() in (goal or "").lower()]
            answer_notes.append(
                f"{row['id']}: got {predicted}"
                + (f", goal={goal!r}" if goal else "")
                + f" — answer_must_contain {row.get('answer_must_contain')}"
                  f" (in goal, informational only: {hits or 'none'})")

    # ----------------------------------------------------------- the table
    # Per-label FIRST, total last — never a lone mean, so all-ignore cannot
    # read as 60%-and-fine. Labels print in the set's canonical order.
    print("per-label accuracy:")
    total_pass = total_n = 0
    for lab in LABELS:
        b = per_label[lab]
        total_pass += b["pass"]
        total_n += b["total"]
        pct = 100.0 * b["pass"] / b["total"] if b["total"] else 0.0
        print(f"  {lab:<7} {b['pass']:2}/{b['total']:<2}  ({pct:5.1f}%)")
    total_pct = 100.0 * total_pass / total_n if total_n else 0.0
    print(f"  {'TOTAL':<7} {total_pass:2}/{total_n:<2}  ({total_pct:5.1f}%)")

    print("\nanswer rows (mapped — see header):")
    for note in answer_notes:
        print(f"  {note}")

    if failures:
        print(f"\nfailing rows ({len(failures)}):")
        for f in failures:
            print(f"  {f['id']}: expected {f['expected']}, got {f['got']}, "
                  f"goal={f['goal']!r} — {'; '.join(f['problems'])}")
    else:
        print("\nno failing rows.")

    # ------------------------------------------------- machine-readable tail
    # ONE json line, last, so a gate or a grep can lift the numbers without
    # parsing prose. Everything above is for humans; this line is for code.
    print(json.dumps({
        "eval": "triage_eval", "mode": mode, "rows": total_n,
        "per_label": {lab: dict(per_label[lab]) for lab in LABELS},
        "total": {"pass": total_pass, "total": total_n,
                  "pct": round(total_pct, 1)},
        "failing_ids": [f["id"] for f in failures],
        "in_two_way_call_kwarg_missing": True,
        "answer_mapping": "act_with_goal",
    }))

    # A measuring stick, not a gate (yet): the exit code never fails the run.
    # When this becomes a gate leg, the threshold goes HERE and nowhere else.
    return 0


if __name__ == "__main__":
    sys.exit(main())
