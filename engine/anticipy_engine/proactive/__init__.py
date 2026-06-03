"""Room 8: the proactive engine.

The primary driver of the whole system — it watches (reads the live-memory seam)
and can act (calls the action layer) without being asked. Typing is a side door;
THIS is the centerpiece. Scaffold: the loop slot is wired but decides nothing.
"""
from .engine import ProactiveEngine  # noqa: F401
