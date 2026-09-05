#!/usr/bin/env python3
"""A fake model provider for proving what src/llm.ts puts on the wire.

    python3 migration/workers/scripts/fake_llm_provider.py --port 9797

Speaks both shapes the proxy speaks, on the same paths the real hosts use, so
`LLM_PROVIDER_BASE=http://127.0.0.1:9797` is the ONLY thing that changes:

    POST /api/v1/chat/completions                       OpenRouter
    POST /v1beta/models/<model>:generateContent         Google
    GET  /health                                        the runner's readiness probe

WHAT IT ANSWERS. The request it received, so a test can assert the floor, the
json_object passthrough and the thinking config from the CLIENT side without a
side channel:

  * OpenRouter path: a chat-completions body with `_fake.received` (the parsed
    request) and `_fake.headers` (PRESENCE of the credential headers). The
    proxy passes OpenRouter's JSON through verbatim, so `_fake` reaches the
    test unchanged.
  * Google path: a generateContent body whose single text part is the JSON of
    {received, headers, path}. The proxy translates that into
    choices[0].message.content, and the test parses it back.

IT NEVER ECHOES A HEADER VALUE. Only `authorization_present`, the scheme, and
`x_goog_api_key_present`. If it echoed the value, the proxy's verbatim
passthrough would carry the key to the client on CORRECT code, and the
"no key in any response" assertion could not distinguish a leak from a
fixture. Presence proves the proxy presented the credential; absence from the
client body proves it kept it.

THE FIXTURE'S FAILURE MODES are chosen by markers in the request body, which
is a test fixture's job and not a product decision:

    FAKE:STATUS=NNN   answer NNN with {"error": {"message": ..., "code": NNN}}
    FAKE:NOJSON       answer 200 with a body that is not JSON
    FAKE:NOTEXT       (Google) answer 200 with a candidate that has no text
    FAKE:SLEEP=S      wait S seconds first (for a timeout spike; not used by
                      the suite, which cannot afford 95 s)

Standard library only, like the contract suite it serves.
"""
import argparse
import json
import re
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

STATUS_RE = re.compile(r"FAKE:STATUS=(\d{3})")
SLEEP_RE = re.compile(r"FAKE:SLEEP=(\d+(?:\.\d+)?)")
GOOGLE_RE = re.compile(r"^/v1beta/models/([^/:]+):generateContent$")


class Handler(BaseHTTPRequestHandler):
    server_version = "fake-llm-provider/1"
    quiet = True

    def log_message(self, fmt, *args):
        if not self.quiet:
            sys.stderr.write("fake-provider: " + (fmt % args) + "\n")

    def _send(self, status, body, content_type="application/json"):
        raw = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _headers_seen(self):
        auth = self.headers.get("Authorization") or ""
        return {
            "authorization_present": bool(auth),
            "authorization_scheme": auth.split(" ", 1)[0] if auth else "",
            "x_goog_api_key_present": bool(self.headers.get("x-goog-api-key")),
            "http_referer": self.headers.get("HTTP-Referer") or "",
            "x_title": self.headers.get("X-Title") or "",
            "content_type": self.headers.get("Content-Type") or "",
        }

    def do_GET(self):
        if self.path == "/health":
            return self._send(200, json.dumps({"ok": True}))
        return self._send(404, json.dumps({"error": "no such path"}))

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or "0")
        raw = self.rfile.read(length).decode("utf-8", "replace") if length else ""
        try:
            received = json.loads(raw) if raw else {}
        except ValueError:
            return self._send(400, json.dumps({"error": "fake provider got non-JSON"}))

        sleep = SLEEP_RE.search(raw)
        if sleep:
            time.sleep(float(sleep.group(1)))
        forced = STATUS_RE.search(raw)
        if forced:
            code = int(forced.group(1))
            return self._send(code, json.dumps(
                {"error": {"message": "fake provider refused", "code": code}}))
        if "FAKE:NOJSON" in raw:
            return self._send(200, "this is not json", "text/plain")

        seen = self._headers_seen()
        google = GOOGLE_RE.match(self.path)
        if google:
            model = google.group(1)
            if "FAKE:NOTEXT" in raw:
                return self._send(200, json.dumps(
                    {"candidates": [{"content": {"parts": [], "role": "model"},
                                     "finishReason": "STOP"}]}))
            text = json.dumps({"received": received, "headers": seen, "path": self.path})
            return self._send(200, json.dumps({
                "candidates": [{
                    "content": {"parts": [{"text": text}], "role": "model"},
                    "finishReason": "STOP",
                }],
                "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 5,
                                  "totalTokenCount": 15},
                "modelVersion": model,
            }))

        if self.path == "/api/v1/chat/completions":
            return self._send(200, json.dumps({
                "id": "fake-" + str(int(time.time() * 1000)),
                "object": "chat.completion",
                "model": received.get("model") if isinstance(received, dict) else None,
                "choices": [{"index": 0, "finish_reason": "stop",
                             "message": {"role": "assistant", "content": "ok"}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 1, "total_tokens": 11},
                "_fake": {"received": received, "headers": seen, "path": self.path},
            }))

        return self._send(404, json.dumps({"error": "no such path", "path": self.path}))


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--port", type=int, default=9797)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    Handler.quiet = not args.verbose
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    sys.stderr.write("fake-provider: listening on http://%s:%d\n" % (args.host, args.port))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
