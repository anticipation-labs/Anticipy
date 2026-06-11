"""Stub workers — the fakes the brain runs against. All hit the frozen contract."""
from .browser import BrowserStub  # noqa: F401
from .channel import ChannelStub, ChannelWorker  # noqa: F401
from .connector import ConnectorStub  # noqa: F401
from .memory import MemoryStub, MemoryWorker  # noqa: F401
from .scriptable import FAIL, NEEDS_HUMAN, SUCCESS, SUCCESS_NO_PROOF, ScriptableStub  # noqa: F401
