"""Live memory agent.

Sits between durable memory stores and the proactive engine. It owns real
capture, context injection, maintenance, inference, and retrieval self-checks.
The default path is deterministic and free; optional model enrichment lives
behind explicit live-mode flags.
"""
from .brain import LiveMemoryBrain  # noqa: F401
