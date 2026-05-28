"""Localhost setup form on port 53118 — Omar pastes tokens in one
sitting, the form encrypts + writes them to ~/.anticipy/oauth/.

This is the alternative to email-reply parsing (which would require a
Gmail watch we haven't built). The flow:
  1. Agent sends one [ANTICIPY-Q] email with setup instructions +
     this form's URL.
  2. Omar follows the steps in each service's dashboard, comes back to
     the form, pastes the tokens, hits Submit.
  3. The form server encrypts each token with PROFILE_ENCRYPTION_KEY
     and writes to ~/.anticipy/oauth/{service}.token.
  4. Form server signals back to the runner.
"""

from __future__ import annotations

import http.server
import json
import os
import sys
import threading
import time
import urllib.parse
from pathlib import Path

from cryptography.fernet import Fernet
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
load_dotenv(REPO_ROOT / ".env.local")

OAUTH_DIR = Path.home() / ".anticipy" / "oauth"
OAUTH_DIR.mkdir(parents=True, exist_ok=True)
FORM_PORT = 53118

SUBMITTED: dict[str, dict] = {}


def _fernet() -> Fernet:
    key = os.environ.get("PROFILE_ENCRYPTION_KEY")
    if not key:
        raise SystemExit("PROFILE_ENCRYPTION_KEY missing")
    return Fernet(key.encode() if isinstance(key, str) else key)


def _save(service: str, payload: dict) -> Path:
    p = OAUTH_DIR / f"{service}.token"
    p.write_bytes(_fernet().encrypt(json.dumps(payload).encode("utf-8")))
    p.chmod(0o600)
    return p


def load_token(service: str) -> dict | None:
    p = OAUTH_DIR / f"{service}.token"
    if not p.exists():
        return None
    try:
        return json.loads(_fernet().decrypt(p.read_bytes()).decode("utf-8"))
    except Exception:
        return None


HTML_FORM = """<!DOCTYPE html>
<html><head>
<meta charset='utf-8'>
<title>Anticipy — token setup</title>
<style>
  body { font: 14px -apple-system, sans-serif; max-width: 720px; margin: 32px auto;
    padding: 24px; background: #0C0C0C; color: #F5F0EB; }
  h1 { color: #C8A97E; font-size: 20px; }
  h2 { color: #C8A97E; font-size: 15px; margin-top: 28px; }
  .ok { color: #6CC57E; }
  .pending { color: #888; }
  label { display: block; font-size: 12px; opacity: 0.7; margin-top: 12px; }
  input, textarea { width: 100%; padding: 8px; background: #1a1a1a;
    color: #F5F0EB; border: 1px solid #2a2a2a; border-radius: 4px;
    font: 12px monospace; box-sizing: border-box; }
  button { margin-top: 14px; padding: 8px 18px; background: #C8A97E;
    color: #0C0C0C; border: 0; border-radius: 4px; font-weight: 600;
    cursor: pointer; }
  .row { margin-bottom: 6px; padding: 4px 0; }
  pre { background: #1a1a1a; padding: 12px; border-radius: 4px;
    overflow-x: auto; font-size: 11px; }
</style>
</head><body>
<h1>Anticipy — token setup</h1>
<p>Paste tokens for each service. Submit each section independently;
the runner picks them up as soon as you submit.</p>
<div id='status'>Status loading…</div>

<h2>Slack</h2>
<form method='POST' action='/submit/slack'>
  <label>Bot User OAuth Token (xoxb-…)</label>
  <input name='bot_token' placeholder='xoxb-…' />
  <label>Test channel (e.g. #anticipy-test or C0123…)</label>
  <input name='channel' placeholder='#anticipy-test' />
  <button type='submit'>Save Slack</button>
</form>

<h2>Notion</h2>
<form method='POST' action='/submit/notion'>
  <label>Internal Integration Token (secret_…)</label>
  <input name='token' placeholder='secret_…' />
  <label>Test database ID (32 hex chars from the database URL)</label>
  <input name='database_id' placeholder='abcdef0123456789…' />
  <button type='submit'>Save Notion</button>
</form>

<h2>Linear</h2>
<form method='POST' action='/submit/linear'>
  <label>API key (lin_api_…)</label>
  <input name='api_key' placeholder='lin_api_…' />
  <label>Team ID (UUID — find in Linear settings → Teams → click team)</label>
  <input name='team_id' placeholder='aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee' />
  <button type='submit'>Save Linear</button>
</form>

<h2>Spotify</h2>
<form method='POST' action='/submit/spotify'>
  <label>Client ID</label>
  <input name='client_id' placeholder='32-char hex' />
  <label>Client Secret</label>
  <input name='client_secret' placeholder='32-char hex' />
  <p style='font-size:11px;opacity:0.6;'>Once saved, I'll open the OAuth consent flow in :9222 — click Allow on that tab.</p>
  <button type='submit'>Save Spotify</button>
</form>

<h2>Resy + Amazon (cookies)</h2>
<p>For these two, log in directly in the sandbox Chrome on :9222 (Cmd+Tab to the Anticipy Chrome window). Then submit below to confirm.</p>
<form method='POST' action='/submit/cookies'>
  <label><input type='checkbox' name='resy' value='1'> Logged in to resy.com</label>
  <label><input type='checkbox' name='amazon' value='1'> Logged in to amazon.com</label>
  <button type='submit'>Confirm logins</button>
</form>

<h2>Status</h2>
<pre id='statusJson'>loading…</pre>
<script>
async function refresh() {
  const r = await fetch('/status');
  const j = await r.json();
  document.getElementById('statusJson').textContent = JSON.stringify(j, null, 2);
  setTimeout(refresh, 3000);
}
refresh();
</script>
</body></html>"""


