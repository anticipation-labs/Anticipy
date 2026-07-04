"""Grader-owned two-page CARRY backend for browser_eval task (D) — carry_form.

Harder than a single-page fill: the agent must READ a value off page 1 and CARRY
it into a form on page 2, then submit. This exercises genuine multi-step
cross-page state, which the single-form tasks (httpbin_form / local_form) do not.

Endpoints:
  * ``GET /``       -> page 1: shows a server-generated **claim token** the agent
                       must read (it is NOT in the task text, so it can only be
                       obtained by actually reading this page), plus a link to
                       ``/form``.
  * ``GET /form``   -> page 2: the shipping/claim form (posts to ``/submit``).
  * ``POST /submit``-> records the exact submitted fields in server memory.
  * ``GET /last``   -> the last-received submission as JSON (checker re-reads this).
  * ``GET /token``  -> the ground-truth token the server actually displayed on
                       page 1 (the checker compares this against what was
                       submitted — an independent postcondition the agent can't
                       forge without truly reading page 1).
  * ``GET /reset``  -> clears the recorded submission and rotates a fresh token.

The whole point of the gate: because the checker re-reads BOTH the token the
server displayed (``/token``) AND the token the server received in the submit
(``/last``), a hand that skips page 1 and guesses — or that "fills" the DOM
without a real trusted submit — cannot match, and fails.

Standalone:  python3 server.py --port 8902        (Ctrl-C to stop)
Embedded:    from server import start; h = start(); ... ; h.stop()
"""
from __future__ import annotations

import argparse
import json
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

PAGE1_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><title>Claim Portal</title></head>
<body>
<h1>Claim portal</h1>
<p>Your claim token is <code id="token">{token}</code>.</p>
<p>Continue to the form and enter this exact token to confirm your claim.</p>
<p><a href="/form">Continue to the form</a></p>
</body></html>
"""

FORM_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><title>Confirm claim</title></head>
<body>
<h1>Confirm your claim</h1>
<form action="/submit" method="post">
  <p><label>Claim token: <input type="text" name="claim_token"></label></p>
  <p><label>Full name: <input type="text" name="fullname"></label></p>
  <p><label>Department:
    <select name="department">
      <option value="sales">Sales</option>
      <option value="operations">Operations</option>
      <option value="support">Support</option>
    </select></label></p>
  <p><label>Notes: <textarea name="notes"></textarea></label></p>
  <p><label><input type="checkbox" name="confirm" value="yes"> I confirm the token above is correct</label></p>
  <p><button type="submit">Submit claim</button></p>
</form>
</body></html>
"""


class _State:
    """Process-wide store: the token we displayed + the last submission."""
    token: str = ""
    last: dict | None = None
    lock = threading.Lock()


def _new_token() -> str:
    return "CLM-" + secrets.token_hex(3).upper()


def _receipt(fields: dict) -> str:
    return ("<!doctype html><html><body><h1>Claim received</h1>"
            f"<pre id='receipt'>{json.dumps(fields, sort_keys=True)}</pre>"
            "<p>Thank you. Your claim has been recorded.</p></body></html>")


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *_a):  # keep test output clean
        return

    def _send(self, code: int, body: str, ctype: str = "text/html") -> None:
        raw = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", f"{ctype}; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):  # noqa: N802
        path = urlparse(self.path).path
        if path in ("/", "/claim"):
            with _State.lock:
                tok = _State.token
            self._send(200, PAGE1_HTML.format(token=tok))
        elif path == "/form":
            self._send(200, FORM_HTML)
        elif path == "/last":
            with _State.lock:
                self._send(200, json.dumps(_State.last or {}), "application/json")
        elif path == "/token":
            with _State.lock:
                self._send(200, json.dumps({"token": _State.token}), "application/json")
        elif path == "/reset":
            with _State.lock:
                _State.last = None
                _State.token = _new_token()
            self._send(200, json.dumps({"ok": True}), "application/json")
        else:
            self._send(404, "not found")

    def do_POST(self):  # noqa: N802
        path = urlparse(self.path).path
        if path != "/submit":
            self._send(404, "not found")
            return
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length).decode("utf-8") if length else ""
        parsed = parse_qs(raw, keep_blank_values=True)
        fields = {k: (v[0] if len(v) == 1 else v) for k, v in parsed.items()}
        with _State.lock:
            _State.last = fields
        self._send(200, _receipt(fields))


class Handle:
    def __init__(self, httpd: ThreadingHTTPServer, thread: threading.Thread):
        self._httpd = httpd
        self._thread = thread
        host, port = httpd.server_address[0], httpd.server_address[1]
        self.host = host
        self.port = port
        self.url = f"http://{host}:{port}/"

    def token(self) -> str:
        with _State.lock:
            return _State.token

    def last(self) -> dict:
        with _State.lock:
            return dict(_State.last or {})

    def reset(self) -> None:
        with _State.lock:
            _State.last = None
            _State.token = _new_token()

    def stop(self) -> None:
        try:
            self._httpd.shutdown()
            self._httpd.server_close()
        except Exception:
            pass


def start(port: int = 0, host: str = "127.0.0.1") -> Handle:
    """Start the server on a background thread. port=0 picks a free port. A fresh
    token is minted so every grader session carries a distinct, unforgeable value."""
    _State.last = None
    _State.token = _new_token()
    httpd = ThreadingHTTPServer((host, port), _Handler)
    t = threading.Thread(target=httpd.serve_forever, name="carry-form-server", daemon=True)
    t.start()
    return Handle(httpd, t)


def main() -> int:
    ap = argparse.ArgumentParser(description="Grader-owned two-page carry backend")
    ap.add_argument("--port", type=int, default=8902)
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()
    h = start(args.port, args.host)
    print(f"carry form server on {h.url}  (GET /  ·  GET /form  ·  POST /submit  ·  "
          f"GET /last  ·  GET /token  ·  GET /reset)   token={h.token()}")
    try:
        while True:
            threading.Event().wait(3600)
    except KeyboardInterrupt:
        h.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
