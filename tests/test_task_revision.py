"""Contextual amendment boundaries; no fixture wording drives production code."""
import json
from types import SimpleNamespace
import pytest
from brain.task_revision import reconcile
from brain.anticipy_core import _required_from_missing, _missing_fact_question
from brain.workflow import new_plan, merge, approve, Consequence, PlanState, WorkflowViolation


def model(answer):
    def chat(system, user, **kwargs):
        model.last_context = json.loads(user)
        if isinstance(answer, Exception):
            raise answer
        return SimpleNamespace(text=json.dumps(answer))
    return SimpleNamespace(live=True, chat=chat)


@pytest.mark.parametrize('answer', [None, {}, {'verdict': 'unclear'},
    {'verdict': 'revised', 'goal': 'task', 'missing': 'not a list'},
    {'verdict': 'revised', 'goal': 'task', 'missing': [None]}, TimeoutError()])
def test_no_valid_verdict_never_replaces_existing_plan(answer):
    assert reconcile(model(answer), {'goal': 'unchanged'}, {'conversation': 'update'}) is None


def test_whole_context_and_opaque_question_keys_reach_model():
    question = 'À quelle heure et dans quel fuseau horaire doit-elle commencer ?'
    current = {'goal': 'Review the supplier contract', 'params': {'missing': [question]}}
    update = {'conversation': 'The supplier is in Montréal. Keep the earlier constraints.'}
    answer = {'verdict': 'revised', 'goal': 'Review the Montréal supplier contract',
              'missing': [question], 'facts': {}}
    assert reconcile(model(answer), current, update) == answer
    assert model.last_context == {'current': current, 'update': update}
    assert _required_from_missing([question, question]) == (question,)
    assert _missing_fact_question([question], [question]).endswith(question)


def test_long_question_blocks_approval_until_answer_and_invalidates_prior_approval():
    question = 'Which of the supplied file formats should the manufacturer receive?'
    p = new_plan(owner_ref='one', lineage_key='one', goal='Send approved design',
                 consequence=Consequence.CONSEQUENTIAL, source_event_id='e1')
    approved = approve(p, expected_version=p.version, owner_words='yes')
    changed = merge(approved, expected_version=approved.version, required=[question])
    assert changed.state == PlanState.DRAFT
    assert changed.approval is None and changed.missing == (question,)
    with pytest.raises(WorkflowViolation):
        approve(changed, expected_version=changed.version, owner_words='yes')
    answered = merge(changed, expected_version=changed.version, facts={question: 'STEP'})
    assert answered.state == PlanState.AWAITING_APPROVAL and not answered.missing
    with pytest.raises(WorkflowViolation):
        approve(answered, expected_version=approved.version, owner_words='yes')


def test_two_answers_preserve_first_answer_and_clear_the_question(monkeypatch):
    from brain.conversation import Conversation
    import brain.conversation as convmod
    from tests.test_correction_integrity import _conv, _pb
    from brain.workflow import put_in_params
    first, second = 'Which manufacturer should receive it?', 'Which export format do they need?'
    p = new_plan(owner_ref='o', lineage_key='design', goal='Send the approved design',
        consequence=Consequence.CONSEQUENTIAL, source_event_id='e1', required=[first, second])
    job = dict(p.job_fields(), id='j1', goal=p.goal, result=first,
        params=json.dumps(put_in_params({'missing': [first, second]}, p)))
    patched = _pb(monkeypatch, convmod, job)
    monkeypatch.setattr(Conversation, '_resolve_question', lambda *a:
        {'verdict': 'partial', 'changes': {first: 'Morgan Engineering'}, 'remaining_question': second})
    assert _conv()._amend('j1', {'owner_answer': 'Morgan Engineering'}, owner_text='Morgan Engineering') == 'amended:j1'
    job.update(patched)
    stored = json.loads(job['params'])['_workflow']
    assert stored['facts'][first] == 'Morgan Engineering'
    assert stored['state'] == 'draft' and job['result'] == second
    monkeypatch.setattr(Conversation, '_resolve_question', lambda *a:
        {'verdict': 'answered', 'changes': {second: 'STEP'}, 'remaining_question': ''})
    assert _conv()._amend('j1', {'owner_answer': 'STEP'}, owner_text='STEP') == 'amended:j1'
    final = json.loads(patched['params'])['_workflow']
    assert final['facts'] == {first: 'Morgan Engineering', second: 'STEP'}
    assert final['state'] == 'awaiting_approval' and patched['result'] == ''
