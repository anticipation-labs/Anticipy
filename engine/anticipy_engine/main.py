"""Anticipy Engine — the hub's HTTP surface.

`/health` is the liveness probe. The legacy compatibility endpoints
(/capture, /memory/history, /extension/hello, /status) route through the same
ControlCore used by the product surface:

    POST /event       -> feed an event to the proactive engine (triage->gate->act)
    GET  /glassbox     -> the live activity feed (what it's doing / did)
    GET  /scorecard    -> health readout (decisions, outcomes, model cost)

The engine is local-first: it binds to 127.0.0.1 only.
"""
from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from . import __version__
from .agent import WebVoyagerAgent, judge
from .capture.transcribe import is_audio_file, transcribe_audio
from .channels.inbound import InboundPoller
from .core.control_core import ControlCore
from .core.envelopes import EventSource, Job, new_id
from .core.gateway import PROVIDER_OPENROUTER, ModelGateway
from .owner_onboarding import OwnerOnboardingIn

ENGINE_NAME = "anticipy-engine"

core = ControlCore()
extension_hello_seen = False
# Real reasoning+vision model for the web-agent loop (kept separate from the
# core's default gateway so the engine/hands tests stay free + deterministic).
gateway_agent = ModelGateway(
    provider=PROVIDER_OPENROUTER,
    cheap_model="google/gemini-3.1-flash-lite",   # routine see-and-locate steps
    smart_model="google/gemini-3.5-flash",        # planning / recovery / stuck / judge
)


async def _trigger_scheduler(interval_s: float) -> None:
    """The clock that makes the engine anticipatory: tick the trigger watcher forever.
    A tick failure is logged and the next tick still happens — the clock never dies."""
    while True:
        await asyncio.sleep(interval_s)
        try:
            await core.proactive.trigger_tick()
        except Exception as e:  # noqa: BLE001 — the scheduler must outlive any one tick
            core.glassbox.log("trigger_tick_error", {"error": f"{type(e).__name__}: {e}"})


async def _inbound_scheduler(poller: InboundPoller, interval_s: float) -> None:
    """Poll Twilio for the owner's SMS replies (YES/NO resolves asks; speech ingests).
    Live-env-gated at startup; a poll failure is logged and the loop lives on."""
    while True:
        await asyncio.sleep(interval_s)
        try:
            await poller.poll_once()
        except Exception as e:  # noqa: BLE001 — the poller must outlive any one pass
            core.glassbox.log("inbound_poll_error", {"error": f"{type(e).__name__}: {e}"})


@asynccontextmanager
async def lifespan(app: FastAPI):
    await core.start()
    # ANTICIPY_TICK_SECONDS=0 disables the scheduler (deterministic tests use POST /trigger/tick)
    interval_s = float(os.environ.get("ANTICIPY_TICK_SECONDS", "30") or 0)
    tick_task = asyncio.create_task(_trigger_scheduler(interval_s)) if interval_s > 0 else None
    # Inbound SMS poll: ONLY with the live channel env (creds + mode) — suite, stub and
    # mock runs never construct a transport. ANTICIPY_INBOUND_POLL_SECONDS=0 disables.
    inbound_s = float(os.environ.get("ANTICIPY_INBOUND_POLL_SECONDS", "15") or 0)
    inbound_task = (asyncio.create_task(_inbound_scheduler(InboundPoller(core), inbound_s))
                    if inbound_s > 0 and InboundPoller.live_ready() else None)
    try:
        yield
    finally:
        for task in (tick_task, inbound_task):
            if task is not None:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
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
    meta: dict = Field(default_factory=dict)


class OwnerIngestIn(BaseModel):
    text: str
    source: str = "transcript"
    meta: dict = Field(default_factory=dict)
    execute_actions: bool = False


class OwnerFileIngestIn(BaseModel):
    path: str
    filename: str = ""
    source: str = "upload"
    meta: dict = Field(default_factory=dict)
    execute_actions: bool = False


class ResolveIn(BaseModel):
    ask_id: str
    approved: bool


class MemoryLoopResolveIn(BaseModel):
    id: str
    status: str = "done"


class ConnectionAuthorizeIn(BaseModel):
    id: str


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": ENGINE_NAME, "version": __version__}


@app.get("/status")
def status() -> dict:
    return {
        "engine": "ok",
        "core": "control_core",
        "extension_connected": extension_hello_seen or core.browser_link.connected,
        "history_count": len(core.memory.history.all()),
        "open_loop_count": len([i for i in core.memory.open_loops.all() if i.status in ("open", "waiting")]),
        "pending_count": len(core.pending_asks()),
        "memory_recovered": bool(getattr(core.memory.db, "recovered_corruption", False)),
        "channels": core.channel_status(),
    }


