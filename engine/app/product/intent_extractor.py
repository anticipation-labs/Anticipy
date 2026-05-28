"""V7 unified intent extractor. Canonical entry point that turns a
normalized input window into a structured Intent. Replaces the fragmented
intent paths scattered across server.py. Every input mode (laptop mic, MP3,
transcript paste, extension capture) converges here before planning, risk
scoring, or memory writes. Cheap-model cascade: deepseek-v4-flash ->
kimi-k2.6-instruct -> gemini-flash-2.5. Hard-negative filters in
is_actionable block third-party wants, hypotheticals, jokes, and
already-satisfied wants from reaching the planner.
"""

from __future__ import annotations

import concurrent.futures
import json
import os
import re
import uuid
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from typing import Any, Optional


OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
TEXT_CASCADE = [
    "deepseek/deepseek-v4-flash",
    "moonshotai/kimi-k2.6",
    "google/gemini-2.5-flash",
]
DEFAULT_TIMEOUT = 5.0

INTENT_TYPES = ("act", "ask", "remind", "research", "create",
                "modify", "delete", "answer", "ignore")
RISK_LEVELS = ("low", "medium", "high")


@dataclass
class Intent:
    """Canonical extracted intent. JSON-serialisable via to_dict()."""

    intent_id: str = ""
    summary: str = ""
    type: str = "ignore"
    target_surface: str = ""
    target_person_refs: list[str] = field(default_factory=list)
    evidence_quotes: list[str] = field(default_factory=list)
    required_slots: list[str] = field(default_factory=list)
    missing_slots: list[str] = field(default_factory=list)
    risk_level: str = "low"
    confidence: float = 0.0
    actionable_probability: float = 0.0
    is_third_party_want: bool = False
    is_hypothetical: bool = False
    model: str = ""
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


SYSTEM_PROMPT = (
    "You are Anticipy's intent extractor. The user is being ambiently "
    "listened to. From the transcript plus surface and memory context, "
    "extract ONE structured intent for what (if anything) the user wants "
    "Anticipy to do.\n\n"
    "Output ONLY a JSON object. No prose, no code fences. Required keys:\n"
    "  summary: one short sentence.\n"
    "  type: act|ask|remind|research|create|modify|delete|answer|ignore. "
    "Use 'act' for any direct draft/send/email/schedule/book request. "
    "Use 'create' only for brand-new standalone artifacts (a new doc/note). "
    "Use 'remind' for reminders/alerts.\n"
    "  target_surface: gmail|google_calendar|notion|native_calendar|"
    "reminders|opentable|google_search|chrome|none.\n"
    "  target_person_refs: array of person names mentioned as "
    "recipient/subject. Empty if none.\n"
    "  evidence_quotes: 1-3 exact transcript substrings showing the intent.\n"
    "  required_slots: array of needed slot names "
    "(recipient_email, send_time, event_title, location, ...).\n"
    "  missing_slots: subset of required_slots not yet resolved.\n"
    "  risk_level: low (read-only/draft)|medium (visible change)|high "
    "(irreversible, external recipient, money).\n"
    "  confidence: 0..1, how sure the intent is real.\n"
    "  actionable_probability: 0..1. 0 for chatter, lyrics, jokes, "
    "third-party wants, or already-done.\n"
    "  is_third_party_want: true if the want belongs to someone other than "
    'the speaker (e.g. "Maya was asking if Marcus could send X").\n'
    "  is_hypothetical: true for jokes, speculation, quoted speech, media "
    'references, or "wouldn\'t it be funny if".\n\n'
    "Hard rules: if the user is not asking for anything to be done, "
    "type=ignore + actionable_probability=0. Quoted speech, song lyrics, "
    "movies, rhetorical questions => is_hypothetical=true. A request "
    "someone else made through the user => is_third_party_want=true. "
    "Never invent fields. Never include prose."
)


def _strip_fences(text: str) -> str:
    cleaned = (text or "").strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned,
                         flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


def _coerce_str_list(value: Any, limit: int = 8) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        items: list = [value]
    elif isinstance(value, (list, tuple)):
        items = [str(v) for v in value if v]
    else:
        return []
    return [s.strip() for s in items if s and str(s).strip()][:limit]


def _coerce_float(value: Any, default: float = 0.0) -> float:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(1.0, f))


