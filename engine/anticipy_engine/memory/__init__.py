"""Memory — four separate drawers, local-first.

``profile`` (profile_fact), ``open_loops`` (open_loop, the deterministic ledger),
``history`` (history, episodic), ``derived`` (derived, inferred w/ confidence).
Kept separate by design; never merged. One local SQLite db + a small local vector
index (embeddings per row). The live memory agent (capture/inject/maintain/infer/
self-check) reasons over these in ``live_memory/``.
"""
from .store import Memory, MemoryDB, MemoryStore  # noqa: F401
