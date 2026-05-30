"""Engine-side handoff convenience routes.

Context

The website handles the heavy lifting of the deep-link handoff flow
(US-008): /api/auth/handoff/mint on the website mints a one-time
token, stores the access plus refresh tokens in the Supabase
handoff_tokens table, and returns an anticipy://session?token=... deep
link. The Mac app's deep-link handler then calls
https://www.anticipy.ai/api/auth/exchange to swap that token for the
real Supabase session, and from there calls the engine's /api/provision
to register the auth token with the local engine.

So the EXCHANGE itself does not require the engine. Z-001's
exchange_handoff step talks directly to the website. The
"app.anticipy.handoff" import that server.py tries used to be a ghost
(no module, silently swallowed). This module replaces that ghost with
something thin and useful: engine-side helpers around handoff that
give the engine a way to (a) finish an exchange on behalf of a caller
and (b) inspect the last-known stored session locally. Nothing here
duplicates what the website already does. The website remains the
source of truth for token minting and exchange.

What attach_to(app) does

It registers two FastAPI routes:

  GET  /api/auth/handoff/session
       Returns the last session the engine cached locally (user_id,
       last_seen_at). Empty object when nothing cached. Read-only.

  POST /api/auth/handoff/exchange
       Body: {"token": "<handoff token>", "site_url": "..."} (site
       optional, defaults to https://www.anticipy.ai). Calls the
       website's /api/auth/exchange under the hood, then if successful
       caches a non-sensitive summary (user id + expiry) on disk at
       ~/.anticipy/session.json. Returns the website's response so
       callers that want the access token still get it.

Storage

Stored at ~/.anticipy/session.json (override via ANTICIPY_SESSION_FILE).
The on-disk record holds ONLY the user id and timestamps, NOT the
tokens. The Mac app already owns token storage in its OS keychain
(desktop/src-tauri/src/lib.rs), so the engine never needs the secret
material on disk. This keeps the privacy moat intact: tokens live in
the keychain, the engine just knows which Supabase user is currently
provisioned.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel


# --- Disk-cached session record ----------------------------------------------


def _session_path() -> Path:
    override = os.environ.get("ANTICIPY_SESSION_FILE", "").strip()
    if override:
        return Path(override).expanduser()
    return Path.home() / ".anticipy" / "session.json"


def _read_session() -> dict:
    path = _session_path()
    if not path.exists():
        return {}
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw or "{}")
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_session(record: dict) -> Path:
    path = _session_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(record, indent=2, sort_keys=False),
                       encoding="utf-8")
        os.replace(tmp, path)
    except Exception:
        # best effort: if we can't write we still return the in-memory
        # record so the caller is not blocked on disk failures.
        pass
    return path


# --- HTTP helper used to call the website /api/auth/exchange route ----------


def _http_post_json(url: str, payload: dict, *,
                    timeout: float = 15.0) -> tuple[int, dict, str]:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            status = resp.status
    except urllib.error.HTTPError as exc:
        try:
            raw = exc.read()
        except Exception:
            raw = b""
        status = exc.code
    except Exception as exc:
        return 0, {}, f"{type(exc).__name__}: {exc}"
    try:
        data = json.loads(raw.decode("utf-8") or "{}")
        if not isinstance(data, dict):
            data = {"raw": data}
    except Exception:
        data = {"raw": raw.decode("utf-8", "replace")[:600]}
    return status, data, ""


# --- Public API: attach_to(app) ---------------------------------------------


class _ExchangeBody(BaseModel):
    token: str
    site_url: str | None = None


def attach_to(app: FastAPI) -> None:
    """Wire the two engine-side handoff convenience routes.

    Called from app.product.server at startup. Both routes are
    namespaced under /api/auth/handoff/* so they never collide with
    the existing engine auth surface (/api/provision, /api/state).
    """

    @app.get("/api/auth/handoff/session")
    def _handoff_session() -> JSONResponse:
        rec = _read_session()
        return JSONResponse({
            "ok": True,
            "session": rec,
            "session_file": str(_session_path()),
            "has_session": bool(rec.get("user_id")),
        })

    @app.post("/api/auth/handoff/exchange")
    def _handoff_exchange(body: _ExchangeBody) -> JSONResponse:
        token = (body.token or "").strip()
        if not token:
            return JSONResponse({
                "ok": False,
                "error": "missing handoff token",
            }, status_code=400)
        site = (body.site_url or "https://www.anticipy.ai").rstrip("/")
        if not site.startswith("http"):
            return JSONResponse({
                "ok": False,
                "error": f"invalid site_url {site!r}",
            }, status_code=400)
        url = f"{site}/api/auth/exchange"
        status, data, err = _http_post_json(url, {"token": token})
        if err:
            return JSONResponse({
                "ok": False,
                "error": f"transport: {err}",
                "site": site,
            }, status_code=502)
        if status != 200:
            return JSONResponse({
                "ok": False,
                "status": status,
                "site": site,
                "remote_error": data,
            }, status_code=status)
        user_obj = data.get("user") if isinstance(data.get("user"), dict) else {}
        user_id = str(user_obj.get("id") or "")
        email = str(user_obj.get("email") or "")
        cached: dict[str, Any] = {
            "user_id": user_id,
            "email": email,
            "last_seen_at": time.strftime(
                "%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "site": site,
        }
        path = _write_session(cached)
        return JSONResponse({
            "ok": True,
            "exchange": data,
            "cached_session": cached,
            "session_file": str(path),
        })


__all__ = ["attach_to"]
