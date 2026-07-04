"""Grader-owned deterministic form backend for browser_eval task (B).

The gold-standard *independent* postcondition: a tiny HTTP server that

  * serves a real HTML form at ``GET /``  (posts to ``/submit``),
  * on ``POST /submit`` records the exact submitted fields in server memory,
  * exposes ``GET /last``  -> the last-received submission as JSON,
  * exposes ``GET /reset`` -> clears the recorded submission.

Because the record lives on the *server*, the checker re-reads what the backend
actually received (via ``/last``) rather than trusting anything the agent says it
did. A hand that "fills" the DOM without a real trusted submit never produces a
``/last`` record, so it fails — which is the whole point of the gate.

Standalone:  python3 server.py --port 8901        (Ctrl-C to stop)
Embedded:    from server import start; h = start(); ... ; h.stop()

Note on the live lane: ``/agent/run`` has an SSRF gate that refuses loopback /
private start URLs, so a live run points the agent at a public tunnel (env
``ANTICIPY_LOCALFORM_URL``) that forwards to this server; the *checker* still
reads ``/last`` on the same backend. In the ``--selftest`` lane everything is
loopback and in-process.
"""
from __future__ import annotations

import argparse
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

# The exact form httpbin's is modelled on, but backed by real storage. The field
# names are deliberately mundane (a shipping form) so the agent has to reason
# about a normal page, not a bespoke test fixture.
FORM_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><title>Arena Shipping Form</title></head>
<body>
<h1>Shipping details</h1>
<form action="/submit" method="post">
  <p><label>Full name: <input type="text" name="fullname"></label></p>
  <p><label>Order code: <input type="text" name="order_code"></label></p>
  <p><label>Address: <input type="text" name="address"></label></p>
  <p><label>Ship speed:
    <select name="speed">
      <option value="standard">Standard</option>
      <option value="express">Express</option>
    </select></label></p>
  <p><label>Notes: <textarea name="notes"></textarea></label></p>
  <p><button type="submit">Submit order</button></p>
</form>
</body></html>
"""


class _State:
    """Process-wide last-submission store (one server = one grader session)."""
    last: dict | None = None
    lock = threading.Lock()


def _receipt(fields: dict) -> str:
    return ("<!doctype html><html><body><h1>Order received</h1>"
            f"<pre id='receipt'>{json.dumps(fields, sort_keys=True)}</pre>"
            "<p>Thank you. Your order has been recorded.</p></body></html>")


class _Handler(BaseHTTPRequestHandler):
    # keep the test output clean
    def log_message(self, *_a):  # noqa: D401
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
        if path in ("/", "/form"):
            self._send(200, FORM_HTML)
        elif path == "/last":
            with _State.lock:
                self._send(200, json.dumps(_State.last or {}), "application/json")
        elif path == "/reset":
            with _State.lock:
                _State.last = None
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
    """A running server you can point an agent at and later read back from."""

    def __init__(self, httpd: ThreadingHTTPServer, thread: threading.Thread):
        self._httpd = httpd
        self._thread = thread
        host, port = httpd.server_address[0], httpd.server_address[1]
        self.host = host
        self.port = port
        self.url = f"http://{host}:{port}/"

    def last(self) -> dict:
        with _State.lock:
            return dict(_State.last or {})

    def reset(self) -> None:
        with _State.lock:
            _State.last = None

    def stop(self) -> None:
        try:
            self._httpd.shutdown()
            self._httpd.server_close()
        except Exception:
            pass


def start(port: int = 0, host: str = "127.0.0.1") -> Handle:
    """Start the server on a background thread. port=0 picks a free port."""
    _State.last = None
    httpd = ThreadingHTTPServer((host, port), _Handler)
    t = threading.Thread(target=httpd.serve_forever, name="local-form-server", daemon=True)
    t.start()
    return Handle(httpd, t)


def main() -> int:
    ap = argparse.ArgumentParser(description="Grader-owned deterministic form backend")
    ap.add_argument("--port", type=int, default=8901)
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()
    h = start(args.port, args.host)
    print(f"local form server on {h.url}  (GET /  ·  POST /submit  ·  GET /last  ·  GET /reset)")
    try:
        while True:
            threading.Event().wait(3600)
    except KeyboardInterrupt:
        h.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
