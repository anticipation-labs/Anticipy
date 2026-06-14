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
import secrets
import tempfile
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from . import __version__
from .agent import WebVoyagerAgent, judge
from .capture.transcribe import is_audio_file, transcribe_audio
from .channels.conversation_relay import ConversationRelayBrain, stream_tokens
from .channels.inbound import InboundPoller
from .core.control_core import ControlCore
from .core.envelopes import EventSource, Job, new_id
from .core.gateway import PROVIDER_OPENROUTER, ModelGateway
from .hands import browser_use_link
from .owner_onboarding import OwnerOnboardingIn

ENGINE_NAME = "anticipy-engine"
DEFAULT_UPLOAD_ROOT = Path(tempfile.gettempdir()) / "anticipy-owner-uploads"
DEFAULT_MAX_UPLOAD_BYTES = 100 * 1024 * 1024
OWNER_API_TOKEN_ENV = "ANTICIPY_OWNER_API_TOKEN"
OWNER_TOKEN_HEADER = "x-anticipy-owner-token"
PUBLIC_PATHS = {"/health"}

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


def _owner_api_token() -> str:
    return (os.environ.get(OWNER_API_TOKEN_ENV) or "").strip()


def _owner_api_authorized(request: Request, token: str) -> bool:
    supplied = (request.headers.get(OWNER_TOKEN_HEADER) or "").strip()
    auth = (request.headers.get("authorization") or "").strip()
    if not supplied and auth.lower().startswith("bearer "):
        supplied = auth[7:].strip()
    return bool(supplied) and secrets.compare_digest(supplied, token)


def _owner_ws_authorized(ws: WebSocket) -> bool:
    """Owner-token gate for owner WebSockets (e.g. Twilio ConversationRelay /cr).

    The HTTP owner-token middleware never runs for the WS handshake, so each owner
    WS must check the token itself BEFORE ws.accept() — exactly as /ws/extension
    does. When ANTICIPY_OWNER_API_TOKEN is unset (local dev / deterministic suite),
    the socket stays open. When it is set, the caller must present the token. Twilio
    ConversationRelay cannot set custom headers, so we accept it on the handshake as
    a ?token= query param (header/bearer also honored for other clients)."""
    token = _owner_api_token()
    if not token:
        return True  # no token configured -> dev/local path stays open
    supplied = (ws.query_params.get("token") or "").strip()
    if not supplied:
        header = (ws.headers.get(OWNER_TOKEN_HEADER) or "").strip()
        auth = (ws.headers.get("authorization") or "").strip()
        if header:
            supplied = header
        elif auth.lower().startswith("bearer "):
            supplied = auth[7:].strip()
    return bool(supplied) and secrets.compare_digest(supplied, token)


@app.middleware("http")
async def owner_api_auth(request: Request, call_next):
    """Optional public-deploy guard.

    Local development and the deterministic suite keep ANTICIPY_OWNER_API_TOKEN
    unset. When it is set, every owner/private engine route requires the server
    held token; only /health remains public for liveness probes.
    """
    token = _owner_api_token()
    if token and request.url.path not in PUBLIC_PATHS and not _owner_api_authorized(request, token):
        return JSONResponse(
            {"error": "unauthorized", "message": "Anticipy owner API token required."},
            status_code=401,
            headers={"www-authenticate": "Bearer"},
        )
    return await call_next(request)


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


class RememberedApproveIn(BaseModel):
    line_id: str


class ConnectionAuthorizeIn(BaseModel):
    id: str


class OnboardingProfileIn(BaseModel):
    """Build-my-profile request: a subject name + a few PUBLIC source URLs.

    Read-only scraping only — no login, no writes. `sources` are bare URLs (or
    {"url","kind"} dicts the builder also accepts).
    """

    name: str
    sources: list = Field(default_factory=list)


