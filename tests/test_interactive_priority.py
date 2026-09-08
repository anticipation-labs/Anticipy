"""Exercise the shipping poll order with a slow speech backlog and new replies."""
import ast
import inspect
import types

import pytest

from brain import worker as W


def hearing_and_reply_pass():
    """Compile the actual main-loop section, without starting providers/threads."""
    main = ast.parse(inspect.getsource(W.main)).body[0]
    loop = next(node for node in main.body if isinstance(node, ast.While))
    body = loop.body[0].body  # main's request/error boundary
    start = next(i for i, node in enumerate(body)
                 if isinstance(node, ast.Assign)
                 and any(isinstance(t, ast.Name) and t.id == 'turn_started' for t in node.targets))
    stop = next(i for i, node in enumerate(body[start:], start)
                if isinstance(node, ast.Try)
                and any(isinstance(n, ast.Attribute) and n.attr == 'sweep' for n in ast.walk(node)))
    return compile(ast.fix_missing_locations(ast.Module(body=body[start:stop], type_ignores=[])), '<shipping-hearing-pass>', 'exec')


def test_direct_answer_runs_before_backlog_and_between_speech_records(monkeypatch):
    clock = [0.0]
    inputs = [{'id': 'answer-before', 'kind': 'app_reply', 'owner_ref': 'owner-a'}]
    ambient = [{'id': str(i), 'source': 'phone_mic', 'text': 'fictional speech'} for i in range(20)]
    heard = []
    replies = []

    def fetch(kind='transcript', owner_ref=''):
        assert owner_ref == 'owner-a'
        return ambient if kind == 'transcript' else [e for e in inputs if e['kind'] == kind]

    def handle(ev, *args):
        replies.append((ev['id'], clock[0], len(heard)))
        inputs.remove(ev)

    def claim(event_id):
        # Simulate one in-flight speech operation. Its completion cannot be
        # interrupted; the next record must not leapfrog a newly arrived reply.
        clock[0] += 20
        heard.append(event_id)
        if len(heard) == 1:
            inputs.append({'id': 'answer-during', 'kind': 'sms_reply', 'owner_ref': 'owner-a'})
        return True

    monkeypatch.setattr(W, 'fetch_unprocessed', fetch)
    monkeypatch.setattr(W, 'handle_inbound', handle)
    monkeypatch.setattr(W, 'fetch_direct_inputs', lambda owner_ref: list(inputs), raising=False)
    monkeypatch.setattr(W, 'claim', claim)
    monkeypatch.setattr(W, 'mark_processed', lambda *a, **k: None)
    monkeypatch.setattr(W, 'meeting_heard', lambda *a: False)
    monkeypatch.setattr(W, 'is_echo_of_her', lambda *a, **k: True)
    monkeypatch.setattr(W, 'time', types.SimpleNamespace(monotonic=lambda:clock[0], time=lambda:clock[0]))
    scope = dict(vars(W), anticipy=types.SimpleNamespace(owner_ref='owner-a'), convo=object(), print=lambda *a:None)
    exec(hearing_and_reply_pass(), scope)
    assert replies == [('answer-before', 0.0, 0), ('answer-during', 20.0, 1)], replies
    assert len(heard) > 1  # Priority must not discard or permanently starve speech.


def test_direct_input_query_is_scoped_and_ordered_across_channels(monkeypatch):
    queries=[]
    class Response:
        def raise_for_status(self): pass
        def json(self):
            return {'items':[
                {'id':'sms','kind':'sms_reply','created':'2026-09-07T12:02:00Z'},
                {'id':'typed','kind':'transcript','source':'typed','created':'2026-09-07T12:01:00Z'},
                {'id':'app','kind':'app_reply','created':'2026-09-07T12:00:00Z'}]}
    def get(url, **kwargs):
        queries.append(kwargs['params']);return Response()
    monkeypatch.setattr(W.backend,'get',get)
    assert [e['id'] for e in W.fetch_direct_inputs('owner-a')] == ['app','typed','sms']
    expr=queries[0]['filter']
    assert 'owner_ref="owner-a"' in expr and 'decision=""' in expr
    for transport in ['sms_reply','app_reply','transcript','typed']:
        assert '"'+transport+'"' in expr


def test_direct_input_fetch_without_owner_performs_no_read(monkeypatch):
    monkeypatch.setattr(W.backend,'get',lambda *a,**k:pytest.fail('Unscoped read'))
    assert W.fetch_direct_inputs('') == []
