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
import base64
import hashlib
import json
import hmac
import ipaddress
import os
import secrets
import socket
import tempfile
import time
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Optional
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from json import JSONDecodeError
from pydantic import BaseModel, Field

from . import __version__
from .agent import WebVoyagerAgent, judge
from .agent import events as agent_events
from .capture.transcribe import is_audio_file, transcribe_audio
from .channels.conversation_relay import (
    ConversationRelayBrain,
    OnboardingCallBrain,
    stream_tokens,
    voice_execute_enabled,
)
from .channels.inbound import InboundPoller
from .core.control_core import ControlCore
from .core import registry
from .core.registry import current_core
from .core.pairing_codes import mint_pairing_code, per_user_hands_enabled, verify_pairing_code
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
# Twilio request-signature header (sent on the /cr WS upgrade). When TWILIO_AUTH_TOKEN
# is configured we can verify a non-local caller IS Twilio even without an owner token.
TWILIO_SIGNATURE_HEADER = "x-twilio-signature"
# /cr per-call caps so a single connection can't drive the decider brain unbounded
# (defence-in-depth alongside the fail-closed handshake gate). Generous for a real
# human call; overridable for tests/ops, hard-floored so a 0/garbage value can't disable it.
CR_MAX_TURNS = 200            # spoken owner turns answered per call
CR_MAX_CALL_SECONDS = 3600.0  # wall-clock lifetime of one /cr socket (1h)
# Cap the in-memory JSON/text body we will read+process synchronously on a single
# request. The ingest/event lanes do heavy work (triage -> gate -> act) per line; one
# enormous body would otherwise pin the event loop. The local file-upload lane keeps its
# own (larger) byte cap (DEFAULT_MAX_UPLOAD_BYTES) because it streams from disk, not body.
# Override with ANTICIPY_MAX_REQUEST_BYTES; a hard ceiling defends against a 0/garbage value.
DEFAULT_MAX_REQUEST_BYTES = 1 * 1024 * 1024  # 1 MiB of request body is already a huge transcript
MAX_REQUEST_BYTES_CEILING = 64 * 1024 * 1024
# Routes whose body is intentionally not size-limited (they validate/stream their own
# payloads): the local-file upload lane caps bytes off disk, not the request body.
REQUEST_SIZE_EXEMPT_PATHS = {"/owner/ingest-file"}

# The DEFAULT brain (unchanged): one global ControlCore at the existing base data_dir.
# Per-user isolation routes signed-in REQUESTS to their own core via the registry, but THIS
# object stays the default — so the suite (which imports `core` and also drives it over HTTP
# unauthenticated), local dev, and the startup/proactive/background paths all keep hitting
# this exact object exactly as before.
core = ControlCore()
# Wire the registry: any NON-default user's core is built by this factory at <base>/users/<id>;
# the default user maps to the `core` above (so unauthenticated == the module-global core).
registry.set_factory(lambda data_dir, user_id: ControlCore(data_dir=data_dir, user_id=user_id))
registry.register_default(core)
extension_hello_seen = False
_mic_source = None  # the always-on Mac-mic CaptureSource when /listen/start is on (None when off)
_proactive_health = {
    "armed": False,
    "interval_s": 0.0,
    "reason": "Manual-only: background anticipation clock is disabled.",
}
# Real reasoning+vision model for the web-agent loop (kept separate from the
# core's default gateway so the engine/hands tests stay free + deterministic).
gateway_agent = ModelGateway(
    provider=PROVIDER_OPENROUTER,
    # Models come from env (the configured truth in .env*), falling back to the working
    # gemini-2.5 family. The cheap tier handles routine see-and-locate steps; the smart tier
    # handles planning / recovery / stuck / the read-back judge.
    cheap_model=os.environ.get("ANTICIPY_MODEL_CHEAP", "google/gemini-2.5-flash-lite"),
    smart_model=os.environ.get("ANTICIPY_MODEL_SMART", "google/gemini-2.5-flash"),
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
        try:
            _maybe_deliver_daily_digest()
        except Exception as e:  # noqa: BLE001 — digest delivery must never kill the clock
            core.glassbox.log("digest_scheduler_error", {"error": f"{type(e).__name__}: {e}"})


def _maybe_deliver_daily_digest() -> None:
    """Once per local day, at/after ANTICIPY_DIGEST_HOUR (0-23), deliver the NF10 digest.

    Default: env unset -> OFF (zero behavior change; the suite never sees this). Fire-once per
    day via a durable stamp (data_dir/digest_last.json), mark-before-send like trigger_tick's
    D16 stamp so a crash mid-send can't double-deliver. A quiet day sends nothing."""
    raw = (os.environ.get("ANTICIPY_DIGEST_HOUR", "") or "").strip()
    if raw == "":
        return
    try:
        hour = max(0, min(23, int(raw)))
    except ValueError:
        return
    import datetime as _dt
    try:
        tz, _name = core._owner_timezone()   # returns (tzinfo, name)
    except Exception:
        tz = None
    now_local = _dt.datetime.now(tz) if tz else _dt.datetime.now()
    if now_local.hour < hour:
        return
    stamp_path = core.data_dir / "digest_last.json"
    today = now_local.strftime("%Y-%m-%d")
    try:
        if json.loads(stamp_path.read_text(encoding="utf-8")).get("date") == today:
            return
    except Exception:
        pass
    stamp_path.write_text(json.dumps({"date": today}), encoding="utf-8")  # mark BEFORE send
    core.proactive.deliver_digest()


async def _derive_scheduler(interval_s: float) -> None:
    """The anticipation clock (FIX-07): periodically derive unspoken needs. OFF unless
    ANTICIPY_DERIVE_SECONDS > 0 — zero behavior change until Omar turns it on. A failed
    pass is logged and the clock lives on."""
    while True:
        await asyncio.sleep(interval_s)
        try:
            await core.derive_tick()
        except Exception as e:  # noqa: BLE001 — the clock must outlive any one pass
            core.glassbox.log("derive_tick_error", {"error": f"{type(e).__name__}: {e}"})


async def _inbound_scheduler(poller: InboundPoller, interval_s: float) -> None:
    """Poll Twilio for the owner's SMS replies (YES/NO resolves asks; speech ingests).
    Live-env-gated at startup; a poll failure is logged and the loop lives on."""
    while True:
        await asyncio.sleep(interval_s)
        try:
            await poller.poll_once()
        except Exception as e:  # noqa: BLE001 — the poller must outlive any one pass
            core.glassbox.log("inbound_poll_error", {"error": f"{type(e).__name__}: {e}"})


def _arm_proactive_health(interval_s: float, armed: bool) -> dict:
    """Record whether the background anticipation clock is armed. Status only; no side effects."""
    global _proactive_health
    _proactive_health = {
        "armed": bool(armed),
        "interval_s": float(interval_s or 0),
        "reason": (
            f"Self-firing every {float(interval_s):g}s."
            if armed
            else "Manual-only: background anticipation clock is disabled."
        ),
    }
    return _proactive_health


@asynccontextmanager
async def lifespan(app: FastAPI):
    await core.start()
    # ANTICIPY_TICK_SECONDS=0 disables the scheduler (deterministic tests use POST /trigger/tick)
    interval_s = float(os.environ.get("ANTICIPY_TICK_SECONDS", "30") or 0)
    tick_task = asyncio.create_task(_trigger_scheduler(interval_s)) if interval_s > 0 else None
    _arm_proactive_health(interval_s, tick_task is not None)
    # The anticipation clock (FIX-07): derive unspoken needs. Default 0 = OFF.
    derive_s = float(os.environ.get("ANTICIPY_DERIVE_SECONDS", "0") or 0)
    derive_task = asyncio.create_task(_derive_scheduler(derive_s)) if derive_s > 0 else None
    # Inbound SMS poll: ONLY with the live channel env (creds + mode) — suite, stub and
    # mock runs never construct a transport. ANTICIPY_INBOUND_POLL_SECONDS=0 disables.
    inbound_s = float(os.environ.get("ANTICIPY_INBOUND_POLL_SECONDS", "15") or 0)
    inbound_task = (asyncio.create_task(_inbound_scheduler(InboundPoller(core), inbound_s))
                    if inbound_s > 0 and InboundPoller.live_ready() else None)
    try:
        yield
    finally:
        for task in (tick_task, derive_task, inbound_task):
            if task is not None:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
        # Stop the default core AND every per-user core built during this process's life so
        # no bus runner task is left dangling on shutdown.
        for c in registry.all_cores():
            with suppress(Exception):
                await c.stop()


app = FastAPI(
    title="Anticipy Engine",
    version=__version__,
    description="Local-first hub for Anticipy. Binds to 127.0.0.1 only.",
    lifespan=lifespan,
)

# CORS (sweep r2): the engine is local-first, but the app/onboard UI can be opened off-origin (a hosted
# build, or a dev server on another localhost port) and still needs to reach the local engine from the
# browser. This is a browser-enforced VISIBILITY policy only — it never authenticates anyone, so it does
# NOT weaken the owner-token gate (every request still needs a valid token when one is set). Explicit
# allowlist, never "*"; the owner token rides as a header (not a cookie), so credentials stay OFF.
_DEFAULT_CORS_ORIGINS = (
    "http://localhost:3000", "http://127.0.0.1:3000",
    "https://anticipy.ai", "https://www.anticipy.ai", "https://app.anticipy.ai",
    "https://anticipy-welcome.vercel.app",
)


def _cors_origins() -> list:
    extra = (os.environ.get("ANTICIPY_CORS_ORIGINS", "") or "").replace(",", " ").split()
    seen: dict = {}
    for o in (*_DEFAULT_CORS_ORIGINS, *(x.strip().rstrip("/") for x in extra if x.strip())):
        seen.setdefault(o, None)
    return list(seen)


try:
    from fastapi.middleware.cors import CORSMiddleware
    app.add_middleware(
        CORSMiddleware, allow_origins=_cors_origins(), allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "x-anticipy-owner-token"])
except Exception:
    pass


def _owner_api_token() -> str:
    return (os.environ.get(OWNER_API_TOKEN_ENV) or "").strip()


def _owner_api_authorized(request: Request, token: str) -> bool:
    supplied = (request.headers.get(OWNER_TOKEN_HEADER) or "").strip()
    auth = (request.headers.get("authorization") or "").strip()
    if not supplied and auth.lower().startswith("bearer "):
        supplied = auth[7:].strip()
    return bool(supplied) and secrets.compare_digest(supplied, token)


