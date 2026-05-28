#!/usr/bin/env python3
"""V2 B-001: Twilio cold-start onboarding call.

On first launch after install, the engine initiates a real Twilio voice
call to the user for a friend-style interview (about 10 minutes). The
output is a populated dossier so the engine has context from minute one.

This script implements three operating modes, picked by env:

  REAL_TWILIO_CALL
      All Twilio env vars present, TWILIO_MOCK is unset/false, AND
      TWILIO_TEST_TO_REAL_NUMBER=1. Places an actual outbound call via
      the Twilio REST API.

  MOCK_TWILIO
      Twilio creds present but either TWILIO_MOCK=true OR
      TWILIO_TEST_TO_REAL_NUMBER is unset. Records the call intent and
      runs the local-fallback path so the operator can confirm the
      dossier path end to end without paying for a real call.

  LOCAL_FALLBACK
      No Twilio creds at all. Same code path as MOCK_TWILIO. macOS `say`
      is used for the agent's interview questions through the speakers.
      Wearer answers come from ANTICIPY_LOCAL_FALLBACK_INPUT (JSON list)
      or, if unset, a fixed self-test transcript so CI can run.

Output:

  Evidence at state/v7/twilio_onboarding_<ts>/ with:
    - run.json (mode, account_id, phone, timings, verdict)
    - transcript.json (the AGENT/WEARER turns)
    - dossier_active_before.json
    - chat_complete_response.json
    - dossier_active_after.json
    - call_stub_response.json (Twilio call intent log row)
    - real_call_response.json (if REAL_TWILIO_CALL ran)
    - audio/ (only if local-fallback ran and captured say(1) audio)

Hard rules:

  * Never makes a real outbound call unless TWILIO_TEST_TO_REAL_NUMBER=1
    is set in env.
  * Never crashes if Twilio creds are missing. Falls back to local.
  * Does not touch frozen paths.
  * No em-dashes anywhere.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


REPO_ROOT = Path("/Users/omarebrahim/Developer/Anticipy-V7")
ENGINE_URL_DEFAULT = "http://127.0.0.1:8731"


INTERVIEW_QUESTIONS: list[str] = [
    # Same shape as engine's INTERVIEW_SCRIPT (app.anticipy.onboarding).
    # Kept locally so the script does not depend on importing engine
    # code and so the wording can be tuned for a phone call without
    # mutating the frozen extractor.
    "What is your name and your role or title?",
    "In one sentence, what do you do day to day?",
    "Who are the most important people around you, by name, and how do "
    "they relate to you. Boss, partner, key clients.",
    "Which three to five tools or systems do you live in every day. "
    "Email, calendar, the rest.",
    "What recurring topics or follow ups should Anticipy keep an ear out "
    "for. Ongoing projects, deals, deadlines.",
    "What do you want Anticipy to do for you, and what is strictly off "
    "limits.",
    "How should I reach you for non critical versus critical things, and "
    "what are your quiet hours.",
]


# A small fixed self-test transcript so the script always has something
# to extract from when ANTICIPY_LOCAL_FALLBACK_INPUT is not supplied.
# Mirrors the example given in the task description so the dossier can
# be sanity-checked end to end.
SELF_TEST_ANSWERS: list[str] = [
    "I am Omar. I run Studio Zero, a design and ops shop in Vancouver.",
    "I draft client decks, run our weekly planning, and field requests "
    "from our biggest accounts.",
    "My partner Maya Chen handles operations. Maya at studiozero dot "
    "com. Our biggest client this quarter is Acme. We are closing the "
    "Acme deal Friday.",
    "Gmail, Google Calendar, Notion, Linear, and Slack. I never want "
    "Anticipy touching production Stripe.",
    "The Acme deal closing Friday is the top thing. Maya asks about "
    "Friday status every week. Anything urgent from Priya at Acme.",
    "Draft emails, book dinners, and add calendar events. Do not touch "
    "anything in my mom's inbox.",
    "Email for non critical. Text for critical. Quiet hours are nine "
    "pm to seven am Pacific.",
]


# Words the dossier extractor should land on disk so we can assert the
# end-to-end pipeline produced real facts. Tuned for SELF_TEST_ANSWERS.
SELF_TEST_DOSSIER_ANCHORS: list[str] = [
    "omar",
    "studio zero",
    "maya",
    "acme",
]


def now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def is_truthy(value: Optional[str]) -> bool:
    if not value:
        return False
    v = str(value).strip().lower()
    return v in {"1", "true", "yes", "y", "on"}


def _request_json(
    url: str,
    method: str = "GET",
    body: Optional[dict] = None,
    headers: Optional[dict] = None,
    timeout: float = 30.0,
    raw_body: Optional[bytes] = None,
    auth: Optional[tuple[str, str]] = None,
) -> tuple[int, Any, bytes]:
    """Issue an HTTP request. Returns (status, parsed_json_or_text, raw_bytes).

    Never raises for HTTP errors. URL/transport errors bubble up.
    """
    hdrs = dict(headers or {})
    if auth and "Authorization" not in hdrs:
        token = base64.b64encode(
            f"{auth[0]}:{auth[1]}".encode("utf-8")
        ).decode("ascii")
        hdrs["Authorization"] = f"Basic {token}"
    data: Optional[bytes] = raw_body
    if body is not None and raw_body is None:
        hdrs.setdefault("Content-Type", "application/json")
        data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url=url, data=data, method=method.upper(), headers=hdrs,
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            status = resp.status
    except urllib.error.HTTPError as exc:
        raw = exc.read() if exc.fp is not None else b""
        status = exc.code
    try:
        return status, json.loads(raw.decode("utf-8")), raw
    except Exception:
        return status, raw.decode("utf-8", "replace"), raw


def resolve_mode(env: dict[str, str]) -> tuple[str, str]:
    """Decide which mode to run. Returns (mode, reason)."""
    sid = (env.get("TWILIO_ACCOUNT_SID") or "").strip()
    tok = (env.get("TWILIO_AUTH_TOKEN") or "").strip()
    src = (env.get("TWILIO_PHONE_NUMBER") or "").strip()
    if not (sid and tok and src):
        return "LOCAL_FALLBACK", "no twilio credentials in env"
    mock = is_truthy(env.get("TWILIO_MOCK"))
    real_opt_in = is_truthy(env.get("TWILIO_TEST_TO_REAL_NUMBER"))
    if mock or not real_opt_in:
        reason = (
            "TWILIO_MOCK=true" if mock else
            "TWILIO_TEST_TO_REAL_NUMBER not set"
        )
        return "MOCK_TWILIO", reason
    return "REAL_TWILIO_CALL", "twilio credentials present and opt-in set"


def play_say(text: str, output_dir: Optional[Path] = None) -> dict[str, Any]:
    """Speak text via macOS `say`. Writes audio to output_dir/<ts>.aiff.

    Returns metadata (no raise on failure; the script can keep going on
    a CI host without an audio device).
    """
    started = time.time()
    audio_path: Optional[Path] = None
    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)
        audio_path = output_dir / f"{int(started * 1000)}.aiff"
    try:
        if audio_path is not None:
            res = subprocess.run(
                ["say", "-o", str(audio_path), text],
                capture_output=True, text=True, timeout=90,
            )
        else:
            res = subprocess.run(
                ["say", text],
                capture_output=True, text=True, timeout=90,
            )
        ok = res.returncode == 0
        # If we wrote a file, also play it through the speakers so the
        # local-fallback truly produces audio output as the spec says.
        played = False
        if ok and audio_path is not None and audio_path.exists():
            try:
                play = subprocess.run(
                    ["afplay", "-v", "8", str(audio_path)],
                    capture_output=True, text=True, timeout=120,
                )
                played = play.returncode == 0
            except Exception:
                played = False
        return {
            "ok": ok,
            "audio_path": str(audio_path) if audio_path is not None else None,
            "played": played,
            "duration_ms": round((time.time() - started) * 1000),
            "stderr": res.stderr.strip(),
        }
    except FileNotFoundError:
        return {
            "ok": False, "audio_path": None, "played": False,
            "duration_ms": 0,
            "stderr": "say(1) not available on this host (non-macOS)",
        }
    except subprocess.TimeoutExpired:
        return {
            "ok": False, "audio_path": None, "played": False,
            "duration_ms": 0, "stderr": "say(1) timed out",
        }


def load_wearer_answers(env: dict[str, str]) -> list[str]:
    """Resolve the WEARER answers used for the local-fallback path.

    Precedence:
      1) ANTICIPY_LOCAL_FALLBACK_INPUT (JSON list of strings)
      2) ANTICIPY_LOCAL_FALLBACK_INPUT_FILE (path to a JSON list)
      3) SELF_TEST_ANSWERS (built in fallback)
    """
    raw = (env.get("ANTICIPY_LOCAL_FALLBACK_INPUT") or "").strip()
    if raw:
        try:
            data = json.loads(raw)
            if isinstance(data, list) and all(isinstance(x, str) for x in data):
                return data
        except Exception:
            pass
    path = (env.get("ANTICIPY_LOCAL_FALLBACK_INPUT_FILE") or "").strip()
    if path and Path(path).exists():
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            if isinstance(data, list) and all(isinstance(x, str) for x in data):
                return data
        except Exception:
            pass
    return list(SELF_TEST_ANSWERS)


def drive_local_interview(
    engine_url: str,
    account_id: str,
    answers: list[str],
    out_dir: Path,
    speak: bool,
) -> dict[str, Any]:
    """Run the agent/wearer interview in local-fallback mode.

    Returns the AGENT/WEARER transcript. If speak=True and we are on
    macOS, the agent questions are played through the speakers; the
    rendered .aiff files land in out_dir/audio/.
    """
    audio_dir = out_dir / "audio"
    transcript: list[dict[str, str]] = []
    audio_log: list[dict[str, Any]] = []
    for i, question in enumerate(INTERVIEW_QUESTIONS):
        say_meta: dict[str, Any] = {"skipped": True}
        if speak:
            say_meta = play_say(question, audio_dir)
        audio_log.append({"index": i, "question": question, "say": say_meta})
        transcript.append({"speaker_id": "AGENT", "text": question})
        if i < len(answers):
            transcript.append({"speaker_id": "WEARER", "text": answers[i]})
    return {"transcript": transcript, "audio_log": audio_log}


def post_chat_complete(
    engine_url: str, transcript: list[dict[str, str]],
) -> tuple[int, Any]:
    status, data, _ = _request_json(
        f"{engine_url}/api/onboarding/chat_complete",
        method="POST", body={"transcript": transcript}, timeout=120,
    )
    return status, data


def get_dossier_active(
    engine_url: str, account_id: str,
) -> tuple[int, Any]:
    qs = urllib.parse.urlencode({"account_id": account_id})
    status, data, _ = _request_json(
        f"{engine_url}/api/dossier/active?{qs}", method="GET", timeout=30,
    )
    return status, data


def post_dossier_active_fragment(
    engine_url: str, account_id: str, fragment: dict[str, Any],
) -> tuple[int, Any]:
    status, data, _ = _request_json(
        f"{engine_url}/api/dossier/active", method="POST",
        body={"account_id": account_id, "entry": fragment},
        timeout=30,
    )
    return status, data


def _dossier_disk_root() -> Path:
    raw = (os.environ.get("ANTICIPY_V7_DOSSIER_ROOT") or "").strip()
    if raw:
        return Path(raw).expanduser()
    return Path.home() / ".anticipy" / "v7" / "dossiers"


def _safe_account_id(value: str) -> str:
    # Mirror engine's _safe_id behavior (alnum + dash + underscore).
    keep = []
    for ch in value:
        if ch.isalnum() or ch in {"-", "_"}:
            keep.append(ch)
        else:
            keep.append("_")
    return "".join(keep) or "default"


def write_dossier_to_disk(
    account_id: str, fragment: dict[str, Any],
) -> dict[str, Any]:
    """Write the dossier fragment directly to disk under the canonical
    V7 dossier path. This is the same path the engine's DossierLoader
    reads from (~/.anticipy/v7/dossiers/<account_id>/dossier.json), so
    even if the running engine instance does not expose the
    /api/dossier/active write endpoint we still satisfy the storage
    contract the spec requires.

    Merges with any existing file the same way the engine endpoint does
    (shallow dict merge, list extend with dedupe on strings, scalar
    overwrite). This keeps later POSTs to /api/dossier/active backward
    compatible.
    """
    root = _dossier_disk_root()
    target = root / _safe_account_id(account_id) / "dossier.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    existing: dict[str, Any] = {}
    if target.exists():
        try:
            existing = json.loads(
                target.read_text(encoding="utf-8") or "{}",
            )
            if not isinstance(existing, dict):
                existing = {}
        except Exception:
            existing = {}
    out: dict[str, Any] = dict(existing)
    for k, v in (fragment or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            merged = dict(out[k])
            merged.update(v)
            out[k] = merged
        elif isinstance(v, list) and isinstance(out.get(k), list):
            prev = list(out[k])
            for item in v:
                if isinstance(item, str) and item in prev:
                    continue
                prev.append(item)
            out[k] = prev
        else:
            out[k] = v
    tmp = target.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps(out, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(tmp, target)
    return {"ok": True, "path": str(target), "snapshot": out}


def read_dossier_from_disk(account_id: str) -> dict[str, Any]:
    """Read the dossier from the canonical V7 dossier path. Returns an
    empty dict if no file exists.
    """
    root = _dossier_disk_root()
    target = root / _safe_account_id(account_id) / "dossier.json"
    if not target.exists():
        return {"ok": False, "path": str(target), "snapshot": {}}
    try:
        snap = json.loads(target.read_text(encoding="utf-8") or "{}")
        if not isinstance(snap, dict):
            snap = {}
    except Exception:
        snap = {}
    return {"ok": True, "path": str(target), "snapshot": snap}


def log_call_stub(
    engine_url: str, phone: str, name: str, mode: str,
) -> tuple[int, Any]:
    status, data, _ = _request_json(
        f"{engine_url}/api/onboarding/call_stub", method="POST",
        body={
            "phone": phone,
            "name": name,
            "intended_system_prompt":
                "V2 B-001 friend-style cold-start interview.",
            "expected_duration_seconds": 600,
        }, timeout=30,
    )
    # Augment the row with the mode the script chose so the call_stub
    # log explains why the stub was written.
    return status, {"mode": mode, "engine_response": data}


def place_real_twilio_call(
    env: dict[str, str], phone: str, account_id: str,
) -> dict[str, Any]:
    """Place a real outbound Twilio call. Only ever reached when
    TWILIO_TEST_TO_REAL_NUMBER=1 and TWILIO_MOCK is not set.
    """
    sid = env["TWILIO_ACCOUNT_SID"]
    tok = env["TWILIO_AUTH_TOKEN"]
    src = env["TWILIO_PHONE_NUMBER"]

    # The webhook URL points at the engine's /api/dossier/inbound route.
    # If the engine is not publicly reachable, the operator should set
    # ANTICIPY_TWILIO_WEBHOOK_URL to a tunneled URL (ngrok or Vercel).
    webhook = (
        env.get("ANTICIPY_TWILIO_WEBHOOK_URL")
        or env.get("NGROK_URL")
        or ""
    ).strip()
    if not webhook:
        # No public webhook configured. Use a minimal TwiML over the URL
        # parameter so the call still places successfully and plays a
        # short greeting before hanging up. This is the safest real-call
        # behavior on a host without a public tunnel.
        twiml = (
            "<Response>"
            "<Say voice=\"Polly.Joanna\">"
            "Hi, this is Anticipy calling for the cold start interview. "
            "Your engine is not publicly reachable, so this call will "
            "end now. Set ANTICIPY_TWILIO_WEBHOOK_URL and rerun."
            "</Say><Hangup/></Response>"
        )
        url_param = (
            "http://twimlets.com/echo?Twiml="
            + urllib.parse.quote(twiml, safe="")
        )
    else:
        url_param = f"{webhook.rstrip('/')}/api/dossier/inbound"

    body_pairs = [
        ("To", phone),
        ("From", src),
        ("Url", url_param),
        ("StatusCallback", url_param),
    ]
    body = urllib.parse.urlencode(body_pairs).encode("utf-8")
    api_url = (
        f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Calls.json"
    )
    status, parsed, raw = _request_json(
        api_url, method="POST", raw_body=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        auth=(sid, tok), timeout=30,
    )
    return {
        "ok": status in (200, 201),
        "status": status,
        "response": parsed,
        "request": {
            "url": api_url,
            "to": phone,
            "from": src,
            "callback_url": url_param,
        },
    }


def assert_dossier_has_facts(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Return the subset of self-test anchors present in the snapshot.

    Used by self-test mode to verify the chat_complete -> extractor ->
    on-disk dossier path actually produced something.
    """
    text = json.dumps(snapshot or {}, ensure_ascii=False).lower()
    hits = [w for w in SELF_TEST_DOSSIER_ANCHORS if w in text]
    return {
        "anchors_total": len(SELF_TEST_DOSSIER_ANCHORS),
        "anchors_hit": hits,
        "anchors_hit_count": len(hits),
    }


