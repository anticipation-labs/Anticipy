"""Owner reply reaches the connection executor before generic interpretation."""
from types import SimpleNamespace
from unittest.mock import Mock
from brain import worker as W


def setup(monkeypatch, status=200, result=None):
    monkeypatch.setenv('ANTICIPY_SERVICE_TOKEN', 'fixture-service')
    response = SimpleNamespace(status_code=status, json=lambda: result or {
        'status': 'completed', 'outcome': {'kind': 'list_connections', 'replied': True, 'question': False}})
    post = Mock(return_value=response)
    monkeypatch.setattr(W.backend, 'post', post)
    return post


def test_uses_stored_identity_not_client_text(monkeypatch):
    post = setup(monkeypatch)
    assert W.connection_command({'id': 'event-1', 'text': 'untrusted duplicate'}, 'owner-1') == 'ignore'
    assert post.call_args.kwargs['json'] == {'event_id': 'event-1', 'owner_ref': 'owner-1'}


def test_pending_and_uncertain_delivery_wait_for_reconciliation(monkeypatch):
    setup(monkeypatch, 202)
    assert W.connection_command({'id': 'event-1'}, 'owner-1') == 'pending'
    setup(monkeypatch, result={'status': 'completed', 'outcome': {'kind': 'connect', 'replied': False}})
    assert W.connection_command({'id': 'event-1'}, 'owner-1') == 'pending'


def test_ordinary_conversation_remains_available(monkeypatch):
    setup(monkeypatch, result={'status': 'completed', 'outcome': {'kind': 'not_for_us', 'replied': False}})
    assert W.connection_command({'id': 'event-1'}, 'owner-1') == 'not_for_us'


def test_owned_message_is_not_interpreted_twice(monkeypatch):
    setup(monkeypatch)
    monkeypatch.setattr(W, 'claim', lambda _: True)
    marks = []
    monkeypatch.setattr(W, 'mark_processed', lambda eid, decision: marks.append((eid, decision)))
    convo = SimpleNamespace(on_reply=Mock(side_effect=AssertionError('duplicate interpretation')))
    owner = SimpleNamespace(owner_ref='owner-1', owner_phone='')
    event = {'id': 'event-1', 'owner_ref': 'owner-1', 'kind': 'app_reply', 'text': 'show connected apps'}
    assert W.handle_inbound(event, convo, owner) == 'ignore'
    assert marks == [('event-1', 'ignore')]
    assert not convo.on_reply.called


def test_pending_preserves_same_event_for_retry(monkeypatch):
    setup(monkeypatch, 202)
    monkeypatch.setattr(W, 'claim', lambda _: True)
    marks = []
    monkeypatch.setattr(W, 'mark_processed', lambda eid, decision: marks.append((eid, decision)))
    event = {'id': 'event-1', 'kind': 'app_reply', 'text': 'yes', 'owner_ref': 'owner-1'}
    assert W.handle_inbound(event, None, SimpleNamespace(owner_ref='owner-1', owner_phone='')) == 'unclaimed'
    assert marks == [('event-1', '')]
