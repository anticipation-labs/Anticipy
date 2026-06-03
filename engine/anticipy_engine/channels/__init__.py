"""Room 10: the channels seam.

How the engine reaches the user: ``call`` (voice), ``text`` (SMS), ``app``
(in-app). All stubbed — no real sending in the scaffold. Twilio/app delivery is
wired in a later chunk behind these same seams.
"""
from .base import Channel  # noqa: F401
from .call import CallChannel  # noqa: F401
from .text import TextChannel  # noqa: F401
from .app import AppChannel  # noqa: F401


class Channels:
    def __init__(self) -> None:
        self.call = CallChannel()
        self.text = TextChannel()
        self.app = AppChannel()
