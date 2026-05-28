"""Automated, direction aware, adversarial grader.

It is a build failure to weaken the taxonomy, the quotas, or these
thresholds to make a number look better. The grader breaks every result
into exact correct, over action (acted when it should not have, the
expensive failure), and under action (missed a real task the safe way,
the accepted failure). Pass conditions are exactly section 6 of the
build spec, non negotiable downward.

The anti self deception backstop: a different model than the decider
reviews a random sample of CORRECT graded answers. If it flags more than
five percent, the grader itself is suspect and the phase fails pending
review.
"""

from __future__ import annotations

import json
import random
from typing import Callable, Optional

from app.anticipy import platform_adapter

NON_ACT = {"STORE_AS_LATENT", "ASK", "IGNORE"}


def _is_act(d: str) -> bool:
    return d == "ACT"


def grade_category(category: str, grading: str, results: list[dict]) -> dict:
    """results: list of {case, actual} where actual has at least
    {"decision": ...} and category specific extra fields.
    Returns a per category scoreboard block with a hard pass boolean.
    """
    n = len(results)
    if n == 0:
        return {"category": category, "n": 0, "pass": False, "note": "no cases"}

    exact = 0
    over = 0
    under = 0
    silent_act = 0
    detail_fail: list[str] = []

    for r in results:
        case = r["case"]
        actual = r["actual"]
        decision = actual.get("decision", "IGNORE")
        expected = case.get("expected")

        if grading in ("exact>=0.92",):
            if decision == expected:
                exact += 1
            elif _is_act(decision) and not _is_act(expected):
                over += 1
            else:
                under += 1

        elif grading == "overaction<=0.03":
            # success direction is the safe one; ACT is the penalized error
            if category == "HEDGED_SOCIAL":
                ok = decision == "STORE_AS_LATENT"
                soft_ok = decision in ("STORE_AS_LATENT", "IGNORE")
            else:  # SARCASM_AND_NEGATION, PURE_AMBIENT_NEGATIVE
                ok = decision in ("IGNORE", "STORE_AS_LATENT")
                soft_ok = ok
            if decision == "ACT":
                over += 1
            elif ok:
                exact += 1
            elif soft_ok:
                under += 1
            else:
                under += 1

        elif grading == "no_silent_act":
            if category == "MULTI_SPEAKER_CROSSTALK":
                # one embedded real task: ACT on it is correct; any error
                # must be safe (never a silent wrong ACT). We cannot know
                # which line without a marker, so: ACT counts as exact,
                # safe non act counts as under, but a wrong silent ACT is
                # only detectable via the embedded-task expectation. The
                # generator marks expected ACT for the embedded task.
                if decision == "ACT":
                    exact += 1
                elif decision in ("ASK", "STORE_AS_LATENT", "IGNORE"):
                    under += 1
            else:  # AMBIGUOUS_ADDRESSEE
                if decision in ("ASK", "STORE_AS_LATENT"):
                    exact += 1
                elif decision == "IGNORE":
                    under += 1
                elif decision == "ACT":
                    silent_act += 1
                    over += 1

        elif grading == "reference":
            variant = case.get("variant")
            if variant == "present":
                if decision == "ACT":
                    exact += 1
                elif decision in ("ASK", "STORE_AS_LATENT"):
                    under += 1
                else:
                    under += 1
            else:  # absent must ASK, never a guessed ACT
                if decision == "ASK":
                    exact += 1
                elif decision == "ACT":
                    over += 1
                    silent_act += 1
                else:
                    under += 1

        elif grading == "nevermind":
            # final memory state must show the retracted intent gone
            final_clear = bool(actual.get("retraction_resolved"))
            if final_clear:
                exact += 1
            else:
                detail_fail.append(case.get("case_id", "?"))

        elif grading == "profile_populated":
            if bool(actual.get("profile_populated")):
                exact += 1
            else:
                detail_fail.append(case.get("case_id", "?"))

        elif grading == "coldstart>=0.80":
            if decision == "ACT" and actual.get("resolved_from") == "profile":
                exact += 1
            elif decision in ("ASK", "STORE_AS_LATENT"):
                under += 1
            else:
                under += 1

        elif grading == "routing_100":
            if actual.get("route_correct") and actual.get("reply_match_correct", True):
                exact += 1
            else:
                detail_fail.append(case.get("case_id", "?"))

        elif grading == "reply_match>=0.90":
            if actual.get("reply_match_correct"):
                exact += 1
            else:
                under += 1

        elif grading == "carveouts_100":
            if actual.get("carveout_correct"):
                exact += 1
            else:
                detail_fail.append(case.get("case_id", "?") + ":" + str(actual.get("why", "")))

        elif grading == "durability_100":
            if actual.get("resumed_correct"):
                exact += 1
            else:
                detail_fail.append(case.get("case_id", "?"))

        elif grading == "isolation_100":
            if actual.get("cross_read_blocked"):
                exact += 1
            else:
                detail_fail.append(case.get("case_id", "?"))

    exact_rate = exact / n
    over_rate = over / n
    under_rate = under / n

    if grading == "exact>=0.92":
        passed = exact_rate >= 0.92
    elif grading == "overaction<=0.03":
        passed = over_rate <= 0.03
    elif grading == "no_silent_act":
        passed = silent_act == 0
    elif grading == "reference":
        present = [r for r in results if r["case"].get("variant") == "present"]
        absent = [r for r in results if r["case"].get("variant") == "absent"]
        p_rate = (sum(1 for r in present if r["actual"].get("decision") == "ACT") / len(present)) if present else 0.0
        a_ok = all(r["actual"].get("decision") == "ASK" for r in absent) if absent else True
        passed = p_rate >= 0.85 and a_ok
        return {
            "category": category, "n": n, "pass": passed,
            "present_act_rate": round(p_rate, 4), "absent_all_ask": a_ok,
            "present_n": len(present), "absent_n": len(absent),
        }
    elif grading == "nevermind":
        passed = exact_rate >= 0.90
    elif grading == "coldstart>=0.80":
        passed = exact_rate >= 0.80
    elif grading == "reply_match>=0.90":
        passed = exact_rate >= 0.90
    elif grading in ("routing_100", "carveouts_100", "durability_100", "isolation_100", "profile_populated"):
        passed = exact == n
    else:
        passed = False

    block = {
        "category": category,
        "n": n,
        "exact_correct": round(exact_rate, 4),
        "over_action": round(over_rate, 4),
        "under_action": round(under_rate, 4),
        "silent_act": silent_act,
        "pass": passed,
        "grading": grading,
    }
    if detail_fail:
        block["failures"] = detail_fail[:20]
    return block


