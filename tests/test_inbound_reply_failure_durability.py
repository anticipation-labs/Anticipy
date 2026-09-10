"""Actual inbox and publisher: a failed answer must not replay task effects.

All records and transports are fixtures. Backend requests use in-memory SQLite;
the only conversation double is the reasoning/effect boundary we must count.
"""
import ast
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from brain import backend, worker as W
from brain.conversation import Conversation, Turn
from brain.reply_delivery import ReplyDelivery


@pytest.fixture
def inbox(monkeypatch):
    db = sqlite3.connect(':memory:')
    db.row_factory = sqlite3.Row
    db.execute('CREATE TABLE events (id TEXT PRIMARY KEY, owner_ref TEXT, kind TEXT, '
               'text TEXT, decision TEXT, goal TEXT, source TEXT, device_id TEXT, '
               'created TEXT, updated TEXT, external_event_id TEXT UNIQUE)')
    stamp = lambda: datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('T', ' ')
    old = (datetime.now(timezone.utc) - timedelta(minutes=11)).isoformat(timespec='milliseconds').replace('T', ' ')
    db.execute("INSERT INTO events VALUES ('input1','owner1','transcript','Fictional request','','','typed','fixture',?,?,NULL)", (old, old))
    failure = SimpleNamespace(reply=False, outbox=False, mark='', mark_after_write=False)
    effects = []

    def response(body):
        return SimpleNamespace(ok=True, status_code=200, json=lambda: body, raise_for_status=lambda: None)

    def get(url, params=None, **kwargs):
        assert '/api/collections/events/records' in url
        expression = params['filter'].replace('&&', 'AND').replace('||', 'OR')
        sort = params.get('sort', 'created')
        order = sort[1:] + ' DESC' if sort.startswith('-') else sort
        rows = db.execute('SELECT * FROM events WHERE ' + expression + ' ORDER BY ' + order + ' LIMIT ?',
                          (params.get('perPage', 100),)).fetchall()
        return response({'items': [dict(row) for row in rows]})

    def post(url, json, **kwargs):
        if (failure.reply and json.get('kind') == 'anticipy_text') or (failure.outbox and json.get('kind') == 'reply_outbox'):
            raise ConnectionError('fixture write unavailable')
        row = {'id': 'row' + str(db.execute('SELECT count(*) FROM events').fetchone()[0]),
               'created': stamp(), 'updated': stamp(), **json}
        db.execute(f'INSERT INTO events ({",".join(row)}) VALUES ({",".join("?" for _ in row)})', list(row.values()))
        return response(dict(db.execute('SELECT * FROM events WHERE id=?', (row['id'],)).fetchone()))

    def patch(url, json, **kwargs):
        fail = failure.mark and json.get('decision') == failure.mark
        if fail and not failure.mark_after_write:
            raise ConnectionError('fixture mark unavailable')
        row = {'updated': stamp(), **json}
        db.execute(f'UPDATE events SET {",".join(k+"=?" for k in row)} WHERE id=?',
                   [*row.values(), url.rsplit('/', 1)[1]])
        if fail:
            raise ConnectionError('fixture mark response lost')
        return response({})

    monkeypatch.setattr(backend, 'get', get)
    monkeypatch.setattr(backend, 'post', post)
    monkeypatch.setattr(backend, 'patch', patch)
    monkeypatch.setattr(W, 'connection_command', lambda *args: 'not_for_us')
    owner = SimpleNamespace(owner_ref='owner1', owner_phone='', llm=None,
                            _voice=Mock(side_effect=AssertionError('recovery must not call a model')))
    transport = SimpleNamespace(send=Mock(return_value={'sid': 'fixture-receipt', 'delivered': False}))
    delivery = ReplyDelivery('http://fixture', 'owner1', transport, lambda: '+15555550101')
    convo = Conversation(owner, transport=transport)
    convo.reply_delivery = delivery.publish

    def reasoning(phone, text, **kwargs):
        effects.append('one task mutation')
        convo.say(phone, 'The original saved answer')
        return {'intent': 'chat', 'reply': 'The original saved answer'}

    convo.on_reply = Mock(side_effect=reasoning)
    read = lambda: dict(db.execute("SELECT * FROM events WHERE id='input1'").fetchone())
    return SimpleNamespace(db=db, failure=failure, effects=effects, owner=owner,
                           convo=convo, delivery=delivery, transport=transport, read=read, old=old)


