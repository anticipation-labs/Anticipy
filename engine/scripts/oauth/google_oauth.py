"""Google OAuth flow for the agent — covers Gmail, Calendar, Sheets,
Maps in a single consent.

Architecture:
  1. Spin up a tiny localhost callback server on port 53117.
  2. Build the consent URL with offline access (so we get a refresh
     token) + all the scopes the 4 Google skills need.
  3. Open the URL in Chrome :9222 (the agent's CDP-attached browser)
     and bring the tab to front so the user actually sees the
     consent.
  4. Poll the callback server until it receives ?code=... — that
     means the user clicked Allow.
  5. Exchange the code for access_token + refresh_token via Google's
     token endpoint.
  6. Encrypt with PROFILE_ENCRYPTION_KEY (Fernet) and write to
     ~/.anticipy/oauth/google.token. Refresh logic in
     load_google_token() handles renewal automatically.

Per Rule D: opening a browser tab + waiting for Omar's Allow click
is not a halt — it's a one-time consent that flows through to
real-production-test capability for 4 skills.
"""

from __future__ import annotations

import argparse
import base64
import http.server
import json
import os
import sys
import threading
import time
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import httpx
from cryptography.fernet import Fernet
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
load_dotenv(REPO_ROOT / ".env.local")

OAUTH_DIR = Path.home() / ".anticipy" / "oauth"
OAUTH_DIR.mkdir(parents=True, exist_ok=True)
TOKEN_PATH = OAUTH_DIR / "google.token"

CALLBACK_PORT = 53117
REDIRECT_URI = f"http://localhost:{CALLBACK_PORT}/oauth2callback"

SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/spreadsheets",
    # Google Maps Places API uses the API key, not OAuth — but we
    # request a profile scope so the consent screen shows the user's
    # account context cleanly.
    "https://www.googleapis.com/auth/userinfo.email",
]


@dataclass
class _CallbackResult:
    code: Optional[str] = None
    error: Optional[str] = None
    received_at: float = 0.0


_callback_state = _CallbackResult()


class _OAuthCallbackHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/oauth2callback":
            self.send_response(404)
            self.end_headers()
            return
        params = urllib.parse.parse_qs(parsed.query)
        if "error" in params:
            _callback_state.error = params["error"][0]
        elif "code" in params:
            _callback_state.code = params["code"][0]
            _callback_state.received_at = time.time()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        body = (
            "<html><body style='font:16px sans-serif; padding:48px; "
            "background:#0C0C0C; color:#F5F0EB;'>"
            "<h2 style='color:#C8A97E'>Anticipy OAuth — done.</h2>"
            "<p>You can close this tab. The agent has the token.</p>"
            "</body></html>"
        )
        self.wfile.write(body.encode("utf-8"))

    def log_message(self, *args, **kwargs):
        pass  # silence default logging


