"""
FastAPI server with WebSocket task execution, REST auth endpoints,
rate limiting, input validation, graceful shutdown, and admin stats.
"""

from __future__ import annotations

import asyncio
import json
import logging
import signal
import time
import uuid
from collections import defaultdict
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app import auth as auth_module
from app import messages as msg
from app.router import classify, handle_chat, handle_question, needs_clarification
from app.agent import execute_task
from app.models import CostTracker
from app.planner import plan_task
from app.safety import check_blocked, block_reason, sanitize_input
from app.config import (
    MAX_INPUT_LENGTH,
    MAX_SECONDS,
    MAX_TASKS_PER_HOUR,
    MAX_TASKS_PER_DAY,
    REQUIRED_ENV_VARS,
    MODEL_CHAIN,
    ENGINE_INTERNAL_TOKEN,
    WS_MAX_MESSAGES_PER_MINUTE,
    WS_MAX_MESSAGE_BYTES,
    WS_REQUIRE_AUTH,
    IS_PRODUCTION,
)
from app import supabase_client
from app.crm_log import log_event as crm_log_event
import os

logger = logging.getLogger("engine")


# --- Rate limiting state ---
# Bounded so a flood of distinct user_ids can't exhaust memory.
_RATE_LIMIT_MAX_USERS = 50_000
_task_timestamps: dict[str, list[float]] = defaultdict(list)
_last_rate_cleanup: float = 0.0


def _cleanup_rate_state() -> None:
    """Periodic sweep so dead user_ids stop accumulating."""
    global _last_rate_cleanup
    now = time.time()
    if now - _last_rate_cleanup < 300:  # at most every 5 min
        return
    _last_rate_cleanup = now
    day_ago = now - 86400
    stale = [uid for uid, ts in _task_timestamps.items() if not ts or max(ts) < day_ago]
    for uid in stale:
        _task_timestamps.pop(uid, None)
    if len(_task_timestamps) > _RATE_LIMIT_MAX_USERS:
        # Drop oldest by most-recent-timestamp until we're back under cap
        sorted_uids = sorted(
            _task_timestamps.items(),
            key=lambda kv: max(kv[1]) if kv[1] else 0,
        )
        for uid, _ in sorted_uids[: len(_task_timestamps) - _RATE_LIMIT_MAX_USERS]:
            _task_timestamps.pop(uid, None)


def _check_task_rate_limit(user_id: str) -> str | None:
    """
    Check task rate limits per user.
    Returns an error message string if rate-limited, None if OK.
    """
    _cleanup_rate_state()
    now = time.time()
    timestamps = _task_timestamps.get(user_id, [])

    # Clean old timestamps
    hour_ago = now - 3600
    day_ago = now - 86400
    timestamps = [ts for ts in timestamps if ts > day_ago]
    _task_timestamps[user_id] = timestamps

    hour_count = sum(1 for ts in timestamps if ts > hour_ago)
    day_count = len(timestamps)

    if hour_count >= MAX_TASKS_PER_HOUR:
        return msg.RATE_LIMIT_TASKS
    if day_count >= MAX_TASKS_PER_DAY:
        return msg.BUDGET_DAILY_EXCEEDED
    return None


def _record_task(user_id: str) -> None:
    """Record a task execution for rate limiting."""
    _task_timestamps[user_id].append(time.time())


# --- WebSocket message-rate state (per-IP) ---
_ws_msg_timestamps: dict[str, list[float]] = defaultdict(list)
_WS_MSG_MAX_IPS = 10_000
_last_ws_cleanup: float = 0.0


def _check_ws_msg_rate(ip: str) -> bool:
    """
    Bucketed WebSocket message rate limit per IP.
    Returns True if the caller should be throttled.
    """
    global _last_ws_cleanup
    now = time.time()
    minute_ago = now - 60

    if now - _last_ws_cleanup > 120:
        _last_ws_cleanup = now
        stale = [k for k, ts in _ws_msg_timestamps.items() if not ts or max(ts) < minute_ago]
        for k in stale:
            _ws_msg_timestamps.pop(k, None)
        if len(_ws_msg_timestamps) > _WS_MSG_MAX_IPS:
            sorted_ips = sorted(
                _ws_msg_timestamps.items(),
                key=lambda kv: max(kv[1]) if kv[1] else 0,
            )
            for k, _ in sorted_ips[: len(_ws_msg_timestamps) - _WS_MSG_MAX_IPS]:
                _ws_msg_timestamps.pop(k, None)

    bucket = [ts for ts in _ws_msg_timestamps.get(ip, []) if ts > minute_ago]
    bucket.append(now)
    _ws_msg_timestamps[ip] = bucket
    return len(bucket) > WS_MAX_MESSAGES_PER_MINUTE


