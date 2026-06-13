"""Workers on the frozen contract.

The package contains both deterministic stubs and real mode-gated workers. The
ControlCore registers real workers last so memory, browser, API, text, and call
intents use the product path when configured, while tests can stay mock-safe.
"""
from .browser import BrowserStub  # noqa: F401
from .channel import ChannelStub, ChannelWorker  # noqa: F401
from .connector import ConnectorStub  # noqa: F401
from .memory import MemoryStub, MemoryWorker  # noqa: F401
from .scriptable import FAIL, NEEDS_HUMAN, SUCCESS, SUCCESS_NO_PROOF, ScriptableStub  # noqa: F401