@app.post("/capture")
async def capture(body: CaptureIn) -> dict:
    if body.source not in EventSource._value2member_map_:
        raise HTTPException(status_code=400, detail=f"unknown capture source: {body.source}")
    return await core.feed(body.source, body.text, {"legacy_capture": True})


@app.get("/memory/history")
def history() -> dict:
    return {"items": [i.model_dump() for i in core.memory.history.all()]}


@app.get("/memory/open-loops")
def memory_open_loops(limit: int = 50) -> dict:
    return core.memory_open_loops(limit=limit)


@app.post("/memory/open-loops/resolve")
def memory_loop_resolve(body: MemoryLoopResolveIn) -> dict:
    out = core.resolve_memory_loop(body.id, body.status)
    if not out.get("resolved"):
        raise HTTPException(status_code=400, detail=out.get("reason") or "could not resolve memory loop")
    return out


@app.post("/connections/authorize")
def connection_authorize(body: ConnectionAuthorizeIn) -> dict:
    out = core.authorize_connection_loop(body.id)
    if not out.get("ok"):
        raise HTTPException(status_code=400, detail=out.get("reason") or "could not prepare connection")
    return out


@app.post("/extension/hello")
def extension_hello(body: ExtensionHello) -> dict:
    global extension_hello_seen
    extension_hello_seen = True
    core.glassbox.log("extension_hello", {"client": body.client})
    return {"connected": True, "client": body.client, "core": "control_core"}


# ---- control core ----
@app.post("/event")
async def event(body: EventIn) -> dict:
    return await core.feed(body.source, body.text, body.meta)


@app.post("/owner/ingest")
async def owner_ingest(body: OwnerIngestIn) -> dict:
    """One shared Action Engine intake for typed transcript, MP3, listening, and pay-to-try."""
    return await core.owner_ingest(body.source, body.text, body.meta, execute_actions=body.execute_actions)


@app.post("/owner/ingest-file")
async def owner_ingest_file(body: OwnerFileIngestIn) -> dict:
    """Read one uploaded local file, then use the same owner-ingest path as typed text."""
    path = Path(body.path).expanduser().resolve()
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail=f"uploaded file not found: {path}")

    filename = body.filename or path.name
    meta = {
        **body.meta,
        "upload_filename": filename,
        "upload_path": str(path),
        "upload_bytes": path.stat().st_size,
    }

    if is_audio_file(path):
        try:
            transcript = transcribe_audio(path)
        except Exception as exc:  # noqa: BLE001 - surface an honest product error
            core.glassbox.log(
                "owner_upload_error",
                {"filename": filename, "path": str(path), "error": f"{type(exc).__name__}: {exc}"},
            )
            raise HTTPException(
                status_code=422,
                detail=f"Could not transcribe {filename}: {type(exc).__name__}: {exc}",
            ) from exc
        text = "\n".join(transcript.lines)
        meta.update({"upload_kind": "audio", "transcript": transcript.metadata})
        source = body.source if body.source != "upload" else "audio_upload"
    else:
        text = path.read_bytes().decode("utf-8", errors="replace")
        meta.update({"upload_kind": "text"})
        source = body.source if body.source != "upload" else "text_upload"

    if not text.strip():
        raise HTTPException(status_code=400, detail=f"{filename} did not contain usable text")

    core.glassbox.log("owner_upload_ingest", {"filename": filename, "source": source, "kind": meta["upload_kind"]})
    return await core.owner_ingest(source, text, meta, execute_actions=body.execute_actions)


@app.get("/owner/cards")
def owner_cards(limit: int = 50) -> dict:
    """Recent durable owner cards, so the app board survives reloads."""
    return core.owner_cards(limit=limit)


@app.post("/owner/onboard")
async def owner_onboard(body: OwnerOnboardingIn) -> dict:
    """First-run setup writes people, preferences, apps, stores, and gates into memory."""
    return await core.owner_onboard(body)


@app.post("/trigger/tick")
async def trigger_tick() -> dict:
    """Deterministic tick (tests/gates): one watcher pass, same path as the scheduler."""
    fired = await core.proactive.trigger_tick()
    return {"fired": fired}


@app.get("/glassbox")
def glassbox(limit: int = 50) -> dict:
    return {"entries": core.glassbox.summaries(limit)}


