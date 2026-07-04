"""S6 — the captcha SOLVER (auto-solve, not just handoff).

Design-of-record: ``final/browser/PLAN.md`` §4.4 (row 5) as amended by the approved
build plan ``.claude/plans/cozy-chasing-comet.md`` **directive-delta #3**: *"Captcha
SOLVING, not just handoff. Build a real solver (CapSolver createTask/getTaskResult +
2Captcha fallback) using the keys already in .env.local. Auto-solve first; handoff only
if solve fails."* This reverses the base-PLAN default (pause→text) for the captcha class
specifically, and is wired into the S5 recovery ladder as the L0 ``solve_captcha`` remedy
(``agent/guarded_step.py``): captcha → auto-solve → verify cleared → continue; handoff
only on solve-fail.

Three pieces, all deterministic and side-effect-free at import time:
  * :func:`detect_captcha` — classify the challenge (reCAPTCHA v2/v3, hCaptcha, Turnstile,
    image) from a page snapshot and extract the sitekey / image payload. Pure, testable.
  * :class:`CaptchaSolver` — a CapSolver client (``createTask`` / ``getTaskResult``) with a
    2Captcha fallback. The HTTP layer is injected (default: ``requests``, imported lazily)
    so the whole client is unit-testable offline with a fake and the *only* live network it
    ever needs for a smoke test is a tiny ``getBalance`` (no full solve).
  * :func:`resolve_captcha` — the bridge the recovery ladder calls: detect → solve → return
    the token + the JS the extension injects to place it where the site's verify reads it.

Nothing here drives a browser or types anything: the solver returns a token; injecting it
and re-verifying the challenge cleared is the extension/loop's job (S9 wire). The module is
key-agnostic and site-agnostic — **zero hardcoded selectors**, only the provider-standard
sitekey/response-field conventions.
"""
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, replace
from typing import Any, Callable, Optional

from ..core.env import load_local_env

__all__ = [
    "CAPTCHA_RECAPTCHA_V2",
    "CAPTCHA_RECAPTCHA_V3",
    "CAPTCHA_HCAPTCHA",
    "CAPTCHA_TURNSTILE",
    "CAPTCHA_IMAGE",
    "CaptchaChallenge",
    "SolveResult",
    "CaptchaOutcome",
    "CaptchaError",
    "CaptchaSolver",
    "detect_captcha",
    "injection_script",
    "resolve_captcha",
    "from_env",
]


# ── challenge taxonomy ────────────────────────────────────────────────────────
CAPTCHA_RECAPTCHA_V2 = "recaptcha_v2"
CAPTCHA_RECAPTCHA_V3 = "recaptcha_v3"
CAPTCHA_HCAPTCHA = "hcaptcha"
CAPTCHA_TURNSTILE = "turnstile"
CAPTCHA_IMAGE = "image"


class CaptchaError(RuntimeError):
    """A solver-level failure (bad key, provider error, malformed response)."""


@dataclass(frozen=True)
class CaptchaChallenge:
    """A detected challenge: the type + the parameters a solver needs."""

    kind: str
    website_url: str = ""
    sitekey: str = ""
    page_action: str = ""   # reCAPTCHA v3 action token
    image_b64: str = ""     # image-captcha payload (base64, no data: prefix)
    detail: str = ""


@dataclass(frozen=True)
class SolveResult:
    """Outcome of a solve attempt. ``ok`` is a real token, never a self-claim."""

    ok: bool
    token: str = ""
    provider: str = ""      # "capsolver" | "twocaptcha"
    kind: str = ""
    error: str = ""
    cost_calls: int = 0     # provider API round-trips spent (cost/telemetry)


@dataclass(frozen=True)
class CaptchaOutcome:
    """What the recovery ladder gets back: solved + token + the injection script,
    or not-solved with a reason (→ ladder falls through to L4 handoff)."""

    solved: bool
    challenge: Optional[CaptchaChallenge] = None
    token: str = ""
    provider: str = ""
    injection: str = ""     # JS the extension runs to place the token
    error: str = ""


# ── detection (pure, deterministic) ───────────────────────────────────────────
_DATA_SITEKEY = re.compile(r'data-sitekey=["\']([^"\']+)["\']', re.I)
_RECAPTCHA_RENDER = re.compile(
    r'recaptcha/api\.js\?[^"\'<>\s]*\brender=([^"\'&<>\s]+)', re.I)
