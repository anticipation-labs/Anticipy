"""Owner reply reaches the connection executor before generic interpretation."""
import contextlib
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from brain import worker as W
from brain.connection_dispatch import ConnectionDispatch


@pytest.fixture(autouse=True)
def own_dispatcher(monkeypatch):
    dispatcher = ConnectionDispatch()
    monkeypatch.setattr(W, '_CONNECTION_DISPATCH', dispatcher)
    yield dispatcher
    dispatcher.close()


def settled(event, owner):
    # The first call only submits the transport request; that is "in_flight",
    # not the API's "pending" verdict (a live lease elsewhere).
    assert W.connection_command(event, owner) == 'in_flight'
    W._CONNECTION_DISPATCH._active[1].result(timeout=2)
    return W.connection_command(event, owner)


def setup(monkeypatch, status=200, result=None):
    monkeypatch.setenv('ANTICIPY_SERVICE_TOKEN', 'fixture-service')
    response = SimpleNamespace(status_code=status, json=lambda: result or {
        'status': 'completed', 'outcome': {'kind': 'list_connections', 'replied': True, 'question': False}})
    post = Mock(return_value=response)
    monkeypatch.setattr(W.backend, 'post', post)
    return post


def test_uses_stored_identity_not_client_text(monkeypatch):
    post = setup(monkeypatch)
    assert settled({'id': 'event-1', 'text': 'untrusted duplicate'}, 'owner-1') == 'ignore'
    assert post.call_args.kwargs['json'] == {'event_id': 'event-1', 'owner_ref': 'owner-1'}
    assert post.call_args.kwargs['timeout'] == 120


def test_pending_and_uncertain_delivery_wait_for_reconciliation(monkeypatch):
    setup(monkeypatch, 202)
    assert settled({'id': 'event-1'}, 'owner-1') == 'pending'
    setup(monkeypatch, result={'status': 'completed', 'outcome': {'kind': 'connect', 'replied': False}})
    assert settled({'id': 'event-1'}, 'owner-1') == 'pending'


def test_ordinary_conversation_remains_available(monkeypatch):
    setup(monkeypatch, result={'status': 'completed', 'outcome': {'kind': 'not_for_us', 'replied': False}})
    assert settled({'id': 'event-1'}, 'owner-1') == 'not_for_us'


def test_owned_message_is_not_interpreted_twice(monkeypatch):
    setup(monkeypatch)
    monkeypatch.setattr(W, 'claim', lambda _: True)
    marks = []
    monkeypatch.setattr(W, 'mark_processed', lambda eid, decision: marks.append((eid, decision)))
    convo = SimpleNamespace(on_reply=Mock(side_effect=AssertionError('duplicate interpretation')))
    owner = SimpleNamespace(owner_ref='owner-1', owner_phone='')
    event = {'id': 'event-1', 'owner_ref': 'owner-1', 'kind': 'app_reply', 'text': 'show connected apps'}
    assert W.handle_inbound(event, convo, owner) == 'unclaimed'
    assert marks == [('event-1', '')]
    W._CONNECTION_DISPATCH._active[1].result(timeout=2)
    assert W.handle_inbound(event, convo, owner) == 'ignore'
    assert marks == [('event-1', ''), ('event-1', 'ignore')]
    assert not convo.on_reply.called


def test_pending_preserves_same_event_for_retry(monkeypatch):
    setup(monkeypatch, 202)
    monkeypatch.setattr(W, 'claim', lambda _: True)
    marks = []
    monkeypatch.setattr(W, 'mark_processed', lambda eid, decision: marks.append((eid, decision)))
    event = {'id': 'event-1', 'kind': 'app_reply', 'text': 'yes', 'owner_ref': 'owner-1'}
    assert W.handle_inbound(event, None, SimpleNamespace(owner_ref='owner-1', owner_phone='')) == 'unclaimed'
    assert marks == [('event-1', '')]


# ---------------------------------------------------------------------------
# THE BOUNDED RECYCLE (2026-09-14). A 202 from /worker/connection-command
# means another holder's lease is live; a 503 or an exception means the route
# is unreachable. Until this date both recycled the reply every two seconds
# forever, with no log line and no answer — silence by construction. The bound
# is two dispatch.ts leases (LEASE_MS = 300_000) measured from the row's own
# `created`, so a restart cannot reset it and a live lease is never
# double-answered.
# ---------------------------------------------------------------------------
def _event(age_seconds, text='show connected apps'):
    created = (datetime.now(timezone.utc) - timedelta(seconds=age_seconds)).isoformat()
    return {'id': 'event-1', 'owner_ref': 'owner-1', 'kind': 'app_reply', 'text': text, 'created': created}


def _harness(monkeypatch, status, on_reply=None):
    setup(monkeypatch, status)
    monkeypatch.setattr(W, 'claim', lambda _: True)
    marks, diagnostics = [], []
    monkeypatch.setattr(W, 'mark_processed', lambda eid, decision, *a, **k: marks.append((eid, decision)) or True)
    monkeypatch.setattr(W, 'record_reply_diagnostic',
                        lambda base, owner, ev, meta: diagnostics.append(meta) or True, raising=False)
    monkeypatch.setattr(W, 'post_event', lambda *a, **k: None, raising=False)
    monkeypatch.setattr(W, '_CONNECTION_RECYCLES', {}, raising=False)
    convo = SimpleNamespace(
        on_reply=on_reply or Mock(side_effect=AssertionError('a live connection lease must never reach reasoning')),
        reply_in_app=lambda: contextlib.nullcontext())
    owner = SimpleNamespace(owner_ref='owner-1', owner_phone='')
    return marks, diagnostics, convo, owner