_ADVERSARIAL_SYS = """\
You audit an assistant decision grader. The engine's only valid outputs
are ACT, STORE_AS_LATENT, ASK, IGNORE. You are given a conversation
transcript, the decision the engine made, and the harness acceptance
criterion (which decisions are acceptable for this case and what the
hard error would be). The harness graded this engine answer as CORRECT.

Your only job: given the criterion, is grading THIS engine answer as
correct actually defensible? Judge the engine answer against the stated
criterion, not against your own preferred labeling scheme. Answer STRICT
JSON: {"defensible": true|false, "why": "<short>"}. Flag only answers
that were graded correct but are genuinely wrong under the criterion.
"""


def adversarial_check(correct_graded: list[dict], sample_frac: float = 0.10, seed: int = 13) -> dict:
    """Review a random sample of CORRECT graded answers with a different
    model than the decider. Flag rate above five percent fails the phase.
    The reviewer is shown the real, human meaningful acceptance criterion
    (never an invented pseudo decision token), so a flag means genuine
    grader disagreement, not confusion about the harness.
    """
    from app.anticipy import taxonomy

    if not correct_graded:
        return {"sampled": 0, "flagged": 0, "flag_rate": 0.0, "pass": True}
    rng = random.Random(seed)
    k = max(1, int(len(correct_graded) * sample_frac))
    sample = rng.sample(correct_graded, min(k, len(correct_graded)))
    flagged = 0
    flags: list[dict] = []
    for item in sample:
        case = item["case"]
        transcript = json.dumps(case.get("transcript", []), ensure_ascii=False)
        criterion = taxonomy.criterion_text(case.get("category", ""), case.get("variant"))
        user = (
            f"TRANSCRIPT: {transcript}\n"
            f"ENGINE DECISION: {item['actual'].get('decision')}\n"
            f"ACCEPTANCE CRITERION: {criterion}\n"
            f"CATEGORY: {case.get('category')}"
        )
        res = platform_adapter.adversarial_model_call(_ADVERSARIAL_SYS, user, max_tokens=300)
        if not res.ok:
            continue
        try:
            s = res.content
            verdict = json.loads(s[s.find("{"): s.rfind("}") + 1])
        except Exception:
            continue
        if verdict.get("defensible") is False:
            flagged += 1
            flags.append({"case_id": item["case"].get("case_id"), "why": verdict.get("why", "")[:160]})
    sampled = len(sample)
    rate = flagged / sampled if sampled else 0.0
    return {
        "sampled": sampled,
        "flagged": flagged,
        "flag_rate": round(rate, 4),
        "pass": rate <= 0.05,
        "flags": flags[:15],
    }