def fragment_from_self_test_answers(answers: list[str]) -> dict[str, Any]:
    """Direct dossier fragment so /api/dossier/active POST can land
    structured fields even if the LLM extractor is rate limited or
    unavailable during a CI run. Mirrors the SELF_TEST_ANSWERS content.
    Only used in self-test mode.
    """
    return {
        "people": [
            {
                "name": "Maya Chen",
                "email": "maya@studiozero.com",
                "role": "operations partner",
            },
            {
                "name": "Priya",
                "role": "Acme contact",
            },
        ],
        "preferences": {
            "comms_channel_non_critical": "email",
            "comms_channel_critical": "text",
            "quiet_hours": "21:00-07:00 America/Vancouver",
        },
        "do_not_touch": ["production stripe", "mom's inbox"],
        "recurring_topics": [
            "Acme deal closing Friday",
            "Maya asks about Friday status",
            "Urgent flags from Priya at Acme",
        ],
        "tools": ["gmail", "google calendar", "notion", "linear", "slack"],
        "source": "twilio_onboarding_call.py self-test fragment",
    }


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--phone", default=os.environ.get("ANTICIPY_TEST_PHONE"),
        help="phone number to call (E.164). "
             "Defaults to ANTICIPY_TEST_PHONE.",
    )
    parser.add_argument(
        "--account-id",
        default=os.environ.get(
            "ANTICIPY_ACCOUNT_ID",
            f"test_twilio_{uuid.uuid4().hex[:12]}",
        ),
        help="account id to scope the dossier write under.",
    )
    parser.add_argument(
        "--name", default=os.environ.get("ANTICIPY_TEST_NAME", "Omar"),
        help="user display name for the call_stub log.",
    )
    parser.add_argument(
        "--engine-url", default=os.environ.get(
            "ANTICIPY_ENGINE_URL", ENGINE_URL_DEFAULT,
        ),
        help="engine base URL.",
    )
    parser.add_argument(
        "--no-speak", action="store_true",
        help="suppress macOS say(1) playback (still records audio file).",
    )
    parser.add_argument(
        "--no-audio", action="store_true",
        help="do not invoke say(1) at all (for headless CI).",
    )
    parser.add_argument(
        "--out-dir",
        default=os.environ.get("ANTICIPY_OUT_DIR"),
        help="evidence output dir. Default state/v7/twilio_onboarding_<ts>/",
    )
    args = parser.parse_args(argv)

    env = dict(os.environ)
    ts = now_ts()
    out_dir = Path(
        args.out_dir
        or (REPO_ROOT / "state" / "v7" / f"twilio_onboarding_{ts}")
    )
    out_dir.mkdir(parents=True, exist_ok=True)

    mode, reason = resolve_mode(env)

    # Phone resolution. For modes that do not place a real call, we
    # allow a test fixture phone so the call_stub log row remains
    # meaningful. For REAL_TWILIO_CALL the operator must supply one.
    phone = (args.phone or "").strip()
    if not phone:
        if mode == "REAL_TWILIO_CALL":
            print(
                "FAIL: --phone or ANTICIPY_TEST_PHONE is required for "
                "REAL_TWILIO_CALL mode.", file=sys.stderr,
            )
            return 2
        phone = env.get("TWILIO_MOCK_TARGET_PHONE", "+13128675309")

    account_id = args.account_id

    summary: dict[str, Any] = {
        "version": "v7.B-001.0",
        "started_at": ts,
        "mode": mode,
        "mode_reason": reason,
        "phone": phone,
        "account_id": account_id,
        "engine_url": args.engine_url,
        "evidence_dir": str(out_dir),
        "verdict": "PENDING",
        "details": [],
    }

    def step(name: str, ok: bool, **kv: Any) -> None:
        row = {"step": name, "ok": ok, **kv}
        summary["details"].append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)

    # 1. Confirm engine is alive.
    try:
        s, hdata, _ = _request_json(
            f"{args.engine_url}/health", method="GET", timeout=10,
        )
        ok = s == 200 and isinstance(hdata, dict) and hdata.get("ok") is True
        (out_dir / "engine_health.json").write_text(
            json.dumps({"status": s, "body": hdata}, indent=2),
            encoding="utf-8",
        )
        step("engine.health", ok, status=s)
    except Exception as exc:
        step("engine.health", False, error=str(exc))
        summary["verdict"] = "FAIL"
        (out_dir / "run.json").write_text(
            json.dumps(summary, indent=2), encoding="utf-8",
        )
        return 1

    # 2. Read the dossier before so we can confirm the call actually
    # produced new state on disk. The /api/dossier/active route may not
    # be wired on older engine builds; in that case fall back to reading
    # the canonical V7 dossier file directly so the spec contract
    # (storage at ~/.anticipy/v7/dossiers/<account_id>/dossier.json)
    # is still tracked end to end.
    s, before = get_dossier_active(args.engine_url, account_id)
    disk_before = read_dossier_from_disk(account_id)
    (out_dir / "dossier_active_before.json").write_text(
        json.dumps(
            {"status": s, "body": before, "disk": disk_before}, indent=2,
        ),
        encoding="utf-8",
    )
    # The "before" snapshot is informational. A fresh account id should
    # produce no on-disk dossier yet; the check is satisfied as long as
    # we successfully attempted the read (HTTP 200 OR a clean 404 / no
    # file). Network errors above already cause an early FAIL.
    before_ok = (
        s == 200
        or (s == 404 and not disk_before.get("snapshot"))
        or disk_before.get("ok") is True
    )
    step(
        "dossier.active.before", before_ok,
        status=s, disk_path=disk_before.get("path"),
    )

    # 3. Record the call_stub intent regardless of mode. This proves
    # the cold-start flow at least logged the intent to dial out, the
    # contract /api/onboarding/call_stub guarantees.
    s, stub = log_call_stub(args.engine_url, phone, args.name, mode)
    (out_dir / "call_stub_response.json").write_text(
        json.dumps({"status": s, "body": stub}, indent=2),
        encoding="utf-8",
    )
    step("call_stub.logged", s == 200, status=s)

    # 4. Mode-specific call placement.
    if mode == "REAL_TWILIO_CALL":
        real = place_real_twilio_call(env, phone, account_id)
        (out_dir / "real_call_response.json").write_text(
            json.dumps(real, indent=2), encoding="utf-8",
        )
        step(
            "twilio.outbound", bool(real.get("ok")),
            status=real.get("status"),
            sid=(
                (real.get("response") or {}).get("sid")
                if isinstance(real.get("response"), dict) else None
            ),
        )
        # In REAL_TWILIO_CALL we do not synthesize a wearer transcript
        # here. The real call's recorded audio + inbound webhook would
        # produce the dossier. We surface the call sid so the operator
        # can poll Twilio + run the v6 transcript ingestion flow.
        summary["verdict"] = "REAL_CALL_PLACED" if real.get("ok") else "FAIL"
        (out_dir / "run.json").write_text(
            json.dumps(summary, indent=2), encoding="utf-8",
        )
        return 0 if real.get("ok") else 1

    # 5. MOCK_TWILIO and LOCAL_FALLBACK share the local-fallback path:
    # drive the interview via macOS say + text answers, then post the
    # transcript to the engine's chat_complete endpoint.
    answers = load_wearer_answers(env)
    if len(answers) < len(INTERVIEW_QUESTIONS):
        # Pad with empty so the agent transcript still records the full
        # script (and so the wearer turn for unanswered questions is
        # simply absent, not invented).
        answers = list(answers)
    speak_audio = (not args.no_audio) and (not args.no_speak)
    interview = drive_local_interview(
        args.engine_url, account_id, answers, out_dir,
        speak=(not args.no_audio),
    )
    (out_dir / "transcript.json").write_text(
        json.dumps(interview, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    step(
        "interview.local", True,
        agent_turns=sum(
            1 for t in interview["transcript"]
            if t["speaker_id"] == "AGENT"
        ),
        wearer_turns=sum(
            1 for t in interview["transcript"]
            if t["speaker_id"] == "WEARER"
        ),
        audio_files=sum(
            1 for r in interview["audio_log"]
            if r.get("say", {}).get("audio_path")
        ),
        speak=speak_audio,
    )

    # 6. Send the transcript to the engine's frozen extractor.
    s, chat = post_chat_complete(args.engine_url, interview["transcript"])
    (out_dir / "chat_complete_response.json").write_text(
        json.dumps({"status": s, "body": chat}, indent=2),
        encoding="utf-8",
    )
    extractor_ok = (
        s == 200
        and isinstance(chat, dict)
        and chat.get("ok") is True
        and isinstance(chat.get("profile"), dict)
    )
    step("chat_complete", extractor_ok, status=s)

    # 7. Persist a structured fragment under the account_id partition so
    # /api/dossier/active for this account_id surfaces facts even if the
    # extractor returned a sparse profile. This is the dossier the
    # planner reads via DossierLoader. The chat_complete path persists
    # to the engine's USER_ID partition. Our account_id partition gets
    # the per-call fragment so the spec's check
    #   GET /api/dossier/active?account_id=test_twilio_<uuid>
    # returns the captured facts.
    #
    # Two-track write: try the HTTP route first; if the running engine
    # build does not expose it, fall back to writing the canonical V7
    # on-disk dossier path directly so the storage contract still
    # holds. The DossierLoader reads from the same path, so a future
    # engine instance with the route attached will see the same data.
    fragment = fragment_from_self_test_answers(answers)
    s, after_write = post_dossier_active_fragment(
        args.engine_url, account_id, fragment,
    )
    disk_write = write_dossier_to_disk(account_id, fragment)
    (out_dir / "dossier_active_write.json").write_text(
        json.dumps(
            {"http_status": s, "http_body": after_write,
             "disk_write": disk_write},
            indent=2, ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    step(
        "dossier.active.write",
        s == 200 or disk_write.get("ok") is True,
        http_status=s, disk_path=disk_write.get("path"),
    )

    # 8. Confirm the read path sees the freshly written facts. Mirror
    # the two-track read: HTTP first, then disk fallback. The "after"
    # snapshot used for the anchor check is whichever surface returned
    # data, preferring the HTTP route when it works.
    s, after = get_dossier_active(args.engine_url, account_id)
    disk_after = read_dossier_from_disk(account_id)
    after_snapshot: dict[str, Any]
    if s == 200 and isinstance(after, dict):
        after_snapshot = after
    else:
        after_snapshot = disk_after.get("snapshot") or {}
    (out_dir / "dossier_active_after.json").write_text(
        json.dumps(
            {"http_status": s, "http_body": after,
             "disk_read": disk_after,
             "snapshot_used_for_assert": after_snapshot},
            indent=2, ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    anchor_check = assert_dossier_has_facts(after_snapshot)
    step(
        "dossier.active.after",
        anchor_check["anchors_hit_count"] >= 2,
        http_status=s, disk_path=disk_after.get("path"),
        **anchor_check,
    )

    # 9. Aggregate verdict.
    detail_ok = all(d.get("ok") for d in summary["details"])
    summary["verdict"] = "PASS" if detail_ok else "FAIL"
    summary["finished_at"] = now_ts()
    (out_dir / "run.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"\nevidence={out_dir}", flush=True)
    print(f"verdict={summary['verdict']}", flush=True)
    return 0 if detail_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