# --- Startup stats ---
_start_time: float = 0.0
_total_tasks: int = 0
_total_errors: int = 0


def _validate_env_vars() -> list[str]:
    """Check required environment variables. Returns list of missing vars."""
    missing = []
    for var in REQUIRED_ENV_VARS:
        if not os.environ.get(var):
            missing.append(var)
    return missing


# --- Database migration check ---
REQUIRED_TABLES = ["engine_users", "browser_profiles", "engine_tasks"]


async def _check_database_tables() -> list[str]:
    """Check if required database tables are accessible. Returns list of missing/inaccessible tables."""
    missing = []
    for table in REQUIRED_TABLES:
        try:
            await supabase_client.select_rows(table, limit=1)
        except Exception:
            missing.append(table)
    return missing


# --- Lifespan ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    global _start_time
    _start_time = time.time()

    # Validate env vars on startup (V65)
    missing = _validate_env_vars()
    if missing:
        logger.warning(f"Missing environment variables: {', '.join(missing)}")

    # Check model chain
    if not MODEL_CHAIN:
        logger.warning("No LLM API keys configured. The engine will not be able to process tasks.")

    # Check database tables (V67)
    try:
        missing_tables = await _check_database_tables()
        if missing_tables:
            logger.warning(f"Database tables not accessible: {', '.join(missing_tables)}")
    except Exception:
        logger.warning("Could not verify database tables on startup.")

    # Graceful shutdown handler (V64)
    loop = asyncio.get_event_loop()

    def _shutdown_handler():
        logger.info("Received shutdown signal, cleaning up...")
        for task in asyncio.all_tasks(loop):
            task.cancel()

    try:
        loop.add_signal_handler(signal.SIGTERM, _shutdown_handler)
        loop.add_signal_handler(signal.SIGINT, _shutdown_handler)
    except (NotImplementedError, RuntimeError):
        # Signal handlers not supported on this platform (e.g., Windows)
        pass

    logger.info("Anticipy Action Engine started.")
    yield
    logger.info("Anticipy Action Engine shutting down.")


app = FastAPI(title="Anticipy Action Engine", version="1.0.0", lifespan=lifespan)

# --- CORS (restricted to known origins) ---
ALLOWED_ORIGINS = [
    "https://anticipy-beta.vercel.app",
    "https://anticipy.ai",
    "https://www.anticipy.ai",
    "http://localhost:3000",
    "http://localhost:8000",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


# --- Pydantic models ---
class AuthRequest(BaseModel):
    username: str
    password: str


class AuthResponse(BaseModel):
    success: bool
    token: str | None = None
    user_id: str | None = None
    message: str


class UserResponse(BaseModel):
    user_id: str
    username: str


# --- Auth dependency ---
async def get_current_user(token: str) -> dict:
    payload = auth_module.verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail=msg.AUTH_TOKEN_INVALID)
    return payload


def _get_client_ip(request: Request) -> str:
    """
    Extract client IP. Honors `x-forwarded-for` ONLY when env
    `TRUST_FORWARDED_FOR=1`. Without that opt-in the direct connection IP
    is used so users can't spoof their own IP via a header.
    """
    if os.environ.get("TRUST_FORWARDED_FOR", "").lower() in {"1", "true", "yes", "on"}:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            # Take the left-most (original client) and strip whitespace.
            first = forwarded.split(",")[0].strip()
            if first:
                return first
        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip.strip()
    return request.client.host if request.client else "unknown"


# ──────────────────────────────────────────────────────────────────────────
# WebSocket connection caps (per-user + per-IP)
# ──────────────────────────────────────────────────────────────────────────

MAX_WS_CONCURRENT_PER_USER: int = 3
MAX_WS_CONCURRENT_PER_IP: int = 10