_RECAPTCHA_KPARAM = re.compile(
    r'recaptcha/api2/(?:anchor|bframe)\?[^"\'<>\s]*\bk=([^"\'&<>\s]+)', re.I)
_HCAPTCHA_SITEKEY = re.compile(
    r'hcaptcha\.com/[^"\'<>\s]*\bsitekey=([^"\'&<>\s]+)', re.I)
_DATA_ACTION = re.compile(r'data-action=["\']([^"\']+)["\']', re.I)
_DATA_URI_IMG = re.compile(r'data:image/[a-z]+;base64,([A-Za-z0-9+/=]{16,})', re.I)


def _page_parts(page: Any) -> tuple[str, str, str, str]:
    """Normalize a page snapshot to (html, text, url, frame-srcs) as one big haystack.

    Accepts a dict ({"html","text","url","frames"/"iframes","elements"}) or a raw string.
    """
    if isinstance(page, str):
        return page, page, "", ""
    if not isinstance(page, dict):
        return "", "", "", ""
    html = str(page.get("html") or page.get("dom") or "")
    text = str(page.get("text") or "")
    url = str(page.get("url") or "")
    frames = page.get("frames") or page.get("iframes") or []
    if isinstance(frames, (list, tuple)):
        frame_src = " ".join(str(f) for f in frames)
    else:
        frame_src = str(frames)
    # element attributes can carry data-sitekey even when raw html isn't captured
    els = page.get("elements") or []
    el_blob = ""
    if isinstance(els, (list, tuple)):
        el_blob = " ".join(json.dumps(e) if isinstance(e, dict) else str(e) for e in els)
    return html + " " + el_blob, text, url, frame_src


def _first(rx: re.Pattern, hay: str) -> str:
    m = rx.search(hay)
    return m.group(1).strip() if m else ""


def _sitekey_prefer(hay: str, prefix: str = "") -> str:
    """All data-sitekey values; prefer one starting with ``prefix`` (e.g. Turnstile "0x")."""
    keys = [m.group(1).strip() for m in _DATA_SITEKEY.finditer(hay)]
    if prefix:
        for k in keys:
            if k.lower().startswith(prefix.lower()):
                return k
    return keys[0] if keys else ""


def detect_captcha(page: Any) -> Optional[CaptchaChallenge]:
    """Classify the challenge on a page snapshot and extract its solve parameters.

    Priority: Turnstile → hCaptcha → reCAPTCHA (v3 render vs v2) → image. Returns
    ``None`` when no captcha is present. Deterministic; reads only the page's own
    markup/attributes, never the acting model.
    """
    html, _text, url, frames = _page_parts(page)
    hay = html + " " + frames
    low = hay.lower()

    # Cloudflare Turnstile.
    if "challenges.cloudflare.com/turnstile" in low or "cf-turnstile" in low:
        sk = _sitekey_prefer(hay, prefix="0x")
        return CaptchaChallenge(CAPTCHA_TURNSTILE, url, sk, detail="cloudflare turnstile")

    # hCaptcha.
    if "hcaptcha.com" in low or "h-captcha" in low:
        sk = _first(_HCAPTCHA_SITEKEY, hay) or _sitekey_prefer(hay)
        return CaptchaChallenge(CAPTCHA_HCAPTCHA, url, sk, detail="hcaptcha")

    # Google reCAPTCHA — v3 (score, invisible) advertises ?render=<sitekey>; else v2.
    if "recaptcha" in low or "g-recaptcha" in low:
        render = _first(_RECAPTCHA_RENDER, hay)
        if render and render.lower() != "explicit":
            action = _first(_DATA_ACTION, hay) or "verify"
            return CaptchaChallenge(CAPTCHA_RECAPTCHA_V3, url, render,
                                    page_action=action, detail="recaptcha v3")
        sk = _sitekey_prefer(hay) or _first(_RECAPTCHA_KPARAM, hay)
        return CaptchaChallenge(CAPTCHA_RECAPTCHA_V2, url, sk, detail="recaptcha v2")

    # Image captcha — a base64 image in an obvious captcha context.
    img = _first(_DATA_URI_IMG, hay)
    if img and "captcha" in low:
        return CaptchaChallenge(CAPTCHA_IMAGE, url, image_b64=img, detail="image captcha")

    return None


