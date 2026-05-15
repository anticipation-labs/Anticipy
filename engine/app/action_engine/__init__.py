"""Action engine. Phase fara-3 onward: CDP dispatcher with humanlike
motion, refusal handling, coordinate cache."""

from .cdp_dispatcher import CDPSession, connect_to_chrome, RefusalSignal
from .humanlike import bezier_path, gaussian_delay

__all__ = [
    "CDPSession",
    "connect_to_chrome",
    "RefusalSignal",
    "bezier_path",
    "gaussian_delay",
]
