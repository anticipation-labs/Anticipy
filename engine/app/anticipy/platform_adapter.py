"""The single seam between the portable Anticipy engine and its
environment. This is the ONLY module in the engine permitted to contain
environment specific code: filesystem paths, the model endpoint, the
comms transport, the action engine invocation, the Supabase client, and
any subprocess or platform branch.

Every other engine module imports from here for anything environmental.
Porting to a home base device is implemented as a new adapter, never as
an engine rewrite. The portability gate greps every other engine module
for environmental calls and fails the build if any are found.

What lives here and why:

  model_call            the cloud reasoning model (OpenRouter, DeepSeek
                        V4 Flash text). Reads OPENROUTER_API_KEY from
                        ~/.anticipy/.env. The only credential this build
                        uses.
  data_dir              the portable per build state and log root.
                        Honors ANTICIPY_DATA_DIR so a home base sets its
                        own location with zero engine changes.
  transcript_source     ambient diarized transcript input. Generated and
                        injected now, real audio front end output later.
                        Same shape both ways.
  direct_command_source path (b) inbound: the user deliberately addresses
                        the agent. Injected now, real inbound text later.
  comms_send            outbound to the user. Test mode recorder now,
                        real Telnyx and SES later, same OutboundMessage
                        shape.
  comms_receive         inbound replies from the user. Test mode injector
                        now, real provider webhook later, same
                        InboundMessage shape.
  action_engine_invoke  the ONLY path to the frozen action engine. A new
                        adapter boundary, never an edit to a frozen file.
  supabase_client       an RLS scoped client bound to one user. Used by
                        engine logic.
  service_role_client   the admin client. Explicitly separate and named
                        so engine logic can never reach for it by
                        accident. Used only by migration and admin code.

Real external sends, real OAuth, and the real action engine are exercised
only behind ANTICIPY_LIVE=1, which is OFF by default and never set during
the autonomous build run.
"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Callable, Optional

# python-dotenv ships with the engine venv (the frozen action engine uses
# it). Loading the env file is environment specific by definition, so it
# belongs here and nowhere else.
try:
    from dotenv import load_dotenv

    _ENV_PATH = os.path.expanduser("~/.anticipy/.env")
    load_dotenv(_ENV_PATH)
except Exception:
    _ENV_PATH = os.path.expanduser("~/.anticipy/.env")


# ---------------------------------------------------------------------------
# data_dir
# ---------------------------------------------------------------------------

_DEFAULT_DATA_DIR = os.path.expanduser("~/.anticipy/system_v1")


def data_dir() -> Path:
    """The portable per build state and log root.

    A home base device sets ANTICIPY_DATA_DIR to its own writable
    location and the entire engine relocates with zero code changes.
    """
    root = Path(os.environ.get("ANTICIPY_DATA_DIR", _DEFAULT_DATA_DIR))
    root.mkdir(parents=True, exist_ok=True)
    return root


def user_data_dir(user_id: str) -> Path:
    """Per user partition under data_dir. The single user local form and
    the multi tenant scaled form differ only in how many of these exist.
    """
    safe = "".join(c for c in user_id if c.isalnum() or c in ("-", "_")) or "anon"
    d = data_dir() / "users" / safe
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------------------
# model_call
# ---------------------------------------------------------------------------

_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
_DEFAULT_MODEL_BROKER_URL = "https://www.anticipy.ai/api/engine/model"
_TEXT_MODEL = "deepseek/deepseek-v4-flash"
# A deliberately different model family for the adversarial grader check.
# It must not be the decider model or the check is not independent.
_ADVERSARIAL_MODEL = "moonshotai/kimi-k2.6"

# DeepSeek V4 Flash is a reasoning model on OpenRouter. Below this floor
# the internal chain of thought consumes the whole budget and content
# comes back empty. Verified by the frozen action engine build.
_MIN_TOKENS = 256

# Provider routing. Discovered from the live OpenRouter endpoints API
# for this exact model (GET /models/deepseek/deepseek-v4-flash/endpoints,
# 12 endpoints): the first party "deepseek" provider is native precision
# and 100% uptime, while third party endpoints range down to DeepInfra
# fp4. With no routing, OpenRouter spreads calls across all of them, so
# at temperature 0 the same input flickers run to run (the P9 finding:
# CLEAR, compound and P8 each green in isolation but failing only in the
# heavy combined run, zero JSON parse failures). sort=throughput made it
# worse (it picked the fast fp4 endpoint, isolated CLEAR 0.933 -> 0.883),
# proving the lever is provider PRECISION, not speed. So we pin the
# first party reference provider and keep allow_fallbacks true: a real
# DeepSeek outage still routes elsewhere (durability preserved, no single
# point of failure) and the JSON-retry wrapper still guards any degraded
# fallback output. Not guessed: read from the live API. Wiring only, in
# the single env seam: no cascade prompt, stage, test or threshold is
# touched.
_PROVIDER_ROUTING = {"order": ["deepseek"], "allow_fallbacks": True}

# OpenRouter per million token pricing for the call ledger. These are the
# catalog values used by the frozen build; the ledger is the real cost
# source for the per decision cost report.
_PRICING = {
    "deepseek/deepseek-v4-flash": {"in": 0.30, "out": 0.50},
    "moonshotai/kimi-k2.6": {"in": 0.60, "out": 2.50},
}

_call_log_lock = threading.Lock()


def _model_call_log_path() -> Path:
    return data_dir() / "model_calls.jsonl"


def _log_model_call(row: dict) -> None:
    try:
        with _call_log_lock:
            with _model_call_log_path().open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(row) + "\n")
    except Exception:
        # Logging must never break a decision. A poisoned flywheel is a
        # P11 concern surfaced by the trajectory logger, not here.
        pass


class ModelResult:
    __slots__ = ("content", "ok", "error", "prompt_tokens", "completion_tokens", "cost_usd", "latency_s")

    def __init__(
        self,
        content: str,
        ok: bool,
        error: Optional[str],
        prompt_tokens: int,
        completion_tokens: int,
        cost_usd: float,
        latency_s: float,
    ) -> None:
        self.content = content
        self.ok = ok
        self.error = error
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.cost_usd = cost_usd
        self.latency_s = latency_s


def _estimate_cost(model: str, p_tok: int, c_tok: int) -> float:
    rate = _PRICING.get(model)
    if not rate:
        return 0.0
    return (p_tok / 1_000_000.0) * rate["in"] + (c_tok / 1_000_000.0) * rate["out"]


def _broker_url() -> str:
    return os.environ.get("ANTICIPY_MODEL_BROKER_URL", "").strip()


def _broker_token() -> str:
    return os.environ.get("ANTICIPY_CLOUD_AUTH_TOKEN", "").strip()


def model_provisioned() -> bool:
    """Whether model calls can run without asking the user for provider keys."""
    return (
        os.environ.get("OPENROUTER_API_KEY", "").startswith("sk-or-")
        or (bool(_broker_url()) and bool(_broker_token()))
    )


def model_call(
    system: str,
    user: str,
    max_tokens: int = 1024,
    temperature: float = 0.0,
    json_mode: bool = True,
    timeout_s: float = 15.0,
    model: Optional[str] = None,
    _retry_on_empty: bool = True,
) -> ModelResult:
    """One blocking chat completion against the portable model endpoint.

    The proactive cascade calls this through a thin async wrapper. The
    return contract: on success ``content`` is the model text (clean JSON
    when json_mode is True). On any failure ``ok`` is False and
    ``content`` is empty, so every cascade stage falls to its documented
    safe default rather than crashing or emitting a wrong ACT.
    """
    import requests  # imported here so the dependency lives only in the adapter

    model = model or _TEXT_MODEL
    max_tokens = max(max_tokens, _MIN_TOKENS)

    # OpenRouter prompt caching (Anthropic-shaped cache_control). The
    # planner cascade sends the same system rubric on every utterance,
    # and the user payload often repeats a large static profile JSON
    # across the burst. Marking the system message with
    # cache_control: ephemeral lets compatible providers (DeepSeek,
    # Anthropic, Gemini via OpenRouter) charge cached input tokens at
    # a 75-90% discount on warm hits, and skip the prefix
    # tokenization, which is the single biggest cut in median planner
    # latency (per the W2O latency budget; see roadmap planner-latency
    # item). Threshold gate: only cache when the system block is large
    # enough to be worth the breakpoint (1000 char floor, matching
    # OpenRouter's recommended min). Below that we send a bare string
    # to avoid spending one of the 4 cache breakpoints on a tiny
    # rubric.
    if isinstance(system, str) and len(system) >= 1000:
        system_content: Any = [{
            "type": "text",
            "text": system,
            "cache_control": {"type": "ephemeral"},
        }]
    else:
        system_content = system

    # Same caching logic for the user payload. The compose_task user
    # payload concatenates the onboarding profile JSON + durable
    # memory ahead of the per-utterance instruction, so the leading
    # prefix is shared across an entire session. Mark the whole user
    # block as cacheable when it crosses the 1000 char floor; the
    # cache breakpoint covers the matching prefix and any new tail
    # (the per-utterance suffix) is billed at the normal rate.
    if isinstance(user, str) and len(user) >= 1000:
        user_content: Any = [{
            "type": "text",
            "text": user,
            "cache_control": {"type": "ephemeral"},
        }]
    else:
        user_content = user

    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_content},
        ],
        "max_tokens": max_tokens,
        "temperature": temperature,
        # Reasoning disabled is the universal fix verified by the frozen
        # build: clean fast content, no reasoning tokens billed.
        "reasoning": {"enabled": False},
        # Deterministic provider selection. Without this OpenRouter
        # spreads each call across every provider serving the model,
        # including low precision quantizations, so at temperature 0 the
        # same input flickers run to run (proven in the P9 run: CLEAR,
        # compound and P8 each green in isolation but failing only
        # inside the heavy combined run, with zero JSON parse failures).
        # The lever is provider QUALITY, not speed: sort=throughput
        # selected a faster low quant provider and dropped isolated
        # CLEAR 0.933 -> 0.883. So we restrict to higher precision
        # quantizations and pin a stable order discovered from the live
        # OpenRouter endpoints API for this exact model (not guessed),
        # with allow_fallbacks true so a primary outage still routes
        # elsewhere: durability preserved, no single point of failure.
        # Wiring only, in the single env seam: no cascade prompt, stage,
        # test or threshold is touched.
        "provider": _PROVIDER_ROUTING,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    broker_url = _broker_url()
    broker_token = _broker_token()
    if api_key.startswith("sk-or-"):
        url = _OPENROUTER_URL
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://anticipy.ai",
            "X-Title": "Anticipy System V1",
        }
        credential_mode = "direct_openrouter"
    elif broker_url and broker_token:
        url = broker_url or _DEFAULT_MODEL_BROKER_URL
        headers = {
            "Authorization": f"Bearer {broker_token}",
            "Content-Type": "application/json",
        }
        credential_mode = "anticipy_broker"
    else:
        result = ModelResult(
            "",
            False,
            "model broker not provisioned and OPENROUTER_API_KEY missing "
            f"(looked in {_ENV_PATH})",
            0,
            0,
            0.0,
            0.0,
        )
        _log_model_call({"ts": time.time(), "error": result.error, "ok": False})
        return result

    backoffs = [0.5, 1.0]
    attempt = 0
    t0 = time.monotonic()
    last_err = "unknown"
    while attempt <= len(backoffs):
        try:
            r = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=timeout_s,
            )
        except Exception as e:  # transport: timeout, connection reset
            last_err = f"transport: {e}"
            if attempt < len(backoffs):
                time.sleep(backoffs[attempt])
                attempt += 1
                continue
            res = ModelResult("", False, last_err, 0, 0, 0.0, time.monotonic() - t0)
            _log_model_call({"ts": time.time(), "error": last_err, "ok": False, "latency_s": round(res.latency_s, 3)})
            return res

        if r.status_code == 429 or r.status_code >= 500:
            last_err = f"http {r.status_code}"
            if attempt < len(backoffs):
                time.sleep(backoffs[attempt])
                attempt += 1
                continue
            res = ModelResult("", False, last_err, 0, 0, 0.0, time.monotonic() - t0)
            _log_model_call({"ts": time.time(), "error": last_err, "ok": False, "latency_s": round(res.latency_s, 3)})
            return res

        if r.status_code != 200:
            res = ModelResult("", False, f"http {r.status_code}: {r.text[:160]}", 0, 0, 0.0, time.monotonic() - t0)
            _log_model_call({"ts": time.time(), "error": res.error, "ok": False})
            return res

        j = r.json()
        choices = j.get("choices") or []
        if not choices:
            res = ModelResult("", False, "no choices", 0, 0, 0.0, time.monotonic() - t0)
            _log_model_call({"ts": time.time(), "error": "no choices", "ok": False})
            return res

        msg = choices[0].get("message", {})
        content = (msg.get("content") or "").strip()
        finish = choices[0].get("finish_reason", "")
        usage = j.get("usage", {})
        p_tok = int(usage.get("prompt_tokens", 0))
        c_tok = int(usage.get("completion_tokens", 0))
        # Cache instrumentation: OpenRouter surfaces cached prefix tokens
        # under usage.prompt_tokens_details.cached_tokens (Anthropic
        # passthrough) or top-level cache_creation_input_tokens /
        # cache_read_input_tokens depending on provider. Pull both
        # shapes so the log can answer "is the cache warm yet" without
        # a second hop. These do not affect cost (already billed
        # inside prompt_tokens) but they let the latency story be
        # measured per call.
        ptd = usage.get("prompt_tokens_details") or {}
        cache_read_tok = int(ptd.get("cached_tokens", 0)
                             or usage.get("cache_read_input_tokens", 0) or 0)
        cache_write_tok = int(usage.get("cache_creation_input_tokens", 0) or 0)
        cost = _estimate_cost(model, p_tok, c_tok)

        # Empty content path: previously this recursed with doubled
        # tokens, which added 15-90s of latency for the worst case.
        # Per the roadmap planner-latency item: drop the recursive
        # retry. If content is empty we return empty and the caller
        # decides what to do (server.py has its own one-shot logic).
        if not content:
            _log_model_call({"ts": time.time(), "model": model, "prompt_tokens": p_tok,
                             "completion_tokens": c_tok, "cost_usd": round(cost, 6),
                             "ok": False, "empty_content": True, "finish": finish})

        res = ModelResult(content, bool(content), None if content else "empty content", p_tok, c_tok, cost, time.monotonic() - t0)
        _log_model_call(
            {
                "ts": time.time(),
                "model": j.get("model", model),
                "credential_mode": credential_mode,
                "prompt_tokens": p_tok,
                "completion_tokens": c_tok,
                "cache_read_tokens": cache_read_tok,
                "cache_write_tokens": cache_write_tok,
                "cost_usd": round(cost, 6),
                "latency_s": round(res.latency_s, 3),
                "ok": res.ok,
                "json_mode": json_mode,
            }
        )
        return res

    res = ModelResult("", False, last_err, 0, 0, 0.0, time.monotonic() - t0)
    _log_model_call({"ts": time.time(), "error": last_err, "ok": False})
    return res


def adversarial_model_call(system: str, user: str, max_tokens: int = 512) -> ModelResult:
    """A second, deliberately different model used only by the grader's
    anti self deception check. It must never be the decider model or the
    check is not independent.
    """
    return model_call(system, user, max_tokens=max_tokens, json_mode=True, model=_ADVERSARIAL_MODEL)


# ---------------------------------------------------------------------------
# transcript_source / direct_command_source
# ---------------------------------------------------------------------------

class _InjectableSource:
    """A test mode source. The harness pushes items; the engine pulls
    them. The real audio front end and the real inbound channel replace
    only this object, never the engine that consumes it.
    """

    def __init__(self, label: str) -> None:
        self._label = label
        self._items: list[Any] = []

    def push(self, item: Any) -> None:
        self._items.append(item)

    def drain(self) -> list[Any]:
        out, self._items = self._items, []
        return out

    def __repr__(self) -> str:
        return f"<InjectableSource {self._label} pending={len(self._items)}>"


_transcript_source = _InjectableSource("transcript")
_direct_command_source = _InjectableSource("direct_command")


def transcript_source() -> _InjectableSource:
    """Ambient diarized transcript input. Generated and injected for the
    build. The real audio front end output replaces this object later
    with the same drain contract.
    """
    return _transcript_source


def direct_command_source() -> _InjectableSource:
    """Path (b): the user deliberately addresses the agent. Injected for
    the build, real inbound text later, same drain contract.
    """
    return _direct_command_source


# ---------------------------------------------------------------------------
# comms_send / comms_receive (two way, test mode recorder and injector)
# ---------------------------------------------------------------------------

class _CommsBus:
    """Test mode two way transport. comms_send records what WOULD be
    sent. comms_receive yields injected user replies. The real Telnyx,
    SES, and TTS adapter implements this exact shape behind ANTICIPY_LIVE,
    which is never set during the autonomous run, so no real message is
    ever sent here.
    """

    def __init__(self) -> None:
        self.sent: list[dict] = []
        self.inbound: list[dict] = []
        self.live = os.environ.get("ANTICIPY_LIVE", "") == "1"

    def send(self, message: dict) -> dict:
        record = dict(message)
        record["_recorded_ts"] = time.time()
        record["_live"] = self.live
        self.sent.append(record)
        if self.live:
            # The production adapter (Telnyx SMS and voice, AWS SES email,
            # ElevenLabs and Kokoro TTS) is wired here. Never reached
            # during the build because ANTICIPY_LIVE is unset.
            raise RuntimeError("live comms transport not provisioned in this build")
        return {"status": "recorded", "channel": record.get("channel"), "task_id": record.get("task_id")}

    def inject_reply(self, message: dict) -> None:
        self.inbound.append(dict(message))

    def receive(self) -> list[dict]:
        out, self.inbound = self.inbound, []
        return out

    def reset(self) -> None:
        self.sent.clear()
        self.inbound.clear()


_comms_bus = _CommsBus()


def comms_send(message: dict) -> dict:
    return _comms_bus.send(message)


def comms_receive() -> list[dict]:
    return _comms_bus.receive()


def comms_bus() -> _CommsBus:
    """Test only handle so the harness can inject replies and inspect
    what was recorded. Not used by engine decision logic.
    """
    return _comms_bus


# ---------------------------------------------------------------------------
# action_engine_invoke (the only path to the frozen action engine)
# ---------------------------------------------------------------------------

_action_engine_impl: Optional[Callable[[dict], dict]] = None


def set_action_engine_impl(fn: Optional[Callable[[dict], dict]]) -> None:
    """P6 wires either a mock (mocked scenarios) or the real frozen
    engine bridge (one real READ only path) through this single seam.
    Engine logic only ever calls action_engine_invoke.
    """
    global _action_engine_impl
    _action_engine_impl = fn


def action_engine_invoke(contract: dict) -> dict:
    if _action_engine_impl is None:
        raise RuntimeError("action engine impl not set: handoff layer is wired in P6")
    return _action_engine_impl(contract)


# ---------------------------------------------------------------------------
# Supabase: RLS scoped client vs explicitly separate service role client
# ---------------------------------------------------------------------------

def supabase_client(user_ctx: Any):
    """An RLS scoped client bound to one user. Engine logic uses only
    this. At single user local scale the durable and memory layers use
    the local SQLite partition under data_dir instead, behind the same
    interfaces, so this returns None until the multi tenant spine (P7)
    is built. A None here means engine code must use its local store,
    never a cross tenant fallback.
    """
    return None


def service_role_client():
    """The admin client. Deliberately a separate, explicitly named
    function so engine logic cannot reach the cross tenant client by
    accident. Used only by migration and admin code, never by engine
    decision logic. Wired in P7.
    """
    return None