class OnboardingClarifyIn(BaseModel):
    """Clarifying-call request: same name + PUBLIC sources as the profile build.

    The endpoint builds the profile (read-only) then plans the short list of
    clarifying questions Anticipy would ask on a phone call. `max_questions`
    caps the call length ("a couple of questions").
    """

    name: str
    sources: list = Field(default_factory=list)
    max_questions: int = 5


def _upload_roots() -> list[Path]:
    raw = os.environ.get("ANTICIPY_UPLOAD_ROOTS") or os.environ.get("ANTICIPY_UPLOAD_ROOT") or str(DEFAULT_UPLOAD_ROOT)
    return [Path(p).expanduser().resolve() for p in raw.split(os.pathsep) if p.strip()]


def _under_root(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _cleanup_upload(path: Path) -> None:
    candidates = [path]
    if is_audio_file(path):
        candidates.append(path.with_suffix(".transcript"))
    for candidate in candidates:
        with suppress(OSError):
            candidate.unlink()
    for parent in path.parents:
        if parent in _upload_roots() or parent == parent.parent:
            break
        with suppress(OSError):
            parent.rmdir()


def _readiness(channels: dict) -> dict:
    browser_connected = bool(core.browser_link.connected or getattr(core.native_bridge_link, "connected", False))
    api_live = core.api_hand.mode == "live"
    inbound_status = (channels.get("inbound") or {}).get("status")
    channels_ready = channels.get("status") == "live_ready" and inbound_status == "live_ready"
    channels_armed = channels.get("status") == "ready_to_enable" or inbound_status == "ready_to_enable"
    memory_recovered = bool(getattr(core.memory.db, "recovered_corruption", False))
    owner_token_set = bool(_owner_api_token())
    items = {
        "app_input": {
            "state": "ready",
            "label": "Go, typed transcript, upload, and listening intake are wired",
        },
        "proactive_engine": {
            "state": "ready",
            "label": "Messy-life input routes through the proactive engine",
        },
        "memory": {
            "state": "warning" if memory_recovered else "ready",
            "label": "Memory recovered from corruption" if memory_recovered else "Memory ledger ready",
        },
        "browser": {
            "state": "ready" if browser_connected else "setup",
            "label": "Browser hand linked" if browser_connected else "Browser hand needs Chrome helper link",
        },
        "api_hands": {
            "state": "ready" if api_live else "mock",
            "label": "API hands live" if api_live else "API hands in mock mode",
        },
        "voice_text": {
            "state": (
                "ready" if channels_ready
                else "ready_to_enable" if channels_armed
                else "setup" if channels.get("mode") == "live"
                else "mock"
            ),
            "label": channels.get("label") or channels.get("status", "mock"),
        },
        "approvals": {
            "state": "ready",
            "label": f"{len(core.pending_asks())} human-impacting action(s) waiting",
        },
        "money_wall": {
            "state": "ready",
            "label": "Money never executes automatically",
        },
        "owner_api": {
            "state": "protected" if owner_token_set else "local",
            "label": "Owner API token gate enabled" if owner_token_set else "Owner API token gate not set",
        },
    }
    blocking_setup = [key for key, item in items.items() if item["state"] == "setup"]
    mock_setup = [key for key, item in items.items() if item["state"] in {"mock", "local", "ready_to_enable"}]
    overall = (
        "ready" if not blocking_setup and not mock_setup
        else "needs_setup" if blocking_setup
        else "local_mock"
    )
    return {"overall": overall, "items": items}


def _env_present(*names: str) -> bool:
    """True only if at least one of the named env vars is set to a non-empty value.
    Reports PRESENCE ONLY — the value is never returned, logged, or compared."""
    return any((os.environ.get(n) or "").strip() for n in names)


def _user_vault_connected() -> bool:
    """Has THIS engine's configured user connected any app through the per-user token
    vault? Reads only the vault's app-name index (never a token); returns False on any
    error so a missing/locked vault never throws into the readiness checklist."""
    broker = getattr(core.api_hand, "_broker", None)
    vault = getattr(broker, "vault", None) if broker is not None else None
    if vault is None:
        return False
    try:
        return bool(vault.apps(core.api_hand.user_id))
    except Exception:  # noqa: BLE001 — readiness must never fail on vault state
        return False


def _connect_readiness() -> dict:
    """The guided 'Connect your accounts' checklist. For each capability that unlocks a
    LIVE owner action, report {capability, status: live|needs_connect, what_to_do} using
    PRESENCE/ABSENCE of config only — never a secret value, number, or token. This turns
    the live-unlock into an honest checklist the owner can work through; it grants nothing
    and connects nothing."""
    channels = core.channel_status()

    # Google / Arcade — the API hand. Live needs the shared ARCADE_API_KEY OR this user's
    # per-user vault connection, AND the hand running in live mode.
    arcade_key = _env_present("ARCADE_API_KEY")
    per_user_vault = _user_vault_connected()
    api_live = core.api_hand.mode == "live" and (arcade_key or per_user_vault)
    if api_live:
        google_what = "Connected. Google Calendar / Gmail run as live API actions."
    elif arcade_key or per_user_vault:
        google_what = (
            "Credentials present but the API hand is in mock mode. Start the engine with "
            "ANTICIPY_HANDS_MODE=live to run real Google actions."
        )
    else:
        google_what = (
            "Sign in to Arcade and authorize Google (Calendar + Gmail), then set "
            "ARCADE_API_KEY (or connect your account to the per-user vault) and run the "
            "engine with ANTICIPY_HANDS_MODE=live."
        )

    # Twilio voice/text — channels mode + creds (presence only via channel_status()).
    channels_mode = channels.get("mode")
    channels_status = channels.get("status")
    twilio_live = channels_mode == "live" and channels_status == "live_ready"
    if twilio_live:
        twilio_what = "Connected. The voice/SMS line can text you and call you back."
    elif channels_status == "ready_to_enable":
        twilio_what = (
            "Twilio and your phone are configured; live mode is off. Set "
            "ANTICIPY_CHANNELS_MODE=live to turn the call/text line on."
        )
    elif channels_status == "missing_owner_contact":
        twilio_what = "Set your phone number (OWNER_PHONE) so the line can reach you."
    else:
        twilio_what = (
            "Create a Twilio account, then set TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, "
            "TWILIO_FROM, and OWNER_PHONE, and run with ANTICIPY_CHANNELS_MODE=live."
        )

    # Browser bridge — the gitignored 3.11 browser_use venv (engine/.bu-venv).
    bridge = browser_use_link.available()
    browser_live = bool(bridge.get("ok"))
    if browser_live:
        browser_what = "Connected. The browser hand can run real read/act sessions in your Chrome."
    else:
        browser_what = (
            "Install the browser bridge: create the engine/.bu-venv Python 3.11 venv and "
            "install browser_use (see scripts), so the browser hand can drive your Chrome."
        )

    # Apple signing — the live-deferred one-click public download (Omar's Apple account).
    apple_live = _env_present("APPLE_DEVELOPER_ID")
    apple_what = (
        "Set. The desktop app can be code-signed and notarized for a one-click download."
        if apple_live
        else "Set APPLE_DEVELOPER_ID (your Apple Developer account) to sign + notarize the "
        "public download. Until then the dev build opens via right-click -> Open."
    )

    def _cap(capability: str, label: str, live: bool, what_to_do: str) -> dict:
        return {
            "capability": capability,
            "label": label,
            "status": "live" if live else "needs_connect",
            "what_to_do": what_to_do,
        }

    items = [
        _cap("google_arcade", "Google (Calendar + Gmail) via Arcade", api_live, google_what),
        _cap("twilio", "Voice + SMS line (Twilio)", twilio_live, twilio_what),
        _cap("browser_bridge", "Browser hand (your Chrome)", browser_live, browser_what),
        _cap("apple_signing", "Signed public download (Apple)", apple_live, apple_what),
    ]
    live_count = sum(1 for it in items if it["status"] == "live")
    return {
        "overall": "all_live" if live_count == len(items) else "needs_connect",
        "live_count": live_count,
        "total": len(items),
        "capabilities": items,
    }


@app.get("/readiness")
def readiness() -> dict:
    """Guided connect-your-accounts checklist: which live capabilities are connected vs
    need-connecting, with the honest one-liner of what to do — exposing PRESENCE/ABSENCE
    of config only, never any secret value. Read-only; grants and connects nothing."""
    return _connect_readiness()


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": ENGINE_NAME, "version": __version__}


@app.get("/status")
def status() -> dict:
    channels = core.channel_status()
    return {
        "engine": "ok",
        "core": "control_core",
        "extension_connected": extension_hello_seen or core.browser_link.connected,
        "history_count": len(core.memory.history.all()),
        "open_loop_count": core.memory_open_loops(limit=0)["count"],
        "pending_count": len(core.pending_asks()),
        "memory_recovered": bool(getattr(core.memory.db, "recovered_corruption", False)),
        "channels": channels,
        "readiness": _readiness(channels),
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


@app.get("/memory/remembered")
def memory_remembered(limit: int = 50) -> dict:
    """The explicit PULL surface for the INERT remember-list ("show me my remembered
    commitments"). Strictly read-only: it returns rows from a SEPARATE table that no
    proactive loop, decider, harm-line, or TriggerWatcher reads, and that carries no
    due/remind/trigger field — so surfacing it can never fire an action or interrupt.
    This endpoint is on NO background loop; it only answers an explicit request.

    Each row is enriched with a DISPLAY-ONLY ``inferred`` {task, people, due_phrase,
    confidence} computed off to the side and CACHED (only un-enriched recent lines are
    inferred per pull). The enrichment is metadata for the review only: it carries no
    due_ts/remind_ts/trigger, creates no open_loop, and never reaches the decider /
    harm-line / TriggerWatcher — the raw line stays the ground truth the owner checks."""
    cap = core.live_memory.capturer
    rows = cap.remember.recent(limit)
    rows = cap.review_enricher.enrich_rows(rows)
    return {"remembered": rows, "count": len(rows)}


@app.post("/memory/remembered/approve")
async def memory_remembered_approve(body: RememberedApproveIn) -> dict:
    """DEFAULT-DENY press-go: the owner presses go on ONE remembered line by id.

    This is the ONLY new execution trigger and it requires an explicit owner POST (sitting
    behind the same owner-token middleware as every other owner route). It enriches the
    line with the SAME review inference, maps it to one closed intent, and executes ONLY
    the whitelisted reversible intents that can be independently read back
    (create_event/write_memory) through the existing orchestrator funnel + read-back gate.
    Everything else (a Gmail draft — reversible but not yet read-back-verifiable, an actual
    send, a message/Slack, money/binding, ambiguous) is prepared-and-handed-back, never
    executed. A vent returns approved=false with no goal. There is no yes/no body that can
    route a non-whitelisted item to execution."""
    return await core.approve_remembered(body.line_id)


@app.post("/memory/remembered/dryrun")
def memory_remembered_dryrun(body: RememberedApproveIn) -> dict:
    """LIVE DRY-RUN PREVIEW for ONE remembered line — show EXACTLY what press-go WOULD do
    WITHOUT doing it (trust-before-connect).

    This runs the SAME default-deny press-go mapping as /memory/remembered/approve (the
    SAME review inference + the SAME map_inferred_to_step + the SAME WHITELIST gate) but
    STOPS before execution. It NEVER builds or saves a Goal, NEVER calls
    orchestrator.start_goal/_drive, NEVER writes a memory note, NEVER touches the api/browser
    hands. It only PLANS and SHOWS.

    For a whitelisted (auto-executable) line it returns {would_execute:true, intent, tool
    (e.g. GoogleCalendar.CreateEvent), the EXACT args it would send, and "This runs for real
    once you connect Google"}. For a non-whitelisted line — including a Gmail draft, which is
    prepared for the owner to create himself until a drafts read-back is wired — it returns
    {would_execute:false, handback, why}. This lets the owner see his whole day's planned
    real actions before connecting anything."""
    return core.dryrun_remembered(body.line_id)


@app.get("/memory/remembered/dryrun-day")
def memory_remembered_dryrun_day(limit: int = 50) -> dict:
    """LIVE DRY-RUN PREVIEW for the WHOLE day — preview every remembered line at once so the
    owner can see his entire day's planned real actions before connecting any account.

    Reuses the inert remembered pull and dry-runs EACH line through the SAME press-go
    mapping (no execution, no Goal, no orchestrator call). Returns the per-line previews
    plus a count of how many WOULD execute on connect."""
    cap = core.live_memory.capturer
    rows = cap.remember.recent(limit)
    previews = [core.dryrun_remembered(str(r.get("id"))) for r in rows]
    would = sum(1 for p in previews if p.get("would_execute"))
    return {"previews": previews, "count": len(previews), "would_execute_count": would}


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
    if not any(_under_root(path, root) for root in _upload_roots()):
        raise HTTPException(status_code=403, detail="uploaded file path is outside the Anticipy upload staging area")
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail=f"uploaded file not found: {path}")
    max_bytes = int(os.environ.get("ANTICIPY_MAX_UPLOAD_BYTES", str(DEFAULT_MAX_UPLOAD_BYTES)) or DEFAULT_MAX_UPLOAD_BYTES)
    size = path.stat().st_size
    if size > max_bytes:
        _cleanup_upload(path)
        raise HTTPException(status_code=413, detail=f"{path.name} is too large ({size} bytes > {max_bytes})")

    filename = body.filename or path.name
    meta = {
        **body.meta,
        "upload_filename": filename,
        "upload_path": str(path),
        "upload_bytes": size,
    }

    try:
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
    finally:
        _cleanup_upload(path)

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


# Max public source URLs we will read per profile build (keep the read bounded).
ONBOARDING_MAX_SOURCES = 6


def _profile_browse_reader():
    """The reader the profile builder uses. Tests may inject a fake via
    app.state.profile_browse_reader (no live browser in CI); production binds the
    real read-only open-source browser arm. Returns None to mean 'use the arm's
    default', so the builder itself binds the real reader.
    """
    return getattr(app.state, "profile_browse_reader", None)


def _normalize_onboarding_sources(raw_name: str, raw_sources) -> tuple[str, list]:
    """Validate + bound the {name, sources} shared by the profile/clarify routes.

    Rejects empty names and non-public (non-http) sources early so we never
    attempt a login-walled or file:// read. Raises HTTPException(422) on bad
    input. Returns (clean_name, bounded_public_sources).
    """
    name = (raw_name or "").strip()
    if not name:
        raise HTTPException(status_code=422, detail="name is required")
    bounded = list(raw_sources or [])[:ONBOARDING_MAX_SOURCES]
    sources: list = []
    for s in bounded:
        url = s.get("url") if isinstance(s, dict) else s
        if not isinstance(url, str):
            continue
        url = url.strip()
        if url.lower().startswith(("http://", "https://")):
            sources.append(s)
    if not sources:
        raise HTTPException(status_code=422, detail="at least one public http(s) source URL is required")
    return name, sources


async def _build_onboarding_profile(name: str, sources: list):
    """Build a profile (read-only) off the event loop, with the honest browser
    probe. Shared by the /onboarding/profile and /onboarding/clarify routes so
    the read path and its honesty signal stay identical.
    """
    from fastapi.concurrency import run_in_threadpool

    from .hands.browser_use_link import available as _browser_available
    from .onboarding.profile_builder import build_profile

    reader = _profile_browse_reader()
    probe = _browser_available()
    profile = await run_in_threadpool(build_profile, name, sources, browse_reader=reader)
    # An injected test reader counts as "available" for the assembly proof.
    browser_available = bool(probe.get("ok")) or reader is not None
    return profile, browser_available, probe


@app.post("/onboarding/profile")
async def onboarding_profile(body: OnboardingProfileIn) -> dict:
    """Owner-gated: build a structured, trust-graded profile of a person/entity
    from a handful of PUBLIC source URLs by reading each READ-ONLY through the
    browser arm.

    Honest by construction: when no browser bridge is available (CI / no-browser),
    each read fails -> the source becomes a blocker and NO facts are invented; the
    response carries `browser_available` so the caller never mistakes an empty,
    honestly-degraded profile for a real one. A test may inject a fake reader via
    app.state.profile_browse_reader so the assembly path is exercised without a
    live browser.
    """
    name, sources = _normalize_onboarding_sources(body.name, body.sources)
    profile, browser_available, probe = await _build_onboarding_profile(name, sources)

    out = profile.as_dict()
    # Honesty signal: was a real browser arm usable for this build? An injected
    # test reader counts as "available" for the purpose of the assembly proof.
    out["browser_available"] = browser_available
    out["browser_probe"] = {"ok": bool(probe.get("ok")), "runner_exists": bool(probe.get("runner_exists"))}
    core.glassbox.log(
        "onboarding_profile_built",
        {
            "name": name,
            "sources": len(sources),
            "facts": out["summary"]["facts"],
            "needs_cross_check": out["summary"]["needs_cross_check"],
            "sources_read_ok": out["summary"]["sources_read_ok"],
            "browser_available": out["browser_available"],
        },
    )
    return out


@app.api_route("/onboarding/clarify", methods=["GET", "POST"])
async def onboarding_clarify(request: Request) -> dict:
    """Owner-gated: plan the CLARIFYING CALL for a built profile.

    Builds the profile (read-only, same path as /onboarding/profile) then runs
    the deterministic clarify planner over it: the short, ranked list of
    questions Anticipy would ask on a phone call — disagreements first, then
    low-confidence confirmations, then unreadable-source gaps, then missing core
    fields — capped so it's "a couple of questions." The phone delivery itself
    (Twilio voice) is LIVE-DEFERRED; this is the brain that decides what to ask.

    Accepts the request as a JSON body (POST) or query params (GET:
    ?name=...&sources=url1&sources=url2&max_questions=5), so a built profile's
    questions are fetchable either way. Honest by construction: only asks about
    uncertainty the profile actually records; no live browser is required in CI
    (an injected reader exercises the assembly path).
    """
    from .onboarding.clarify import clarify_payload

    # Parse name/sources/max_questions from JSON body or query string.
    if request.method == "POST":
        try:
            raw = await request.json()
        except Exception:
            raw = {}
        if not isinstance(raw, dict):
            raw = {}
        raw_name = raw.get("name", "")
        raw_sources = raw.get("sources", [])
        raw_max = raw.get("max_questions", 5)
    else:
        qp = request.query_params
        raw_name = qp.get("name", "")
        raw_sources = qp.getlist("sources")
        raw_max = qp.get("max_questions", 5)

    try:
        max_questions = int(raw_max)
    except (TypeError, ValueError):
        max_questions = 5
    if max_questions < 0:
        max_questions = 0

    name, sources = _normalize_onboarding_sources(raw_name, raw_sources)
    profile, browser_available, probe = await _build_onboarding_profile(name, sources)

    out = clarify_payload(profile, max_questions=max_questions)
    # Honesty signals mirrored from the build so an empty, honestly-degraded call
    # plan is never mistaken for "no questions needed."
    out["browser_available"] = browser_available
    out["browser_probe"] = {"ok": bool(probe.get("ok")), "runner_exists": bool(probe.get("runner_exists"))}
    out["blockers"] = list(getattr(profile, "blockers", []) or [])
    core.glassbox.log(
        "onboarding_clarify_planned",
        {
            "name": name,
            "sources": len(sources),
            "questions": out["summary"]["count"],
            "by_reason": out["summary"]["by_reason"],
            "browser_available": browser_available,
        },
    )
    return out


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


def _relay_brain() -> ConversationRelayBrain:
    """The brain for the two-way voice line — the SAME Room 1.5 decider, never a fork.

    Live engines (ANTICIPY_MODEL_PROVIDER=openrouter) already hold a constructed decider on
    the proactive engine; reuse that exact instance. Stub engines skip the decider for a
    deterministic suite, so build the very same ``Decider`` class on the engine's own
    gateway — identical prompt, parse, and verdicts. Either way the voice answers with the
    same judgment the always-listening loop would make on that line."""
    decider = getattr(core.proactive, "decider", None)
    if decider is not None:
        return ConversationRelayBrain(decider)
    return ConversationRelayBrain.from_gateway(core.gateway, glassbox=core.glassbox)


@app.websocket("/cr")
async def conversation_relay(ws: WebSocket) -> None:
    """Twilio ConversationRelay socket — the two-way voice turn loop (the 2:45 call).

    Twilio attaches here (via the <Connect><ConversationRelay url=...> TwiML) and speaks
    JSON frames. We answer with the SAME decider/brain the proactive engine runs:

      <- {type:"setup", ...}                 (Twilio call metadata; acknowledged, no reply)
      <- {type:"prompt", voicePrompt:"..."}  (one owner utterance, transcribed by Twilio)
      -> {type:"text", token:"...", last:false} * N   (the brain's reply, streamed)
      -> {type:"text", token:"", last:true}           (turn's reply complete)
      ...repeat for each owner turn...
      <- {type:"interrupt"} / {type:"dtmf"}  (acknowledged; barge-in stops the turn)
      -> {type:"end", handoffData:{...}}     (on hang-up: what the brain decided)

    The reply is words only — judging a line and speaking the verdict. The real act/ask
    still flows through the proactive spine on the ambient transcript, money stays a hard
    ASK, and a vent stays SILENT, exactly as the decider's contract guarantees."""
    if not _owner_ws_authorized(ws):
        # No owner token on the handshake while one is configured: reject before
        # accept() so an unauthenticated caller can never drive the decider brain.
        await ws.close(code=1008)  # policy violation
        core.glassbox.log("conversation_relay", {"event": "rejected_unauthenticated"})
        return
    await ws.accept()
    brain = _relay_brain()
    core.glassbox.log("conversation_relay", {"event": "connected"})
    last_handoff: dict = {"event": "no_prompt"}
    try:
        while True:
            msg = await ws.receive_json()
            kind = msg.get("type")
            if kind == "prompt":
                turn = await brain.turn(msg.get("voicePrompt") or "")
                last_handoff = turn.handoff_data()
                # stream the reply as ConversationRelay text tokens; the FINAL frame
                # carries last:true so Twilio knows the turn's speech is complete
                tokens = list(stream_tokens(turn.reply))
                for tok in tokens:
                    await ws.send_json({"type": "text", "token": tok, "last": False})
                await ws.send_json({"type": "text", "token": "", "last": True})
                core.glassbox.log("conversation_relay",
                                  {"event": "turn", "verdict": turn.verdict})
            elif kind in ("interrupt", "dtmf", "setup"):
                # Twilio control frames — nothing to say back; the next prompt drives.
                continue
            else:
                # Unknown frame: stay silent rather than guess (mirrors the decider's bias).
                continue
    except WebSocketDisconnect:
        pass
    finally:
        # Close the turn with the brain's last verdict so a downstream Twilio Function
        # (or the call log) can see what Anticipy decided on this call.
        with suppress(Exception):
            await ws.send_json({"type": "end", "handoffData": last_handoff})
        core.glassbox.log("conversation_relay", {"event": "disconnected"})


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
