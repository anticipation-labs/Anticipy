"""Track A — the WORKER (does the real thing via Arcade). Builder side.

Given ONLY a natural-language ask + the current clock, it (1) uses a cheap model to turn the ask
into a concrete event {summary, start_datetime, end_datetime} (general language->fields; it must
resolve "this Friday at 2pm" itself), then (2) creates a REAL Google Calendar event through the
engine's real ApiHand -> Arcade. It returns the real event id Arcade hands back.

LAW: this file NEVER imports, reads, or knows the judge. It receives NO expected answer / id /
label. The clock is passed in (an agent must know "now"); that is not a per-task shortcut. Events
are private holds with NO attendees (nothing reaches a third party) and a "[Anticipy test]" label so
they are identifiable + deletable.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime

from anticipy_engine.core.gateway import CHEAP, PROVIDER_OPENROUTER, ModelGateway
from anticipy_engine.core.envelopes import Job, Risk
from anticipy_engine.hands.api_hand import ApiHand, MODE_LIVE

_LABEL = "[Anticipy test] "  # uniform safety label on EVERY event — not task-specific tuning
_LIVE_TESTS_FLAG = "ANTICIPY_TRACK_A_ALLOW_LIVE_CALENDAR"


def _robust_json(raw: str):
    if not raw:
        return None
    s = re.sub(r"```(json)?", "", raw).strip()
    try:
        return json.loads(s)
    except Exception:
        pass
    a, b = s.find("{"), s.rfind("}")
    if 0 <= a < b:
        try:
            return json.loads(s[a:b + 1])
        except Exception:
            return None
    return None


def _gateway() -> ModelGateway:
    return ModelGateway(provider=PROVIDER_OPENROUTER,
                        cheap_model=os.environ.get("ANTICIPY_MODEL_CHEAP", "google/gemini-3.1-flash-lite"),
                        smart_model=os.environ.get("ANTICIPY_MODEL_SMART", "google/gemini-3.5-flash"))


def _prompt(ask: str, now: datetime) -> str:
    return (
        f"Today is {now.isoformat()} (timezone {now.tzname()}). A person said:\n"
        f'  "{ask}"\n'
        "Turn it into ONE calendar event. Reply with ONLY minified JSON: "
        '{"summary": <short title>, "start_datetime": <ISO-8601 with timezone offset>, '
        '"end_datetime": <ISO-8601 with timezone offset>}. '
        "Resolve relative dates/times against today; the event MUST be in the future. "
        "If no duration is stated, use 30 minutes. No prose, no fences."
    )


async def do(ask: str, now: datetime) -> dict:
    """Return the worker's claim. status='created' only if Arcade really made the event."""
    claim = {"ask": ask, "summary": None, "start_datetime": None, "end_datetime": None,
             "event_id": None, "status": "failed", "error": None}
    if os.environ.get(_LIVE_TESTS_FLAG) != "1":
        claim["error"] = (
            f"live calendar writes disabled; set {_LIVE_TESTS_FLAG}=1 only for a deliberate "
            "proof run against a disposable calendar"
        )
        return claim
    gw = _gateway()
    raw = await gw.think(_prompt(ask, now), tier=CHEAP, caller="track_a")
    data = _robust_json(raw)
    if not isinstance(data, dict) or not data.get("summary") or not data.get("start_datetime"):
        claim["error"] = f"model did not return a usable event: {str(raw)[:120]}"
        return claim
    # validate the datetimes are real + future (no faking a malformed event into existence)
    try:
        start = datetime.fromisoformat(str(data["start_datetime"]))
        end = datetime.fromisoformat(str(data.get("end_datetime") or data["start_datetime"]))
    except Exception as e:
        claim["error"] = f"unparseable datetime: {e}"
        return claim
    if start.tzinfo is None or start <= now.astimezone(start.tzinfo if start.tzinfo else None):
        # require an explicit tz and a future start; otherwise refuse (don't create garbage)
        claim["error"] = f"datetime not future/tz-aware: start={data['start_datetime']}"
        return claim
    summary = _LABEL + str(data["summary"]).strip()
    args = {"summary": summary, "start_datetime": start.isoformat(), "end_datetime": end.isoformat(),
            "approved": True}
    hand = ApiHand(user_id=os.environ["ARCADE_USER_ID"], mode=MODE_LIVE)
    res = await hand.handle(Job(intent="create_event", args=args, risk=Risk.low, goal_id=f"trackA-{abs(hash(ask))%10**8}"))
    claim.update(summary=summary, start_datetime=start.isoformat(), end_datetime=end.isoformat())
    if res.status.value == "success" and res.proof and res.proof.get("id"):
        claim["status"] = "created"
        claim["event_id"] = res.proof["id"]
    else:
        claim["status"] = "failed"
        claim["error"] = res.error or str(res.output)
    return claim