def test_failed_reply_remains_recoverable_without_repeating_task(inbox):
    inbox.failure.reply = True
    W.handle_inbound(inbox.read(), inbox.convo, inbox.owner)
    assert inbox.read()['decision'] == 'reply_error_pending'
    assert inbox.db.execute("SELECT count(*) FROM events WHERE kind='anticipy_text'").fetchone()[0] == 0
    inbox.failure.reply = False
    W.service_direct_inputs(inbox.convo, inbox.owner)
    assert inbox.read()['decision'] == 'error'
    assert inbox.effects == ['one task mutation']
    assert inbox.convo.on_reply.call_count == 1
    assert inbox.transport.send.call_count == 1
    assert inbox.db.execute("SELECT count(*) FROM events WHERE kind='reply_outbox'").fetchone()[0] == 1
    assert not inbox.owner._voice.called


def test_existing_normal_reply_is_recovered_without_rewording(inbox):
    inbox.failure.outbox = True
    W.handle_inbound(inbox.read(), inbox.convo, inbox.owner)
    assert inbox.read()['decision'] == 'reply_error_pending'
    inbox.failure.outbox = False
    W.service_direct_inputs(inbox.convo, inbox.owner)
    messages = inbox.db.execute("SELECT text FROM events WHERE kind='anticipy_text'").fetchall()
    assert [row[0] for row in messages] == ['The original saved answer']
    assert inbox.effects == ['one task mutation']
    # Its original presentation metadata was never saved. Do not invent a
    # metadata-free SMS that could be a superseded task approval question.
    assert inbox.transport.send.call_count == 0
    assert inbox.db.execute("SELECT decision FROM events WHERE kind='reply_outbox'").fetchone()[0] == 'reply_context_unavailable'


@pytest.mark.parametrize('after_write', [False, True])
def test_unknown_initial_processing_marker_never_runs_reasoning(inbox, after_write):
    inbox.failure.mark = 'reply_processing'
    inbox.failure.mark_after_write = after_write
    assert W.handle_inbound(inbox.read(), inbox.convo, inbox.owner) == 'unclaimed'
    assert not inbox.convo.on_reply.called
    assert not inbox.effects
    assert inbox.transport.send.call_count == 0


def test_failed_error_marker_is_not_released_into_reasoning(inbox):
    inbox.failure.reply = True
    inbox.failure.mark = 'reply_error_pending'
    W.handle_inbound(inbox.read(), inbox.convo, inbox.owner)
    assert inbox.read()['decision'] == 'reply_processing'
    inbox.db.execute("UPDATE events SET updated=? WHERE id='input1'", (inbox.old,))
    assert W.release_stranded_claims('owner1') == 0
    inbox.failure.reply = False
    inbox.failure.mark = ''
    W.service_direct_inputs(inbox.convo, inbox.owner)
    assert inbox.read()['decision'] == 'error'
    assert inbox.effects == ['one task mutation']
    assert inbox.transport.send.call_count == 1


def test_failed_terminal_marker_reconciles_saved_reply_without_repeating_effect(inbox):
    inbox.failure.mark = 'chat'
    W.handle_inbound(inbox.read(), inbox.convo, inbox.owner)
    assert inbox.read()['decision'] == 'reply_processing'
    inbox.db.execute("UPDATE events SET updated=? WHERE id='input1'", (inbox.old,))
    inbox.failure.mark = ''
    W.service_direct_inputs(inbox.convo, inbox.owner)
    assert inbox.convo.on_reply.call_count == 1
    assert inbox.transport.send.call_count == 1
    assert inbox.db.execute("SELECT text FROM events WHERE kind='anticipy_text'").fetchone()[0] == 'The original saved answer'


