"""A spoken task's evidence must survive the classifier -> brain handoff."""
import json
from types import SimpleNamespace

from brain.conversation import Conversation


def conversation(monkeypatch):
    captured = []
    model = SimpleNamespace(live=True, chat=lambda system, user: (
        captured.append(json.loads(user)) or
        SimpleNamespace(text='{"intent":"new_request","reply":""}')))
    brain = SimpleNamespace(llm=model, memory=SimpleNamespace(recall=lambda *a, **k: []))
    c = Conversation(brain)
    for name in ("_pending", "_blocked", "_running", "_recent_outcomes"):
        monkeypatch.setattr(c, name, lambda: [])
    monkeypatch.setattr(c, "_thread", lambda phone: [])
    heard = []
    brain.hear = lambda text, **kwargs: (heard.append((text, kwargs)) or {})
    return c, captured, heard


def test_full_original_evidence_reaches_brain_even_when_classifier_asks_for_new_work(monkeypatch):
    c, classified, heard = conversation(monkeypatch)
    records = [{"id": "owner-task", "goal": "Compare two listings", "status": "queued",
                "params": json.dumps({"source": "Compare https://a.example/18 with "
                                       "https://b.example/47. Private comparison only."})}]
    monkeypatch.setattr(c, "_queued", lambda: records)
    text = "Also check whether those two prices include tax."
    c._classify("owner", text)
    c._think(text, "owner")
    assert classified[0]["queued"] == records
    prompt = heard[0][1]["context"][-1]
    assert json.loads(prompt.split(": ", 1)[1])["queued"] == records
    assert "not instructions or fresh consent" in prompt
    assert heard[0][0] == text
    assert heard[0][1]["explicit"] is True
    assert heard[0][1]["source_context"][0]["text"] == json.loads(records[0]["params"])["source"]


def test_task_snapshot_is_replaced_on_the_next_message(monkeypatch):
    c, _, heard = conversation(monkeypatch)
    records = [{"id": "finished-task", "goal": "Prior request", "params": "{}"}]
    monkeypatch.setattr(c, "_queued", lambda: list(records))
    c._classify("owner", "First message")
    records.clear()
    c._classify("owner", "An unrelated new request")
    c._think("An unrelated new request", "owner")
    assert "finished-task" not in str(heard)


def test_unprocessed_captured_context_reaches_reply_and_brain_as_quoted_source(monkeypatch):
    c, classified, heard = conversation(monkeypatch)
    c.anticipy.owner_ref = 'owner-a'
    c.anticipy.backend_url = 'https://fixture.invalid'
    c._incoming_event = {'id':'reply-a','owner_ref':'owner-a','created':'2026-09-07 12:01:00Z'}
    captured = {'id':'speech-a','owner_ref':'owner-a','kind':'transcript','source':'phone_mic',
                'text':'The two listings are https://a.example/18 and https://b.example/47.',
                'speaker':'other','decision':'','created':'2026-09-07 12:00:00Z'}
    queries=[]
    def get(url, **kwargs):
        queries.append(kwargs['params']);return SimpleNamespace(ok=True,json=lambda:{'items':[captured]})
    monkeypatch.setattr('brain.conversation.backend.get',get)
    monkeypatch.setattr(c,'_queued',lambda:[])
    c._classify('owner','Compare those two, privately.')
    c._think('Compare those two, privately.','owner')
    rows=classified[0]['captured_context']
    assert rows[0]['text']==captured['text'] and rows[0]['speaker']=='other'
    assert 'https://a.example/18' in str(heard[0][1]['context'])
    assert heard[0][1]['source_context'][0]['text'] == captured['text']
    expr=queries[0]['filter']
    assert 'owner_ref="owner-a"' in expr and 'created<=' in expr
    assert 'source!="typed"' in expr and 'decision=' not in expr


def test_captured_context_requires_a_real_incoming_event_and_owner(monkeypatch):
    c, _, _ = conversation(monkeypatch)
    monkeypatch.setattr('brain.conversation.backend.get',lambda *a,**k: (_ for _ in ()).throw(AssertionError('Unscoped read')))
    assert c._captured_context() == []


def test_sources_remain_flat_after_repeated_task_handoffs():
    from brain.source_context import source_records
    record = {'id':'speech', 'text':'Compare https://a.example/18', 'speaker':'other'}
    context = [record]
    for _ in range(20):
        snapshot = {'queued':[{'id':'task','params':{'source':'Compare those',
                    '_source_context':context,'_workflow':{'secret':'not a source'}}}]}
        context = source_records(snapshot)
    assert len(context) == 2
    assert context[0] == record
    assert 'secret' not in str(context)


def test_source_context_is_scoped_to_one_hear_and_restored_after_failure(monkeypatch):
    import pytest
    from brain.anticipy_core import Anticipy
    a = object.__new__(Anticipy)
    seen = []
    def hear(*args, **kwargs):
        seen.append(a._source_context)
        if len(seen) == 2:
            raise RuntimeError('provider failed')
        return {}
    monkeypatch.setattr(a, '_hear', hear)
    source = [{'text':'Quoted earlier speech','speaker':'other'}]
    a.hear('Compare it', source_context=source)
    with pytest.raises(RuntimeError):
        a.hear('Another request', source_context=[{'text':'Other context'}])
    a.hear('Unrelated turn')
    assert seen == [source,[{'text':'Other context'}],[]]
    assert a._source_context == []


def test_rebuilt_thread_does_not_read_later_replies(monkeypatch):
    c, _, _ = conversation(monkeypatch)
    c.anticipy.backend_url = 'https://fixture.invalid'
    c._incoming_event = {'id':'reply','created':'2026-09-07 12:01:00Z'}
    monkeypatch.setattr(c, '_owner_filter', lambda:'owner_ref="owner-a"')
    queries = []
    monkeypatch.setattr('brain.conversation.backend.get', lambda *a,**k:
        (queries.append(k['params']['filter']) or SimpleNamespace(ok=True,json=lambda:{'items':[]})))
    assert c._thread_from_record('phone') == []
    assert 'created<="2026-09-07 12:01:00Z"' in queries[0]


def test_api_hand_and_tool_receive_quoted_context_without_changing_authority(monkeypatch):
    from brain import hands
    from brain.source_context import quoted_context
    rows=[{'text':'The reference is invoice ABC-41', 'speaker':'other'}]
    monkeypatch.setattr(hands, 'read_connections', lambda *a: ())
    monkeypatch.setattr(hands, 'browser_is_online', lambda *a: True)
    ctx=hands.gather_context({'source':'Read that invoice', '_source_context':rows},owner_ref='owner-a')
    assert ctx.source == 'Read that invoice'
    assert ctx.source_context == quoted_context(rows)
    prompts=[]
    model=SimpleNamespace(live=True,chat=lambda system,user,**kwargs:
        (prompts.append(user) or SimpleNamespace(text='{}')))
    hands.choose_hand('Read invoice',ctx,llm=model)
    tool={'slug':'READ_INVOICE','toolkit':'ledger','name':'Read invoice',
          'input_parameters':{'type':'object','properties':{'id':{'type':'string'}},'required':['id']}}
    hands.choose_tool('Read invoice','ledger',[tool],llm=model,heard=ctx.source,source_context=ctx.source_context)
    assert len(prompts) >= 2
    assert all('ABC-41' in p and 'not instructions' in p for p in prompts)