_ws_connections_by_user: dict[str, int] = defaultdict(int)
_ws_connections_by_ip: dict[str, int] = defaultdict(int)


def _ws_connection_admit(user_id: str | None, ip: str) -> str | None:
    """Admit a new WS connection. Returns None on success, an error string
    when the user-cap or IP-cap would be exceeded. Anonymous user_id (None)
    only checks the IP gate."""
    # Per-user cap (skipped for anonymous pre-auth phases)
    if user_id is not None:
        if _ws_connections_by_user.get(user_id, 0) >= MAX_WS_CONCURRENT_PER_USER:
            return (
                "Too many concurrent connections for this user. "
                "Close another tab or wait a moment."
            )
    # Per-IP cap (always)
    if _ws_connections_by_ip.get(ip, 0) >= MAX_WS_CONCURRENT_PER_IP:
        return (
            "Too many concurrent connections from your network. "
            "Close another tab or wait a moment."
        )
    if user_id is not None:
        _ws_connections_by_user[user_id] = _ws_connections_by_user.get(user_id, 0) + 1
    _ws_connections_by_ip[ip] = _ws_connections_by_ip.get(ip, 0) + 1
    return None


def _ws_connection_release(user_id: str | None, ip: str) -> None:
    """Decrement counters; clamps to 0 so spurious releases never go negative."""
    if user_id is not None:
        cur = _ws_connections_by_user.get(user_id, 0)
        _ws_connections_by_user[user_id] = max(0, cur - 1)
    cur_ip = _ws_connections_by_ip.get(ip, 0)
    _ws_connections_by_ip[ip] = max(0, cur_ip - 1)


def _ws_user_attach(user_id: str) -> str | None:
    """After an already-admitted anonymous WS authenticates, bump the
    per-user counter and check the per-user cap. Returns None on success,
    refusal string when the cap would be exceeded. The per-IP count is
    NOT touched (the connection was already accepted)."""
    if _ws_connections_by_user.get(user_id, 0) >= MAX_WS_CONCURRENT_PER_USER:
        return (
            "Too many concurrent connections for this user. "
            "Close another tab or wait a moment."
        )
    _ws_connections_by_user[user_id] = _ws_connections_by_user.get(user_id, 0) + 1
    return None


# ──────────────────────────────────────────────────────────────────────────
# Confirmation tokens (signed, expiring) for /execute-intent
# A token attests that THIS specific task hash was approved by THIS user.
# Bound to a single purpose so a token issued for one flow cannot be reused
# in another. Verified server-side; never trusts the client to be honest
# about which task is "actually" being run.
# ──────────────────────────────────────────────────────────────────────────

import hashlib  # noqa: E402

import jwt  # noqa: E402

from app.config import JWT_ALGORITHM, JWT_SECRET  # noqa: E402

_CONFIRMATION_PURPOSE = "execute_intent"
_CONFIRMATION_EXPIRY_SECONDS = 600  # 10 minutes


def _hash_task(task: str) -> str:
    """Stable lower-cased SHA-256 of the task string for token binding."""
    if not isinstance(task, str):
        task = str(task)
    return hashlib.sha256(task.strip().encode("utf-8")).hexdigest()


def _issue_confirmation_token(task: str, user_id: str) -> str:
    """Issue a short-lived JWT that authorizes running THIS task for THIS
    user. Token is bound to a SHA-256 hash of the task and the user_id, plus
    a `purpose` field, plus an expiry."""
    now = int(time.time())
    payload = {
        "task_hash": _hash_task(task),
        "user_id": user_id,
        "iat": now,
        "exp": now + _CONFIRMATION_EXPIRY_SECONDS,
        "purpose": _CONFIRMATION_PURPOSE,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def _verify_confirmation_token(token: str, task: str, user_id: str) -> bool:
    """True iff the token was issued for the same task hash + user, has the
    correct purpose, and has not expired. Any decode failure → False."""
    if not token or not isinstance(token, str):
        return False
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError:
        return False
    if payload.get("purpose") != _CONFIRMATION_PURPOSE:
        return False
    if payload.get("user_id") != user_id:
        return False
    if payload.get("task_hash") != _hash_task(task):
        return False
    return True


def _bearer_user(authorization: str | None) -> dict:
    """Validate an `Authorization: Bearer <jwt>` header and return the JWT
    payload. Raises HTTPException(401) on missing / wrong-scheme / invalid."""
    if not authorization or not isinstance(authorization, str):
        raise HTTPException(status_code=401, detail="missing authorization")
    parts = authorization.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail="invalid authorization scheme")
    payload = auth_module.verify_token(parts[1].strip())
    if not payload:
        raise HTTPException(status_code=401, detail="invalid token")
    return payload


