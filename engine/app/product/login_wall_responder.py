"""Login-wall fallback: when the action engine drives a real site and
hits an authentication wall, Anticipy notifies the user via Twilio so
they can finish the login in the browser. Per owner rule (2026-05-28):
"If it needs to sign into something, it calls you and asks."

Security stance: we do NOT ask the user to speak the password over the
phone. ASR is unreliable on random secrets and would leave a recorded
audio trail. The Twilio call instead alerts the user, names the service
and task, and asks them to type the password into the open browser
window. The action engine wrapper pauses until the user resumes it.

This module is a SIBLING of the frozen engine/app/action_engine/ tree.
It must not import from action_engine/ at module load time; the wiring
is one-directional (server.py wraps action_engine; this module exposes
helpers server.py can call).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


KNOWN_LOGIN_HOSTS: dict[str, str] = {
    "accounts.google.com": "Google",
    "mail.google.com/mail/u/0/_/_/signin": "Gmail",
    "login.microsoftonline.com": "Microsoft",
    "login.live.com": "Microsoft",
    "slack.com/signin": "Slack",
    "app.slack.com/signin": "Slack",
    "trello.com/login": "Trello",
    "id.atlassian.com": "Atlassian",
    "notion.so/login": "Notion",
    "linear.app/login": "Linear",
    "github.com/login": "GitHub",
    "twitter.com/i/flow/login": "X (Twitter)",
    "x.com/i/flow/login": "X (Twitter)",
    "linkedin.com/uas/login": "LinkedIn",
    "linkedin.com/checkpoint": "LinkedIn",
    "stripe.com/login": "Stripe",
    "dashboard.stripe.com/login": "Stripe",
    "amazon.com/ap/signin": "Amazon",
    "smile.amazon.com/ap/signin": "Amazon",
    "apple.com/auth": "Apple ID",
    "appleid.apple.com": "Apple ID",
    "dropbox.com/login": "Dropbox",
    "okta.com/login": "Okta",
    "auth0.com/login": "Auth0",
    "secure.bookingbug.com": "BookingBug",
    "calendly.com/users/sign_in": "Calendly",
}


_TITLE_HINTS = (
    "sign in",
    "log in",
    "login",
    "signin",
    "authenticate",
    "two-step verification",
    "two factor",
    "2-step",
)


def detect_login_wall(url: str, title: str | None = None) -> dict[str, Any]:
    """Cheap, deterministic check: URL substring match first (highest
    signal), then title hint as a fallback. Returns a dict the caller
    can branch on.
    """
    u = (url or "").lower()
    for host_fragment, label in KNOWN_LOGIN_HOSTS.items():
        if host_fragment.lower() in u:
            return {
                "is_login_wall": True,
                "service": label,
                "reason": f"url matched known host fragment {host_fragment!r}",
            }
    t = (title or "").lower()
    if any(h in t for h in _TITLE_HINTS):
        host = ""
        try:
            host = urllib.parse.urlparse(url).netloc or ""
        except Exception:
            host = ""
        return {
            "is_login_wall": True,
            "service": host or "this site",
            "reason": "title looked like a sign-in page",
        }
    return {"is_login_wall": False, "service": None, "reason": "no match"}


def _normalize_phone(phone: str) -> str:
    """Same minimal E.164 normalization the onboarding path uses."""
    p = re.sub(r"[^0-9+]", "", phone or "")
    if not p:
        return ""
    if not p.startswith("+"):
        if len(p) == 10:
            p = "+1" + p
        elif len(p) == 11 and p.startswith("1"):
            p = "+" + p
        else:
            p = "+" + p
    return p


def _twilio_env() -> tuple[str, str, str]:
    return (
        (os.environ.get("TWILIO_ACCOUNT_SID") or "").strip(),
        (os.environ.get("TWILIO_AUTH_TOKEN") or "").strip(),
        (os.environ.get("TWILIO_PHONE_NUMBER") or "").strip(),
    )


def _twilio_ready() -> tuple[bool, str]:
    sid, tok, src = _twilio_env()
    if not (sid and tok and src):
        return False, "twilio credentials not in env"
    if (os.environ.get("TWILIO_MOCK") or "").strip().lower() in (
        "1", "true", "yes",
    ):
        return False, "TWILIO_MOCK is set"
    if (os.environ.get("TWILIO_TEST_TO_REAL_NUMBER") or "").strip() != "1":
        return False, "TWILIO_TEST_TO_REAL_NUMBER not set"
    return True, "ready"


def _build_twiml(service_label: str, task_description: str) -> str:
    """The voice prompt the user hears. Read aloud by Twilio's <Say>.
    Keeps secrets off the phone line: tells user to type the password
    in the browser window the engine has already opened.
    """
    task = (task_description or "this task").strip() or "this task"
    svc = (service_label or "the site").strip() or "the site"
    say = (
        f"Hi, this is Anticipy. I am trying to do {task} for you, "
        f"and I need you to sign into {svc}. I have the sign in page open in your "
        f"browser right now. Please type your password into that window. "
        f"I will not ask you to say the password out loud. When you are done, "
        f"come back to me and I will keep going. Thanks."
    )
    return f"<Response><Say voice=\"Polly.Joanna\">{say}</Say><Hangup/></Response>"


def _maybe_local_say(text: str) -> dict[str, Any]:
    """Real-voice local audio fallback. Used when Twilio is not
    configured so the user still hears something through the Mac.

    Routes through ``app.product.tts`` which prefers ElevenLabs (cloud
    real-voice), falls back to Polly, then finally to macOS ``say``.
    Returns the TTS module's record annotated for the caller's
    existing log shape so existing tests and dashboards keep parsing
    the same fields.
    """
    if sys.platform != "darwin":
        return {"ok": False, "skipped": True, "reason": "not macOS"}
    try:
        from app.product import tts as _tts
    except Exception as exc:
        # Hard fallback if the TTS module fails to import for any
        # reason. Preserve the legacy say behavior so the login wall
        # notification still fires.
        say_bin = shutil.which("say") or "/usr/bin/say"
        if not Path(say_bin).exists():
            return {"ok": False, "skipped": True,
                    "reason": "say binary missing",
                    "tts_import_error": f"{type(exc).__name__}: {exc}"}
        try:
            subprocess.Popen(
                [say_bin, "-r", "180", text],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            return {"ok": True, "spoken": True, "provider": "say",
                    "tts_import_error": f"{type(exc).__name__}: {exc}"}
        except Exception as e:
            return {"ok": False, "error": f"{type(e).__name__}: {e}"}
    rec = _tts.play_speech(text)
    return {
        "ok": bool(rec.get("ok")),
        "spoken": bool(rec.get("ok")),
        "provider": rec.get("provider", "none"),
        "cache_hit": bool(rec.get("cache_hit", False)),
        "synth_ms": rec.get("synth_ms", 0.0),
        "play_ms": rec.get("play_ms", 0.0),
        "total_ms": rec.get("total_ms", 0.0),
        "path": rec.get("path", ""),
        "error": rec.get("error", ""),
    }


def place_login_wall_call(
    service_label: str,
    task_description: str,
    phone: str,
    timeout: float = 30.0,
) -> dict[str, Any]:
    """Place the actual Twilio outbound call. Returns a dict describing
    what happened. Never raises.
    """
    ready, reason = _twilio_ready()
    if not ready:
        return {"ok": False, "skipped": True, "reason": reason}
    e164 = _normalize_phone(phone)
    if not e164:
        return {"ok": False, "error": "invalid phone number"}
    sid, tok, src = _twilio_env()
    twiml = _build_twiml(service_label, task_description)
    url_param = (
        "http://twimlets.com/echo?Twiml="
        + urllib.parse.quote(twiml, safe="")
    )
    body = urllib.parse.urlencode([
        ("To", e164),
        ("From", src),
        ("Url", url_param),
    ]).encode("utf-8")
    api_url = (
        f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Calls.json"
    )
    req = urllib.request.Request(
        api_url,
        data=body,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    import base64
    auth = base64.b64encode(f"{sid}:{tok}".encode("utf-8")).decode("ascii")
    req.add_header("Authorization", f"Basic {auth}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            status = r.getcode()
            raw = r.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return {
            "ok": False,
            "error": f"twilio http {e.code}",
            "body": e.read().decode("utf-8", errors="replace")[:600],
        }
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
    parsed: dict[str, Any] = {}
    try:
        parsed = json.loads(raw)
    except Exception:
        pass
    return {
        "ok": status in (200, 201),
        "status": status,
        "twilio_sid": parsed.get("sid"),
        "request": {"to": e164, "from": src, "twiml_chars": len(twiml)},
    }


def notify_login_wall(
    url: str,
    title: str | None,
    task_description: str,
    phone: str | None = None,
) -> dict[str, Any]:
    """Single entry point the action engine wrapper (or any product
    endpoint) calls. Detects the wall, places a Twilio call when
    configured, and falls back to local `say` so the user notices on
    the same machine.
    """
    ts = time.time()
    det = detect_login_wall(url, title)
    out: dict[str, Any] = {
        "ts": ts,
        "url": url,
        "title": title or "",
        "task_description": task_description,
        "phone": phone or "",
        "detection": det,
        "twilio": {"ok": False, "skipped": True,
                   "reason": "not invoked (no login wall detected)"},
        "fallback_say": {"ok": False, "skipped": True,
                         "reason": "not invoked"},
    }
    if not det.get("is_login_wall"):
        return out
    svc = det.get("service") or "the site"
    if phone:
        out["twilio"] = place_login_wall_call(svc, task_description, phone)
    else:
        out["twilio"] = {"ok": False, "skipped": True,
                         "reason": "no phone supplied"}
    say_text = (
        f"Anticipy paused. Please sign into {svc} in your browser. "
        f"I will keep going once you are done."
    )
    out["fallback_say"] = _maybe_local_say(say_text)
    return out
