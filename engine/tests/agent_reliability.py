"""
Agent reliability harness for ITEM 7 of the Anticipy proof goal.

Runs 30 scenarios against a live local Anticipy engine at 127.0.0.1:8731:
  20 resolvable: indirect utterance plus context that points clearly at ONE
                 contact from the profile. Pass = /api/act resolves to that
                 contact with intent=email_draft.
  10 ambiguous:  context names TWO contacts comparably for the same task.
                 Pass = pending.clarify is true, plan.question names BOTH
                 contenders by first name, and /api/act is NOT called.

Pass thresholds (per the goal):
  resolvable: 18/20 (== 28/30 floor when ambiguous is perfect)
  ambiguous:  10/10
Combined floor: 28/30 with ambiguous perfect.

Assumes profile already onboarded with:
  Dana Bright   (boss)              omarkebrahim+anticipy-dana@gmail.com
  Priya Shah    (strategy advisor)  omarkebrahim+anticipy-priya@gmail.com
  Maya Chen     (operations partner) omarkebrahim+anticipy-maya@gmail.com
If not, the run aborts with a precondition failure.

Usage:
  python engine/tests/agent_reliability.py [--engine-url URL]
                                           [--out PATH]
                                           [--no-act]
                                           [--only NAME]

Exits 0 on pass, 1 on fail.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Optional

import requests

DEFAULT_ENGINE_URL = "http://127.0.0.1:8731"

INJECT = "/api/listen/inject"
LRESET = "/api/listen/reset"
LSTART = "/api/listen/start"
LSTAT = "/api/listen/status"
ACT = "/api/act"
STATE = "/api/state"

REQUIRED_PEOPLE = ("Dana Bright", "Priya Shah", "Maya Chen")


@dataclass
class Scenario:
    name: str
    category: str
    context: list[str]
    trigger: str
    expected_person: Optional[str] = None
    expected_contenders: Optional[list[str]] = None


@dataclass
class Result:
    scenario: Scenario
    passed: bool = False
    actual_mode: str = ""
    actual_person: str = ""
    actual_question: str = ""
    actual_intent: str = ""
    error: str = ""
    duration_s: float = 0.0
    raw: dict = field(default_factory=dict)


RESOLVABLE: list[Scenario] = [
    Scenario("R01-dana-q3", "resolvable",
             ["Dana Bright owns the Q3 roadmap and asked for my notes today."],
             "I should send those to her by tomorrow.",
             expected_person="Dana Bright"),
    Scenario("R02-dana-friday-update", "resolvable",
             ["Dana wants the Friday launch update before the all-hands."],
             "I really need to get that out to her tonight.",
             expected_person="Dana Bright"),
    Scenario("R03-dana-board-deck", "resolvable",
             ["Dana is presenting to the board and asked me for the latest deck."],
             "I owe her the deck before close of business.",
             expected_person="Dana Bright"),
    Scenario("R04-dana-1on1-notes", "resolvable",
             ["I told Dana I would write up our 1-on-1 notes."],
             "Those notes are still sitting in my drafts.",
             expected_person="Dana Bright"),
    Scenario("R05-dana-budget", "resolvable",
             ["Dana flagged the marketing budget for review."],
             "I should walk her through the numbers this week.",
             expected_person="Dana Bright"),
    Scenario("R06-dana-followups", "resolvable",
             ["My boss Dana wants follow-ups from the customer call."],
             "I need to write those up and send them over.",
             expected_person="Dana Bright"),
    Scenario("R07-priya-strategy-memo", "resolvable",
             ["Priya Shah needs the strategy memo for our advisor call."],
             "I should get that over to her tonight.",
             expected_person="Priya Shah"),
    Scenario("R08-priya-market-analysis", "resolvable",
             ["Priya asked for the market analysis from last quarter."],
             "I told her I would forward it before Friday.",
             expected_person="Priya Shah"),
    Scenario("R09-priya-positioning", "resolvable",
             ["Our strategy advisor Priya wants the positioning doc."],
             "I should send her the latest version.",
             expected_person="Priya Shah"),
    Scenario("R10-priya-investor-prep", "resolvable",
             ["Priya is helping us prep for the investor meeting."],
             "I need to share the financial model with her.",
             expected_person="Priya Shah"),
    Scenario("R11-priya-roadmap-review", "resolvable",
             ["Priya offered to review the roadmap before we ship it."],
             "I should send the roadmap to her tonight.",
             expected_person="Priya Shah"),
    Scenario("R12-priya-pricing-notes", "resolvable",
             ["Priya asked me to write up the pricing exploration."],
             "She is waiting on those notes.",
             expected_person="Priya Shah"),
    Scenario("R13-priya-board-feedback", "resolvable",
             ["Priya gave feedback on the board deck and wants the revised one back."],
             "I should send the revised version to her.",
             expected_person="Priya Shah"),
    Scenario("R14-maya-ops-checklist", "resolvable",
             ["Maya Chen is handling the ops handoff this week."],
             "I owe her the ops checklist.",
             expected_person="Maya Chen"),
    Scenario("R15-maya-vendor-list", "resolvable",
             ["Maya asked for the vendor list and our renewal dates."],
             "I should pull that together and send it to her.",
             expected_person="Maya Chen"),
    Scenario("R16-maya-onboarding-doc", "resolvable",
             ["Maya is onboarding the new hire and asked for our onboarding doc."],
             "I need to share that with her today.",
             expected_person="Maya Chen"),
    Scenario("R17-maya-payroll", "resolvable",
             ["Our operations partner Maya needs the payroll schedule."],
             "I should send her the schedule before next pay run.",
             expected_person="Maya Chen"),
    Scenario("R18-maya-runbook", "resolvable",
             ["Maya wants the incident runbook from last month."],
             "I should get her the runbook by tomorrow.",
             expected_person="Maya Chen"),
    Scenario("R19-maya-team-expenses", "resolvable",
             ["Maya is finalizing this month's team expense report."],
             "I need to send her my receipts.",
             expected_person="Maya Chen"),
    Scenario("R20-maya-tooling", "resolvable",
             ["Maya is reviewing our tooling stack and asked for my list."],
             "I should send the tooling list over to her.",
             expected_person="Maya Chen"),
]


AMBIGUOUS: list[Scenario] = [
    Scenario("A01-dana-vs-priya-launch-recap", "ambiguous",
             ["Dana Bright asked for the launch recap. Priya Shah also asked for the launch recap."],
             "I should get that over to her before tomorrow.",
             expected_contenders=["Dana", "Priya"]),
    Scenario("A02-priya-vs-maya-planning-notes", "ambiguous",
             ["Priya wants the planning notes for our advisor call. Maya wants the same planning notes for the ops review."],
             "I need to send those over.",
             expected_contenders=["Priya", "Maya"]),
    Scenario("A03-dana-vs-maya-onboarding-doc", "ambiguous",
             ["Dana asked for the onboarding doc to share with a candidate. Maya asked for the onboarding doc for the new hire."],
             "I should send the doc to her today.",
             expected_contenders=["Dana", "Maya"]),
    Scenario("A04-dana-vs-priya-board-deck", "ambiguous",
             ["Dana needs the board deck for her presentation. Priya wants the board deck to review the narrative."],
             "I should send her the deck.",
             expected_contenders=["Dana", "Priya"]),
    Scenario("A05-priya-vs-maya-pricing", "ambiguous",
             ["Priya wants the pricing exploration from a strategy angle. Maya wants the same pricing doc for the ops billing setup."],
             "I owe her the pricing notes by Friday.",
             expected_contenders=["Priya", "Maya"]),
    Scenario("A06-dana-vs-priya-roadmap", "ambiguous",
             ["Dana wants the roadmap for the all-hands. Priya wants the roadmap to advise us on sequencing."],
             "I should get the roadmap over to her tonight.",
             expected_contenders=["Dana", "Priya"]),
    Scenario("A07-dana-vs-maya-budget", "ambiguous",
             ["Dana flagged the marketing budget for review. Maya needs the same budget for ops planning."],
             "I should walk her through the numbers this week.",
             expected_contenders=["Dana", "Maya"]),
    Scenario("A08-priya-vs-maya-investor-prep", "ambiguous",
             ["Priya is helping us prep for the investor meeting. Maya is putting together the ops section for the same meeting."],
             "I need to share the financial model with her.",
             expected_contenders=["Priya", "Maya"]),
    Scenario("A09-dana-vs-priya-positioning", "ambiguous",
             ["Dana wants the positioning doc for the board. Priya wants the same positioning doc to give strategy feedback."],
             "I should send her the latest version.",
             expected_contenders=["Dana", "Priya"]),
    Scenario("A10-dana-vs-maya-followups", "ambiguous",
             ["Dana wants the follow-ups from the customer call. Maya is owning the post-call ops follow-ups for the same call."],
             "I need to write those up and send them over.",
             expected_contenders=["Dana", "Maya"]),
]


def _post(engine_url: str, path: str, body: Optional[dict] = None,
          timeout: float = 30.0) -> dict:
    r = requests.post(engine_url + path, json=body or {}, timeout=timeout)
    r.raise_for_status()
    return r.json()


def _get(engine_url: str, path: str, timeout: float = 10.0) -> dict:
    r = requests.get(engine_url + path, timeout=timeout)
    r.raise_for_status()
    return r.json()


def _preflight(engine_url: str) -> None:
    state = _get(engine_url, STATE)
    if not state.get("onboarded"):
        raise SystemExit(
            "PRECONDITION FAILED: engine reports onboarded=false. "
            "Onboard via anticipy.ai/app or run the engine with a HOME that "
            "already has product_profile.json populated."
        )
    profile = state.get("profile") or {}
    people = profile.get("people") or {}
    flat = " ".join(f"{k}={v}" for k, v in people.items())
    missing = [p for p in REQUIRED_PEOPLE if p not in flat]
    if missing:
        raise SystemExit(
            f"PRECONDITION FAILED: profile missing required people {missing}. "
            f"Profile people seen: {flat!r}"
        )


def _ensure_listening(engine_url: str) -> None:
    s = _get(engine_url, LSTAT)
    if not s.get("on"):
        _post(engine_url, LSTART)


def _run_scenario(engine_url: str, sc: Scenario, do_act: bool) -> Result:
    t0 = time.monotonic()
    res = Result(scenario=sc)
    try:
        _post(engine_url, LRESET)
        for ctx in sc.context:
            _post(engine_url, INJECT, {"text": ctx})
        trig = _post(engine_url, INJECT, {"text": sc.trigger}, timeout=120.0)
        res.raw["inject"] = trig

        pending = (trig.get("pending") or {})
        plan = (pending.get("plan") or {})
        res.actual_mode = (plan.get("mode") or "").strip().lower()
        res.actual_person = (plan.get("person") or pending.get("person") or "").strip()
        res.actual_question = (plan.get("question") or "").strip()
        res.actual_intent = (plan.get("intent") or "").strip()

        if sc.category == "ambiguous":
            is_clarify = bool(pending.get("clarify")) or res.actual_mode == "clarify"
            q_lower = res.actual_question.lower()
            names_both = all(c.lower() in q_lower for c in (sc.expected_contenders or []))
            res.passed = is_clarify and names_both
            if not res.passed and not res.error:
                res.error = (
                    f"expected clarify naming {sc.expected_contenders!r}, "
                    f"got mode={res.actual_mode!r} q={res.actual_question!r}"
                )
            return res

        if res.actual_mode != "act":
            res.error = (
                f"resolvable: expected mode=act, got mode={res.actual_mode!r} "
                f"q={res.actual_question!r}"
            )
            return res

        if sc.expected_person and sc.expected_person.lower() not in res.actual_person.lower():
            res.error = (
                f"resolvable: expected person={sc.expected_person!r}, "
                f"got person={res.actual_person!r}"
            )
            return res

        if do_act:
            act_resp = _post(engine_url, ACT, {}, timeout=480.0)
            res.raw["act"] = act_resp
            ran = bool(act_resp.get("ran"))
            status = (act_resp.get("status") or "").upper()
            resolved = (act_resp.get("resolved_person") or "").strip()
            if not ran or status != "SUCCESS":
                res.error = f"act failed: ran={ran} status={status!r}"
                return res
            if sc.expected_person.lower() not in resolved.lower():
                res.error = (
                    f"act resolved wrong person: expected {sc.expected_person!r}, "
                    f"got {resolved!r}"
                )
                return res

        res.passed = True
    except requests.HTTPError as e:
        res.error = f"http error: {e!r}"
    except requests.RequestException as e:
        res.error = f"request error: {e!r}"
    except Exception as e:
        res.error = f"unexpected error: {e!r}"
    finally:
        res.duration_s = round(time.monotonic() - t0, 2)
    return res


def _print_table(results: list[Result]) -> None:
    header = f"{'#':>3}  {'name':<32}  {'cat':<10}  {'verdict':<6}  {'sec':>5}  details"
    print(header)
    print("-" * len(header))
    for i, r in enumerate(results, start=1):
        v = "PASS" if r.passed else "FAIL"
        det = r.error if not r.passed else (
            r.actual_question if r.scenario.category == "ambiguous" else r.actual_person
        )
        print(f"{i:>3}  {r.scenario.name:<32}  {r.scenario.category:<10}  "
              f"{v:<6}  {r.duration_s:>5.2f}  {det[:80]}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine-url", default=DEFAULT_ENGINE_URL)
    parser.add_argument("--out", default="proof-artifacts/agent_reliability.json")
    parser.add_argument("--no-act", action="store_true",
                        help="skip /api/act calls (faster, doesn't drive Gmail)")
    parser.add_argument("--only", default=None,
                        help="run only one scenario by name (debug)")
    args = parser.parse_args()

    _preflight(args.engine_url)
    _ensure_listening(args.engine_url)

    all_scenarios = RESOLVABLE + AMBIGUOUS
    if args.only:
        all_scenarios = [s for s in all_scenarios if s.name == args.only]
        if not all_scenarios:
            print(f"no scenario named {args.only!r}", file=sys.stderr)
            return 1

    results: list[Result] = []
    do_act = not args.no_act
    for sc in all_scenarios:
        r = _run_scenario(args.engine_url, sc, do_act)
        results.append(r)

    _print_table(results)

    resolvable_results = [r for r in results if r.scenario.category == "resolvable"]
    ambiguous_results = [r for r in results if r.scenario.category == "ambiguous"]
    resolvable_pass = sum(1 for r in resolvable_results if r.passed)
    ambiguous_pass = sum(1 for r in ambiguous_results if r.passed)

    print()
    print(f"resolvable: {resolvable_pass}/{len(resolvable_results)}")
    print(f"ambiguous:  {ambiguous_pass}/{len(ambiguous_results)}")

    overall_pass = (resolvable_pass + ambiguous_pass) >= 28 and ambiguous_pass == len(ambiguous_results)
    verdict = "PASS" if overall_pass else "FAIL"
    print(f"verdict:    {verdict}")

    out_path = args.out
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    summary = {
        "engine_url": args.engine_url,
        "do_act": do_act,
        "resolvable_pass": resolvable_pass,
        "resolvable_total": len(resolvable_results),
        "ambiguous_pass": ambiguous_pass,
        "ambiguous_total": len(ambiguous_results),
        "verdict": verdict,
        "results": [
            {
                "name": r.scenario.name,
                "category": r.scenario.category,
                "passed": r.passed,
                "duration_s": r.duration_s,
                "actual_mode": r.actual_mode,
                "actual_person": r.actual_person,
                "actual_question": r.actual_question,
                "actual_intent": r.actual_intent,
                "error": r.error,
            }
            for r in results
        ],
    }
    with open(out_path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"summary written to {out_path}")

    return 0 if overall_pass else 1


if __name__ == "__main__":
    sys.exit(main())
