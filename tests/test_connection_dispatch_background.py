"""Slow connection I/O cannot occupy the serial owner loop or duplicate a request."""
import threading
from concurrent.futures import ThreadPoolExecutor

from brain.connection_dispatch import ConnectionDispatch


def test_slow_http_returns_pending_and_never_queues_parallel_requests():
    entered, release = threading.Event(), threading.Event()
    calls = []
    dispatcher = ConnectionDispatch()
    def slow_request():
        calls.append('first')
        entered.set()
        assert release.wait(2)
        return 'ignore'
    try:
        assert dispatcher.poll(('backend', 'owner', 'first'), slow_request) == 'pending'
        assert entered.wait(1)
        # These all return before the first HTTP request is allowed to finish.
        with ThreadPoolExecutor(max_workers=4) as callers:
            pending = list(callers.map(lambda i: dispatcher.poll(
                ('backend', 'owner', f'other-{i}'), lambda: calls.append('unexpected')), range(20)))
        assert pending == ['pending'] * 20
        assert calls == ['first']
        assert dispatcher.poll(('backend', 'owner', 'first'), slow_request) == 'pending'
        release.set()
        dispatcher._active[1].result(timeout=1)
        assert dispatcher.poll(('backend', 'owner', 'first'), slow_request) == 'ignore'
        assert calls == ['first']
    finally:
        release.set()
        dispatcher.close()


def test_completed_reply_keeps_backend_owner_and_event_identity():
    dispatcher = ConnectionDispatch()
    release = threading.Event()
    try:
        owner_a = ('backend', 'owner-a', 'same-event')
        owner_b = ('backend', 'owner-b', 'same-event')
        dispatcher.poll(owner_a, lambda: 'ask')
        dispatcher._active[1].result(timeout=1)
        assert dispatcher.poll(owner_b, lambda: release.wait(1) and 'ignore') == 'pending'
        assert dispatcher.poll(owner_a, lambda: 'WRONG') == 'ask'
        release.set()
        dispatcher._active[1].result(timeout=1)
        assert dispatcher.poll(owner_b, lambda: 'WRONG') == 'ignore'
    finally:
        release.set()
        dispatcher.close()


def test_failed_request_is_pending_and_can_be_reconciled_without_a_poisoned_future():
    dispatcher = ConnectionDispatch()
    key = ('backend', 'owner', 'event')
    def failed():
        raise TimeoutError()
    try:
        dispatcher.poll(key, failed)
        future = dispatcher._active[1]
        try:
            future.result(timeout=1)
        except TimeoutError:
            pass
        assert dispatcher.poll(key, failed) == 'pending'
        dispatcher.poll(key, lambda: 'ignore')
        dispatcher._active[1].result(timeout=1)
        assert dispatcher.poll(key, lambda: 'WRONG') == 'ignore'
    finally:
        dispatcher.close()


def test_orphaned_completed_results_cannot_grow_memory_without_bound():
    dispatcher = ConnectionDispatch(retained_results=4)
    try:
        # The parent may stop polling an event after ingress marks it handled.
        # Each next input harvests the previous completion without consuming it.
        for i in range(20):
            assert dispatcher.poll(('backend', 'owner', str(i)), lambda: 'ignore') == 'pending'
            dispatcher._active[1].result(timeout=1)
        assert len(dispatcher._completed) == 4
        assert ('backend', 'owner', '0') not in dispatcher._completed
    finally:
        dispatcher.close()
