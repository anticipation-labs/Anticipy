"""A texted answer to a PARKED job must keep the plan blob.

The failure this pins: _blocked() built its pool entries without `params`,
_open_work() copied them through, and _amend()'s single-candidate fallback
therefore rebuilt the record with params={} — dropping params._workflow. The
backend guard rejects a write that drops the plan, so every SMS answer to a
parked job came back "Hit a snag updating that on my end" and the job never
moved. Contract: the pools agree on their shape.
"""
import inspect
from brain import conversation


def _pool_keys(fn_name):
    src = inspect.getsource(getattr(conversation.Conversation, fn_name))
    return {"params": '"params"' in src, "status": '"status"' in src}


def test_every_pool_carries_params_and_status():
    for name in ("_blocked", "_pending", "_queued"):
        keys = _pool_keys(name)
        assert keys["params"], f"{name}() drops params -> _amend loses _workflow"
        assert keys["status"], f"{name}() drops status -> _amend misreads the gate"


def test_open_work_copies_params_through():
    src = inspect.getsource(conversation.Conversation._open_work)
    assert 'job.get("params"' in src
