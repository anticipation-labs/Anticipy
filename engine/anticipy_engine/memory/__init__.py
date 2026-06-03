"""Room 6: memory — three separate stores.

``profile`` (profile_fact), ``open_loops`` (open_loop), ``history`` (history).
Kept separate by design; never merged. Local storage only (a JSON file per
store under the data dir). Read/write only — no smart memory logic yet.
"""
from .store import Memory, MemoryStore  # noqa: F401
