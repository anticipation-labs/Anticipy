"""Do not start work that could never have finished.

Omar, 2026-08-05, after five of them in a row: "why is it trying to do things
without full context?"

Every one of these was started and could not finish, because she did not know
WHICH thing was meant:

    "put the link to today's recording into the doc and email it to the team"
    "open that budget spreadsheet and add the August"
    "email Priya the invoice"
    "send email to Andy from Barry"        -> 19 steps on a search page

The triage prompt has always asked for exactly this, in a field called
"missing". Measured against the live model on those four lines, it came back
EMPTY four times out of four. Writing a longer, clearer instruction about it
changed the output on ZERO of seven cases — the field is one of eight in a
JSON object and it loses every time.

Asked as the ONLY question, the same model on the same goals scored 8/8,
including correctly leaving a fully-specified booking and an open-ended
research task alone. So it is a separate call, and these tests pin the wall
around it rather than the model's judgement, which is measured live elsewhere.
"""
import json
import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from brain.orchestrator import SUFFICIENCY_SYSTEM, check_sufficiency  # noqa: E402


class Fake:
    live = True

    def __init__(self, payload):
        self.payload = payload
        self.asked = []

    def chat(self, system, user, **kw):
        self.asked.append((system, user))
        text = self.payload if isinstance(self.payload, str) else json.dumps(self.payload)
        return types.SimpleNamespace(text=text)


def test_an_unstartable_task_reports_what_is_needed():
    llm = Fake({"can_start": False,
                "needed": ["Which doc?", "Which recording?", "Who is the team?"]})
    assert check_sufficiency(llm, "add the recording link to the doc") == \
        ["Which doc?", "Which recording?", "Who is the team?"]


def test_a_startable_task_blocks_nothing():
    llm = Fake({"can_start": True, "needed": []})
    assert check_sufficiency(llm, "book a table for two at 7pm at Cactus Club") == []


def test_only_an_explicit_no_ever_blocks():
    """Absent, null, a string, a number — none of these are a refusal. A task
    is stopped only when the model actually says it cannot be started."""
    for payload in ({"needed": ["x"]},
                    {"can_start": None, "needed": ["x"]},
                    {"can_start": "false", "needed": ["x"]},
                    {"can_start": 0, "needed": ["x"]},
                    {"can_start": True, "needed": ["x"]}):
        assert check_sufficiency(Fake(payload), "some goal") == [], payload


def test_every_failure_blocks_nothing():
    """The honesty wall. A broken check must never stop work — it must vanish
    and leave behaviour exactly as it was before this existed."""
    assert check_sufficiency(Fake("not json at all"), "goal") == []
    assert check_sufficiency(Fake("{ broken "), "goal") == []
    assert check_sufficiency(Fake({"can_start": False, "needed": "not a list"}), "g") == []
    assert check_sufficiency(Fake({"can_start": False}), "g") == []
    assert check_sufficiency(None, "goal") == []
    assert check_sufficiency(Fake({"can_start": False, "needed": ["x"]}), "") == []

    class Dead:
        live = False

        def chat(self, *a, **k):
            raise AssertionError("must not be called when the model is offline")
    assert check_sufficiency(Dead(), "goal") == []

    class Boom:
        live = True

        def chat(self, *a, **k):
            raise RuntimeError("network")
    assert check_sufficiency(Boom(), "goal") == []


def test_the_question_is_bounded():
    llm = Fake({"can_start": False, "needed": [f"thing {n}" for n in range(20)]})
    assert len(check_sufficiency(llm, "goal")) == 4


def test_blank_entries_are_dropped():
    llm = Fake({"can_start": False, "needed": ["  ", "", "Which doc?", None]})
    assert check_sufficiency(llm, "goal") == ["Which doc?"]