def _start_callback_server() -> http.server.HTTPServer:
    srv = http.server.HTTPServer(("127.0.0.1", CALLBACK_PORT), _OAuthCallbackHandler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    return srv


def _build_consent_url(client_id: str) -> str:
    params = {
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",  # forces refresh_token issuance
        "include_granted_scopes": "true",
    }
    return "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params)


def _open_in_chrome_9222(url: str) -> bool:
    """Open url in Chrome :9222 via CDP. Brings the tab to front so the
    user sees the consent screen. Returns True on success.
    """
    try:
        # PUT /json/new opens a new tab with the given URL
        r = httpx.put(
            f"http://localhost:9222/json/new?{urllib.parse.quote(url, safe='')}",
            timeout=10.0,
        )
        r.raise_for_status()
        tab = r.json()
        ws_url = tab.get("webSocketDebuggerUrl")
        if not ws_url:
            return False
        # Bring the tab to front via Page.bringToFront over the WS
        # Doing this with a one-shot websocket call.
        try:
            from websockets.sync.client import connect  # type: ignore
        except ImportError:
            # If sync.client isn't available in this version, skip
            # bringToFront — the tab is open, user can just switch to it.
            return True
        with connect(ws_url, max_size=1_000_000) as ws:
            ws.send(json.dumps({"id": 1, "method": "Page.enable"}))
            ws.recv()
            ws.send(json.dumps({"id": 2, "method": "Page.bringToFront"}))
            ws.recv()
        return True
    except Exception as e:
        print(f"[oauth] failed to open in :9222 — {e}", file=sys.stderr)
        return False


def _exchange_code_for_token(code: str, client_id: str, client_secret: str) -> dict:
    r = httpx.post(
        "https://oauth2.googleapis.com/token",
        data={
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": REDIRECT_URI,
            "grant_type": "authorization_code",
        },
        timeout=15.0,
    )
    r.raise_for_status()
    return r.json()


def _fernet_from_env() -> Fernet:
    key = os.environ.get("PROFILE_ENCRYPTION_KEY")
    if not key:
        raise SystemExit("PROFILE_ENCRYPTION_KEY missing from env")
    return Fernet(key.encode() if isinstance(key, str) else key)


def save_token(payload: dict) -> Path:
    f = _fernet_from_env()
    enc = f.encrypt(json.dumps(payload).encode("utf-8"))
    TOKEN_PATH.write_bytes(enc)
    TOKEN_PATH.chmod(0o600)
    return TOKEN_PATH


def load_google_token() -> Optional[dict]:
    """Load + auto-refresh the Google token. Returns dict with
    access_token + refresh_token + expires_at, or None if not authed.
    """
    if not TOKEN_PATH.exists():
        return None
    f = _fernet_from_env()
    try:
        payload = json.loads(f.decrypt(TOKEN_PATH.read_bytes()).decode("utf-8"))
    except Exception:
        return None
    # Refresh if expiring within 60 s
    if payload.get("expires_at", 0) - time.time() < 60:
        client_id = os.environ.get("GOOGLE_OAUTH_CLIENT_ID")
        client_secret = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET")
        rt = payload.get("refresh_token")
        if not (client_id and client_secret and rt):
            return payload  # best-effort; caller will hit a 401 and surface it
        try:
            r = httpx.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "refresh_token": rt,
                    "grant_type": "refresh_token",
                },
                timeout=15.0,
            )
            r.raise_for_status()
            new = r.json()
            payload["access_token"] = new["access_token"]
            payload["expires_at"] = time.time() + int(new.get("expires_in", 3600))
            save_token(payload)
        except Exception as e:
            print(f"[oauth] refresh failed: {e}", file=sys.stderr)
    return payload


def run_consent_flow(timeout_s: int = 600) -> dict:
    """Full consent flow. Blocks up to timeout_s waiting for callback."""
    client_id = os.environ.get("GOOGLE_OAUTH_CLIENT_ID")
    client_secret = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET")
    if not (client_id and client_secret):
        raise SystemExit("GOOGLE_OAUTH_CLIENT_ID/_SECRET missing from env")

    srv = _start_callback_server()
    try:
        url = _build_consent_url(client_id)
        opened = _open_in_chrome_9222(url)
        print(json.dumps({
            "consent_url": url,
            "opened_in_9222": opened,
            "callback_listening_on": REDIRECT_URI,
            "next": "switch to the Chrome window on profile ~/.anticipy/chrome-profile/, sign in to Google, click Allow.",
        }, indent=2))

        deadline = time.time() + timeout_s
        while time.time() < deadline:
            if _callback_state.code:
                tok = _exchange_code_for_token(_callback_state.code, client_id, client_secret)
                tok["expires_at"] = time.time() + int(tok.get("expires_in", 3600))
                tok["scopes_at_consent"] = SCOPES
                path = save_token(tok)
                return {"ok": True, "token_path": str(path), "has_refresh": bool(tok.get("refresh_token"))}
            if _callback_state.error:
                return {"ok": False, "error": _callback_state.error}
            time.sleep(0.5)
        return {"ok": False, "error": "consent_timeout"}
    finally:
        srv.shutdown()


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--timeout", type=int, default=600)
    args = p.parse_args()
    out = run_consent_flow(timeout_s=args.timeout)
    print(json.dumps(out, indent=2))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
