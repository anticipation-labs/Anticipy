"""Track C — Gmail DRAFT worker (BUILT, NOT VERIFIED — needs the `gmail.compose` tap).

Mirrors Track A's worker but for a Gmail draft via Arcade `Gmail.WriteDraftEmail`. A draft NEVER
sends; recipient is forced to TEST_RECIPIENT (the person's own email) so even if anything ever sent,
it reaches only them. Cannot be verified tonight: `Gmail.WriteDraftEmail` is `pending` (see STATUS).
The moment the scope is granted, `draft_runner.py` proves it for real against the inbox.

LAW: never imports/knows the judge; receives no expected answer; forced safe recipient.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime

from anticipy_engine.core.gateway import CHEAP, PROVIDER_OPENROUTER, ModelGateway
from anticipy_engine.core.envelopes import Job, Risk
from anticipy_engine.hands.api_hand import ApiHand, MODE_LIVE

_LABEL = "[Anticipy test] "


def _robust_json(raw: str):
    if not raw:
        return None
    s = re.sub(r"```(json)?", "", raw).strip()
    try:
        return json.loads(s)
    except Exception:
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


async def do(ask: str) -> dict:
    """Create a real Gmail DRAFT (never sends). Forced recipient = the person's own email."""
    safe_to = os.environ.get("TEST_RECIPIENT") or os.environ.get("ARCADE_USER_ID")
    claim = {"ask": ask, "subject": None, "draft_id": None, "recipient": safe_to,
             "status": "failed", "error": None}
    gw = _gateway()
    prompt = (f'A person said: "{ask}"\nWrite a short email draft for them. Reply ONLY minified JSON '
              '{"subject": <short subject>, "body": <2-4 sentence body>}. No prose, no fences.')
    data = _robust_json(await gw.think(prompt, tier=CHEAP, caller="track_c_draft"))
    if not isinstance(data, dict) or not data.get("subject") or not data.get("body"):
        claim["error"] = "model did not return a usable subject/body"
        return claim
    subject = _LABEL + str(data["subject"]).strip()
    args = {"recipient": safe_to, "subject": subject, "body": str(data["body"]).strip(), "approved": True}
    hand = ApiHand(user_id=os.environ["ARCADE_USER_ID"], mode=MODE_LIVE)
    res = await hand.handle(Job(intent="send_email_draft", args=args, risk=Risk.low,
                                goal_id=f"trackC-{abs(hash(ask))%10**8}"))
    claim["subject"] = subject
    if res.status.value == "success" and res.proof and res.proof.get("id"):
        claim.update(status="created", draft_id=res.proof["id"])
    else:
        claim["error"] = res.error or str(res.output)
    return claim