SERVICE_FIELDS = {
    "slack": ["bot_token", "channel"],
    "notion": ["token", "database_id"],
    "linear": ["api_key", "team_id"],
    "spotify": ["client_id", "client_secret"],
}


class _Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        if self.path == "/" or self.path == "/index.html":
            self._send(200, HTML_FORM, "text/html")
        elif self.path == "/status":
            status = {
                svc: ("saved" if (OAUTH_DIR / f"{svc}.token").exists() else "pending")
                for svc in ["google", "slack", "notion", "linear", "spotify", "cookies"]
            }
            self._send(200, json.dumps(status, indent=2), "application/json")
        else:
            self._send(404, "not found", "text/plain")

    def do_POST(self):  # noqa: N802
        clen = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(clen).decode("utf-8")
        params = {k: v[0] for k, v in urllib.parse.parse_qs(body).items()}
        if self.path.startswith("/submit/"):
            svc = self.path.split("/")[-1]
            if svc in SERVICE_FIELDS:
                payload = {f: params.get(f, "") for f in SERVICE_FIELDS[svc]}
                if not all(payload.values()):
                    self._send(400, "Missing fields", "text/plain")
                    return
                _save(svc, payload)
                SUBMITTED[svc] = payload
                self._send(200, f"<html><body style='background:#0C0C0C;color:#F5F0EB;font:14px sans-serif;padding:24px;'><h2 style='color:#6CC57E;'>{svc} saved.</h2><a href='/' style='color:#C8A97E;'>← back</a></body></html>", "text/html")
            elif svc == "cookies":
                payload = {
                    "resy_logged_in": params.get("resy") == "1",
                    "amazon_logged_in": params.get("amazon") == "1",
                    "confirmed_at": time.time(),
                }
                _save("cookies", payload)
                SUBMITTED["cookies"] = payload
                self._send(200, "<html><body style='background:#0C0C0C;color:#F5F0EB;font:14px sans-serif;padding:24px;'><h2 style='color:#6CC57E;'>Cookie status saved.</h2><a href='/' style='color:#C8A97E;'>← back</a></body></html>", "text/html")
            else:
                self._send(404, "unknown service", "text/plain")
        else:
            self._send(404, "not found", "text/plain")

    def log_message(self, *args, **kwargs):
        pass

    def _send(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        b = body.encode("utf-8") if isinstance(body, str) else body
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)


def serve(port: int = FORM_PORT, blocking: bool = True) -> http.server.HTTPServer:
    srv = http.server.HTTPServer(("127.0.0.1", port), _Handler)
    if blocking:
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            pass
        return srv
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    return srv


if __name__ == "__main__":
    print(f"Anticipy setup form: http://localhost:{FORM_PORT}/")
    serve()