def test_fresh_processing_is_not_interrupted_or_reclaimed(inbox):
    inbox.db.execute("UPDATE events SET decision='reply_processing',updated=? WHERE id='input1'",
                     (datetime.now(timezone.utc).isoformat().replace('T', ' '),))
    W.service_direct_inputs(inbox.convo, inbox.owner)
    assert inbox.convo.on_reply.call_count == 0
    assert inbox.transport.send.call_count == 0
    assert W.release_stranded_claims('owner1') == 0


def test_terminal_error_write_failure_reuses_exact_recovery_reply(inbox):
    inbox.failure.reply = True
    W.handle_inbound(inbox.read(), inbox.convo, inbox.owner)
    inbox.failure.reply = False
    inbox.failure.mark = 'error'
    W.service_direct_inputs(inbox.convo, inbox.owner)
    assert inbox.read()['decision'] == 'reply_error_pending'
    W.service_direct_inputs(inbox.convo, inbox.owner)
    assert inbox.transport.send.call_count == 1
    assert inbox.effects == ['one task mutation']
    inbox.failure.mark = ''
    W.service_direct_inputs(inbox.convo, inbox.owner)
    assert inbox.read()['decision'] == 'error'


def test_foreign_recovery_input_never_gets_claimed_or_published(inbox):
    event = {**inbox.read(), 'owner_ref': 'foreign', 'decision': 'reply_error_pending'}
    assert W.handle_inbound(event, inbox.convo, inbox.owner) == 'unclaimed'
    assert inbox.read()['decision'] == ''
    assert inbox.convo.on_reply.call_count == 0
    assert inbox.transport.send.call_count == 0


def test_shipping_ambient_snapshot_cannot_reprocess_a_typed_reply(inbox):
    from test_interactive_priority import hearing_and_reply_pass
    scope = {**vars(W), 'anticipy': inbox.owner, 'convo': inbox.convo}
    exec(hearing_and_reply_pass(), scope)
    assert inbox.convo.on_reply.call_count == 1
    assert inbox.effects == ['one task mutation']
    assert inbox.transport.send.call_count == 1


def test_provider_response_uncertainty_is_not_a_retry_license(inbox):
    inbox.transport.send.side_effect = TimeoutError('fixture provider uncertainty')
    inbox.failure.mark = 'chat'
    W.handle_inbound(inbox.read(), inbox.convo, inbox.owner)
    inbox.db.execute("UPDATE events SET updated=? WHERE id='input1'", (inbox.old,))
    inbox.failure.mark = ''
    W.service_direct_inputs(inbox.convo, inbox.owner)
    assert inbox.transport.send.call_count == 1
    assert inbox.effects == ['one task mutation']
    assert inbox.db.execute("SELECT decision FROM events WHERE kind='notification_status'").fetchone()[0] == 'sms_unconfirmed'


@pytest.mark.parametrize('updated', ['', 'not-a-date', '9999999999999999999999'])
def test_unknown_processing_timestamp_is_not_expiry(inbox, updated):
    event = {**inbox.read(), 'decision': 'reply_processing', 'updated': updated}
    assert W.handle_inbound(event, inbox.convo, inbox.owner) == 'unclaimed'
    assert inbox.convo.on_reply.call_count == 0
    assert inbox.transport.send.call_count == 0


def test_duplicate_recovery_cannot_resend_or_repeat_task(inbox):
    inbox.failure.reply = True
    W.handle_inbound(inbox.read(), inbox.convo, inbox.owner)
    stale = inbox.read()
    inbox.failure.reply = False
    W.handle_inbound(stale, inbox.convo, inbox.owner)
    W.handle_inbound(stale, inbox.convo, inbox.owner)
    assert inbox.effects == ['one task mutation']
    assert inbox.transport.send.call_count == 1
    assert inbox.db.execute("SELECT count(*) FROM events WHERE kind='anticipy_text'").fetchone()[0] == 1