def _parse_intent(text: str, *, model: str,
                  fallback_quote: str) -> Optional[Intent]:
    cleaned = _strip_fences(text)
    if not cleaned:
        return None
    try:
        obj = json.loads(cleaned)
    except Exception:
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not match:
            return None
        try:
            obj = json.loads(match.group(0))
        except Exception:
            return None
    if not isinstance(obj, dict):
        return None
    raw_type = str(obj.get("type") or "ignore").strip().lower()
    if raw_type not in INTENT_TYPES:
        raw_type = "ignore"
    raw_risk = str(obj.get("risk_level") or "low").strip().lower()
    if raw_risk not in RISK_LEVELS:
        raw_risk = "low"
    evidence = _coerce_str_list(obj.get("evidence_quotes"), limit=4)
    if not evidence and fallback_quote:
        evidence = [fallback_quote[:280]]
    return Intent(
        intent_id=str(uuid.uuid4()),
        summary=str(obj.get("summary") or "")[:240].strip(),
        type=raw_type,
        target_surface=str(obj.get("target_surface") or "").strip().lower(),
        target_person_refs=_coerce_str_list(obj.get("target_person_refs"), 8),
        evidence_quotes=evidence,
        required_slots=_coerce_str_list(obj.get("required_slots"), 12),
        missing_slots=_coerce_str_list(obj.get("missing_slots"), 12),
        risk_level=raw_risk,
        confidence=_coerce_float(obj.get("confidence")),
        actionable_probability=_coerce_float(obj.get("actionable_probability")),
        is_third_party_want=bool(obj.get("is_third_party_want")),
        is_hypothetical=bool(obj.get("is_hypothetical")),
        model=model,
    )


def _transcript_from_normalized(normalized_input: dict) -> str:
    if not isinstance(normalized_input, dict):
        return ""
    window = normalized_input.get("window") or {}
    turns = window.get("turns") if isinstance(window, dict) else None
    if isinstance(turns, list) and turns:
        joined = "\n".join(
            f"{t.get('speaker', 'user')}: {t.get('text', '')}"
            for t in turns if isinstance(t, dict) and t.get("text")
        )
        if joined.strip():
            return joined
    # FIX (W2O): the previous form `capture = ... or {}` made the bare-text
    # fallback unreachable because `{}` is still a dict. Now we only return
    # from the capture branch when it actually has content, so a text-only
    # caller (no `capture` payload, just `{"text": "..."}`) still gets its
    # transcript through.
    capture = normalized_input.get("capture")
    if isinstance(capture, dict) and capture:
        captured = str(capture.get("asr_normalized")
                       or capture.get("raw_asr_transcript") or "")
        if captured.strip():
            return captured
    return str(normalized_input.get("text") or "")


