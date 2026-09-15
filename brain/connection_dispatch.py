"""Keep one connection HTTP request off an owner's serial reasoning loop.

The API keeps the request open until its durable event-based dispatch settles.
There is no detached Worker waitUntil task and no unbounded local work queue.
Only transport runs in the thread; Python conversation/memory never enter it.
"""
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from threading import Lock


class ConnectionDispatch:
    def __init__(self, retained_results=16):
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="connection-http")
        self._lock = Lock()
        self._active = None
        self._completed = OrderedDict()
        self._retained_results = retained_results

    def poll(self, key, request):
        with self._lock:
            if self._active is not None and self._active[1].done():
                finished_key, future = self._active
                self._active = None
                try:
                    result = future.result()
                except Exception:
                    # The request function catches its own transport errors;
                    # a throw here is a defect in the thread itself, and the
                    # honest answer is "no verdict yet", never "unreachable".
                    result = "pending"
                self._completed[finished_key] = result
                # Eviction loses only a read cache. The API's event id and
                # durable execution fence still prevent duplicate effects.
                while len(self._completed) > self._retained_results:
                    self._completed.popitem(last=False)
            if key in self._completed:
                return self._completed.pop(key)
            if self._active is None:
                self._active = (key, self._executor.submit(request))
            # Our own transport thread still holds (or is queued for) this
            # request. That is a state of THIS process, not the API's verdict:
            # "pending" is reserved for the API saying another holder's lease
            # is live, so the caller can bound one without ever parking the
            # other (2026-09-14, the silent recycle).
            return "in_flight"

    def close(self):
        self._executor.shutdown(wait=True, cancel_futures=True)