def _ws_owner_token_supplied(ws: WebSocket) -> str:
    """Extract a presented owner token from the WS handshake (?token=, header, bearer).
    Twilio ConversationRelay cannot set custom headers, so the ?token= query param is the
    primary carrier; header/bearer are honored for other clients."""
    supplied = (ws.query_params.get("token") or "").strip()
    if not supplied:
        header = (ws.headers.get(OWNER_TOKEN_HEADER) or "").strip()
        auth = (ws.headers.get("authorization") or "").strip()
        if header:
            supplied = header
        elif auth.lower().startswith("bearer "):
            supplied = auth[7:].strip()
    return supplied


def _ws_is_local(ws: WebSocket) -> bool:
    """True only when the WS peer is the loopback interface (real localhost dev) or the
    in-process Starlette TestClient (the deterministic suite, never a network peer).

    A public-deploy attacker connects from a routable address, so this is False for them —
    which is exactly what flips the /cr gate from fail-OPEN to fail-CLOSED. We never trust
    Host/Forwarded headers here (spoofable); only the transport-level peer address counts."""
    client = ws.client
    host = (getattr(client, "host", None) or "").strip()
    if not host:
        # No peer address at all -> cannot prove local; fail closed.
        return False
    # Starlette's in-process TestClient reports this fixed sentinel (not a real socket).
    # It is impossible to reach over the network, so honoring it keeps the suite/dev open
    # without opening any real remote path.
    if host == "testclient":
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    # Unwrap IPv4-mapped IPv6 (::ffff:127.0.0.1) so a v4 loopback can't hide behind v6.
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return ip.is_loopback


def _twilio_signature_valid(ws: WebSocket) -> bool:
    """Verify the Twilio X-Twilio-Signature on the /cr WS upgrade WITHOUT the twilio SDK.

    Twilio signs base64(HMAC-SHA1(auth_token, full_url + sorted_concat(POST params))).
    A WS GET upgrade carries no POST params, so the signed string is just the URL Twilio
    was configured to dial — our trusted ANTICIPY_CR_WSS_URL (we validate against the value
    WE published, never a caller-supplied/spoofable Host header). Returns False unless both
    TWILIO_AUTH_TOKEN and ANTICIPY_CR_WSS_URL are configured and the signature matches."""
    auth_token = (os.environ.get("TWILIO_AUTH_TOKEN") or "").strip()
    signed_url = (os.environ.get("ANTICIPY_CR_WSS_URL") or "").strip()
    if not auth_token or not signed_url:
        return False
    supplied = (ws.headers.get(TWILIO_SIGNATURE_HEADER) or "").strip()
    if not supplied:
        return False
    mac = hmac.new(auth_token.encode("utf-8"), signed_url.encode("utf-8"), hashlib.sha1)
    expected = base64.b64encode(mac.digest()).decode("ascii")
    return secrets.compare_digest(supplied, expected)


def _owner_ws_authorized(ws: WebSocket) -> bool:
    """Auth gate for owner WebSockets (e.g. Twilio ConversationRelay /cr), checked BEFORE
    ws.accept() because the HTTP owner-token middleware never runs for a WS handshake.

    A valid Twilio request-signature always authorizes (a proven real Twilio caller, no
    owner token needed). Otherwise:
      * Token CONFIGURED  -> the caller MUST present that token (?token=/header/bearer);
        locality grants no bypass (preserves the strict owner-token contract).
      * Token NOT configured -> allowed ONLY from loopback/localhost (real dev) or the
        in-process TestClient (suite). This is the fix: a token-less PUBLIC deploy no longer
        waves through a routable-address connect, so nobody on the internet can drive the
        decider brain unauthenticated. Twilio still gets in via the signature branch above."""
    # A proven Twilio caller is always allowed (the voice line works on a signature-only
    # deploy, with or without an owner token).
    if _twilio_signature_valid(ws):
        return True
    token = _owner_api_token()
    if token:
        # Token configured: the only other way in is presenting it. No local bypass.
        supplied = _ws_owner_token_supplied(ws)
        return bool(supplied) and secrets.compare_digest(supplied, token)
    # No token configured: open for loopback/localhost dev (and the in-process suite),
    # FAIL CLOSED for any remote/public peer.
    return _ws_is_local(ws)


def _pairing_claim_public(path: str) -> bool:
    """True only for the signed-pairing CLAIM endpoint, and only while per-user hands is enabled.

    The extension presents an HMAC-signed pairing code (its own auth) with no Supabase bearer, so
    /ws/pair must bypass the owner-token gate — but the mint endpoint (/ws/pair_code) must NOT,
    since it needs the signed-in user's identity. OFF by default -> always False (byte-identical)."""
    return per_user_hands_enabled() and path == "/ws/pair"


@app.middleware("http")
async def owner_api_auth(request: Request, call_next):
    """Auth guard + per-user identity.

    Local dev / the deterministic suite keep ANTICIPY_OWNER_API_TOKEN unset (everything open). When a
    token IS set (the public deploy), a request is authorized by EITHER the owner token (local/admin) OR
    a valid signed-in Supabase user (a Bearer access token). A valid Supabase login also tags
    request.state.user_id / user_email so handlers can key per-user data. /health stays public.
    """
    # Resolve the signed-in Supabase user, if a Bearer is present (cached + off-loop so it never blocks).
    request.state.user_id = None
    request.state.user_email = None
    _auth = (request.headers.get("authorization") or "").strip()
    _bearer = (request.headers.get(OWNER_TOKEN_HEADER) or "").strip()
    if not _bearer and _auth.lower().startswith("bearer "):
        _bearer = _auth[7:].strip()
    if _bearer and _bearer.count(".") == 2:   # only JWTs (not the opaque owner token) hit Supabase
        from fastapi.concurrency import run_in_threadpool
        from .core.auth import verify_supabase_token
        info = await run_in_threadpool(verify_supabase_token, _bearer)
        if info:
            request.state.user_id = info["user_id"]
            request.state.user_email = info["email"]

    token = _owner_api_token()
    # B12: the signed-pairing CLAIM endpoint (/ws/pair) authenticates via its OWN HMAC code — the
    # extension carries no Supabase bearer — so it bypasses owner auth, but ONLY when per-user hands
    # is enabled. OFF by default -> _pairing_claim_public() is always False -> this line is
    # byte-identical to before, and the endpoint itself still 404s while the flag is off.
    if token and request.url.path not in PUBLIC_PATHS and not _pairing_claim_public(request.url.path):
        if not (_owner_api_authorized(request, token) or request.state.user_id):
            return JSONResponse(
                {"error": "unauthorized", "message": "Sign in to use Anticipy."},
                status_code=401,
                headers={"www-authenticate": "Bearer"},
            )

    # Per-user data isolation: bind THIS request to its user's core. A signed-in Supabase
    # user gets their own (request.state.user_id); the owner-token/local/suite path leaves
    # user_id None -> the DEFAULT core (registry maps None -> default_user()). current_core()
    # in the handlers below then resolves to the right per-user ControlCore. Reset in finally
    # so the binding never leaks to the next request on this task/thread.
    _user_token = registry.set_current_user(request.state.user_id)
    try:
        return await call_next(request)
    finally:
        registry.reset_current_user(_user_token)


def _max_request_bytes() -> int:
    """The body-size cap (bytes). Configurable, but bounded to a sane ceiling so a
    garbage/zero override can never disable the guard or open an unbounded read."""
    try:
        raw = int(os.environ.get("ANTICIPY_MAX_REQUEST_BYTES", "") or DEFAULT_MAX_REQUEST_BYTES)
    except (TypeError, ValueError):
        raw = DEFAULT_MAX_REQUEST_BYTES
    if raw <= 0:
        raw = DEFAULT_MAX_REQUEST_BYTES
    return min(raw, MAX_REQUEST_BYTES_CEILING)


def _too_large_response(limit: int) -> JSONResponse:
    return JSONResponse(
        {"error": "payload_too_large", "message": f"Request body exceeds {limit} bytes.", "limit": limit},
        status_code=413,
    )


@app.middleware("http")
async def request_size_cap(request: Request, call_next):
    """Reject an oversized request body with 413 BEFORE any heavy synchronous work.

    One huge /event (or /owner/ingest) body would otherwise drive triage->gate->act on a
    giant string and pin the event loop. We reject in two layers: (1) a declared
    Content-Length over the cap is refused immediately (no read), and (2) the body is
    read with a hard cap so a missing/understated Content-Length (chunked, or a lying
    client) still cannot smuggle an unbounded body past the gate. The upload-from-disk
    lane is exempt — it caps bytes off disk, not the request body.
    """
    if request.method in ("POST", "PUT", "PATCH") and request.url.path not in REQUEST_SIZE_EXEMPT_PATHS:
        limit = _max_request_bytes()
        declared = request.headers.get("content-length")
        if declared is not None:
            try:
                if int(declared) > limit:
                    return _too_large_response(limit)
            except (TypeError, ValueError):
                pass  # malformed Content-Length: fall through to the read-size guard
        # Defend against a missing/understated Content-Length: read the body here with a
        # hard cap. Caching it on request._body lets the downstream handler re-read it
        # (Starlette's Request.body() returns the cached bytes) without a second read.
        body = b""
        async for chunk in request.stream():
            body += chunk
            if len(body) > limit:
                return _too_large_response(limit)
        request._body = body
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


class ForgetMeIn(BaseModel):
    # RIGHT-TO-DELETE (M5) is gated like the money hard-stop: destructive + irreversible, so it
    # NEVER fires by accident. The caller must echo the exact confirm phrase.
    confirm: str = ""


class RecallIn(BaseModel):
    # Read-only SEMANTIC recall probe ("what do you know relevant to <query>?"). Runs the
    # existing hybrid retriever; writes nothing, fires nothing. Exposes retrieval-by-meaning so
    # paraphrase recall can be proven end-to-end (stub embed can't; Gemini cloud can).
    query: str = ""
    k: int = 8


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


def _readiness(channels: dict, core) -> dict:
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


def _user_vault_connected(core) -> bool:
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


def _connect_readiness(core) -> dict:
    """The guided 'Connect your accounts' checklist. For each capability that unlocks a
    LIVE owner action, report {capability, status: live|needs_connect, what_to_do} using
    PRESENCE/ABSENCE of config only — never a secret value, number, or token. This turns
    the live-unlock into an honest checklist the owner can work through; it grants nothing
    and connects nothing."""
    channels = core.channel_status()

    # Google / Arcade — the API hand. Live needs the shared ARCADE_API_KEY OR this user's
    # per-user vault connection, AND the hand running in live mode.
    arcade_key = _env_present("ARCADE_API_KEY")
    per_user_vault = _user_vault_connected(core)
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
    return _connect_readiness(current_core())