# --- REST endpoints ---
@app.post("/auth/signup", response_model=AuthResponse)
async def signup(req: AuthRequest):
    if not req.username or not req.password:
        return AuthResponse(success=False, message=msg.AUTH_MISSING_FIELDS)

    # Defensive bounds before we touch the DB.
    u_err = auth_module.validate_username(req.username)
    if u_err:
        return AuthResponse(success=False, message=msg.AUTH_USERNAME_INVALID)
    p_err = auth_module.validate_password(req.password)
    if p_err == "too_short":
        return AuthResponse(success=False, message=msg.AUTH_PASSWORD_TOO_SHORT)
    if p_err == "too_long":
        return AuthResponse(success=False, message=msg.AUTH_PASSWORD_TOO_LONG)

    try:
        result = await auth_module.signup(req.username.strip(), req.password)
    except Exception:
        logger.exception("signup error")
        return AuthResponse(success=False, message=msg.CONNECTION_ERROR)

    if result["success"]:
        return AuthResponse(
            success=True,
            token=result["token"],
            user_id=result["user_id"],
            message=msg.AUTH_SIGNUP_SUCCESS,
        )
    err = result.get("error", "")
    if err == "exists":
        return AuthResponse(success=False, message=msg.AUTH_USER_EXISTS)
    if err == "username":
        return AuthResponse(success=False, message=msg.AUTH_USERNAME_INVALID)
    if err == "password_too_short":
        return AuthResponse(success=False, message=msg.AUTH_PASSWORD_TOO_SHORT)
    if err == "password_too_long":
        return AuthResponse(success=False, message=msg.AUTH_PASSWORD_TOO_LONG)
    return AuthResponse(success=False, message=msg.CONNECTION_ERROR)


@app.post("/auth/login", response_model=AuthResponse)
async def login(req: AuthRequest, request: Request):
    if not req.username or not req.password:
        return AuthResponse(success=False, message=msg.AUTH_MISSING_FIELDS)

    # Don't even hit the DB for obviously malformed input.
    if len(req.username) > 256 or len(req.password) > 1024:
        return AuthResponse(success=False, message=msg.AUTH_INVALID_CREDENTIALS)

    client_ip = _get_client_ip(request)

    # Check rate limit (V17)
    if auth_module.check_login_rate_limit(client_ip):
        return AuthResponse(success=False, message=msg.AUTH_RATE_LIMITED)

    try:
        result = await auth_module.login(req.username.strip(), req.password, ip=client_ip)
    except Exception:
        logger.exception("login error")
        return AuthResponse(success=False, message=msg.CONNECTION_ERROR)

    if result["success"]:
        return AuthResponse(
            success=True,
            token=result["token"],
            user_id=result["user_id"],
            message=msg.AUTH_LOGIN_SUCCESS,
        )
    if result.get("error") == "rate_limited":
        return AuthResponse(success=False, message=msg.AUTH_RATE_LIMITED)
    return AuthResponse(success=False, message=msg.AUTH_INVALID_CREDENTIALS)


@app.get("/auth/me", response_model=UserResponse)
async def me(token: str):
    payload = auth_module.verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail=msg.AUTH_TOKEN_INVALID)
    return UserResponse(user_id=payload["user_id"], username=payload["username"])


@app.get("/health")
async def health():
    return {"status": "ok"}