def test_non_inbound_row_cannot_become_a_recovery_reply(inbox):
    event = {**inbox.read(), 'kind': 'notification_status', 'decision': 'reply_error_pending'}
    assert W.handle_inbound(event, inbox.convo, inbox.owner) == 'unclaimed'
    assert inbox.read()['decision'] == ''
    assert inbox.convo.on_reply.call_count == 0
    assert inbox.transport.send.call_count == 0


def test_lost_task_question_context_cannot_turn_into_unconditional_sms(inbox):
    def reason(phone, text):
        inbox.effects.append('one task mutation')
        inbox.convo._reply_metadata = {'purpose': 'task_question', 'job_id': 'job1',
            'version': 2, 'status': 'awaiting_confirm', 'question': 'Approve the old task?'}
        try:
            inbox.convo.say(phone, 'Approve the old task?')
        finally:
            inbox.convo._reply_metadata = None  # The real on_reply finally does this.
    inbox.convo.on_reply.side_effect = reason
    inbox.failure.outbox = True
    W.handle_inbound(inbox.read(), inbox.convo, inbox.owner)
    inbox.failure.outbox = False
    W.service_direct_inputs(inbox.convo, inbox.owner)
    inbox.delivery.sweep()
    assert inbox.effects == ['one task mutation']
    assert inbox.transport.send.call_count == 0
    assert inbox.db.execute("SELECT text FROM events WHERE kind='anticipy_text'").fetchone()[0] == 'Approve the old task?'
    assert inbox.db.execute("SELECT decision FROM events WHERE kind='reply_outbox'").fetchone()[0] == 'reply_context_unavailable'


@pytest.mark.parametrize('saved_answer', [False, True])
def test_next_app_classifier_sees_exact_recovered_answer_once(inbox, saved_answer):
    inbox.owner.backend_url = 'http://fixture'
    inbox.owner.memory = SimpleNamespace(recall=lambda *args, **kwargs: [])
    inbox.convo.on_reply = Conversation.on_reply.__get__(inbox.convo)
    if saved_answer:
        inbox.convo._classify = Mock(return_value={
            'intent': 'chat', 'reply': 'The original saved answer'})
        inbox.failure.outbox = True
    else:
        inbox.convo._classify = Mock(side_effect=RuntimeError('fixture interrupted reasoning'))
        inbox.failure.reply = True
    W.handle_inbound(inbox.read(), inbox.convo, inbox.owner)
    stale = inbox.read()
    assert stale['decision'] == 'reply_error_pending'
    # Actual on_reply cached the owner's turn before the interrupted reply.
    assert inbox.convo.threads['app:owner1']
    inbox.failure.reply = inbox.failure.outbox = False
    W.handle_inbound(stale, inbox.convo, inbox.owner)
    W.handle_inbound(stale, inbox.convo, inbox.owner)
    answer = inbox.db.execute("SELECT text FROM events WHERE kind='anticipy_text'").fetchone()[0]

    payloads = []
    def model_reply(system, payload):
        payloads.append(json.loads(payload))
        return SimpleNamespace(text='{"intent":"chat","reply":"fixture"}')
    inbox.convo.llm = SimpleNamespace(live=True, chat=model_reply)
    for method in ('_pending', '_blocked', '_queued', '_running', '_recent_outcomes', '_captured_context'):
        setattr(inbox.convo, method, lambda: [])
    next_input = {**inbox.read(), 'id': 'input2', 'text': 'What did you mean?',
                  'created': (datetime.now(timezone.utc) + timedelta(seconds=1)).isoformat().replace('T', ' ')}
    with inbox.convo.from_event(next_input):
        Conversation._classify(inbox.convo, 'app:owner1', next_input['text'])
    thread = payloads[0]['thread']
    assert sum(turn == {'who': 'anticipy', 'text': answer} for turn in thread) == 1
    assert sum(turn == {'who': 'owner', 'text': 'Fictional request'} for turn in thread) == 1
    assert inbox.transport.send.call_count == (0 if saved_answer else 1)


