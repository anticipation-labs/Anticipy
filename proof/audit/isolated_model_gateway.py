"""Fresh, loopback-only task-evaluation transport; explicit dollar and call caps.

No production backend is imported or contacted. Only a selected dotenv key is
read as data. Every call reserves the entire priced model context plus bounded
output before dispatch; unknown cost halts the run without releasing its hold.
Restart with the same directory is refused, never a way to reset a journal.
Model semantics and production prompts are not changed by this transport.
CLI startup requires both approved limits; the existing US$5/100-call safety
ceilings cannot be raised here. A smaller grant is enforced, not merely logged.
"""
from __future__ import annotations

import argparse
import asyncio
import hmac
import json
import math
import os
from pathlib import Path
import secrets
import stat
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import httpx

from proof.audit.local_env_preflight import parse
from proof.audit.model_gateway import Budget, Refused, UPSTREAM, atomic_json, prepare

MODELS = {"deepseek/deepseek-v3.2", "google/gemini-3.1-pro-preview", "anthropic/claude-sonnet-4.6"}
MAX_RESPONSE_BYTES = 2_000_000
MAX_REQUEST_BYTES = 256_000


def validate_bounds(budget_usd, max_calls, lifetime):
    if (type(budget_usd) not in (int, float) or not 0 < budget_usd <= 5
            or not math.isfinite(budget_usd)
            or type(max_calls) is not int or not 1 <= max_calls <= 100
            or type(lifetime) not in (int, float) or not 0 < lifetime <= 1800
            or not math.isfinite(lifetime)):
        raise Refused("invalid run bounds")


def read_key(path: Path) -> str:
    try:
        with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), "rb") as stream:
            info = os.fstat(stream.fileno())
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                    or stat.S_IMODE(info.st_mode) & 0o077 or info.st_size > 1_000_000):
                raise Refused("credential file must be private, regular and bounded")
            raw = stream.read(1_000_001)
            if len(raw) > 1_000_000:
                raise Refused("credential file size refused")
            values, duplicates, invalid = parse(raw.decode())
            key = values.get("OPENROUTER_API_KEY", "")
            if duplicates or invalid or not key:
                raise Refused("credential file is missing or ambiguous")
            return key
    except (OSError, UnicodeError):
        raise Refused("private credential file unavailable") from None


async def post_model(key, payload, *, timeout=90, transport=None):
    async def request():
        async with httpx.AsyncClient(timeout=httpx.Timeout(80, connect=10),
                                     follow_redirects=False, trust_env=False,
                                     transport=transport) as client:
            async with client.stream("POST", UPSTREAM, json=payload, headers={
                "Authorization": "Bearer " + key, "HTTP-Referer": "https://anticipy.ai",
                "X-Title": "Anticipy isolated task evaluation",
            }) as response:
                if response.status_code != 200:
                    raise Refused("provider HTTP " + str(response.status_code) + "; reservation retained")
                body = bytearray()
                async for chunk in response.aiter_bytes(chunk_size=65536):
                    body.extend(chunk)
                    if len(body) > MAX_RESPONSE_BYTES:
                        raise Refused("provider response size refused")
                result = json.loads(body)
                if not isinstance(result, dict) or "error" in result:
                    raise Refused("provider result unavailable")
                return result
    try:
        return await asyncio.wait_for(request(), timeout=timeout)
    except asyncio.TimeoutError:
        raise Refused("provider total deadline exceeded; reservation retained") from None
    except Refused:
        raise
    except Exception:
        raise Refused("provider transport/result unavailable; reservation retained") from None


async def fetch_pricing(*, transport=None, timeout=20):
    """Public pricing has its own byte and whole-request deadline, no key."""
    async def request():
        async with httpx.AsyncClient(timeout=15, follow_redirects=False,
                                     trust_env=False, transport=transport) as client:
            async with client.stream("GET", "https://openrouter.ai/api/v1/models") as response:
                if response.status_code != 200:
                    raise Refused("public model pricing unavailable")
                body = bytearray()
                async for chunk in response.aiter_bytes(chunk_size=65536):
                    body.extend(chunk)
                    if len(body) > 8_000_000:
                        raise Refused("public model pricing size refused")
                rows = json.loads(body)["data"]
                return {item["id"]: {"context_length": item["context_length"], "pricing": item["pricing"]}
                        for item in rows if item["id"] in MODELS}
    try:
        return await asyncio.wait_for(request(), timeout=timeout)
    except Exception:
        raise Refused("bounded public pricing fetch unavailable") from None