# --- Admin stats endpoint (V66) ---
@app.get("/stats")
async def stats(request: Request, token: str | None = None):
    """
    Admin monitoring endpoint.

    Auth modes (any one):
      - X-Engine-Token header matching ENGINE_INTERNAL_TOKEN
      - JWT token (in `token` query param) for a username on the admin allow-list
    """
    # Server-to-server bypass for ops dashboards
    server_token = request.headers.get("x-engine-token")
    if server_token and ENGINE_INTERNAL_TOKEN and server_token == ENGINE_INTERNAL_TOKEN:
        pass
    else:
        if not token:
            raise HTTPException(status_code=401, detail=msg.AUTH_TOKEN_INVALID)
        payload = auth_module.verify_token(token)
        if not payload:
            raise HTTPException(status_code=401, detail=msg.AUTH_TOKEN_INVALID)
        if not auth_module.is_admin(payload.get("username")):
            raise HTTPException(status_code=403, detail="forbidden")

    uptime = time.time() - _start_time if _start_time else 0
    return {
        "uptime_seconds": round(uptime, 1),
        "total_tasks": _total_tasks,
        "total_errors": _total_errors,
        "models_configured": len(MODEL_CHAIN),
        "active_rate_limited_users": len(_task_timestamps),
    }


# --- Intent execution endpoint ---
# Called by Next.js backend when a user confirms an action.
# Runs the browser agent and returns the result (blocking up to MAX_SECONDS).

class ExecuteIntentRequest(BaseModel):
    task: str
    intent_id: str | None = None
    user_id: str | None = None