# ── token injection (provider-standard receivers; no site selectors) ──────────
_RESPONSE_FIELD = {
    CAPTCHA_RECAPTCHA_V2: "g-recaptcha-response",
    CAPTCHA_RECAPTCHA_V3: "g-recaptcha-response",
    CAPTCHA_HCAPTCHA: "h-captcha-response",
    CAPTCHA_TURNSTILE: "cf-turnstile-response",
}


def injection_script(challenge: CaptchaChallenge, token: str) -> str:
    """The JS the extension runs to place a solved token where the site's verify reads it.

    reCAPTCHA/hCaptcha expose a hidden ``textarea[name=<field>]`` (and ``#g-recaptcha-
    response``); Turnstile a hidden ``input[name=cf-turnstile-response]``. These names are
    the provider's own convention — **not** site selectors. Image captchas have no hidden
    receiver (the actor types the text into the visible field), so this returns "".
    """
    if challenge is None:
        return ""
    field = _RESPONSE_FIELD.get(challenge.kind)
    if not field:
        return ""
    tok = json.dumps(token)
    fld = json.dumps(field)
    return (
        "(function(){var t=" + tok + ";var f=" + fld + ";"
        "var els=document.querySelectorAll('textarea[name=\"'+f+'\"],input[name=\"'+f+'\"],#'+f);"
        "if(!els.length){var ta=document.createElement('textarea');ta.name=f;"
        "ta.style.display='none';document.body.appendChild(ta);els=[ta];}"
        "els.forEach(function(el){el.value=t;"
        "el.dispatchEvent(new Event('input',{bubbles:true}));"
        "el.dispatchEvent(new Event('change',{bubbles:true}));});"
        "return true;})();"
    )


# ── the solver client ─────────────────────────────────────────────────────────
_CAPSOLVER_BASE = "https://api.capsolver.com"
_TWOCAPTCHA_IN = "https://2captcha.com/in.php"
_TWOCAPTCHA_RES = "https://2captcha.com/res.php"

_CAPSOLVER_TASK = {
    CAPTCHA_RECAPTCHA_V2: "ReCaptchaV2TaskProxyLess",
    CAPTCHA_RECAPTCHA_V3: "ReCaptchaV3TaskProxyLess",
    CAPTCHA_HCAPTCHA: "HCaptchaTaskProxyLess",
    CAPTCHA_TURNSTILE: "AntiTurnstileTaskProxyLess",
    CAPTCHA_IMAGE: "ImageToTextTask",
}
_TWOCAPTCHA_METHOD = {
    CAPTCHA_RECAPTCHA_V2: "userrecaptcha",
    CAPTCHA_RECAPTCHA_V3: "userrecaptcha",
    CAPTCHA_HCAPTCHA: "hcaptcha",
    CAPTCHA_TURNSTILE: "turnstile",
    CAPTCHA_IMAGE: "base64",
}
_NOT_READY = {"CAPCHA_NOT_READY", "CAPTCHA_NOT_READY"}


def _requests_http(method: str, url: str, *, json: Any = None, data: Any = None,
                   params: Any = None, timeout: float = 30) -> Any:
    """Default HTTP adapter. ``requests`` is imported lazily so importing this module
    never requires it (keeps engine boot + the guarded-step cell dependency-light)."""
    import requests  # noqa: WPS433 (intentional lazy import)
    return requests.request(method, url, json=json, data=data, params=params, timeout=timeout)


def _json(resp: Any) -> dict:
    try:
        out = resp.json()
        return out if isinstance(out, dict) else {}
    except Exception:
        try:
            return json.loads(getattr(resp, "text", "") or "{}") or {}
        except Exception:
            return {}


def _extract_token(solution: dict, kind: str) -> str:
    for k in ("gRecaptchaResponse", "token", "text"):
        v = solution.get(k)
        if v:
            return str(v)
    return ""


