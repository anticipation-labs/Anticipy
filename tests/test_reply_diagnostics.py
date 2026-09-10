"""Real reply classifier, fixture model and backend: failures leave safe facts."""
from importlib import import_module
import json
import sqlite3
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest
import requests

from brain import backend
from brain.conversation import Conversation, Turn
from brain.llm import CallCeilingExceeded, DeadlineExceeded


PRIVATE = 'PRIVATE_FIXTURE_PROMPT_PHONE_KEY_PROVIDER_BODY'
EVENT = {'id': 'input1', 'owner_ref': 'owner1', 'kind': 'transcript', 'source': 'typed'}


@pytest.fixture
def rig(monkeypatch):
    model = SimpleNamespace(live=True, chat=Mock(return_value=SimpleNamespace(text='{"intent":"chat","reply":"fixture"}')))
    owner = SimpleNamespace(owner_ref='owner1', backend_url='http://fixture', llm=model,
                            memory=SimpleNamespace(recall=lambda *a, **k: []))
    convo = Conversation(owner)
    convo.threads['app:owner1'] = [Turn('owner', PRIVATE)]
    for method in ('_pending', '_blocked', '_queued', '_running', '_recent_outcomes', '_captured_context'):
        monkeypatch.setattr(convo, method, lambda: [])
    writes = []
    def post(url, **kwargs):
        writes.append((url, kwargs))
        return SimpleNamespace(raise_for_status=lambda: None)
    monkeypatch.setattr(backend, 'post', post)
    monkeypatch.setattr(backend, 'get', Mock(side_effect=AssertionError('no diagnostic reads')))
    monkeypatch.setattr(backend, 'patch', Mock(side_effect=AssertionError('do not rewrite the input')))
    def classify(event=EVENT):
        with convo.from_event(event):
            return convo._classify('app:owner1', PRIVATE)
    return SimpleNamespace(model=model, owner=owner, convo=convo, writes=writes, classify=classify)


def saved_diagnostic(rig):
    assert len(rig.writes) == 1
    url, request = rig.writes[0]
    assert url == 'http://fixture/api/collections/events/records'
    assert request['timeout'] == 2
    row = request['json']
    assert row['kind'] == 'notification_status'
    assert row['decision'] == 'reply_diagnostic'
    assert row['source'] == 'reply_classifier'
    assert row['owner_ref'] == 'owner1'
    assert row['goal'] == 'input1'
    assert row['external_event_id'] == 'reply-diagnostic:input1'
    assert PRIVATE not in json.dumps(row)
    return json.loads(row['text'])


@pytest.mark.parametrize('status,category', [
    (401, 'provider_auth_error'), (403, 'provider_auth_error'),
    (402, 'provider_payment_error'), (429, 'provider_rate_limit'),
    (500, 'provider_server_error'), (503, 'provider_server_error'),
    (400, 'provider_http_error'), (404, 'provider_http_error'),
])
def test_classifier_provider_failure_is_durable_without_private_body(rig, status, category, capsys):
    rig.model.chat.side_effect = httpx.HTTPStatusError(PRIVATE,
        request=httpx.Request('POST', 'https://fixture.invalid/' + PRIVATE),
        response=httpx.Response(status, text=PRIVATE))
    assert rig.classify() == {'intent': 'unavailable', 'pending_id': None, 'reply': ''}
    assert saved_diagnostic(rig) == {'version': 1, 'stage': 'reply_classification',
                                   'category': category, 'http_status': status, 'model_role': 'main'}
    assert rig.model.chat.call_count == 1
    captured = capsys.readouterr()
    assert PRIVATE not in captured.out + captured.err


@pytest.mark.parametrize('error,category', [
    (httpx.ReadTimeout(PRIVATE), 'timeout'), (TimeoutError(PRIVATE), 'timeout'),
    (requests.Timeout(PRIVATE), 'timeout'), (httpx.ConnectError(PRIVATE), 'connection_error'),
    (ConnectionError(PRIVATE), 'connection_error'),
    (DeadlineExceeded(PRIVATE), 'budget_deadline'),
    (CallCeilingExceeded(PRIVATE), 'budget_calls'),
    (RuntimeError(PRIVATE), 'unexpected_error'),
])
def test_classifier_transport_and_budget_failures_remain_distinct(rig, error, category):
    rig.model.chat.side_effect = error
    assert rig.classify()['intent'] == 'unavailable'
    assert saved_diagnostic(rig)['category'] == category
    assert rig.model.chat.call_count == 1