@app.post("/execute-intent")
async def execute_intent_endpoint(req: ExecuteIntentRequest, request: Request):
    """
    Execute a browser automation task from a structured intent description.

    Starts the browser agent as a background asyncio task so the browser
    keeps running even if the HTTP client disconnects early.  Waits up to
    25 s for a result before returning a "working" response; the background
    task writes the final outcome to engine_tasks in Supabase either way.

    Requires the X-Engine-Token header to match ENGINE_INTERNAL_TOKEN — this
    is a server-to-server endpoint called by the Next.js backend on behalf of
    a user, not directly by the user. If ENGINE_INTERNAL_TOKEN is not set the
    endpoint refuses all calls (fail-closed).
    """
    if not ENGINE_INTERNAL_TOKEN:
        raise HTTPException(status_code=503, detail="endpoint disabled")
    if request.headers.get("x-engine-token") != ENGINE_INTERNAL_TOKEN:
        raise HTTPException(status_code=401, detail="unauthorized")

    if not req.task or not req.task.strip():
        raise HTTPException(status_code=400, detail="task is required")

    if len(req.task) > MAX_INPUT_LENGTH:
        raise HTTPException(status_code=400, detail="task is too long")

    task_text = sanitize_input(req.task.strip())
    if not task_text:
        raise HTTPException(status_code=400, detail="task text is empty after sanitization")

    reason = block_reason(task_text)
    if reason:
        if reason == "password":
            block_msg = msg.PASSWORD_REQUEST_BLOCKED
        elif reason == "financial":
            block_msg = msg.FINANCIAL_TRANSACTION_BLOCKED
        else:
            block_msg = msg.BLOCKED_ACTION
        crm_log_event(
            "action_engine",
            "task_blocked",
            f"Blocked ({reason}): {task_text[:80]}",
            {"reason": reason, "user_id": req.user_id, "channel": "rest"},
        )
        return {
            "success": False,
            "message": block_msg,
            "data": {"reason": reason},
            "plan": "",
        }

    # Surface a clarifying question to the user instead of silently failing on
    # an under-specified task. The Next.js confirm route relays this `message`
    # back to the user verbatim.
    clarification = needs_clarification(task_text)
    if clarification:
        return {
            "success": False,
            "needs_clarification": True,
            "message": clarification,
            "data": {"reason": "needs_clarification"},
            "plan": "",
        }

    task_id = str(uuid.uuid4())
    messages_log: list[dict] = []
    plan_text: str = ""
    crm_log_event(
        "action_engine",
        "task_started",
        f"Task: {task_text[:80]}",
        {"task_id": task_id, "user_id": req.user_id, "intent_id": req.intent_id, "channel": "rest"},
        related_entity_type="engine_task",
        related_entity_id=task_id,
    )

    # --- Generate a quick plan so we can return something useful ---
    try:
        tracker = CostTracker()
        plan = await asyncio.wait_for(plan_task(task_text, tracker), timeout=8)
        sub_goals = plan.get("sub_goals", [])
        if sub_goals:
            plan_text = " → ".join(str(g) for g in sub_goals[:3])
    except Exception:
        pass  # Plan is optional; proceed without it

    # --- Result container shared between background task and waiter ---
    result_holder: list[dict] = []  # holds at most one result dict

    async def collect(msg_dict: dict) -> None:
        messages_log.append(msg_dict)

    async def receive_confirmation() -> str:
        return "confirmed"  # Auto-confirm for API-driven executions

    async def run_and_store() -> None:
        """Run the browser agent and persist the result to Supabase."""
        try:
            await execute_task(
                goal=task_text,
                send=collect,
                receive_confirmation=receive_confirmation,
                user_id=req.user_id,
            )
        except Exception:
            logger.exception("execute_intent background task error")

        # Derive final result from collected messages
        final: dict = {"success": False, "message": "No result returned from agent.", "data": {}}
        for m in reversed(messages_log):
            m_type = m.get("type")
            if m_type == "complete":
                final = {"success": True, "message": m.get("message", "Done."), "data": {}}
                break
            if m_type == "error":
                final = {"success": False, "message": m.get("message", "Task failed."), "data": {}}
                break

        result_holder.append(final)
        crm_log_event(
            "action_engine",
            "task_completed" if final["success"] else "task_failed",
            f"{'Done' if final['success'] else 'Failed'}: {task_text[:80]}",
            {"task_id": task_id, "user_id": req.user_id, "result": final.get("message", "")[:200]},
            related_entity_type="engine_task",
            related_entity_id=task_id,
        )

        # Persist to engine_tasks
        try:
            await supabase_client.insert_row(
                "engine_tasks",
                {
                    "id": task_id,
                    "user_id": req.user_id,
                    "goal": task_text,
                    "status": "completed" if final["success"] else "failed",
                    "result": final["message"],
                    "metadata": {
                        "intent_id": req.intent_id,
                        "plan": plan_text,
                        "log_count": len(messages_log),
                    },
                },
            )
        except Exception:
            pass  # Non-critical

        # Update anticipy_actions if intent_id provided
        if req.intent_id:
            try:
                await supabase_client.insert_row(
                    "anticipy_actions",
                    {
                        "intent_id": req.intent_id,
                        "status": "success" if final["success"] else "failed",
                        "result": {"message": final["message"], "task_id": task_id},
                        "external_id": task_id,
                    },
                )
            except Exception:
                pass  # anticipy_actions may not exist in engine db — Next.js handles it too

    # Start the browser task in background (survives HTTP disconnect)
    bg_task = asyncio.create_task(run_and_store())

    # Wait up to 25 s for an early result
    try:
        await asyncio.wait_for(asyncio.shield(bg_task), timeout=25)
    except asyncio.TimeoutError:
        # Task is still running; return a "working" response so Next.js
        # can show the user "Working on it…" without blocking the HTTP response.
        return {
            "success": True,
            "working": True,
            "message": "Working on it — this may take a minute.",
            "data": {"task_id": task_id},
            "plan": plan_text,
        }
    except Exception:
        pass  # Will be captured in result_holder

    if result_holder:
        r = result_holder[0]
        return {
            "success": r["success"],
            "message": r["message"],
            "data": {**r.get("data", {}), "task_id": task_id},
            "plan": plan_text,
        }

    return {
        "success": False,
        "message": "Agent finished without a clear result.",
        "data": {"task_id": task_id},
        "plan": plan_text,
    }


# --- WebSocket helpers ---
def _ws_client_ip(websocket: WebSocket) -> str:
    """Extract caller IP from a WebSocket, preferring x-forwarded-for."""
    forwarded = websocket.headers.get("x-forwarded-for")
    if forwarded:
        first = forwarded.split(",")[0].strip()
        if first:
            return first
    real = websocket.headers.get("x-real-ip")
    if real:
        return real.strip()
    return websocket.client.host if websocket.client else "unknown"