@app.get("/pending")
def pending() -> dict:
    """Room 6: the 'needs you' surface — detrimental actions paused awaiting approve/deny."""
    return {"pending": core.pending_asks()}


@app.post("/resolve")
async def resolve(body: ResolveIn) -> dict:
    """Room 6: the app's approve/deny -> resolves the REAL paused goal (brain -> app -> back)."""
    return await core.resolve(body.ask_id, body.approved)


@app.get("/scorecard")
def scorecard() -> dict:
    return core.scorecard.readout()


@app.get("/goals/{goal_id}")
def get_goal(goal_id: str) -> dict:
    g = core.store.load(goal_id)
    return g.model_dump(mode="json") if g else {"error": "not found"}


@app.get("/gateway")
def gateway_info() -> dict:
    # Cost counters PLUS the real run-mode signals, so a caller (e.g. the journey gauge's
    # precondition) can VERIFY the engine is actually live — real model + live API hand —
    # rather than assume it. These read the engine's actual wired objects, not env strings.
    return {
        "smart_calls": len(core.gateway.smart_calls),
        "total_cost": core.gateway.total_cost(),
        "provider": core.gateway.provider,
        "cheap_model": core.gateway.cheap_model,
        "smart_model": core.gateway.smart_model,
        "api_hands_mode": core.api_hand.mode,
    }


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
    agent: bool = False


@app.post("/ws/browse")
async def ws_browse(body: BrowseIn) -> dict:
    if body.agent:
        res = await core.browser_hand.handle(Job(intent=body.intent, args=body.args))
    else:
        # Transport diagnostic only. M3 evidence must use /event and real sites.
        from .hands.browser_hand import BrowserHand

        res = await BrowserHand(core.browser_link, timeout=30.0).handle(Job(intent=body.intent, args=body.args))
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


class AgentRunIn(BaseModel):
    task: str
    start_url: str
    max_steps: int = 8
    judge: bool = False
    model: Optional[str] = None  # per-run brain override (model bake-off); None = default ladder


def _gateway_for(model: Optional[str]) -> ModelGateway:
    if not model:
        return gateway_agent
    # single-model gateway for an A/B run (both tiers = the candidate)
    return ModelGateway(provider=PROVIDER_OPENROUTER, cheap_model=model, smart_model=model)


@app.post("/agent/run")
async def agent_run(body: AgentRunIn) -> dict:
    gw = _gateway_for(body.model)
    agent = WebVoyagerAgent(core.browser_link, gw, max_steps=body.max_steps,
                            notifier=core.notify_user)
    result = await agent.run(body.task, body.start_url)
    shot = result.pop("final_shot", None)  # vision-judge in-process; don't ship the image over HTTP
    # The general judge decides success — but only for an actual answer. A safety
    # stop or a wall handoff is already a correct outcome and is not judged.
    if body.judge and not result.get("needs_human") and not result.get("stopped_for_safety"):
        result["judgment"] = await judge(gw, body.task, result, image=shot)
    return result


class AgentResumeIn(BaseModel):
    task: str
    start_url: str          # the page AFTER the human cleared the wall
    resume_token: str = ""
    max_steps: int = 12
    judge: bool = False


@app.post("/agent/resume")
async def agent_resume(body: AgentResumeIn) -> dict:
    # STUB seam: the human cleared the wall and said "go". Restoring the exact
    # mid-plan state (same subgoal/history) is the TODO; for now we continue the
    # task from the now-unblocked page and never re-touch the wall.
    core.glassbox.log("handoff", {"event": "resume", "token": body.resume_token, "url": body.start_url})
    agent = WebVoyagerAgent(core.browser_link, gateway_agent, max_steps=body.max_steps,
                            notifier=core.notify_user)
    result = await agent.run(body.task, body.start_url)
    result["resumed"] = True
    shot = result.pop("final_shot", None)
    if body.judge and not result.get("needs_human") and not result.get("stopped_for_safety"):
        result["judgment"] = await judge(gateway_agent, body.task, result, image=shot)
    return result


class AgentJudgeIn(BaseModel):
    task: str
    answer: str = ""
    final_url: str = ""


@app.post("/agent/judge")
async def agent_judge(body: AgentJudgeIn) -> dict:
    return await judge(gateway_agent, body.task, {"answer": body.answer, "final_url": body.final_url})


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
        await core.browser_link.detach(ws)
        core.glassbox.log("extension", {"event": "disconnected"})