class IsolatedGateway:
    def __init__(self, directory, key, pricing, *, budget_usd=5, max_calls=100, lifetime=1800):
        validate_bounds(budget_usd, max_calls, lifetime)
        directory = Path(directory)
        if directory.is_symlink():
            raise Refused("private state directory required")
        directory.mkdir(mode=0o700, parents=False, exist_ok=True)
        info = directory.stat()
        if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
            raise Refused("private state directory required")
        # Exclusive reservation ensures a second process cannot reset evidence.
        fd = os.open(directory / "run-created", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(fd)
        if any((directory / name).exists() for name in ("spend.json", "gateway-token", "model-traces")):
            raise Refused("existing audit state must be preserved")
        for info in pricing.values():
            if not isinstance(info.get("context_length"), int) or info["context_length"] <= 0:
                raise Refused("invalid pricing context")
            rates = [info["pricing"]] + info["pricing"].get("overrides", [])
            for rate in rates:
                for field in ("prompt", "completion"):
                    value = float(rate.get(field, info["pricing"][field]))
                    if not math.isfinite(value) or value < 0:
                        raise Refused("invalid pricing rate")
        self.directory, self.key, self.pricing = directory, key, pricing
        self.max_calls, self.deadline = max_calls, time.monotonic() + lifetime
        self.serial = threading.Lock()
        self.budget = Budget(directory / "spend.json", operating_limit=budget_usd)
        atomic_json(directory / "spend.json", {"budget_usd": budget_usd, "max_calls": max_calls,
                    "lifetime_seconds": lifetime, "calls": [], "halted": False})
        atomic_json(directory / "model-pricing.json", pricing)
        self.token = secrets.token_urlsafe(32)
        fd = os.open(directory / "gateway-token", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as out:
            out.write(self.token)
        self.traces = directory / "model-traces"
        self.traces.mkdir(mode=0o700)

    def halt(self, reason):
        with self.budget.locked() as state:
            state["halted"] = reason
            atomic_json(self.budget.path, state)

    def handle(self, payload, audit_run=None):
        try:
            data, reservation = prepare(payload, self.pricing)
            body = json.dumps(data, allow_nan=False).encode()
            if len(body) > MAX_REQUEST_BYTES:
                raise Refused("request size refused")
        except Refused:
            raise
        except Exception:
            raise Refused("invalid model request") from None
        if not self.serial.acquire(timeout=1):
            raise Refused("evaluation transport busy; calls must be serial")
        try:
            if time.monotonic() >= self.deadline:
                raise Refused("evaluation deadline reached")
            with self.budget.locked() as state:
                if len(state["calls"]) >= self.max_calls:
                    raise Refused("evaluation call limit reached")
            request_id = self.budget.reserve(reservation, data["model"], body, audit_run)
            try:
                atomic_json(self.traces / (request_id + "-request.json"), data)
                remaining = self.deadline - time.monotonic()
                if remaining <= 0:
                    raise Refused("evaluation deadline reached before dispatch")
                result = asyncio.run(post_model(self.key, data, timeout=min(90, remaining)))
                atomic_json(self.traces / (request_id + "-response.json"), result)
                self.budget.finish(request_id, result, "returned")
                cost = (result.get("usage") or {}).get("cost")
                if (isinstance(cost, bool) or not isinstance(cost, (int, float))
                        or not math.isfinite(cost) or cost < 0 or cost > reservation):
                    self.halt("missing or out-of-reservation provider cost")
                    raise Refused("provider cost could not be safely reconciled; run halted")
                return result
            except Exception as error:
                self.budget.finish(request_id, status="uncertain")
                self.halt("provider request uncertain; reservation retained")
                if isinstance(error, Refused):
                    raise
                raise Refused("provider result unavailable; reservation retained") from None
        finally:
            self.serial.release()


def serve(gateway, port):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def setup(self):
            super().setup()
            self.connection.settimeout(10)

        def answer(self, status, value):
            body = json.dumps(value).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            url = urlsplit(self.path)
            query = parse_qs(url.query, keep_blank_values=True)
            tags = query.get("audit_run", [])
            if (url.path != "/api/v1/chat/completions" or set(query) - {"audit_run"}
                    or len(tags) > 1 or (tags and (len(tags[0]) > 120 or
                    any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-/" for c in tags[0])))):
                return self.answer(400, {"error": "invalid evaluation route"})
            if not hmac.compare_digest(self.headers.get("Authorization", ""), "Bearer " + gateway.token):
                return self.answer(401, {"error": "invalid local evaluation credential"})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= MAX_REQUEST_BYTES or self.headers.get("Transfer-Encoding"):
                    raise Refused("request size or framing refused")
                raw = self.rfile.read(length)
                if len(raw) != length:
                    raise Refused("incomplete request")
                result = gateway.handle(json.loads(raw), tags[0] if tags else None)
                return self.answer(200, result)
            except Refused as error:
                return self.answer(402, {"error": str(error)})
            except Exception:
                return self.answer(502, {"error": "evaluation request unavailable"})

    with ThreadingHTTPServer(("127.0.0.1", port), Handler) as server:
        print(json.dumps({"listening": port, "budget_usd": gateway.budget.operating_limit,
                          "max_calls": gateway.max_calls, "state": str(gateway.directory)}), flush=True)
        timer = threading.Timer(max(0, gateway.deadline - time.monotonic()), server.shutdown)
        timer.daemon = True
        timer.start()
        try:
            server.serve_forever()
        finally:
            timer.cancel()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--budget-usd", type=float, required=True,
                        help="Explicit approved dollar ceiling for this fresh run, at most 5")
    parser.add_argument("--max-calls", type=int, required=True,
                        help="Explicit approved total calls, including retries, at most 100")
    parser.add_argument("--port", type=int, default=8794)
    args = parser.parse_args()
    try:
        if not 1024 <= args.port <= 65535:
            raise Refused("invalid local port")
        # Refuse an invalid grant before touching a key or the public pricing API.
        validate_bounds(args.budget_usd, args.max_calls, 1800)
        key = read_key(args.env_file)
        pricing = asyncio.run(fetch_pricing())
        if set(pricing) != MODELS:
            raise Refused("not all evaluation models were priced")
        serve(IsolatedGateway(args.state_dir, key, pricing, budget_usd=args.budget_usd,
                              max_calls=args.max_calls), args.port)
    except KeyboardInterrupt:
        pass
    except Exception:
        print("Evaluation gateway refused startup; no credential details logged", flush=True)
        raise SystemExit(2) from None


if __name__ == "__main__":
    main()