def _build_messages(transcript: str, surface_context: dict,
                    memory_context: str) -> list[dict[str, Any]]:
    surface_text = ""
    if isinstance(surface_context, dict) and surface_context:
        parts = []
        for k in ("url", "active_url", "title", "active_title",
                  "app", "surface", "mode", "input_mode"):
            v = surface_context.get(k)
            if v:
                parts.append(f"{k}={v}")
        surface_text = "; ".join(parts) or json.dumps(
            surface_context, default=str)[:400]
    mem_text = (memory_context or "").strip()[:1200]
    user = (
        f"TRANSCRIPT WINDOW:\n{transcript[:4000]}\n\n"
        f"SURFACE CONTEXT: {surface_text or '(none)'}\n\n"
        f"MEMORY CONTEXT: {mem_text or '(none)'}\n\n"
        "Return JSON only."
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


def _do_request(model: str, messages: list[dict[str, Any]],
                api_key: str, timeout: float) -> tuple[str, str]:
    body = json.dumps({
        "model": model,
        "messages": messages,
        "temperature": 0.0,
        "max_tokens": 250,
        "response_format": {"type": "json_object"},
    }).encode("utf-8")
    req = urllib.request.Request(
        OPENROUTER_URL, data=body, method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Connection": "close",
            "HTTP-Referer": "https://anticipy.ai",
            "X-Title": "Anticipy Intent Extractor",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
        data = json.loads(raw)
        text = (data.get("choices") or [{}])[0].get(
            "message", {}).get("content", "")
        if not text:
            return "", f"empty content from {model}"
        return text, ""
    except urllib.error.HTTPError as exc:
        try:
            msg = exc.read().decode("utf-8", "replace")[:200]
        except Exception:
            msg = ""
        return "", f"http {exc.code} {model}: {msg}"
    except Exception as exc:
        return "", f"{type(exc).__name__}: {exc}"


# Shared executor: a fresh ThreadPoolExecutor per call blocks on .__exit__
# until pending threads die, which defeats the wall-clock budget. A small
# reusable pool lets a stuck request stay parked while we fall through.
_POOL = concurrent.futures.ThreadPoolExecutor(
    max_workers=8, thread_name_prefix="intent-extractor")


def _empty_intent(transcript: str, reason: str) -> Intent:
    return Intent(
        intent_id=str(uuid.uuid4()),
        summary="",
        type="ignore",
        evidence_quotes=[transcript[:280]] if transcript else [],
        confidence=0.0,
        actionable_probability=0.0,
        model="cascade-failed",
        error=reason[:240],
    )


def extract(normalized_input: dict,
            surface_context: Optional[dict] = None,
            memory_context: str = "",
            *,
            api_key: Optional[str] = None,
            timeout: float = DEFAULT_TIMEOUT,
            cascade: Optional[list[str]] = None) -> Intent:
    """Single canonical intent extraction entrypoint.

    `timeout` is the TOTAL wall-clock budget. We fire the cascade models
    in parallel and return the first parseable response, preferring the
    earlier-in-cascade model when more than one returns simultaneously.
    This bounds tail latency to the FASTEST model's response time, not
    the sum of all cold-starts. Returns an empty ignore Intent with
    `error` populated if no model produces parseable output in time.
    """
    import time as _time
    transcript = _transcript_from_normalized(normalized_input)
    if not transcript.strip():
        return _empty_intent("", "empty_transcript")
    messages = _build_messages(
        transcript, surface_context or {}, memory_context or "")
    key = api_key or os.environ.get("OPENROUTER_API_KEY", "")
    models = list(cascade or TEXT_CASCADE)
    deadline = _time.monotonic() + float(timeout)
    futures: dict[concurrent.futures.Future, tuple[int, str]] = {}
    for idx, model in enumerate(models):
        f = _POOL.submit(_do_request, model, messages, key, float(timeout))
        futures[f] = (idx, model)
    results: dict[int, Intent] = {}
    last_err = ""
    while futures:
        remaining = deadline - _time.monotonic()
        if remaining <= 0.05:
            break
        try:
            done, _pending = concurrent.futures.wait(
                list(futures.keys()),
                timeout=max(0.05, remaining),
                return_when=concurrent.futures.FIRST_COMPLETED,
            )
        except Exception as exc:
            last_err = f"{type(exc).__name__}: {exc}"
            break
        if not done:
            break
        for f in done:
            idx, model = futures.pop(f)
            try:
                text, err = f.result()
            except Exception as exc:
                last_err = f"{type(exc).__name__}: {exc}"
                continue
            if err:
                last_err = err
                continue
            intent = _parse_intent(
                text, model=model, fallback_quote=transcript.strip())
            if intent is not None:
                results[idx] = intent
            else:
                last_err = f"unparseable response from {model}: {text[:160]}"
        if results:
            break
    if results:
        return results[min(results.keys())]
    return _empty_intent(transcript, last_err or "no_models_available")


def extract_batch(inputs: list[dict],
                  surface_context: Optional[dict] = None,
                  memory_context: str = "",
                  *,
                  api_key: Optional[str] = None,
                  timeout: float = DEFAULT_TIMEOUT,
                  cascade: Optional[list[str]] = None) -> list[Intent]:
    """Batch path. Sequential calls today (the cheap models do not have a
    batched endpoint over urllib). The function exists so callers stabilise
    against a single entrypoint and we can swap in concurrency later without
    touching them.
    """
    if not isinstance(inputs, list):
        return []
    out: list[Intent] = []
    for item in inputs:
        if not isinstance(item, dict):
            out.append(_empty_intent("", "invalid_input"))
            continue
        out.append(extract(
            item, surface_context, memory_context,
            api_key=api_key, timeout=timeout, cascade=cascade,
        ))
    return out


def is_actionable(intent: Intent) -> bool:
    """Hard-negative filter. Block third-party wants, hypotheticals, jokes,
    quoted speech, and already-satisfied wants from reaching the planner.

    Returns True only when the intent is a real, first-person, present-or-
    future thing the user wants Anticipy to do.
    """
    if not isinstance(intent, Intent):
        return False
    if intent.type == "ignore":
        return False
    if intent.is_third_party_want:
        return False
    if intent.is_hypothetical:
        return False
    if intent.actionable_probability < 0.4:
        return False
    if intent.confidence < 0.3:
        return False
    # Already-satisfied is encoded by the model as low actionable_probability
    # plus type=ignore. We also drop empty summaries which cannot be planned.
    if not intent.summary.strip():
        return False
    return True


__all__ = [
    "Intent",
    "INTENT_TYPES",
    "RISK_LEVELS",
    "TEXT_CASCADE",
    "extract",
    "extract_batch",
    "is_actionable",
]
