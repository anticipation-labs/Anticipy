"""Anticipy Engine — the hub's HTTP surface.

`/health` is the liveness probe. The rest wire the rooms together so clients
(the SwiftUI app, the browser extension, the hello-loop) can drive the brain:

    GET  /health            -> liveness
    GET  /status            -> engine + extension state, history count
    POST /capture           -> capture -> think -> history write (hello-loop path)
    GET  /memory/history     -> read history back (another client reading the scrap)
    POST /extension/hello    -> the extension reports "connected"

The engine is local-first: it binds to 127.0.0.1 only.
"""
from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel

from . import __version__
from .brain import Brain

ENGINE_NAME = "anticipy-engine"

app = FastAPI(
    title="Anticipy Engine",
    version=__version__,
    description="Local-first hub for Anticipy. Binds to 127.0.0.1 only.",
)

brain = Brain()


class CaptureIn(BaseModel):
    text: str
    source: str = "mac_mic"


class ExtensionHello(BaseModel):
    client: str = "chrome"


@app.get("/health")
def health() -> dict:
    """Liveness probe. The hub is up iff this returns ``status: ok``."""
    return {"status": "ok", "service": ENGINE_NAME, "version": __version__}


@app.get("/status")
def status() -> dict:
    return brain.status()


@app.post("/capture")
def capture(body: CaptureIn) -> dict:
    return brain.handle_capture(body.text, body.source)


@app.get("/memory/history")
def history() -> dict:
    return {"items": [i.model_dump() for i in brain.memory.history.all()]}


@app.post("/extension/hello")
def extension_hello(body: ExtensionHello) -> dict:
    return brain.mark_extension_connected(body.client)