def test_it_is_asked_on_its_own_not_bolted_onto_triage():
    """The whole finding. As one field among eight it returned empty every
    time; as the only question it was right 8/8."""
    llm = Fake({"can_start": True, "needed": []})
    check_sufficiency(llm, "book a table")
    system, user = llm.asked[0]
    assert system is SUFFICIENCY_SYSTEM
    assert '"decision"' not in system, "this must not be the triage prompt"
    assert '"owes"' not in system
    assert user.strip() == "TASK: book a table", "the goal, and nothing else"


def test_the_question_names_the_trap():
    """Pointing words with no referent are the entire failure mode."""
    low = " ".join(SUFFICIENCY_SYSTEM.split()).lower()
    assert "which one" in low
    assert "could it actually be done" in low
    # And the opposite mistake — refusing to start over things you would
    # simply look up on the way — is named too.
    assert "discoverable once you are underway" in low


def test_it_runs_before_the_gate_that_turns_act_into_ask():
    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "brain", "anticipy_core.py")).read()
    call = src.index("check_sufficiency(self.llm, decision.goal)")
    gate = src.index('if decision.decision == "act" and decision.missing:')
    assert call < gate, "the check must feed the gate, not run after it"


def test_an_explicit_ask_is_never_second_guessed():
    """When he says it TO her, he is present and can be asked directly. The
    check is for work she started off her own back."""
    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "brain", "anticipy_core.py")).read()
    line = [l for l in src.splitlines() if "check_sufficiency(self.llm" in l][0]
    idx = src.index(line)
    window = src[max(0, idx - 400):idx]
    assert "not explicit" in window


def test_the_gate_keeps_the_second_key():
    """The act->ask rebuild used to drop owes and continues on the floor —
    on exactly the path that fires most often now."""
    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "brain", "anticipy_core.py")).read()
    i = src.index('decision="ask", goal=decision.goal')
    block = src[i:i + 320]
    assert "owes=decision.owes" in block
    assert "continues=decision.continues" in block


def test_an_unrelated_pending_job_does_not_skip_the_check():
    """The regression that let the Priya email out.

    The first cut of the "already on his desk" guard also skipped whenever ANY
    plan was open, which says nothing about the goal in hand. With an
    unrelated email job pending, "Email Priya about the invoice" went straight
    past the check: she never asked who Priya was, opened Gmail, typed the
    word "Priya" into the address field, and pressed send.
    """
    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "brain", "anticipy_core.py")).read()
    i = src.index("already = None")
    block = src[i:i + 500]
    assert "_same_pending(decision.goal)" in block
    assert "_refines_pending(decision.goal)" in block
    assert "_open_plan" not in block, \
        "a bare open plan is not evidence about THIS goal"


def test_the_open_plan_skip_is_goal_specific_not_all_or_nothing():
    """Both directions of the same mistake, one week apart in the same file.

    Skipping the check whenever ANY plan was open let "Email Priya about the
    invoice" past unasked — she opened Gmail and typed the word "Priya" into
    the address field.

    Deleting the check outright broke the opposite case: every refining line
    of ONE dinner ("Brooklyn one", "Saturday at one", "it'll be us four")
    re-ran sufficiency and came back a fresh question, so the plan never
    became a card at all. The live Earls proof failed 2 of 2.

    The answer is neither: skip only when the open plan IS this plan.
    """
    src = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "brain", "anticipy_core.py")).read()
    i = src.index("already = None")
    block = src[i:i + 1400]
    assert "_same_pending(decision.goal)" in block
    assert "_refines_pending(decision.goal)" in block
    assert "self._same_plan(decision.goal, open_goal)" in block, \
        "an open plan may only skip the check when it is the SAME plan"
    # And the branch must be REACHABLE. Mutation testing walked straight past
    # the assertion above by replacing the condition with `if False:` — the
    # line was still in the file, just dead.
    assert "if not already and self._open_plan:" in block, \
        "the goal-specific skip must actually be reachable"
    # And the goal has to be carried, or the comparison has nothing to read.
    assert "self._open_plan = (job_id, time.time(), goal)" in src