class CaptchaSolver:
    """CapSolver (primary) + 2Captcha (fallback). HTTP is injectable for offline tests.

    ``solve`` tries CapSolver first; on any failure (and if a 2Captcha key is set) it
    falls back to 2Captcha. The poll loop is bounded by ``timeout/poll_interval`` *iterations*
    (not wall-clock) so a test with a no-op ``sleep`` still terminates deterministically.
    """

    def __init__(self, *, capsolver_key: Optional[str] = None,
                 twocaptcha_key: Optional[str] = None,
                 http: Optional[Callable[..., Any]] = None,
                 poll_interval: float = 3.0, timeout: float = 120.0,
                 sleep: Optional[Callable[[float], Any]] = None) -> None:
        self.capsolver_key = (capsolver_key or "").strip()
        self.twocaptcha_key = (twocaptcha_key or "").strip()
        self._http = http or _requests_http
        self.poll_interval = max(0.0, float(poll_interval))
        self.timeout = max(1.0, float(timeout))
        self._sleep = sleep or time.sleep

    @property
    def available(self) -> bool:
        return bool(self.capsolver_key or self.twocaptcha_key)

    @property
    def _max_polls(self) -> int:
        step = self.poll_interval if self.poll_interval > 0 else 1.0
        return max(1, int(self.timeout / step))

    # -- the live smoke test: a tiny balance read, no full solve --------------
    def balance(self) -> float:
        """CapSolver ``getBalance`` — the cheap live health-check for the client + key."""
        if not self.capsolver_key:
            raise CaptchaError("no CAPSOLVER_API_KEY configured")
        r = self._http("POST", f"{_CAPSOLVER_BASE}/getBalance",
                       json={"clientKey": self.capsolver_key}, timeout=20)
        data = _json(r)
        if data.get("errorId"):
            raise CaptchaError(
                f"capsolver getBalance error: "
                f"{data.get('errorCode') or data.get('errorDescription') or data}")
        return float(data.get("balance") or 0.0)

    # -- solve (capsolver → 2captcha fallback) --------------------------------
    def solve(self, challenge: CaptchaChallenge) -> SolveResult:
        errors = []
        if self.capsolver_key:
            res = self._solve_capsolver(challenge)
            if res.ok:
                return res
            errors.append(f"capsolver: {res.error}")
        if self.twocaptcha_key:
            res = self._solve_twocaptcha(challenge)
            if res.ok:
                return res
            errors.append(f"twocaptcha: {res.error}")
        return SolveResult(False, kind=challenge.kind,
                           error="; ".join(errors) or "no solver key configured")

    def _capsolver_task(self, challenge: CaptchaChallenge) -> Optional[dict]:
        t = _CAPSOLVER_TASK.get(challenge.kind)
        if not t:
            return None
        if challenge.kind == CAPTCHA_IMAGE:
            return {"type": t, "body": challenge.image_b64}
        task = {"type": t, "websiteURL": challenge.website_url,
                "websiteKey": challenge.sitekey}
        if challenge.kind == CAPTCHA_RECAPTCHA_V3:
            task["pageAction"] = challenge.page_action or "verify"
        return task

    def _solve_capsolver(self, challenge: CaptchaChallenge) -> SolveResult:
        task = self._capsolver_task(challenge)
        if task is None:
            return SolveResult(False, provider="capsolver", kind=challenge.kind,
                               error="unsupported challenge type")
        calls = 1
        data = _json(self._http("POST", f"{_CAPSOLVER_BASE}/createTask",
                                json={"clientKey": self.capsolver_key, "task": task},
                                timeout=30))
        if data.get("errorId") or not data.get("taskId"):
            return SolveResult(False, provider="capsolver", kind=challenge.kind, cost_calls=calls,
                               error=str(data.get("errorDescription")
                                         or data.get("errorCode") or "createTask failed"))
        task_id = data["taskId"]
        for _ in range(self._max_polls):
            self._sleep(self.poll_interval)
            calls += 1
            data = _json(self._http("POST", f"{_CAPSOLVER_BASE}/getTaskResult",
                                    json={"clientKey": self.capsolver_key, "taskId": task_id},
                                    timeout=30))
            if data.get("errorId"):
                return SolveResult(False, provider="capsolver", kind=challenge.kind, cost_calls=calls,
                                   error=str(data.get("errorDescription") or "getTaskResult error"))
            if data.get("status") == "ready":
                token = _extract_token(data.get("solution") or {}, challenge.kind)
                if token:
                    return SolveResult(True, token=token, provider="capsolver",
                                       kind=challenge.kind, cost_calls=calls)
                return SolveResult(False, provider="capsolver", kind=challenge.kind, cost_calls=calls,
                                   error="ready but no token in solution")
        return SolveResult(False, provider="capsolver", kind=challenge.kind,
                           cost_calls=calls, error="timeout waiting for solution")

    def _solve_twocaptcha(self, challenge: CaptchaChallenge) -> SolveResult:
        method = _TWOCAPTCHA_METHOD.get(challenge.kind)
        if not method:
            return SolveResult(False, provider="twocaptcha", kind=challenge.kind,
                               error="unsupported challenge type")
        params: dict[str, Any] = {"key": self.twocaptcha_key, "method": method, "json": 1}
        if challenge.kind == CAPTCHA_IMAGE:
            params["body"] = challenge.image_b64
        else:
            params["pageurl"] = challenge.website_url
            if challenge.kind in (CAPTCHA_RECAPTCHA_V2, CAPTCHA_RECAPTCHA_V3):
                params["googlekey"] = challenge.sitekey
            else:
                params["sitekey"] = challenge.sitekey
            if challenge.kind == CAPTCHA_RECAPTCHA_V3:
                params["version"] = "v3"
                params["action"] = challenge.page_action or "verify"
        calls = 1
        data = _json(self._http("POST", _TWOCAPTCHA_IN, data=params, timeout=30))
        if str(data.get("status")) != "1":
            return SolveResult(False, provider="twocaptcha", kind=challenge.kind, cost_calls=calls,
                               error=str(data.get("request") or "in.php submit failed"))
        cid = data["request"]
        for _ in range(self._max_polls):
            self._sleep(self.poll_interval)
            calls += 1
            data = _json(self._http("GET", _TWOCAPTCHA_RES,
                                    params={"key": self.twocaptcha_key, "action": "get",
                                            "id": cid, "json": 1}, timeout=30))
            if str(data.get("status")) == "1":
                return SolveResult(True, token=str(data.get("request")), provider="twocaptcha",
                                   kind=challenge.kind, cost_calls=calls)
            if str(data.get("request")) not in _NOT_READY:
                return SolveResult(False, provider="twocaptcha", kind=challenge.kind,
                                   cost_calls=calls, error=str(data.get("request")))
        return SolveResult(False, provider="twocaptcha", kind=challenge.kind,
                           cost_calls=calls, error="timeout waiting for solution")


