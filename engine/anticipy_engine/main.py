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
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from . import __version__
from .brain import Brain
from .core.control_core import ControlCore
from .core.envelopes import Job, new_id

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


@app.get("/goals/{goal_id}")
def get_goal(goal_id: str) -> dict:
    g = core.store.load(goal_id)
    return g.model_dump(mode="json") if g else {"error": "not found"}


@app.get("/gateway")
def gateway_info() -> dict:
    return {"smart_calls": len(core.gateway.smart_calls), "total_cost": core.gateway.total_cost()}


# ---- browser hand link (authenticated WebSocket) ----
@app.get("/ws/state")
def ws_state() -> dict:
    return {"connected": core.browser_link.connected}


@app.get("/ws/token")
def ws_token() -> dict:
    # The extension (host-permitted for 127.0.0.1) can read this; a web page can't
    # (no CORS headers). The token gates the WS so no site/process can pilot Chrome.
    return {"token": core.browser_link.token}


@app.post("/ws/reload")
async def ws_reload() -> dict:
    # dev-only hot-reload trigger
    sent = await core.browser_link.reload()
    return {"reloaded": sent}


class BrowseIn(BaseModel):
    intent: str = "browse_task"
    args: dict = {}


@app.post("/ws/browse")
async def ws_browse(body: BrowseIn) -> dict:
    # dev/test: drive the real BrowserHand over the live extension link
    from .hands.browser_hand import BrowserHand

    hand = BrowserHand(core.browser_link, timeout=30.0)
    res = await hand.handle(Job(intent=body.intent, args=body.args))
    return res.model_dump(mode="json")


class ObserveIn(BaseModel):
    url: Optional[str] = None


class ActIn(BaseModel):
    action: str
    index: int = 0
    text: str = ""
    url: str = ""
    dir: str = "down"
    enter: bool = False


@app.post("/ws/observe")
async def ws_observe(body: ObserveIn) -> dict:
    args = {k: v for k, v in body.model_dump().items() if v is not None}
    return await core.browser_link.send_browse(new_id(), "observe", args, timeout=40.0)


@app.post("/ws/act")
async def ws_act(body: ActIn) -> dict:
    return await core.browser_link.send_browse(new_id(), "act", body.model_dump(), timeout=40.0)


@app.websocket("/ws/extension")
async def ws_extension(ws: WebSocket) -> None:
    if not core.browser_link.check_token(ws.query_params.get("token")):
        await ws.close(code=1008)  # reject unauthenticated handshake
        return
    await ws.accept()
    await core.browser_link.attach(ws)
    core.glassbox.log("extension", {"event": "connected"})
    try:
        while True:
            msg = await ws.receive_json()
            if msg.get("type") == "ping":
                await ws.send_json({"type": "pong"})
            else:
                await core.browser_link.on_message(msg)
    except WebSocketDisconnect:
        pass
    finally:
        await core.browser_link.detach()
        core.glassbox.log("extension", {"event": "disconnected"})
