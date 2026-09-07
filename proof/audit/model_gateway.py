"""Loopback-only audit transport with a crash-safe, shared dollar reservation.

The production brain still builds prompts, judges, retries and parses replies.
Only its HTTP endpoint changes. This gateway never interprets a human request.
It caps output, disables paid add-ons/cache writes, and reserves the price of
an ENTIRE model context before forwarding. Unknown costs keep the reservation.
No request is retried here; a caller retry receives a separate reservation.
"""
from __future__ import annotations

import argparse
import copy
import fcntl
import hashlib
import hmac
import json
import math
import os
import secrets
import threading
import time
import urllib.error
import urllib.request
import urllib.parse
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
UPSTREAM = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_STATE = ROOT / "work/audit"


class Refused(ValueError):
    pass


def atomic_json(path: Path, data):
    temporary = path.with_name(path.name + ".tmp")
    fd = os.open(temporary, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w") as out:
        json.dump(data, out, indent=2)
        out.write("\n")
        out.flush()
        os.fsync(out.fileno())
    os.replace(temporary, path)
    descriptor = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


class Budget:
    def __init__(self, path: Path, operating_limit=25.0):
        self.path = path
        self.operating_limit = operating_limit
        self.mutex = threading.RLock()

    @contextmanager
    def locked(self):
        with self.mutex, open(str(self.path) + ".lock", "a+") as lock:
            os.chmod(lock.name, 0o600)
            fcntl.flock(lock, fcntl.LOCK_EX)
            state = json.loads(self.path.read_text())
            try:
                yield state
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    @staticmethod
    def committed(state):
        return sum(c.get("cost_usd") if c.get("cost_usd") is not None
                   else c["reserved_usd"] for c in state["calls"])

    def reserve(self, dollars, model, body, audit_run=None):
        if not math.isfinite(dollars) or dollars <= 0:
            raise Refused("invalid reservation")
        with self.locked() as state:
            limit = min(float(state["budget_usd"]), self.operating_limit)
            if state.get("halted") or self.committed(state) + dollars > limit:
                raise Refused("audit spending limit reached or ledger halted")
            request_id = secrets.token_hex(12)
            state["calls"].append({
                "id": request_id, "at": time.time(), "model": model, "audit_run": audit_run,
                "request_sha256": hashlib.sha256(body).hexdigest(),
                "reserved_usd": dollars, "cost_usd": None, "state": "reserved",
            })
            state["committed_estimate_usd"] = self.committed(state)
            atomic_json(self.path, state)
            return request_id

    def finish(self, request_id, response=None, status="uncertain"):
        with self.locked() as state:
            entry = next(c for c in state["calls"] if c["id"] == request_id)
            entry["state"] = status
            if response:
                entry["generation_id"] = response.get("id")
                usage = response.get("usage") or {}
                entry["usage"] = usage
                cost = usage.get("cost")
                if isinstance(cost, (int, float)) and not isinstance(cost, bool) and math.isfinite(cost) and cost >= 0:
                    entry["cost_usd"] = cost
                    if cost > entry["reserved_usd"]:
                        state["halted"] = "provider cost exceeded conservative reservation"
            state["committed_estimate_usd"] = self.committed(state)
            state["observed_cost_usd"] = sum(c.get("cost_usd") or 0 for c in state["calls"])
            atomic_json(self.path, state)


ALLOWED_FIELDS = {
    "model", "messages", "temperature", "seed", "usage", "max_tokens",
    "max_completion_tokens", "response_format", "tools", "tool_choice",
    "parallel_tool_calls", "top_p", "stop", "frequency_penalty", "presence_penalty",
    "stream", "n",
}


def prepare(payload, pricing):
    if not isinstance(payload, dict) or set(payload) - ALLOWED_FIELDS:
        raise Refused("unsupported request field; paid add-ons and alternate routing are disabled")
    model = payload.get("model")
    if model not in pricing:
        raise Refused("model was not priced for this audit")
    if payload.get("stream", False) is not False or payload.get("n", 1) != 1:
        raise Refused("only one non-streaming completion is supported")
    data = copy.deepcopy(payload)
    messages = data.get("messages")
    if not isinstance(messages, list) or not messages:
        raise Refused("messages are required")
    for message in messages:
        if not isinstance(message, dict):
            raise Refused("invalid message")
        message.pop("cache_control", None)
        content = message.get("content")
        if isinstance(content, list):
            for block in content:
                if not isinstance(block, dict) or block.get("type") != "text" or not isinstance(block.get("text"), str):
                    raise Refused("this audit transport currently supports text only")
                block.pop("cache_control", None)
        elif not isinstance(content, str) and content is not None:
            raise Refused("invalid message content")
    tools = data.get("tools", [])
    if not isinstance(tools, list) or any(t.get("type") != "function" for t in tools):
        raise Refused("only client-executed function tools are allowed")
    for tool in tools:
        tool.pop("cache_control", None)
    requested = data.pop("max_completion_tokens", data.get("max_tokens", 4096))
    if isinstance(requested, bool) or not isinstance(requested, int) or requested < 1:
        raise Refused("invalid completion limit")
    data["max_tokens"] = min(requested, 4096)
    data["stream"] = False
    data["n"] = 1
    data["usage"] = {"include": True}
    info = pricing[model]
    price = info["pricing"]
    rates = [price] + price.get("overrides", [])
    prompt = max(float(p.get("prompt", price["prompt"])) for p in rates)
    completion = max(float(p.get("completion", price["completion"])) for p in rates)
    # OpenRouter max_price uses USD per million tokens; reservation uses USD.
    data["provider"] = {"require_parameters": True, "max_price": {
        "prompt": prompt * 1_000_000, "completion": completion * 1_000_000, "request": 0,
    }}
    dollars = info["context_length"] * prompt + data["max_tokens"] * completion
    return data, dollars


class Gateway:
    def __init__(self, directory: Path, operating_limit=25.0):
        self.directory = directory
        self.pricing = json.loads((directory / "model-pricing.json").read_text())
        authorized = float(json.loads((directory / "spend.json").read_text())["budget_usd"])
        if not math.isfinite(operating_limit) or not 0 < operating_limit <= authorized:
            raise ValueError("Operating ceiling must fit inside the authorized ledger budget")
        self.budget = Budget(directory / "spend.json", operating_limit=operating_limit)
        self.key = json.loads((directory / "secrets.json").read_text())["OPENROUTER_API_KEY"]
        token_file = directory / "gateway-token"
        if not token_file.exists():
            descriptor = os.open(token_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "w") as out:
                out.write(secrets.token_urlsafe(32))
        self.token = token_file.read_text().strip()
        self.traces = directory / "model-traces"
        self.traces.mkdir(mode=0o700, exist_ok=True)

    def handle(self, payload, audit_run=None):
        data, reservation = prepare(payload, self.pricing)
        body = json.dumps(data).encode()
        request_id = self.budget.reserve(reservation, data["model"], body, audit_run)
        atomic_json(self.traces / (request_id + "-request.json"), data)
        request = urllib.request.Request(UPSTREAM, body, headers={
            "Authorization": "Bearer " + self.key, "Content-Type": "application/json",
            "HTTP-Referer": "https://anticipy.ai", "X-Title": "Anticipy isolated audit",
        })
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                result = json.load(response)
            atomic_json(self.traces / (request_id + "-response.json"), result)
            self.budget.finish(request_id, result, "returned")
            return result
        except Exception:
            # A response loss can follow a charged completion. Keep the full
            # reservation until a provider ledger proves the actual amount.
            self.budget.finish(request_id, status="uncertain")
            raise


def serve(directory, port, operating_limit=25.0):
    gateway = Gateway(directory, operating_limit=operating_limit)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass  # neither prompts nor credentials belong in terminal logs

        def answer(self, status, data):
            body = json.dumps(data).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def do_POST(self):
            url = urllib.parse.urlsplit(self.path)
            query = urllib.parse.parse_qs(url.query)
            tags = query.get("audit_run", [])
            if set(query) - {"audit_run"} or len(tags) > 1:
                return self.answer(400, {"error": "invalid audit attribution"})
            audit_run = tags[0] if tags else None
            if audit_run and (len(audit_run) > 120 or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-/" for c in audit_run)):
                return self.answer(400, {"error": "invalid audit attribution"})
            if url.path != "/api/v1/chat/completions":
                return self.answer(404, {"error": "unknown route"})
            if not hmac.compare_digest(self.headers.get("Authorization", ""), "Bearer " + gateway.token):
                return self.answer(401, {"error": "invalid audit credential"})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length < 1 or length > 4_000_000:
                    raise Refused("invalid request size")
                payload = json.loads(self.rfile.read(length))
                result = gateway.handle(payload, audit_run)
            except Refused as error:
                return self.answer(402, {"error": str(error)})
            except urllib.error.HTTPError as error:
                return self.answer(error.code, {"error": "model provider refused the request; reservation retained"})
            except Exception:
                return self.answer(502, {"error": "model result unavailable; reservation retained if dispatched"})
            self.answer(200, result)

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"Audit model transport listening on 127.0.0.1:{port}; US${operating_limit:g} operating ceiling; authorized ledger budget unchanged", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--port", type=int, default=8790)
    parser.add_argument("--operating-limit", type=float, default=25.0)
    args = parser.parse_args()
    serve(args.state, args.port, args.operating_limit)
