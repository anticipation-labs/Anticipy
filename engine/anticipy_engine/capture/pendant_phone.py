"""PendantPhoneSource — the empty future slot.

pendant -> phone -> this engine. It is intentionally unimplemented in the
scaffold; it exists so the socket is reserved and proven to share the exact
``CaptureSource`` interface. When the pendant chunk lands, only this file gains
a body — the engine does not change.
"""
from __future__ import annotations

from .base import CaptureSource


class PendantPhoneSource(CaptureSource):
    name = "pendant_phone"

    def start(self) -> None:
        raise NotImplementedError("PendantPhoneSource is wired in a later chunk")

    def stop(self) -> None:
        raise NotImplementedError("PendantPhoneSource is wired in a later chunk")