def _settle():
    W._CONNECTION_DISPATCH._active[1].result(timeout=2)


def _round(event, convo, owner):
    """One full poll cycle: submit the request, let it land, read the verdict.

    poll() answers 'in_flight' on the call that submits and returns the API's
    verdict on the next one, so a test that wants N verdicts must drive 2N
    calls. Doing that by hand is how the first draft of these cases silently
    asserted on the in-flight answer instead of the verdict.
    """
    assert W.handle_inbound(event, convo, owner) == 'unclaimed'
    _settle()
    return W.handle_inbound(event, convo, owner)


def test_pending_lease_parks_after_two_lease_lengths_never_reasoning(monkeypatch):
    marks, diagnostics, convo, owner = _harness(monkeypatch, 202)
    young = _event(5)
    assert _round(young, convo, owner) == 'unclaimed'                # pending, not aged
    assert marks == [('event-1', ''), ('event-1', '')]
    assert diagnostics == []
    old = _event(W.CONNECTION_COMMAND_PARK_AFTER_SECONDS + 1)
    assert _round(old, convo, owner) == 'reply_error_pending'        # watched twice now
    assert marks[-1] == ('event-1', 'reply_error_pending')
    assert diagnostics == [{'stage': 'reply_classification', 'category': 'connection_command_pending'}]
    assert not convo.on_reply.called


def test_an_old_row_is_never_parked_on_its_first_verdict(monkeypatch):
    """A restart, a backlog or a late pickup must not park a fresh live lease.

    The row's own age is durable across restarts, which is why the bound is
    measured from `created` -- but on its own it would park a row the brain has
    never actually watched stall, and a lease that is seconds old is exactly
    the one about to answer.
    """
    marks, diagnostics, convo, owner = _harness(monkeypatch, 202)
    old = _event(W.CONNECTION_COMMAND_PARK_AFTER_SECONDS * 10)
    assert _round(old, convo, owner) == 'unclaimed'
    assert diagnostics == [], 'an unwatched row was parked on its first verdict'
    assert _round(old, convo, owner) == 'reply_error_pending'
    assert diagnostics == [{'stage': 'reply_classification', 'category': 'connection_command_pending'}]
    assert not convo.on_reply.called


def test_an_unreachable_route_parks_too_and_never_reaches_reasoning(monkeypatch):
    """"unreachable" covers a read timeout on a POST the API received, and the
    API answers 503 in states reached AFTER the plan has run. Releasing that to
    reasoning is the double answer its execution fence exists to prevent."""
    marks, diagnostics, convo, owner = _harness(monkeypatch, 503)
    young = _event(5)
    assert _round(young, convo, owner) == 'unclaimed'                # not aged: recycled
    old = _event(W.CONNECTION_COMMAND_PARK_AFTER_SECONDS + 1)
    assert _round(old, convo, owner) == 'reply_error_pending'
    assert marks[-1] == ('event-1', 'reply_error_pending')
    assert diagnostics == [{'stage': 'reply_classification',
                            'category': 'connection_command_unreachable'}]
    assert not convo.on_reply.called


def test_a_created_ahead_of_our_clock_still_ages_out(monkeypatch):
    """A stamp from a host running ahead is an unusable stamp, not a young row.
    Clamping it to zero would hold the row below the bound for as long as the
    skew lasts -- which is the silence the bound exists to end."""
    marks, diagnostics, convo, owner = _harness(monkeypatch, 202)
    future = _event(-(W.CLOCK_SKEW_MAX_S + 60))
    outcome, rounds = None, 0
    for _ in range(W.CONNECTION_COMMAND_RECYCLE_BACKSTOP + 2):
        rounds += 1
        outcome = _round(future, convo, owner)
        if outcome != 'unclaimed':
            break
    assert outcome == 'reply_error_pending', 'an unreadable stamp recycled past its backstop'
    # It must reach the owner through the TRY backstop, not by being read as an
    # aged row: a stamp we cannot trust is not evidence that ten minutes passed.
    assert rounds > 2, 'a future stamp was treated as an aged row'
    assert diagnostics == [{'stage': 'reply_classification',
                            'category': 'connection_command_pending'}]
    assert marks[-1] == ('event-1', 'reply_error_pending')


def test_in_flight_request_never_parks_even_when_aged_out(monkeypatch):
    marks, diagnostics, convo, owner = _harness(monkeypatch, 202)
    old = _event(W.CONNECTION_COMMAND_PARK_AFTER_SECONDS + 1)
    assert W.handle_inbound(old, convo, owner) == 'unclaimed'
    assert marks == [('event-1', '')]
    assert diagnostics == []
    _settle()


def test_diagnostic_vocabulary_knows_the_connection_command_categories():
    from brain.reply_diagnostics import diagnostic
    for category in ('connection_command_pending', 'connection_command_unreachable'):
        assert diagnostic('reply_classification', category)['category'] == category


def test_park_bound_is_two_dispatch_leases():
    """dispatch.ts LEASE_MS and this bound must not drift apart silently."""
    import re
    from pathlib import Path
    source = Path(__file__).resolve().parents[1] / 'migration/workers/src/connections/dispatch.ts'
    lease_ms = int(re.search(r'const LEASE_MS = ([0-9_]+)', source.read_text()).group(1).replace('_', ''))
    assert W.CONNECTION_COMMAND_PARK_AFTER_SECONDS == 2 * lease_ms // 1000