class ChannelModeIn(BaseModel):
    mode: str  # "mock" | "live"


@app.get("/channels/mode")
def channels_mode_get() -> dict:
    """Current comms-line mode + readiness for the Settings mock/live toggle.

    Read-only. Reports mode (mock/live), whether the credentials and owner contact needed to
    actually go live are present, and a human label — presence/absence of config only, never a
    secret value or the phone number. The one honest source the toggle button reads."""
    return current_core().channel_status()


@app.post("/channels/mode")
def channels_mode_set(body: ChannelModeIn) -> dict:
    """Flip the comms line between MOCK (nothing real leaves the machine) and LIVE (real
    text/call) — the single Settings button. Process-local: it sets ANTICIPY_CHANNELS_MODE,
    which every send path re-reads at call time, so the flip is immediate and consistent across
    text, call, and the inbound reply poll. Going LIVE still needs the credentials + owner phone;
    the returned status reports if they're missing, and the send path stays mock-safe until they
    are present — flipping the intent never fabricates a live transport out of thin config."""
    mode = (body.mode or "").strip().lower()
    if mode not in {"mock", "live"}:
        raise HTTPException(status_code=400, detail="mode must be 'mock' or 'live'")
    os.environ["ANTICIPY_CHANNELS_MODE"] = mode
    c = current_core()
    c.glassbox.log("channels_mode_set", {"mode": mode})
    return c.channel_status()


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": ENGINE_NAME, "version": __version__}


@app.get("/status")
def status() -> dict:
    c = current_core()
    channels = c.channel_status()
    proactive = dict(_proactive_health)
    proactive["outreach"] = channels.get("mode", "mock")
    return {
        "engine": "ok",
        "core": "control_core",
        "extension_connected": extension_hello_seen or c.browser_link.connected,
        "history_count": len(c.memory.history.all()),
        "open_loop_count": c.memory_open_loops(limit=0)["count"],
        "pending_count": len(c.pending_asks()),
        "memory_recovered": bool(getattr(c.memory.db, "recovered_corruption", False)),
        "channels": channels,
        "proactive": proactive,
        "readiness": _readiness(channels, c),
    }


@app.post("/capture")
async def capture(body: CaptureIn) -> dict:
    if body.source not in EventSource._value2member_map_:
        raise HTTPException(status_code=400, detail=f"unknown capture source: {body.source}")
    return await current_core().feed(body.source, body.text, {"legacy_capture": True})


@app.get("/memory/history")
def history() -> dict:
    return {"items": [i.model_dump() for i in current_core().memory.history.all()]}


@app.get("/memory/drawers")
def memory_drawers() -> dict:
    """Read surface for all four memory drawers — count + recent items each (the dossier writes land in
    profile [stated] and derived [inferred]). Fixes the harness G4 read + the missing-read-surface gap."""
    c = current_core()
    def snap(store):
        items = store.all()
        return {"count": len(items), "recent": [i.model_dump() for i in items[-15:]]}
    return {"drawers": {
        "profile": snap(c.memory.profile),
        "derived": snap(c.memory.derived),
        "open_loops": snap(c.memory.open_loops),
        "history": snap(c.memory.history),
    }}


@app.post("/memory/recall")
def memory_recall(body: RecallIn) -> dict:
    """Read-only SEMANTIC recall surface: "what do you know that's relevant to <query>?".

    Runs the existing hybrid retriever (semantic + keyword + recency + importance) over the
    fuzzy drawers (profile/history/derived) and returns the surfaced items, ranked, plus the
    best semantic score. It is a pure READ — it writes nothing and fires no action. Its purpose
    is to make retrieval-by-MEANING observable end-to-end: with the on-device stub embedder a
    keyword-disjoint paraphrase scores ~0 and the fact is filtered out; with a real embedder
    (Gemini cloud when ANTICIPY_EMBED_PROVIDER=gemini) the paraphrase recalls it. Provider is
    whatever the env selects at call time, so default behavior is the on-device store."""
    c = current_core()
    inj = c.live_memory.inject(body.query or "", k=int(body.k or 8))
    items = inj.get("items", [])
    return {
        "query": body.query,
        "top_relevance": float(inj.get("top_relevance", 0.0)),
        "abstain": bool(inj.get("abstain", True)),
        "embedding_dim": _active_embedding_dim(),
        "count": len(items),
        "items": [{"kind": i.kind, "text": i.text, "fields": i.fields} for i in items],
        "text": inj.get("text", ""),
    }


def _active_embedding_dim() -> int:
    """The width of the ACTIVE embedder (768 for live Gemini, 256 for the stub) — lets a caller
    prove the cloud embedder is really in use, not a silent fallback to on-device."""
    try:
        from .memory.embed import embedding_dim
        return int(embedding_dim())
    except Exception:
        return 0


# The exact phrase the right-to-delete endpoint requires (money-stop-grade confirmation).
_FORGET_CONFIRM = "DELETE MY DATA"


@app.post("/memory/forget-me")
def memory_forget_me(body: ForgetMeIn) -> dict:
    """RIGHT-TO-DELETE (M5), gated like the money hard-stop: wipe EVERY trace of the user — all
    four drawers AND the inert remember-list. Irreversible, so it requires the exact confirm
    phrase; without it nothing is touched (default-deny)."""
    if (body.confirm or "").strip() != _FORGET_CONFIRM:
        return {"deleted": False, "reason": "confirmation required",
                "confirm_phrase": _FORGET_CONFIRM}
    core = current_core()
    res = core.live_memory.forget_all()
    # right-to-delete also wipes the temporal knowledge graph (Phase 4) for this scope, so a
    # forget clears people/relationships too. Flag-gated + fail-safe: when the graph is off
    # (default) ``context.graph`` is None and this no-ops, byte-identical to before.
    graph_removed = 0
    try:
        ctx = getattr(core, "context", None)
        if ctx is not None and getattr(ctx, "graph", None) is not None:
            graph_removed = int(ctx.graph.clear_scope())
    except Exception:
        graph_removed = 0
    return {"deleted": True, "removed": res["removed"], "graph_removed": graph_removed}


@app.get("/proactive/gateway/recent")
def proactive_gateway_recent(limit: int = 50) -> dict:
    """Recent Plan Baby Steps gateway events across browser, memory, voice/text, and app lanes."""
    return current_core().proactive_gateway_recent(limit=limit)


@app.get("/memory/open-loops")
def memory_open_loops(limit: int = 50) -> dict:
    return current_core().memory_open_loops(limit=limit)


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
    cap = current_core().live_memory.capturer
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
    return await current_core().approve_remembered(body.line_id)


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
    return current_core().dryrun_remembered(body.line_id)


@app.get("/memory/remembered/dryrun-day")
def memory_remembered_dryrun_day(limit: int = 50) -> dict:
    """LIVE DRY-RUN PREVIEW for the WHOLE day — preview every remembered line at once so the
    owner can see his entire day's planned real actions before connecting any account.

    Reuses the inert remembered pull and dry-runs EACH line through the SAME press-go
    mapping (no execution, no Goal, no orchestrator call). Returns the per-line previews
    plus a count of how many WOULD execute on connect."""
    c = current_core()
    cap = c.live_memory.capturer
    rows = cap.remember.recent(limit)
    previews = [c.dryrun_remembered(str(r.get("id"))) for r in rows]
    would = sum(1 for p in previews if p.get("would_execute"))
    return {"previews": previews, "count": len(previews), "would_execute_count": would}


@app.post("/memory/open-loops/resolve")
def memory_loop_resolve(body: MemoryLoopResolveIn) -> dict:
    out = current_core().resolve_memory_loop(body.id, body.status)
    if not out.get("resolved"):
        raise HTTPException(status_code=400, detail=out.get("reason") or "could not resolve memory loop")
    return out


@app.post("/connections/authorize")
def connection_authorize(body: ConnectionAuthorizeIn) -> dict:
    out = current_core().authorize_connection_loop(body.id)
    if not out.get("ok"):
        raise HTTPException(status_code=400, detail=out.get("reason") or "could not prepare connection")
    return out


@app.post("/extension/hello")
def extension_hello(body: ExtensionHello) -> dict:
    global extension_hello_seen
    extension_hello_seen = True
    current_core().glassbox.log("extension_hello", {"client": body.client})
    return {"connected": True, "client": body.client, "core": "control_core"}


# ---- control core ----
@app.post("/event")
async def event(body: EventIn) -> dict:
    return await current_core().feed(body.source, body.text, body.meta)


@app.post("/owner/ingest")
async def owner_ingest(body: OwnerIngestIn) -> dict:
    """One shared Action Engine intake for typed transcript, MP3, listening, and pay-to-try."""
    return await current_core().owner_ingest(body.source, body.text, body.meta, execute_actions=body.execute_actions)