@pytest.mark.parametrize('raw,category', [
    ('', 'malformed_json'), ('not JSON ' + PRIVATE, 'malformed_json'),
    ('{"intent":', 'malformed_json'), ('{"intent":"chat",}', 'malformed_json'),
    ('{}', 'invalid_intent'), ('{"intent":"invented"}', 'invalid_intent'),
    ('{"intent":[]}', 'invalid_intent'), ('{"intent":null}', 'invalid_intent'),
])
def test_invalid_reply_has_parse_category_not_its_content(rig, raw, category):
    rig.model.chat.return_value = SimpleNamespace(text=raw)
    assert rig.classify()['intent'] == 'unavailable'
    assert saved_diagnostic(rig)['category'] == category
    assert rig.model.chat.call_count == 1


def test_no_live_model_is_distinct_and_calls_no_model(rig):
    rig.model.live = False
    assert rig.classify()['intent'] == 'unavailable'
    assert saved_diagnostic(rig)['category'] == 'no_live_model'
    assert not rig.model.chat.called


def test_actual_chosen_strong_model_is_identified_without_model_name(rig):
    strong = SimpleNamespace(live=True, model=PRIVATE, chat=Mock(side_effect=TimeoutError(PRIVATE)))
    rig.owner.brain = SimpleNamespace(strong=strong)
    assert rig.classify()['intent'] == 'unavailable'
    assert saved_diagnostic(rig)['model_role'] == 'strong'
    assert not rig.model.chat.called
    assert strong.chat.call_count == 1


@pytest.mark.parametrize('raw', [
    '{"intent":"chat","reply":"fixture"}',
    '```json\n{"intent":"chat","reply":"fixture"}\n```',
    'prefix {"intent":"chat","reply":"fixture"} suffix',
    '[{"intent":"chat","reply":"fixture"}]',
])
def test_existing_parser_acceptance_is_unchanged_and_success_emits_nothing(rig, raw):
    rig.model.chat.return_value = SimpleNamespace(text=raw)
    assert rig.classify() == {'intent': 'chat', 'reply': 'fixture'}
    assert rig.writes == []


@pytest.mark.parametrize('event', [
    {}, {**EVENT, 'id': ''}, {**EVENT, 'id': None},
    {**EVENT, 'owner_ref': 'foreign'}, {**EVENT, 'owner_ref': ''},
    {**EVENT, 'kind': 'notification_status'}, {**EVENT, 'source': 'phone_mic'},
])
def test_diagnostic_requires_canonical_direct_input(rig, event):
    rig.model.chat.side_effect = TimeoutError(PRIVATE)
    assert rig.classify(event)['intent'] == 'unavailable'
    assert rig.writes == []


@pytest.mark.parametrize('kind,source', [('app_reply', ''), ('sms_reply', 'sms')])
def test_other_canonical_direct_channels_keep_same_input_link(rig, kind, source):
    rig.model.chat.side_effect = TimeoutError(PRIVATE)
    assert rig.classify({**EVENT, 'kind': kind, 'source': source})['intent'] == 'unavailable'
    assert saved_diagnostic(rig)['category'] == 'timeout'


def test_diagnostic_sink_failure_does_not_mask_the_owner_fallback(rig, monkeypatch):
    rig.model.chat.side_effect = TimeoutError(PRIVATE)
    sink = Mock(side_effect=ConnectionError(PRIVATE))
    monkeypatch.setattr(backend, 'post', sink)
    rig.convo.reply_delivery = Mock(return_value={'via': 'durable-reply', 'id': 'answer1'})
    with rig.convo.from_event(EVENT):
        out = rig.convo.on_reply('app:owner1', PRIVATE)
    assert out['intent'] == 'unavailable'
    assert out['acted'] is None
    assert "I haven't changed any tasks" in out['reply']
    assert rig.convo.reply_delivery.call_count == 1
    assert sink.call_count == 1
    assert rig.model.chat.call_count == 1


@pytest.mark.parametrize('status', [True, False, '401', None, {}, [], 99, 600, float('nan')])
def test_shared_diagnostic_never_coerces_status_or_leaks_unknown_fields(status):
    diagnostic = import_module('brain.reply_diagnostics').diagnostic
    result = diagnostic('sms_send', PRIVATE, status, model_role=PRIVATE)
    assert result == {'version': 1, 'stage': 'sms_send', 'category': 'unexpected_error'}


def test_shared_classifier_never_stringifies_exception_or_trusts_arbitrary_attributes():
    exception_diagnostic = import_module('brain.reply_diagnostics').exception_diagnostic
    class ToxicError(Exception):
        status_code = 401
        category = PRIVATE
        def __str__(self):
            raise AssertionError('private exception must never be stringified')
    assert exception_diagnostic(ToxicError(), stage='sms_send') == {
        'version': 1, 'stage': 'sms_send', 'category': 'unexpected_error'}