def test_recovery_history_invalidation_is_canonical_owner_scoped(inbox):
    other = Conversation(SimpleNamespace(owner_ref='other-owner', llm=None))
    other.threads['app:other-owner'] = [Turn('owner', 'Other fixture conversation')]
    inbox.convo.threads['old-phone-key'] = [Turn('owner', 'Earlier account conversation')]
    inbox.convo.threads['app:owner1'] = [Turn('owner', 'Current account conversation')]
    assert not inbox.convo.invalidate_reply_history({**inbox.read(), 'owner_ref': 'other-owner'})
    assert len(inbox.convo.threads) == 2
    assert inbox.convo.invalidate_reply_history(inbox.read())
    assert inbox.convo.threads == {}
    assert other.threads['app:other-owner'][0].text == 'Other fixture conversation'


def test_unpersisted_recovery_does_not_discard_cached_history(inbox):
    inbox.convo.threads['app:owner1'] = [Turn('owner', 'Current account conversation')]
    inbox.failure.reply = True
    event = {**inbox.read(), 'decision': 'reply_error_pending'}
    assert W.recover_inbound_reply(event, inbox.convo, inbox.owner) == 'unclaimed'
    assert inbox.convo.threads['app:owner1'][0].text == 'Current account conversation'


@pytest.mark.parametrize('decision', ['reply_processing', 'reply_error_pending'])
def test_offline_outcome_readers_do_not_report_recovery_as_a_verdict(decision):
    from proof.e2e_cloudflare import decision_state, heard_state
    from proof.outcome_rate import classify
    assert decision_state({'decision': decision}) == 'processing'
    assert heard_state({'decision': decision}) == 'unheard'
    assert classify({'decision': decision}, set(), False) == 'in_flight'


@pytest.mark.parametrize('path,local', [
    ('proof/audit/run_transcripts.py', 'row'),
    ('proof/audit/live_reply_probe.py', 'current'),
])
@pytest.mark.parametrize('decision', ['reply_processing', 'reply_error_pending'])
def test_live_probe_verdict_predicates_are_pending_without_running_probes(path, local, decision):
    # Compile only the actual predicate. Never import these live scripts or
    # run their main(), credentials, mutations, providers or network calls.
    source = Path(__file__).resolve().parents[1] / path
    tree = ast.parse(source.read_text())
    test = next(node.test for node in ast.walk(tree) if isinstance(node, ast.If)
                and '"processing"' in ast.unparse(node.test).replace("'", '"')
                and '.get(' in ast.unparse(node.test) and 'not in' in ast.unparse(node.test))
    predicate = compile(ast.Expression(body=test), '<actual-probe-predicate>', 'eval')
    assert not eval(predicate, {local: {'decision': decision}, 'replies': [object()]})
    assert eval(predicate, {local: {'decision': 'chat'}, 'replies': [object()]})


def extracted_function(path, name, scope):
    tree = ast.parse((Path(__file__).resolve().parents[1] / path).read_text())
    node = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name)
    exec(compile(ast.Module(body=[node], type_ignores=[]), '<actual-reader-function>', 'exec'), scope)
    return scope[name]


def test_decision_measurement_query_excludes_recovery_without_loading_gate_env():
    observed = []
    def get(url, **kwargs):
        observed.append(kwargs['params'])
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {'items': []})
    reader = extracted_function('overnight/is_the_decision_bounded.py', 'decided_rows', {
        'requests': SimpleNamespace(get=get), 'headers': lambda:{}, 'PB': 'http://fixture', 'PAGE': 500})
    assert reader('2026-09-09 00:00:00') == []
    for decision in ('reply_processing', 'reply_error_pending'):
        assert f'decision != "{decision}"' in observed[0]['filter']


@pytest.mark.parametrize('decision', ['reply_processing', 'reply_error_pending'])
def test_legacy_verifier_cannot_call_recovery_success_without_running_live_script(decision):
    reports = []
    reader = extracted_function('proof/verify_all.py', 'check_brain_hears', {
        'create': lambda *args: {'id':'fixture'}, 'api': lambda *args:{'decision':decision},
        'time':SimpleNamespace(sleep=lambda _:None), 'report':lambda *args:reports.append(args)})
    assert reader() is None
    assert reports and reports[-1][1] is False