@app.post("/owner/ingest-file")
async def owner_ingest_file(body: OwnerFileIngestIn) -> dict:
    """Read one uploaded local file, then use the same owner-ingest path as typed text."""
    c = current_core()
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
                c.glassbox.log(
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

    c.glassbox.log("owner_upload_ingest", {"filename": filename, "source": source, "kind": meta["upload_kind"]})
    return await c.owner_ingest(source, text, meta, execute_actions=body.execute_actions)


# ---- ALWAYS-ON LISTENING: the Mac mic, heard text -> the proactive brain ----
@app.post("/listen/start")
async def listen_start() -> dict:
    """Turn on always-on listening: capture the Mac mic in rolling windows, transcribe locally
    with Whisper, and feed every heard utterance into owner_ingest (execute=on) so the brain
    decides act/ask/silent on your real day. Words only until the brain decides; money still asks."""
    global _mic_source
    if _mic_source is not None and _mic_source.running:
        current_core().gateway_ledger.record_listen_status(
            source="mac_mic", listening=True,
            details={"already_running": True, "device": _mic_source._device})
        return {"listening": True, "already_running": True, "device": _mic_source._device}
    loop = asyncio.get_running_loop()
    # Capture THIS caller's core now; the mic-thread sink fires later with NO request context
    # (current_core() would resolve to the default there), so the stream must stay bound to
    # the user who started it.
    c = current_core()

    def _sink(event) -> None:  # called FROM the mic thread; bounce onto the engine loop
        c.glassbox.log("mic_heard", {"text": (event.text or "")[:200]})
        try:
            asyncio.run_coroutine_threadsafe(
                c.owner_ingest(event.source, event.text, {"capture": "mac_mic"}, execute_actions=True),
                loop)
        except Exception as exc:  # noqa: BLE001 — a sink failure must not kill the mic loop
            c.glassbox.log("mic_sink_error", {"error": f"{type(exc).__name__}: {exc}"})

    from .capture.mac_mic import MacMicSource
    _mic_source = MacMicSource(_sink)
    _mic_source.start()
    c.glassbox.log("listen", {"event": "started", "device": _mic_source._device,
                                 "window_seconds": _mic_source._window})
    c.gateway_ledger.record_listen_status(
        source="mac_mic",
        listening=True,
        details={"device": _mic_source._device, "window_seconds": _mic_source._window},
    )
    return {"listening": True, "device": _mic_source._device, "window_seconds": _mic_source._window,
            "note": "Anticipy is listening on your Mac mic now — just talk; it acts on what it hears."}


@app.post("/listen/stop")
async def listen_stop() -> dict:
    global _mic_source
    windows = getattr(_mic_source, "windows", 0)
    utterances = getattr(_mic_source, "utterances", 0)
    if _mic_source is not None:
        _mic_source.stop()
        current_core().glassbox.log("listen", {"event": "stopped", "windows": windows, "utterances": utterances})
        current_core().gateway_ledger.record_listen_status(
            source="mac_mic",
            listening=False,
            status="stopped",
            details={"windows": windows, "utterances": utterances},
        )
    _mic_source = None
    return {"listening": False, "windows": windows, "utterances": utterances}


@app.get("/listen/status")
async def listen_status() -> dict:
    s = _mic_source
    return {"listening": bool(s and s.running), "device": getattr(s, "_device", None),
            "window_seconds": getattr(s, "_window", None), "windows": getattr(s, "windows", 0),
            "utterances": getattr(s, "utterances", 0), "last_error": getattr(s, "last_error", None)}


@app.websocket("/listen/stream")
async def listen_stream_ws(ws: WebSocket):
    """Real-time streaming transcription via Deepgram.
    Browser sends raw audio (WebM/Opus or linear16). We proxy to Deepgram's
    streaming API with speaker diarization, smart formatting, and endpointing.
    Returns real-time transcript chunks with speaker labels.
    When silence is detected (endpointing), we auto-feed the accumulated
    transcript into the owner ingest pipeline."""
    await ws.accept()
    # A WS upgrade does not pass through the HTTP auth middleware, so the per-user contextvar
    # is unset here -> current_core() returns the DEFAULT (owner) core, which is correct for
    # this local Mac-mic/Deepgram stream. Bind it once so the long-lived recv loop is stable.
    c = current_core()

    dg_key = os.environ.get("DEEPGRAM_API_KEY", "")
    if not dg_key:
        c.gateway_ledger.record_listen_status(
            source="browser_mic",
            listening=False,
            status="unavailable",
            details={"reason": "deepgram_not_configured"},
        )
        await ws.send_json({"type": "error", "message": "DEEPGRAM_API_KEY not configured"})
        await ws.close()
        return

    import websockets as _ws

    dg_url = (
        "wss://api.deepgram.com/v1/listen?"
        "model=nova-2&language=en&smart_format=true&diarize=true"
        "&interim_results=true&utterance_end_ms=1500&vad_events=true"
        "&endpointing=500&encoding=linear16&sample_rate=16000&channels=1"
    )
    dg_headers = {"Authorization": f"Token {dg_key}"}

    accumulated_transcript = []
    last_final_time = time.time()

    try:
        async with _ws.connect(dg_url, additional_headers=dg_headers) as dg_ws:
            c.glassbox.log("listen_stream", {"event": "deepgram_connected"})

            async def _dg_recv():
                """Read from Deepgram and forward transcription to the browser."""
                nonlocal last_final_time
                try:
                    async for raw in dg_ws:
                        import json as _json
                        try:
                            msg = _json.loads(raw)
                        except Exception:
                            continue
                        msg_type = msg.get("type", "")
                        if msg_type == "Results":
                            channel = msg.get("channel", {})
                            alt = (channel.get("alternatives") or [{}])[0]
                            transcript = alt.get("transcript", "")
                            is_final = msg.get("is_final", False)
                            speech_final = msg.get("speech_final", False)
                            words = alt.get("words", [])
                            # Build speaker-labeled segments
                            segments = []
                            cur_speaker = None
                            cur_text = []
                            for w in words:
                                sp = w.get("speaker", 0)
                                if sp != cur_speaker and cur_text:
                                    segments.append({"speaker": cur_speaker, "text": " ".join(cur_text)})
                                    cur_text = []
                                cur_speaker = sp
                                cur_text.append(w.get("punctuated_word", w.get("word", "")))
                            if cur_text:
                                segments.append({"speaker": cur_speaker, "text": " ".join(cur_text)})

                            await ws.send_json({
                                "type": "transcript",
                                "transcript": transcript,
                                "is_final": is_final,
                                "speech_final": speech_final,
                                "segments": segments,
                            })
                            if is_final and transcript.strip():
                                speaker_text = " | ".join(
                                    f"[Speaker {s['speaker']}] {s['text']}" for s in segments
                                ) if segments else transcript
                                accumulated_transcript.append(speaker_text)
                                last_final_time = time.time()
                        elif msg_type == "UtteranceEnd":
                            await ws.send_json({"type": "utterance_end"})
                            # Auto-ingest after utterance end if we have content
                            if accumulated_transcript:
                                full = "\n".join(accumulated_transcript)
                                accumulated_transcript.clear()
                                await ws.send_json({"type": "processing", "text": full})
                                try:
                                    result = await c.owner_ingest(
                                        "start_listening", full,
                                        {"capture": "deepgram_stream"},
                                        execute_actions=True
                                    )
                                    await ws.send_json({"type": "ingest_result", "result": result})
                                except Exception as exc:
                                    await ws.send_json({"type": "ingest_error", "error": str(exc)})
                except _ws.exceptions.ConnectionClosed:
                    pass

            async def _browser_send():
                """Read audio from browser and send to Deepgram."""
                try:
                    while True:
                        data = await ws.receive_bytes()
                        await dg_ws.send(data)
                except WebSocketDisconnect:
                    # Browser disconnected — close Deepgram too
                    await dg_ws.send(b'')  # empty byte to signal end
                except Exception:
                    pass

            # Run both directions concurrently
            recv_task = asyncio.create_task(_dg_recv())
            send_task = asyncio.create_task(_browser_send())
            done, pending = await asyncio.wait(
                [recv_task, send_task], return_when=asyncio.FIRST_COMPLETED
            )
            for t in pending:
                t.cancel()
                with suppress(asyncio.CancelledError):
                    await t

    except Exception as exc:
        c.glassbox.log("listen_stream", {"event": "error", "error": str(exc)})
        with suppress(Exception):
            await ws.send_json({"type": "error", "message": str(exc)})
    finally:
        # If there's leftover transcript, ingest it
        if accumulated_transcript:
            full = "\n".join(accumulated_transcript)
            try:
                await c.owner_ingest("start_listening", full,
                                        {"capture": "deepgram_stream"},
                                        execute_actions=True)
            except Exception:
                pass
        with suppress(Exception):
            c.gateway_ledger.record_listen_status(
                source="browser_mic",
                listening=False,
                status="stopped",
                details={"reason": "stream_disconnected"},
            )
        c.glassbox.log("listen_stream", {"event": "disconnected"})


@app.get("/owner/cards")
def owner_cards(limit: int = 50) -> dict:
    """Recent durable owner cards, so the app board survives reloads."""
    return current_core().owner_cards(limit=limit)


@app.post("/owner/onboard")
async def owner_onboard(body: OwnerOnboardingIn) -> dict:
    """First-run setup writes people, preferences, apps, stores, and gates into memory."""
    return await current_core().owner_onboard(body)


class DiscoverConnectionsIn(BaseModel):
    discovered: list[dict] = Field(default_factory=list)
    source: str = "chrome_scrape"


@app.post("/onboard/discover")
async def onboard_discover(body: DiscoverConnectionsIn) -> dict:
    """Ingest a logged-in-Chrome connection scan (the extension's discover_connections intent)
    and write the per-person mesh via the SAME path typed onboarding uses: each discovered
    logged-in service becomes a profile card + a 'Connect X' open-loop, and a service Anticipy
    already holds a vault token for is marked connected. Discovery only — no credentials entered."""
    return await current_core().onboard_discover(body.discovered, source=body.source)


class ScanIn(BaseModel):
    services: list[dict] = Field(default_factory=list)  # optional [{name,url}]; empty -> extension defaults
    wait: bool = False  # when true, return the extension's actual discovery result
    timeout_s: float = 90.0


@app.post("/onboard/scan")
async def onboard_scan(body: ScanIn) -> dict:
    """TRIGGER the onboarding account-scan in the user's connected Chrome. This is the wiring the
    'scrapes you' step was missing: the engine tells the extension to scan; the extension reads a
    logged-in-vs-signin signal per service and POSTs results back to /onboard/discover. Returns
    triggered=False (no error) when no extension is connected to drive."""
    c = current_core()
    if body.wait:
        timeout_s = max(5.0, min(float(body.timeout_s or 90.0), 240.0))
        result = await c.browser_link.scan_connections(body.services or None, timeout=timeout_s)
        c.glassbox.log("onboard_scan", {
            "triggered": bool(result.get("triggered")),
            "waited": True,
            "services": len(body.services or []),
            "status": result.get("status"),
            "discovered_count": len(result.get("discovered") or []),
            "posted": bool(result.get("posted")),
        })
        result["note"] = ("scan completed in your Chrome; results were posted to /onboard/discover"
                          if result.get("posted") else "scan completed, but the extension did not confirm posting")
        return result
    triggered = await c.browser_link.discover_connections(body.services or None)
    c.glassbox.log("onboard_scan", {"triggered": triggered, "waited": False, "services": len(body.services or [])})
    return {"triggered": triggered, "note": ("scan started in your Chrome; results arrive via "
            "/onboard/discover" if triggered else "no browser extension connected")}


class OwnerScrapeIn(BaseModel):
    cdp_url: Optional[str] = None
    max_chars: int = 6000


@app.post("/onboard/owner-scrape")
async def onboard_owner_scrape(body: OwnerScrapeIn) -> dict:
    """FULL-BROWSER owner self-scrape (the 'Anticipy scrapes YOU' step).

    Reads the owner's OWN logged-in Gmail / sent mail / Calendar / Contacts /
    LinkedIn over CDP (read-only, money nav-wall still on), then the REAL smart
    model synthesizes a graded dossier — identity, work, the people who matter,
    family, tools, the sites the browser arm will ACT on (full-browser, NOT an
    API), and the gaps to ask about — which is written to memory (stated facts ->
    profile drawer, inferred -> derived drawer). Honest by construction: a surface
    that bounced to a sign-in wall is reported needs_login, never faked, and with
    no usable signals the dossier is empty + carries a clarifying question."""
    from fastapi.concurrency import run_in_threadpool

    from .onboarding import dossier as _dossier
    from .onboarding.owner_scrape import DEFAULT_SURFACES, scrape_owner
    from .onboarding.permissions import SURFACE_SERVICE

    c = current_core()
    # CONSENT GATE (sweep #2/#5): read ONLY services the owner explicitly allowed — never all of them via
    # None. Mirrors run_loop; an exposed route must not bypass the per-service allow gate the product promises.
    allowed = [s for s in DEFAULT_SURFACES
               if c.onboard_permissions.is_allowed(SURFACE_SERVICE.get(s.get("key"), ""))]
    if not allowed:
        return {"dossier": {}, "scrape": {"usable_count": 0, "needs_login": [], "surfaces": []},
                "memory_written": {"profile": 0, "derived": 0},
                "reason": "no service allowed yet — approve at least one account first"}
    signals = await run_in_threadpool(scrape_owner, body.cdp_url, allowed, max_chars=body.max_chars)
    doss = await _dossier.synthesize_dossier(signals, c.gateway)
    counts = _dossier.write_dossier_to_memory(doss, c.memory)
    status = {"usable_count": len(signals.get("logged_in", [])),
              "needs_login": signals.get("needs_login", []),
              "surfaces": [{"key": s.get("key"), "status": s.get("status"), "chars": s.get("chars")}
                           for s in signals.get("surfaces", [])]}
    c.glassbox.log("owner_scrape", {"usable": status["usable_count"],
                                       "needs_login": status["needs_login"], "wrote": counts})
    return {"dossier": doss, "scrape": status, "memory_written": counts}


class DeepScrapeIn(BaseModel):
    scraped: list[dict] = Field(default_factory=list)
    source: str = "chrome_deep_scrape"


@app.post("/onboard/deep-scrape")
async def onboard_deep_scrape(body: DeepScrapeIn) -> dict:
    """Ingest the extension's CONTENT deep-scrape (real Chrome: emails/events/files/...) -> synthesize a
    dossier -> write it to memory. This is the 'scrapes you' step that actually LEARNS about the owner,
    run through their OWN logged-in Chrome (the extension), NOT a CDP debug browser."""
    return await current_core().ingest_deep_scrape(body.scraped, source=body.source)


class DeepReadHandIn(BaseModel):
    targets: list[dict] = Field(default_factory=list)
    source: str = "hand_deep_read"


@app.post("/onboard/deep-read-hand")
async def onboard_deep_read_hand(body: DeepReadHandIn) -> dict:
    """STEP 3: onboarding deep-read driven by the LIVE hand (the connected Chrome) — OPENS + reads each
    target deep across sections (not screenshot-the-first-screen) and lands the learned facts in memory.
    targets=[{url,label,max_steps}]. For real accounts pass _DEEP_SCAN_URLS entries (read-only; a login
    wall -> needs_login surface, never types credentials)."""
    return await current_core().onboard_deep_read_via_hand(body.targets, source=body.source)


# Canonical URLs for a consent-gated content deep-scan: ONLY services the owner allowed are opened.
_DEEP_SCAN_URLS = {
    "gmail": ("Gmail", "https://mail.google.com/mail/u/0/#inbox"),
    "calendar": ("Google Calendar", "https://calendar.google.com/calendar/u/0/r"),
    "drive": ("Google Drive", "https://drive.google.com/drive/my-drive"),
    "linkedin": ("LinkedIn", "https://www.linkedin.com/feed/"),
}


@app.post("/onboard/deep-scan")
async def onboard_deep_scan() -> dict:
    """TRIGGER a CONTENT deep-scrape in the user's connected Chrome — CONSENT-GATED to the services the
    owner allowed (mirrors owner-scrape). The extension reads real content in the user's OWN Chrome and
    POSTs it to /onboard/deep-scrape. Returns triggered=False (no error) when no extension is connected."""
    c = current_core()
    services = [{"name": label, "url": url}
                for key, (label, url) in _DEEP_SCAN_URLS.items()
                if c.onboard_permissions.is_allowed(key)]
    if not services:
        return {"triggered": False, "note": "no service allowed yet — approve at least one account first"}
    triggered = await c.browser_link.deep_scrape(services)
    c.glassbox.log("onboard_deep_scan", {"triggered": triggered, "services": [s["name"] for s in services]})
    return {"triggered": triggered, "services": [s["name"] for s in services],
            "note": ("deep scan started in your Chrome; results arrive via /onboard/deep-scrape"
                     if triggered else "no browser extension connected")}


class OnboardPermissionIn(BaseModel):
    service: str
    allowed: bool = True


@app.get("/onboard/permissions")
def onboard_permissions_get() -> dict:
    """The per-service allow gate (allow Gmail, allow Calendar, ...). Nothing is read until allowed."""
    return current_core().onboard_permissions.state()


@app.post("/onboard/permissions")
def onboard_permissions_set(body: OnboardPermissionIn) -> dict:
    return current_core().onboard_permissions.set(body.service, body.allowed)


class OnboardLoopIn(BaseModel):
    cdp_url: Optional[str] = None
    max_layers: int = 4


@app.post("/onboard/loop")
async def onboard_loop(body: OnboardLoopIn) -> dict:
    """The four-layer onboarding loop: guided layer 1 (allow + login), then autonomous deeper passes —
    scrape ONLY allowed services, rebuild the dossier, report what still needs login + the gaps."""
    from .onboarding.loop import run_loop
    return await run_loop(current_core(), body.cdp_url, body.max_layers)


class OnboardCompleteIn(BaseModel):
    complete: bool = True


@app.get("/onboard/status")
def onboard_status() -> dict:
    """First-run marker (sweep #12): has onboarding been completed/confirmed?"""
    p = current_core().data_dir / "onboard_complete.json"
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"onboarding_complete": False}
    except Exception as exc:
        # fail-open (don't trap a real owner on a corrupt marker), but LEAVE A TRACE so it's diagnosable
        try:
            current_core().glassbox.log("onboard_status_read_error", {"error": f"{type(exc).__name__}: {exc}"})
        except Exception:
            pass
        return {"onboarding_complete": False}