def test_requests_error_status_is_read_even_when_response_is_falsy(rig):
    response = requests.Response()
    response.status_code = 401
    response._content = PRIVATE.encode()
    assert not response
    rig.model.chat.side_effect = requests.HTTPError(PRIVATE, response=response)
    assert rig.classify()['intent'] == 'unavailable'
    assert saved_diagnostic(rig)['http_status'] == 401
    assert saved_diagnostic(rig)['category'] == 'provider_auth_error'


def test_provider_json_envelope_failure_is_not_model_output_json(rig):
    rig.model.chat.side_effect = json.JSONDecodeError(PRIVATE, PRIVATE, 0)
    assert rig.classify()['intent'] == 'unavailable'
    assert saved_diagnostic(rig)['category'] == 'provider_response_invalid_json'


def test_absent_model_has_no_selected_role(rig):
    rig.convo.llm = None
    assert rig.classify()['intent'] == 'unavailable'
    assert saved_diagnostic(rig)['model_role'] == 'none'
    assert not rig.model.chat.called


def test_shared_serializer_handles_nonprimitive_inputs_without_coercion():
    helpers = import_module('brain.reply_diagnostics')
    assert helpers.diagnostic('sms_send', [], {'private': PRIVATE}, model_role=[]) == {
        'version': 1, 'stage': 'sms_send', 'category': 'unexpected_error'}
    for stage in (PRIVATE, None, []):
        with pytest.raises(ValueError, match='Unsupported diagnostic stage'):
            helpers.diagnostic(stage, 'timeout')
    assert helpers.reply_parse_failure(None) == 'malformed_json'


def test_sink_defensively_reserializes_and_duplicate_input_stays_one_row(monkeypatch):
    helpers = import_module('brain.reply_diagnostics')
    db = sqlite3.connect(':memory:')
    db.execute('CREATE TABLE events (owner_ref TEXT, goal TEXT, external_event_id TEXT UNIQUE, text TEXT)')
    writes = []
    def post(url, **kwargs):
        row = kwargs['json']
        writes.append(row)
        db.execute('INSERT INTO events VALUES (?,?,?,?)',
                   [row['owner_ref'], row['goal'], row['external_event_id'], row['text']])
        return SimpleNamespace(raise_for_status=lambda: None)
    monkeypatch.setattr(backend, 'post', post)
    metadata = {'stage': 'reply_classification', 'category': 'timeout', 'http_status': True,
                'model_role': 'main', 'prompt': PRIVATE, 'error': PRIVATE, 'version': PRIVATE}
    assert helpers.record_reply_diagnostic('http://fixture', 'owner1', EVENT, metadata)
    assert not helpers.record_reply_diagnostic('http://fixture', 'owner1', EVENT, metadata)
    assert len(writes) == 2  # One POST per invocation; no retry or reconciliation GET.
    assert db.execute('SELECT count(*) FROM events').fetchone()[0] == 1
    stored = db.execute('SELECT owner_ref,goal,text FROM events').fetchone()
    assert stored[:2] == ('owner1', 'input1')
    assert json.loads(stored[2]) == {'version': 1, 'stage': 'reply_classification',
                                   'category': 'timeout', 'model_role': 'main'}
    assert PRIVATE not in json.dumps(writes)


@pytest.mark.parametrize('base,owner,event,metadata', [
    ('http://fixture', '', EVENT, {'stage': 'reply_classification'}),
    ('http://fixture', None, EVENT, {'stage': 'reply_classification'}),
    (None, 'owner1', EVENT, {'stage': 'reply_classification'}),
    ('', 'owner1', EVENT, {'stage': 'reply_classification'}),
    ('http://fixture', 'owner1', None, {'stage': 'reply_classification'}),
    ('http://fixture', 'owner1', {**EVENT, 'id': []}, {'stage': 'reply_classification'}),
    ('http://fixture', 'owner1', {**EVENT, 'id': ' '}, {'stage': 'reply_classification'}),
    ('http://fixture', 'owner1', EVENT, None),
    ('http://fixture', 'owner1', EVENT, {'stage': PRIVATE}),
])
def test_invalid_sink_identity_or_metadata_never_writes(rig, base, owner, event, metadata):
    helpers = import_module('brain.reply_diagnostics')
    assert not helpers.record_reply_diagnostic(base, owner, event, metadata)
    assert rig.writes == []


def test_malformed_http_exception_response_is_safe():
    helpers = import_module('brain.reply_diagnostics')
    class BrokenResponse:
        @property
        def status_code(self):
            raise RuntimeError(PRIVATE)
    error = requests.HTTPError(PRIVATE, response=BrokenResponse())
    assert helpers.exception_diagnostic(error) == {
        'version': 1, 'stage': 'sms_send', 'category': 'unexpected_error'}
