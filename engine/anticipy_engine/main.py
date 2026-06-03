"""Anticipy Engine — Room 1: the hub.

This is the local service every other room connects to. Room 1 of the scaffold
exposes only ``/health``; subsequent rooms (capture, model, memory, live-memory,
proactive loop, action layer, channels) attach as routers without changing this
file's contract.

Run locally:

    uvicorn anticipy_engine.main:app --host 127.0.0.1 --port 8000

The engine is local-first by design: it binds to 127.0.0.1 only.
"""
from __future__ import annotations

from fastapi import FastAPI

from . import __version__

ENGINE_NAME = "anticipy-engine"

app = FastAPI(
    title="Anticipy Engine",
    version=__version__,
    description="Local-first hub for Anticipy. Binds to 127.0.0.1 only.",
)


@app.get("/health")
def health() -> dict:
    """Liveness probe. The hub is up iff this returns ``status: ok``."""
    return {"status": "ok", "service": ENGINE_NAME, "version": __version__}