@app.post("/onboard/complete")
def onboard_complete(body: OnboardCompleteIn) -> dict:
    """Persist that the owner confirmed their dossier — the durable 'onboarding done' signal the app
    reads to skip the guided flow on subsequent runs (sweep #12)."""
    import time as _t
    data = {"onboarding_complete": bool(body.complete), "at": _t.time()}
    try:
        (current_core().data_dir / "onboard_complete.json").write_text(json.dumps(data), encoding="utf-8")
    except Exception as exc:
        # NEVER claim done on a failed persist — the next GET /onboard/status would read False and
        # re-trap the owner. Report the failure honestly instead of returning a phantom success.
        try:
            current_core().glassbox.log("onboard_complete_write_error", {"error": f"{type(exc).__name__}: {exc}"})
        except Exception:
            pass
        return {"onboarding_complete": False, "error": "could not persist onboarding completion"}
    return data


# (The /hands/compose-email endpoint was deleted 2026-07-02: it imported hands/cdp_client,
#  a module that does not exist, so every call 500'd — a lie in the API surface. The REAL
#  Gmail compose hand is FIX-13 in PLANS/00_OVERARCHING.md and will be built through the
#  browser-hand path, not resurrected here.)

# Max public source URLs we will read per profile build (keep the read bounded).
ONBOARDING_MAX_SOURCES = 6

# SSRF guard: how many DNS-resolved addresses we will check per source host. A host that
# fans out to more than this is treated as suspicious and rejected (defends both the read
# budget and a host that floods the resolver).
SSRF_MAX_RESOLVED_ADDRS = 32


def _ip_is_public(ip: ipaddress._BaseAddress) -> bool:
    """A single address is safe to fetch ONLY if it is a globally-routable public IP.

    Rejects loopback (127/8, ::1), link-local incl. the cloud-metadata 169.254.169.254
    and IPv6 fe80::/10, private (10/8, 172.16/12, 192.168/16, fc00::/7), reserved,
    multicast, unspecified (0.0.0.0/::), and the CGNAT 100.64/10 (is_global is False).
    IPv4-mapped IPv6 (::ffff:127.0.0.1) is unwrapped first so it cannot smuggle a private
    v4 address past a v6 check."""
    mapped = getattr(ip, "ipv4_mapped", None)
    if mapped is not None:
        ip = mapped
    if (
        ip.is_loopback
        or ip.is_link_local
        or ip.is_private
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    ):
        return False
    return bool(ip.is_global)