# ── the recovery-ladder bridge ────────────────────────────────────────────────
def resolve_captcha(page: Any, solver: Optional[CaptchaSolver], *,
                    page_url: str = "") -> CaptchaOutcome:
    """Detect → solve → package the outcome for the recovery ladder (guarded_step).

    Returns ``solved=True`` with the token + the injection script when a challenge is
    present and a solver clears it; otherwise ``solved=False`` with a reason — which is
    the ladder's signal to bump ``captcha_solves_used`` and fall through to L4 handoff.
    """
    challenge = detect_captcha(page)
    if challenge is None:
        return CaptchaOutcome(False, error="no captcha detected on page")
    if page_url and not challenge.website_url:
        challenge = replace(challenge, website_url=page_url)
    if not solver or not getattr(solver, "available", False):
        return CaptchaOutcome(False, challenge=challenge, error="no captcha solver configured")
    res = solver.solve(challenge)
    if not res.ok:
        return CaptchaOutcome(False, challenge=challenge, error=res.error)
    return CaptchaOutcome(True, challenge=challenge, token=res.token, provider=res.provider,
                          injection=injection_script(challenge, res.token))


def from_env(**kwargs: Any) -> CaptchaSolver:
    """Build a solver from ``.env.local`` (``CAPSOLVER_API_KEY`` / ``TWOCAPTCHA_API_KEY``)."""
    load_local_env()
    return CaptchaSolver(
        capsolver_key=os.environ.get("CAPSOLVER_API_KEY"),
        twocaptcha_key=os.environ.get("TWOCAPTCHA_API_KEY"),
        **kwargs,
    )