# --- WebSocket task execution ---
@app.websocket("/ws/task")
async def ws_task(websocket: WebSocket):
    global _total_tasks, _total_errors
    await websocket.accept()

    client_ip = _ws_client_ip(websocket)

    # Per-IP connection cap applies even before auth so a single attacker
    # cannot exhaust file descriptors. The per-user cap kicks in after
    # the auth token is validated below. We admit anonymously here and
    # may upgrade once we know the user.
    refusal = _ws_connection_admit(None, client_ip)
    if refusal is not None:
        try:
            await websocket.send_json({"type": "error", "message": refusal})
            await websocket.close(code=4429)
        except Exception:
            pass
        return
    admitted_user_id: str | None = None
    admitted_ip: str = client_ip

    # Confirmation channel: agent blocks on this when it needs user input
    confirm_event = asyncio.Event()
    confirm_value: list[str] = [""]

    async def send_msg(data: dict) -> None:
        """Send a JSON message to the WebSocket client."""
        try:
            await websocket.send_json(data)
        except Exception:
            pass

    async def receive_confirmation() -> str:
        """Block until the client sends a confirm/continue message."""
        confirm_event.clear()
        confirm_value[0] = ""
        try:
            await asyncio.wait_for(confirm_event.wait(), timeout=120)
        except asyncio.TimeoutError:
            return "timeout"
        return confirm_value[0]

    user_id: str | None = None
    username: str | None = None
    task_running = False
    bg_task: asyncio.Task | None = None

    # Extract token from query params
    query_token = websocket.query_params.get("token")
    if query_token:
        payload = auth_module.verify_token(query_token)
        if payload:
            user_id = payload["user_id"]
            username = payload.get("username")
            user_refusal = _ws_user_attach(user_id)
            if user_refusal:
                _ws_connection_release(None, admitted_ip)
                try:
                    await send_msg({"type": "error", "message": user_refusal})
                    await websocket.close(code=4429)
                except Exception:
                    pass
                return
            admitted_user_id = user_id

    if WS_REQUIRE_AUTH and not user_id:
        _ws_connection_release(admitted_user_id, admitted_ip)
        await send_msg({"type": "error", "message": msg.AUTH_REQUIRED})
        try:
            await websocket.close(code=4401)
        except Exception:
            pass
        return

    try:
        while True:
            raw = await websocket.receive_text()

            # Per-IP message-rate guard.  Don't accept anything from a flooder.
            if _check_ws_msg_rate(client_ip):
                await send_msg({"type": "error", "message": msg.RATE_LIMIT_WS})
                continue

            # Frame size guard
            if raw is None or len(raw) > WS_MAX_MESSAGE_BYTES:
                await send_msg({"type": "error", "message": msg.INPUT_INVALID})
                continue

            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await send_msg({"type": "error", "message": msg.INPUT_INVALID})
                continue

            if not isinstance(data, dict):
                await send_msg({"type": "error", "message": msg.INPUT_INVALID})
                continue

            msg_type = data.get("type", "")

            # --- Authentication (optional, via token field in message body) ---
            if "token" in data and not user_id:
                tok = data.get("token")
                if isinstance(tok, str):
                    payload = auth_module.verify_token(tok)
                    if payload:
                        user_id = payload["user_id"]
                        username = payload.get("username")
                        user_refusal = _ws_user_attach(user_id)
                        if user_refusal:
                            await send_msg({"type": "error", "message": user_refusal})
                            try:
                                await websocket.close(code=4429)
                            except Exception:
                                pass
                            return
                        admitted_user_id = user_id

            # --- Start task ---
            if msg_type == "start":
                if task_running:
                    await send_msg({"type": "error", "message": msg.TASK_ALREADY_RUNNING})
                    continue

                raw_text = data.get("text", "")
                if not isinstance(raw_text, str):
                    await send_msg({"type": "error", "message": msg.INPUT_INVALID})
                    continue
                text = raw_text.strip()
                if not text:
                    await send_msg({"type": "error", "message": msg.AMBIGUOUS_REQUEST})
                    continue

                # Input size limit (V27)
                if len(text) > MAX_INPUT_LENGTH:
                    await send_msg({"type": "error", "message": msg.INPUT_TOO_LONG})
                    continue

                # Sanitize input (V19)
                text = sanitize_input(text)
                if not text:
                    await send_msg({"type": "error", "message": msg.AMBIGUOUS_REQUEST})
                    continue

                # Safety check FIRST — before classification, with category-aware messages
                reason = block_reason(text)
                if reason:
                    if reason == "password":
                        block_msg = msg.PASSWORD_REQUEST_BLOCKED
                    elif reason == "financial":
                        block_msg = msg.FINANCIAL_TRANSACTION_BLOCKED
                    else:
                        block_msg = msg.BLOCKED_ACTION
                    crm_log_event(
                        "action_engine",
                        "task_blocked",
                        f"Blocked ({reason}): {text[:80]}",
                        {"reason": reason, "user_id": user_id, "channel": "ws"},
                    )
                    await send_msg({"type": "complete", "message": block_msg})
                    continue

                # Rate limiting on task creation (V18)
                rate_user = user_id or f"anon:{client_ip}"
                rate_error = _check_task_rate_limit(rate_user)
                if rate_error:
                    await send_msg({"type": "error", "message": rate_error})
                    continue

                # Classify intent
                tracker = CostTracker()
                try:
                    classification = await classify(text, tracker)
                except Exception:
                    logger.exception("classify error")
                    from app.router import Classification as _C
                    classification = _C(category="ambiguous", degraded=True)

                category = classification.category

                if category == "chat":
                    try:
                        response = await handle_chat(text, tracker)
                    except Exception:
                        logger.exception("handle_chat error")
                        response = msg.CONNECTION_ERROR
                    await send_msg({"type": "complete", "message": response})
                    continue

                if category == "question":
                    try:
                        answer = await handle_question(text, tracker)
                    except Exception:
                        logger.exception("handle_question error")
                        answer = msg.CONNECTION_ERROR
                    await send_msg({"type": "complete", "message": answer})
                    continue

                if category == "ambiguous":
                    # If the cascade failed entirely we should tell the user
                    # so they understand the lack of action.
                    out = (
                        msg.CONNECTION_ERROR
                        if classification.degraded
                        else msg.AMBIGUOUS_REQUEST
                    )
                    await send_msg({"type": "complete", "message": out})
                    continue

                # category == "action"
                # Ask one clarifying question up front for vague requests so we
                # don't burn a 30-second browser session and fail.
                clarification = needs_clarification(text)
                if clarification:
                    await send_msg({"type": "complete", "message": clarification})
                    continue

                _record_task(rate_user)
                _total_tasks += 1
                crm_log_event(
                    "action_engine",
                    "task_started",
                    f"Task: {text[:80]}",
                    {"channel": "ws", "user_id": user_id},
                )

                # Run the agent in the background
                task_running = True
                # Snapshot user_id at task-start time so it can't change underneath us.
                task_user_id = user_id

                async def run_task(text_: str = text, uid: str | None = task_user_id):
                    nonlocal task_running
                    global _total_errors
                    try:
                        await execute_task(
                            goal=text_,
                            send=send_msg,
                            receive_confirmation=receive_confirmation,
                            user_id=uid,
                        )
                    except asyncio.CancelledError:
                        raise
                    except Exception:
                        _total_errors += 1
                        logger.exception("agent task crashed")
                        await send_msg({"type": "error", "message": msg.CONNECTION_ERROR})
                    finally:
                        task_running = False

                bg_task = asyncio.create_task(run_task())

            # --- Confirmation / continue ---
            elif msg_type in ("confirm", "continue"):
                value = data.get("value", data.get("text", "continue"))
                if not isinstance(value, str):
                    value = "continue"
                # Bound the confirmation payload too
                confirm_value[0] = value[:1024]
                confirm_event.set()

            elif msg_type == "cancel":
                # Allow the client to abort an in-flight task explicitly.
                if bg_task is not None and not bg_task.done():
                    bg_task.cancel()
                    await send_msg({"type": "status", "message": msg.TASK_INTERRUPTED})

            else:
                await send_msg({"type": "error", "message": msg.INPUT_INVALID})

    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("ws_task error")
        try:
            await websocket.close()
        except Exception:
            pass
    finally:
        # Cancel any running browser task so we don't leak browser sessions
        # or burn LLM tokens after the client disconnects.
        if bg_task is not None and not bg_task.done():
            bg_task.cancel()
            try:
                await bg_task
            except (asyncio.CancelledError, Exception):
                pass
        # Always release the connection counters — even if the browser task
        # is still cancelling. Otherwise a panic-disconnect leaks a slot
        # forever and the cap pins to "Too many connections" for that user.
        _ws_connection_release(admitted_user_id, admitted_ip)