def _assert_public_source_url(url: str) -> None:
    """SSRF gate for an onboarding source URL: reject anything that resolves to a
    non-public address BEFORE we hand it to the read-only browser arm.

    Validates the scheme is http(s), extracts the host, and:
      - if the host is a literal IP, classifies it directly;
      - if the host is a name, resolves it (getaddrinfo) and requires EVERY resolved
        address to be public — so `localhost`, an internal name, or a DNS-rebind to a
        private IP is all rejected.
    Raises HTTPException(422) with a non-leaky message on any rejection. The host is never
    echoed back beyond a short, sanitized label."""
    parts = urlsplit(url)
    if parts.scheme.lower() not in ("http", "https"):
        raise HTTPException(status_code=422, detail="source URL must be http(s)")
    host = parts.hostname  # already lowercased, brackets stripped for IPv6
    if not host:
        raise HTTPException(status_code=422, detail="source URL has no host")

    # TEST-ONLY opt-in: allow a local target (localhost/127.0.0.1) ONLY when the operator
    # explicitly sets ANTICIPY_ALLOW_LOCAL_TARGET=1. Used to drive a self-hosted test store
    # on this box; OFF by default so production SSRF hardening is unchanged.
    if os.getenv("ANTICIPY_ALLOW_LOCAL_TARGET") == "1" and host in ("localhost", "127.0.0.1", "::1"):
        return

    # 1) Host is a literal IP address -> classify it directly (no DNS).
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None:
        if not _ip_is_public(literal):
            raise HTTPException(status_code=422, detail="source URL host is not a public address")
        return

    # 2) Host is a name -> resolve and require EVERY resolved address to be public. A name
    # that resolves to ANY non-public address (incl. a DNS-rebind to 169.254.169.254 / a
    # private IP / localhost->127.0.0.1) is rejected. A name that does NOT resolve
    # (NXDOMAIN, a reserved .example/.invalid/.test TLD, or a transient resolver miss) is
    # NOT an SSRF vector — nothing internal can be reached through it — so it is allowed to
    # pass to the read-only browser arm, which fails the read honestly and yields a blocker
    # (never a 422 and never an invented fact). This keeps the gate about WHERE a host
    # points, not whether it currently resolves.
    try:
        infos = socket.getaddrinfo(host, parts.port or None, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        return  # unresolvable: not an SSRF target; let the browser arm degrade honestly
    addrs = []
    for info in infos:
        sockaddr = info[4]
        if not sockaddr:
            continue
        addrs.append(sockaddr[0])
        if len(addrs) > SSRF_MAX_RESOLVED_ADDRS:
            raise HTTPException(status_code=422, detail="source URL host resolves to too many addresses")
    for raw in addrs:
        # Strip a scoped-IPv6 zone id (fe80::1%en0) before parsing.
        candidate = raw.split("%", 1)[0]
        try:
            resolved = ipaddress.ip_address(candidate)
        except ValueError:
            # An address we cannot classify is treated as unsafe (fail closed).
            raise HTTPException(status_code=422, detail="source URL host resolved to an unparseable address")
        if not _ip_is_public(resolved):
            raise HTTPException(status_code=422, detail="source URL host resolves to a non-public address")


def _assert_public_agent_url(url: str) -> None:
    """SSRF gate for the agent-driving endpoints (/agent/run, /agent/resume, /ws/observe,
    /ws/act). The URL the agent is pointed at — the start page, the resumed page, or a driven
    navigate — must be a PUBLIC http(s) host. Reuses the onboarding SSRF classifier so a
    loopback/link-local (incl. 169.254.169.254 cloud-metadata)/private/file:// target is
    rejected with 422 before the live browser agent ever touches it. Empty is rejected too;
    the agent has nowhere safe to go without a URL.

    Note: this is the ENTRY gate. The deeper, code-level navigation WALL (core.navwall) runs
    at the bridge on EVERY navigate the model emits mid-run and additionally blocks
    banking/password destinations — so an injected navigate is stopped even if it never came
    through one of these endpoints."""
    if not (url or "").strip():
        raise HTTPException(status_code=422, detail="agent target URL is required")
    _assert_public_source_url(url)


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
        if not url.lower().startswith(("http://", "https://")):
            continue
        # SSRF gate: the host must resolve to a PUBLIC address. A loopback/link-local
        # (incl. 169.254.169.254 cloud-metadata)/private/internal host is rejected (422)
        # before the read-only browser arm is ever pointed at it.
        _assert_public_source_url(url)
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
    current_core().glassbox.log(
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
    current_core().glassbox.log(
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
    fired = await current_core().proactive.trigger_tick()
    return {"fired": fired}


@app.post("/derive/tick")
async def derive_tick_endpoint() -> dict:
    """TRUE PROACTIVITY (FIX-07): one anticipation pass — derive unspoken needs from memory/
    calendar/open-loops, research the world browser-only, act through the ONE front door,
    text the owner. Deterministic entry for tests/gates; the scheduler calls the same method
    when ANTICIPY_DERIVE_SECONDS > 0."""
    return await current_core().derive_tick()


@app.post("/digest/deliver")
async def digest_deliver() -> dict:
    """Deliver the day's accumulated non-urgent items as ONE message (NF10), then clear.

    Wired 2026-07-02 (FIX-01 Phase 3): deliver_digest existed with NO caller — the queue
    filled forever and never sent. A quiet day returns {"sent": false, "reason": "quiet day"}
    and sends nothing. The scheduler also calls this daily when ANTICIPY_DIGEST_HOUR is set."""
    return current_core().proactive.deliver_digest()


@app.get("/glassbox")
def glassbox(limit: int = 50) -> dict:
    return {"entries": current_core().glassbox.summaries(limit)}


@app.get("/pending")
def pending() -> dict:
    """Room 6: the 'needs you' surface — detrimental actions paused awaiting approve/deny."""
    return {"pending": current_core().pending_asks()}


@app.post("/resolve")
async def resolve(body: ResolveIn) -> dict:
    """Room 6: the app's approve/deny -> resolves the REAL paused goal (brain -> app -> back)."""
    return await current_core().resolve(body.ask_id, body.approved)


class OwnerStopIn(BaseModel):
    card_id: str = ""
    id: str = ""


@app.post("/owner/stop")
async def owner_stop(body: OwnerStopIn) -> dict:
    """STOP control for an 'On it — you can stop me' reversible chore: halt any in-flight/queued work
    and flip the durable card to 'stopped'. Reversible chores only (see stop_owner_card). The app's
    STOP button POSTs {card_id}; without one, it no-ops honestly instead of erroring."""
    cid = (body.card_id or body.id or "").strip()
    if not cid:
        return {"stopped": False, "reason": "no card_id provided"}
    result = current_core().stop_owner_card(cid)
    return result if isinstance(result, dict) else {"stopped": True, "card_id": cid}


class AutonomyModeIn(BaseModel):
    mode: str


@app.get("/owner/autonomy_mode")
def owner_autonomy_mode_get() -> dict:
    """M3: the user-facing autonomy dial — full_send / regular / limited (default regular)."""
    return current_core().get_autonomy_mode()


@app.post("/owner/autonomy_mode")
def owner_autonomy_mode_set(body: AutonomyModeIn) -> dict:
    """M3: set the dial. The two invariants (money/send/irreversible always confirm; low-confidence
    drops a level) hold in EVERY mode — Full-Send only adds reach on reversible, no-money tasks."""
    return current_core().set_autonomy_mode(body.mode)


@app.get("/scorecard")
def scorecard() -> dict:
    return current_core().scorecard.readout()


@app.get("/goals/{goal_id}")
def get_goal(goal_id: str) -> dict:
    g = current_core().store.load(goal_id)
    return g.model_dump(mode="json") if g else {"error": "not found"}


@app.get("/gateway")
def gateway_info() -> dict:
    # Cost counters PLUS the real run-mode signals, so a caller (e.g. the journey gauge's
    # precondition) can VERIFY the engine is actually live — real model + live API hand —
    # rather than assume it. These read the engine's actual wired objects, not env strings.
    c = current_core()
    return {
        "smart_calls": len(c.gateway.smart_calls),
        "total_cost": c.gateway.total_cost(),
        "provider": c.gateway.provider,
        "cheap_model": c.gateway.cheap_model,
        "smart_model": c.gateway.smart_model,
        "api_hands_mode": c.api_hand.mode,
    }


# ---- browser hand link (authenticated WebSocket) ----
# Note: browser_link drives a real Chrome over a WS the extension dials into /ws/extension
# (which attaches to the DEFAULT core's link). A signed-in remote user gets THEIR OWN core's
# (unconnected) link, so they can never pilot the owner's Chrome — correct isolation.
@app.get("/ws/state")
def ws_state() -> dict:
    return {"connected": current_core().browser_link.connected}


@app.get("/ws/token")
def ws_token() -> dict:
    # The extension (host-permitted for 127.0.0.1) can read this; a web page can't
    # (no CORS headers). The token gates the WS so no site/process can pilot Chrome.
    return {"token": current_core().browser_link.token}


class PairIn(BaseModel):
    code: str = ""


@app.get("/ws/pair_code")
def ws_pair_code() -> dict:
    """MINT a signed per-user pairing code (B12, flag-gated).

    The signed-in web app reaches this THROUGH its authenticated proxy, so the auth middleware has
    already bound this request to the caller's user (current_user()). We hand back a short-lived
    HMAC-signed code carrying that user id; the web app relays it to the extension via pair_device.
    OFF by default (404 while per-user hands is disabled) and refuses (503) when no
    ENGINE_INTERNAL_TOKEN secret is configured — fail closed either way."""
    if not per_user_hands_enabled():
        raise HTTPException(status_code=404, detail={"reason": "per_user_hands_disabled"})
    code = mint_pairing_code(registry.current_user())
    if not code:
        raise HTTPException(status_code=503, detail={"reason": "pairing_secret_unconfigured"})
    return {"ok": True, "code": code}


@app.post("/ws/pair")
def ws_pair(body: PairIn) -> dict:
    """CLAIM a per-user hand with a signed pairing code (B12, flag-gated).

    The extension presents the signed code (no Supabase bearer — the HMAC IS the auth). We verify
    the signature + expiry and, only on a valid code, return the TARGET user's per-user
    browser_link token so the extension binds the WS via /ws/extension?user=<id>&token=<token>. A
    forged / tampered / expired code is rejected (403). OFF by default (404) -> the single-owner
    /ws/token path is untouched."""
    if not per_user_hands_enabled():
        raise HTTPException(status_code=404, detail={"reason": "per_user_hands_disabled"})
    user_id = verify_pairing_code(body.code)
    if not user_id:
        raise HTTPException(status_code=403, detail={"reason": "invalid_pairing_code"})
    target = registry.core_for(user_id)
    return {"ok": True, "user": user_id, "token": target.browser_link.token}


@app.post("/ws/reload")
async def ws_reload() -> dict:
    # dev-only hot-reload trigger
    sent = await current_core().browser_link.reload()
    return {"reloaded": sent}


class BrowseIn(BaseModel):
    intent: str = "browse_task"
    args: dict = {}
    agent: bool = False


@app.post("/ws/browse")
async def ws_browse(body: BrowseIn) -> dict:
    c = current_core()
    if body.agent:
        res = await c.browser_hand.handle(Job(intent=body.intent, args=body.args))
    else:
        # Transport diagnostic only. M3 evidence must use /event and real sites.
        from .hands.browser_hand import BrowserHand

        res = await BrowserHand(c.browser_link, timeout=30.0).handle(Job(intent=body.intent, args=body.args))
    return res.model_dump(mode="json")


class ObserveIn(BaseModel):
    url: Optional[str] = None


class ActIn(BaseModel):
    action: str
    index: int = 0
    text: str = ""
    value: str = ""
    url: str = ""
    dir: str = "down"
    enter: bool = False


@app.post("/ws/observe")
async def ws_observe(body: ObserveIn) -> dict:
    args = {k: v for k, v in body.model_dump().items() if v is not None}
    if body.url:
        _assert_public_agent_url(body.url)  # SSRF: never point the agent at a private/metadata host
    return await current_core().browser_link.send_browse(new_id(), "observe", args, timeout=40.0)


@app.post("/ws/act")
async def ws_act(body: ActIn) -> dict:
    if str(body.action or "").strip() == "navigate" and body.url:
        _assert_public_agent_url(body.url)  # SSRF: a driven navigate must target a public host
    return await current_core().browser_link.send_browse(new_id(), "act", body.model_dump(), timeout=40.0)


class AgentRunIn(BaseModel):
    task: str
    start_url: str
    max_steps: int = 8
    judge: bool = False
    model: Optional[str] = None  # per-run brain override (model bake-off); None = default ladder


class AgentActIn(BaseModel):
    task: str
    start_url: str
    max_steps: int = 16
    cdp_url: Optional[str] = None  # attach to the user's logged-in Chrome (--remote-debugging-port)


@app.post("/agent/act")
async def agent_act(body: AgentActIn) -> dict:
    """The PROVEN action arm: browser-use (vision) completes the task — add-to-cart, fill a
    form to the review step — with money/checkout/login as HARD STOPS in the runner's action
    guard. Far more reliable on arbitrary stores than the bespoke loop. SSRF: the start page
    must be a PUBLIC http(s) host. When cdp_url is set the agent runs in the user's OWN
    already-running Chrome (their real, logged-in session) instead of a throwaway browser."""
    _assert_public_agent_url(body.start_url)
    res = await asyncio.to_thread(
        browser_use_link.browse_act, body.task, url=body.start_url,
        max_steps=body.max_steps, cdp_url=body.cdp_url)
    # M4 HONESTY — NEVER fake done. `res.success` is the agent's OWN "I called done" flag, not a
    # verification the task was actually accomplished (returning it as success let a finished-but-
    # WRONG task report success:true). Split the agent's self-report (agent_finished) from a
    # JUDGE-verified outcome (task_succeeded). A finished-but-failed task returns needs_human, never
    # a false success. A hard infra error stays a tool failure (not a human-clearable wall).
    agent_finished = bool(res.success)
    if res.error is None and agent_finished and res.result:
        verdict = await judge(gateway_agent, body.task, {"answer": res.result, "final_url": res.url})
    else:
        verdict = {"success": False, "reason": "agent did not finish or returned no result"}
    task_succeeded = bool(verdict.get("success")) and agent_finished and bool(res.result)
    needs_human = (not task_succeeded) and (res.error is None) and agent_finished
    return {
        "success": task_succeeded,          # back-compat key — now equals task_succeeded (judge-verified)
        "task_succeeded": task_succeeded,    # the ONLY field that means "really done" (a judge blessed it)
        "agent_finished": agent_finished,    # the agent stopped on its own — UNVERIFIED
        "needs_human": needs_human,          # finished/stalled but not judge-verified -> a human should look
        "judgment": verdict,
        "answer": res.result,
        "steps": res.steps,
        "final_url": res.url,
        "actions": res.actions,
        "allowed_domains": res.allowed_domains,
        "error": res.error,
        "agent": "browser-use",
    }


def _gateway_for(model: Optional[str]) -> ModelGateway:
    if not model:
        return gateway_agent
    # single-model gateway for an A/B run (both tiers = the candidate)
    return ModelGateway(provider=PROVIDER_OPENROUTER, cheap_model=model, smart_model=model)


@app.post("/agent/run")
async def agent_run(body: AgentRunIn) -> dict:
    # SSRF: the agent's start page must be a PUBLIC http(s) host. A loopback/link-local
    # (incl. 169.254.169.254 cloud-metadata)/private/file:// start_url is rejected (422)
    # before the live browser agent is ever pointed at it.
    _assert_public_agent_url(body.start_url)
    c = current_core()
    gw = _gateway_for(body.model)
    # Scale the per-subgoal budget with the task length: a long multi-page task (e.g. "page through
    # ALL pages and record qualifying items") legitimately needs more than the default 8 steps under
    # a single subgoal, or it fails the subgoal mid-pagination. Short tasks keep the tight default.
    _per_subgoal = max(8, body.max_steps // 3)
    agent = WebVoyagerAgent(c.browser_link, gw, max_steps=body.max_steps,
                            per_subgoal=_per_subgoal, notifier=c.notify_user)
    result = await agent.run(body.task, body.start_url)
    shot = result.pop("final_shot", None)  # vision-judge in-process; don't ship the image over HTTP
    # The general judge decides success — but only for an actual answer. A safety
    # stop or a wall handoff is already a correct outcome and is not judged.
    # M4 HONESTY (sweep #14): JUDGE every answered run on the real model — not only when body.judge is set
    # (it defaults False). A judge verdict of false flips the run to needs_human; never a silent fake done.
    if (not result.get("needs_human") and not result.get("stopped_for_safety")
            and (body.judge or getattr(gw, "provider", None) == PROVIDER_OPENROUTER)
            and (result.get("answer") or result.get("final_url"))):
        result["judgment"] = await judge(gw, body.task, result, image=shot)
        result["task_succeeded"] = bool(result["judgment"].get("success"))
        if not result["task_succeeded"]:
            result["needs_human"] = True
        # LEARNED-RECIPE CACHE (Pillar 4): persist the action-trace ONLY for a fresh, judge-verified
        # run (never from a replay, never unverified). The agent records the trace; the judge — which
        # the agent can't be — blesses it; only then does it become a replayable recipe. This is the
        # discover-don't-author rule that keeps recipes general while bending $/task down on repeats.
        if (result["task_succeeded"] and not result.get("replayed")
                and result.get("recipe_key") and result.get("trace")):
            try:
                agent.recipes.save(result["recipe_key"], body.task, body.start_url, result["trace"])
            except Exception:
                pass  # a cache write must never affect the user-visible outcome
    # LIVE CONSOLE: announce the final verdict + cost so the mission-control page can close out
    # the run on screen (success/needs_human, $/task, steps, frontier%, replayed).
    agent_events.publish({
        "type": "done",
        "success": bool(result.get("task_succeeded")),
        "needs_human": bool(result.get("needs_human")),
        "answer": (result.get("answer") or "")[:300],
        "replayed": bool(result.get("replayed")),
        "metrics": result.get("metrics") or {},
        "judge_reason": (result.get("judgment") or {}).get("reason"),
    })
    result.pop("trace", None)  # internal-only; don't ship the raw trace over HTTP
    # M4 (audit #5): a wall handoff mints a resume_token — PERSIST the run state under it so a later
    # /agent/resume can be VALIDATED and resumed with context, instead of a blind cold restart.
    if result.get("resume_token") and (result.get("needs_human") or result.get("paused")):
        c.resume_store.put(str(result["resume_token"]), {
            "task": body.task, "start_url": body.start_url,
            "wall_kind": result.get("wall_kind"),
            "history": (result.get("history") or [])[-30:], "step": result.get("steps")})
    return result


@app.post("/agent/reset")
async def agent_reset() -> dict:
    """Clean-slate reset: clear cookies + per-origin storage in the working tab so the next task
    starts uncontaminated by what a prior task saved (saved cart, login, form state). Used by the
    benchmark harness for honest, deterministic cold-start measurement."""
    c = current_core()
    try:
        out = await c.browser_link.reset_state()
        return {"ok": True, "result": out.get("output", out)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.get("/console")
async def agent_console():
    """Serve the live mission-control console (same-origin, so no CORS needed). It fires tasks at
    /agent/run and renders the /agent/events step stream — the foreground proof surface while the
    agent drives a background tab."""
    from fastapi.responses import HTMLResponse
    p = Path(__file__).resolve().parents[2] / "web" / "mission_control.html"
    try:
        return HTMLResponse(p.read_text())
    except Exception:
        return HTMLResponse("<h1>console missing</h1>", status_code=404)


@app.get("/agent/events")
async def agent_events_stream(request: Request):
    """Server-Sent-Events stream of LIVE agent step-events (task_start / step / mode / done).
    The mission-control console subscribes here and renders the per-step action log in real time
    while the agent advances a BACKGROUND tab. Observability only — never affects an agent run."""
    from fastapi.responses import StreamingResponse

    async def gen():
        q = agent_events.subscribe()
        try:
            # greet immediately so the client knows the stream is live
            yield "event: hello\ndata: {}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    ev = await asyncio.wait_for(q.get(), timeout=15.0)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"  # SSE comment to keep the connection warm
                    continue
                yield "data: " + json.dumps(ev) + "\n\n"
        finally:
            agent_events.unsubscribe(q)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


class AgentResumeIn(BaseModel):
    task: str
    start_url: str          # the page AFTER the human cleared the wall
    resume_token: str = ""
    max_steps: int = 12
    judge: bool = False


@app.post("/agent/resume")
async def agent_resume(body: AgentResumeIn) -> dict:
    # SSRF: the resumed page (the now-unblocked URL the caller supplies) must be a PUBLIC
    # http(s) host, exactly like /agent/run — a private/metadata/file:// resume target is
    # rejected (422) before the agent continues.
    _assert_public_agent_url(body.start_url)
    c = current_core()
    # M4 (audit #5): VALIDATE the resume_token against the stored state. A present token resumes WITH
    # context (the prior history is handed to the agent so it doesn't redo what's done); a missing/expired
    # token resumes COLD (resumed_cold=True). Either way it continues from the now-unblocked page and
    # never re-touches the wall. (Full mid-plan loop re-entry is a noted optimization on top of this.)
    state = c.resume_store.pop(body.resume_token) if body.resume_token else None
    c.glassbox.log("handoff", {"event": "resume", "token": body.resume_token,
                                  "url": body.start_url, "restored": bool(state)})
    agent = WebVoyagerAgent(c.browser_link, gateway_agent, max_steps=body.max_steps,
                            notifier=c.notify_user)
    task = body.task
    prior = (state or {}).get("history") or []
    if prior:
        task = (body.task + "\n\n[Resuming after the user cleared a wall. Already done: "
                + "; ".join(str(h)[:80] for h in prior[-6:])
                + ". Continue from here — do NOT redo these steps.]")
    result = await agent.run(task, body.start_url)
    result["resumed"] = True
    result["resumed_cold"] = state is None
    shot = result.pop("final_shot", None)
    # M4 HONESTY (sweep #14): judge a resumed run the same fail-safe way (judge on the real model, not
    # only when body.judge is set); an unverified resume becomes needs_human, never a fake done.
    if (not result.get("needs_human") and not result.get("stopped_for_safety")
            and (body.judge or getattr(gateway_agent, "provider", None) == PROVIDER_OPENROUTER)
            and (result.get("answer") or result.get("final_url"))):
        result["judgment"] = await judge(gateway_agent, body.task, result, image=shot)
        result["task_succeeded"] = bool(result["judgment"].get("success"))
        if not result["task_succeeded"]:
            result["needs_human"] = True
    # sweep #17: re-persist resume state if the resumed run hit ANOTHER wall (multi-wall handoff)
    if result.get("resume_token") and (result.get("needs_human") or result.get("paused")):
        c.resume_store.put(str(result["resume_token"]), {
            "task": body.task, "start_url": body.start_url, "wall_kind": result.get("wall_kind"),
            "history": (result.get("history") or [])[-30:], "step": result.get("steps")})
    return result


class AgentJudgeIn(BaseModel):
    task: str
    answer: str = ""
    final_url: str = ""


@app.post("/agent/judge")
async def agent_judge(body: AgentJudgeIn) -> dict:
    return await judge(gateway_agent, body.task, {"answer": body.answer, "final_url": body.final_url})


def _relay_brain():
    """The brain for the two-way voice CALL.

    A live call is a CONVERSATION, not an ambient judgment: the OnboardingCallBrain drives a warm setup
    chat with real turn memory (Omar's ask: a call you can't tell is AI), and still holds money/irreversible
    for a yes — it executes nothing. (The ambient ACT/ASK/SILENT judging still runs on the LISTEN stream via
    the decider; ConversationRelayBrain remains for that verdict-rendering path.) Set ANTICIPY_CR_BRAIN=decider
    to fall back to the old verdict brain on the call."""
    if (os.environ.get("ANTICIPY_CR_BRAIN") or "").strip().lower() == "decider":
        decider = getattr(core.proactive, "decider", None)
        return ConversationRelayBrain(decider) if decider is not None \
            else ConversationRelayBrain.from_gateway(core.gateway, glassbox=core.glassbox)
    return OnboardingCallBrain(core.gateway, glassbox=core.glassbox)


def _cr_max_turns() -> int:
    """Per-call answered-turn cap. Overridable (ANTICIPY_CR_MAX_TURNS) for tests/ops but
    hard-floored to 1 so a 0/negative/garbage override can never disable the cap."""
    try:
        raw = int(os.environ.get("ANTICIPY_CR_MAX_TURNS", "") or CR_MAX_TURNS)
    except (TypeError, ValueError):
        raw = CR_MAX_TURNS
    return max(1, raw)


def _cr_max_call_seconds() -> float:
    """Per-call wall-clock lifetime cap (seconds). Overridable
    (ANTICIPY_CR_MAX_CALL_SECONDS) but hard-floored to 1s so it can never be disabled."""
    try:
        raw = float(os.environ.get("ANTICIPY_CR_MAX_CALL_SECONDS", "") or CR_MAX_CALL_SECONDS)
    except (TypeError, ValueError):
        raw = CR_MAX_CALL_SECONDS
    return max(1.0, raw)



# ---- ANTICIPATORY RESEARCH: hear a name → figure out who they are ----
class PersonResearchIn(BaseModel):
    name: str = Field(..., description="Person's name to research")
    task_context: str = Field("", description="The task they were mentioned in")
    people: list = Field(default_factory=list, description="List of people names to research")


@app.post("/anticipate/research")
async def anticipate_research(body: PersonResearchIn) -> dict:
    """Research a person mentioned in conversation — search email, build context.

    This is the anticipatory piece: the system figures out WHO someone is from the
    owner's own email/contacts, without being asked."""
    from .proactive.anticipate import anticipatory_research, research_person, format_human_notification

    c = current_core()
    # Get remembered items from memory for person lookup
    remembered = []
    try:
        remembered = c.live_memory.capturer.remember.all()
    except Exception:
        pass

    if body.people:
        results = await anticipatory_research(
            body.task_context, body.people, c.gateway, remembered, caller="anticipate_api")
        return {
            "people": {name: ctx.as_dict() for name, ctx in results.items()},
            "notification": format_human_notification(body.task_context, results),
        }
    else:
        ctx = await research_person(body.name, body.task_context, c.gateway, remembered, caller="anticipate_api")
        return {
            "person": ctx.as_dict(),
            "notification": format_human_notification(body.task_context, {body.name: ctx}),
        }


@app.api_route("/voice", methods=["GET", "POST"])
async def voice_incoming(request: Request):
    """Twilio Voice 'A call comes in' webhook -> TwiML that hands the live call to the two-way
    ConversationRelay socket (/cr). Point the number's Voice webhook at https://<engine>/voice.

    The /cr socket authorizes the inbound connection via the Twilio request signature (no owner token
    needed on a public deploy), so the returned wss URL carries no secret. This was the missing piece:
    the /cr loop + the TwiML helper existed, but nothing served the inbound TwiML for an INCOMING call,
    so voice could only ever go OUTBOUND. Now a real inbound call is wired."""
    from fastapi.responses import Response as _Resp
    from .channels.call import CallChannel
    ws_url = (os.environ.get("ANTICIPY_CR_WSS_URL") or "").strip()
    if not ws_url.startswith("wss://"):
        host = (request.headers.get("host") or request.url.netloc or "").strip()
        ws_url = f"wss://{host}/cr"
    greeting = (os.environ.get("ANTICIPY_CR_GREETING")
                or "Hey, it's your Anticipy assistant. What can I do for you?").strip()
    twiml = CallChannel.conversation_relay_twiml(ws_url, greeting)
    current_core().glassbox.log("voice_incoming", {"ws_url": ws_url})
    return _Resp(content=twiml, media_type="text/xml")


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
    # Per-call caps: a single connection can answer at most _cr_max_turns() owner turns and
    # live at most _cr_max_call_seconds() of wall-clock time, so a stuck/abusive call (or a
    # caller who got past auth on a dev box) can't drive the decider brain unbounded.
    max_turns = _cr_max_turns()
    deadline = time.monotonic() + _cr_max_call_seconds()
    turns_used = 0
    try:
        while True:
            if time.monotonic() >= deadline:
                core.glassbox.log("conversation_relay",
                                  {"event": "cap_reached", "reason": "duration"})
                break
            try:
                msg = await ws.receive_json()
            except JSONDecodeError:
                # A malformed/non-JSON frame mid-call must not crash the live call:
                # stay silent and wait for the next frame (mirrors the unknown-frame bias).
                continue
            if not isinstance(msg, dict):
                # A valid-JSON but non-object frame (a bare string/number/array) has no
                # type and no fields to read — skip it before any msg.get().
                continue
            kind = msg.get("type")
            if kind == "prompt":
                if turns_used >= max_turns or time.monotonic() >= deadline:
                    # Turn/duration cap hit: stop answering and close the call. The
                    # finally-block still sends the end frame with the last verdict.
                    core.glassbox.log("conversation_relay",
                                      {"event": "cap_reached",
                                       "reason": "turns" if turns_used >= max_turns else "duration",
                                       "turns": turns_used})
                    break
                turns_used += 1
                turn = await brain.turn(msg.get("voicePrompt") or "")
                last_handoff = turn.handoff_data()
                with suppress(Exception):
                    core.gateway_ledger.record_voice_turn(
                        prompt=msg.get("voicePrompt") or "",
                        handoff=last_handoff,
                        channel="conversation_relay",
                    )
                # stream the reply as ConversationRelay text tokens; the FINAL frame
                # carries last:true so Twilio knows the turn's speech is complete
                tokens = list(stream_tokens(turn.reply))
                for tok in tokens:
                    await ws.send_json({"type": "text", "token": tok, "last": False})
                await ws.send_json({"type": "text", "token": "", "last": True})
                core.glassbox.log("conversation_relay",
                                  {"event": "turn", "verdict": turn.verdict})
                # VOICE -> ACT: the spoken reply above is words only. When voice execution is
                # turned on (config-ready, OFF by default — see voice_execute_enabled(), the
                # InboundPoller-style gate), ALSO route the utterance into the SAME owner action
                # spine as typed/MP3/SMS intake, so a spoken task actually creates a card/errand.
                # Safety is the spine's, reused not rebuilt: owner_ingest holds money/irreversible
                # as an ASK and a vent stays SILENT. Best-effort — an ingest error never breaks the
                # live call (the reply already streamed); it can never SEND on the call itself.
                if voice_execute_enabled():
                    with suppress(Exception):
                        ingest = await core.owner_ingest(
                            "voice", msg.get("voicePrompt") or "",
                            {"channel": "conversation_relay", "from": "owner"},
                            execute_actions=True)
                        core.glassbox.log(
                            "conversation_relay",
                            {"event": "voice_ingested",
                             "cards": len((ingest or {}).get("cards") or [])})
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
    # PER-USER HANDS (Step 4): the extension carries its signed-in user id (?user=<supabase id>) so the
    # WS binds to THAT user's core.browser_link — each user pilots their OWN Chrome, never another's.
    # No user id (owner-token / local / suite) -> the DEFAULT core. The token still gates it: each core
    # has its OWN browser_link.token (fetched from /ws/token under that user), so a user can only attach
    # with their own core's token — a wrong/cross token is rejected.
    target = registry.core_for((ws.query_params.get("user") or "").strip() or None)
    if not target.browser_link.check_token(ws.query_params.get("token")):
        await ws.close(code=1008)  # reject unauthenticated / cross-user handshake
        return
    await ws.accept()
    await target.browser_link.attach(ws)
    target.glassbox.log("extension", {"event": "connected",
                                      "user": (ws.query_params.get("user") or "").strip() or "default"})
    try:
        while True:
            try:
                msg = await ws.receive_json()
            except JSONDecodeError:
                # A malformed/non-JSON frame must not drop the extension link: skip it
                # and keep the socket alive for the next frame.
                continue
            if not isinstance(msg, dict):
                # A valid-JSON but non-object frame has no type/fields to act on — skip
                # before any msg.get() and before handing it to the browser link.
                continue
            if msg.get("type") == "ping":
                await ws.send_json({"type": "pong"})
            else:
                await target.browser_link.on_message(msg)
    except WebSocketDisconnect:
        pass
    finally:
        await target.browser_link.detach(ws)
        target.glassbox.log("extension", {"event": "disconnected"})


# ---- M7: serve the premium frontend (welcome + app) from the engine's OWN origin ----
# The app's fetches are same-origin (ENGINE=""), and the engine has no CORS — so the app is served
# from http://127.0.0.1:8787 itself. Mounted LAST so every API route above is matched FIRST;
# StaticFiles only catches leftover paths (/, /app.html, /styles.css, /app.js, ...). html=True -> "/" = index.html.
try:
    from fastapi.staticfiles import StaticFiles

    class _NoCacheStatic(StaticFiles):
        # Always revalidate the app shell (HTML/JS/CSS): the browser keeps an etag and gets a fast 304
        # when nothing changed, but picks up a fresh build the instant a file changes — no stale UI.
        async def get_response(self, path, scope):
            resp = await super().get_response(path, scope)
            try:
                resp.headers["Cache-Control"] = "no-cache, must-revalidate"
            except Exception:
                pass
            return resp

    _web_dir = Path(__file__).resolve().parents[2] / "web"
    if _web_dir.is_dir():
        app.mount("/", _NoCacheStatic(directory=str(_web_dir), html=True), name="web")
except Exception:
    pass
