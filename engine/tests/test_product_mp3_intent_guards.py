import os

os.environ.setdefault("ANTICIPY_PORT", "18731")

from app.product import server


def test_second_person_allergy_advice_is_not_user_task():
    text = (
        "You have to book an allergies appointment and ask them, "
        "and then it's like this grass tech thing."
    )

    assert server._ambient_peer_chatter(text) is True
    assert server._mp3_eval_candidate_score(text) == 0
    assert server._low_context_clarify_plan(text) is None


def test_vague_homework_chatter_is_not_actionable():
    for text in (
        "Hey, we've got some homework to do.",
        "We have to do the homework.",
    ):
        low = text.lower()
        assert server._vague_homework_mention(low) is True
        assert server._mp3_eval_candidate_score(text) == 0
        assert server._low_context_clarify_plan(text) is None


def test_concrete_homework_and_assessments_still_surface():
    concrete = (
        "For homework, you will have to write those two documents "
        "that you started writing."
    )
    deadline = (
        "Writing assessment you do Monday, June 1st, and your listening, "
        "you do Thursday, June 4th."
    )

    assert server._mp3_eval_candidate_score(concrete) > 0
    assert server._low_context_clarify_plan(concrete)["intent"] == "school_homework_reminder"
    assert server._mp3_eval_candidate_score(deadline) > 0
    assert server._low_context_clarify_plan(deadline)["intent"] == "school_deadline_reminder"


def test_garbled_school_timing_is_not_deadline():
    text = "So I need first criteria to be my Saturday morning."

    assert server._garbled_school_timing(text.lower()) is True
    assert server._mp3_eval_candidate_score(text) == 0
    assert server._low_context_clarify_plan(text) is None


def test_teacher_title_period_does_not_split_candidate_excerpt():
    text = (
        "I'm gonna go talk to Mr. Hildebrand, because I can probably "
        "push it to a seven or a six at least."
    )

    excerpts = server._mp3_eval_candidate_excerpts(text)
    plan = server._low_context_clarify_plan(text)

    assert excerpts == [text]
    assert plan["intent"] == "teacher_followup_reminder"
    assert plan["teacher"] == "Mr. Hildebrand"
    assert "Mr. Hildebrand" in plan["question"]


def test_noisy_teacher_fragments_are_not_followup_tasks():
    for text in (
        "Yeah, but I'll ask you, I'll I'll talk to Miss Wayne.",
        "This way, I'll talk to Mr. Hilder and Mr. Hilton.",
    ):
        assert server._noisy_teacher_followup(text) is True
        assert server._mp3_eval_candidate_score(text) == 0
        assert server._low_context_clarify_plan(text) is None


def test_miss_title_is_not_rendered_with_period():
    text = "I'll talk to Miss Wayne today."
    plan = server._low_context_clarify_plan(text)

    assert plan["teacher"] == "Miss Wayne"
    assert "Miss Wayne" in plan["question"]
