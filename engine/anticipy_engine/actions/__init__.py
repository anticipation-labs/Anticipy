"""Room 9: the action layer.

Two adapter seams + a gate:
  - ConnectorAdapter: reach common apps through a THIRD-PARTY connector service
    (security-first, per-user-scoped). We do NOT hand-build integrations. Vendor
    is chosen/wired in the action chunk. Stub here.
  - BrowserAdapter: the browser fallback (wraps the browser engine later). Stub.
  - ActGate: the act-vs-ask gate. low -> act, needs_confirm -> confirm,
    ask_human -> escalate.
"""
from .layer import ActionLayer  # noqa: F401
from .gate import ActGate  # noqa: F401
from .connector import ConnectorAdapter  # noqa: F401
from .browser import BrowserAdapter  # noqa: F401
