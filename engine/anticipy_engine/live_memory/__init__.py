"""Room 7: the live memory brain seam.

Sits between the memory stores (Room 6) and the proactive engine (Room 8). Three
stubbed jobs — ``inject`` (pull relevant memory into context), ``capture`` (fold
an event into memory), ``maintain`` (housekeeping). No real logic yet; this is
the wired slot the real live-memory brain drops into next chunk.
"""
from .brain import LiveMemoryBrain  # noqa: F401
