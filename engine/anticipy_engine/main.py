"""Anticipy Engine — the hub's HTTP surface.

`/health` is the liveness probe. Scaffold endpoints (/capture, /memory/history,
/extension/hello, /status) remain. The control core adds:

    POST /event       -> feed an event to the proactive engine (triage->gate->act)
    GET  /glassbox     -> the live activity feed (what it's doing / did)
    GET  /scorecard    -> health readout (decisions, outcomes, model cost)

The engine is local-first: it binds to 127.0.0.1 only.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from pydantic import BaseModel

from . import __version__
from .brain import Brain
from .core.control_core import ControlCore

ENGINE_NAME = "anticipy-engine"

brain = Brain()
core = ControlCore()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await core.start()
    try:
        yield
    finally:
        await core.stop()


app = FastAPI(
    title="Anticipy Engine",
    version=__version__,
    description="Local-first hub for Anticipy. Binds to 127.0.0.1 only.",
    lifespan=lifespan,
)


class CaptureIn(BaseModel):
    text: str
    source: str = "mac_mic"


class ExtensionHello(BaseModel):
    client: str = "chrome"


class EventIn(BaseModel):
    text: str
    source: str = "app"


@app.get("/health")
def health() -> dict:
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


# ---- control core ----
@app.post("/event")
async def event(body: EventIn) -> dict:
    return await core.feed(body.source, body.text)


@app.get("/glassbox")
def glassbox(limit: int = 50) -> dict:
    return {"entries": core.glassbox.summaries(limit)}


@app.get("/scorecard")
def scorecard() -> dict:
    return core.scorecard.readout()
